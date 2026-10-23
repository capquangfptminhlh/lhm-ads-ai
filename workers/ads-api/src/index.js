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
      return json({
        service:'lhm-ads-cloudflare',
        auth_ready:false,
        device_only_ready:false,
        ads_api_ready:false,
        mcp_ready:false,
        monitoring_ready:false,
        ads_credential_custody:'device_only',
        message:'Cloudflare control plane and local-only Ads access not yet implemented.'
      });
    }
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
