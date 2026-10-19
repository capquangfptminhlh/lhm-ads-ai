# LHM Ads AI — Private Studio 0.3

Private Vietnamese advertising dashboard, designed to run on your own VPS. External MCP tools, remote bridge, API key issuance, and outgoing LLM analysis have been removed.

## Available features

- Browser-session login (admin/operator/reader), CSRF, audit logs, tenant isolation.
- Encrypted official Meta/Google advertising credentials. Daily reporting dashboard, CSV exports, and clearly labeled demo data.
- Internal report assistant: on-server, deterministic summaries. Does not send reports, client labels, or conversations to external AI models.
- Meta pause requests with explicit administrator approval via logged-in browser.
- Team management and password changes.

## Upgrade from 0.2

The next application startup **drops the legacy api_keys table**, revoking old third-party tool keys. Removed routes: /mcp, /api/mcp/call, /api/keys, /classic, and the old classic UI. These routes should return 404. Back up your database and existing MASTER_KEY first. Keep the same MASTER_KEY or existing encrypted provider credentials cannot be decrypted.

**Updating GitHub does not stop an older container running on your VPS.** Rebuild and restart the real deployed container and remove old public reverse-proxy routes before considering those connections disabled. Historical Git commits can still contain old implementation code; never commit credentials.

## Setup

1. For new installs, run ./setup.sh. Preserve .env for upgrades.
2. Run docker compose up -d --build.
3. Create an admin with docker compose exec ads-ai python -m ads_core.cli create-admin --email you@example.com.
4. Serve /studio behind HTTPS and a reverse proxy; add rate limiting, access controls/VPN, backup/recovery and MFA.
5. Test with the Demo account first. Obtain official Meta and Google Ads API permissions before using live accounts.

Google Ads credential input is JSON containing client_id, client_secret, refresh_token and optional login_customer_id. A GOOGLE_ADS_DEVELOPER_TOKEN setting is also required.

## Status and limitations

- Meta: reports and browser-admin-approved pause through official Graph API.
- Google Ads: read-only adapter, not validated with a live customer account.
- TikTok / OpenAI Ads: live integration not implemented; returns 501.
- Only browser users can access these application APIs; no bearer API key authentication.
- This is a pilot, not a security-certified service. Security review, production MFA, rate limiting and backup tests are required.
- Optional Telegram pause notifications still send a brief event to the configured Telegram chat.
- Actual Meta/Google Ads reporting still requires outbound communication to those official providers.

Testing: pip install -r requirements.txt pytest && python -m pytest -q
