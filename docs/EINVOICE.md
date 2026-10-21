# LHM Ads AI — Hóa đơn điện tử: vì sao đang chờ và cách kích hoạt

## Quy tắc bắt buộc (không đổi theo nhà cung cấp)

Hóa đơn điện tử chỉ được xuất cho đơn **đã được xác nhận thanh toán trong sổ
bán hàng** (`tools/vendor_ledger.py`): hoặc bên bán đã tự đối chiếu tiền
chuyển khoản về tài khoản của mình và chạy `confirm-payment`, hoặc đơn PayOS
đã ở trạng thái `paid` qua webhook đã xác minh chữ ký. Chưa xác nhận tiền →
không xuất hóa đơn, không có ngoại lệ. Việc xuất hóa đơn **không** thay đổi
quy trình cấp license: license vẫn do bên bán ký tay trên máy của mình sau
khi xác nhận tiền.

## Vì sao tích hợp đang TẮT (dormant)

Xuất hóa đơn điện tử có giá trị pháp lý tại Việt Nam bắt buộc phải qua một
**tổ chức cung cấp dịch vụ hóa đơn điện tử** đã ký hợp đồng với bên bán và
được cơ quan thuế chấp nhận (theo Nghị định 123/2020/NĐ-CP và Thông tư
78/2021/TT-BTC). Mỗi hợp đồng cấp bộ khóa API, mẫu số (template) và ký hiệu
(series) **riêng của bên bán** — không có khóa mặc định, không dùng chung
được, và không thể "bật thử" khi chưa có hợp đồng. Vì vậy code đã viết sẵn ở
dạng chờ (`tools/einvoice.py`): chưa cấu hình thì mọi thao tác đều báo rõ
"chưa được kích hoạt" và **không có yêu cầu nào được tạo hay gửi đi**.

Module này cố ý **không chứa bất kỳ địa chỉ máy chủ nhà cung cấp nào** và
**không tự gọi mạng**: nó chỉ dựng + kiểm tra + ký payload hóa đơn, và xác
minh/đọc webhook. Địa chỉ API lấy duy nhất từ biến môi trường của bên bán.

## Nhà cung cấp nào khớp với khuôn này

Payload trong `tools/einvoice.py` theo khuôn chung mà các nhà cung cấp lớn
đều hỗ trợ (tạo hóa đơn từ dữ liệu đơn hàng, ký số phía nhà cung cấp, trả số
hóa đơn qua API/webhook):

- **Viettel S-Invoice** — dịch vụ hóa đơn điện tử của Viettel; có API tích
  hợp cho phần mềm bán hàng, mẫu hóa đơn đăng ký theo doanh nghiệp.
- **VNPT Invoice** — dịch vụ hóa đơn điện tử của VNPT; hỗ trợ tích hợp API
  và nhiều mẫu/ký hiệu theo từng hợp đồng.
- **MISA meInvoice** — dịch vụ hóa đơn điện tử của MISA; có API cho đối tác
  phần mềm, quen thuộc với kế toán doanh nghiệp nhỏ.

Khi ký hợp đồng, đối chiếu lại tài liệu API của nhà cung cấp đã chọn: nếu
họ yêu cầu trường bổ sung (ví dụ mã cơ quan thuế, loại hóa đơn có mã/không
mã), bổ sung vào payload tại bước nối sổ (xem "Còn thiếu" ở cuối) — không
sửa logic kiểm tra tiền/tổng tiền.

## Kích hoạt khi đã có hợp đồng

1. Ký hợp đồng với một nhà cung cấp ở trên bằng pháp nhân của bên bán;
   đăng ký **mẫu số** và **ký hiệu** hóa đơn với cơ quan thuế qua nhà cung
   cấp; nhận **API Key / API Secret** và địa chỉ API chính thức.
2. Trên máy bên bán, đặt biến môi trường (không ghi vào repo, không gửi ai):

   ```powershell
   $env:EINVOICE_PROVIDER = '<tên nhà cung cấp đã ký>'
   $env:EINVOICE_API_BASE = '<địa chỉ API nhà cung cấp cấp>'
   $env:EINVOICE_API_KEY = '<api key>'
   $env:EINVOICE_API_SECRET = '<api secret>'
   $env:EINVOICE_TEMPLATE_CODE = '<mẫu số đã đăng ký>'
   $env:EINVOICE_SERIES = '<ký hiệu đã đăng ký>'
   ```

3. Tự kiểm tra cấu hình và payload bằng Python (không gửi đi đâu):

   ```powershell
   python -c "from tools import einvoice; print(einvoice.is_configured())"
   ```

   In `True` là đủ điều kiện dựng payload. Dựng thử một hóa đơn từ đơn đã
   xác nhận để xem payload và chữ ký trước khi nối bước gửi thật.

4. Khi nối bước gửi (lập trình viên thực hiện theo tài liệu nhà cung cấp):
   dùng `build_create_request(order)` để lấy method/URL/headers/body đã ký,
   gửi bằng kênh nhà cung cấp yêu cầu, và ghi lại kết quả; webhook (nếu nhà
   cung cấp hỗ trợ) phải qua `verify_webhook_signature` **trước** khi dùng
   `parse_webhook`, và chỉ trạng thái "đã phát hành" mới được ghi nhận.

## Ranh giới cố ý giữ nguyên

- **Chỉ xuất sau khi tiền đã xác nhận** trong sổ bán hàng (quy tắc ở đầu
  tài liệu này). Không xuất hóa đơn "trước cho tiện", không xuất cho đơn
  `pending`.
- Khóa API hóa đơn nằm trên máy bên bán qua biến môi trường; không đưa vào
  repo, không gửi cho khách, không liên quan tới khóa ký license (hai hệ
  khóa hoàn toàn tách biệt).
- Module không tự gửi yêu cầu: việc truyền tải thật chỉ được nối khi đã có
  hợp đồng và làm theo đúng tài liệu của nhà cung cấp đã chọn.

## Còn thiếu (việc nối sổ — chưa làm trong bản này)

- Lệnh trong `tools/vendor_ledger.py` để xuất hóa đơn cho một đơn đã
  `confirm-payment`/`paid` và ghi lại số hóa đơn vào sổ.
- Cột/trạng thái lưu số hóa đơn đã phát hành theo đơn trong sổ bán hàng.
- (Tùy nhà cung cấp) máy chủ nhận webhook hóa đơn, tương tự
  `tools/payos_webhook_server.py`.
