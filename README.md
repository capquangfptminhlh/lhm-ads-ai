# LHM Ads AI — Private Warm Studio 0.5

A private, Vietnamese advertising dashboard with a responsive black/cream/orange UI inspired by the user's dashboard reference.

## Current features
- Self-hosted FastAPI web app, responsive dashboard and mobile sidebar.
- Multi-account Meta and Google Ads reporting (requires valid official provider API credentials), with clearly labeled demo data.
- Internal rule-based assistant, CSV exports, approval workflow for Meta pause requests.
- Team roles, browser login sessions, CSRF protections, encrypted official provider tokens and audit log.
- Global account search filters the actual loaded account table. No fake Ads reporting in production.
- **No inbound or outbound MCP connections, no remote-control API keys, and no external AI report sharing.** Official advertising providers are contacted only for approved advertising API functionality.

## Security and upgrades
On startup, the app removes any legacy `api_keys`, `mcp_connections`, `agent_jobs`, and `agent_outputs` tables from previous pilots. **Back up your SQLite database before deployment:** removal deletes old MCP connection credentials and scheduled output records. Other advertising accounts and user tables remain.
The new code takes effect on the VPS only after updating/rebuilding/restarting the running container. Check reverse-proxy paths, rotate any credentials previously exposed and turn off any retired MCP service outside this application.

Production use still requires HTTPS, proper rate limiting, MFA, backup/restore verification and an independent security review. The Meta/Google integrations require real OAuth/API tokens, which are not shipped in this repository. TikTok and OpenAI Ads live adapters are not implemented.

## Local development
```bash
cp .env.example .env
# Set secure MASTER_KEY and SESSION_SECRET in .env
docker compose up -d --build
```

See [docs/STUDIO.md](docs/STUDIO.md) for migration notes. Run tests with:
```bash
pip install -r requirements.txt pytest
python -m pytest -q
node --check static/studio.js
```
