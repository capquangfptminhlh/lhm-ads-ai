/*
 * Cloudflare Worker routing scaffold for GitHub Pages at ads.lhm.com.
 * No OAuth, no Ads data or MCP is enabled here yet. Fail closed by design.
 * Port FastAPI -> Workers + D1 only after tenant isolation/security review.
 */
'use strict';
const json = (payload, status=200) => new Response(
  JSON.stringify(payload), {
    status, headers: {
      'Content-Type':'application/json; charset=utf-8',
      'Cache-Control':'no-store, max-age=0',
      'X-Content-Type-Options':'nosniff',
      'Referrer-Policy':'no-referrer'
    }
  }
);
export default {
  async fetch(request, env) {
    const path = new URL(request.url).pathname;
    if (path === '/api/_hosting/status' && request.method === 'GET') {
      return json({
        service: 'lhm-ads-cloudflare',
        auth_ready: false,
        ads_api_ready: false,
        mcp_ready: false,
        monitoring_ready: false,
        message: 'Cloudflare API has not yet been migrated from FastAPI and SQLite.'
      });
    }
    if (path.startsWith('/api/')) {
      return json({
        detail: 'Cloudflare backend is not activated. Do not submit credentials here.'
      }, 503);
    }
    // Worker Static Assets host the PWA under the SAME custom domain.\n    if (env && env.ASSETS) return env.ASSETS.fetch(request);\n    return json({detail:'Static asset binding unavailable'},503);
  }
};
