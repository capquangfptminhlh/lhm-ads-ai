import test from 'node:test';
import assert from 'node:assert/strict';
import {webcrypto,createHash} from 'node:crypto';
globalThis.crypto??=webcrypto;
// Node 22+ detects import syntax in this Worker .js module.
const {desktopPair}=await import('../workers/ads-api/src/desktop-pair.js');
const origin='https://ads.lhmcrm.com';
const hash=x=>createHash('sha256').update(x).digest('hex');
const client=(path,body)=>new Request(origin+path,{method:'POST',headers:{'content-type':'application/json'},
 body:JSON.stringify(body)});
const verifier='d'.repeat(64);
const env=()=>{
 let pair=null,session=null;
 const db={prepare(sql){return{bind(...args){return{
   async run(){
     if(sql.startsWith('INSERT INTO desktop_pairings')){pair={id:args[0],verifier_hash:args[1],display_code:args[2],expires_at:args[3],customer_id:null};return{meta:{changes:1}};}
     if(sql.startsWith('DELETE FROM desktop_pairings WHERE expires_at'))return{meta:{changes:0}};
     if(sql.startsWith('DELETE FROM desktop_pairings WHERE id=')){
       if(pair?.id!==args[0]||pair.verifier_hash!==args[1]||pair.customer_id!==args[2])return{meta:{changes:0}};
       pair=null;return{meta:{changes:1}};
     }
     if(sql.startsWith('INSERT INTO desktop_sessions')){session={token_hash:args[0],customer_id:args[1],expires_at:args[2]};return{meta:{changes:1}};}
     return{meta:{changes:0}};
   },
   async first(){
     if(sql.startsWith('SELECT customer_id FROM desktop_pairings')){
       if(pair?.id!==args[0]||pair.verifier_hash!==args[1]||pair.expires_at<=args[2])return null;
       return{customer_id:pair.customer_id};
     }
     if(sql.startsWith('SELECT id FROM licenses'))return args[0]==='user-1'?{id:'license-1'}:null;
     if(sql.startsWith('SELECT email FROM customers'))return{email:'owner@example.com'};
     if(sql.startsWith('SELECT display_code,customer_id,expires_at FROM desktop_pairings'))
       return pair?{display_code:pair.display_code,customer_id:pair.customer_id,expires_at:pair.expires_at}:null;
     return null;
   }
 };}}}};
 return{COMMERCE_DB:db,getPair:()=>pair,approve:()=>{if(pair)pair.customer_id='user-1';},getSession:()=>session};
};
test('one-time desktop pairing cannot claim before consent, and does not store raw token',async()=>{
 const e=env();
 let r=await desktopPair(client('/api/desktop/pair/start',{verifier_hash:hash(verifier)}),e);
 assert.equal(r.status,201);const start=await r.json();
 assert.match(start.verify_url,/^https:\/\/ads\.lhmcrm\.com\/desktop\/pair\/\?id=/);
 assert.equal(start.display_code.length,6);
 const pairId=start.pair_id;
 r=await desktopPair(client('/api/desktop/pair/claim',{pair_id:pairId,verifier:'f'.repeat(64)}),e);
 assert.equal(r.status,410);
 r=await desktopPair(client('/api/desktop/pair/claim',{pair_id:pairId,verifier}),e);
 assert.equal(r.status,202);
 e.approve();
 r=await desktopPair(client('/api/desktop/pair/claim',{pair_id:pairId,verifier}),e);
 assert.equal(r.status,200);const allowed=await r.json();
 assert.equal(allowed.status,'authorized');assert.match(allowed.desktop_token,/^[0-9a-f]{64}$/);
 assert.equal(e.getSession().token_hash,hash(allowed.desktop_token));
 assert.notEqual(e.getSession().token_hash,allowed.desktop_token);
 r=await desktopPair(client('/api/desktop/pair/claim',{pair_id:pairId,verifier}),e);
 assert.equal(r.status,410);
});
test('pairing approval refuses cross-site post',async()=>{
 const e=env();
 const r=await desktopPair(new Request(origin+'/api/desktop/pair/approve',{
   method:'POST',headers:{Origin:'https://attacker.invalid','Content-Type':'application/x-www-form-urlencoded'},
   body:'id=00000000-0000-4000-8000-000000000000'}),e);
 assert.equal(r.status,403);
});
test('browser pairing page does not expose verifier or desktop bearer',async()=>{
 const e=env();
 const r=await desktopPair(new Request(origin+'/desktop/pair/?id=11111111-1111-4111-8111-111111111111'),e);
 const html=await r.text();assert.match(html,/Liên kết đã hết hạn/);
 assert.doesNotMatch(html,/desktop_token|verifier_hash/);
});
