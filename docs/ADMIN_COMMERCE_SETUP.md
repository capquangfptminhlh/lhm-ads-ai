# LHM Ads AI — Commercial Admin (Cloudflare Workers)
Status: **code scaffold, NOT live until configured and tested**.

The admin UI is at `https://ads.lhmcrm.com/admin/` after Workers Builds deployment.
All privileged `/api/admin/*` routes reject requests unless (1) Cloudflare Access
sends a signed JWT, (2) the Worker verifies the JWT against the Access team's
JWKS, its audience and expiry, and (3) the email matches `ADMIN_EMAIL`.
The Worker now also enforces the signed Access JWT before serving `/admin/`, `/admin/index.html`, or any `/api/admin/*` response; unauthenticated requests return HTTP 401. Cloudflare Access must ALSO enforce those routes at its edge. No payment gateway
or bank connection is installed, so approval is **manual**, after verifying
the incoming bank credit outside the app.

## Required Cloudflare setup

1. Create a Cloudflare D1 database named `lhm-ads-commerce`. Get its **real**
   database ID. In `wrangler.toml`, add:

   ```toml
   [[d1_databases]]
   binding = "COMMERCE_DB"
   database_name = "lhm-ads-commerce"
   database_id = "<actual D1 UUID from dashboard>"
   migrations_dir = "migrations"
   ```

   Do **not** paste an example UUID into production.
2. In Cloudflare Workers deploy settings, configure three **non-secret**
   environment variables (do not place personal values in public Git):
   - `CF_ACCESS_TEAM_DOMAIN` = your exact `xxxxx.cloudflareaccess.com` team domain.
   - `CF_ACCESS_AUD` = the application audience tag displayed by Cloudflare Access.
   - `ADMIN_EMAIL` = the sole permitted administrator's actual email.
3. In **Zero Trust → Access → Applications**, create a **Self-hosted** Access
   application protecting both `ads.lhmcrm.com/admin/*` and
   `ads.lhmcrm.com/api/admin/*` (use 2 Access applications if wildcard routes
   cannot be combined; each must use the same AUD only if they share that
   application). Restrict policy to the intended administrator and require MFA.
   If 2 different audience tags are produced, configure a single application
   with multiple domain/path destinations instead of weakening JWT validation.
4. From project root with approved Cloudflare credentials, run:
   `npx wrangler d1 migrations apply lhm-ads-commerce --remote`.
   **Back up production before future schema migrations.**
5. Build and deploy: `python tools/build_github_pages.py --output _site`,
   `npx wrangler deploy`. If automatic Git integration is enabled, deploy
   `main` through the normal Cloudflare Builds pipeline instead.
6. Open `/admin/` using the authorized administrator email. Confirm
   unauthorized access to `/api/admin/overview` returns 401 or Access redirect.
   Test adding a customer, making a pending order, recording a bank reference,
   approving it, issuing a key, renewing from another paid order, revoking,
   and audit entries.

## Business workflow

Customer → pending order → manually check bank statement → record reference →
approve payment → issue license (raw key displayed **once**) → manually send key
to customer → later create and approve a **new** order → extend existing key.

Raw license key is not stored; a SHA-256 hash is stored instead. A separate
license-validation client endpoint and enforcement in customer products must
be built/tested before selling licenses. **Simply generating a key does not
make an app enforce entitlement.** Revocation affects only the control-plane
record until that enforcement exists.

This control plane stores customer contact details and subscription data, but
**never** Ads OAuth tokens, Ads account IDs, or campaign reports. Do not use
it to collect passwords or payment card data. Payment approval is not proof
of settlement unless the administrator has checked their bank records.

### Production hardening before selling
- Add idempotency/transactional renewal and issue operations, concurrency tests,
  audit reconciliation, backup/restore drills, D1 permission review.
- Add customer-facing sign-in, secure license validation and activation rate limits,
  device binding policy, refunds/cancellations, renewal reminders and invoices.
- Add comprehensive role handling rather than `ADMIN_EMAIL` if staff need access.
- Ensure Access path policy actually covers `/api/admin/*` and the UI; do not
  rely solely on frontend visibility.

## Current deployment behavior (2026-10-24)

- The public homepage and device-only PWA are independent of Cloudflare D1.
- The Admin page is no longer a public preview. Before Access is set up, direct
  `/admin/` access returns **HTTP 401** intentionally. It is NOT a customer login.
- Admin API requests authenticate the Access JWT **before** checking D1 binding.
  Unauthorized requests get 401 even if D1 has not been configured.
- The public `/api/_hosting/status` endpoint exposes only non-secret readiness
  booleans. Verify `commerce_binding_present`, `commerce_access_configured`
  and `commerce_schema_ready` are true, but **never** assume this proves
  the edge Access policy itself was tested.

## One-command authenticated D1 rollout

In a trusted command-line/Workers Builds environment authorized to the correct
Cloudflare account:

```bash
python tools/build_github_pages.py --output _site
python tools/deploy_commerce.py --dry-run
python tools/deploy_commerce.py
```

The helper locates **only an existing** D1 database named `lhm-ads-commerce`,
verifies its actual UUID, applies migrations against it remotely, and deploys
the Worker with a generated binding. It refuses to deploy if the D1 database
cannot be found. It does not create a database, set Access policy, or invent
credentials. The generated config is temporary, not committed to GitHub.

Cloudflare Workers Builds may still use a plain `npx wrangler deploy` command;
that default does **not** invoke this helper. For Workers Builds production,
configure the Deploy command to run the helper with a valid D1 setup, or
supply a permanent verified D1 binding in Wrangler configuration. Do not
point multiple Cloudflare accounts at the same domain unintentionally.

## Payment review UX and subscription expiry

Admin list distinguishes **Chờ chuyển khoản** from **Chờ đối soát**.
The Approve button is disabled until a transaction reference exists.
Approving payment remains a human decision **after checking bank statements**;
the UI alone never verifies funds. Subscription list offers a seven-day
expiring-key filter (limited to the most recent 100 licenses returned by API).


## GitHub Actions deployment (manual only)

Workflow: `.github/workflows/deploy-commerce.yml`, labeled
**Deploy LHM Ads Commerce (manual, guarded)**. It never runs on a normal push.
It requires GitHub repository Actions secrets `CLOUDFLARE_API_TOKEN` and
`CLOUDFLARE_ACCOUNT_ID` authorized for the matching Cloudflare account. The
token must be permitted to read D1 databases, apply D1 migrations and deploy
this Worker. Never commit these secrets.

When manually dispatched, the workflow builds and verifies the existing
`lhm-ads-commerce` D1, applies remote migrations, deploys the Worker
with `COMMERCE_DB`, and executes the read-only HTTPS production smoke gate.
It fails early rather than pretending that an unconfigured account is ready.

The Worker configuration uses `keep_vars = true` so Cloudflare Dashboard
runtime variables (`CF_ACCESS_TEAM_DOMAIN`, `CF_ACCESS_AUD`, `ADMIN_EMAIL`)
are preserved when Wrangler redeploys; see Cloudflare documentation for
the source-of-truth rules. This **does not** set these values automatically.

Before treating payments/licenses as production-ready, independently confirm
Cloudflare Access actually protects both `/admin/*` and `/api/admin/*`,
and verify the full manual bank reconciliation and issuance lifecycle.
