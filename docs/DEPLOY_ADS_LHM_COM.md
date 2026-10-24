# Production domain: https://ads.lhmcrm.com

This file configures the LHM Ads AI PWA/API deployment endpoint and Google/Meta OAuth callback origin.
Adding these files to GitHub **does not** change DNS, deploy a VPS, approve Google/Meta APIs, generate a TLS certificate, or make the application live.

## Requirements

- Control of the **lhmcrm.com** DNS zone and a Linux VPS with Docker Engine + Compose plugin.
- A public IPv4 address (and optional IPv6) for that VPS; no other application using host TCP 80 or TCP/UDP 443.
- Firewall allows inbound TCP 80/443 and, optionally, UDP 443; SSH remains access-controlled.
- Do not commit `.env`, `/secrets/`, Google/Meta OAuth secrets, VAPID private keys, or vendor licensing keys.

## DNS

Create **A** record: **Name:** `ads`; **Value:** the actual VPS public IPv4 (do not use an example IP).
Add an **AAAA** record only if the VPS has working public IPv6. If using Cloudflare, use **DNS only** while initially obtaining HTTPS; if later enabling the Cloudflare proxy, set SSL mode to **Full (strict)** and recheck application cookies/OAuth. Wait for propagation, then verify that `ads.lhmcrm.com` resolves to your intended host.

Do not repoint unrelated records for `lhmcrm.com` or `www.lhmcrm.com`.

## Fresh deployment

1. On the intended VPS, clone the reviewed/merged repository and run `./setup.sh` once. It creates random server-side `MASTER_KEY` / `SESSION_SECRET`. **Never overwrite a production .env or regenerate MASTER_KEY**, because existing encrypted Ads credentials would become unreadable.
2. Configure `PUBLIC_BASE_URL=https://ads.lhmcrm.com` and `COOKIE_SECURE=true` in `.env`. The production overlay enforces these two values for the `ads-ai` service even if older .env files differ.
3. Register server Web OAuth callback URLs with your own Google/Meta applications:
   - **Google (Web application OAuth client)**: `https://ads.lhmcrm.com/api/oauth/google/callback`. Server-side web OAuth uses the GOOGLE_OAUTH_CLIENT_ID / GOOGLE_OAUTH_CLIENT_SECRET environment settings, not a local Windows Desktop client callback. Ensure the OAuth consent screen and Google Ads API project access are approved for actual users.
   - **Meta (Facebook Login)**: `https://ads.lhmcrm.com/api/oauth/meta/callback`. Configure META_APP_ID / META_APP_SECRET, `ads_read`, and obtain the necessary Meta permissions/App Review for external users.
4. For optional Web Push, generate VAPID key material **outside Git** with `python tools/create_vapid_keys.py --private-file secrets/vapid.pem`. Set `LHM_VAPID_PUBLIC_KEY` and `LHM_VAPID_SUBJECT` (a real contact email in `mailto:` format). The compose stack mounts `secrets/vapid.pem` as `/run/secrets/lhm/vapid.pem`; keep `LHM_VAPID_PRIVATE_KEY_FILE=/run/secrets/lhm/vapid.pem`. Ensure the private key is readable by the app's unprivileged UID 10001, without making the directory or contents public.
5. Start HTTPS reverse proxy, Ads API, and background monitor together:
   ```bash
   docker compose -f docker-compose.yml -f compose.ads-lhm-com.yml up -d --build
   docker compose -f docker-compose.yml -f compose.ads-lhm-com.yml ps
   ```
   Caddy obtains and renews TLS certificates when DNS and inbound ports work. Do not publish backend port 8080 to the Internet; base compose binds it to loopback.
6. On a new database, use the documented CLI setup to create the first administrator and configure MFA. Log in at `https://ads.lhmcrm.com/studio`.
7. In the UI, connect authorized Google/Meta test accounts and verify genuinely live reports. Set the monitoring schedule and budget threshold (e.g. 200,000 VND/day). Enable Web Push on a **supported, installed** Android/iPhone PWA and use the test notification button. Verify device behavior while screen is locked, with HTTPS and Internet available.

## Acceptance checks

- `https://ads.lhmcrm.com/healthz` returns `ok: true` and a server version.
- `https://ads.lhmcrm.com/manifest.webmanifest` and `https://ads.lhmcrm.com/sw.js` return 200 under trusted TLS; `/studio` loads and login works.
- Protected `/api/...` routes return 401 when signed out; user sessions set Secure/HttpOnly cookies.
- The two exact callback URLs above appear in `/api/oauth/status` **after** an authorized admin signs in; Meta/Google provider authorization still requires review and explicit OAuth consent.
- `docker compose ... ps` shows **ads-ai, ads-monitor, reverse-proxy**. Test a real account's budget-alert cycle. Results may lag API reporting; no guarantee of instantaneous notification.
- Mobile PWA/service-worker cache never stores credentials or Ads reports.
- No public HTTP MCP is provided. Local stdio MCP requires authorized, time-limited keys and access to the same trusted machine/database.
- Check backup/restore, MFA, account separation, API permissions, expiry/revocation, rate limits, push delivery, and security headers before commercial launch.

## Architecture constraints

The existing web backend still stores provider OAuth credentials encrypted in its server database. Therefore this deployment is **not** a customer-device-only credential architecture. Background monitoring while all customer devices are switched off cannot simultaneously rely solely on tokens stored on those switched-off devices. A separate consent/custody architecture decision and implementation are required before advertising device-only storage.
