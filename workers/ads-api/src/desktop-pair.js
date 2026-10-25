/* One-time PC/browser sign-in pairing. NO advertising credentials, tokens,
 * account numbers, campaign data, or payment card details ever enter this API.
 */
import { googleSessionActor } from './google-subscription.js';
const enc=new TextEncoder();
const hex=buffer=>Array.from(new Uint8Array(buffer),n=>n.toString(16).padStart(2,'0')).join('');
const digest=async value=>hex(await crypto.subtle.digest('SHA-256',enc.encode(value)));
const reply=(data,status=200)=>new Response(JSON.stringify(data),{status,headers:{
 'Content-Type':'application/json; charset=utf-8','Cache-Control':'no-store',
 'X-Content-Type-Options':'nosniff','Referrer-Policy':'no-referrer'}});
const uuid=/^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;
const key=/^[0-9a-f]{64}$/;
const now=()=>new Date().toISOString();
const later=ms=>new Date(Date.now()+ms).toISOString();
const esc=s=>String(s).replace(/[&<>"']/g,x=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[x]));
const page=(heading,description,actions='')=>new Response(
  '<!doctype html><html lang="vi"><meta charset="utf-8">'+
  '<meta name="viewport" content="width=device-width,initial-scale=1">'+
  '<title>LHM Ads AI · Kết nối PC</title><style>body{background:#f4f7fc;'+
  'font:16px/1.6 system-ui;color:#1d3149;margin:0;min-height:100vh;display:grid;place-items:center}'+
  'main{background:white;border:1px solid #dce5ef;border-radius:20px;padding:32px;max-width:490px;margin:16px}'+
  'a,button{display:inline-block;background:#146bd1;border:none;color:white;border-radius:9px;'+
  'padding:12px 16px;font:inherit;font-weight:700;text-decoration:none;cursor:pointer}'+
  'small{color:#536980}</style><main><h2>'+esc(heading)+'</h2><p>'+esc(description)+
  '</p>'+actions+'<p><small>Trang xác thực bản quyền. Không yêu cầu token Google Ads hay Meta Ads.</small></p></main></html>',
  {status:200,headers:{'Content-Type':'text/html; charset=utf-8','Cache-Control':'no-store',
   'X-Content-Type-Options':'nosniff','Referrer-Policy':'no-referrer','X-Frame-Options':'DENY',
   'Content-Security-Policy':"default-src 'none'; style-src 'unsafe-inline'; form-action 'self'; base-uri 'none'; frame-ancestors 'none'"}});
const jsonBody=async req=>{
  if(req.headers.get('content-type')?.split(';')[0]!=='application/json')return null;
  if(Number(req.headers.get('content-length')||0)>256)return null;
  const raw=await req.text();
  if(raw.length>256)return null;
  try{return JSON.parse(raw);}catch{return null;}
};
const originOk=req=>!req.headers.get('origin')||req.headers.get('origin')===new URL(req.url).origin;
const activeLicense=async(db,id)=>db.prepare("SELECT id FROM licenses WHERE customer_id=? AND status='active' AND expires_at>? ORDER BY expires_at DESC LIMIT 1").bind(id,now()).first();
const bearer=req=>(req.headers.get('Authorization')||'').match(/^Bearer ([a-f0-9]{64})$/)?.[1]||null;
export async function desktopPair(req,env){
 const u=new URL(req.url),path=u.pathname,method=req.method,db=env.COMMERCE_DB;
 if(!db)return reply({error:'Commerce D1 not configured'},503);
 if(path==='/api/desktop/pair/start'&&method==='POST'){
   if(!originOk(req))return reply({error:'Origin mismatch'},403);
   const x=await jsonBody(req);
   if(!key.test(x?.verifier_hash||''))return reply({error:'Invalid pairing challenge'},400);
   const id=crypto.randomUUID();
   const code=String(new DataView(crypto.getRandomValues(new Uint8Array(4)).buffer).getUint32(0)%1000000).padStart(6,'0');
   await db.prepare('DELETE FROM desktop_pairings WHERE expires_at<?').bind(now()).run();
   await db.prepare('INSERT INTO desktop_pairings(id,verifier_hash,display_code,expires_at) VALUES(?,?,?,?)')
     .bind(id,x.verifier_hash,code,later(5*60*1000)).run();
   return reply({pair_id:id,display_code:code,verify_url:u.origin+'/desktop/pair/?id='+id,expires_in_seconds:300},201);
 }
 if(path==='/desktop/pair/'&&method==='GET'){
   const id=u.searchParams.get('id')||'';
   if(!uuid.test(id))return page('Liên kết không hợp lệ','Mở lại từ phần mềm LHM Ads AI trên PC.');
   const p=await db.prepare('SELECT display_code,customer_id,expires_at FROM desktop_pairings WHERE id=?').bind(id).first();
   if(!p||p.expires_at<=now())return page('Liên kết đã hết hạn','Vui lòng tạo mã đăng nhập mới trên PC.');
   const actor=await googleSessionActor(req,db);
   if(!actor){
     return page('Đăng nhập Google để dùng trên PC','Đối chiếu mã '+p.display_code+
       ' đang hiển thị trên máy tính rồi đăng nhập Gmail của bạn.',
       '<a href="/api/auth/google/start?pair='+id+'">Đăng nhập bằng Google</a>');
   }
   if(p.customer_id)return page('Đã xác nhận','Quay lại ứng dụng PC để hoàn tất kích hoạt.');
   if(!await activeLicense(db,actor.id))
     return page('Cần đăng ký gói','Tài khoản '+actor.email+
       ' chưa có bản quyền còn hạn. Chọn gói và thanh toán trên trang LHM Ads trước.',
       '<a href="/local/">Chọn gói dịch vụ</a>');
   return page('Xác nhận PC của bạn','Gmail: '+actor.email+' · Mã đối chiếu: '+p.display_code+
     '. Chỉ xác nhận nếu mã trên PC trùng khớp.',
     '<form action="/api/desktop/pair/approve" method="post">'+
     '<input type="hidden" name="id" value="'+id+'"><button type="submit">Cho phép máy tính đăng nhập</button></form>');
 }
 if(path==='/api/desktop/pair/approve'&&method==='POST'){
   // Require explicit same-origin browser form submission, not just SameSite cookie.
   if(req.headers.get('origin')!==u.origin)return reply({error:'Origin mismatch'},403);
   if(req.headers.get('content-type')?.split(';')[0]!=='application/x-www-form-urlencoded')return reply({error:'Bad form'},415);
   const raw=await req.text(); if(raw.length>200)return reply({error:'Form too large'},413);
   const id=new URLSearchParams(raw).get('id')||'';
   if(!uuid.test(id))return reply({error:'Invalid request'},400);
   const actor=await googleSessionActor(req,db);
   if(!actor)return page('Cần đăng nhập Google','Quay lại liên kết xác thực trên máy tính.');
   if(!await activeLicense(db,actor.id))
     return page('Chưa có gói dịch vụ','Đăng ký gói bản quyền trước khi xác nhận PC.',
       '<a href="/local/">Chọn gói</a>');
   const res=await db.prepare('UPDATE desktop_pairings SET customer_id=? WHERE id=? AND customer_id IS NULL AND expires_at>?')
     .bind(actor.id,id,now()).run();
   if(res.meta.changes!==1)return page('Không xác nhận được','Liên kết đã dùng hoặc hết hạn. Thử lại trên PC.');
   return page('Đã xác nhận thành công','Quay lại phần mềm LHM Ads AI trên PC. Không cần nhập key.');
 }
 if(path==='/api/desktop/pair/claim'&&method==='POST'){
   if(!originOk(req))return reply({error:'Origin mismatch'},403);
   const x=await jsonBody(req);
   if(!uuid.test(x?.pair_id||'')||!key.test(x?.verifier||''))return reply({error:'Invalid pairing proof'},400);
   const verifierHash=await digest(x.verifier);
   const p=await db.prepare('SELECT customer_id FROM desktop_pairings WHERE id=? AND verifier_hash=? AND expires_at>?')
     .bind(x.pair_id,verifierHash,now()).first();
   if(!p)return reply({error:'Pairing has expired'},410);
   if(!p.customer_id)return reply({status:'pending'},202);
   if(!await activeLicense(db,p.customer_id))return reply({error:'Paid subscription required'},403);
   const deleted=await db.prepare('DELETE FROM desktop_pairings WHERE id=? AND verifier_hash=? AND customer_id=? AND expires_at>?')
     .bind(x.pair_id,verifierHash,p.customer_id,now()).run();
   if(deleted.meta.changes!==1)return reply({error:'Pairing already consumed'},409);
   const session=hex(crypto.getRandomValues(new Uint8Array(32)));
   const actor=await db.prepare('SELECT email FROM customers WHERE id=?').bind(p.customer_id).first();
   await db.prepare('INSERT INTO desktop_sessions(token_hash,customer_id,expires_at) VALUES(?,?,?)')
     .bind(await digest(session),p.customer_id,later(30*86400000)).run();
   return reply({status:'authorized',desktop_token:session,email:actor?.email||'',expires_in_seconds:30*86400});
 }
 if(path==='/api/desktop/session/logout'&&method==='POST'){
   if(!originOk(req))return reply({error:'Origin mismatch'},403);
   const token=bearer(req);
   if(!token)return reply({error:'Desktop authentication required'},401);
   await db.prepare('DELETE FROM desktop_sessions WHERE token_hash=?').bind(await digest(token)).run();
   return reply({ok:true});
 }
 return reply({error:'Unknown desktop pairing endpoint'},404);
}
