import { adminApi, adminIdentity } from './admin.js';
import { customerAuth } from './customer-auth.js';
/*
 * Cloudflare serves installable PWA assets plus LHM subscription/control-plane API.
 * STRICT device-only advertising credential custody:
 * no Ads OAuth secrets/tokens, account IDs or report data may be stored at Cloudflare.
 * All Ads-specific APIs and the MCP cloud gateway remain CLOSED pending a vetted
 * device-only client architecture. Never claim this scaffold is commercially ready.
 */
'use strict';
const json=(payload,status=200)=>new Response(JSON.stringify(payload),{
  status,headers:{
    'Content-Type':'application/json; charset=utf-8',
    'Cache-Control':'no-store, max-age=0',
    'X-Content-Type-Options':'nosniff',
    'Referrer-Policy':'no-referrer'
  }
});
export default {
  async fetch(request,env){
    const path=new URL(request.url).pathname;
    // Admin UI is NEVER a publicly downloadable static page.
    // This requires Worker-first asset routing for /admin and /admin/*.
    if(path==='/admin' || path.startsWith('/admin/')){
      if(request.method!=='GET' && request.method!=='HEAD')
        return json({error:'Method not allowed'},405);
      const actor=await adminIdentity(request,env);
      if(!actor){
        const page='<!doctype html><html lang="vi"><meta charset="utf-8">'+
          '<meta name="viewport" content="width=device-width,initial-scale=1">'+
          '<meta name="robots" content="noindex,nofollow">'+
          '<title>LHM Ads AI · Quyền quản trị</title>'+
          '<style>body{font:16px system-ui;margin:0;min-height:100dvh;display:grid;place-items:center;'+
          'background:#f3f8ff;color:#24415d}.panel{margin:20px;max-width:520px;padding:36px;'+
          'background:#fff;border:1px solid #dce8f4;border-radius:20px;'+
          'box-shadow:0 20px 50px #1d5b891a}a{color:#1978c6}</style>'+
          '<main class="panel"><h1>Quản trị chưa được xác thực</h1>'+
          '<p>Chỉ chủ sở hữu đã đăng nhập qua Cloudflare Access mới được vào trang này.</p>'+
          '<p>Hãy kiểm tra cấu hình Cloudflare Access và email quản trị viên.</p>'+
          '<a href="/">← Về trang chủ LHM Ads AI</a></main></html>';
        return new Response(request.method==='HEAD'?null:page,{
          status:401,headers:{'Content-Type':'text/html; charset=utf-8',
          'Cache-Control':'no-store, max-age=0','X-Robots-Tag':'noindex, nofollow',
          'X-Frame-Options':'DENY','X-Content-Type-Options':'nosniff',
          'Referrer-Policy':'no-referrer'}});
      }
      if(path==='/admin')return Response.redirect(new URL('/admin/',request.url),302);
      if(!env?.ASSETS)return json({error:'Static assets unavailable'},503);
      const asset=await env.ASSETS.fetch(request);
      const headers=new Headers(asset.headers);
      headers.set('Cache-Control','no-store, max-age=0');
      headers.set('X-Robots-Tag','noindex, nofollow');
      return new Response(request.method==='HEAD'?null:asset.body,{
        status:asset.status,statusText:asset.statusText,headers
      });
    }
    if(path==='/api/_hosting/status' && request.method==='GET') {
      const commerce_binding_present=Boolean(env?.COMMERCE_DB);
      const commerce_access_configured=Boolean(env?.CF_ACCESS_TEAM_DOMAIN && env?.CF_ACCESS_AUD && env?.ADMIN_EMAIL);
      let commerce_schema_ready=false;
      if(commerce_binding_present){
        try{
          const rows=await env.COMMERCE_DB.prepare(
            "SELECT name FROM sqlite_master WHERE type='table' AND name IN ('customers','orders','licenses','payment_reviews','admin_audit','license_fulfillments')"
          ).all();
          commerce_schema_ready=(rows.results||[]).length===6;
        }catch(_){commerce_schema_ready=false;}
      }
      return json({
        service:'lhm-ads-cloudflare',
        auth_ready:false,
        device_only_ready:false,
        ads_api_ready:false,
        mcp_ready:false,
        monitoring_ready:false,
        commerce_binding_present,
        commerce_access_configured,
        commerce_schema_ready,
        commerce_admin_config_ready:commerce_binding_present && commerce_access_configured && commerce_schema_ready,
        commerce_access_policy_verified:false,
        ads_credential_custody:'device_only',
        message:'Cloudflare control plane and local-only Ads access not yet implemented.'
      });
    }
    // Public read-only key validation. Never returns customer PII or Ads data.
    if(path==='/api/license/verify' && request.method==='POST'){
      if(!env?.COMMERCE_DB)return json({error:'License service not configured'},503);
      const url=new URL(request.url);
      const origin=request.headers.get('origin');
      if(origin && origin!==url.origin)return json({error:'Origin mismatch'},403);
      if(request.headers.get('content-type')?.split(';')[0]!=='application/json')
        return json({error:'Expected JSON'},415);
      const raw=await request.text();
      if(raw.length>512)return json({error:'Payload too large'},413);
      let parsed;try{parsed=JSON.parse(raw)}catch{return json({error:'Invalid JSON'},400);}
      const key=typeof parsed.key==='string'?parsed.key.trim().toUpperCase():'';
      if(!/^LHM-[A-F0-9]{48}$/.test(key))return json({valid:false});
      const digest=await crypto.subtle.digest('SHA-256',new TextEncoder().encode(key));
      const hash=Array.from(new Uint8Array(digest),v=>v.toString(16).padStart(2,'0')).join('');
      try{
        const license=await env.COMMERCE_DB.prepare(
          "SELECT status,expires_at FROM licenses WHERE key_hash=?"
        ).bind(hash).first();
        const valid=Boolean(license && license.status==='active' && Date.parse(license.expires_at)>Date.now());
        return json(valid?{valid:true,expires_at:license.expires_at}:{valid:false});
      }catch{return json({error:'License database unavailable'},503);}
    }
    if(path.startsWith('/api/admin/'))return adminApi(request,env);
    if(path.startsWith('/api/customer/'))return customerAuth(request,env);
    if(path.startsWith('/api/')){
      return json({
        detail:'Cloudflare Ads API is not enabled. Do not send Ads credentials to this service.',
        code:'DEVICE_ONLY_NOT_READY'
      },503);
    }
    if(env && env.ASSETS) return env.ASSETS.fetch(request);
    return json({detail:'Static asset binding unavailable'},503);
  }
};
