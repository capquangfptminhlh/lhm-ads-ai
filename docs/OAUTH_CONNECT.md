# Kết nối Google Ads / Meta Ads bằng nút OAuth

Bản này **không tích hợp MCP**. Chỉ người dùng `admin` đăng nhập trên website mới có thể bắt đầu OAuth, chọn tài khoản và lưu token mã hóa tại máy chạy ứng dụng.

## Cấu hình một lần ở máy chủ

Chỉnh `.env` hoặc biến môi trường của Windows trước khi chạy EXE (không đưa API secret vào source code, không gửi qua chat):

```ini
# Trên VPS dùng đúng URL HTTPS của ứng dụng, ví dụ:
PUBLIC_BASE_URL=https://ads.example.com
GOOGLE_OAUTH_CLIENT_ID=...apps.googleusercontent.com
GOOGLE_OAUTH_CLIENT_SECRET=...
GOOGLE_ADS_DEVELOPER_TOKEN=...
GOOGLE_ADS_API_VERSION=v25
META_APP_ID=...
META_APP_SECRET=...
META_OAUTH_SCOPES=ads_read
```

Tạo Google Cloud OAuth **Web application**, bật API Google Ads nếu cần, cấu hình consent screen, thêm Redirect URI chính xác:

`https://ads.example.com/api/oauth/google/callback`

Tạo Meta developer app, bật Facebook Login (phù hợp app type/cấu hình), quyền `ads_read` và Redirect URI chính xác:

`https://ads.example.com/api/oauth/meta/callback`

Cần quyền/app review từ Meta cho người dùng bên ngoài vai trò test/dev. Meta `ads_read` chỉ cho đọc; tính năng tạm dừng Meta yêu cầu quyền `ads_management` riêng, và vẫn phải qua bước admin duyệt. Để yêu cầu cả hai quyền, chỉ khi Meta App đã được phê duyệt, đặt `META_OAUTH_SCOPES=ads_read,ads_management`.

Google Ads còn cần **Developer Token** ở cấp Manager account phù hợp quyền truy cập. Danh sách trả về có các tài khoản mà người dùng đăng nhập có quyền trực tiếp, cộng tài khoản con của MCC nếu API cho phép liệt kê. Việc hiển thị và truy xuất dữ liệu phụ thuộc quyền của ứng dụng/API; OAuth **không** bỏ qua bước xét duyệt API.

## Luồng sử dụng

1. Chạy web trên domain HTTPS cấu hình ở trên, hoặc chạy EXE cục bộ đã cấu hình OAuth dành cho môi trường thử nghiệm.
2. Vào `Tài khoản quảng cáo` với quyền Admin, chọn `Kết nối Google Ads` hoặc `Kết nối Meta Ads`.
3. Trang đăng nhập chính thức của Google/Meta xuất hiện. Đồng ý các quyền được yêu cầu.
4. Hệ thống đưa về mục `Tài khoản quảng cáo`, hiển thị danh sách được ủy quyền. Tick tài khoản và bấm `Lưu tài khoản đã chọn`.
5. Tài khoản có trạng thái đã kết nối; mở dashboard để tải dữ liệu thật từ API chính thức.

**Đối với Windows EXE:** ứng dụng nghe trên `http://127.0.0.1:8765` mặc định, nên callback tương ứng là `http://127.0.0.1:8765/api/oauth/{google|meta}/callback`. Google và Meta có các quy định khác nhau về HTTP loopback và loại OAuth client. Không bảo đảm Facebook Login chấp nhận mọi callback localhost HTTP trong mọi ứng dụng: **nên triển khai OAuth lên VPS HTTPS**. Không nhúng Meta App Secret vào ứng dụng phát cho máy của khách hàng; desktop local là thử nghiệm trên thiết bị do chủ ứng dụng kiểm soát.

## Bảo mật

- State 256-bit, lưu hash; ràng buộc với user, org, phiên đăng nhập; dùng một lần trong 10 phút. Google OAuth dùng PKCE S256.
- Cookie đăng nhập `SameSite=Lax` để callback từ Google/Meta có thể sử dụng phiên admin; các POST từ dashboard vẫn phải có CSRF token.
- Client secret chỉ đọc từ môi trường máy chủ; mã OAuth một lần trao đổi ở backend. Refresh token Google / Meta long-lived token được mã hóa AES-GCM bằng khóa của ứng dụng.
- API danh sách tài khoản và trạng thái **không trả token** ra trình duyệt. Khóa ở trạng thái chờ chỉ có tuổi thọ 10 phút; khi nhập tài khoản sẽ xóa.
- Google refresh token có thể bị thu hồi; Meta long-lived token cũng có thể hết hạn. Khi đó cần kết nối lại.
- Nếu tài khoản không trả tên hoặc tiền tệ do thiếu quyền, giao diện đánh dấu tiền tệ `XXX` (không đoán bừa VND/USD). Kiểm tra lại trước khi cộng báo cáo.

## Kiểm thử

```bash
pip install -r requirements.txt pytest
python -m pytest -q
node --check static/studio.js
```

Các bài kiểm thử OAuth mock provider HTTP và **không xác nhận quyền trên tài khoản quảng cáo thật**. Để hoàn thiện sản phẩm thương mại cần đăng ký ứng dụng đã duyệt, triển khai HTTPS, MFA, vòng đời token và kiểm thử quyền trên tài khoản thực tế.
