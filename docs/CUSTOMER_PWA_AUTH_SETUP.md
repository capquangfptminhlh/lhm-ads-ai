# Customer PWA login: deployment and recovery

The customer PWA uses email + password, not Cloudflare Access seats. Cloudflare Access remains strictly for Admin. Customer auth is separated from local device vault; Ads credentials and Ads reports never enter D1.

## Production migration

The existing database is **lhm-ads-commerce**, binding name **COMMERCE_DB**. After 0001 and 0002 (six tables) run `migrations/0003_customer_auth.sql` ONCE via D1 Console or the guarded Wrangler deploy workflow. It creates `customer_auth` and `customer_sessions`. Do not create a new database or overwrite existing records.

**Danger: automatic deployments currently use `wrangler.toml` without a persisted `[[d1_databases]]` binding.** A deployment can remove the Worker binding (even though the D1 data remain). A current production status of `commerce_binding_present:false` means the Worker is disconnected, not that the tables were deleted.

To fix permanently: obtain the real D1 Database ID (UUID) from Cloudflare D1 > lhm-ads-commerce > Settings; add `[[d1_databases]]` with `binding = "COMMERCE_DB"`, `database_name = "lhm-ads-commerce"`, `database_id = "<real UUID>"`, and `migrations_dir = "migrations"` to the Worker deployment config. Never fabricate the UUID. The existing `tools/deploy_commerce.py` may instead discover the ID and deploy using a generated config; configure the Cloudflare build/deploy command to use it rather than a plain `wrangler deploy`.

After deploying check `/api/_hosting/status`: `commerce_binding_present:true`, `commerce_schema_ready:true`, `customer_auth_schema_ready:true`. The first is currently NOT true after a plain auto-deploy; do not invite customers until fixed.

## Customer journey

Admin creates a customer, paid order and issues a license key through the existing Admin API (Access protected). In PWA, customer selects **Kích hoạt lần đầu**, provides the matching customer email, the issued license key, and chooses a password >= 12 characters. Activation is one-time. Then sign in, verify an active license and unlock the separate encrypted local vault. The API only sends an HttpOnly, Secure, SameSite=Strict 7-day cookie; D1 stores only its SHA-256 hash. Passwords use PBKDF2-SHA256 with 210000 iterations and random salt. Five bad attempts lock sign-in for 15 minutes.

## Boundaries and production criteria

- Customer auth does not grant Admin capabilities or Cloudflare Access. The Admin Access configuration is still needed for Admin UI.
- PWA UI sign-in is a client-side gate, **not server-side protection for public static JS/HTML**. Every future paid Ads/API endpoint must independently require an authenticated, active subscriber on the Worker.
- This is an initial implementation: test real devices, 100-client load, provisioning, subscription revocation, password reset using verified email, rate limits, session pruning and recovery before inviting paying customers.
- There is no cloud storage/sync of advertising data. Ads credentials and private reports remain encrypted on the device. Do not pretend the ad platform API integrations are live.
