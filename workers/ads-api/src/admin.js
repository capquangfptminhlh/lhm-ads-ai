/* Privileged Cloudflare Access/D1 commercial control-plane. No advertising data. */
const reply=(data,status=200)=>new Response(JSON.stringify(data),{status,headers:{'content-type':'application/json; charset=utf-8','cache-control':'no-store','x-content-type-options':'nosniff'}});
const uuid=()=>crypto.randomUUID();
const hex=async s=>Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',new TextEncoder().encode(s)))).map(n=>n.toString(16).padStart(2,'0')).join('');
const b64=s=>{const t=s.replace(/-/g,'+').replace(/_/g,'/');return Uint8Array.from(atob(t+'='.repeat((4-t.length%4)%4)),c=>c.charCodeAt(0));};
export async function adminIdentity(req,env){
  const raw=req.headers.get('Cf-Access-Jwt-Assertion');
  if(!raw || !env?.CF_ACCESS_TEAM_DOMAIN || !env?.CF_ACCESS_AUD || !env?.ADMIN_EMAIL)return null;
  const parts=raw.split('.');if(parts.length!==3)return null;
  let hdr,claims;try{hdr=JSON.parse(new TextDecoder().decode(b64(parts[0])));claims=JSON.parse(new TextDecoder().decode(b64(parts[1])));}catch{return null;}
  if(hdr.alg!=='RS256'||!hdr.kid||claims.aud!==env.CF_ACCESS_AUD && !(Array.isArray(claims.aud)&&claims.aud.includes(env.CF_ACCESS_AUD)))return null;
  const domain=String(env.CF_ACCESS_TEAM_DOMAIN).replace(/^https?:\/\//,'').replace(/\/$/,'');
  if(!/^[a-z0-9-]+\.cloudflareaccess\.com$/.test(domain))return null;
  const now=Date.now()/1000;
  if(claims.iss!=='https://'+domain || !Number.isFinite(claims.exp)||claims.exp<=now||!claims.sub)return null;
  if(claims.nbf!==undefined && (!Number.isFinite(claims.nbf)||claims.nbf>now+30))return null;
  if(claims.iat!==undefined && (!Number.isFinite(claims.iat)||claims.iat>now+30))return null;
  const email=String(claims.email||'').toLowerCase();
  if(!email || email!==String(env.ADMIN_EMAIL).trim().toLowerCase())return null;
  try{
    const cert=await fetch('https://'+domain+'/cdn-cgi/access/certs');
    if(!cert.ok)return null;
    const jwks=await cert.json();
    const jwk=(jwks.keys||[]).find(k=>k.kid===hdr.kid&&k.kty==='RSA');
    if(!jwk)return null;
    const key=await crypto.subtle.importKey('jwk',jwk,{name:'RSASSA-PKCS1-v1_5',hash:'SHA-256'},false,['verify']);
    const ok=await crypto.subtle.verify('RSASSA-PKCS1-v1_5',key,b64(parts[2]),new TextEncoder().encode(parts[0]+'.'+parts[1]));
    return ok?email:null;
  }catch{return null;}
}
const permitted=(req,origin)=>req.headers.get('origin')===null||req.headers.get('origin')===origin;
async function body(req){if(Number(req.headers.get('content-length')||0)>10000)throw Error('payload_too_large');const s=await req.text();if(s.length>10000)throw Error('payload_too_large');return JSON.parse(s);}
const string=(v,max)=>typeof v==='string'?v.trim().slice(0,max):'';
async function audit(db,actor,action,target){await db.prepare('INSERT INTO admin_audit(id,actor,action,target_id) VALUES(?,?,?,?)').bind(uuid(),actor,action,target).run();}
export async function adminApi(request,env){
  // Authentication must precede configuration checks to avoid exposing internals.
  const actor=await adminIdentity(request,env);
  if(!actor)return reply({error:'Administrator access required'},401);
  if(!env?.COMMERCE_DB)return reply({error:'Commerce database not configured'},503);
  const url=new URL(request.url);
  if(!permitted(request,url.origin))return reply({error:'Origin mismatch'},403);
  const path=url.pathname,method=request.method,db=env.COMMERCE_DB;
  if(method!=='GET'&&request.headers.get('content-type')?.split(';')[0]!=='application/json')return reply({error:'Expected JSON'},415);
  try{
    if(path==='/api/admin/overview'&&method==='GET'){
      const [customers,orders,licenses,auditLog,fulfilled]=await Promise.all([
        db.prepare('SELECT id,name,email,phone,status,created_at FROM customers ORDER BY created_at DESC LIMIT 100').all(),
        db.prepare('SELECT o.*,c.name AS customer_name, pr.reference AS review_reference, pr.submitted_at AS review_submitted_at FROM orders o JOIN customers c ON c.id=o.customer_id LEFT JOIN payment_reviews pr ON pr.order_id=o.id ORDER BY o.created_at DESC LIMIT 100').all(),
        db.prepare('SELECT l.id,l.customer_id,l.key_hint,l.status,l.expires_at,l.seat_limit,l.created_at,c.name AS customer_name FROM licenses l JOIN customers c ON c.id=l.customer_id ORDER BY l.created_at DESC LIMIT 100').all(),
        db.prepare('SELECT actor,action,target_id,at FROM admin_audit ORDER BY at DESC LIMIT 30').all(),
        db.prepare('SELECT order_id FROM license_fulfillments ORDER BY created_at DESC LIMIT 500').all()]);
      return reply({actor,customers:customers.results,orders:orders.results,licenses:licenses.results,audit:auditLog.results,
        fulfilled_order_ids:fulfilled.results.map(x=>x.order_id)});
    }
    if(path==='/api/admin/customers'&&method==='POST'){
      const x=await body(request),name=string(x.name,120),email=string(x.email,200).toLowerCase(),phone=string(x.phone,40);
      if(!name||!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email))return reply({error:'Invalid name/email'},400);
      const id=uuid();await db.prepare('INSERT INTO customers(id,name,email,phone) VALUES(?,?,?,?)').bind(id,name,email,phone).run();await audit(db,actor,'customer_create',id);
      return reply({id},201);
    }
    if(path==='/api/admin/orders'&&method==='POST'){
      const x=await body(request),months=Number(x.months),amount=Number(x.amount_vnd),customer=string(x.customer_id,50),seats=Number(x.seat_limit||1);
      if(!customer||!Number.isInteger(months)||months<1||months>36||!Number.isSafeInteger(amount)||amount<0||amount>1000000000||![1,3,5].includes(seats))return reply({error:'Invalid order'},400);
      const id=uuid();await db.prepare('INSERT INTO orders(id,customer_id,months,amount_vnd,seat_limit) VALUES(?,?,?,?,?)').bind(id,customer,months,amount,seats).run();await audit(db,actor,'order_create',id);
      return reply({id},201);
    }
    if(path==='/api/admin/payments/review'&&method==='POST'){
      const x=await body(request),id=string(x.order_id,50),ref=string(x.reference,120),note=string(x.note,500);
      if(!id||!ref)return reply({error:'Order and transfer reference required'},400);
      const order=await db.prepare('SELECT status FROM orders WHERE id=?').bind(id).first();
      if(!order||order.status!=='pending')return reply({error:'Order is not pending'},409);
      await db.prepare('INSERT INTO payment_reviews(order_id,reference,note) VALUES(?,?,?) ON CONFLICT(order_id) DO UPDATE SET reference=excluded.reference,note=excluded.note,submitted_at=CURRENT_TIMESTAMP').bind(id,ref,note).run();
      await audit(db,actor,'payment_reference_recorded',id);
      return reply({ok:true});
    }
    if(path==='/api/admin/payments/approve'&&method==='POST'){
      const x=await body(request),id=string(x.order_id,50);
      const review=await db.prepare('SELECT reference FROM payment_reviews WHERE order_id=?').bind(id).first();
      if(!review)return reply({error:'Record and independently verify transfer reference first'},409);
      const changed=await db.prepare("UPDATE orders SET status='paid',paid_at=CURRENT_TIMESTAMP,approved_by=?,reference=? WHERE id=? AND status='pending'").bind(actor,review.reference,id).run();
      if(changed.meta.changes!==1)return reply({error:'Order already processed or missing'},409);
      await audit(db,actor,'payment_approved',id);
      return reply({ok:true});
    }
    if(path==='/api/admin/licenses/issue'&&method==='POST'){
      const x=await body(request),order=await db.prepare("SELECT * FROM orders WHERE id=? AND status='paid'")
        .bind(string(x.order_id,50)).first();
      if(!order)return reply({error:'Paid order required'},409);
      const spent=await db.prepare('SELECT order_id FROM license_fulfillments WHERE order_id=?')
        .bind(order.id).first();
      if(spent)return reply({error:'Order already used for a license'},409);
      const key='LHM-'+Array.from(crypto.getRandomValues(new Uint8Array(24)),v=>v.toString(16).padStart(2,'0')).join('').toUpperCase();
      const expires=new Date();expires.setUTCMonth(expires.getUTCMonth()+order.months);
      // D1 batch is transactional; a unique order_id prevents duplicate fulfillment.
      await db.batch([
        db.prepare('INSERT INTO licenses(id,customer_id,key_hash,key_hint,expires_at,seat_limit) VALUES(?,?,?,?,?,?)')
          .bind(order.id,order.customer_id,await hex(key),key.slice(-8),expires.toISOString(),order.seat_limit||1),
        db.prepare("INSERT INTO license_fulfillments(order_id,license_id,action) VALUES(?,?,'issue')")
          .bind(order.id,order.id),
        db.prepare('INSERT INTO admin_audit(id,actor,action,target_id) VALUES(?,?,?,?)')
          .bind(uuid(),actor,'license_issue',order.id)
      ]);
      return reply({key,expires_at:expires.toISOString(),notice:'Copy now. Raw key is not stored.'},201);
    }
    if(path==='/api/admin/licenses/renew'&&method==='POST'){
      const x=await body(request),id=string(x.license_id,50);
      const order=await db.prepare("SELECT * FROM orders WHERE id=? AND status='paid'")
        .bind(string(x.order_id,50)).first();
      const lic=await db.prepare('SELECT * FROM licenses WHERE id=?').bind(id).first();
      if(!order||!lic||order.customer_id!==lic.customer_id)
        return reply({error:'Matching paid order and license required'},409);
      const spent=await db.prepare('SELECT order_id FROM license_fulfillments WHERE order_id=?')
        .bind(order.id).first();
      if(spent)return reply({error:'Order already used for a license'},409);
      // Compute next expiration *inside SQLite*, so two distinct renewals
      // cannot overwrite each other's expiry based on stale reads.
      await db.batch([
        db.prepare("INSERT INTO license_fulfillments(order_id,license_id,action) VALUES(?,?,'renew')")
          .bind(order.id,id),
        db.prepare(`UPDATE licenses SET
          expires_at=strftime('%Y-%m-%dT%H:%M:%fZ',
            datetime(CASE WHEN julianday(expires_at)>julianday('now')
              THEN expires_at ELSE 'now' END, '+' || ? || ' months')),
          status='active',seat_limit=?,updated_at=CURRENT_TIMESTAMP WHERE id=?`)
          .bind(order.months,order.seat_limit||1,id),
        db.prepare('INSERT INTO admin_audit(id,actor,action,target_id) VALUES(?,?,?,?)')
          .bind(uuid(),actor,'license_renew',order.id)
      ]);
      const result=await db.prepare('SELECT expires_at FROM licenses WHERE id=?').bind(id).first();
      return reply({expires_at:result.expires_at});
    }
    if(path==='/api/admin/licenses/revoke'&&method==='POST'){
      const x=await body(request),id=string(x.license_id,50);
      const c=await db.prepare("UPDATE licenses SET status='revoked',updated_at=CURRENT_TIMESTAMP WHERE id=? AND status='active'").bind(id).run();
      if(c.meta.changes!==1)return reply({error:'License missing or already revoked'},409);
      await audit(db,actor,'license_revoke',id);return reply({ok:true});
    }
    return reply({error:'Unknown administration endpoint'},404);
  }catch(e){
    if(e.message==='payload_too_large')return reply({error:'Payload too large'},413);
    if(e instanceof SyntaxError)return reply({error:'Invalid JSON'},400);
    if(/UNIQUE constraint/.test(String(e)))return reply({error:'Duplicate record'},409);
    if(/FOREIGN KEY constraint/.test(String(e)))return reply({error:'Customer does not exist'},409);
    return reply({error:'Operation failed; check D1 migration and configuration'},500);
  }
}
