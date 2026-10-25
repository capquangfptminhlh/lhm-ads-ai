/* Privileged Cloudflare Access/D1 commercial control-plane. No advertising data. */
import {normalizeEmail,validEmail,fulfillPaidOrder,grantFromOrder,signOutEverywhere,iso,SEAT_TTL_SECONDS} from './commerce.js';
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
async function audit(db,actor,action,target,detail=null){await db.prepare('INSERT INTO admin_audit(id,actor,action,target_id,detail) VALUES(?,?,?,?,?)').bind(uuid(),actor,action,target,detail).run();}
const auditStmt=(db,actor,action,target,detail=null)=>db.prepare('INSERT INTO admin_audit(id,actor,action,target_id,detail) VALUES(?,?,?,?,?)').bind(uuid(),actor,action,target,detail);
const CUSTOMER_PATH=/^\/api\/admin\/customers\/([0-9a-f-]{36})(?:\/(block|unblock|unlink-google|signout-all|notes))?$/i;
const LICENSE_PATH=/^\/api\/admin\/licenses\/([0-9a-f-]{36})\/transfer$/i;
/* Find a customer by Gmail (normalized), or create an unlinked one the
 * customer claims on first Google sign-in. */
async function customerByEmail(db,email,name){
  const key=normalizeEmail(email);
  if(!key)return null;
  const found=await db.prepare('SELECT * FROM customers WHERE email_key=?').bind(key).first();
  if(found)return {...found,created:false};
  const id=uuid(),clean=email.trim().toLowerCase();
  await db.prepare('INSERT INTO customers(id,name,email,email_key,updated_at) VALUES(?,?,?,?,CURRENT_TIMESTAMP)')
    .bind(id,string(name,120)||clean.split('@')[0],clean,key).run();
  return {id,name:name||clean,email:clean,email_key:key,status:'active',google_sub:null,created:true};
}
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
      const [customers,orders,licenses,auditLog,fulfilled,plans]=await Promise.all([
        db.prepare('SELECT id,name,email,phone,status,created_at,google_sub IS NOT NULL AS linked FROM customers ORDER BY created_at DESC LIMIT 100').all(),
        db.prepare('SELECT o.*,c.name AS customer_name,c.email AS customer_email,c.google_sub IS NOT NULL AS customer_linked,p.name AS plan_name, pr.reference AS review_reference, pr.submitted_at AS review_submitted_at FROM orders o JOIN customers c ON c.id=o.customer_id LEFT JOIN plans p ON p.code=o.plan_code LEFT JOIN payment_reviews pr ON pr.order_id=o.id ORDER BY o.created_at DESC LIMIT 100').all(),
        db.prepare('SELECT l.id,l.customer_id,l.key_hint,l.status,l.expires_at,l.seat_limit,l.plan_code,l.created_at,c.name AS customer_name,c.email AS customer_email FROM licenses l JOIN customers c ON c.id=l.customer_id ORDER BY l.created_at DESC LIMIT 100').all(),
        db.prepare('SELECT actor,action,target_id,detail,at FROM admin_audit ORDER BY at DESC LIMIT 30').all(),
        db.prepare('SELECT order_id FROM license_fulfillments ORDER BY created_at DESC LIMIT 500').all(),
        db.prepare('SELECT code,name,seat_limit,months,price_vnd,active,sort FROM plans ORDER BY sort,code').all()]);
      return reply({actor,customers:customers.results,orders:orders.results,licenses:licenses.results,audit:auditLog.results,
        fulfilled_order_ids:fulfilled.results.map(x=>x.order_id),plans:plans.results});
    }
    if(path==='/api/admin/customers'&&method==='POST'){
      const x=await body(request),name=string(x.name,120),email=string(x.email,200).toLowerCase(),phone=string(x.phone,40);
      if(!name||!validEmail(email))return reply({error:'Invalid name/email'},400);
      const id=uuid();await db.prepare('INSERT INTO customers(id,name,email,email_key,phone,updated_at) VALUES(?,?,?,?,?,CURRENT_TIMESTAMP)').bind(id,name,email,normalizeEmail(email),phone).run();await audit(db,actor,'customer_create',id);
      return reply({id},201);
    }
    if(path==='/api/admin/customers'&&method==='GET'){
      const q=string(url.searchParams.get('q')||'',120).toLowerCase(),page=Math.max(0,Math.min(500,Number(url.searchParams.get('page'))||0));
      const like='%'+q.replace(/[%_\\]/g,'\\$&')+'%';
      const rows=await db.prepare(`SELECT c.id,c.name,c.email,c.phone,c.status,c.created_at,c.google_sub IS NOT NULL AS linked,
          l.expires_at,l.plan_code,l.seat_limit FROM customers c
          LEFT JOIN licenses l ON l.customer_id=c.id AND l.status='active'
          WHERE ?='' OR c.email_key=? OR lower(c.name) LIKE ? ESCAPE '\\' OR lower(c.email) LIKE ? ESCAPE '\\' OR c.phone LIKE ? ESCAPE '\\'
          ORDER BY c.created_at DESC LIMIT 51 OFFSET ?`)
        .bind(q,normalizeEmail(q),like,like,like,page*50).all();
      const results=rows.results||[];
      return reply({customers:results.slice(0,50),next_page:results.length>50?page+1:null});
    }
    const customerMatch=path.match(CUSTOMER_PATH);
    if(customerMatch){
      const id=customerMatch[1],verb=customerMatch[2]||'';
      const customer=await db.prepare('SELECT id,name,email,email_key,phone,status,created_at,google_sub IS NOT NULL AS linked FROM customers WHERE id=?').bind(id).first();
      if(!customer)return reply({error:'Customer not found'},404);
      if(!verb&&method==='GET'){
        const since=iso(Date.now()-SEAT_TTL_SECONDS*1000);
        const [licenses,orders,notes,seats]=await Promise.all([
          db.prepare('SELECT id,status,expires_at,seat_limit,plan_code,key_hint,created_at FROM licenses WHERE customer_id=? ORDER BY created_at DESC').bind(id).all(),
          db.prepare('SELECT o.id,o.status,o.amount_vnd,o.months,o.days,o.seat_limit,o.plan_code,o.payment_code,o.source,o.created_at,o.paid_at,o.reference FROM orders o WHERE o.customer_id=? ORDER BY o.created_at DESC LIMIT 50').bind(id).all(),
          db.prepare('SELECT actor,note,at FROM customer_notes WHERE customer_id=? ORDER BY at DESC LIMIT 50').bind(id).all(),
          db.prepare('SELECT s.license_id,s.client_hash,s.platform,s.device_label,s.last_seen_at,s.first_seen_at FROM license_seats s JOIN licenses l ON l.id=s.license_id WHERE l.customer_id=? AND s.last_seen_at>=? ORDER BY s.last_seen_at DESC').bind(id,since).all()]);
        return reply({customer,licenses:licenses.results,orders:orders.results,notes:notes.results,
          devices:(seats.results||[]).map(s=>({...s,id:s.client_hash.slice(0,12)}))});
      }
      if(method!=='POST')return reply({error:'Unknown administration endpoint'},404);
      const x=await body(request);
      if(verb==='block'||verb==='unblock'){
        const to=verb==='block'?'blocked':'active';
        const writes=[db.prepare('UPDATE customers SET status=?,updated_at=CURRENT_TIMESTAMP WHERE id=?').bind(to,id),
          auditStmt(db,actor,'customer_'+verb,id,string(x.reason,300)||null)];
        if(to==='blocked')writes.push(...signOutEverywhere(db,id));
        await db.batch(writes);
        return reply({ok:true,status:to});
      }
      if(verb==='unlink-google'){
        const reason=string(x.reason,300);
        if(reason.length<5)return reply({error:'A reason is required'},400);
        await db.batch([db.prepare('UPDATE customers SET google_sub=NULL,updated_at=CURRENT_TIMESTAMP WHERE id=?').bind(id),
          ...signOutEverywhere(db,id),auditStmt(db,actor,'google_unlinked',id,reason)]);
        return reply({ok:true});
      }
      if(verb==='signout-all'){
        await db.batch([...signOutEverywhere(db,id),auditStmt(db,actor,'customer_signout_all',id)]);
        return reply({ok:true});
      }
      if(verb==='notes'){
        const note=string(x.note,1000);
        if(!note)return reply({error:'Note is empty'},400);
        await db.prepare('INSERT INTO customer_notes(id,customer_id,actor,note) VALUES(?,?,?,?)').bind(uuid(),id,actor,note).run();
        return reply({ok:true},201);
      }
    }
    if(path==='/api/admin/orders/activate'&&method==='POST'){
      const x=await body(request),id=string(x.order_id,50),ref=string(x.reference,120);
      if(!id||ref.length<3)return reply({error:'Order and bank transfer reference required'},400);
      const result=await fulfillPaidOrder(db,id,actor,{reference:ref,note:string(x.note,500)||null});
      if(!result.ok)return reply({error:result.error},409);
      return reply(result);
    }
    if(path==='/api/admin/grant'&&method==='POST'){
      // Grant or extend a plan for a Gmail without a customer order (phone sales,
      // gifts, pilot migration). The admin types the Gmail twice.
      const x=await body(request),email=string(x.email,200),confirm=string(x.confirm_email,200);
      if(!validEmail(email))return reply({error:'Invalid Gmail'},400);
      if(normalizeEmail(email)!==normalizeEmail(confirm))return reply({error:'The two Gmail entries do not match'},400);
      const ref=string(x.reference,120);
      if(ref.length<3)return reply({error:'Payment or approval reference required'},400);
      const source=x.source==='pilot_migration'?'pilot_migration':'admin_grant';
      let months=null,days=null,seats,planCode=null,amount=Number(x.amount_vnd||0);
      if(x.plan_code){
        const plan=await db.prepare('SELECT * FROM plans WHERE code=?').bind(string(x.plan_code,40)).first();
        if(!plan)return reply({error:'Unknown plan'},400);
        planCode=plan.code;seats=plan.seat_limit;months=plan.months;
        if(!x.amount_vnd)amount=plan.price_vnd;
        if(x.days)days=Number(x.days);
      }else{
        seats=Number(x.seat_limit);months=x.months?Number(x.months):null;days=x.days?Number(x.days):null;
        if(!Number.isInteger(seats)||seats<1||seats>20)return reply({error:'Invalid device limit'},400);
      }
      if(days!==null&&(!Number.isInteger(days)||days<1||days>1100))return reply({error:'Invalid number of days'},400);
      if(days===null&&(!Number.isInteger(months)||months<1||months>36))return reply({error:'Invalid number of months'},400);
      if(!Number.isSafeInteger(amount)||amount<0||amount>1000000000)return reply({error:'Invalid amount'},400);
      const customer=await customerByEmail(db,email,x.name);
      if(customer.status==='blocked')return reply({error:'Customer is blocked; unblock first'},409);
      const orderId=uuid();
      await db.prepare("INSERT INTO orders(id,customer_id,months,days,seat_limit,amount_vnd,status,plan_code,source,reference,paid_at,approved_by) VALUES(?,?,?,?,?,?,'paid',?,?,?,CURRENT_TIMESTAMP,?)")
        .bind(orderId,customer.id,months||Math.max(1,Math.ceil(days/30)),days,seats,amount,planCode,source,ref,actor).run();
      const order=await db.prepare('SELECT * FROM orders WHERE id=?').bind(orderId).first();
      const result=await grantFromOrder(db,order,actor,{reference:ref,note:string(x.note,500)||null,action:source});
      return reply({...result,customer_id:customer.id,customer_created:customer.created,linked:Boolean(customer.google_sub)},201);
    }
    const transfer=path.match(LICENSE_PATH);
    if(transfer&&method==='POST'){
      const x=await body(request),email=string(x.to_email,200);
      if(!validEmail(email)||normalizeEmail(email)!==normalizeEmail(string(x.confirm_email,200)))
        return reply({error:'Type the target Gmail twice'},400);
      const lic=await db.prepare("SELECT * FROM licenses WHERE id=? AND status='active'").bind(transfer[1]).first();
      if(!lic)return reply({error:'Active license not found'},404);
      const target=await customerByEmail(db,email,x.name);
      if(target.id===lic.customer_id)return reply({error:'License already belongs to this Gmail'},409);
      if(target.status==='blocked')return reply({error:'Target customer is blocked'},409);
      const taken=await db.prepare("SELECT id FROM licenses WHERE customer_id=? AND status='active'").bind(target.id).first();
      if(taken)return reply({error:'Target Gmail already has an active plan'},409);
      await db.batch([db.prepare('UPDATE licenses SET customer_id=?,updated_at=CURRENT_TIMESTAMP WHERE id=?').bind(target.id,lic.id),
        db.prepare('DELETE FROM license_seats WHERE license_id=?').bind(lic.id),
        auditStmt(db,actor,'license_transfer',lic.id,'from='+lic.customer_id+' to='+target.id+' '+string(x.reason,200))]);
      return reply({ok:true,customer_id:target.id});
    }
    if(path==='/api/admin/seats/kick'&&method==='POST'){
      const x=await body(request),lic=string(x.license_id,50),prefix=string(x.device_id,12);
      if(!/^[0-9a-f]{12}$/.test(prefix))return reply({error:'Invalid device'},400);
      const r=await db.prepare("DELETE FROM license_seats WHERE license_id=? AND substr(client_hash,1,12)=?").bind(lic,prefix).run();
      if(r.meta.changes<1)return reply({error:'Device not found'},404);
      await audit(db,actor,'seat_kick',lic,'device='+prefix);
      return reply({ok:true});
    }
    if(path==='/api/admin/plans'&&method==='GET'){
      return reply({plans:(await db.prepare('SELECT * FROM plans ORDER BY sort,code').all()).results});
    }
    if(path==='/api/admin/plans'&&method==='PUT'){
      const x=await body(request),code=string(x.code,40),name=string(x.name,80);
      const seats=Number(x.seat_limit),months=Number(x.months),price=Number(x.price_vnd),sort=Number(x.sort||0);
      if(!/^[a-z0-9-]{2,40}$/.test(code)||!name||!Number.isInteger(seats)||seats<1||seats>20||
        !Number.isInteger(months)||months<1||months>36||!Number.isSafeInteger(price)||price<0||price>1000000000)
        return reply({error:'Invalid plan'},400);
      await db.prepare(`INSERT INTO plans(code,name,seat_limit,months,price_vnd,active,sort,updated_at) VALUES(?,?,?,?,?,?,?,CURRENT_TIMESTAMP)
        ON CONFLICT(code) DO UPDATE SET name=excluded.name,seat_limit=excluded.seat_limit,months=excluded.months,
        price_vnd=excluded.price_vnd,active=excluded.active,sort=excluded.sort,updated_at=CURRENT_TIMESTAMP`)
        .bind(code,name,seats,months,price,x.active?1:0,Number.isInteger(sort)?sort:0).run();
      await audit(db,actor,'plan_update',code,name+' '+price+'d '+seats+' devices '+(x.active?'on':'off'));
      return reply({ok:true});
    }
    if(path==='/api/admin/expiring'&&method==='GET'){
      const days=Math.max(1,Math.min(60,Number(url.searchParams.get('days'))||7));
      const rows=await db.prepare(`SELECT l.id,l.expires_at,l.plan_code,l.seat_limit,c.id AS customer_id,c.name,c.email,c.phone
        FROM licenses l JOIN customers c ON c.id=l.customer_id WHERE l.status='active' AND l.expires_at>? AND l.expires_at<=?
        ORDER BY l.expires_at`).bind(iso(Date.now()),iso(Date.now()+days*86400000)).all();
      return reply({licenses:rows.results});
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
