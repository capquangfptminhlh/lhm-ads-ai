# Kết nối Google Ads / Meta Ads với LHM Ads AI — API trực tiếp và MCP (23/10/2026)

> **Phân biệt:** Bản Windows LHM Ads AI hiện có luồng **OAuth / Marketing API trực tiếp**. MCP **chưa được tích hợp** vào backend LHM Ads AI (các endpoint MCP cũ đã bị vô hiệu hóa có chủ đích). Hướng dẫn MCP dưới đây dùng **AI client hỗ trợ MCP** riêng, không phải khẳng định đã có nút MCP hoạt động trong EXE.

## 1. Google Ads — kết nối trực tiếp LHM Ads AI (nên dùng trước)

### Chuẩn bị
- Đăng nhập Google đang có quyền ít nhất **đọc** tài khoản Google Ads mục tiêu; nếu quản lý nhiều khách hàng có thể liên kết tài khoản qua Google Ads Manager (MCC).
- Vào https://console.cloud.google.com/ chọn hoặc tạo một dự án do bạn kiểm soát.
- Tại **APIs & Services → Library**, bật **Google Ads API**.
- Trên trang **Google Ads API Overview** của chính dự án trong Google Cloud, kiểm tra quyền: **Test** chỉ dùng tài khoản thử nghiệm; muốn đọc tài khoản thật, xin **Explorer** (hoặc Basic/Standard) cho dự án. https://developers.google.com/google-ads/api/docs/api-policy/access-levels
- **Cập nhật chính sách 09/09/2026:** developer token Google Ads API đã sunset. Không cần xin token ở API Center nữa; legacy header được bỏ qua. Quyền gắn với **Google Cloud project**. Tham khảo https://developers.google.com/google-ads/api/docs/api-policy/developer-token (có thể còn trang tài liệu cũ nói token bắt buộc).
- Vào **Google Auth Platform / OAuth consent screen**: điền tên ứng dụng, email hỗ trợ, nhóm Audience. Thêm **scope** `https://www.googleapis.com/auth/adwords`. Nếu đang ở trạng thái Testing, thêm email của chính bạn vào **Test users**. Với sản phẩm bán cho nhiều khách hàng phải thực hiện xác minh thương hiệu/ứng dụng khi Google yêu cầu.
- Vào **APIs & Services → Credentials → Create credentials → OAuth client ID → Desktop app**. Tải file JSON. File hợp lệ có khóa `installed` với `client_id` và (khi được cấp) `client_secret`. Không dùng **Service Account JSON** (`type: service_account`) thay vào biểu mẫu Desktop OAuth.

### Thao tác trong EXE
1. Mở **LHM Ads AI → Tài khoản Ads → Google Ads → Cấu hình Google OAuth** (hoặc **Cài đặt → Trợ lý kết nối → Google Ads**).
2. Xem Bước 1, vào Bước 2 và bấm **Chọn file JSON trên máy**. Trình hướng dẫn chỉ **điền** Client ID/Secret, chưa tự lưu.
3. Vào Bước 3, bấm **Lưu ứng dụng Google trên máy**. Thông tin được lưu trong kho dữ liệu mã hóa tại máy. Nếu đã nhập thủ công, kiểm tra Client ID kết thúc bằng `.apps.googleusercontent.com`.
4. Vào Bước 4 → **Đến nút đăng nhập Google Ads**. Cửa sổ đăng nhập **trình duyệt hệ thống** mở, không nhập mật khẩu trong LHM Ads AI. Chọn đúng email có quyền, xác nhận OAuth.
5. Sau khi callback thành công, **chọn tài khoản Google Ads** từ danh sách. Với MCC chọn đúng tài khoản con; kiểm tra `customer_id` 10 chữ số. LHM Ads AI hỗ trợ lưu `login_customer_id` khi đi qua MCC.
6. Bấm **Kiểm tra API** của từng tài khoản; xác nhận thấy số liệu Ads thực, đúng đơn vị tiền, ngày. Không coi dữ liệu Demo là xác nhận quyền thực.

### Nếu lỗi
- `CLOUD_PROJECT_NOT_APPROVED_FOR_PRODUCTION`: dự án còn quyền Test → nâng lên Explorer/Basic/Standard ở Google Cloud.
- `access_denied`, `403`: email chưa có quyền Ads, chưa là Test user, chưa chấp thuận OAuth, hoặc app chưa được xác minh.
- `redirect_uri_mismatch`: bảo đảm tạo **Desktop app** đúng, không lấy Client ID Web application.
- Có OAuth nhưng không thấy tài khoản: kiểm tra email thực tế đã đăng nhập, quyền trên Ads/MCC, account ID.
- Có tài khoản nhưng không đọc báo cáo: kiểm tra API access level, trạng thái tài khoản, quyền API và phiên bản Google Ads API.

Nguồn chính thức: https://developers.google.com/google-ads/api/docs/get-started/make-first-call và https://developers.google.com/google-ads/api/docs/oauth/overview

## 2. Meta/Facebook Ads — kết nối trực tiếp LHM Ads AI

### Chuẩn bị
- Có tài khoản Facebook được cấp quyền cho ad account / Business Portfolio cần quản lý. Mở https://business.facebook.com/settings kiểm tra quyền.
- Vào https://developers.facebook.com/apps/, tạo **Meta App** phù hợp với Marketing API/Facebook Login, liên kết Business Portfolio khi yêu cầu.
- Trong **App settings → Basic**, lấy **App ID** và **App Secret**.
- Cấp quyền phù hợp: **`ads_read`** để đọc báo cáo; **`ads_management`** khi cần quản lý/ghi; **`business_management`** chỉ nếu luồng thực sự đòi quyền Business. Quyền phát hành cho người dùng ngoài vai trò phát triển có thể phải qua **App Review, Business Verification và Advanced Access** theo Meta.
- Thiết lập Facebook Login và **Valid OAuth Redirect URIs**. Trình hướng dẫn LHM Ads AI hiển thị callback cụ thể của **máy đang chạy**. Meta có thể không cho HTTP localhost đối với app Live; không có cơ chế bỏ qua HTTPS/App Review.

### Thao tác trong EXE
1. **Tài khoản Ads → Meta Ads → Cấu hình Meta App** (hoặc **Cài đặt → Trợ lý kết nối → Meta**).
2. Bước 1: kiểm tra yêu cầu về Business/App và **Sao chép Redirect URI** từ ứng dụng để khai báo nếu Meta chấp nhận.
3. Bước 2: nhập App ID và App Secret **trong phần mềm**, không gửi qua chat.
4. Bước 3: lưu cấu hình; Bước 4: chuyển về **Tài khoản Ads → Đăng nhập Meta Ads** trong **trình duyệt hệ thống** và chấp thuận quyền.
5. Chọn tài khoản quảng cáo muốn thêm, bấm **Kiểm tra API** để chắc chắn có dữ liệu thật. ID ad account Meta thường được biểu diễn với tiền tố `act_`.

### Phương án token Marketing API
Nếu OAuth localhost không được chấp nhận:
- Sử dụng luồng **nhập Access Token Meta nâng cao** có sẵn trong phần mềm. Tạo token thuộc app/business hợp lệ (Graph API Explorer hoặc System User trong Business Settings theo use case). Đọc quyền trên token và thời hạn trong Access Token Debugger.
- Chỉ nhập token của **tài khoản bạn có quyền**; cấp `ads_read` khi chỉ xem báo cáo. Token ngắn hạn không phù hợp chạy liên tục; nếu cần xử lý máy chủ, dùng system user token được cấp đúng quyền và có quy trình xoay vòng/thu hồi.
- Không nhập mật khẩu Facebook vào phần mềm, không đăng token lên GitHub/Zalo/chat.

Nguồn Meta: https://developers.facebook.com/documentation/ads-commerce/marketing-api ; https://developers.facebook.com/documentation/development/permissions

## 3. MCP Google Ads (dùng trong AI client, KHÔNG phải kết nối API của EXE)

Google cung cấp dự án **google-ads-mcp** chính thức, bản hiện tại **chỉ đọc dữ liệu** (không đổi budget, pause hay sửa bids). Để cài trên máy có Python và `pipx`:

1. Chuẩn bị Google Cloud project có Explorer access trở lên và OAuth/ADC hợp lệ với email có quyền Ads.
2. Thiết lập Google Application Default Credentials. Để thử trên máy cá nhân, có thể dùng `gcloud auth application-default login` theo hướng dẫn Google; tài khoản phải cấp scope phù hợp. Không dán credential JSON vào file cấu hình chia sẻ.
3. Trong **AI client hỗ trợ MCP stdio** đặt cấu hình mẫu (tên file tùy client):

```json
{
  "mcpServers": {
    "google-ads-mcp": {
      "command": "pipx",
      "args": ["run", "--spec", "git+https://github.com/googleads/google-ads-mcp.git", "google-ads-mcp"],
      "env": {
        "GOOGLE_PROJECT_ID": "YOUR_PROJECT_ID",
        "GOOGLE_APPLICATION_CREDENTIALS": "C:/private/google-application-credentials.json"
      }
    }
  }
}
```

Nếu cần dùng MCC, cấu hình thêm `GOOGLE_ADS_LOGIN_CUSTOMER_ID` (ID số không dấu gạch). Ví dụ hỏi: *“Liệt kê tài khoản Google Ads tôi có quyền”, “So sánh chi phí/CPL trong 7 ngày”*.

Tham khảo đầy đủ, kể cả triển khai Cloud Run với OAuth: https://developers.google.com/google-ads/api/docs/developer-toolkit/mcp-server . **Không triển khai HTTP MCP công khai không có OAuth**.

## 4. MCP Meta Ads

Meta hiện cung cấp **Ads MCP Server / Ads AI Connectors** chính thức cho AI client đủ điều kiện. Tài liệu: https://developers.facebook.com/ads-mcp-server và https://www.facebook.com/meta-ads-ai-connectors .

- Chọn công cụ AI có hỗ trợ Meta Ads connector/MCP; trong trang kết nối của công cụ, sử dụng connector do Meta cung cấp, **đăng nhập Facebook tại trang chính thức** và chọn tài khoản/Business được cấp phép.
- Kiểm tra quyền được yêu cầu; với công cụ có khả năng sửa quảng cáo, chỉ cấp/cho phép hành động ghi khi thật sự cần và thiết lập phê duyệt trước khi thực thi.
- LHM Ads AI **không có nút MCP Meta tích hợp**; màn hình Google/Meta trong EXE vẫn là API trực tiếp. Không nhập token Meta vào URL MCP lạ hoặc cho AI bên thứ ba quản lý trực tiếp khi chưa xác minh nhà cung cấp.

## 5. Nên lựa chọn như thế nào?

- Muốn **LHM Ads AI theo dõi nhiều tài khoản, dashboard 24/7, báo cáo định kỳ và hoạt động local-only** → ưu tiên **API trực tiếp**; token lưu mã hóa riêng theo tài khoản.
- Muốn hỏi AI *“Vì sao CPC tăng, tài khoản nào kém nhất?”* qua giao diện chatbot → có thể dùng **Google/Meta MCP chính thức** trong AI client bên ngoài, read-only trước, tránh đưa token vào mô hình.
- Muốn cho AI **thay ngân sách/giá thầu** → không nhầm MCP Google hiện tại với API ghi; cần tích hợp API ghi riêng, quyền đúng, nhật ký và **phê duyệt thủ công**. MCP không tự cấp thêm quyền.

**Không cần gửi thông tin nhạy cảm cho người hỗ trợ:** chỉ gửi trạng thái của màn hình, mã lỗi đã che token, tên bước bị lỗi; giữ Client Secret, Refresh Token, Access Token, tài khoản và mật khẩu ở máy.
