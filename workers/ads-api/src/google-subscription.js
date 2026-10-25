/* Google account -> LHM subscription -> concurrent access seats.
 * This control plane NEVER accepts or persists Google Ads/Meta OAuth credentials,
 * account IDs, reports, or campaign data.
 */
import {normalizeEmail,paymentCode,activePlans,entitlement,STATE_ERRORS,planView,
  paymentInstructions,signOutEverywhere,signLease,SEAT_TTL_SECONDS,HEARTBEAT_SECONDS,iso,uuid} from './commerce.js';

const encoder=new TextEncoder();
const hex=b=>Array.from(b,x=>x.toString(16).padStart(2,'0')).join('');
const random=()=>hex(crypto.getRandomValues(new Uint8Array(32)));
const hash=async x=>hex(new Uint8Array(await crypto.subtle.digest('SHA-256',encoder.encode(x))));
const json=(body,status=200,headers={})=>new Response(JSON.stringify(body),{status,headers:{
 'Content-Type':'application/json; charset=utf-8','Cache-Control':'no-store, private',
 'X-Content-Type-Options':'nosniff',...headers}});
const cookie=(name,value,age,path='/')=>name+'='+value+'; Path='+path+'; HttpOnly; Secure; SameSite=Lax; Max-Age='+age;
const extract=(req,name)=>(req.headers.get('cookie')||'').split(';').map(s=>s.trim())
 .find(x=>x.startsWith(name+'='))?.slice(name.length+1)||'';
const seconds=()=>Math.floor(Date.now()/1000);
const oauthReady=e=>!!(e.GOOGLE_CLIENT_ID&&e.GOOGLE_CLIENT_SECRET&&e.COMMERCE_DB);
const headers={ 'Referrer-Policy':'no-referrer', 'X-Frame-Options':'DENY' };
const b64url=x=>btoa(String.fromCharCode(...x)).replace(/\+/g,'-').replace(/\//g,'_').replace(/=+$/,'');
const bytes=s=>Uint8Array.from(atob(s.replace(/-/g,'+').replace(/_/g,'/')+'='.repeat((4-s.length%4)%4)),c=>c.charCodeAt(0));
const UUID_RE=/^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;
const fail=(state,extra={})=>{const e=STATE_ERRORS[state];return json({error:e.error,code:e.code,...extra},e.status);};

async function oidcClaims(jwt,clientId,nonce){
 const parts=String(jwt||'').split('.');
 if(parts.length!==3)throw Error('Invalid identity token');
 const head=JSON.parse(new TextDecoder().decode(bytes(parts[0])));
 const claims=JSON.parse(new TextDecoder().decode(bytes(parts[1])));
 if(head.alg!=='RS256'||!head.kid||
   !['accounts.google.com','https://accounts.google.com'].includes(claims.iss)||
   claims.aud!==clientId||!claims.sub||claims.nonce!==nonce||
   claims.email_verified!==true||typeof claims.email!=='string'||
   !Number.isFinite(claims.exp)||claims.exp<=seconds()||
   !Number.isFinite(claims.iat)||claims.iat>seconds()+60)throw Error('Invalid Google identity');
 const jwksResponse=await fetch('https://www.googleapis.com/oauth2/v3/certs');
 if(!jwksResponse.ok)throw Error('Google signature lookup failed');
 const jwks=await jwksResponse.json();
 const jwk=(jwks.keys||[]).find(x=>x.kid===head.kid&&x.kty==='RSA'&&x.use==='sig');
 if(!jwk)throw Error('Unknown Google signing key');
 const key=await crypto.subtle.importKey('jwk',jwk,{name:'RSASSA-PKCS1-v1_5',hash:'SHA-256'},false,['verify']);
 if(!await crypto.subtle.verify('RSASSA-PKCS1-v1_5',key,bytes(parts[2]),encoder.encode(parts[0]+'.'+parts[1])))
   throw Error('Google signature mismatch');
 const picture=typeof claims.picture==='string'&&/^https:\/\/[a-z0-9.-]+\.googleusercontent\.com\//i.test(claims.picture)
   ?claims.picture.slice(0,500):null;
 return {sub:claims.sub,email:claims.email.trim().toLowerCase(),name:String(claims.name||claims.email).slice(0,120),picture};
}

/* Brief §4.2: the Google `sub` is the identity; the email only matches a customer
 * the first time (e.g. one an admin pre-registered by Gmail). */
export async function linkGoogleIdentity(db,identity){
 const key=normalizeEmail(identity.email);
 if(!key)return {error:'invalid_email'};
 const bySub=await db.prepare('SELECT id,status FROM customers WHERE google_sub=?').bind(identity.sub).first();
 if(bySub){
   if(bySub.status==='blocked')return {error:'blocked'};
   await db.prepare('UPDATE customers SET email=?,name=?,picture_url=?,updated_at=CURRENT_TIMESTAMP WHERE id=?')
     .bind(identity.email,identity.name,identity.picture,bySub.id).run().catch(async()=>{
       // Another customer row already uses that exact email string; keep ours, refresh the rest.
       await db.prepare('UPDATE customers SET name=?,picture_url=?,updated_at=CURRENT_TIMESTAMP WHERE id=?')
         .bind(identity.name,identity.picture,bySub.id).run();
     });
   return {id:bySub.id};
 }
 const byKey=await db.prepare('SELECT id,status,google_sub FROM customers WHERE email_key=?').bind(key).first();
 if(byKey){
   if(byKey.google_sub&&byKey.google_sub!==identity.sub)return {error:'mismatch'};
   if(byKey.status==='blocked')return {error:'blocked'};
   const linked=await db.prepare('UPDATE customers SET google_sub=?,picture_url=?,updated_at=CURRENT_TIMESTAMP WHERE id=? AND google_sub IS NULL')
     .bind(identity.sub,identity.picture,byKey.id).run();
   if(linked.meta.changes!==1)return {error:'mismatch'};
   await db.prepare('INSERT INTO admin_audit(id,actor,action,target_id,detail) VALUES(?,?,?,?,?)')
     .bind(uuid(),'google-signin','google_linked',byKey.id,'email_key='+key).run();
   return {id:byKey.id};
 }
 const id=uuid();
 await db.prepare('INSERT INTO customers(id,name,email,email_key,google_sub,picture_url,updated_at) VALUES(?,?,?,?,?,?,CURRENT_TIMESTAMP)')
   .bind(id,identity.name,identity.email,key,identity.sub,identity.picture).run();
 return {id,created:true};
}

async function user(req,db,{allowBlocked=false}={}){
 const authorization=req.headers.get('Authorization')||'';
 let row=null,desktop=false;
 if(/^Bearer [a-f0-9]{64}$/.test(authorization)){
   row=await db.prepare('SELECT c.id,c.name,c.email,c.status,c.google_sub,c.picture_url FROM desktop_sessions s JOIN customers c ON c.id=s.customer_id WHERE s.token_hash=? AND s.expires_at>?')
     .bind(await hash(authorization.slice(7)),iso(Date.now())).first();
   desktop=true;
 }else{
   const token=extract(req,'lhm_google_session');
   if(!/^[a-f0-9]{64}$/.test(token))return null;
   row=await db.prepare("SELECT c.id,c.name,c.email,c.status,c.google_sub,c.picture_url FROM customer_sessions s JOIN customers c ON c.id=s.customer_id WHERE s.token_hash=? AND s.expires_at>?")
     .bind(await hash(token),iso(Date.now())).first();
 }
 if(!row?.google_sub)return null;
 if(row.status!=='active'&&!allowBlocked)return null;
 return {...row,desktop};
}
function safeReturn(request){
 const u=new URL(request.url);
 // Only allow our own fixed pairing destination or /local/. Never an arbitrary URL.
 const pending=extract(request,'lhm_oauth_pair');
 return u.origin+(pending&&UUID_RE.test(pending)?'/desktop/pair/?id='+pending:'/local/');
}
async function readBody(req){
 if(req.headers.get('content-type')?.split(';')[0]!=='application/json')return null;
 if(Number(req.headers.get('content-length')||0)>1024)return null;
 const raw=await req.text();
 if(raw.length>1024)return null;
 try{return JSON.parse(raw);}catch{return null;}
}
const cleanLabel=v=>String(v||'').replace(/[^\p{L}\p{N} ._-]/gu,'').trim().slice(0,40)||null;
async function seatsOf(db,licenseId){
 const rows=await db.prepare('SELECT client_hash,platform,device_label,last_seen_at,first_seen_at FROM license_seats WHERE license_id=? AND last_seen_at>=? ORDER BY last_seen_at DESC')
   .bind(licenseId,iso(Date.now()-SEAT_TTL_SECONDS*1000)).all();
 return rows.results||[];
}
const deviceView=(row,current)=>({id:row.client_hash.slice(0,12),platform:row.platform||null,
 label:row.device_label||(row.platform==='windows'?'Máy tính Windows':'Trình duyệt'),
 last_seen_at:row.last_seen_at,current:row.client_hash===current});

async function expireStaleOrders(db,customerId){
 await db.prepare("UPDATE orders SET status='cancelled' WHERE customer_id=? AND status='pending' AND expires_at IS NOT NULL AND expires_at<=?")
   .bind(customerId,iso(Date.now())).run();
}

export async function googleSubscription(req,env){
 const url=new URL(req.url),path=url.pathname,method=req.method,db=env.COMMERCE_DB;
 if(!db)return json({error:'Subscription database unavailable'},503);
 if(path==='/api/auth/google/start'&&method==='GET'){
   if(!oauthReady(env))return json({error:'Google Sign-In not configured'},503);
   const state=random(),nonce=random(),verifier=random();
   const pair=url.searchParams.get('pair')||'';
   if(pair&&!UUID_RE.test(pair))return json({error:'Invalid PC pairing reference'},400);
   const digest=new Uint8Array(await crypto.subtle.digest('SHA-256',encoder.encode(verifier)));
   const params=new URLSearchParams({client_id:env.GOOGLE_CLIENT_ID,redirect_uri:url.origin+'/api/auth/google/callback',
    response_type:'code',scope:'openid email profile',state,nonce,code_challenge:b64url(digest),
    code_challenge_method:'S256',prompt:'select_account'});
   const h=new Headers({Location:'https://accounts.google.com/o/oauth2/v2/auth?'+params,...headers,'Cache-Control':'no-store'});
   h.append('Set-Cookie',cookie('lhm_oauth_flow',state+'.'+nonce+'.'+verifier,300));
   h.append('Set-Cookie',cookie('lhm_oauth_pair',pair,300));
   return new Response(null,{status:302,headers:h});
 }
 if(path==='/api/auth/google/callback'&&method==='GET'){
   const data=extract(req,'lhm_oauth_flow').split('.');
   const validFlow=data.length===3&&data.every(x=>/^[a-f0-9]{64}$/.test(x))&&
     url.searchParams.get('state')===data[0]&&!!url.searchParams.get('code');
   const cleared=cookie('lhm_oauth_flow','',0);
   if(!validFlow)return json({error:'Google sign-in expired. Please try again.'},401,{'Set-Cookie':cleared});
   try{
     const res=await fetch('https://oauth2.googleapis.com/token',{method:'POST',headers:{'Content-Type':'application/x-www-form-urlencoded'},
      body:new URLSearchParams({client_id:env.GOOGLE_CLIENT_ID,client_secret:env.GOOGLE_CLIENT_SECRET,
       code:url.searchParams.get('code'),code_verifier:data[2],grant_type:'authorization_code',
       redirect_uri:url.origin+'/api/auth/google/callback'})});
     if(!res.ok)throw Error('Google OAuth exchange failed');
     const token=await res.json();
     const identity=await oidcClaims(token.id_token,env.GOOGLE_CLIENT_ID,data[1]);
     const linked=await linkGoogleIdentity(db,identity);
     if(linked.error==='blocked')
       return json({error:STATE_ERRORS.blocked.error,code:'ACCOUNT_BLOCKED'},403,{'Set-Cookie':cleared});
     if(linked.error)return json({error:'Gmail này đã gắn với một tài khoản Google khác. Liên hệ hỗ trợ.',code:'GOOGLE_ACCOUNT_MISMATCH'},403,{'Set-Cookie':cleared});
     const sessionToken=random();
     await db.prepare('INSERT INTO customer_sessions(token_hash,customer_id,expires_at) VALUES(?,?,?)')
       .bind(await hash(sessionToken),linked.id,iso(Date.now()+7*86400000)).run();
     const h=new Headers({Location:safeReturn(req),'Cache-Control':'no-store',...headers});
     h.append('Set-Cookie',cookie('lhm_oauth_pair','',0));
     // Separate Set-Cookie headers are required; never comma-join cookies.
     h.append('Set-Cookie',cleared);
     h.append('Set-Cookie',cookie('lhm_google_session',sessionToken,7*86400));
     return new Response(null,{status:302,headers:h});
   }catch(_){return json({error:'Google sign-in failed. Check OAuth configuration and D1 migration.'},503,{'Set-Cookie':cleared});}
 }
 if(!path.startsWith('/api/auth/'))return json({error:'Not found'},404);
 if(req.headers.get('origin')&&req.headers.get('origin')!==url.origin)return json({error:'Origin mismatch'},403);
 if(path==='/api/auth/logout'&&method==='POST'){
   const token=extract(req,'lhm_google_session');
   if(/^[a-f0-9]{64}$/.test(token))await db.prepare('DELETE FROM customer_sessions WHERE token_hash=?').bind(await hash(token)).run();
   return json({ok:true},200,{'Set-Cookie':cookie('lhm_google_session','',0)});
 }
 const actor=await user(req,db,{allowBlocked:true});
 if(!actor)return json({authenticated:false,code:'SIGNIN_REQUIRED',error:'Sign in with Google'},401);
 if(actor.status==='blocked')return fail('blocked',{authenticated:true,email:actor.email});
 await expireStaleOrders(db,actor.id);
 const ent=await entitlement(db,actor);
 const plan=ent.license;

 if(path==='/api/auth/session'&&method==='GET'){
   const pending=ent.pending?{...ent.pending,payment:paymentInstructions(env,ent.pending)}:null;
   const seats=plan?{occupied:(await seatsOf(db,plan.id)).length,limit:plan.seat_limit}:null;
   return json({authenticated:true,account_id:actor.id,email:actor.email,name:actor.name,picture:actor.picture_url||null,
    state:ent.state,subscribed:ent.state==='active',plan:planView(plan),pending_order:pending,seats,
    expired_at:ent.expired_at||null,heartbeat_seconds:HEARTBEAT_SECONDS});
 }
 if(path==='/api/auth/plans'&&method==='GET'){
   return json({plans:(await activePlans(db)).map(p=>({...p,available:true}))});
 }
 if(path==='/api/auth/plan'&&method==='POST'){
   const body=await readBody(req);
   const code=String(body?.plan_code||'');
   const chosen=(await activePlans(db)).find(p=>p.code===code);
   if(!chosen)return json({error:'Invalid subscription plan',code:'INVALID_PLAN'},400);
   if(ent.pending)return json({error:'A pending order already exists',code:'PAYMENT_PENDING',
     pending_order:{...ent.pending,payment:paymentInstructions(env,ent.pending)}},409);
   const pendingHours=Math.min(168,Math.max(1,Number(env.ORDER_PENDING_HOURS)||48));
   const id=uuid(),expires=iso(Date.now()+pendingHours*3600000);
   let created=null;
   for(let attempt=0;attempt<5&&!created;attempt++){
     const payCode=paymentCode();
     try{
       await db.prepare("INSERT INTO orders(id,customer_id,months,seat_limit,amount_vnd,status,plan_code,payment_code,expires_at,source) VALUES(?,?,?,?,?,'pending',?,?,?,'self_service')")
         .bind(id,actor.id,chosen.months,chosen.seat_limit,chosen.price_vnd,chosen.code,payCode,expires).run();
       created=payCode;
     }catch(e){if(!/UNIQUE/.test(String(e)))throw e;}
   }
   if(!created)return json({error:'Could not allocate a payment code, try again'},503);
   const order={id,payment_code:created,amount_vnd:chosen.price_vnd,plan_code:chosen.code,plan_name:chosen.name,
     months:chosen.months,seat_limit:chosen.seat_limit,expires_at:expires};
   return json({...order,status:'pending',payment:paymentInstructions(env,order),
     message:'Payment must be independently verified by admin'},201);
 }
 if(path==='/api/auth/order/cancel'&&method==='POST'){
   const body=await readBody(req);
   const id=String(body?.order_id||'');
   const r=await db.prepare("UPDATE orders SET status='cancelled' WHERE id=? AND customer_id=? AND status='pending'")
     .bind(id,actor.id).run();
   if(r.meta.changes!==1)return json({error:'No pending order to cancel'},409);
   return json({ok:true});
 }
 if(path==='/api/auth/devices'&&method==='GET'){
   if(!plan)return fail(ent.state);
   const client=url.searchParams.get('client_id')||'';
   const current=UUID_RE.test(client)?await hash(plan.id+':'+client):'';
   return json({seat_limit:plan.seat_limit,devices:(await seatsOf(db,plan.id)).map(r=>deviceView(r,current))});
 }
 if(path==='/api/auth/devices/signout-all'&&method==='POST'){
   await db.batch(signOutEverywhere(db,actor.id));
   return json({ok:true},200,{'Set-Cookie':cookie('lhm_google_session','',0)});
 }
 if(path==='/api/auth/seat'&&method==='POST'){
   if(!plan)return fail(ent.state);
   const data=await readBody(req);
   const client=String(data?.client_id||'');
   if(!UUID_RE.test(client))return json({error:'Invalid client identifier'},400);
   const mode=['attach','heartbeat','takeover'].includes(data?.mode)?data.mode:'attach';
   const platform=actor.desktop?'windows':'pwa';
   const label=cleanLabel(data?.device_label);
   const clientHash=await hash(plan.id+':'+client);
   const since=iso(Date.now()-SEAT_TTL_SECONDS*1000),now=iso(Date.now());
   // Remove expired seats; only licenses and random client IDs are stored.
   await db.prepare('DELETE FROM license_seats WHERE license_id=? AND last_seen_at<?').bind(plan.id,since).run();
   const old=await db.prepare('SELECT client_hash FROM license_seats WHERE license_id=? AND client_hash=?').bind(plan.id,clientHash).first();
   if(old){
     await db.prepare('UPDATE license_seats SET last_seen_at=?,device_label=COALESCE(?,device_label) WHERE license_id=? AND client_hash=?')
       .bind(now,label,plan.id,clientHash).run();
   }else{
     if(mode==='heartbeat')return json({error:'Gmail này đang dùng trên máy khác.',code:'SEAT_REPLACED'},409);
     const insert=()=>db.prepare('INSERT INTO license_seats(license_id,client_hash,last_seen_at,first_seen_at,platform,device_label) SELECT ?,?,?,?,?,? WHERE (SELECT COUNT(*) FROM license_seats WHERE license_id=?)<?')
       .bind(plan.id,clientHash,now,now,platform,label,plan.id,plan.seat_limit).run();
     // Single conditional write prevents two simultaneous new clients from over-allocating.
     let inserted=await insert();
     if(inserted.meta.changes!==1){
       if(mode!=='takeover'){
         return json({error:'Đã dùng hết số máy của gói.',code:'SEAT_LIMIT',seat_limit:plan.seat_limit,
           devices:(await seatsOf(db,plan.id)).map(r=>deviceView(r,''))},409);
       }
       // The customer confirmed: sign out the least recently active device.
       await db.prepare('DELETE FROM license_seats WHERE license_id=? AND client_hash=(SELECT client_hash FROM license_seats WHERE license_id=? ORDER BY last_seen_at ASC,client_hash ASC LIMIT 1)')
         .bind(plan.id,plan.id).run();
       inserted=await insert();
       if(inserted.meta.changes!==1)return json({error:'Seat limit reached. Please retry.',code:'SEAT_LIMIT'},409);
     }
   }
   const count=await db.prepare('SELECT COUNT(*) AS n FROM license_seats WHERE license_id=?').bind(plan.id).first();
   const response={active:true,account_id:actor.id,account_email:actor.email,expires_at:plan.expires_at,
     seat_limit:plan.seat_limit,occupied:count?.n||0,ttl_seconds:SEAT_TTL_SECONDS,heartbeat_seconds:HEARTBEAT_SECONDS,
     plan:planView(plan)};
   // Only the Windows app gets an offline lease; it is bound to this seat and plan.
   if(actor.desktop){
     const lease=await signLease(env,{customer:actor,license:plan,clientHash});
     if(lease)response.lease=lease;
   }
   return json(response);
 }
 return json({error:'Unknown endpoint'},404);
}

// Used by browser-side PC approval; only a verified Google cookie can authorize it.
export async function googleSessionActor(request,db){
 if((request.headers.get('Authorization')||'').length)return null;
 return user(request,db);
}
