# LHM Ads AI — Thu tiền: quy trình hiện tại và tích hợp PayOS (chờ kích hoạt)

## Quy trình ĐANG DÙNG (mặc định)

Quyết định của chủ phần mềm (21/10/2026): hiện tại khách thanh toán bằng
**chuyển khoản vào tài khoản ngân hàng của chính bên bán**. Bên bán **tự xác
nhận tiền đã về** rồi mới ký và cấp license, đúng quy trình trong
[VENDOR_OPERATIONS.md](VENDOR_OPERATIONS.md) (`record`/`confirm-payment` chỉ
sau khi đối chiếu ngân hàng). Không có bước nào trong quy trình này tự động
kích hoạt khi chưa có xác nhận của người bán.

## PayOS — đã tích hợp sẵn, đang TẮT

Code tích hợp PayOS đã có trong repo (`tools/payos.py`,
`tools/payos_webhook_server.py`, các lệnh `payos-*` trong
`tools/vendor_ledger.py`) nhưng **chỉ hoạt động khi bên bán cấu hình khóa
merchant của chính mình**. Chưa có khóa thì mọi lệnh PayOS đều báo rõ "chưa
được kích hoạt" và quy trình thủ công ở trên vẫn là đường duy nhất — không có
khóa mặc định, không có khóa dùng chung, không gửi tiền qua tài khoản lạ.

### Kích hoạt khi đã có tài khoản merchant PayOS

1. Đăng ký merchant tại payos.vn bằng pháp nhân/tài khoản ngân hàng của bên
   bán; lấy **Client ID**, **API Key**, **Checksum Key** trong dashboard.
2. Trên máy bên bán, đặt biến môi trường (không ghi vào repo, không gửi ai):

   ```powershell
   $env:PAYOS_CLIENT_ID = '<client id>'
   $env:PAYOS_API_KEY = '<api key>'
   $env:PAYOS_CHECKSUM_KEY = '<checksum key>'
   $env:PAYOS_RETURN_URL = 'https://<miền-của-bạn>/payos/return'
   $env:PAYOS_CANCEL_URL = 'https://<miền-của-bạn>/payos/cancel'
   ```

3. Kiểm tra trạng thái (không in bí mật):

   ```powershell
   python tools/vendor_ledger.py payos-status
   ```

4. Tạo link thanh toán cho khách đã đăng ký mã máy:

   ```powershell
   python tools/vendor_ledger.py payos-create --customer KH001 --amount 299000
   ```

   Lệnh in ra `checkout_url` để gửi khách; đơn được ghi vào sổ với trạng
   thái `pending`.

5. Chạy máy chủ webhook sau HTTPS (reverse proxy/tunnel) và khai báo URL
   `https://<miền-của-bạn>/payos/webhook` trong dashboard PayOS:

   ```powershell
   $env:PAYOS_CHECKSUM_KEY = '<checksum key>'
   python tools/payos_webhook_server.py --port 8899
   ```

   Webhook được **xác minh chữ ký HMAC-SHA256** và đối chiếu số tiền với đơn
   đã ghi; đạt thì đơn chuyển `paid` (xem bằng lệnh `payments`). Trang
   return/cancel chỉ là trang thông tin — không bao giờ tự xác nhận thanh
   toán.

### Ranh giới cố ý giữ nguyên

- Webhook PayOS **chỉ đánh dấu đơn đã trả tiền**. Việc ký license vẫn do bên
  bán thực hiện trên máy ngoại tuyến sau khi thấy đơn `paid` — giống hệt xác
  nhận chuyển khoản tay. Khóa ký riêng **không** đưa lên máy chủ webhook.
- Muốn cấp license hoàn toàn tự động ngay khi tiền về là một quyết định kiến
  trúc khác (phải đặt khóa ký trên máy chủ trực tuyến) — chưa làm và cần chủ
  phần mềm quyết định riêng.
- Hóa đơn điện tử vẫn chưa tích hợp (cần hợp đồng nhà cung cấp hóa đơn riêng).
