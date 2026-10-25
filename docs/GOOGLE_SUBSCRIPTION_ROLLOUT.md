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
1. Back up D1 and apply both `migrations/0004_google_seats.sql` and `migrations/0005_desktop_pairing.sql` through Wrangler **before** deploying the Worker.
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

## Windows app — code added to feature branch, NOT yet customer-ready
The current Windows desktop is **Python/pywebview/WebView2**, not Electron.
This branch now contains a native CloudLicense client and a Google-only WebView2 sign-in overlay,
but all Windows cloud licensing must remain **staging only** until tested with
real Cloudflare Google OAuth credentials and an actual signed/packaged Windows EXE.

- `POST /api/desktop/pair/start` takes a SHA-256 hash of the locally generated random proof; server creates a short-lived pairing URL and a display code.
- Browser opens first-party `/desktop/pair/?id=...`, signs in with Google,
  selects/pays for the required plan and must explicitly approve the PC.
- PC polls `POST /api/desktop/pair/claim` with the secret verifier that never leaves the PC except via its direct TLS request. A single-use bearer license grant is issued only after approval.
- On Windows the bearer is saved via DPAPI and used only for `/api/auth/seat` heartbeats; no Ads tokens, report values, Google/Meta ad-account IDs or client credentials pass to Cloudflare.
- Windows local API gate in `ads_core/desktop_cloud_license.py` returns HTTP 402 before Ads reads/writes if the cloud seat lease is absent/expired. Local login and pairing control endpoints remain accessible to resolve the issue.
- Launch this branch for staging with `LHM_CLOUD_LICENSE_MODE=required`. Default PC builds retain the legacy license path and **are not protected** by the new cloud subscription mechanism, pending acceptance.
- **Google-only Windows flow is now implemented in source:** the native WebView2 receives a per-process proof, displays Google sign-in, issues a local tenant-scoped session after a verified active lease, and blocks old password/first-run enrollment when `LHM_CLOUD_LICENSE_MODE=required`. Switching Google accounts cannot open the prior customer's local Ads records. Integration tests run in CI, but physical-device sign-in, renewals, eviction, offline and revocation **still require real-cloud acceptance before commercial release**.
- Do not enable required mode until the customer account/seat and Google OAuth settings have passed end-to-end staging QA.

## Known limitations / to verify
- A normal browser PWA cannot have an unforgeable hardware fingerprint. Concurrent sessions are a practical subscription quota, not DRM.
- Offline authenticated access is blocked; product requires periodic Internet access to enforce concurrent seats. The PWA encrypted vault remains stored locally.
- The default local IndexedDB vault created by pre-migration demo releases is not silently assigned to a Google identity; users should export existing encrypted backups before migration.
- Payment is **manual verified** in current Admin; do not promise automatic provisioning, refunds or card collection.
- Old password/customer endpoints still exist for backwards compatibility and require a separate migration/deprecation policy.

## Local database safety during migration
- The Windows Google-only mode stores Ads tokens **on this PC** in SQLite and encrypts secrets with the existing local master key. Each Google customer's data is partitioned by `org_id=google:<verified-cloud-customer-uuid>`; FastAPI checks license customer identity on every authenticated request.
- Legacy data is not silently copied to a new Google account. If an old local admin already uses the same email, the server returns a 409 conflict to protect the existing encrypted accounts until a deliberate, reviewed migration is performed.
- The secure native proof exists only in memory of the packaged WebView2/Windows process, not in the Cloudflare database, license file, query string or GitHub.
- Cloudflare's seat response now includes the verified account UUID/email. Windows rejects mismatched identities even if an apparently valid bearer is present.
