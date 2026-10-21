# Nhật ký thay đổi — LHM Ads AI

Định dạng theo [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
phiên bản theo [Semantic Versioning](https://semver.org/lang/vi/).

**Phiên bản đang khai báo trong mã nguồn: 0.3** — "Private Studio 0.3"
(trang đầu `README.md` và `docs/STUDIO.md`). Hiện chưa có hằng số phiên bản
trong code, không có git tag; mọi ghi chú dưới đây thuộc mục *Chưa phát
hành* cho đến khi chủ phần mềm quyết định số phiên bản kế tiếp và cập nhật
đồng thời cả hai nơi khai báo trên (xem `docs/RELEASE_CHECKLIST.md`).

## [Chưa phát hành]

Các thay đổi đã hợp nhất vào `main` ngày 2026-10-21, chuẩn bị cho bản
thương mại đầu tiên. Trạng thái nghiệm thu trực tiếp (live acceptance):
**Google Ads — NOT_RUN; Meta Ads — NOT_RUN** (chưa chạy với tài khoản thật;
xem `docs/ACCEPTANCE.md`).

### Đã thêm

- **Xác thực hai lớp TOTP (MFA) tùy chọn cho từng người dùng** (PR #6):
  khóa bí mật được mã hóa AES-GCM; tắt MFA bắt buộc nhập lại mật khẩu kèm
  mã hợp lệ; màn hình đăng nhập Studio có ô nhập mã MFA.
- **Nhắc gia hạn cho bên bán** (PR #6): lệnh `vendor_ledger.py remind`
  liệt kê bản quyền đã hết hạn/sắp hết hạn, tùy chọn gửi một tin Telegram
  về chat của chính người bán.
- **Tích hợp PayOS ở trạng thái chờ (dormant)** (PR #7): `tools/payos.py`
  (ký HMAC-SHA256, kiểm chứng webhook), lệnh sổ bán hàng `payos-status`,
  `payos-create`, `payments` và máy chủ webhook `tools/payos_webhook_server.py`.
  Chưa có khóa merchant thì không tạo được gì; webhook chỉ đánh dấu *đã
  thanh toán*, **không bao giờ tự cấp bản quyền** — quy trình mặc định vẫn
  là khách chuyển khoản vào tài khoản của chủ phần mềm, chủ xác nhận nhận
  tiền rồi mới kích hoạt. Hướng dẫn: `docs/PAYOS.md`.
- **Font Inter đóng gói kèm phần mềm** (PR #9): font biến đổi (độ đậm
  100–900; subset Latin, Latin mở rộng và tiếng Việt) nhúng trong
  `static/fonts.css`, giấy phép SIL OFL tại `static/fonts/LICENSE-Inter.txt`.
  Trước đây máy Windows không có sẵn Inter nên giao diện lặng lẽ rơi về
  Segoe UI, mỗi máy hiển thị một khác.
- **Hiệu ứng chuyển động cho trang đăng nhập và các panel** (PR #9):
  màn hình đăng nhập xuất hiện mềm theo nhịp; mọi panel trong các trang
  làm việc dùng hiệu ứng vào `fp-card-arrive`; tôn trọng chế độ giảm
  chuyển động của hệ điều hành.

### Đã thay đổi

- **Giới hạn đăng nhập bền vững trong SQLite** (PR #6): 5 lần sai theo
  email, 20 lần theo IP trong 15 phút — thay cho bộ đếm trong bộ nhớ của
  từng tiến trình (khởi động lại là mất).
- **Tổng hợp dữ liệu gửi OpenRouter đầy đủ hơn** (PR #5): payload nay gồm
  chuyển đổi, giá trị chuyển đổi, CPA và ROAS, chỉ tính từ các nhóm dữ
  liệu đầy đủ; thiếu dữ liệu thì ghi *chưa rõ*, không điền 0.
- **Cảnh báo giám sát và tư vấn tới được người vận hành** (PR #5): ngoài
  hiển thị trong app, cảnh báo lỗi nhà cung cấp và phát hiện mới của bộ
  tư vấn được gửi thêm tới Telegram của người vận hành (gộp theo nhịp
  chống spam; chỉ gửi mã lỗi và số tài khoản nội bộ).

### Đã sửa

- **Tài liệu mô tả sai khả năng thực tế** (PR #5): bảng nhà cung cấp trong
  README (Google Ads có thao tác tạm dừng/ngân sách qua phê duyệt, không
  phải "chỉ đọc"), mâu thuẫn về AI bên ngoài, và mục 0 của đặc tả 24/7 đã
  viết lại đúng với code hiện tại — giám sát là tác nhân nền trên máy
  khách, chỉ đọc, và mọi thay đổi quảng cáo đều cần người phê duyệt.
- **Sáu lỗi giao diện từ đợt rà soát bằng ảnh chụp** (PR #8):
  - Nguyên nhân gốc: CSP `style-src 'self'` của chính app chặn các style
    nội tuyến do JS tự phát ra — toàn bộ đã chuyển sang class CSS, trang
    Bản quyền hết vỡ bố cục, nhãn và ô dán giấy phép xếp dọc đầy đủ.
  - Trang Bản quyền không còn in lỗi đỏ "Cần đăng nhập tài khoản nội bộ"
    cho người đã đăng nhập.
  - Ô tích chọn đồng ý OpenRouter gắn liền với nhãn của nó.
  - Ô chọn tài khoản ở trang Chiến dịch có trạng thái trống rõ ràng, khóa
    nút phân tích và hướng dẫn nơi kết nối tài khoản trước.
  - Hai nhãn trạng thái trùng nhau ở Tổng quan đã gộp/tách nghĩa rõ ràng.
  - Bỏ vệt mờ cam ở góc thẻ KPI; logo đăng nhập bản mobile về đúng màu
    cam thương hiệu.

### Bảo mật

- MFA TOTP và giới hạn đăng nhập bền vững (xem trên) thu hẹp hai khoảng
  trống đã ghi nhận trong đợt kiểm toán bảo mật 2026-10-21.
- CSP chỉ nới đúng một điểm cho font đóng gói: `font-src 'self' data:`.

## [0.3]

Bản "Private Studio 0.3" đang khai báo trong `README.md`/`docs/STUDIO.md`:
dashboard phân tích chỉ đọc cho Meta/Google Ads, tạm dừng chiến dịch qua
phê duyệt quản trị, phân tích nội bộ tại máy (tùy chọn OpenRouter khi
quản trị bật), bản quyền ngoại tuyến ký Ed25519 theo máy, sổ bán hàng
ngoại tuyến cho bên bán. MCP đã bị loại bỏ hoàn toàn từ trước bản này vì
lý do bảo mật (các route `/mcp` trả 404 và có test khóa).
