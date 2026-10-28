/* Gmail-bound plans end to end on real SQLite with all D1 migrations:
 * sign-in matching, self-service orders, Admin activation, seats, expiry,
 * blocking, grants, transfers and the signed PC lease. */
import test from 'node:test';
import assert from 'node:assert/strict';
import {webcrypto,createHash} from 'node:crypto';
import {createD1} from './helpers/d1-sqlite.mjs';
globalThis.crypto??=webcrypto;
const {googleSubscription,linkGoogleIdentity}=await import('../workers/ads-api/src/google-subscription.js');
const {adminApi}=await import('../workers/ads-api/src/admin.js');
const {normalizeEmail,signLease}=await import('../workers/ads-api/src/commerce.js');
const {cleanup}=await import('../workers/ads-api/src/index.js');

const base='https://ads.lhmcrm.com';
const sha=x=>createHash('sha256').update(x).digest('hex');
const b64url=buf=>Buffer.from(buf).toString('base64url');

/* Cloudflare Access JWT signed by a throwaway RSA key served from a mocked JWKS. */
const accessKeys=await crypto.subtle.generateKey({name:'RSASSA-PKCS1-v1_5',modulusLength:2048,
 publicExponent:new Uint8Array([1,0,1]),hash:'SHA-256'},true,['sign','verify']);
const jwk={...(await crypto.subtle.exportKey('jwk',accessKeys.publicKey)),kid:'k1'};
globalThis.fetch=async url=>{
 if(String(url)==='https://team.cloudflareaccess.com/cdn-cgi/access/certs')return Response.json({keys:[jwk]});
 throw Error('unexpected network call '+url);
};
async function accessJwt(){
 const head=b64url(JSON.stringify({alg:'RS256',kid:'k1'}));
 const now=Math.floor(Date.now()/1000);
 const body=b64url(JSON.stringify({aud:'aud-1',iss:'https://team.cloudflareaccess.com',sub:'admin',
   email:'owner@example.com',iat:now,exp:now+600}));
 const sig=await crypto.subtle.sign('RSASSA-PKCS1-v1_5',accessKeys.privateKey,new TextEncoder().encode(head+'.'+body));
 return head+'.'+body+'.'+b64url(sig);
}

function setup(extraEnv={}){
 const db=createD1();
 const env={COMMERCE_DB:db,CF_ACCESS_TEAM_DOMAIN:'team.cloudflareaccess.com',CF_ACCESS_AUD:'aud-1',
   ADMIN_EMAIL:'owner@example.com',...extraEnv};
 const admin=async(path,payload,method)=>{
   const r=await adminApi(new Request(base+path,{method:method||(payload?'POST':'GET'),
     headers:{'Cf-Access-Jwt-Assertion':await accessJwt(),...(payload?{'Content-Type':'application/json'}:{})},
     body:payload?JSON.stringify(payload):undefined}),env);
   return {status:r.status,body:await r.json()};
 };
 // Sign a customer in exactly like the OAuth callback does after Google verifies them.
 const signIn=async(identity)=>{
   const linked=await linkGoogleIdentity(db,{name:'Khách',picture:null,...identity});
   if(linked.error)return linked;
   const token='a'.repeat(63)+String(Math.floor(Math.random()*10));
   const fresh=sha(token+Math.random()).slice(0,64);
   await db.prepare('INSERT INTO customer_sessions(token_hash,customer_id,expires_at) VALUES(?,?,?)')
     .bind(sha(fresh),linked.id,new Date(Date.now()+86400000).toISOString()).run();
   const call=async(path,payload)=>{
     const r=await googleSubscription(new Request(base+path,{method:payload?'POST':'GET',
       headers:{cookie:'lhm_google_session='+fresh,...(payload?{'Content-Type':'application/json'}:{})},
       body:payload?JSON.stringify(payload):undefined}),env);
     return {status:r.status,body:await r.json()};
   };
   return {...linked,call};
 };
 const desktop=async(customerId)=>{
   const token=sha('desktop'+Math.random());
   await db.prepare('INSERT INTO desktop_sessions(token_hash,customer_id,expires_at) VALUES(?,?,?)')
     .bind(sha(token),customerId,new Date(Date.now()+86400000).toISOString()).run();
   return async(path,payload)=>{
     const r=await googleSubscription(new Request(base+path,{method:'POST',
       headers:{Authorization:'Bearer '+token,'Content-Type':'application/json'},body:JSON.stringify(payload)}),env);
     return {status:r.status,body:await r.json()};
   };
 };
 return {db,env,admin,signIn,desktop};
}
const client=()=>crypto.randomUUID();

test('Gmail normalization matches Google: dots, +tag, googlemail, case',()=>{
 assert.equal(normalizeEmail(' Nguyen.Van.A+ads@GoogleMail.com '),'nguyenvana@gmail.com');
 assert.equal(normalizeEmail('nguyenvana@gmail.com'),'nguyenvana@gmail.com');
 assert.equal(normalizeEmail('first.last@company.vn'),'first.last@company.vn');
 assert.equal(normalizeEmail('not-an-email'),'');
});

test('migration backfills the same email_key as the Worker',async()=>{
 const {db}=setup();
 const rows=[['A.B+x@googlemail.com'],['C.D@Example.com']];
 for(const [email] of rows)
   db.sqlite.prepare('INSERT INTO customers(id,name,email) VALUES(?,?,?)').run(crypto.randomUUID(),'n',email);
 // Re-run only the backfill statement on rows inserted after the migration.
 db.sqlite.exec(`UPDATE customers SET email_key=CASE
  WHEN substr(lower(trim(email)),instr(lower(trim(email)),'@')+1) IN ('gmail.com','googlemail.com')
  THEN replace(CASE WHEN instr(lower(trim(email)),'+')>0 THEN substr(lower(trim(email)),1,instr(lower(trim(email)),'+')-1)
  ELSE substr(lower(trim(email)),1,instr(lower(trim(email)),'@')-1) END,'.','')||'@gmail.com' ELSE lower(trim(email)) END`);
 for(const r of db.sqlite.prepare('SELECT email,email_key FROM customers').all())
   assert.equal(r.email_key,normalizeEmail(r.email));
});

test('admin grant by Gmail is claimed on first Google sign-in, then locked to that Google ID',async()=>{
 const {admin,signIn}=setup();
 let r=await admin('/api/admin/grant',{email:'Nguyen.Van.A@gmail.com',confirm_email:'nguyenvana@gmail.com',
   plan_code:'personal-1m',reference:'CK-0001'});
 assert.equal(r.status,201,JSON.stringify(r.body));
 assert.equal(r.body.linked,false);
 const first=await signIn({sub:'google-sub-1',email:'nguyenvana@gmail.com'});
 assert.equal(first.id,r.body.customer_id);
 const session=await first.call('/api/auth/session');
 assert.equal(session.body.state,'active');
 assert.equal(session.body.plan.seat_limit,2);
 // Someone else whose Google account shows the same address cannot take it over.
 const other=await signIn({sub:'google-sub-2',email:'nguyen.van.a@gmail.com'});
 assert.equal(other.error,'mismatch');
 // The real owner keeps access after renaming the address on their Google account.
 const renamed=await signIn({sub:'google-sub-1',email:'new.address@gmail.com'});
 assert.equal(renamed.id,first.id);
});

test('grant refuses mismatched confirmation and unknown plans',async()=>{
 const {admin}=setup();
 let r=await admin('/api/admin/grant',{email:'a@gmail.com',confirm_email:'b@gmail.com',plan_code:'personal-1m',reference:'CK-1'});
 assert.equal(r.status,400);
 r=await admin('/api/admin/grant',{email:'a@gmail.com',confirm_email:'a@gmail.com',plan_code:'nope',reference:'CK-1'});
 assert.equal(r.status,400);
});

test('self-service order -> QR -> admin activate -> seats -> renew -> expiry',async()=>{
 const {db,admin,signIn}=setup({BANK_BIN:'970436',BANK_ACCOUNT_NO:'0123456789',BANK_ACCOUNT_NAME:'NGUYEN VAN A'});
 const me=await signIn({sub:'sub-buyer',email:'buyer@gmail.com'});
 let r=await me.call('/api/auth/session');
 assert.equal(r.body.state,'none');
 r=await me.call('/api/auth/seat',{client_id:client()});
 assert.equal(r.status,402);assert.equal(r.body.code,'SUBSCRIPTION_REQUIRED');

 r=await me.call('/api/auth/plans');
 assert.deepEqual(r.body.plans.map(p=>p.code),['personal-1m','personal-6m','personal-12m']);
 r=await me.call('/api/auth/plan',{plan_code:'personal-1m'});
 assert.equal(r.status,201);
 assert.match(r.body.payment_code,/^LHM[A-HJKMNP-Z2-9]{5}$/);
 assert.equal(r.body.payment.configured,true);
 assert.equal(r.body.payment.transfer_content,r.body.payment_code);
 assert.match(r.body.payment.qr_url,/^https:\/\/img\.vietqr\.io\/image\/970436-0123456789-compact2\.png\?amount=499000&addInfo=LHM/);
 const orderId=r.body.id;
 r=await me.call('/api/auth/plan',{plan_code:'personal-6m'});
 assert.equal(r.status,409);assert.equal(r.body.code,'PAYMENT_PENDING');
 r=await me.call('/api/auth/seat',{client_id:client()});
 assert.equal(r.body.code,'PAYMENT_PENDING');

 r=await admin('/api/admin/overview');
 const listed=r.body.orders.find(o=>o.id===orderId);
 assert.equal(listed.customer_linked,1);assert.equal(listed.payment_code.length,8);
 r=await admin('/api/admin/orders/activate',{order_id:orderId,reference:'FT2610ABC'});
 assert.equal(r.status,200,JSON.stringify(r.body));
 assert.equal(r.body.renewed,false);
 r=await admin('/api/admin/orders/activate',{order_id:orderId,reference:'FT2610ABC'});
 assert.equal(r.status,409,'second activation of the same order must be refused');

 r=await me.call('/api/auth/session');
 assert.equal(r.body.state,'active');
 const firstExpiry=Date.parse(r.body.plan.expires_at);
 assert.ok(firstExpiry>Date.now()+27*86400000);

 // Two devices fit; the third must ask before signing anyone out.
 const [phone,pc,tablet]=[client(),client(),client()];
 assert.equal((await me.call('/api/auth/seat',{client_id:phone,device_label:'Chrome Android'})).status,200);
 assert.equal((await me.call('/api/auth/seat',{client_id:pc})).status,200);
 r=await me.call('/api/auth/seat',{client_id:tablet});
 assert.equal(r.status,409);assert.equal(r.body.code,'SEAT_LIMIT');assert.equal(r.body.devices.length,2);
 r=await me.call('/api/auth/seat',{client_id:tablet,mode:'takeover'});
 assert.equal(r.status,200);assert.equal(r.body.occupied,2);
 // The least recently active device (phone) was signed out and cannot silently come back.
 r=await me.call('/api/auth/seat',{client_id:phone,mode:'heartbeat'});
 assert.equal(r.status,409);assert.equal(r.body.code,'SEAT_REPLACED');
 r=await me.call('/api/auth/seat',{client_id:pc,mode:'heartbeat'});
 assert.equal(r.status,200);

 // Renewing early extends from the current expiry, never from today.
 r=await me.call('/api/auth/plan',{plan_code:'personal-1m'});
 r=await admin('/api/admin/orders/activate',{order_id:r.body.id,reference:'FT2610DEF'});
 assert.equal(r.body.renewed,true);
 r=await me.call('/api/auth/session');
 assert.ok(Date.parse(r.body.plan.expires_at)>firstExpiry+27*86400000);

 // Hard lock once expired.
 db.sqlite.prepare("UPDATE licenses SET expires_at='2020-01-01T00:00:00.000Z'").run();
 r=await me.call('/api/auth/session');
 assert.equal(r.body.state,'expired');assert.equal(r.body.plan,null);
 r=await me.call('/api/auth/seat',{client_id:pc,mode:'heartbeat'});
 assert.equal(r.status,402);assert.equal(r.body.code,'SUBSCRIPTION_EXPIRED');
});

test('device takeover never deletes an occupied seat before installing its replacement',async()=>{
 const {db,admin,signIn}=setup();
 const grant=await admin('/api/admin/grant',{email:'atomic.seat@gmail.com',
   confirm_email:'atomic.seat@gmail.com',plan_code:'personal-1m',reference:'CK-SEAT-ATOMIC'});
 assert.equal(grant.status,201,JSON.stringify(grant.body));
 const me=await signIn({sub:'sub-seat-atomic',email:'atomic.seat@gmail.com'});
 const phone=client(),pc=client(),tablet=client();
 assert.equal((await me.call('/api/auth/seat',{client_id:phone})).status,200);
 assert.equal((await me.call('/api/auth/seat',{client_id:pc})).status,200);
 const license=db.sqlite.prepare('SELECT id FROM licenses WHERE customer_id=?').get(me.id);
 const originals=new Set([sha(license.id+':'+phone),sha(license.id+':'+pc)]);
 const replacement=sha(license.id+':'+tablet);
 // A separate DELETE used to run before a second INSERT. An interrupted INSERT
 // left the customer missing an active seat. No such statement may execute.
 const prepare=db.prepare;
 db.prepare=sql=>{
   if(sql.startsWith('DELETE FROM license_seats WHERE license_id=? AND client_hash='))
     throw Error('unsafe delete-before-insert takeover');
   return prepare(sql);
 };
 const result=await me.call('/api/auth/seat',{client_id:tablet,mode:'takeover'});
 assert.equal(result.status,200,JSON.stringify(result.body));
 assert.equal(result.body.occupied,2);
 const seats=db.sqlite.prepare('SELECT client_hash FROM license_seats WHERE license_id=?').all(license.id);
 assert.equal(seats.length,2);
 assert.ok(seats.some(s=>s.client_hash===replacement));
 // Both original devices can have the same millisecond timestamp. The
 // implementation resolves that tie by hash, not insertion order.
 assert.equal(seats.filter(s=>originals.has(s.client_hash)).length,1);
 assert.equal(new Set(seats.map(s=>s.client_hash)).size,2);
});

test('a heartbeat raced by a device takeover cannot return an active seat',async()=>{
 const {db,admin,signIn}=setup();
 const grant=await admin('/api/admin/grant',{email:'race.seat@gmail.com',
   confirm_email:'race.seat@gmail.com',plan_code:'personal-1m',reference:'CK-SEAT-RACE'});
 assert.equal(grant.status,201,JSON.stringify(grant.body));
 const me=await signIn({sub:'sub-seat-race',email:'race.seat@gmail.com'});
 const pc=client();
 assert.equal((await me.call('/api/auth/seat',{client_id:pc})).status,200);
 const prepare=db.prepare;
 // Simulate a concurrent session eviction after SELECT but before UPDATE.
 db.prepare=sql=>sql.startsWith('UPDATE license_seats SET last_seen_at=')
   ?{bind:()=>({run:async()=>({meta:{changes:0}})})}
   :prepare(sql);
 const result=await me.call('/api/auth/seat',{client_id:pc,mode:'heartbeat'});
 assert.equal(result.status,409,JSON.stringify(result.body));
 assert.equal(result.body.code,'SEAT_REPLACED');
 assert.equal(result.body.active,undefined);
});

test('a paid seat downgrade immediately evicts excess devices within the license transaction',async()=>{
 const {db,admin,signIn}=setup();
 const email='downgrade.seat@gmail.com';
 let r=await admin('/api/admin/grant',{email,confirm_email:email,
   seat_limit:5,days:10,reference:'CK-PLAN-BIG'});
 assert.equal(r.status,201,JSON.stringify(r.body));
 const me=await signIn({sub:'sub-seat-downgrade',email});
 const ids=Array.from({length:5},()=>client());
 for(const id of ids)
   assert.equal((await me.call('/api/auth/seat',{client_id:id})).status,200);
 assert.equal(db.sqlite.prepare('SELECT COUNT(*) AS n FROM license_seats').get().n,5);
 r=await admin('/api/admin/grant',{email,confirm_email:email,
   seat_limit:2,days:30,reference:'CK-PLAN-SMALL'});
 assert.equal(r.status,201,JSON.stringify(r.body));
 assert.equal(r.body.license.seat_limit,2);
 const seats=db.sqlite.prepare('SELECT client_hash FROM license_seats').all().map(x=>x.client_hash);
 assert.equal(seats.length,2);
 const license=db.sqlite.prepare('SELECT id FROM licenses WHERE customer_id=?').get(me.id);
 for(const id of ids){
   const active=seats.includes(sha(license.id+':'+id));
   const response=await me.call('/api/auth/seat',{client_id:id,mode:'heartbeat'});
   assert.equal(response.status,active?200:409);
   if(!active)assert.equal(response.body.code,'SEAT_REPLACED');
 }
});

test('legacy payment approval also atomically grants license, never marks paid alone',async()=>{
 const {db,admin,signIn}=setup();
 const buyer=await signIn({sub:'legacy-approve-sub',email:'legacy-approve@gmail.com'});
 const order=await buyer.call('/api/auth/plan',{plan_code:'personal-1m'});
 assert.equal(order.status,201);
 const reviewed=await admin('/api/admin/payments/review',{
   order_id:order.body.id,reference:'LEGACY-BANK-APPROVAL-01',note:'Bank transfer checked separately'});
 assert.equal(reviewed.status,200,JSON.stringify(reviewed.body));
 const approved=await admin('/api/admin/payments/approve',{order_id:order.body.id});
 assert.equal(approved.status,200,JSON.stringify(approved.body));
 assert.equal(approved.body.ok,true);
 assert.equal(db.sqlite.prepare('SELECT status FROM orders WHERE id=?').get(order.body.id).status,'paid');
 assert.equal(db.sqlite.prepare('SELECT COUNT(*) AS n FROM license_fulfillments WHERE order_id=?').get(order.body.id).n,1);
 assert.equal((await buyer.call('/api/auth/session')).body.state,'active');
 assert.equal((await admin('/api/admin/payments/approve',{order_id:order.body.id})).status,409);
});

test('one verified bank transfer cannot activate two different Gmail orders',async()=>{
 const {db,admin,signIn}=setup();
 const first=await signIn({sub:'bank-receipt-owner-a',email:'receipt-owner-a@gmail.com'});
 const second=await signIn({sub:'bank-receipt-owner-b',email:'receipt-owner-b@gmail.com'});
 const o1=await first.call('/api/auth/plan',{plan_code:'personal-1m'});
 const o2=await second.call('/api/auth/plan',{plan_code:'personal-1m'});
 assert.equal(o1.status,201);
 assert.equal(o2.status,201);
 const approved=await admin('/api/admin/orders/activate',{
   order_id:o1.body.id,reference:'BANK-RECEIPT-ABCD-123'});
 assert.equal(approved.status,200,JSON.stringify(approved.body));
 const duplicate=await admin('/api/admin/orders/activate',{
   order_id:o2.body.id,reference:' bank-receipt-abcd-123 '});
 assert.equal(duplicate.status,409,'case/whitespace variations must not reuse one transfer');
 const secondOrder=db.sqlite.prepare('SELECT status,paid_at FROM orders WHERE id=?').get(o2.body.id);
 assert.equal(secondOrder.status,'pending');
 assert.equal(secondOrder.paid_at,null);
 assert.equal(db.sqlite.prepare('SELECT COUNT(*) AS n FROM license_fulfillments WHERE order_id=?').get(o2.body.id).n,0);
 assert.equal(db.sqlite.prepare('SELECT COUNT(*) AS n FROM licenses WHERE customer_id=?').get(second.id).n,0);
 // A genuinely different verified reference must still allow retry of that order.
 const retried=await admin('/api/admin/orders/activate',{
   order_id:o2.body.id,reference:'BANK-RECEIPT-ABCD-456'});
 assert.equal(retried.status,200,JSON.stringify(retried.body));
 assert.equal(db.sqlite.prepare('SELECT COUNT(*) AS n FROM orders WHERE status=\'paid\'').get().n,2);
});

test('bank payment approval is atomic: SQL fault cannot mark order paid without license',async()=>{
 const {db,admin,signIn}=setup();
 const buyer=await signIn({sub:'bank-atomicity-buyer',email:'bank-atomicity@gmail.com'});
 const purchase=await buyer.call('/api/auth/plan',{plan_code:'personal-1m'});
 assert.equal(purchase.status,201);
 const id=purchase.body.id;
 const normalBatch=db.batch;
 // Inject a failure as the last SQL statement: the order transition and all
 // license writes must roll back together under one D1 transaction.
 db.batch=async statements=>normalBatch([...statements,
   db.prepare('INSERT INTO deliberate_missing_commerce_table VALUES(1)')]);
 const failed=await admin('/api/admin/orders/activate',{order_id:id,reference:'BANK-ATOMIC-001'});
 assert.equal(failed.status,500);
 assert.equal(db.sqlite.prepare('SELECT status FROM orders WHERE id=?').get(id).status,'pending');
 assert.equal(db.sqlite.prepare('SELECT COUNT(*) AS n FROM license_fulfillments WHERE order_id=?').get(id).n,0);
 assert.equal(db.sqlite.prepare('SELECT COUNT(*) AS n FROM licenses WHERE customer_id=?').get(buyer.id).n,0);
 db.batch=normalBatch;
 const retried=await admin('/api/admin/orders/activate',{order_id:id,reference:'BANK-ATOMIC-001'});
 assert.equal(retried.status,200,JSON.stringify(retried.body));
 assert.equal(db.sqlite.prepare('SELECT status FROM orders WHERE id=?').get(id).status,'paid');
 assert.equal(db.sqlite.prepare('SELECT COUNT(*) AS n FROM license_fulfillments WHERE order_id=?').get(id).n,1);
});

test('manual Gmail grant is atomic: failed issuance leaves no paid order',async()=>{
 const {db,admin,signIn}=setup();
 const buyer=await signIn({sub:'manual-atomicity-buyer',email:'manual-atomicity@gmail.com'});
 const normalBatch=db.batch;
 db.batch=async statements=>normalBatch([...statements,
   db.prepare('INSERT INTO deliberate_missing_commerce_table VALUES(1)')]);
 const fields={email:'manual-atomicity@gmail.com',confirm_email:'manual-atomicity@gmail.com',
   plan_code:'personal-1m',reference:'DIRECT-ATOMIC-001'};
 const failed=await admin('/api/admin/grant',fields);
 assert.equal(failed.status,500);
 assert.equal(db.sqlite.prepare("SELECT COUNT(*) AS n FROM orders WHERE customer_id=?").get(buyer.id).n,0);
 assert.equal(db.sqlite.prepare("SELECT COUNT(*) AS n FROM licenses WHERE customer_id=?").get(buyer.id).n,0);
 db.batch=normalBatch;
 const retried=await admin('/api/admin/grant',fields);
 assert.equal(retried.status,201,JSON.stringify(retried.body));
 assert.equal(db.sqlite.prepare("SELECT COUNT(*) AS n FROM orders WHERE customer_id=? AND status='paid'").get(buyer.id).n,1);
 assert.equal(db.sqlite.prepare("SELECT COUNT(*) AS n FROM license_fulfillments").get().n,1);
});

test('revoked plan and blocked customer are refused everywhere',async()=>{
 const {admin,signIn}=setup();
 const me=await signIn({sub:'sub-x',email:'x@gmail.com'});
 let r=await admin('/api/admin/grant',{email:'x@gmail.com',confirm_email:'x@gmail.com',plan_code:'personal-1m',reference:'CK-9'});
 const licenseId=r.body.license.id;
 r=await admin('/api/admin/licenses/revoke',{license_id:licenseId});
 assert.equal(r.status,200);
 r=await me.call('/api/auth/seat',{client_id:client()});
 assert.equal(r.status,403);assert.equal(r.body.code,'LICENSE_REVOKED');

 r=await admin('/api/admin/customers/'+me.id+'/block',{reason:'chargeback'});
 assert.equal(r.status,200);
 r=await me.call('/api/auth/session');
 assert.equal(r.status,401,'blocking ends every session');
 const again=await signIn({sub:'sub-x',email:'x@gmail.com'});
 assert.equal(again.error,'blocked');
 r=await admin('/api/admin/customers/'+me.id+'/unblock',{});
 assert.equal((await signIn({sub:'sub-x',email:'x@gmail.com'})).id,me.id);
});

test('pilot migration grants remaining days; transfer moves a plan between Gmails',async()=>{
 const {admin,signIn}=setup();
 let r=await admin('/api/admin/grant',{email:'pilot@gmail.com',confirm_email:'pilot@gmail.com',seat_limit:1,days:12,
   reference:'PILOT-KH001',source:'pilot_migration'});
 assert.equal(r.status,201,JSON.stringify(r.body));
 const days=(Date.parse(r.body.license.expires_at)-Date.now())/86400000;
 assert.ok(days>11.9&&days<12.1,String(days));
 const licenseId=r.body.license.id;
 r=await admin('/api/admin/licenses/'+licenseId+'/transfer',{to_email:'right@gmail.com',confirm_email:'right@gmail.com',reason:'typo'});
 assert.equal(r.status,200,JSON.stringify(r.body));
 const right=await signIn({sub:'sub-right',email:'right@gmail.com'});
 assert.equal((await right.call('/api/auth/session')).body.state,'active');
 const wrong=await signIn({sub:'sub-pilot',email:'pilot@gmail.com'});
 // The plan moved, so the mistyped Gmail is back to having no plan at all.
 assert.equal((await wrong.call('/api/auth/session')).body.state,'none');
 r=await admin('/api/admin/customers?q=RIGHT@gmail.com');
 assert.equal(r.body.customers.length,1);assert.equal(r.body.customers[0].linked,1);
 r=await admin('/api/admin/customers/'+right.id);
 assert.equal(r.body.licenses.length,1);
});

test('Windows cannot consume a paid device seat when lease signing is not configured',async()=>{
 const {db,admin,signIn,desktop}=setup();
 const me=await signIn({sub:'sub-pc-no-signer',email:'pc-no-signer@gmail.com'});
 const granted=await admin('/api/admin/grant',{email:'pc-no-signer@gmail.com',
   confirm_email:'pc-no-signer@gmail.com',seat_limit:1,days:3,reference:'CK-NO-SIGNER'});
 assert.equal(granted.status,201,JSON.stringify(granted.body));
 const pc=await desktop(me.id);
 const response=await pc('/api/auth/seat',{client_id:client()});
 assert.equal(response.status,503,JSON.stringify(response.body));
 assert.equal(response.body.code,'LEASE_SIGNING_UNAVAILABLE');
 assert.notEqual(response.body.active,true);
 assert.equal(db.sqlite.prepare('SELECT COUNT(*) AS n FROM license_seats').get().n,0);
 // A browser license is online-only, so no Windows signer is needed.
 assert.equal((await me.call('/api/auth/seat',{client_id:client()})).status,200);
});

test('Windows app receives an Ed25519 lease bound to its seat that never outlives the plan',async()=>{
 const pair=await crypto.subtle.generateKey({name:'Ed25519'},true,['sign','verify']);
 const pkcs8=Buffer.from(await crypto.subtle.exportKey('pkcs8',pair.privateKey)).toString('base64');
 const {admin,signIn,desktop}=setup({LEASE_SIGNING_KEY:pkcs8});
 const me=await signIn({sub:'sub-pc',email:'pc@gmail.com'});
 await admin('/api/admin/grant',{email:'pc@gmail.com',confirm_email:'pc@gmail.com',seat_limit:2,days:2,reference:'CK-PC'});
 const pc=await desktop(me.id);
 const r=await pc('/api/auth/seat',{client_id:client()});
 assert.equal(r.status,200);
 const [body,sig]=r.body.lease.split('.');
 assert.ok(await crypto.subtle.verify({name:'Ed25519'},pair.publicKey,Buffer.from(sig,'base64url'),new TextEncoder().encode(body)));
 const lease=JSON.parse(Buffer.from(body,'base64url'));
 assert.equal(lease.customer_id,me.id);
 // 72h grace is capped by the 2-day plan.
 assert.equal(lease.valid_until,lease.license_expires_at);
 // Browsers never get a lease.
 const web=await me.call('/api/auth/seat',{client_id:client()});
 assert.equal(web.body.lease,undefined);
});

test('Worker clamps even misconfigured 168-hour grace to 72h (without shortening paid plan)',async()=>{
 const keys=await crypto.subtle.generateKey({name:'Ed25519'},true,['sign','verify']);
 const pkcs8=Buffer.from(await crypto.subtle.exportKey('pkcs8',keys.privateKey)).toString('base64');
 const farFuture=new Date(Date.now()+30*86400000).toISOString();
 const lease=await signLease({LEASE_SIGNING_KEY:pkcs8,LEASE_GRACE_HOURS:168},{
   customer:{id:'e02ab0e4-c2b0-4a23-99a1-acd430b37fea',email:'customer@gmail.com'},
   license:{id:'5b2f6a4e-1d0c-4b7e-9a3d-2f8e7c6b5a49',
            expires_at:farFuture,plan_code:'personal-1m',seat_limit:2},
   clientHash:'a'.repeat(64)
 });
 assert.ok(lease,'Missing Ed25519 lease');
 const [body,sig]=lease.split('.');
 assert.ok(await crypto.subtle.verify({name:'Ed25519'},keys.publicKey,
   Buffer.from(sig,'base64url'),new TextEncoder().encode(body)));
 const signed=JSON.parse(Buffer.from(body,'base64url'));
 const duration=Date.parse(signed.valid_until)-Date.parse(signed.issued_at);
 assert.equal(duration,72*3600000,'Offline lease may not exceed 72h');
 assert.ok(Date.parse(signed.valid_until)<Date.parse(signed.license_expires_at));
});

test('daily cleanup cancels stale pending orders',async()=>{
 const {db,signIn}=setup();
 const me=await signIn({sub:'sub-c',email:'c@gmail.com'});
 const r=await me.call('/api/auth/plan',{plan_code:'personal-1m'});
 db.sqlite.prepare("UPDATE orders SET expires_at='2020-01-01T00:00:00.000Z'").run();
 await cleanup(db);
 assert.equal(db.sqlite.prepare('SELECT status FROM orders WHERE id=?').get(r.body.id).status,'cancelled');
});

test('admin can price and switch plans; customers only see active priced plans',async()=>{
 const {admin,signIn}=setup();
 let r=await admin('/api/admin/plans',{code:'team-1m',name:'Team · 1 tháng',seat_limit:5,months:1,price_vnd:1990000,active:true,sort:40},'PUT');
 assert.equal(r.status,200);
 const me=await signIn({sub:'sub-p',email:'p@gmail.com'});
 r=await me.call('/api/auth/plans');
 assert.ok(r.body.plans.some(p=>p.code==='team-1m'&&p.seat_limit===5));
});

test('Admin API still requires Cloudflare Access',async()=>{
 const {env}=setup();
 const r=await adminApi(new Request(base+'/api/admin/grant',{method:'POST',headers:{'Content-Type':'application/json'},body:'{}'}),env);
 assert.equal(r.status,401);
});
