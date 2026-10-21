# LHM Ads AI — Vận hành thuê bao trên máy bên bán

Đây là công cụ **quản lý bản quyền ngoại tuyến**. Không phải cổng thanh toán, không phải máy chủ giữ token Google/Meta, và không được đóng gói vào file EXE của khách. Công cụ nằm tại `tools/vendor_ledger.py`, sử dụng Python 3.12, SQLite, `cryptography`.

## Mô hình

- Một mã khách nội bộ (`KH001`, `SHOP-01`) gắn với **một Device ID**. Mỗi thiết bị khác cần đăng ký mã khách khác; không lưu email, tên thật hoặc tài khoản Ads trong sổ này.
- Một khách có thể có nhiều license gia hạn. Sổ chỉ hiển thị license có hạn cuối xa nhất; các giao dịch cũ giữ nguyên để kiểm tra.
- License JSON luôn được **xác minh chữ ký bằng public key của bên bán** trước khi ghi nhận. File giả, sai máy, sai sản phẩm bị từ chối.
- Trạng thái thanh toán `pending` là mặc định. `confirmed` yêu cầu mã tham chiếu do nhân viên **tự xác minh giao dịch ở bên ngoài**. `trial` dành cho license dùng thử; không tự coi là đã trả tiền.
- Dữ liệu lưu riêng tại `%LOCALAPPDATA%\LHMAdsAI-Vendor\customers.sqlite3` (Windows), không dùng chung database của khách, không đồng bộ lên GitHub. Sao lưu file khi ứng dụng đã đóng, vào ổ lưu mã hóa; bảo vệ tài khoản Windows.

## Cách dùng thực tế

Chạy từ thư mục gốc repo trên **máy bên bán**, sau khi đã tự tạo bộ khóa riêng theo `docs/COMMERCIAL_LICENSE.md`.

**1. Đăng ký khách nhận Mã máy từ phần mềm (không nhận token quảng cáo).**

```powershell
python tools/vendor_ledger.py register --customer KH001 --device 0123456789abcdef0123456789abcdef
```

**2. Sau khi đã xác minh tiền về, cấp license trên chính máy có private key.**

```powershell
python tools/license_issuer.py sign --private C:\LHMKeys\vendor-private-key.pem --expected-public C:\LHMKeys\vendor-public.b64 --device 0123456789abcdef0123456789abcdef --days 30 --plan monthly --out KH001-2026-11.json
```

Lệnh trên hỏi mật khẩu private key. Không ghi mật khẩu hoặc khóa ký vào câu lệnh, lịch sử PowerShell, GitHub, file CSV, ứng dụng bên thứ ba.

**3. Ghi nhận file license đã ký cùng mã biên nhận.**

```powershell
python tools/vendor_ledger.py record --customer KH001 --license KH001-2026-11.json --public C:\LHMKeys\vendor-public.b64 --payment-status confirmed --receipt TT-KH001-001
```

Mã biên nhận là chuỗi quản lý nội bộ, **không nhập số tài khoản ngân hàng, số thẻ, thông tin cá nhân hoặc token Ads**. Nếu chưa xác minh giao dịch, bỏ `--payment-status confirmed --receipt ...` để lưu `pending`.

**4. Theo dõi khách sắp hết hạn và đối chiếu thanh toán.**

```powershell
python tools/vendor_ledger.py list
python tools/vendor_ledger.py due --within-days 7
python tools/vendor_ledger.py export --out danh-sach-gia-han.csv
```

Nếu lúc đầu đã lưu `pending`, sau khi nhân viên đối chiếu ngân hàng thành công có thể dùng:

```powershell
python tools/vendor_ledger.py confirm-payment --license-id <LICENSE_ID> --receipt TT-KH001-001
```

**5. Gia hạn sớm:** sử dụng `license_issuer.py sign --renew-from KH001-2026-11.json`, rồi ghi nhận JSON mới bằng `vendor_ledger.py record`. Không ghi đè file license cũ. Sổ sẽ từ chối bản gia hạn có hạn cuối thấp hơn hồ sơ đã ghi.

## Ranh giới chưa triển khai

- Công cụ **không kiểm tra số dư ngân hàng** hoặc thu phí tự động, không phát hành hóa đơn điện tử, không nhắc Zalo/SMS tự động tới khách. Lệnh `remind` (mục 7) chỉ gửi nhắc tới Telegram của chính bên bán.
- Public key chỉ xác minh nguồn phát hành license; **không thay thế** chữ ký Authenticode của EXE.
- Chỉ nên giao bản Commercial sau khi có bản EXE đã ký số, thử nghiệm với API thật và đối chiếu giấy phép qua từng bước. Artifact của GitHub hiện chưa phải bản cài đặt phát hành đại trà.
**7. Nhắc gia hạn cho chính bên bán.** Liệt kê khách đã hết hạn hoặc sắp hết hạn (mặc định 7 ngày):

```powershell
python tools/vendor_ledger.py remind --within-days 7
```

Muốn nhận danh sách này qua Telegram của bên bán, đặt hai biến môi trường trên máy bên bán rồi thêm `--send`:

```powershell
$env:VENDOR_TELEGRAM_BOT_TOKEN = '<bot token của bên bán>'
$env:VENDOR_TELEGRAM_CHAT_ID = '<chat id của bên bán>'
python tools/vendor_ledger.py remind --within-days 7 --send
```

Tin nhắn chỉ chứa mã khách nội bộ, gói, số ngày còn lại và trạng thái thanh toán — không chứa token Ads hay thông tin ngân hàng. Có thể đặt lệnh này vào Task Scheduler chạy hằng ngày.

**6. Sao lưu sổ khách hàng nhất quán**, sau đó chuyển bản sao lưu vào kho lưu trữ mã hóa bên bán (không gửi lên repo):

```powershell
python tools/vendor_ledger.py backup --out C:\\LHMKeys\\customers-backup-2026-10.sqlite3
```

Không ghi đè các bản sao lưu cũ. Đường dẫn thư mục đích phải tồn tại. Không dùng tùy chọn `--db` trỏ vào thư mục chia sẻ không an toàn, và không đặt dữ liệu bên bán trong repo.
