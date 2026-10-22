# Studio 0.3 — Internal-only upgrade

> Version source of truth: `ads_core/version.py` (`__version__ = "0.3.0"`; "0.3" above is its short display form).

All external MCP/remote tool connections have been removed, including routes /mcp and /api/mcp/call, key issuance APIs /api/keys, the stdio executable, and UI. No outside assistant receives report data: the assistant uses local rule-based analysis even when an old OPENAI_API_KEY remains in your environment.

Legacy key hashes are deleted on next startup (DROP TABLE IF EXISTS api_keys). Old bearer credentials cannot authenticate.

## Upgrade

1. Securely back up SQLite database and the existing MASTER_KEY. Keep MASTER_KEY unchanged.
2. Update the existing VPS checkout and rebuild and restart with docker compose up -d --build.
3. Confirm GET/POST /mcp, POST /api/mcp/call, and GET/POST /api/keys all return 404.
4. Confirm access requires a browser login and write requests require a matching CSRF token.
5. Remove stale reverse-proxy routes, old client settings, firewall openings and cached copies. Rotate leaked credentials.
6. Restrict production access with HTTPS, WAF/rate limits, MFA or VPN, proper monitoring and encrypted backups.

A repository update alone does not reconfigure an already-running VPS. The old code remains active until deployment. Provider connections still use their official remote APIs and encrypted server-side credentials.
