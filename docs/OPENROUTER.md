# OpenRouter AI (private, read-only)

- Default: OFF. Only an authenticated admin can set an OpenRouter key, choose a model and enable processing.
- The key stays AES-GCM encrypted locally. Account passwords, provider tokens, account labels/IDs are excluded from the constructed model payload. User-entered text is masked for common token, URL, email and phone/ID formats; **arbitrary names or unique identifiers may remain**.
- Preview: in Trợ lý AI choose "Xem trước dữ liệu gửi đi" to see the exact sanitized question and numeric statistics (no external API call).
- Privacy: requests force OpenRouter `provider.zdr=true` and `provider.data_collection=deny`. A model without qualifying endpoints can fail. ZDR means the provider should not retain prompts, **not** that processing is local. Consult OpenRouter's endpoint-specific privacy policies.
- Quota: max 10 calls per user per 5 minutes in-process and 30 calls per organization UTC day by default (admin may choose 1-200). Daily count persists in SQLite across restarts. All admitted attempts, including failed provider requests, count against quota. This is a **request quota**, NOT a price cap. Set spending/key limits independently on OpenRouter.
- Token counts (when returned) are stored per org/day. Tokens are not a reliable billing amount.
- OpenRouter may charge for AI calls. No model controls advertising, changes budgets, or accesses MCP. The existing human approval for Meta pause actions is unchanged.
- Update Docker/Windows builds to load new backend; restart application. Existing encrypted key and login secrets remain valid if MASTER_KEY is preserved.
- Read-only preview and local fallback can be used with OpenRouter OFF. Do not enter credentials, customer identities, or commercially sensitive raw notes in the AI prompt.
