/* Google-only SaaS: retired email/password customer routes must fail closed.
 * The new endpoints are covered by google_subscription_contract.test.mjs.
 */
import test from 'node:test';
import assert from 'node:assert/strict';
import worker from '../workers/ads-api/src/index.js';

const base='https://ads.lhmcrm.com';
const unavailable={COMMERCE_DB:{prepare(){throw Error('Retired customer routes MUST NOT access D1');}}};

test('all legacy customer password and key auth routes are permanently disabled',async()=>{
 for(const path of ['/api/customer/login','/api/customer/session',
                    '/api/customer/activate','/api/customer/logout']){
   for(const options of [undefined,{method:'POST',headers:{'Content-Type':'application/json'},
       body:JSON.stringify({email:'some@gmail.com',password:'wrong',key:'LHM-not-valid'})}]){
     const result=await worker.fetch(new Request(base+path,options),unavailable);
     assert.equal(result.status,410,path);
     assert.equal((await result.json()).code,'GOOGLE_LOGIN_REQUIRED');
   }
 }
});
test('Google login remains protected without Cloudflare D1',async()=>{
 const result=await worker.fetch(new Request(base+'/api/auth/session'),{});
 assert.equal(result.status,503);
});
