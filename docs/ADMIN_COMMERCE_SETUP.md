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

The helper locates the real account-scoped D1 database named `lhm-ads-commerce`,
verifies its actual UUID, applies migrations against it remotely, and deploys
the Worker with a generated binding. By default it refuses to deploy if D1 is missing. An explicit
`--provision-only --create-db` can create this **one named D1** in the selected
Cloudflare account, after the owner approves. It does not invent credentials. The generated config is temporary, not committed to GitHub.

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


## GitHub Actions deployment — single guarded workflow

Workflow: `.github/workflows/deploy-commerce.yml`, named
**Deploy LHM Ads Commerce (manual, guarded)**. It is never started on push.

Store these **three** values in the GitHub repository's **Actions Secrets**
(do not paste a token, account ID, or private email into chat or source files):

| Secret | Purpose |
|---|---|
| `CLOUDFLARE_API_TOKEN` | Account-scoped token |
| `CLOUDFLARE_ACCOUNT_ID` | 32-character Cloudflare account identifier |
| `LHM_ADMIN_EMAIL` | Intended owner email for Access allowlist |

Cloudflare API token permissions needed: **Workers Scripts Edit**,
**D1 Edit**, **Access Apps and Policies Edit**, and **Zero Trust Organization Read**,
scoped to the chosen Cloudflare account. Relevant rights may be named slightly
differently in the Cloudflare dashboard. Workers routing in a custom domain
may also require zone-level route permissions. Do not use a Global API Key.

Ensure a Cloudflare Zero Trust organization and an authentication method
(such as an approved IdP or One-time PIN) are already configured.

Launch GitHub → **Actions** → **Deploy LHM Ads Commerce (manual, guarded)**
→ **Run workflow** on `main`. The workflow has **two explicit opt-in switches**:

1. **Create missing D1:** create `lhm-ads-commerce` only if absent.
   By default, require it to exist already.
2. **Create missing Access app:** create `LHM Ads AI Admin` with precisely
   these protected public destinations within one Access audience:
   `ads.lhmcrm.com/admin`, `ads.lhmcrm.com/admin/*`,
   `ads.lhmcrm.com/api/admin/*`.
   The new policy permits only `LHM_ADMIN_EMAIL`. If an overlapping
   application already exists, refuse rather than modify an unknown app.

The workflow then:

1. Runs local tests and validates Cloudflare credentials.
2. Finds or explicitly provisions the named D1.
3. **Persists the verified, non-secret D1 UUID in `wrangler.toml`** and
   commits the change to `main` so normal Cloudflare Workers Builds deploys
   cannot silently remove `COMMERCE_DB` on the next commit. The GitHub
   workflow requires **Actions → General → Workflow permissions →
   Read and write permissions** for its restricted `contents: write` scope,
   or a repository policy that authorizes this exact push. If a protected
   branch rejects the commit, the workflow fails safely.
4. Checks or creates the Access app (only with explicit opt-in).
5. Verifies **actual Cloudflare Access policy** by reading the application's
   policy list and policy detail. Exactly one Allow policy for the configured
   owner email is accepted; wildcard accounts, Bypass, overlapping apps, and
   extra policies block deployment instead of silently widening admin access.
   Runs remote D1 migrations and deploys the Worker using the verified D1.
6. Writes `CF_ACCESS_TEAM_DOMAIN`, `CF_ACCESS_AUD`, and `ADMIN_EMAIL`
   as Cloudflare Worker secrets. It always uses a Wrangler configuration
   containing the matching D1 binding during these secret writes.
7. Performs a **read-only HTTPS production smoke check** requiring D1 schema
   and Access configuration to be present and anonymous Admin routes denied.

The script deliberately **never** creates the Zero Trust organization,
changes existing/overlapping Access policies, collects payment credentials,
or simulates actual bank payments. Authentication and the owner's email must
be reviewed in Cloudflare Zero Trust. If the app supports MFA through the
chosen identity provider, enforce it there.

Important: As of the last observed production check,
`commerce_binding_present=false` and `commerce_access_configured=false`.
Adding GitHub Secrets alone does not run this manual workflow. A green local
test does not replace an authenticated browser test of Admin after rollout.

### Repeat deployments

The real D1 UUID is now part of source configuration after successful
bootstrap, so both Cloudflare Workers Builds and the explicit GitHub deployment
use the same binding. `keep_vars = true` preserves Worker runtime secrets
in dashboard-based deploys. **Do not edit the D1 UUID by hand** or silently
replace the bound database.

Before commercial release, perform real authenticated Admin tests for
customer creation, pending order, bank reference review, payment approval,
license issue, renewal and revocation, including negative tests for unauthorized
users. Account/customer credentials and advertising access are distinct systems.
