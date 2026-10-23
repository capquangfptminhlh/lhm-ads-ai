# Quy tắc bắt buộc: tài khoản quảng cáo nằm 100% trên thiết bị khách

**Quyết định sản phẩm ngày 24/10/2026:** Không lưu định danh tài khoản Ads, access token, refresh token, developer token của từng khách, OAuth authorization code, API client secret riêng của khách, campaign dữ liệu hoặc bản sao credentials Google/Meta/TikTok tại Cloudflare Workers, D1, KV, R2, Queues, logs, Analytics hoặc bất cứ máy chủ LHM nào. Không sao lưu hoặc đồng bộ chúng lên GitHub.

## Phân chia vai trò

| Thành phần | Lưu được | Không lưu / không nhận |
|---|---|---|
| Electron/Windows | Credentials của khách trong kho khóa hệ điều hành (ví dụ Windows DPAPI/Credential Manager), kết nối Ads, tài khoản và báo cáo cục bộ | Không đồng bộ token lên LHM |
| PWA trên điện thoại | Tài khoản, credential và báo cáo trong kho cục bộ của origin; khóa mật mã không gửi máy chủ, giải mã sau khi khách chủ động mở khóa | Không gửi token về máy chủ LHM hoặc bộ phân tích AI |
| Cloudflare Workers / D1 | Người dùng LHM, hợp đồng thuê, gói, số slot còn lại, quyền thiết bị, dữ liệu trạng thái chung không nhận diện Ads | Không giữ ID Ads, email quản trị Ads, Ads credentials, báo cáo Ads |
| MCP Gateway / AI | Định danh thiết bị ẩn danh, trạng thái online, khả năng giao tiếp với agent theo quyền và kết quả tổng hợp đã ẩn danh nếu khách cho phép | Không lưu nội dung Ads, token hoặc xuất báo cáo thô sang cloud nếu chưa được phép rõ ràng |

## Đảm bảo phạm vi

- Cloudflare Workers là **control plane**, quản lý thuê bao, hiện diện và quyền kết nối; không phải nơi thực hiện thay mặt khách OAuth Ads hoặc lấy Ads API bằng token của khách.
- **Data plane** (OAuth Ads, gọi API, báo cáo, lệnh Ads, MCP tools) chạy ở thiết bị khách. Agent trung tâm có thể gửi yêu cầu hành động đến client online bằng kênh thiết lập từ thiết bị; thiết bị tự xác thực quyền và thực hiện cục bộ. Không chuyển token vào yêu cầu hay phản hồi MCP.
- PWA có thể dùng IndexedDB để lưu **ciphertext**. Khóa giải mã phải được dẫn xuất từ mật khẩu/mã mở khóa người dùng riêng tư (WebCrypto PBKDF2/AES-GCM, có salt và nonce đúng chuẩn) hoặc một phương án khóa nền tảng được kiểm chứng. **Không lưu khóa giải mã bên cạnh ciphertext** và không tải mật khẩu mở khóa lên Cloudflare.
- WebCrypto/IndexedDB không bảo đảm chống XSS hoặc JavaScript độc hại được phục vụ cùng origin; phải triển khai CSP, kiểm soát supply chain, kiểm toán code, chống injection. Dữ liệu IndexedDB có thể bị xóa do trình duyệt/hệ điều hành; cần quy trình tái ủy quyền hoặc sao lưu mã hóa do khách tự giữ.
- Trên từng điện thoại hoặc laptop, người dùng cần cấp quyền Ads riêng; không suy đoán đăng nhập LHM trên máy thứ hai tự chuyển credential từ máy trước.
- OAuth theo nền tảng **phải được xác minh** về CORS, yêu cầu confidential client, refresh-token grant, PKCE, phê duyệt API. Nếu một nền tảng chỉ cho phép trao đổi token qua confidential backend hoặc chặn browser API: **không được âm thầm proxy token qua Cloudflare**; hãy hiển thị giới hạn hoặc đề xuất quy trình khác để chủ sản phẩm phê duyệt.
- Cloudflare chỉ nhận kết quả tổng hợp/ẩn danh nếu khách chủ động cấp quyền theo từng loại dữ liệu và có thể rút quyền; theo yêu cầu hiện tại, mặc định là **không đồng bộ số liệu quảng cáo**.

## Hệ quả bắt buộc đối với giám sát

- **Electron** có thể giám sát theo lịch khi máy khách bật, có mạng và tiến trình giám sát chạy.
- **PWA trên mobile** có thể đọc Ads và tạo cảnh báo tại chỗ khi hoạt động; hệ điều hành có thể đóng/tạm dừng PWA, chặn việc đọc API nền.
- **Cloudflare Cron không thể đọc Ads khi tất cả thiết bị khách offline/ứng dụng bị dừng**, vì không có token. Không quảng cáo "PWA luôn online như Zalo", "theo dõi 24/7 khi tắt điện thoại" hoặc "cảnh báo vượt mức ngay lập tức".
- Web Push từ Cloudflare chỉ có thể thông báo dựa trên tín hiệu không nhạy cảm **đã được thiết bị online chủ động gửi với sự đồng ý**; không thể tự phát hiện mức chi tiêu mới của tài khoản offline.

## Tình trạng code và phát hành

- Backend FastAPI cũ (`ads_core/app.py`, `ads_core/oauth_connect.py`, `ads_core/db.py`) hiện vẫn lưu token Ads mã hóa vào SQLite phía backend. Đó là **kiến trúc legacy, không đạt chính sách device-only khi chạy trên máy chủ**. Chỉ coi đó là lưu trữ cục bộ nếu FastAPI/DB chạy thực sự trên laptop do khách kiểm soát.
- Cloudflare Worker hiện chỉ trả 503 cho API chưa phát triển, **không nhận credentials**. Không bật `auth_ready` hoặc tính năng OAuth cho khách hàng trước khi có kho local, luồng ủy quyền phù hợp và kiểm thử bảo mật end-to-end.
- MCP stdio hiện chạy bên cạnh backend local, chưa phải một agent từ xa tự truy cập được thiết bị khách.
- Chưa xác nhận Google/Meta/TikTok browser-only OAuth + API đầy đủ. Không khẳng định có tích hợp live trên PWA cho đến khi chứng minh được.
- Chính sách **ưu tiên hơn** mọi tài liệu Docker/VPS cũ, mô hình proxy credentials, server-stored encrypted token hoặc tư vấn Cloudflare Cron thu thập trực tiếp tài khoản Ads.

## Điều kiện phát hành không được bỏ qua

1. Test mạng khi OAuth/login/report chạy từ PWA: không có token, ID Ads hoặc dữ liệu Ads xuất hiện ở bất cứ endpoint Cloudflare, logging hay analytics.
2. Test lưu trữ trong DevTools: dữ liệu Ads chỉ cục bộ, đã mã hóa, không khóa giải mã lưu cùng; logout và xóa dữ liệu gỡ toàn bộ.
3. Kiểm tra CSRF/XSS/supply chain/CSP và hạn chế service-worker caching; test thiết bị Android/iOS thật.
4. Test cách ly nhiều người dùng trên cùng một trình duyệt, giới hạn số tài khoản theo giấy phép, thao tác thu hồi khóa/thiết bị, MFA LHM.
5. Test OAuth và Ads API riêng cho mỗi nhà cung cấp bằng credential thật do khách cấp, không chuyển credential đến LHM.
6. Test offline/mobile khóa màn hình; UI phải hiển thị "Không giám sát khi ứng dụng tạm dừng", không hứa 24/7.
