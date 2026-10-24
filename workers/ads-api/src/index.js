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
