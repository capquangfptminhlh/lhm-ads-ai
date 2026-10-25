/* Local HTTP server running the real Worker against SQLite for end-to-end
 * browser tests. TEST ONLY: it signs a Cloudflare Access JWT for the admin and
 * offers /__test/signin to stand in for Google, so never deploy it.
 * Usage: node tests/helpers/worker-dev-server.mjs <built-site-dir>
 */
import http from 'node:http';
import {readFile,stat} from 'node:fs/promises';
import {join,extname,resolve} from 'node:path';
import {webcrypto,createHash} from 'node:crypto';
import {createD1} from './d1-sqlite.mjs';
globalThis.crypto??=webcrypto;
const worker=(await import('../../workers/ads-api/src/index.js')).default;
const {linkGoogleIdentity}=await import('../../workers/ads-api/src/google-subscription.js');

const site=resolve(process.argv[2]||'_site');
const db=createD1();
const TYPES={'.html':'text/html; charset=utf-8','.js':'text/javascript','.css':'text/css','.json':'application/json',
 '.webmanifest':'application/manifest+json','.png':'image/png','.svg':'image/svg+xml','.woff2':'font/woff2','.ico':'image/x-icon'};

const keys=await crypto.subtle.generateKey({name:'RSASSA-PKCS1-v1_5',modulusLength:2048,publicExponent:new Uint8Array([1,0,1]),hash:'SHA-256'},true,['sign','verify']);
const jwk={...(await crypto.subtle.exportKey('jwk',keys.publicKey)),kid:'dev'};
const realFetch=globalThis.fetch;
globalThis.fetch=async(url,...rest)=>String(url)==='https://dev.cloudflareaccess.com/cdn-cgi/access/certs'
 ?Response.json({keys:[jwk]}):realFetch(url,...rest);
async function accessJwt(){
 const b=x=>Buffer.from(JSON.stringify(x)).toString('base64url');
 const now=Math.floor(Date.now()/1000);
 const unsigned=b({alg:'RS256',kid:'dev'})+'.'+b({aud:'dev-aud',iss:'https://dev.cloudflareaccess.com',sub:'admin',email:'owner@example.com',iat:now,exp:now+600});
 const sig=await crypto.subtle.sign('RSASSA-PKCS1-v1_5',keys.privateKey,new TextEncoder().encode(unsigned));
 return unsigned+'.'+Buffer.from(sig).toString('base64url');
}
async function asset(request){
 let path=decodeURIComponent(new URL(request.url).pathname);
 if(path.endsWith('/'))path+='index.html';
 const file=join(site,path);
 if(!file.startsWith(site))return new Response('Forbidden',{status:403});
 try{
   const info=await stat(file);
   if(info.isDirectory())return Response.redirect(new URL(path+'/',request.url),301);
   return new Response(await readFile(file),{headers:{'Content-Type':TYPES[extname(file)]||'application/octet-stream'}});
 }catch{return new Response('Not found',{status:404});}
}
const env={COMMERCE_DB:db,ASSETS:{fetch:asset},CF_ACCESS_TEAM_DOMAIN:'dev.cloudflareaccess.com',CF_ACCESS_AUD:'dev-aud',
 ADMIN_EMAIL:'owner@example.com',GOOGLE_CLIENT_ID:'dev',GOOGLE_CLIENT_SECRET:'dev',
 BANK_BIN:'970436',BANK_ACCOUNT_NO:'0123456789',BANK_ACCOUNT_NAME:'NGUYEN VAN A'};

const server=http.createServer(async(req,res)=>{
 try{
   const url=new URL(req.url,'http://'+req.headers.host);
   if(url.pathname==='/__test/signin'){
     const linked=await linkGoogleIdentity(db,{sub:url.searchParams.get('sub'),email:url.searchParams.get('email'),
       name:url.searchParams.get('name')||'Khách thử',picture:null});
     if(linked.error){res.writeHead(403,{'Content-Type':'application/json'});res.end(JSON.stringify(linked));return;}
     const token=createHash('sha256').update(String(Math.random())).digest('hex');
     await db.prepare('INSERT INTO customer_sessions(token_hash,customer_id,expires_at) VALUES(?,?,?)')
       .bind(createHash('sha256').update(token).digest('hex'),linked.id,new Date(Date.now()+86400000).toISOString()).run();
     res.writeHead(302,{'Set-Cookie':'lhm_google_session='+token+'; Path=/; HttpOnly; SameSite=Lax',Location:'/local/'});
     res.end();return;
   }
   const chunks=[];for await(const c of req)chunks.push(c);
   const headers=new Headers();
   for(const [k,v] of Object.entries(req.headers))headers.set(k,Array.isArray(v)?v.join(', '):v);
   if(url.pathname.startsWith('/admin')||url.pathname.startsWith('/api/admin/'))headers.set('Cf-Access-Jwt-Assertion',await accessJwt());
   const request=new Request(url,{method:req.method,headers,body:chunks.length&&!['GET','HEAD'].includes(req.method)?Buffer.concat(chunks):undefined});
   const response=await worker.fetch(request,env,{waitUntil(){}});
   const out={};
   response.headers.forEach((v,k)=>{if(k!=='set-cookie')out[k]=v;});
   const cookies=response.headers.getSetCookie?.()||[];
   if(cookies.length)out['set-cookie']=cookies.map(c=>c.replace('; Secure',''));
   res.writeHead(response.status,out);
   res.end(Buffer.from(await response.arrayBuffer()));
 }catch(e){res.writeHead(500,{'Content-Type':'text/plain'});res.end(String(e.stack||e));}
});
server.listen(0,'127.0.0.1',()=>console.log('LISTENING '+server.address().port));
