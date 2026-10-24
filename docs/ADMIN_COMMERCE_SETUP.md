# LHM Ads AI — Commercial Admin (Cloudflare Workers)
Status: **code scaffold, NOT live until configured and tested**.

The admin UI is at `https://ads.lhmcrm.com/admin/` after Workers Builds deployment.
All privileged `/api/admin/*` routes reject requests unless (1) Cloudflare Access
sends a signed JWT, (2) the Worker verifies the JWT against the Access team's
JWKS, its audience and expiry, and (3) the email matches `ADMIN_EMAIL`.
Cloudflare Access must ALSO enforce the route on its edge. No payment gateway
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
