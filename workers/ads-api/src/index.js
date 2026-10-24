import { adminApi } from './admin.js';
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
