import test from 'node:test';
import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import worker from '../workers/ads-api/src/index.js';

const base='https://ads.lhmcrm.com';
const key='LHM-'+'A'.repeat(48);
const hash=createHash('sha256').update(key).digest('hex');
const mockDB={
  prepare(sql){
    return {
      async all(){
        if(sql.includes('sqlite_master'))return {results:[
          'customers','orders','licenses','payment_reviews','admin_audit','license_fulfillments'
        ].map(name=>({name}))};
        return {results:[]};
      },
      bind(...args){
        return {async first(){
          if(sql.includes('FROM licenses WHERE key_hash=?') && args[0]===hash)
            return {status:'active',expires_at:'2099-01-01T00:00:00.000Z'};
          return null;
        }};
      }
    };
  }
};

test('hosting health reports missing commerce dependencies, never claims auth is ready',async()=>{
  const res=await worker.fetch(new Request(base+'/api/_hosting/status'),{});
  assert.equal(res.status,200);
  const state=await res.json();
  assert.equal(state.auth_ready,false);
  assert.equal(state.commerce_binding_present,false);
  assert.equal(state.commerce_admin_config_ready,false);
});

test('commercial routes fail closed without database',async()=>{
  const admin=await worker.fetch(new Request(base+'/api/admin/overview'),{});
  assert.equal(admin.status,503);
  const verify=await worker.fetch(new Request(base+'/api/license/verify',{
    method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({key})
  }),{});
  assert.equal(verify.status,503);
});

test('admin API rejects non-Access caller even when database exists',async()=>{
  const res=await worker.fetch(new Request(base+'/api/admin/overview'),{COMMERCE_DB:mockDB});
  assert.equal(res.status,401);
});

test('valid key verification is read-only and returns no PII',async()=>{
  const res=await worker.fetch(new Request(base+'/api/license/verify',{
    method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({key})
  }),{COMMERCE_DB:mockDB});
  assert.equal(res.status,200);
  const out=await res.json();
  assert.equal(out.valid,true);
  assert.equal(out.expires_at,'2099-01-01T00:00:00.000Z');
  assert.equal('customer_id' in out,false);
});

test('invalid and malformed key never return customer data',async()=>{
  for(const candidate of ['wrong','LHM-'+'B'.repeat(48)]){
    const res=await worker.fetch(new Request(base+'/api/license/verify',{
      method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({key:candidate})
    }),{COMMERCE_DB:mockDB});
    assert.deepEqual(await res.json(),{valid:false});
  }
});


test('Cloudflare Access verifies signed JWT, audience and admin email',async()=>{
  const pair=await crypto.subtle.generateKey(
    {name:'RSASSA-PKCS1-v1_5',modulusLength:2048,
      publicExponent:new Uint8Array([1,0,1]),hash:'SHA-256'},
    true,['sign','verify']);
  const jwk=await crypto.subtle.exportKey('jwk',pair.publicKey);
  jwk.kid='test-key';
  const encode=obj=>Buffer.from(JSON.stringify(obj)).toString('base64url');
  async function makeJwt(overrides={}){
    const header=encode({alg:'RS256',kid:'test-key'});
    const payload=encode({aud:'test-aud',iss:'https://unit.cloudflareaccess.com',
      sub:'admin-user',email:'owner@example.invalid',exp:Math.floor(Date.now()/1000)+3600,
      ...overrides});
    const data=header+'.'+payload;
    const signature=await crypto.subtle.sign('RSASSA-PKCS1-v1_5',pair.privateKey,
      new TextEncoder().encode(data));
    return data+'.'+Buffer.from(signature).toString('base64url');
  }
  const originalFetch=globalThis.fetch;
  globalThis.fetch=async url=>{
    assert.equal(url,'https://unit.cloudflareaccess.com/cdn-cgi/access/certs');
    return new Response(JSON.stringify({keys:[jwk]}),{status:200});
  };
  try{
    const env={COMMERCE_DB:mockDB,CF_ACCESS_TEAM_DOMAIN:'unit.cloudflareaccess.com',
      CF_ACCESS_AUD:'test-aud',ADMIN_EMAIL:'owner@example.invalid'};
    for(const [claim,code] of [
      [{},200],
      [{aud:'wrong'},401],
      [{email:'somebody-else@example.invalid'},401],
      [{exp:Math.floor(Date.now()/1000)-60},401]
    ]){
      const jwt=await makeJwt(claim);
      const res=await worker.fetch(new Request(base+'/api/admin/overview',{
        headers:{'Cf-Access-Jwt-Assertion':jwt}
      }),env);
      assert.equal(res.status,code,JSON.stringify(claim));
    }
  }finally{globalThis.fetch=originalFetch;}
});
