# Không sử dụng GitHub Pages để phát hành LHM Ads AI thương mại

**Tài liệu cũ đã thay thế.** Do GitHub Pages không cho phép dùng làm hosting miễn phí cho SaaS thương mại, kế hoạch đặt PWA LHM Ads AI trả phí tại GitHub Pages không được áp dụng.

**Kiến trúc mới không VPS:** GitHub lưu mã nguồn, Cloudflare Workers + Static Assets triển khai PWA + API cùng tên miền `ads.lhm.com`. Đọc [hướng dẫn mới](DEPLOY_CLOUDFLARE_WORKERS.md).

- Không tạo CNAME `ads.lhm.com -> capquangfptminhlh.github.io`.
- Không dùng GitHub Pages để nhận mật khẩu, OAuth token hoặc thanh toán.
- Worker hiện là bản an toàn mặc định, chưa có backend Ads thật; chưa phát hành thương mại.

Điều khoản: https://docs.github.com/en/pages/getting-started-with-github-pages/github-pages-limits
