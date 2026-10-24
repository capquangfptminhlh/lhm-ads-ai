import test from 'node:test';
import assert from 'node:assert/strict';
import worker from '../workers/ads-api/src/index.js';
const base='https://ads.lhmcrm.com';
test('customer session requires D1 binding',async()=>{
 const r=await worker.fetch(new Request(base+'/api/customer/session'),{});
 assert.equal(r.status,503);
});
test('customer signin cannot accept password via GET or malformed JSON',async()=>{
 const db={prepare(){throw Error('should not use DB for invalid payload')}};
 const get=await worker.fetch(new Request(base+'/api/customer/login'),{COMMERCE_DB:db});
 assert.equal(get.status,405);
 const post=await worker.fetch(new Request(base+'/api/customer/login',{
  method:'POST',headers:{'content-type':'application/json'},body:'{bad'
 }),{COMMERCE_DB:db});
 assert.equal(post.status,400);
});
test('customer email/password validation blocks weak credentials before DB queries',async()=>{
 const db={prepare(){throw Error('unexpected query')}};
 const r=await worker.fetch(new Request(base+'/api/customer/login',{
  method:'POST',headers:{'content-type':'application/json'},
  body:JSON.stringify({email:'test@example.com',password:'123'})
 }),{COMMERCE_DB:db});
 assert.equal(r.status,400);
});
test('cross-origin PWA customer auth is rejected',async()=>{
 const r=await worker.fetch(new Request(base+'/api/customer/session',{
  headers:{origin:'https://evil.example'}
 }),{COMMERCE_DB:{}});
 assert.equal(r.status,403);
});
test('customer session never permits anonymous request',async()=>{
 const db={prepare(){throw Error('no query for missing cookie')}};
 const r=await worker.fetch(new Request(base+'/api/customer/session'),{COMMERCE_DB:db});
 assert.equal(r.status,401);
 assert.equal((await r.json()).authenticated,false);
});
