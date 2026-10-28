# LHM Ads AI — Audit toàn dự án (26/10/2026)

**Phạm vi:** mã nguồn PR #46, GitHub Actions Windows/Linux/PWA, giao diện và API công khai của `ads.lhmcrm.com`. Báo cáo này là **ảnh chụp tại thời điểm kiểm tra**, không phải chứng nhận sản phẩm hoàn toàn không lỗi. Không sử dụng tài khoản quảng cáo hay chuyển khoản thật, không xem bí mật Cloudflare/GitHub và không triển khai production.

## Phát hiện đã sửa trên nhánh tính năng

| Mức | Phần | Lỗi có bằng chứng | Thay đổi |
| --- | --- | --- | --- |
| Cao | Thanh toán D1 | Duyệt đơn đặt `status=paid` **trước** khi cấp/gia hạn license ở giao dịch khác; lỗi SQL có thể để lại đơn đã thanh toán nhưng không có quyền dùng, retry báo trùng. | `fulfillPaidOrder` chuyển ghi tiền, license, fulfillment, payment review và audit vào **một `db.batch` atomic**. |
| Cao | Cấp gói thủ công | Admin tạo đơn `paid` trước khi cấp quyền; lỗi grant để lại đơn mồ côi. | Cấp gói và tạo paid order cùng một `db.batch` bằng `createPaidOrder`. |
| Cao | Kiểm chứng lỗi rollback | Chưa có bài test cố ý làm D1 lỗi giữa giao dịch. | Thêm `worker_gmail_plans.test.mjs` test tiêm lỗi ở cuối batch, xác nhận **rollback** và thử lại thành công. |
| Trung bình | Triển khai Cloudflare | Pre-deploy chưa chạy toàn bộ regression thanh toán/gói Gmail thật trên SQLite. | `deploy-commerce.yml` chạy `node --test tests/worker_gmail_plans.test.mjs`. |
| Cao | Nghiệm thu production | `smoke_production.py --strict` có thể PASS khi Admin/D1 cũ còn chạy nhưng chức năng Gmail/PWA Ads mới trả 503. | Thêm `tools/smoke_gmail_production.py` và test, nối vào workflows **Production HTTPS smoke** và **Deploy LHM Ads Commerce**. |
| Trung bình | License Windows | Mất mạng/408/429/5xx trước đây có thể khóa oan khi lease ký số còn hạn. | Giữ duy nhất lease Ed25519 đã kiểm tra, vẫn giới hạn 72h và ngày hết hạn; phản hồi thu hồi/khóa từ máy chủ khóa ngay. |
| Cao | Bản thương mại | Có đường đóng gói nhầm pilot hoặc thiếu khóa Worker ký lease. | Build fail-closed, kiểm tra provenance Nuitka, SHA-256 và **khóa công khai Worker được tin cậy độc lập**. |
| Trung bình | Pháp lý | Trang Điều khoản/Chính sách bảo mật còn `BẢN NHÁP` và `[CẦN ĐIỀN]`. | `check_commercial_legal.py` chặn **commercial=true**, không bịa thông tin cá nhân/chính sách. |

## Nghiệm thu qua mã nguồn và CI

- [x] Unit test Python toàn bộ repo; các bộ kiểm thử JavaScript, SQLite D1, tài khoản Gmail, ghép PC, tự động hóa, backup/restore và Google/Meta với mock: workflow **Test LHM Ads AI** phải PASS ở SHA phát hành.
- [x] Kiểm tra tài sản và cú pháp Worker/PWA: workflow **Validate Cloudflare PWA static bundle**.
- [x] Windows Nuitka và PyInstaller bản pilot đã PASS trong các lượt CI trước, gồm khởi động EXE thật, WebView2, audit mã nội bộ, SHA-256, pilot smoke và Gmail-only staging smoke.
- [ ] Cần xác nhận lại **cả ba workflow PASS cùng đúng SHA mới nhất** sau các commit sửa giao dịch và thêm production smoke. Không sử dụng artifact cũ để khẳng định bản mới đạt.
- [ ] Build `workflow_dispatch commercial=true` bằng **khóa công khai vendor và Worker production thật**, không sử dụng khóa thử nghiệm.
- [ ] Nghiệm thu sạch trên Windows 10/11 thật, ngủ/thức máy, khôi phục dữ liệu, cập nhật có chữ ký, 2 thiết bị và lease 72 giờ.
- [ ] Đăng nhập Google/OAuth production thật, chọn gói 499.000đ, chuyển khoản VietQR, xác nhận ngân hàng thật, gia hạn và thu hồi.
- [ ] Đọc tài khoản Google Ads và Meta Ads thật; đối chiếu số liệu với giao diện chính thức, kiểm tra MCC, OAuth scopes/quota và CORS trên Chrome/iPhone.
- [ ] Điều khoản dịch vụ, bảo mật, hoàn tiền, liên hệ và chứng từ đã được chủ cung cấp xác nhận.

## Kiểm tra HTTPS production không đăng nhập (trạng thái trước deploy)

Kiểm tra read-only `https://ads.lhmcrm.com` vào ngày 26/10/2026:

| Đường dẫn | Quan sát | Đánh giá |
| --- | --- | --- |
| `/` | HTTP 200, trang giới thiệu hiện hoạt | PASS tải trang, chưa phải chứng cứ thương mại |
| `/local/` | HTTP 200, **vẫn hiện đăng nhập email/mật khẩu và kích hoạt bằng key** | FAIL đối với luồng Gmail-only mới |
| `/api/_hosting/status` | HTTP 200, D1/Access commerce cũ báo sẵn sàng; `auth_ready=false`, `ads_api_ready=false`, thiếu cờ Google/Gmail plans mới | FAIL readiness Gmail commercial |
| `/api/auth/session` | HTTP **503** `DEVICE_ONLY_NOT_READY` | FAIL: luồng Gmail mới chưa triển khai |
| `/api/public/ads-config` | HTTP **503** `DEVICE_ONLY_NOT_READY` | FAIL: chưa phục vụ cấu hình OAuth Ads công khai |
| `/admin/` | Điều hướng sang đăng nhập **Cloudflare Access** | Chỉ xác nhận có lớp bảo vệ; chưa thử Admin đã xác thực |

**Kết luận:** mã PR chưa triển khai vào Worker/PWA production. Không thể coi `auth_ready`, `ads_api_ready`, thương mại hoặc đăng ký Gmail là đã hoạt động trên domain. Không tự merge hoặc deploy khi chưa đủ khóa/secrets và nghiệm thu của chủ sở hữu.

## Rủi ro cần xác nhận khi live

1. **API/Browser:** logic giả lập Google Ads–Meta API trong Chromium không chứng minh được CORS, OAuth scopes, quota và quyền cập nhật chiến dịch ngoài đời. Trên Google Ads, quyền production gắn với Cloud project; cần kiểm tra quyền API trong Google Cloud Console.
2. **Thanh toán:** công cụ kiểm soát việc kích hoạt sau khi Admin nhập/chấp thuận reference, nhưng không phải hệ thống tự đọc ngân hàng. Cần quy trình kiểm tra số tiền, mã đơn, mã giao dịch và phát hiện trùng giao dịch trước khi kích hoạt.
3. **License:** mất mạng có thể dùng đến giới hạn lease đã ký, nhưng không thể biết việc thu hồi mới phát sinh trong lúc máy hoàn toàn offline; đây là giới hạn thiết kế của grace period.
4. **Bảo mật/Windows:** binary **không ký Authenticode** theo lựa chọn chủ sản phẩm, nên có thể xuất hiện SmartScreen/Unknown Publisher. Chữ ký Ed25519 của manifest không thay thế sự tin cậy của Windows.
5. **Vận hành:** cần xác minh GitHub/Cloudflare secrets, Worker D1 migrations, App Review Google/Meta, versioned update manifest và khả năng phục hồi backup ngoài môi trường giả lập.

## Tiêu chí chốt

**Chỉ gọi READY TO SELL khi:** cùng một SHA có CI Linux/Chromium, PWA, Windows Nuitka PASS; `smoke_production.py --strict` **và** `smoke_gmail_production.py` đều PASS sau khi triển khai; chủ sản phẩm phê duyệt các bài nghiệm thu live cùng bản phát hành không ký số/kiểm tra chữ ký offline. Mọi mục thiếu bằng chứng giữ **NOT_RUN** thay vì tuyên bố hoàn tất.

Liên quan: `docs/ACCEPTANCE.md`, `docs/GOOGLE_SUBSCRIPTION_ROLLOUT.md`, [PR #46](https://github.com/capquangfptminhlh/lhm-ads-ai/pull/46).
