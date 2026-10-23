# ads.lhm.com: GitHub Pages + Cloudflare (không VPS)

**Phương án đã chọn:** GitHub repo là source of truth, GitHub Pages chỉ phát hành giao diện HTML/CSS/JS/PWA; Cloudflare quản lý DNS/TLS và có thể chạy một Worker riêng ở đường dẫn `/api/*`.

> Không chạy Python FastAPI hay SQLite trong GitHub Pages. Các chức năng đăng nhập, tài khoản quảng cáo, OAuth, giám sát, MCP, AI và Web Push cần backend phù hợp Cloudflare (Workers + D1/Queues/Cron). Đây là công việc **chuyển đổi backend**, không phải chỉ đổi DNS. Worker hiện tại là placeholder 503 an toàn và chưa thể xác thực tài khoản hay đọc Ads.

## Bước 1 — GitHub Pages

1. Trong repo `capquangfptminhlh/lhm-ads-ai`, hoàn thành review/merge PR đang phát triển vào `main` sau khi CI xanh. Không gộp chỉ để có website nếu API chưa được xem xét bảo mật.
2. GitHub → **Settings → Pages → Build and deployment → Source: GitHub Actions**. Workflow `.github/workflows/github-pages-pwa.yml` build nội dung tĩnh từ `static/` bằng `python tools/build_github_pages.py --output _site`.
3. GitHub → **Settings → Pages → Custom domain**: `ads.lhm.com`. Đặt site là nguồn được ủy quyền cho tên miền và bật **Enforce HTTPS** khi chứng chỉ đã sẵn sàng.
4. Website tĩnh có đường dẫn `https://ads.lhm.com/studio/`. Biểu tượng, manifest và service worker cùng root domain. Biểu mẫu đăng nhập được ẩn mặc định để không đánh lừa khách khi API chưa được chuyển sang Cloudflare.
5. Chạy lại pipeline trên `main` để cập nhật sau khi merge; GitHub Actions chỉ deploy static files, không chứa `.env`, token hay database.

## Bước 2 — Cloudflare DNS

- Trên zone **lhm.com** → DNS → tạo **CNAME**: Name `ads` → Target `capquangfptminhlh.github.io` (**không** thêm `/lhm-ads-ai`). Giữ cấu hình GitHub custom domain chính xác; ban đầu chọn DNS-only nếu GitHub cần xác minh HTTPS; sau khi HTTPS hoạt động và sẵn sàng route Worker, dùng Cloudflare proxy (orange cloud) và SSL **Full (strict)**.
- **Không** trỏ A record vào VPS không tồn tại, không thay đổi MX hay record của `lhm.com` chính.
- Xác nhận HTTPS, quyền sở hữu tên miền và chứng chỉ trên GitHub/Cloudflare trước khi phát hành công khai.

Nguồn: https://docs.github.com/en/pages/configuring-a-custom-domain-for-your-github-pages-site/managing-a-custom-domain-for-your-github-pages-site

## Bước 3 — Cloudflare Worker cho API

- Cấu hình mẫu: `workers/ads-api/wrangler.toml` dùng route `ads.lhm.com/api/*`, zone `lhm.com`. Route chỉ hoạt động với Cloudflare-proxied DNS.
- Tập tin `workers/ads-api/src/index.js` hiện trả `/api/_hosting/status` với `auth_ready:false`; các API khác trả **503**. Đây là phép thử route fail-closed, **không phải** server Ads hoàn thiện.
- Khi đã có tài khoản Cloudflare đủ quyền và đã port xong backend, triển khai sau review bằng `npx wrangler deploy -c workers/ads-api/wrangler.toml` (yêu cầu xác thực Wrangler từ máy riêng). **Không** đưa Cloudflare API token vào GitHub code hay ChatGPT chat.
- Worker phải đọc/ghi dữ liệu cách ly theo tenant vào D1 và lưu secrets trong Cloudflare Secrets hoặc một thiết kế giữ khóa phía khách phù hợp. Không chuyển token quảng cáo vào Cloudflare khi khách chưa đồng ý.
- OAuth Google: `https://ads.lhm.com/api/oauth/google/callback`.
- OAuth Meta: `https://ads.lhm.com/api/oauth/meta/callback`.
- Báo cáo/AI chạy khi quyền API có thật; Cron chỉ có thể chạy giám sát thường xuyên khi hệ thống có cách truy cập thông tin Ads được khách chấp thuận. Không khẳng định PWA khóa màn hình chạy agent 24/7.

Nguồn: https://developers.cloudflare.com/workers/configuration/routing/routes/

## Quyết định an toàn quan trọng

Anh đã từng yêu cầu **dữ liệu và token quảng cáo chỉ nằm trên thiết bị khách**, không lưu trên máy chủ. Nếu giữ ràng buộc này tuyệt đối, Cloudflare Cron không thể âm thầm đọc Google/Meta khi tất cả thiết bị khách đã tắt. Có hai mô hình khác nhau:

- **Client-only:** token được lưu an toàn tại thiết bị, agent hoạt động khi thiết bị đang online và môi trường cho phép. Không bảo đảm giám sát khi điện thoại khóa, khi PWA bị hệ điều hành dừng, hoặc khi không có thiết bị online.
- **Server-based với đồng ý rõ ràng:** OAuth và token mã hóa tại backend Cloudflare, Cron hoặc Queues/Workers có thể kiểm tra theo lịch và Web Push khi khách không mở PWA. Cần quản trị khóa/mã hóa, tách tenant, giới hạn sử dụng, quyền thu hồi và chính sách dữ liệu minh bạch.

Phải chọn rõ mô hình này trước khi bật OAuth thật. Đừng tự ý thay đổi yêu cầu lưu trữ của khách.

## Chấp nhận trước khi công bố

- GitHub Pages build từ `main`, TLS hợp lệ, `/studio/`, `/sw.js`, `/manifest.webmanifest` đều hoạt động trên cả Android và iPhone.
- Cloudflare Worker route hoạt động, API không trả 200 giả cho các endpoint chưa hoàn thiện.
- Chuyển đổi đầy đủ `/api/login`, `/api/studio/me`, OAuth/callback, token custody, account management, reports, alert rules, MCP gateway và push theo D1/Workers nếu muốn sản phẩm vận hành không VPS.
- Thử Google/Meta OAuth thật, kiểm thử multi-tenant, budget/currency/date, khóa/mở màn hình và thu hồi quyền, giới hạn Cloudflare.
- Không công bố 24/7, MCP điều khiển quảng cáo hoặc TikTok Ads đang hoạt động trước khi có kiểm thử end-to-end.

## Giữ lại Docker cho tương lai

Các tập tin `Dockerfile`, `docker-compose.yml`, `compose.ads-lhm-com.yml`, Caddy vẫn là phương án **khác**, không dùng để triển khai GitHub Pages + Cloudflare Worker. Không được khởi động hai kiến trúc cùng một tên miền cùng lúc nếu chưa xử lý proxy và di chuyển dữ liệu.
