/* Customer PWA accounts; separate from privileged Cloudflare Access Admin.
   Passwords and raw session tokens are never stored in D1. No Ads account data. */
const respond=(x,s=200,extra={})=>new Response(JSON.stringify(x),{status:s,headers:{'content-type':'application/json; charset=utf-8','cache-control':'no-store, private','x-content-type-options':'nosniff',...extra}});
const enc=new TextEncoder();
const hex=bytes=>Array.from(bytes,x=>x.toString(16).padStart(2,'0')).join('');
const sha=async s=>hex(new Uint8Array(await crypto.subtle.digest('SHA-256',enc.encode(s))));
const salt=()=>hex(crypto.getRandomValues(new Uint8Array(16)));
const iterations=210000;
async function passwordHash(password,s){
 const key=await crypto.subtle.importKey('raw',enc.encode(password),'PBKDF2',false,['deriveBits']);
 return hex(new Uint8Array(await crypto.subtle.deriveBits({name:'PBKDF2',salt:enc.encode(s),iterations,hash:'SHA-256'},key,256)));
}
const goodEmail=s=>typeof s==='string'&&s.length<=200&&/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(s);
const cookie=(token,age)=>'lhm_session='+token+'; Path=/; HttpOnly; Secure; SameSite=Strict; Max-Age='+age;
const now=()=>new Date().toISOString();
const expires=()=>new Date(Date.now()+7*86400000).toISOString();
function active(license){return !!(license && license.status==='active' && Date.parse(license.expires_at)>Date.now());}
async function jsonBody(req){
 if(req.headers.get('content-type')?.split(';')[0]!=='application/json')return null;
 if(Number(req.headers.get('content-length')||0)>1500)return null;
 const s=await req.text();if(s.length>1500)return null;
 try{return JSON.parse(s);}catch{return null;}
}
async function session(req,db){
 const token=(req.headers.get('cookie')||'').split(';').map(x=>x.trim()).find(x=>x.startsWith('lhm_session='))?.slice(12);
 if(!token||!/^[a-f0-9]{64}$/.test(token))return null;
 const row=await db.prepare(`SELECT s.customer_id,c.name,c.email,c.status AS customer_status,l.expires_at,l.status AS license_status
   FROM customer_sessions s JOIN customers c ON c.id=s.customer_id
   JOIN licenses l ON l.customer_id=c.id
   WHERE s.token_hash=? AND s.expires_at>? ORDER BY l.expires_at DESC LIMIT 1`).bind(await sha(token),now()).first();
 return row && row.customer_status==='active' && active({status:row.license_status,expires_at:row.expires_at})?row:null;
}
async function issue(db,customerId){
 const token=hex(crypto.getRandomValues(new Uint8Array(32)));
 await db.prepare('INSERT INTO customer_sessions(token_hash,customer_id,expires_at) VALUES(?,?,?)').bind(await sha(token),customerId,expires()).run();
 return cookie(token,7*86400);
}
export async function customerAuth(req,env){
 const u=new URL(req.url),path=u.pathname,method=req.method;
 if(!env?.COMMERCE_DB)return respond({error:'Database not available'},503);
 if(req.headers.get('origin') && req.headers.get('origin')!==u.origin)return respond({error:'Origin mismatch'},403);
 const db=env.COMMERCE_DB;
 try{
  if(path==='/api/customer/session'&&method==='GET'){
   const user=await session(req,db);
   return user?respond({authenticated:true,name:user.name,email:user.email,expires_at:user.expires_at}):respond({authenticated:false},401);
  }
  if(path==='/api/customer/logout'&&method==='POST'){
   const token=(req.headers.get('cookie')||'').split(';').map(x=>x.trim()).find(x=>x.startsWith('lhm_session='))?.slice(12);
   if(token&&/^[a-f0-9]{64}$/.test(token))await db.prepare('DELETE FROM customer_sessions WHERE token_hash=?').bind(await sha(token)).run();
   return respond({ok:true},200,{'set-cookie':cookie('',0)});
  }
  if(!['/api/customer/activate','/api/customer/login'].includes(path)||method!=='POST')return respond({error:'Method not allowed'},405);
  const x=await jsonBody(req);
  if(!x)return respond({error:'Invalid request'},400);
  const email=typeof x.email==='string'?x.email.trim().toLowerCase():'';
  const password=x.password;
  if(!goodEmail(email)||typeof password!=='string'||password.length<12||password.length>128)return respond({error:'Email or password invalid (minimum 12 characters)'},400);
  const customer=await db.prepare('SELECT id,status FROM customers WHERE email=?').bind(email).first();
  if(path==='/api/customer/activate'){
   const key=typeof x.key==='string'?x.key.trim().toUpperCase():'';
   if(!/^LHM-[A-F0-9]{48}$/.test(key)||!customer||customer.status!=='active')return respond({error:'Activation failed'},403);
   const lic=await db.prepare('SELECT status,expires_at FROM licenses WHERE customer_id=? AND key_hash=?').bind(customer.id,await sha(key)).first();
   if(!active(lic))return respond({error:'Activation failed'},403);
   const s=salt(),hash=await passwordHash(password,s);
   const inserted=await db.prepare('INSERT OR IGNORE INTO customer_auth(customer_id,password_salt,password_hash) VALUES(?,?,?)').bind(customer.id,s,hash).run();
   if(inserted.meta.changes!==1)return respond({error:'Account already activated. Please sign in.'},409);
   return respond({ok:true,message:'Account activated. Sign in with your password.'},201);
  }
  // Use generic authentication errors; account existence is not leaked.
  if(!customer||customer.status!=='active')return respond({error:'Invalid credentials or subscription'},401);
  const record=await db.prepare('SELECT * FROM customer_auth WHERE customer_id=?').bind(customer.id).first();
  if(!record)return respond({error:'Invalid credentials or subscription'},401);
  if(record.locked_until&&Date.parse(record.locked_until)>Date.now())return respond({error:'Too many attempts. Try again later.'},429);
  const computed=await passwordHash(password,record.password_salt);
  if(computed!==record.password_hash){
   const count=Number(record.failed_attempts||0)+1;
   await db.prepare('UPDATE customer_auth SET failed_attempts=?,locked_until=? WHERE customer_id=?')
     .bind(count,count>=5?new Date(Date.now()+15*60000).toISOString():null,customer.id).run();
   return respond({error:'Invalid credentials or subscription'},401);
  }
  const lic=await db.prepare('SELECT status,expires_at FROM licenses WHERE customer_id=? ORDER BY expires_at DESC LIMIT 1').bind(customer.id).first();
  if(!active(lic))return respond({error:'Subscription expired or revoked'},403);
  await db.prepare('UPDATE customer_auth SET failed_attempts=0,locked_until=NULL WHERE customer_id=?').bind(customer.id).run();
  return respond({ok:true,expires_at:lic.expires_at},200,{'set-cookie':await issue(db,customer.id)});
 }catch(_){return respond({error:'Account service temporarily unavailable'},503);}
}
