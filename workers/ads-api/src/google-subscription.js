/* Google account -> LHM subscription -> concurrent access seats.
 * This control plane NEVER accepts or persists Google Ads/Meta OAuth credentials,
 * account IDs, reports, or campaign data.
 */
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
const iso=ms=>new Date(ms).toISOString();
const isActive=l=>l&&l.status==='active'&&Date.parse(l.expires_at)>Date.now();
const oauthReady=e=>!!(e.GOOGLE_CLIENT_ID&&e.GOOGLE_CLIENT_SECRET&&e.COMMERCE_DB);
const headers={ 'Referrer-Policy':'no-referrer', 'X-Frame-Options':'DENY' };
const b64url=x=>btoa(String.fromCharCode(...x)).replace(/\+/g,'-').replace(/\//g,'_').replace(/=+$/,'');
const bytes=s=>Uint8Array.from(atob(s.replace(/-/g,'+').replace(/_/g,'/')+'='.repeat((4-s.length%4)%4)),c=>c.charCodeAt(0));
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
 return {sub:claims.sub,email:claims.email.trim().toLowerCase(),name:String(claims.name||claims.email).slice(0,120)};
}
async function user(req,db){
 const authorization=req.headers.get('Authorization')||'';
 if(new URL(req.url).pathname==='/api/auth/seat'&&/^Bearer [a-f0-9]{64}$/.test(authorization)){
   const secret=authorization.slice(7);
   const native=await db.prepare('SELECT c.id,c.name,c.email,c.status,c.google_sub FROM desktop_sessions s JOIN customers c ON c.id=s.customer_id WHERE s.token_hash=? AND s.expires_at>?')
     .bind(await hash(secret),iso(Date.now())).first();
   return native?.status==='active'&&native.google_sub?native:null;
 }
 const token=extract(req,'lhm_google_session');
 if(!/^[a-f0-9]{64}$/.test(token))return null;
 const row=await db.prepare("SELECT c.id,c.name,c.email,c.status,c.google_sub FROM customer_sessions s JOIN customers c ON c.id=s.customer_id WHERE s.token_hash=? AND s.expires_at>?")
  .bind(await hash(token),iso(Date.now())).first();
 return row?.status==='active'&&row.google_sub?row:null;
}
async function license(db,id){
 return db.prepare("SELECT id,status,expires_at,seat_limit FROM licenses WHERE customer_id=? AND status='active' AND expires_at>? ORDER BY expires_at DESC LIMIT 1")
   .bind(id,iso(Date.now())).first();
}
function safeReturn(request){
 const u=new URL(request.url);
 // Only allow our own fixed pairing destination or /local/. Never an arbitrary URL.
 const pending=extract(request,'lhm_oauth_pair');
 return u.origin+(pending&&/^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i.test(pending)
  ?'/desktop/pair/?id='+pending:'/local/');
}
async function readBody(req){
 if(req.headers.get('content-type')?.split(';')[0]!=='application/json')return null;
 if(Number(req.headers.get('content-length')||0)>1024)return null;
 const raw=await req.text();
 if(raw.length>1024)return null;
 try{return JSON.parse(raw);}catch{return null;}
}
export async function googleSubscription(req,env){
 const url=new URL(req.url),path=url.pathname,method=req.method,db=env.COMMERCE_DB;
 if(!db)return json({error:'Subscription database unavailable'},503);
 if(path==='/api/auth/google/start'&&method==='GET'){
   if(!oauthReady(env))return json({error:'Google Sign-In not configured'},503);
   const state=random(),nonce=random(),verifier=random();
   const pair=url.searchParams.get('pair')||'';
   if(pair&&!/^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i.test(pair))
     return json({error:'Invalid PC pairing reference'},400);
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
     // Identity is the stable Google sub, not a Gmail string or Ads token.
     const existing=await db.prepare('SELECT id,google_sub FROM customers WHERE email=?').bind(identity.email).first();
     const id=existing?.id||crypto.randomUUID();
     if(existing?.google_sub&&existing.google_sub!==identity.sub)return json({error:'Google account mismatch'},403,{'Set-Cookie':cleared});
     if(existing){
       await db.prepare('UPDATE customers SET google_sub=? WHERE id=? AND (google_sub IS NULL OR google_sub=?)')
         .bind(identity.sub,id,identity.sub).run();
     }else{
       await db.prepare('INSERT INTO customers(id,name,email,google_sub) VALUES(?,?,?,?)')
         .bind(id,identity.name,identity.email,identity.sub).run();
     }
     const sessionToken=random();
     await db.prepare('INSERT INTO customer_sessions(token_hash,customer_id,expires_at) VALUES(?,?,?)')
       .bind(await hash(sessionToken),id,iso(Date.now()+7*86400000)).run();
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
 const actor=await user(req,db);
 if(!actor)return json({authenticated:false,error:'Sign in with Google'},401);
 const plan=await license(db,actor.id);
 if(path==='/api/auth/session'&&method==='GET'){
   const pending=await db.prepare("SELECT id,seat_limit,amount_vnd,months FROM orders WHERE customer_id=? AND status='pending' ORDER BY created_at DESC LIMIT 1").bind(actor.id).first();
   return json({authenticated:true,account_id:actor.id,email:actor.email,name:actor.name,
    subscribed:!!plan,plan:plan?{expires_at:plan.expires_at,seat_limit:plan.seat_limit}:null,pending_order:pending||null});
 }
 if(path==='/api/auth/plans'&&method==='GET'){
   const items=[1,3,5].map(seats=>({seats,months:1,price_vnd:Number(env['PRICE_SEAT_'+seats]||0)}));
   return json({plans:items.map(x=>({...x,available:Number.isSafeInteger(x.price_vnd)&&x.price_vnd>0}))});
 }
 if(path==='/api/auth/plan'&&method==='POST'){
   const body=await readBody(req);
   const seats=Number(body?.seats);
   if(![1,3,5].includes(seats))return json({error:'Invalid subscription plan'},400);
   const amount=Number(env['PRICE_SEAT_'+seats]||0);
   if(!Number.isSafeInteger(amount)||amount<=0)return json({error:'Plan price has not been configured'},503);
   const pending=await db.prepare("SELECT id,seat_limit,amount_vnd FROM orders WHERE customer_id=? AND status='pending' ORDER BY created_at DESC LIMIT 1").bind(actor.id).first();
   if(pending)return json({error:'A pending order already exists',pending_order:pending},409);
   const id=crypto.randomUUID();
   await db.prepare("INSERT INTO orders(id,customer_id,months,seat_limit,amount_vnd,status) VALUES(?,?,1,?,?,'pending')")
     .bind(id,actor.id,seats,amount).run();
   return json({order_id:id,seats,amount_vnd:amount,status:'pending',message:'Payment must be independently verified by admin'},201);
 }
 if(path==='/api/auth/seat'&&method==='POST'){
   if(!isActive(plan))return json({error:'Subscription required',code:'SUBSCRIPTION_REQUIRED'},403);
   const data=await readBody(req);
   const client=String(data?.client_id||'');
   if(!/^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i.test(client))
     return json({error:'Invalid client identifier'},400);
   const clientHash=await hash(plan.id+':'+client);
   const heartbeat=data?.mode==='heartbeat';
   const since=iso(Date.now()-120000),now=iso(Date.now());
   // Remove expired seats; only licenses and random client IDs are stored.
   await db.prepare('DELETE FROM license_seats WHERE license_id=? AND last_seen_at<?').bind(plan.id,since).run();
   // Existing slot: refresh without changing the count.
   const old=await db.prepare('SELECT client_hash FROM license_seats WHERE license_id=? AND client_hash=?').bind(plan.id,clientHash).first();
   if(old){
     await db.prepare('UPDATE license_seats SET last_seen_at=? WHERE license_id=? AND client_hash=?').bind(now,plan.id,clientHash).run();
   }else{
     if(heartbeat)return json({error:'Session seat replaced',code:'SEAT_REPLACED'},409);
     // Single conditional write prevents two simultaneous new clients from over-allocating.
     const inserted=await db.prepare('INSERT INTO license_seats(license_id,client_hash,last_seen_at) SELECT ?,?,? WHERE (SELECT COUNT(*) FROM license_seats WHERE license_id=?)<?')
       .bind(plan.id,clientHash,now,plan.id,plan.seat_limit).run();
     if(inserted.meta.changes!==1){
       // No user device-removal UI: displace least-recently-active session.
       await db.prepare('DELETE FROM license_seats WHERE license_id=? AND client_hash=(SELECT client_hash FROM license_seats WHERE license_id=? ORDER BY last_seen_at ASC,client_hash ASC LIMIT 1)')
         .bind(plan.id,plan.id).run();
       const retry=await db.prepare('INSERT INTO license_seats(license_id,client_hash,last_seen_at) SELECT ?,?,? WHERE (SELECT COUNT(*) FROM license_seats WHERE license_id=?)<?')
         .bind(plan.id,clientHash,now,plan.id,plan.seat_limit).run();
       if(retry.meta.changes!==1)return json({error:'Seat limit reached. Please retry.'},409);
     }
   }
   const count=await db.prepare('SELECT COUNT(*) AS n FROM license_seats WHERE license_id=?').bind(plan.id).first();
   return json({active:true,expires_at:plan.expires_at,seat_limit:plan.seat_limit,occupied:count?.n||0,ttl_seconds:120});
 }
 return json({error:'Unknown endpoint'},404);
}

// Used by browser-side PC approval; only a verified Google cookie can authorize it.
export async function googleSessionActor(request,db){
 if((request.headers.get('Authorization')||'').length)return null;
 return user(request,db);
}
