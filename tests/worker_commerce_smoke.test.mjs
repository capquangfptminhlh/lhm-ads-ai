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
