/* Cloudflare static bundle has no live Ads authentication until backend port is verified. */
'use strict';
(() => {
  const form = document.getElementById('login-form');
  const status = document.getElementById('lhm-hosted-status');
  const guard = document.getElementById('lhm-static-api-guard');
  if (!form || !status || !guard) return; // Desktop FastAPI build has no guard.
  const submit = form.querySelector('button[type=submit]');
  if (submit) submit.disabled = true;
  form.addEventListener('submit', event => {
    if (guard.isConnected) {
      event.preventDefault();
      event.stopImmediatePropagation();
    }
  }, true);
  async function checkApi() {
    try {
      const controller = new AbortController();
      const timeout = setTimeout(() => controller.abort(), 4000);
      let res;
      try {
        res = await fetch('/api/_hosting/status', {
          method: 'GET', headers: {'Accept':'application/json'},
          credentials: 'same-origin', cache:'no-store', signal: controller.signal
        });
      } finally { clearTimeout(timeout); }
      const ct = res.headers.get('content-type') || '';
      if (!res.ok || !ct.includes('application/json')) return;
      const data = await res.json();
      // This must be a verified API auth readiness signal, not just 200 /healthz.
      if (data?.service === 'lhm-ads-cloudflare' && data?.auth_ready === true && data?.device_only_ready === true && data?.ads_credential_custody === 'device_only') {
        guard.remove();
        status.textContent = 'Cloudflare API đã sẵn sàng. Bạn có thể đăng nhập.';
        status.style.borderColor = '#60a57d';
        if (submit) submit.disabled = false;
      }
    } catch (_) { /* Fail closed. Never enable credential input based on guesses. */ }
  }
  checkApi();
})();
