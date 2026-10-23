# Triển khai LHM Ads AI không VPS: GitHub + Cloudflare Workers

**Tên miền thương mại:** https://ads.lhm.com

## Vì sao KHÔNG dùng GitHub Pages để bán phần mềm?

GitHub Pages chỉ hỗ trợ web tĩnh và GitHub **không cho dùng GitHub Pages làm dịch vụ hosting miễn phí cho SaaS thương mại**. Vì LHM Ads AI có gói trả tiền, GitHub vẫn nên giữ mã nguồn và kiểm thử, còn Cloudflare Workers + Static Assets đảm nhận PWA và API.

Quy định chính thức: https://docs.github.com/en/pages/getting-started-with-github-pages/github-pages-limits

## Cấu trúc đã chuẩn bị trong repo

- `static/`: giao diện PWA hiện có (trình duyệt và mobile).
- `tools/build_github_pages.py`: bộ xuất giao diện thành `_site/`. Tên file giữ để tương thích với kiểm thử cũ, **nhưng output hiện dùng cho Cloudflare, không xuất bản GitHub Pages thương mại**.
- `wrangler.toml`: một Worker ở **ads.lhm.com**, `assets.directory = "./_site"`, `run_worker_first = ["/api/*"]`. Cloudflare cấp HTTPS và DNS custom-domain, không cần trỏ CNAME tới GitHub.
- `workers/ads-api/src/index.js`: Worker bản an toàn mặc định, chỉ trả health readiness `/api/_hosting/status` (`auth_ready:false`) và 503 cho API chưa được chuyển đổi. File tĩnh giao cho Cloudflare Assets.
- `static/cloudflare-hosting-gate.js`: khóa form đăng nhập trong bundle tĩnh cho đến khi API thật tự xác minh sẵn sàng.
- GitHub Actions chỉ **build + test**; việc nối Cloudflare Git Integration phải được chủ tài khoản Cloudflare cho phép.

## Cài đặt Cloudflare Workers Builds (một lần)

1. Vào **Cloudflare Dashboard → Workers & Pages → Create application → GitHub**, cấp quyền repo `capquangfptminhlh/lhm-ads-ai`.
2. Tạo Worker có **name `lhm-ads-cloudflare-api`**, matching với `wrangler.toml`. Chọn production branch `main` (sau khi PR đã nghiệm thu và merge), repository root `/`.
3. **Build command:** `python tools/build_github_pages.py --output _site`. Nếu build image chưa có Python thì cấu hình môi trường có Python hoặc thay bằng GH Actions xuất artifact/deploy qua Wrangler.
4. **Deploy command:** `npx wrangler deploy` (đọc `wrangler.toml` ở gốc repo). Preview builds nên được kiểm tra trước khi cho production.
5. Khi bật **Custom Domain `ads.lhm.com`**, Cloudflare tự cấu hình DNS/TLS nếu `lhm.com` là zone do Cloudflare quản lý. Kiểm tra xung đột nếu tên miền đang được một project khác sử dụng. Đừng tạo CNAME trỏ tới GitHub Pages.
6. Trên điện thoại, mở `https://ads.lhm.com/studio/` để xem bản PWA và cài lên màn hình chính. Nếu chưa có backend thực tế, màn hình phải **khóa đăng nhập** và hiển thị thông báo đang triển khai.

Nguồn Cloudflare Workers Static Assets: https://developers.cloudflare.com/workers/static-assets/

Nguồn Git integration: https://developers.cloudflare.com/workers/ci-cd/builds/

Nguồn custom-domain: https://developers.cloudflare.com/workers/configuration/routing/custom-domains/

## Chính sách chủ sản phẩm: 100% tài khoản Ads chỉ ở thiết bị

**Đã khóa quyết định:** không đưa credentials, danh sách tài khoản Ads hay báo cáo Ads của khách lên Cloudflare kể cả khi đã mã hóa. Cloudflare chỉ quản lý hợp đồng, đăng nhập LHM, giấy phép và trạng thái kết nối không nhạy cảm. OAuth + API quảng cáo + MCP data-plane phải vận hành trên thiết bị của khách sau khi xác minh tính khả thi của từng nền tảng; **không được giữ token Ads trên server để chạy Cron**.

PWA có thể bị hệ điều hành tạm ngừng khi khóa máy, nên không thể cam kết theo dõi 24/7 chỉ nhờ điện thoại. Bản Cloudflare Worker cố ý trả `device_only_ready:false` và API Ads 503 cho đến khi thật sự đạt yêu cầu.

Đọc toàn bộ điều kiện kỹ thuật tại [DEVICE_ONLY_ADS_DATA.md](DEVICE_ONLY_ADS_DATA.md).

## Backend thương mại chưa được chuyển đổi

Repo hiện vẫn có FastAPI/Python dùng SQLite, phiên đăng nhập, OAuth, mã hóa token, agent và MCP cục bộ. Không thể bê nguyên code cùng SQLite/uvicorn vào một Worker JS mà coi là chạy được. Để có app thật **không VPS**, cần port/test các hạng mục theo thứ tự:

1. Cloudflare D1/DO: bảng người dùng, tenant, giấy phép, quyền riêng, phiên đăng nhập; giao dịch/throttling và audit; backup phù hợp.
2. Secure authentication, CSRF, MFA, mã hóa và quản lý vòng đời token; rà soát lựa chọn người giữ khóa. Chỉ bật một khả năng khi có endpoint thật, được kiểm thử.
3. Google/Meta OAuth và truy vấn API thực trên Worker, callback `https://ads.lhm.com/api/oauth/google/callback` / `https://ads.lhm.com/api/oauth/meta/callback`.
4. Báo cáo, AI giới hạn theo gói, cảnh báo ngân sách bằng Cron/Queues, Web Push với opt-in, chống báo trùng và giới hạn Cloudflare.
5. MCP Gateway HTTP có xác thực, tenant isolation và tool read-only mặc định, có audit và thu hồi quyền; không tự động cho agent sửa quảng cáo.
6. TikTok Ads chỉ tích hợp khi có quyền API/duyệt ứng dụng hợp lệ.

**MCP stdio local** chạy ở bản desktop không trở thành remote MCP chỉ nhờ deploy frontend.

**Lưu ý dữ liệu:** yêu cầu token Ads chỉ lưu ở thiết bị khách xung đột với mô hình serverless giám sát khi mọi thiết bị đều tắt. Nếu dùng Cron 24/7, cần có credential delegation với sự đồng ý rõ ràng và quản trị khóa phù hợp. Không mặc nhiên sao chép token khách lên Cloudflare.

## Chỉ công bố thương mại sau khi có bằng chứng

- CI mới nhất xanh; Worker triển khai có TLS, không trả 200 giả cho endpoints chưa làm.
- Test OAuth thật, D1 tách tenant, gói 5/20/50/100 tài khoản, gia hạn, license và AI rate limits.
- Test background Cron/Web Push trên iPhone/Android, lỗi API và throttling, app bị khóa màn hình.
- Kiểm thử bảo mật, lộ token/logs, xóa dữ liệu khách, sao lưu, quyền rút ủy quyền.
- Hiện tại bản Static Assets mới **chỉ là bản PWA an toàn để dựng hosting và kiểm tra giao diện**. Chưa bán/giao cho khách như sản phẩm hoàn chỉnh.
