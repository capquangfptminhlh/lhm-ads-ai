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

4. Bước gửi đã được nối sẵn qua sổ bán hàng (xem mục "Xuất hóa đơn bằng
   lệnh `einvoice-issue`" bên dưới): adapter `issue_invoice` dựng + ký yêu
   cầu từ `build_create_request(order)` và gửi qua transport do sổ cung
   cấp; webhook (nếu nhà cung cấp hỗ trợ) phải qua
   `verify_webhook_signature` **trước** khi dùng `parse_webhook`, và chỉ
   trạng thái "đã phát hành" mới được ghi nhận. Trước lần xuất thật đầu
   tiên, đối chiếu lại **định dạng phản hồi** của nhà cung cấp đã ký (tên
   trường số hóa đơn/trạng thái) với tài liệu API của họ — adapter đọc
   theo các tên trường thông dụng và từ chối ghi nhận nếu phản hồi không
   có số hóa đơn.

## Xuất hóa đơn bằng lệnh `einvoice-issue`

Sau khi đơn đã ở trạng thái `paid` trong sổ (xem `payments` để lấy mã
đơn) và thông tin người mua đã có trên bản ghi đơn (các cột `buyer_name`,
`buyer_address`, và nếu có: `buyer_tax_code`, `buyer_email`):

```powershell
python tools/vendor_ledger.py einvoice-issue --order <mã đơn>
```

Hành vi của lệnh, theo đúng thứ tự cổng kiểm tra — mọi cổng đều **không
ghi gì vào sổ** khi chưa qua:

1. Đơn không tồn tại, hoặc đơn chưa ở trạng thái `paid` → báo lỗi rõ
   ràng và dừng. Không xuất hóa đơn cho đơn `pending`/`cancelled`/`failed`.
2. Đơn đã có số hóa đơn → báo lỗi "đã có hóa đơn", không gọi nhà cung cấp
   lần thứ hai. Hủy/thay thế hóa đơn phải làm qua nhà cung cấp.
3. Chưa cấu hình nhà cung cấp (thiếu biến môi trường ở bước 2 phần kích
   hoạt) → in đúng thông báo "chưa được kích hoạt" của adapter, thoát mã
   khác 0, **không ghi gì** — dormant nghĩa là dormant.
4. Thiếu thông tin người mua mà nhà cung cấp bắt buộc (`buyer_name`,
   `buyer_address`) → báo lỗi tiếng Việt liệt kê từng trường còn thiếu;
   bổ sung vào bản ghi đơn rồi chạy lại.
5. Đủ điều kiện: gửi yêu cầu đã ký tới địa chỉ trong `EINVOICE_API_BASE`,
   và chỉ khi nhà cung cấp trả về số hóa đơn mới ghi `invoice_no`,
   `invoice_series`, `invoice_issued_at` vào bản ghi đơn. Số tiền trên
   đơn trong sổ là **tổng khách đã trả (đã gồm VAT)**; lệnh tách phần
   trước VAT làm dòng hàng và adapter tự kiểm tra khớp tổng — lệch do
   làm tròn sẽ dừng lại thay vì xuất hóa đơn sai số tiền.

Xem lại hóa đơn đã ghi bằng lệnh `payments` (có thêm các cột
`invoice_no`, `invoice_series`, `invoice_issued_at`).

## Ranh giới cố ý giữ nguyên

- **Chỉ xuất sau khi tiền đã xác nhận** trong sổ bán hàng (quy tắc ở đầu
  tài liệu này). Không xuất hóa đơn "trước cho tiện", không xuất cho đơn
  `pending`.
- Khóa API hóa đơn nằm trên máy bên bán qua biến môi trường; không đưa vào
  repo, không gửi cho khách, không liên quan tới khóa ký license (hai hệ
  khóa hoàn toàn tách biệt).
- Module không tự gửi yêu cầu: việc truyền tải thật chỉ được nối khi đã có
  hợp đồng và làm theo đúng tài liệu của nhà cung cấp đã chọn.

## Còn thiếu

- (Tùy nhà cung cấp) máy chủ nhận webhook hóa đơn, tương tự
  `tools/payos_webhook_server.py` — hiện kết quả xuất hóa đơn được ghi
  từ phản hồi đồng bộ của lệnh `einvoice-issue`.
- Đối chiếu định dạng phản hồi thật của nhà cung cấp đã ký hợp đồng
  (không thể kiểm chứng khi chưa có hợp đồng — xem bước 4 ở trên).
- Cách nhập thông tin người mua vào bản ghi đơn ngay từ bước tạo đơn:
  hiện các cột `buyer_*` nằm trên bản ghi `payment_orders`; bên bán điền
  khi chốt đơn với khách.

Đã xong trong bản này: lệnh `einvoice-issue` trong
`tools/vendor_ledger.py` (cổng `paid`, chống xuất trùng, dormant không
ghi gì) và các cột lưu số hóa đơn/ký hiệu/thời điểm phát hành trên bản
ghi đơn (tự bổ sung vào sổ cũ khi mở sổ).
