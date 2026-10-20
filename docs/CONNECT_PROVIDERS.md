# Hướng dẫn kết nối Google Ads và Meta Ads riêng biệt

Trong LHM Ads AI Desktop, mở mục **Tài khoản Ads**. Chọn **Google Ads** hoặc **Meta Ads** bằng hai thẻ riêng. Hai nền tảng KHÔNG dùng chung tài khoản, session OAuth hoặc access token.

## Google Ads
1. Chọn Google Ads → Cấu hình Google OAuth.
2. Tạo Google Cloud OAuth client loại Desktop và cấp quyền Google Ads API cho project: https://console.cloud.google.com/apis/credentials
3. Nhập OAuth Client ID (và Client Secret nếu Google cấp) ở mục Cài đặt trên máy Windows.
4. Bấm Đăng nhập Google Ads. Trình duyệt mặc định mở màn hình cấp quyền Google.
5. Quay lại cửa sổ LHM Ads AI, chọn tài khoản được quyền và bấm lưu. Dùng bộ lọc Google Ads và nút Kiểm tra API để đọc báo cáo thử.

## Meta Ads
1. Chọn Meta Ads → Cấu hình Meta App.
2. Dùng Meta Developer App chính thức (https://developers.facebook.com/apps/) với App ID, App Secret, Facebook Login và quyền quảng cáo thích hợp.
3. Nhập App ID và App Secret trên máy Windows; bấm Đăng nhập Meta Ads để cấp quyền trong trình duyệt hệ thống.
4. Quay lại ứng dụng, chọn những tài khoản Meta được cấp quyền, lưu và bấm Kiểm tra API.
5. Meta App Live có thể yêu cầu HTTPS callback, xét duyệt ứng dụng và quyền ads_read/ads_management. Đăng nhập localhost có thể không được chấp nhận khi phát hành rộng.

## Lưu ý
- Bộ lọc Tất cả / Google Ads / Meta Ads / Demo phân tách danh sách tài khoản; xác minh API gọi tài khoản được chọn, không gửi token về giao diện.
- Đã lưu token khác với đã xác nhận API hoạt động. Mỗi lần kiểm tra gọi báo cáo của nền tảng tương ứng.
- Nhập token thủ công được đặt dưới mục nâng cao của nền tảng đã chọn. Không nhập mật khẩu Google/Facebook vào phần mềm.
- Không có kết nối MCP; OpenRouter chỉ dùng nếu người dùng chủ động bật và cấp quyền.
- Windows EXE chạy trên máy cá nhân, không cần VPS. Kết nối Google/Meta vẫn yêu cầu Internet và ứng dụng OAuth của từng nhà cung cấp.
- GitHub Actions dùng HTTP mock để thử OAuth, không chứng minh tài khoản Ads thật được cấp quyền.