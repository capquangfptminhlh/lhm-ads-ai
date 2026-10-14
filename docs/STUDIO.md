# LHM Ads AI Studio v0.2 — deployment and usage

## Functional features added

- Modern responsive Vietnamese dashboard at `/studio` (root `/` redirects to it); original interface at `/classic`.
- Chat at `/api/assistant/chat`: uses live reports and never performs mutations. With `OPENAI_API_KEY`, requests an AI explanation. Without it, deterministic rule-based analysis of the SAME report data is returned and clearly labeled. No model gets provider access tokens.
- Team management: admins create admin/operator/reader accounts with a one-time random temporary password, disable users and revoke their sessions and API keys. Staff should change their password immediately after first login.
- Admin may revoke MCP API keys in dashboard; all users may rotate passwords, which logs out all sessions and removes owned keys.
- CSV daily report export, with formula escaping for spreadsheet safety.
- Stateless MCP Streamable HTTP endpoint `/mcp` using JSON-RPC 2.0, bearer API keys and 2025-11-25 handshake. Supports `initialize`, `ping`, `tools/list`, `tools/call`, and notifications. GET/SSE not supported (405). This is **not** an OAuth 2.1 authorization server. Browsers with an unapproved Origin are denied; set `MCP_ALLOWED_ORIGINS` to exact trusted origins if required. Non-browser clients normally omit Origin.
- Read and operator tools: `list_accounts`, `get_insights`, `list_actions`, `request_pause_campaign`. No remote approval tool exists; browser admin must approve each Meta pause.

## Start

The Dockerfile now starts `uvicorn ads_mcp.extended:app` rather than `ads_mcp.app:app`. The new module layers these routes onto the original database and providers; no migration is necessary.

1. Run `./setup.sh` to create a fresh `.env` with strong unique secrets. **Never commit it.** Existing `.env` and encrypted token data MUST retain their original `MASTER_KEY` when upgrading, or tokens become unreadable.
2. Set `COOKIE_SECURE=true`, then build: `docker compose up -d --build`.
3. Create the first user: `docker compose exec ads-ai python -m ads_mcp.cli create-admin --email you@example.com`.
4. Configure an HTTPS reverse proxy with access restrictions, rate limits, security headers, and backup/restore for volume + master key before putting this online. No public ports are exposed by Compose by default.
5. Open `https://YOUR_DOMAIN/studio`; add a demo account first. For live connections, obtain the right provider APIs and approvals.
6. Optional: set `OPENAI_API_KEY` and `OPENAI_CHAT_MODEL=gpt-4.1-mini` in `.env` for LLM-generated answers grounded in reporting data. The model only receives account labels and aggregate metrics. Note: labels and metrics will be transmitted to OpenAI when the key is configured; do not enable without consent/privacy review. The assistant may generate errors and must not be used to execute automated changes.
7. Optional: set `MCP_ALLOWED_ORIGINS=https://trusted-client.example` only if a browser MCP client needs to send an Origin header. MCP URL for a remote client: `https://YOUR_DOMAIN/mcp`. Bearer API key can be created in UI. Do not put tokens in query strings.

## Security limitations

This is a deployable pilot, **not** a production-certified multi-tenant advertising SaaS. Before customers use it, complete independent security testing, 2FA/TOTP or passkeys, secure user onboarding/invites, strict scopes and delegated OAuth, web application firewall/rate-limits, account recovery, backups, monitoring, compliance and provider app approvals. Internal API keys are not OAuth credentials. Temporary passwords should not be reused. `POST /api/login` has only in-process rate limiting in the starter; put a proxy rate limit in front.

## Provider coverage

| Provider | Reports | Pause campaigns | Important |
|---|---|---|---|
| Demo | Mock data (clearly labeled) | No | For testing only |
| Meta Ads | Graph API (requires token and ads_read) | Request + browser admin approval + ads_management | Confirm API version, permissions and real-account behavior |
| Google Ads | Read-only v25 API adapter | No | Requires OAuth developer token; not validated against your real Google account |
| TikTok Ads | Not implemented (returns 501) | No | Official Business API access required |
| OpenAI Ads | Not implemented (returns 501) | No | Pending official API scope/access |

To run tests locally: `pip install -r requirements.txt pytest && python -m pytest -q` and `node --check static/studio.js`.
