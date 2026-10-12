# LHM Ads AI — self-hosted starter (MVP)

An independently developed advertising command center, inspired by the *category* of multi-platform Ads MCP tools. NOT Noti source code or a copy of its proprietary skill. Vietnamese dashboard; no Supabase.

## Implemented

- Admin login, 24h HttpOnly SameSite=Strict cookie sessions, per-request CSRF protection.
- Argon2 password hashes. AES-256-GCM encrypted API access tokens with tenant/account AAD; never returned to browser or AI.
- Multi-user/tenant-aware database schema, roles `admin`, `operator`, `reader`; initial admin provisioned locally by CLI.
- Connect demo, Meta or Google Ads; Meta Insights is implemented against Graph API. Google Ads read-only v25 OAuth-refresh adapter is implemented but not validated with a live customer account.
- Create `pause_campaign` requests. **Only a logged-in browser admin can approve.** Server validates campaign's Meta account before requesting PAUSED. No auto-change of spend or budgets.
- Audit log, revocation of saved credentials, optional Telegram confirmation after successful pause.
- MCP-compatible **stdio tool gateway**: `list_accounts`, `get_insights`, `request_pause_campaign`, `list_actions`. Scope-limited API keys (shown once); no approve tool.
- Distinctly labeled **demo** data. Non-Meta platforms return `501 Not Implemented` for actual report retrieval (no fabricated data).
- Docker Compose, bound by default to localhost only. Responsive UI.

## NOT implemented (do not sell as feature-complete)

- TikTok, OpenAI Ads authenticated reporting/control adapters; Google Ads mutation/OAuth onboarding; Meta bulk operations, campaign creation/duplication, adjusting bids or budgets, OAuth onboarding.
- One-link **remote HTTPS MCP** OAuth 2.1 authorization server, multi-client compatibility validation, proper horizontally distributed rate-limiting.
- Full AI chat/LLM integration, scheduled AI optimization, alerting on spend anomalies, external agency billing, fine-grained resource ACL.
- Production-grade security review, Meta/TikTok/Google API authorization approvals, background job queues, disaster recovery drills and e2e tests against real advertising accounts.

## Local install

Requires Python 3.12+, `pip` and an HTTPS reverse proxy in production.

```bash
cp .env.example .env
python -c "import secrets,base64;print('MASTER_KEY='+base64.b64encode(secrets.token_bytes(32)).decode());print('SESSION_SECRET='+secrets.token_urlsafe(48))"
# Replace MASTER_KEY and SESSION_SECRET values in .env with command output.
# Never commit .env. Back up MASTER_KEY safely; losing it makes stored tokens unreadable.
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
export DB_PATH=./data/lhm-ads.sqlite3
export MASTER_KEY='<from .env>'
export SESSION_SECRET='<from .env>'
export COOKIE_SECURE=false  # only for localhost HTTP DEVELOPMENT
python -m ads_mcp.cli create-admin --email admin@example.com
uvicorn ads_mcp.app:app --host 127.0.0.1 --port 8080
```

Open http://127.0.0.1:8080. Use a local `.env` loader or set variables manually when not running Docker; plain Python doesn't automatically load `.env`.

## Docker on VPS

```bash
cp .env.example .env
# Edit .env: generate both secrets as described above; set COOKIE_SECURE=true
# Never expose port 8080 to public internet.
docker compose up -d --build
docker compose exec ads-ai python -m ads_mcp.cli create-admin --email admin@example.com
```

Place Caddy/Nginx as an HTTPS reverse proxy in front of localhost:8080 (TLS certificate + request rate limiting). Add host firewall, backups of the named Docker volume **and** backed-up master key, and monitor errors. OAuth and API permissions must be obtained via official advertising platforms. Do NOT input social account usernames/passwords.

## Connecting MCP stdio

1. In web UI **Kết nối AI / MCP**, create an API key (reader or operator).
2. On the computer running your stdio-compatible MCP client, install this package's requirements and configure the command `python -m ads_mcp.mcp_stdio` from the project directory.
3. Set `LHM_ADS_URL` to reachable HTTPS backend URL, and `LHM_ADS_API_KEY` to the generated token in the client's secure environment.
4. Browser approval is REQUIRED for every pause command. The AI cannot approve actions.

**Important:** This starter does not expose the MCP endpoint via a single remote URL yet; it uses stdio. Do not enter an HTTP `/api/mcp/call` URL in a client expecting the MCP Streamable HTTP protocol — that endpoint is an internal tool bridge, not a full remote MCP transport.

## Meta authorization

- Meta Business developer app and valid access token with relevant permissions (`ads_read` for reports, `ads_management` for mutations), associated with the target ad account.
- When adding an account, enter numeric ID (`123456789`) or `act_123456789` and the token. `META_GRAPH_VERSION` is configurable. Check current Meta Graph API compatibility before live operation.
- In MVP, Meta Ads has read/one-write integration; Google Ads has read-only connector code (requires actual credentials and testing). Reporting `yesterday` or `last_7d`. Dashboard does **not** invent CPA/ROAS from tracking that is not connected.

## Important controls before public deployment

- Add TOTP or passkey 2FA for admin accounts. **Two-step human approval** in this MVP is NOT 2FA.
- Implement tenant invitations, operator account management, temporary MFA recovery and revocable remote OAuth MCP credentials.
- Harden login rate limiting at reverse proxy/WAF (in-process rate limit is single-worker only), session storage hygiene and organization quotas.
- Add provider credential refresh/OAuth; do not ask customers for their social-platform passwords.
- Use a dedicated private PostgreSQL instance and jobs/queue for scale, with fine-grained permissions, backup rotation, alert monitoring and external penetration test.
- For real Meta mutations, test on a low-risk account and verify API permissions, status and detailed ad policies.

## Google Ads read-only integration (experimental)

Google Ads API needs both [OAuth 2.0 credentials and a developer token](https://developers.google.com/google-ads/api/docs/oauth/overview). Configure `GOOGLE_ADS_DEVELOPER_TOKEN` on VPS. When creating a Google Ads account, use customer ID numbers and enter encrypted credential bundle into the API field in the following **format** (substitute actual secret values; never commit them):

```json
{"client_id":"YOUR_CLIENT_ID.apps.googleusercontent.com","client_secret":"YOUR_CLIENT_SECRET","refresh_token":"YOUR_OAUTH_REFRESH_TOKEN","login_customer_id":"OPTIONAL_MANAGER_CUSTOMER_ID"}
```

Read-only reporting uses Google Ads API `v25` SearchStream with `segments.date`, `metrics.cost_micros`, `metrics.clicks`, `metrics.impressions`. Test with an actual Google Ads developer account before production; the scaffold has only been tested offline.

## Fast Docker bootstrap

Instead of manually editing secrets, run `./setup.sh` to generate `.env` safely. Then run `docker compose up -d --build` and `docker compose exec ads-ai python -m ads_mcp.cli create-admin --email YOUR_EMAIL`. This creates a new locally managed admin account and prompts for a password; no default password is shipped. Change any provider settings in `.env` and restart the container as needed.
