# LHM Ads AI — Campaign Advice 24/7 (local-only)

New account-level read-only recommendation engine. Scans Google/Meta campaigns on the locally installed Windows machine using official API credentials. **No MCP and no inbound ports.**

## Behavior
- Optional Windows agent, requires a valid signed license and monitoring enabled per org.
- Background reads aggregate campaign performance once per day per account; provider errors retry no more often than hourly. Explicit admin scan has a one-hour interval.
- Candidate findings: extremely low CTR with >=100 clicks and >=1,000 impressions; Google campaign with >=100 clicks but no reported conversions. These are **signals for review only**, not proof the campaign should be paused or budget reduced. Meta conversions are not yet normalized.
- Last agent heartbeat stored locally; UI indicates whether seen in the last two minutes. If PC is sleeping, off or offline, no monitoring can occur.
- Findings deduplicated by account/campaign/rule, saved in local SQLite. No account names, token contents or IDs are sent to OpenRouter by this engine.
- Read-only API GET status, admin-protected POST scan and acknowledge. No provider write API is reachable through this module.

## Limits
- This is a deterministic advisory rule engine, not automatic bidding and not an LLM. AI interpretation remains separately opt-in via OpenRouter.
- Campaign API reads are subject to provider rate limits, access scopes, business policies and conversion tracking accuracy.
- For actual mutations, use existing human-reviewed Autopilot plan endpoint with prior permission and policy checks, not findings.
- Manual verification with authorized Google and Meta test accounts remains required before selling a 24/7 optimization claim.

## Local validation
```bash
python -m pytest -q
node --check static/advisor.js
```
