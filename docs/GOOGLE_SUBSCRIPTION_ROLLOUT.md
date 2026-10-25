# Google login + subscription gate (deployment checklist)

Status: **feature branch for review, NOT deployed or production verified**.

## Product decision
- The customer signs in once with their real Google account; email alone is not authentication.
- New customer accounts can sign in without a subscription but **cannot use the Ads account-add UI** until a paid license is issued.
- Monthly plans have 1, 3 or 5 **concurrent active browser installations** (not permanent machine binding).
- When all seats are occupied, a new sign-in may replace the least-recently-active session. Old sessions lose permission at their next heartbeat; no manual remove-device action required.
- **Only** Google account identity (verified Google sub + email), order and license metadata, and one-way hashes of random client seat IDs are in Cloudflare D1. Google Ads, Meta Ads, OpenRouter credentials, Ad account IDs and reports remain only on the customer's own device.
- PWA vault names are keyed by server-issued customer UUID; switching Google accounts on the same browser must not open another customer's encrypted vault.

## Required Cloudflare setup BEFORE activating feature
1. Back up D1 and apply `migrations/0004_google_seats.sql` through Wrangler **before** deploying the Worker.
2. In Google Cloud Console, create **OAuth Web application** credentials. Configure exactly:
   - Authorized redirect: `https://ads.lhmcrm.com/api/auth/google/callback`
   - Origin: `https://ads.lhmcrm.com`
   - Enable Google authentication with `openid email profile`. Production consent-screen publishing/verification requirements still apply.
3. Store `GOOGLE_CLIENT_ID` and `GOOGLE_CLIENT_SECRET` as **Cloudflare Worker secrets**, not git files or frontend JS.
4. Set server-side non-secret Worker variables `PRICE_SEAT_1`, `PRICE_SEAT_3`, `PRICE_SEAT_5` in VND per month. They must be positive integers. **Do not use placeholder prices in production**. Existing key issuance is still performed by Admin *after* independent payment verification.
5. Keep `COMMERCE_DB` binding and Cloudflare Access protection of `/admin/*` and `/api/admin/*`. Test Google sign-in, pending order, admin approval, paid license, renewal, expiry, concurrent 4th login eviction and authentication failures in staging.
6. Only enable production after test reports and real smoke tests pass on mobile and desktop. Never mark OAuth, pricing, billing or Windows as complete based on code review alone.

## PWA
- `GET /api/auth/google/start` initiates OAuth code + PKCE/state/nonce.
- `GET /api/auth/google/callback` verifies Google's **RSA signature, audience, issuer, expiry, verified email and nonce**. It issues an HttpOnly session cookie.
- `GET /api/auth/session` provides license status, `GET /api/auth/plans` server-defined pricing, and `POST /api/auth/plan` requests a pending order.
- `POST /api/auth/seat` grants/refeshes 120-second seats for active licenses; it stores only hashed random IDs. Heartbeats never silently reclaim evicted seats.
- `/local/` client stays gated without an active seat. `/studio/` on the hosted Worker redirects to `/local/`; the local Windows application is a separate offline backend.

## Windows app — IMPORTANT not implemented by this patch
The current Windows desktop app is **Python/pywebview/WebView2**, not Electron. It still uses a signed local-device license file. This branch **does not** yet implement the secure Google-browser-to-desktop pairing, server-side seat heartbeat or PC-side mutation gate; do not market Windows as covered by the new multi-device plan. That requires a separate trusted browser-to-native authorization handoff and a fail-closed license dependency in the local API. Never copy Google OAuth client secrets, a raw website session cookie or Ads tokens into the packaged binary.

## Known limitations / to verify
- A normal browser PWA cannot have an unforgeable hardware fingerprint. Concurrent sessions are a practical subscription quota, not DRM.
- Offline authenticated access is blocked; product requires periodic Internet access to enforce concurrent seats. The PWA encrypted vault remains stored locally.
- The default local IndexedDB vault created by pre-migration demo releases is not silently assigned to a Google identity; users should export existing encrypted backups before migration.
- Payment is **manual verified** in current Admin; do not promise automatic provisioning, refunds or card collection.
- Old password/customer endpoints still exist for backwards compatibility and require a separate migration/deprecation policy.
