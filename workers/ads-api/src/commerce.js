/* Shared Gmail-plan rules for the customer and Admin APIs.
 * Subscription metadata only: no Ads credentials, account IDs or reports.
 */
const enc=new TextEncoder();
const hex=bytes=>Array.from(bytes,x=>x.toString(16).padStart(2,'0')).join('');
export const sha256=async s=>hex(new Uint8Array(await crypto.subtle.digest('SHA-256',enc.encode(s))));
export const iso=ms=>new Date(ms).toISOString();
export const uuid=()=>crypto.randomUUID();

/* Gmail ignores dots and "+tag" in the local part and treats googlemail.com as
 * gmail.com. Other domains only get trimmed and lower-cased.
 * Must stay identical to the SQL backfill in migrations/0006. */
export function normalizeEmail(value){
 const email=String(value||'').trim().toLowerCase();
 const at=email.lastIndexOf('@');
 if(at<1||at===email.length-1)return '';
 let local=email.slice(0,at),domain=email.slice(at+1);
 if(domain==='gmail.com'||domain==='googlemail.com'){
   local=local.split('+')[0].replace(/\./g,'');
   domain='gmail.com';
 }
 return local?local+'@'+domain:'';
}
export const validEmail=s=>typeof s==='string'&&s.length<=200&&/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(s.trim());

// No 0/O/1/I/L so codes survive being read out or retyped from a bank app.
const CODE_ALPHABET='ABCDEFGHJKMNPQRSTUVWXYZ23456789';
export function paymentCode(){
 const bytes=crypto.getRandomValues(new Uint8Array(5));
 return 'LHM'+Array.from(bytes,b=>CODE_ALPHABET[b%CODE_ALPHABET.length]).join('');
}

export const SEAT_TTL_SECONDS=600;
export const HEARTBEAT_SECONDS=300;
export const EXPIRING_SOON_DAYS=7;

export async function activePlans(db){
 const rows=await db.prepare('SELECT code,name,seat_limit,months,price_vnd FROM plans WHERE active=1 AND price_vnd>0 ORDER BY sort,code').all();
 return rows.results||[];
}

/* Where a customer stands. Order matters: blocked > active > revoked > expired > none. */
export async function entitlement(db,customer){
 if(customer.status==='blocked')return {state:'blocked',license:null,pending:null};
 const now=iso(Date.now());
 const active=await db.prepare("SELECT l.id,l.status,l.expires_at,l.seat_limit,l.plan_code,p.name AS plan_name FROM licenses l LEFT JOIN plans p ON p.code=l.plan_code WHERE l.customer_id=? AND l.status='active' AND l.expires_at>? ORDER BY l.expires_at DESC LIMIT 1")
   .bind(customer.id,now).first();
 const pending=await db.prepare("SELECT o.id,o.payment_code,o.amount_vnd,o.plan_code,o.months,o.seat_limit,o.expires_at,p.name AS plan_name FROM orders o LEFT JOIN plans p ON p.code=o.plan_code WHERE o.customer_id=? AND o.status='pending' AND (o.expires_at IS NULL OR o.expires_at>?) ORDER BY o.created_at DESC LIMIT 1")
   .bind(customer.id,now).first();
 if(active)return {state:'active',license:active,pending};
 const last=await db.prepare('SELECT id,status,expires_at FROM licenses WHERE customer_id=? ORDER BY updated_at DESC,expires_at DESC LIMIT 1')
   .bind(customer.id).first();
 if(last?.status==='revoked')return {state:'revoked',license:null,pending};
 if(last)return {state:pending?'pending':'expired',license:null,pending,expired_at:last.expires_at};
 return {state:pending?'pending':'none',license:null,pending};
}

/* API error code per state, shared by PWA, PC and Admin wording. */
export const STATE_ERRORS={
 none:{status:402,code:'SUBSCRIPTION_REQUIRED',error:'Chọn và thanh toán gói để dùng phần mềm.'},
 pending:{status:402,code:'PAYMENT_PENDING',error:'Đơn hàng đang chờ xác nhận thanh toán.'},
 expired:{status:402,code:'SUBSCRIPTION_EXPIRED',error:'Gói đã hết hạn. Gia hạn để tiếp tục.'},
 revoked:{status:403,code:'LICENSE_REVOKED',error:'Gói đã bị thu hồi. Liên hệ hỗ trợ.'},
 blocked:{status:403,code:'ACCOUNT_BLOCKED',error:'Tài khoản đang bị tạm khoá. Liên hệ hỗ trợ.'}
};

export function planView(license){
 if(!license)return null;
 const left=Date.parse(license.expires_at)-Date.now();
 return {code:license.plan_code||null,name:license.plan_name||null,seat_limit:license.seat_limit,
   expires_at:license.expires_at,days_left:Math.max(0,Math.ceil(left/86400000)),
   expiring_soon:left<=EXPIRING_SOON_DAYS*86400000};
}

/* Bank transfer instructions with a VietQR image link. The link carries only the
 * amount, the payment code and the seller's public account details. */
export function paymentInstructions(env,order){
 const bin=String(env?.BANK_BIN||'').trim(),account=String(env?.BANK_ACCOUNT_NO||'').trim(),
   holder=String(env?.BANK_ACCOUNT_NAME||'').trim();
 if(!order)return null;
 const base={amount_vnd:order.amount_vnd,transfer_content:order.payment_code};
 if(!/^\d{6}$/.test(bin)||!/^[A-Za-z0-9]{4,24}$/.test(account)||!holder||holder.length>80)
   return {...base,configured:false};
 const qr='https://img.vietqr.io/image/'+bin+'-'+account+'-compact2.png?'+new URLSearchParams({
   amount:String(order.amount_vnd),addInfo:order.payment_code||'',accountName:holder});
 return {...base,configured:true,bank_bin:bin,account_no:account,account_name:holder,qr_url:qr};
}

/* Mark payment AND issue/renewal in one atomic D1 batch.
 * Never leave status='paid' without a license if a later SQL statement fails.
 * The order_id unique fulfillment constraint also rejects concurrent approvals. */
export async function fulfillPaidOrder(db,orderId,actor,{reference,note,action='payment_activate'}={}){
 const order=await db.prepare("SELECT * FROM orders WHERE id=? AND status='pending'")
   .bind(orderId).first();
 if(!order)return {ok:false,error:'Order already processed or missing'};
 return grantFromOrder(db,order,actor,{reference,note,action,markPendingPaid:true});
}

/* All effects of an order fulfillment are transactional, including creating a
 * directly granted paid order and transitioning a pending bank payment. */
export async function grantFromOrder(db,order,actor,{reference,note,action,
    markPendingPaid=false,createPaidOrder=false}={}){
 const step=order.days?'+'+Number(order.days)+' days':'+'+Number(order.months)+' months';
 const current=await db.prepare("SELECT id FROM licenses WHERE customer_id=? AND status='active' ORDER BY expires_at DESC LIMIT 1")
   .bind(order.customer_id).first();
 const writes=[];
 if(createPaidOrder){
   writes.push(db.prepare("INSERT INTO orders(id,customer_id,months,days,seat_limit,amount_vnd,status,plan_code,source,reference,paid_at,approved_by) VALUES(?,?,?,?,?,?,'paid',?,?,?,CURRENT_TIMESTAMP,?)")
     .bind(order.id,order.customer_id,order.months,order.days||null,order.seat_limit,
       order.amount_vnd,order.plan_code||null,order.source||'admin_grant',reference||null,actor));
 }
 if(markPendingPaid){
   writes.push(db.prepare("UPDATE orders SET status='paid',paid_at=CURRENT_TIMESTAMP,approved_by=?,reference=? WHERE id=? AND status='pending'")
     .bind(actor,reference||null,order.id));
 }
 if(reference)writes.push(db.prepare('INSERT INTO payment_reviews(order_id,reference,note) VALUES(?,?,?) ON CONFLICT(order_id) DO UPDATE SET reference=excluded.reference,note=excluded.note,submitted_at=CURRENT_TIMESTAMP')
   .bind(order.id,reference,note||null));
 let licenseId;
 if(current){
   licenseId=current.id;
   writes.push(
     db.prepare("INSERT INTO license_fulfillments(order_id,license_id,action) VALUES(?,?,'renew')").bind(order.id,licenseId),
     // Extend from the later of now and the current expiry, inside SQLite.
     db.prepare(`UPDATE licenses SET expires_at=strftime('%Y-%m-%dT%H:%M:%fZ',
         datetime(CASE WHEN julianday(expires_at)>julianday('now') THEN expires_at ELSE 'now' END, ?)),
       seat_limit=?,plan_code=COALESCE(?,plan_code),updated_at=CURRENT_TIMESTAMP WHERE id=?`)
       .bind(step,order.seat_limit||1,order.plan_code||null,licenseId));
   // A renewal may downgrade 5 seats to 1 or 2. Trim the least recently
   // active devices INSIDE the same transaction as the license change;
   // otherwise existing heartbeats could exceed the paid concurrency limit.
   writes.push(db.prepare(
     'DELETE FROM license_seats WHERE license_id=? AND client_hash IN (SELECT client_hash FROM license_seats WHERE license_id=? ORDER BY last_seen_at DESC,client_hash DESC LIMIT -1 OFFSET ?)'
   ).bind(licenseId,licenseId,order.seat_limit||1));
 }else{
   licenseId=order.id;
   // Gmail-bound plans never hand out a key; the hash only satisfies the legacy column.
   const internal=await sha256('gmail-plan:'+order.id+':'+uuid());
   writes.push(
     db.prepare(`INSERT INTO licenses(id,customer_id,key_hash,key_hint,expires_at,seat_limit,plan_code,status,updated_at)
       VALUES(?,?,?,'GMAIL',strftime('%Y-%m-%dT%H:%M:%fZ',datetime('now',?)),?,?,'active',CURRENT_TIMESTAMP)`)
       .bind(licenseId,order.customer_id,internal,step,order.seat_limit||1,order.plan_code||null),
     db.prepare("INSERT INTO license_fulfillments(order_id,license_id,action) VALUES(?,?,'issue')").bind(order.id,licenseId));
 }
 writes.push(db.prepare('INSERT INTO admin_audit(id,actor,action,target_id,detail) VALUES(?,?,?,?,?)')
   .bind(uuid(),actor,action,order.id,'customer='+order.customer_id+' license='+licenseId));
 await db.batch(writes);
 const result=await db.prepare('SELECT id,expires_at,seat_limit,plan_code FROM licenses WHERE id=?').bind(licenseId).first();
 return {ok:true,license:result,renewed:Boolean(current)};
}

/* Remove every way a customer is currently signed in or holding a seat. */
export function signOutEverywhere(db,customerId){
 return [
   db.prepare('DELETE FROM customer_sessions WHERE customer_id=?').bind(customerId),
   db.prepare('DELETE FROM desktop_sessions WHERE customer_id=?').bind(customerId),
   db.prepare('DELETE FROM license_seats WHERE license_id IN (SELECT id FROM licenses WHERE customer_id=?)').bind(customerId)
 ];
}

/* Signed offline lease for the Windows app (Ed25519, PKCS#8 key in LEASE_SIGNING_KEY).
 * Format: base64url(JSON payload) "." base64url(signature over the first part). */
const b64url=bytes=>btoa(String.fromCharCode(...bytes)).replace(/\+/g,'-').replace(/\//g,'_').replace(/=+$/,'');
let cachedKey=null,cachedSource='';
async function leaseKey(env){
 const source=String(env?.LEASE_SIGNING_KEY||'').trim();
 if(!source)return null;
 if(cachedKey&&cachedSource===source)return cachedKey;
 const der=Uint8Array.from(atob(source.replace(/-/g,'+').replace(/_/g,'/')),c=>c.charCodeAt(0));
 cachedKey=await crypto.subtle.importKey('pkcs8',der,{name:'Ed25519'},false,['sign']);
 cachedSource=source;
 return cachedKey;
}
export async function signLease(env,{customer,license,clientHash}){
 const key=await leaseKey(env).catch(()=>null);
 if(!key)return null;
 // Product policy: an offline lease must NEVER exceed 72 hours, even with
 // an incorrect Worker configuration. The Windows verifier enforces this too.
 const graceHours=Math.min(72,Math.max(1,Number(env?.LEASE_GRACE_HOURS)||72));
 const now=Date.now();
 const validUntil=Math.min(now+graceHours*3600000,Date.parse(license.expires_at));
 const payload={v:1,customer_id:customer.id,email:customer.email,license_id:license.id,client_hash:clientHash,
   plan_code:license.plan_code||null,seat_limit:license.seat_limit,
   license_expires_at:license.expires_at,issued_at:iso(now),valid_until:iso(validUntil)};
 const body=b64url(enc.encode(JSON.stringify(payload)));
 const sig=new Uint8Array(await crypto.subtle.sign({name:'Ed25519'},key,enc.encode(body)));
 return body+'.'+b64url(sig);
}
