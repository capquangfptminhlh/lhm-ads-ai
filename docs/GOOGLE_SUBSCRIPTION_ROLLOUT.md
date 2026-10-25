# Gmail sign-in, Gmail-bound plans and PWA Ads — rollout checklist

Status: **built and tested on the feature branch (PR #46); not deployed to production.**
Production deploy, Google/Meta app settings, bank details and live acceptance are the owner's.
Plan and owner checklist: `docs/KE_HOACH_TONG_THE.md` · Agent brief: `docs/AGENT_BRIEF_GMAIL_LICENSE.md`.

## What customers get

- Sign in with **Gmail** on the PWA (`/local/`) or the Windows app (browser pairing with a 6-digit code). No password, no key.
- Choose a plan → bank transfer with a **VietQR** code and a payment code `LHMxxxxx` → the admin activates it → the app unlocks by itself within ~15 s.
- The plan belongs to the Gmail: sign in with that Gmail on any device, up to the plan's number of devices at once. A device beyond the limit asks before signing the least recently active one out.
- **Hard lock** when the plan expires, is revoked or the account is blocked. Data on the device is kept and opens again after renewal.
- Windows keeps working offline for at most 72 h (signed lease, never past the plan's end).
- The PWA reads Google Ads / Meta directly from the browser: accounts (incl. MCC children), live reports, the same optimization playbook as the PC, and pause with confirmation. Background monitoring, autopilot and MCP remain PC-only.
- Ads tokens, account IDs and reports never reach Cloudflare.

## Cloudflare (owner)

1. **Back up D1**, then apply migrations `0004`, `0005`, `0006` (the deploy workflow runs them):
   GitHub → Actions → *Deploy LHM Ads Commerce* (it also deploys the Worker and verifies Access).
2. Worker **secrets** (`npx wrangler secret put NAME`):
   - `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET` — OAuth client **LHM Login** (Web application), redirect `https://ads.lhmcrm.com/api/auth/google/callback`.
   - `LEASE_SIGNING_KEY` — from `python tools/create_lease_keys.py` (private half).
3. Worker **variables** (not secret):
   - `BANK_BIN` (6-digit VietQR bank BIN), `BANK_ACCOUNT_NO`, `BANK_ACCOUNT_NAME` — shown with the QR. Without them customers see "Quản trị viên sẽ gửi số tài khoản".
   - `GOOGLE_ADS_WEB_CLIENT_ID` — OAuth client **LHM Ads PWA** (Web application), JavaScript origin `https://ads.lhmcrm.com`, redirect `https://ads.lhmcrm.com/local/oauth/google`, same Cloud project as the PC client.
   - `META_APP_ID`; Meta app: Valid OAuth Redirect URI `https://ads.lhmcrm.com/local/oauth/meta`, Client and Web OAuth Login on.
   - Optional: `META_OAUTH_SCOPES` (default `ads_read`; add `ads_management` only after App Review, needed for pause), `GOOGLE_ADS_API_VERSION` (default `v25`), `META_GRAPH_VERSION` (default `v24.0`), `ORDER_PENDING_HOURS` (48), `LEASE_GRACE_HOURS` (72).
4. The daily cron in `wrangler.toml` cancels unpaid orders after `ORDER_PENDING_HOURS` and cleans expired sessions/seats.
5. Check `https://ads.lhmcrm.com/api/_hosting/status`: `google_login_configured`, `gmail_plans_schema_ready`, `payment_instructions_configured`, `desktop_lease_signing_configured` should all be `true`.

## Windows build (owner)

- Generate the Worker Ed25519 lease signer on the owner's trusted computer with `python tools/create_lease_keys.py`. Store its **PRIVATE** value only as Cloudflare Worker secret `LEASE_SIGNING_KEY`. Do not email or commit it.
- Set GitHub Actions variable `LHM_LEASE_PUBLIC_KEY_B64` to the matching **PUBLIC** value and secret `LHM_COMMERCIAL_PUBLIC_KEY_B64` to the vendor license **PUBLIC** value. Neither is a private signing key.
- Store the same Worker **PUBLIC** base64 value independently on the owner's signing workstation in a file such as `trusted-worker-lease-public.b64`; do **not** derive this trusted copy from `release-manifest.json` or the candidate ZIP. Verify that it corresponds to the production Worker secret.
- Manually trigger **Build and test Windows EXE** with `commercial=true`. This builds **Nuitka only** and fails closed if either public key is missing/invalid. The manifest must say `commercial-candidate`, `nuitka`, `google-only` and list the Worker lease key fingerprint.
- Before customer distribution, run `python tools/release_gate.py inspect-candidate --exe LHM-Ads-AI.exe --checksum LHM-Ads-AI.sha256 --manifest release-manifest.json --vendor-public vendor-public.b64 --lease-public trusted-worker-lease-public.b64` using files from the *same* candidate build. It verifies EXE SHA-256 plus both independently trusted public keys; **it does not approve sale**.
- After all live acceptance evidence and owner approval, an unsigned Windows ZIP can be prepared locally via `tools/package_unsigned_release.py package` (now requires `--lease-public` as well as `--vendor-public`). Customers verifying a package also need `--trusted-lease-public` along with `--trusted-vendor-public`. Optional Authenticode packaging through `windows/package-commercial-release.ps1` also requires `-LeasePublicFile`.
- Staging without a commercial EXE: set `LHM_CLOUD_LICENSE_MODE=required` and `LHM_LEASE_PUBLIC_KEY_B64`. The **pilot** EXE remains pilot-only; a commercial build without a Worker lease public key now **fails** instead of silently falling back to legacy licensing.

## Admin

`/admin/` (Cloudflare Access): **Đơn chờ** (activate by payment code), **Khách hàng** (Gmail search, devices, block, unlink Google, transfer, notes), **Cấp gói theo Gmail** (incl. pilot bulk import), **Sắp hết hạn**, **Bảng giá**, **Nhật ký**.

## Moving pilot customers

1. Collect each pilot customer's Gmail into `gmails.csv` (`customer_ref,gmail`).
2. `python tools/migrate_pilot_to_gmail.py --map gmails.csv --out grants.csv` (preview without `--out`).
3. Admin → Cấp gói theo Gmail → *Nhập danh sách chuyển khách pilot* → paste `grants.csv`.
4. Ship the Gmail-mode EXE; customers sign in with that Gmail. Old offline licenses still work until they expire.

## Automated checks (CI)

- Worker on real SQLite: `tests/worker_gmail_plans.test.mjs`.
- PWA ↔ PC parity, 1,145 cases from the Python code: `tests/core_parity.test.mjs` (+ `tests/test_core_fixtures.py`).
- Windows lease (JS-signed, Python-verified): `tests/test_cloud_lease.py`.
- Browser: `tools/pwa_plans_smoke.py`, `tools/e2e_gmail_flow.py`, `tools/pc_gate_smoke.py`, `tools/pwa_ads_smoke.py`.

## Not verified yet (live acceptance, owner)

Real Google sign-in and consent screen, real bank transfer + activation, real Google Ads / Meta accounts on the PWA (numbers equal to the PC), a signed commercial EXE on clean Windows 10/11, Android Chrome and iPhone Safari installs, seat takeover between a phone and a PC, 72 h offline, revocation. Record results in `docs/ACCEPTANCE.md` §E; keep `NOT_RUN` until done.
