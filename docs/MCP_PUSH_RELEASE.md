# LHM Ads AI — MCP read-only + Mobile Web Push (24/10/2026)

**Security architecture superseded for cloud deployments:** all Ads account data and OAuth tokens are required to stay on customer devices. The server-side monitor/Cloudflare Cron scheme described below **must not be deployed with customer Ads credentials**. Cloud control-plane push remains unable to discover new Ads budget overruns while devices are offline. See [DEVICE_ONLY_ADS_DATA.md](DEVICE_ONLY_ADS_DATA.md). Existing Linux server functionality below documents legacy capabilities, not the approved cloud model.


## What works in source code

- Local MCP stdio JSON-RPC 2.0 (2025-06-18) exposes `lhm_accounts`, `lhm_report`, `lhm_alerts` (read-only). It authenticates via a browser-admin-issued 1–30 day revocable key; every tool call checks its tenant/user identity. No credentials or external Ads customer IDs returned by these tools.
- Admin: **Cài đặt → MCP → Tạo khóa** (shown once). Configure an MCP client **running on the SAME trusted computer/backend** with `command=python`, `args=["-m","ads_core.mcp_stdio"]`, env `LHM_MCP_ACCESS_TOKEN=...` and the **same private DB_PATH/MASTER_KEY** as LHM. Install Python requirements and make `ads_core` importable. Treat MCP client process as having access to private metrics.
- **No public HTTP MCP endpoint** and no remote agent-control API. A ChatGPT-cloud hosted connector is not automatically connected to a user's local stdio process. Google/Meta API authorization must be configured separately; OAuth is not bypassed by MCP.
- In **Cài đặt → Cảnh báo ngân sách**, set each connected account's threshold in its own currency. The independent monitoring agent checks the provider's TODAY report only for enabled rules. After the first measured exceedance per account/day, writes an alert and attempts Web Push to explicitly opted-in users. **It never adjusts/pause Ads or changes budgets.**

## Deploy requirements

1. Deploy app and monitoring agent on a trusted server with HTTPS. Local Windows desktop can run an agent **only while powered on and logged into Windows**. The PWA is a client, **not** the background job scheduler.
2. Install `pywebpush` from requirements and generate keys locally: `python tools/create_vapid_keys.py --private-file /secure/keys/lhm-vapid.pem`. Store private key off GitHub with restrictive file permissions.
3. Configure server environment `LHM_VAPID_PRIVATE_KEY_FILE` (absolute key path), `LHM_VAPID_PUBLIC_KEY` (printed public URL-safe key), `LHM_VAPID_SUBJECT=mailto:support@YOUR_DOMAIN`. The worker must have access to the same DB, VAPID key and environment.
4. Ensure authenticated Google/Meta Ads read permission, provider account settings, monitoring license, and background agent enablement. Select a cadence of 15–240 minutes; the alert fires at the next successful fetch **after** the threshold is exceeded, not at the precise VND 200,000 crossing.
5. Install PWA from HTTPS in Chrome Android or Home Screen Safari iOS. On iOS, notifications require a supported iOS version and home-screen web app. Each user must press **Bật thông báo trên thiết bị này** and consent to browser permission.
6. Test with authorized test accounts. Check provider TODAY spend/date/timezone, multiple currencies, revoked/expired user, invalid VAPID, offline, app closed/phone locked, push gone/denied. Confirm no false claim of instantaneous or guaranteed alerts. Verify HTTPS and push via a real device before selling.

## Security boundaries and limitations

- Push subscriptions are encrypted with the backend AES-GCM MASTER_KEY; each user enrolls independently. No Ads OAuth secret or external ad-account ID is sent in notifications.
- Push endpoint hosts are allowlisted (FCM/Mozilla/Apple), protecting the server from arbitrary SSRF URLs. Requests require a browser session and CSRF check.
- Notifications may fail due to expired subscriptions, browser settings or providers, and no automatic retries/queues are implemented yet.
- Authenticated API/backend still stores encrypted customer provider tokens server-side. This **is not** zero-server-credential or phone-only storage. A full key-custody redesign would be needed to promise local-only customer tokens.
- Web Push requires a background worker running **continuously**, not just a page left open. Data on today's spend can lag the platform or be reported in the account's timezone.
- Meta/Google API permissions, external app verification, billing, compliance, commercial licensing and actual Windows/Android/iOS user acceptance still require independent testing.
- TikTok Ads API/MCP adapter is **not** implemented; current third-party providers are Google/Meta reporting only. Do not claim TikTok metrics are live without authorized API and contract.
