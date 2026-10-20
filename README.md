# Desktop local-only mode (EXE, không VPS)

Khi dùng bản EXE Windows, ứng dụng chỉ chạy trên máy cá nhân và không cần VPS. Hướng dẫn: [docs/LOCAL_DESKTOP.md](docs/LOCAL_DESKTOP.md). Google OAuth Desktop hỗ trợ localhost; Meta localhost phụ thuộc chế độ App và có thể không chạy với Meta Live. Không có MCP.

# LHM Ads AI — Private Studio 0.3

Vietnamese advertising dashboard for an owner-managed VPS. **No MCP server, API keys, remote tool bridge or external AI model connection.** Data analysis is calculated locally from fetched provider reports, not sent to a third-party AI service. Supported upstream Meta and Google Ads APIs are separate from external remote-control integration.

## Included

- Admin/operator/reader logins using server-side sessions and CSRF protection; multi-tenant isolation.
- Encrypted Meta and Google advertising credentials stored in the existing SQLite volume.
- Read-only analytics dashboard, CSV export, labeled demonstration data, local Vietnamese report summarizer.
- Meta campaign pause as a requested action that only an authenticated browser admin can approve.
- Team management, account revocation, password change and audit log.
- No classic UI, no external automation endpoints, no third-party tool-access keys.

## Upgrade notice — mandatory

Upgrading an existing v0.2 database deletes the old `api_keys` table on app startup, thus **all old MCP keys become invalid**. Removed: `/mcp`, `/api/mcp/call`, `/api/keys`, stdio gateway, external-LLM report sharing, legacy dashboard. Deployment MUST be rebuilt and restarted on the active VPS for this to take effect. A GitHub code change alone does not disable a running old container. Check all public proxies for stale upstream routes and redeploy. Existing provider API tokens and existing browser sessions are not deleted by this change.

Before updating an existing installation, back up the encrypted SQLite database and `MASTER_KEY`. Do not regenerate `MASTER_KEY` or the existing Meta/Google credentials will become unreadable. Changing or losing it cannot decrypt saved credentials.

## Setup on a new server

1. `./setup.sh` creates `.env` with unique server secrets; do not commit `.env`.
2. `docker compose up -d --build`
3. `docker compose exec ads-ai python -m ads_core.cli create-admin --email you@example.com`
4. Access `/studio` through HTTPS reverse proxy with appropriate IP policies, per-IP rate limits, backups, 2FA at reverse proxy where possible. Docker Compose binds the application to localhost by default.
5. Test with a Demo account, then connect provider-API accounts using official access credentials.

## Provider coverage

| Platform | Reporting | Mutating |
|---|---|---|
| Demo | Labeled simulation | No |
| Meta Ads | Graph API (authorized token) | Pause with admin approval |
| Google Ads | Read-only adapter, requires OAuth and developer token, **not live-validated** | No |
| TikTok Ads | Not implemented (501) | No |
| OpenAI Ads | Not implemented (501) | No |

Google Ads `token` input requires JSON with keys `client_id`, `client_secret`, `refresh_token`, and optional `login_customer_id`; set `GOOGLE_ADS_DEVELOPER_TOKEN` on the server. Meta account IDs must be numbers or `act_` plus numbers.

## Security and limitations

This is still a pilot, not security-certified SaaS. Local analysis is deterministic/rule-based, **not a cloud LLM chat**. To avoid leaking reports, no OpenAI API key or other remote assistant is used. Advertising data still transits the official provider APIs for reporting and is visible to authorized users of the web dashboard; the Telegram notification integration remains optional and only sends pause confirmations when explicitly configured. No MCP does not mean all other security risks are solved. Before production: independent security review, stronger rate limiting, admin MFA, secret handling, least privilege, backup and recovery tests, and permission checks.

Test: `pip install -r requirements.txt pytest && python -m pytest -q`; frontend syntax: `node --check static/studio.js`.

See [security and upgrade notes](docs/STUDIO.md).

## 1-click OAuth: Google Ads / Meta Ads

A login-and-select-account OAuth flow is now implemented using server-side Google Ads and Meta credentials. The Google developer token and both providers' app client ID/secret must be configured on the server. Nothing has been pre-authorized with customer accounts. Authenticated admin only, state+session bound, expiring encrypted tokens, PKCE for Google. No MCP endpoint. See [docs/OAUTH_CONNECT.md](docs/OAUTH_CONNECT.md) for setup and callback URL registration. Production requires HTTPS and approved API permissions. For Windows local testing the EXE uses its configured loopback origin; Meta may require an HTTPS callback depending on app settings.
