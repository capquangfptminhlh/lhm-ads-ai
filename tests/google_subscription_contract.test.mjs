/* Run with node --test tests/google_subscription_contract.test.mjs */
import test from 'node:test';
import assert from 'node:assert/strict';
import {webcrypto} from 'node:crypto';

globalThis.crypto ??= webcrypto;
const {googleSubscription}=await import('../workers/ads-api/src/google-subscription.js');
const base='https://ads.lhmcrm.com';
const env={COMMERCE_DB:{},GOOGLE_CLIENT_ID:'unit-test.apps.googleusercontent.com',GOOGLE_CLIENT_SECRET:'not-real'};
const request=(p,options)=>new Request(base+p,options);

test('Google start uses OAuth code + PKCE S256 and short-lived secure state cookie',async()=>{
 const r=await googleSubscription(request('/api/auth/google/start'),env);
 assert.equal(r.status,302);
 const url=new URL(r.headers.get('location'));
 assert.equal(url.hostname,'accounts.google.com');
 assert.equal(url.searchParams.get('response_type'),'code');
 assert.equal(url.searchParams.get('code_challenge_method'),'S256');
 assert.ok(url.searchParams.get('code_challenge'));
 assert.equal(url.searchParams.get('redirect_uri'),base+'/api/auth/google/callback');
 assert.match(r.headers.get('set-cookie'),/HttpOnly; Secure; SameSite=Lax; Max-Age=300/);
 assert.equal(url.searchParams.get('state').length,64);
});
test('Google callback rejects missing or forged state before hitting token endpoint',async()=>{
 const r=await googleSubscription(request('/api/auth/google/callback?state=forged&code=fake'),env);
 assert.equal(r.status,401);
 assert.equal((await r.json()).error,'Google sign-in expired. Please try again.');
});
test('Subscription, plans and seat API require authenticated Google identity',async()=>{
 for(const [p,opts] of [
   ['/api/auth/session',undefined],['/api/auth/plans',undefined],
   ['/api/auth/seat',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({client_id:crypto.randomUUID()})}],
   ['/api/auth/plan',{method:'POST',headers:{'Content-Type':'application/json'},body:'{"plan_code":"personal-1m"}'}]
 ]){
   const r=await googleSubscription(request(p,opts),env);
   assert.equal(r.status,401,p);
 }
});
test('Cross-origin JSON mutations are refused',async()=>{
 const r=await googleSubscription(request('/api/auth/seat',{
   method:'POST',headers:{Origin:'https://evil.invalid','Content-Type':'application/json'},body:'{}'
 }),env);
 assert.equal(r.status,403);
});
test('No authentication without real configuration',async()=>{
 const r=await googleSubscription(request('/api/auth/google/start'),{COMMERCE_DB:{}});
 assert.equal(r.status,503);
});
