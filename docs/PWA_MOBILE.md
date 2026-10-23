# LHM Ads AI — Installable mobile PWA

## Mobile install

- Open the HTTPS deployment's `/studio` URL in Android Chrome. Choose **Cài LHM Ads AI trên điện thoại** (or the browser menu's **Cài đặt ứng dụng**).
- On iPhone, open the URL in Safari, choose **Chia sẻ → Thêm vào Màn hình chính**.
- Sign in with an existing LHM account; browser sessions are still controlled by the existing backend.

## Scope and security

- The PWA provides an installable, mobile-responsive shell and honest offline fallback. **PWA alone cannot perform monitoring 24/7 while the phone is locked**.
- The service worker only caches public JavaScript, CSS, fonts and icon files. It never caches `/studio`, `/api/*`, OAuth callbacks or reports.
- Access to live Google/Meta Ads requires the configured official API integration and secure HTTPS origin.
- **Existing backend storage model has not changed.** The current FastAPI deployment encrypts provider credentials in its SQLite store; therefore it **does not meet a phone-only token-storage guarantee**. Do not market PWA as device-only storage yet. Redesign OAuth/provider access and test each platform before claiming that guarantee.
- A local, opt-in read-only MCP stdio bridge now exists; this does not implement TikTok Ads MCP or expose a remote HTTP MCP service. See docs/MCP_PUSH_RELEASE.md.
- API responses are not real-time push; refresh cadence and quotas still apply. The PWA adds no Web Push backend, and background notifications cannot yet be promised.

## Test before release

1. `pytest -q tests/test_pwa.py`; `node --check static/sw.js` and `node --check static/pwa-install.js`.
2. Deploy over HTTPS and verify `/manifest.webmanifest` and `/sw.js` return HTTP 200.
3. On Android Chrome and iPhone Safari, test install, display-mode standalone, app navigation, login/logout, API access and offline fallback.
4. Inspect Application → Cache Storage: no `/api/`, `/studio` or tokens should be stored.
5. Test cache update behavior across deploys, including app reload and service-worker activation.
