# LHM Ads AI — GitHub + Cloudflare Workers (không VPS)

> **Gmail và gói theo Gmail (nhánh PR #46, chưa lên production):** khách đăng nhập bằng Gmail trên PWA và bản Windows, mua gói qua VietQR, admin kích hoạt theo mã chuyển khoản; hết hạn là khóa cứng. PWA đọc Google Ads/Meta trực tiếp từ trình duyệt với cùng bộ quy tắc như bản PC. Triển khai: [docs/GOOGLE_SUBSCRIPTION_ROLLOUT.md](docs/GOOGLE_SUBSCRIPTION_ROLLOUT.md) · Kế hoạch: [docs/KE_HOACH_TONG_THE.md](docs/KE_HOACH_TONG_THE.md).

**Yêu cầu bảo mật đã chốt: 100% tài khoản, token và báo cáo quảng cáo nằm trên thiết bị khách, Cloudflare không lưu bản sao.** Không thể sử dụng backend FastAPI trên VPS hoặc Cloudflare OAuth token storage để đáp ứng yêu cầu này; client-side Ads integrations cần thiết kế lại và kiểm thử từng nền tảng. Không hứa PWA giám sát khi thiết bị bị hệ điều hành tạm dừng. Xem [docs/DEVICE_ONLY_ADS_DATA.md](docs/DEVICE_ONLY_ADS_DATA.md).


**Phương án ưu tiên hiện tại:** GitHub lưu mã nguồn và CI, Cloudflare Workers + Static Assets phát hành PWA tại `https://ads.lhmcrm.com` và sẽ xử lý backend khi được chuyển đổi. **GitHub Pages không được dùng làm hosting thương mại cho SaaS**. Bộ build GitHub Pages và Worker an toàn mặc định nằm trong repo; **đăng nhập Google/Meta, giám sát 24/7 và MCP cloud chưa hoạt động trên hosting tĩnh**. Đừng triển khai cho khách thật khi các API còn trả 503.

Xem [hướng dẫn Cloudflare Workers không VPS](docs/DEPLOY_CLOUDFLARE_WORKERS.md). Các hướng dẫn Docker/Caddy bên dưới là phương án hosting backend khác, không phải lựa chọn trước mắt.

# Desktop local-only mode (EXE, không VPS)

Khi dùng bản EXE Windows, ứng dụng chỉ chạy trên máy cá nhân và không cần VPS. Hướng dẫn: [docs/LOCAL_DESKTOP.md](docs/LOCAL_DESKTOP.md). Google OAuth Desktop hỗ trợ localhost; Meta localhost phụ thuộc chế độ App và có thể không chạy với Meta Live. Có tùy chọn MCP stdio chỉ đọc với khóa riêng, không có HTTP MCP công khai; xem docs/MCP_PUSH_RELEASE.md.

# LHM Ads AI — Private Studio 0.3

> Version source of truth: `ads_core/version.py` (`__version__ = "0.3.1"`; "0.3" above is its short display form). Do not hardcode the version elsewhere.

Vietnamese advertising dashboard for an owner-managed VPS. **Read-only local MCP stdio is opt-in via short-lived, revocable keys; no public remote MCP endpoint and no mutation tools.** By default, analysis is calculated locally from fetched provider reports and nothing is sent to a third-party AI service. Optional exception: an admin may explicitly enable OpenRouter AI analysis with their own key (see docs/OPENROUTER.md); only filtered aggregate statistics are sent, never Ads credentials or campaign identifiers. Supported upstream Meta and Google Ads APIs are separate from external remote-control integration.

## Included

- Admin/operator/reader logins using server-side sessions and CSRF protection; multi-tenant isolation.
- Encrypted Meta and Google advertising credentials stored in the existing SQLite volume.
- Read-only analytics dashboard, CSV export, labeled demonstration data, local Vietnamese report summarizer.
- Meta campaign pause as a requested action that only an authenticated browser admin can approve.
- Team management, account revocation, password change and audit log.
- No classic UI or public external automation endpoints; local MCP read-only credentials are opt-in, expiring and revocable.

## Upgrade notice — mandatory

Upgrading an existing v0.2 database deletes the old `api_keys` table on app startup, thus **all old MCP keys become invalid**. Removed: `/mcp`, `/api/mcp/call`, `/api/keys`, stdio gateway, external-LLM report sharing, legacy dashboard. Deployment MUST be rebuilt and restarted on the active VPS for this to take effect. A GitHub code change alone does not disable a running old container. Check all public proxies for stale upstream routes and redeploy. Existing provider API tokens and existing browser sessions are not deleted by this change.

Before updating an existing installation, back up the encrypted SQLite database and `MASTER_KEY`. Do not regenerate `MASTER_KEY` or the existing Meta/Google credentials will become unreadable. Changing or losing it cannot decrypt saved credentials.

## Setup on a new server

1. `./setup.sh` creates `.env` with unique server secrets; do not commit `.env`.
2. `docker compose up -d --build`
3. `docker compose exec ads-ai python -m ads_core.cli create-admin --email you@example.com`
4. Access `/studio` through HTTPS reverse proxy with appropriate IP policies, per-IP rate limits, backups, 2FA at reverse proxy where possible. Docker Compose binds the application to localhost by default.
5. Test with a Demo account, then connect provider-API accounts using official access credentials.

## Provider coverage

| Platform | Reporting | Mutating |
|---|---|---|
| Demo | Labeled simulation | No |
| Meta Ads | Graph API (authorized token) | Campaign pause, plus ad-set daily-budget/bid-cap changes through guarded plans — every change needs a separate admin approval |
| Google Ads | Read-only reporting adapter, requires OAuth and developer token, **not live-validated** | Campaign pause, plus campaign-budget/manual-CPC changes through guarded plans — every change needs a separate admin approval; mutations are likewise **not live-validated** |
| TikTok Ads | Not implemented (501) | No |
| OpenAI Ads | Not implemented (501) | No |

Google Ads `token` input requires JSON with keys `client_id`, `client_secret`, `refresh_token`, and optional `login_customer_id`; set `GOOGLE_ADS_DEVELOPER_TOKEN` on the server. Meta account IDs must be numbers or `act_` plus numbers.

## Security and limitations

This is still a pilot, not security-certified SaaS. Local analysis is deterministic/rule-based, **not a cloud LLM chat**. No OpenAI API key is used; the only remote assistant is the optional, off-by-default OpenRouter integration described above, which an admin must explicitly enable. Advertising data still transits the official provider APIs for reporting and is visible to authorized users of the web dashboard; the Telegram notification integration remains optional and, when explicitly configured, sends pause confirmations and monitoring/advisor alerts (it never receives Ads credentials or report data). Read-only MCP also requires independent security review; no public MCP transport is enabled. In-app MFA is now available as opt-in per-user TOTP (Settings → MFA) and login failures are throttled durably in the database per email and source IP. Before production: independent security review, secret handling, least privilege, backup and recovery tests, and permission checks.

Test: `pip install -r requirements.txt pytest && python -m pytest -q`; frontend syntax: `node --check static/studio.js`.

See [security and upgrade notes](docs/STUDIO.md).

## 1-click OAuth: Google Ads / Meta Ads

A login-and-select-account OAuth flow is now implemented using server-side Google Ads and Meta credentials. The Google developer token and both providers' app client ID/secret must be configured on the server. Nothing has been pre-authorized with customer accounts. Authenticated admin only, state+session bound, expiring encrypted tokens, PKCE for Google. No public HTTP MCP endpoint; local read-only stdio exists. See [docs/OAUTH_CONNECT.md](docs/OAUTH_CONNECT.md) for setup and callback URL registration. Production requires HTTPS and approved API permissions. For Windows local testing the EXE uses its configured loopback origin; Meta may require an HTTPS callback depending on app settings.


## Internet tự động trên Windows (không cần VPS)

Khi mở EXE, chương trình dùng mạng Internet sẵn có của Windows, không cần kết nối qua VPS và không cần cấu hình địa chỉ máy chủ. Giao diện và API vẫn chỉ chạy ở `127.0.0.1:8765`. Sau khi đăng nhập, ứng dụng kiểm tra truy cập Internet qua hai địa chỉ HTTPS công khai cố định (Google và Cloudflare) bằng cách gọi từ máy cục bộ khoảng 45 giây/lần. Không gửi cookies, token Ads, API keys hay dữ liệu khách hàng tới hai địa chỉ kiểm tra. Nếu hai địa chỉ không truy cập được, ứng dụng hiển thị 'Chưa xác nhận Internet' (có thể vẫn có Internet nếu firewall chặn các địa chỉ đó).

Khi đường truyền phục hồi và người dùng đang xem Dashboard/Tài khoản Ads, ứng dụng tự tải lại dữ liệu; không tự đăng nhập hay xin thêm quyền thay người dùng. Google/Meta yêu cầu người dùng cấp OAuth một lần và cấu hình ứng dụng phù hợp; OpenRouter cần khóa hợp lệ và quyền chia sẻ dữ liệu do người dùng chủ động bật. Khi offline, giao diện cục bộ vẫn mở được nhưng không thể lấy báo cáo mới hoặc gọi AI trực tuyến. Đây là ứng dụng EXE portable, không phải bộ cài tự khởi động cùng Windows.


## Windows UX: no more CMD prompts

The Windows executable now uses PyInstaller `--windowed` (no black console window). On a fresh machine, it automatically opens a beautifully styled Vietnamese onboarding screen to create the first administrator and signs in automatically. Later launches open the dashboard directly.

The one-time setup endpoint is enabled only in desktop mode, accessible only on loopback, requires an ephemeral random token delivered via the browser URL fragment, and refuses any second administrator bootstrap after one account exists. User data stays in `%LOCALAPPDATA%\\LHMAdsAI`. Browser-based interface remains local at `http://localhost:8765`; no VPS or MCP. Credentials for Google/Meta OAuth and OpenRouter must still be configured by the user.

The EXE is portable, not an MSI installer, and is not yet code-signed. To stop the background process, close LHM Ads AI using Windows Task Manager. For troubleshooting, inspect the local `%LOCALAPPDATA%\\LHMAdsAI\\logs\\startup.log`.

## Native-window desktop shell (Windows)

LHM Ads AI now launches a **standalone Windows desktop window** using the
Microsoft Edge WebView2 engine, rather than opening the Chrome/Edge browser
for its primary UI. It is technically a *hybrid desktop application*:
the rich existing HTML/CSS dashboard renders inside the native window, with
the Python API and encrypted database confined to 127.0.0.1 on the user's PC.
This is not a fully rewritten Qt/WinUI user interface and not a remote website.
It requires the Microsoft Edge WebView2 Runtime on Windows.

Double-click `LHM-Ads-AI.exe`. On first use, the local window opens the
Vietnamese admin onboarding screen. On later uses it opens the dashboard in
the same standalone window. Closing the window shuts down its local API.
No browser tab, address bar, VPS, external MCP route, or bundled customer API key.

**Official Google/Meta OAuth consent deliberately opens the system browser**:
Google blocks OAuth logins from embedded webviews. After consent the browser
shows a confirmation and the desktop app retrieves the pending account list;
ad account data/tokens stay in the authenticated desktop session. This
hand-off requires a valid Google/Meta developer app and provider-granted scopes.


## Google Ads / Meta Ads: kết nối riêng từng nền tảng
Giao diện **Tài khoản Ads** có hai thẻ chọn riêng **Google Ads** và **Meta Ads**; từng nền tảng có hướng dẫn OAuth, cấu hình ứng dụng, nút đăng nhập, danh sách chờ chọn tài khoản và nhập token nâng cao riêng. Không sử dụng chung tài khoản Google với Facebook. Bộ lọc và nút **Kiểm tra API** có thể đọc thử báo cáo của chính tài khoản được chọn; trạng thái “Đã lưu token” không đồng nghĩa đã kết nối API thành công. [Hướng dẫn trong repo](docs/CONNECT_PROVIDERS.md).

Giao diện đã bổ sung hiệu ứng chuyển trang nhẹ, thẻ thống kê, biểu đồ, bộ lọc tài khoản và hỗ trợ hệ thống bật Reduce Motion. Không thay đổi chính sách bảo mật hoặc bật MCP. Google/Meta production OAuth và quyền quảng cáo thật vẫn cần ứng dụng/giấy phép của nhà cung cấp. Chưa triển khai TikTok/OpenAI Ads API thực.

## Offline monthly rental & Windows background collector (pilot)

See [docs/COMMERCIAL_LICENSE.md](docs/COMMERCIAL_LICENSE.md). Local machine-bound signed licenses are issued and renewed manually, the issuer's private signing key must never be in GitHub or EXE. The opt-in background collector only reads 7-day provider summary and records errors; it does NOT optimize bids, budgets or strategies. Billing integration and fully autonomous Ads API writing remain unimplemented.

## MCP and PWA budget Web Push (24/10/2026)

Read-only stdio MCP integration with revocable admin-issued credentials; and opt-in daily-spend thresholds with encrypted device Push subscriptions are implemented in the source code. Both need live OAuth/API approval, HTTPS, a continuously running monitor worker and real phone/browser acceptance testing before production claims. **No TikTok reporting MCP adapter, no unattended provider write tools and no guaranteed 24/7 alerts from a phone-only PWA.** See [deployment guide](docs/MCP_PUSH_RELEASE.md).

## Deployment domain for PWA/API

Public production origin: **https://ads.lhmcrm.com** (pending Cloudflare Workers DNS deployment; the legacy VPS route is optional). The Caddy HTTPS production overlay lives in [compose.ads-lhm-com.yml](compose.ads-lhm-com.yml), with exact Google/Meta callback URLs and step-by-step setup in [docs/DEPLOY_ADS_LHM_COM.md](docs/DEPLOY_ADS_LHM_COM.md). The Windows local app remains separate on localhost. Never assume the GitHub commit means this public domain is already live.
