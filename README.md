# LHM Ads AI — Private Studio 0.4 (outbound MCP pilot)

Private Vietnamese advertising dashboard designed for your VPS. The public/inbound MCP server, API key issuance and third-party remote control remain disabled. Studio 0.4 adds an **outbound, allowlisted MCP client** for Google Ads and Meta Ads, plus local daily read-only reports and campaign-plan draft scheduling. This is not a full autonomous AI campaign builder.

## Available features

- Browser-session login (admin/operator/reader), CSRF, audit logs, tenant isolation.
- Encrypted official Meta/Google advertising credentials. Daily reporting dashboard, CSV exports, and clearly labeled demo data.
- Internal report assistant: on-server, deterministic summaries. Does not send reports, client labels, or conversations to external AI models.
- Meta pause requests with explicit administrator approval via logged-in browser.
- Team management and password changes.
- /automation: add an allowlisted HTTPS MCP endpoint and Bearer token; token is encrypted and never shown again.
- Admin can test MCP handshake, list available tools, approve read-only tool names in VPS config and schedule daily reports or draft campaign plans.
- Scheduler runs daily at Asia/Ho_Chi_Minh local time and stores output for human review. It never creates live campaigns or changes budgets.
- Optionally set `LOCAL_AI_CHAT_URL` to a private OpenAI-compatible `/v1/chat/completions` endpoint, `LOCAL_AI_MODEL` and if needed `LOCAL_AI_KEY` to generate actual draft plans/analyses. Without them the assistant is only rules-based. Never point local AI to a public endpoint without a separate security/privacy review.

## Upgrade from 0.2

The next application startup **drops the legacy api_keys table**, revoking old third-party tool keys. Removed routes: /mcp, /api/mcp/call, /api/keys, /classic, and the old classic UI. These routes should return 404. Back up your database and existing MASTER_KEY first. Keep the same MASTER_KEY or existing encrypted provider credentials cannot be decrypted.

**Updating GitHub does not stop an older container running on your VPS.** Rebuild and restart the real deployed container and remove old public reverse-proxy routes before considering those connections disabled. Historical Git commits can still contain old implementation code; never commit credentials.

## Outbound MCP security and automation

1. In server `.env`, set `MCP_ALLOWED_HOSTS` to a comma-separated list of exact trusted MCP server domain names (no scheme, wildcards or ports); blank means connections are blocked by default.
2. Configure `MCP_READ_TOOLS_GOOGLE` and `MCP_READ_TOOLS_META` to exact *read-only* tool names. Review the provider's MCP tool implementations, not just its descriptions, before enabling them.
3. Rebuild/restart the running service, log in as admin and visit `/automation`. Paste the trusted server HTTPS endpoint and Bearer token **only into this page** (never into GitHub or chat). Click Check to verify the handshake and discover tools.
4. Schedule daily MCP reports using an allowlisted read tool or create a campaign-plan outline. Outputs remain drafts and do not cause API writes/spend.
5. For production use, restrict egress with network firewall/DNS-pinning or a trusted proxy; allowlist alone plus a DNS check is not a complete SSRF defense. Turn on HTTPS, MFA, rate limits and backups. The scheduler expects one running instance and has no production-grade distributed queue.

Note: An MCP Bearer token is *not* a universal Google/Meta token. The remote MCP server must already be authorized with the required advertising accounts. This app has no exposed `/mcp` endpoint, and tools returned from MCP are always untrusted. The prior internal assistant remains rules-based; actual model-driven content generation, autonomous campaign creation and native ad scheduling are **not** implemented in this release. Live operations will require separate permission-specific connectors and human approval.

## Setup

1. For new installs, run ./setup.sh. Preserve .env for upgrades.
2. Run docker compose up -d --build.
3. Create an admin with docker compose exec ads-ai python -m ads_core.cli create-admin --email you@example.com.
4. Serve /studio behind HTTPS and a reverse proxy; add rate limiting, access controls/VPN, backup/recovery and MFA.
5. Test with the Demo account first. Obtain official Meta and Google Ads API permissions before using live accounts.

The legacy direct Google Ads read-only adapter still accepts OAuth credential JSON. Its optional developer-token header check is outdated: Google sunset developer tokens on 2026-09-09, and access levels now attach to the OAuth Cloud project. Update the direct adapter before connecting production Google Ads accounts. Outbound MCP mode does not depend on this legacy field.

## Status and limitations

- Meta: reports and browser-admin-approved pause through official Graph API.
- Google Ads: read-only adapter, not validated with a live customer account.
- TikTok / OpenAI Ads: live integration not implemented; returns 501.
- Only browser users can access these application APIs; no bearer API key authentication.
- This is a pilot, not a security-certified service. Security review, production MFA, rate limiting and backup tests are required.
- Optional Telegram pause notifications still send a brief event to the configured Telegram chat.
- Actual Meta/Google Ads reporting still requires outbound communication to those official providers.

Testing: pip install -r requirements.txt pytest && python -m pytest -q
