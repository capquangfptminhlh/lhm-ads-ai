import { adminApi, adminIdentity } from './admin.js';
import { customerAuth } from './customer-auth.js';
import { googleSubscription } from './google-subscription.js';
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
    // Hosted Studio demo cannot bypass the Google subscription gate.
    if(path==='/studio'||path.startsWith('/studio/'))
      return Response.redirect(new URL('/local/',request.url),302);
    // Admin UI is NEVER a publicly downloadable static page.
    // This requires Worker-first asset routing for /admin and /admin/*.
    if(path==='/admin' || path.startsWith('/admin/')){
      if(request.method!=='GET' && request.method!=='HEAD')
        return json({error:'Method not allowed'},405);
      const configured=Boolean(env?.CF_ACCESS_TEAM_DOMAIN && env?.CF_ACCESS_AUD && env?.ADMIN_EMAIL);
      const actor=configured?await adminIdentity(request,env):null;
      if(!actor){
        const unavailable=!configured;
        const heading=unavailable?'Quản trị chưa được kích hoạt':'Cần đăng nhập quản trị';
        const description=unavailable
          ?'Cloudflare Access chưa có cấu hình xác thực cho LHM Ads AI. Đây không phải lỗi mật khẩu hoặc trình duyệt.'
          :'Phiên quản trị chưa được Cloudflare Access xác thực. Chỉ email quản trị được cấp quyền mới mở được dashboard.';
        const detail=unavailable
          ?'<strong>Cần hoàn tất:</strong> (1) Tạo ứng dụng Cloudflare Access bảo vệ /admin/* và /api/admin/*; '+
           '(2) cấu hình CF_ACCESS_TEAM_DOMAIN, CF_ACCESS_AUD, ADMIN_EMAIL; '+
           '(3) gắn D1 COMMERCE_DB và chạy migrations.'
          :'<strong>Kiểm tra:</strong> Đăng nhập qua ứng dụng Cloudflare Access đã bảo vệ đường dẫn này. '+
           'Nếu vẫn quay lại trang này, kiểm tra Access policy, AUD và ADMIN_EMAIL.';
        const page='<!doctype html><html lang="vi"><head><meta charset="utf-8">'+
          '<meta name="viewport" content="width=device-width,initial-scale=1">'+
          '<meta name="robots" content="noindex,nofollow">'+
          '<title>LHM Ads AI · '+heading+'</title>'+
          '<style>*{box-sizing:border-box}body{margin:0;min-height:100dvh;display:grid;place-items:center;'+
          'font:15px/1.7 system-ui,-apple-system,Segoe UI,sans-serif;background:radial-gradient(circle at 85% 12%,#daecff,transparent 43%),#f3f8ff;'+
          'color:#294460;padding:20px}.panel{width:min(100%,610px);padding:clamp(23px,4vw,43px);'+
          'background:#fff;border:1px solid #dce8f4;border-radius:20px;box-shadow:0 24px 58px #265b8b17}'+
          '.logo{font-weight:850;color:#2a7ecc;letter-spacing:.4px}.tag{display:inline-block;margin-top:23px;padding:5px 11px;'+
          'border-radius:99px;background:#fff2df;color:#8e651f;font-size:11px;font-weight:800;letter-spacing:.7px}'+
          'h1{font-size:clamp(24px,4vw,32px);line-height:1.25;color:#243c58;margin:13px 0 10px}'+
          'p{color:#627f99;margin:10px 0}.notice{margin-top:23px;border-left:3px solid #2d8bd6;'+
          'background:#eff7ff;padding:15px;border-radius:0 12px 12px 0;color:#456986}'+
          '.actions{display:flex;flex-wrap:wrap;gap:10px;margin-top:25px}a.btn{display:inline-block;border-radius:11px;'+
          'padding:10px 15px;text-decoration:none;font-weight:750;border:1px solid #d5e6f5;color:#236faa;background:#f2f8ff}'+
          'a.btn.primary{color:#fff;background:#267fda;border-color:#267fda}</style></head>'+
          '<body><main class="panel"><div class="logo">✦ LHM ADS AI / ADMIN</div>'+
          '<div class="tag">'+(unavailable?'CHƯA CẤU HÌNH':'YÊU CẦU XÁC THỰC')+'</div>'+
          '<h1>'+heading+'</h1><p>'+description+'</p><div class="notice">'+detail+'</div>'+
          '<div class="actions"><a class="btn primary" href="https://dash.cloudflare.com/">Mở Cloudflare</a>'+
          '<a class="btn" href="https://github.com/capquangfptminhlh/lhm-ads-ai/blob/main/docs/ADMIN_COMMERCE_SETUP.md">Hướng dẫn kích hoạt</a>'+
          '<a class="btn" href="/">Trang chủ</a></div>'+
          '</main></body></html>';
        return new Response(request.method==='HEAD'?null:page,{
          status:unavailable?503:401,headers:{'Content-Type':'text/html; charset=utf-8',
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
      let customer_auth_schema_ready=false;
      if(commerce_binding_present){
        try{
          const tables=await env.COMMERCE_DB.prepare(
            "SELECT name FROM sqlite_master WHERE type='table' AND name IN ('customer_auth','customer_sessions')"
          ).all();
          customer_auth_schema_ready=(tables.results||[]).length===2;
        }catch(_){customer_auth_schema_ready=false;}
      }
      return json({
        service:'lhm-ads-cloudflare',
        customer_auth_schema_ready,
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
    if(path.startsWith('/api/auth/'))return googleSubscription(request,env);
    // Legacy password sessions remain for migration, but customer PWA uses Google only.
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
