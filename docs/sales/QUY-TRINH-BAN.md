# Quy trình bán LHM Ads AI — Sổ tay bên bán (Pilot)

Tài liệu nội bộ cho bên bán, mô tả trọn vẹn một vòng bán hàng: tư vấn → khách lấy mã máy → chuyển khoản → bên bán tự xác nhận tiền về → ký license → ghi sổ → giao khách kích hoạt → nhắc gia hạn.

Mô hình thu tiền hiện tại (chủ sản phẩm đã chốt): **khách chuyển khoản vào tài khoản của chính bên bán, bên bán tự kiểm tra tiền về rồi mới ký và kích hoạt license**. Phần mềm **không** tự xác nhận giao dịch ngân hàng, **không** tự thu tiền, **không** thu hồi license từ xa. PayOS đã tích hợp sẵn nhưng đang tắt — chỉ dùng khi chủ sản phẩm có khóa merchant và quyết định bật (xem `docs/PAYOS.md`); kể cả khi bật, webhook PayOS cũng chỉ đánh dấu đơn đã trả tiền, việc ký license vẫn làm tay theo quy trình này.

Các lệnh dưới đây chạy từ thư mục gốc repo trên **máy riêng của bên bán** (máy giữ khóa ký). Không chạy trên máy khách, không đưa `tools/vendor_ledger.py` vào bản EXE gửi khách.

---

## Điểm khác biệt khi tư vấn — LHM Vòng lặp Tối ưu (tính năng đã có trong bản bán)

Phần này dùng khi khách hỏi "khác gì công cụ miễn phí / gợi ý sẵn của nền tảng". Mọi ý dưới đây đều kiểm chứng được trong `docs/OPTIMIZATION_SKILL.md` — chỉ nói đúng ngần này:

- **Tư vấn tối ưu 16 quy tắc, chỉ đọc — không tự sửa quảng cáo.** Playbook phân tích số liệu 7 ngày cấp chiến dịch (chi tiêu, CPA, ROAS...) và đưa đề xuất kèm lý do, bước xử lý và rào chắn. Mọi thay đổi thật do khách tự duyệt và thực hiện trong Google Ads / Meta Ads Manager; phần mềm không tự ghi thay đổi nào vào tài khoản quảng cáo.
- **Hồ sơ nền riêng từng tài khoản.** Phần mềm lưu các kỳ quét và tính CPA/ROAS trung vị của chính từng chiến dịch, nên báo được "chiến dịch này đang xấu đi so với chính nó" — điều mà ngưỡng chung toàn ngành không bắt được.
- **Vòng kiểm chứng kết quả.** Đề xuất được đo lại ở các kỳ quét sau (từ 7 ngày) và nhận phán quyết: cải thiện / xấu đi / không đổi / chưa đủ dữ liệu (biến động ±5% coi là nhiễu). Bán điểm này như "khách nhìn thấy đề xuất nào từng đi kèm cải thiện trên chính tài khoản của mình", **không** bán như cam kết kết quả.
- **Chống tự mâu thuẫn.** Một lần quét không bao giờ vừa khuyên mở rộng vừa khuyên cắt giảm cùng một chiến dịch; gợi ý mở rộng bị chặn khi có cảnh báo cắt giảm, và mã bị chặn được ghi lại.
- **So với target thật trên nền tảng.** Phần mềm đọc target tCPA/tROAS và cấu hình giá thầu khách đã đặt trên Google/Meta, so hiệu quả thực tế với chính các con số đó — kể cả khi khách chưa đặt mục tiêu trong phần mềm.
- **Rào chắn là một phần của sản phẩm:** mọi đề xuất chỉnh tối đa 20%/bước, một biến mỗi lần, kiểm tra tracking trước, tôn trọng pha học, người duyệt mọi thay đổi.

**Giá để neo khi tư vấn:** gói **Pilot 499.000 đ / 30 ngày / 1 máy** (đã chốt 2026-10-22; kỳ hạn dài và giá niêm yết sau pilot xem `BANG-GIA-MAU.md` — không tự sửa con số ở bất kỳ đâu).

**Tuyệt đối không nói khi tư vấn tính năng này:**

- Không hứa tăng ROAS, giảm CPA hay bất kỳ kết quả quảng cáo nào; không nêu phần trăm hiệu quả — phần mềm không đo và không đảm bảo được những điều đó.
- Không chê bai, so sánh hạ thấp công cụ của đối thủ hay của nền tảng; chỉ nêu cơ chế của mình (các chiến thuật tối ưu là kiến thức chung của ngành, điểm khác là cơ chế chạy trên dữ liệu riêng của khách).
- Không dùng ngôn ngữ "an toàn tuyệt đối", "không bao giờ bị khóa tài khoản", "đảm bảo sạch" — phần mềm không can thiệp được các quyết định của nền tảng.
- Không nói phần mềm "tự động tối ưu" — nó tư vấn; khách là người duyệt và thực hiện thay đổi.

## Chuẩn bị một lần (trước khách đầu tiên)

1. Tạo bộ khóa phát hành theo `docs/COMMERCIAL_LICENSE.md` bước 1 (`license_issuer.py keygen`), sao lưu khóa riêng ở hai nơi tách biệt. **Không thay bộ khóa sau khi đã bán**, nếu không license mới sẽ không khớp bản EXE đã phát hành.
2. Build bản COMMERCIAL theo `docs/COMMERCIAL_LICENSE.md` bước 2 và tự kiểm tra trên một máy Windows sạch: cài đặt, mở phần mềm, đọc được Mã máy ở trang **Bản quyền**.
3. Điền các mẫu trong `MAU-TIN-NHAN.md`: thông tin chuyển khoản, cú pháp nội dung chuyển tiền, giá gói (xem `BANG-GIA-MAU.md`).
4. Quyết định các mục còn để trống trong `FAQ-KHACH-HANG.md` (hạn kích hoạt sau khi nhận tiền, chính sách hoàn tiền, số lần đổi máy miễn phí...). Các mục này đều ghi `[CHU SAN PHAM QUYET DINH]` — chốt xong mới gửi FAQ cho khách.

---

## Bước 1 — Tư vấn và gửi báo giá

**Gửi cho khách:** mẫu tin nhắn số 1 trong `MAU-TIN-NHAN.md` (báo giá + hướng dẫn lấy mã máy), kèm bản COMMERCIAL đã được nghiệm thu, kiểm tra manifest và công bố rõ trạng thái ký số Windows [CHU SAN PHAM QUYET DINH: kênh gửi file cài đặt — link tải / gửi trực tiếp qua Zalo].

**Nói đúng khả năng phần mềm, không hứaเกิน:**

- Phần mềm chạy trên máy của khách, dữ liệu quảng cáo và token ở lại máy khách, không gửi về máy chủ của bên bán.
- Giám sát nền chỉ **đọc** báo cáo qua API, và chỉ hoạt động **khi máy khách đang bật, đã đăng nhập Windows và có Internet**. Tắt máy là không giám sát — đây không phải dịch vụ đám mây chạy 24/7.
- Mọi thay đổi ngân sách/giá thầu đều cần người duyệt; phần mềm không tự ý chỉnh quảng cáo.
- License gắn với **một máy** qua mã máy; đổi máy phải liên hệ bên bán cấp lại.

**Không cần ghi sổ ở bước này.**

## Bước 2 — Nhận mã máy và đăng ký khách vào sổ

Khách cài phần mềm, mở trang **Bản quyền**, bấm **Sao chép mã máy** và gửi mã cho bên bán. Nhắc khách: **chỉ gửi mã máy, tuyệt đối không gửi token quảng cáo hay mật khẩu tài khoản Ads**.

Gán cho khách một mã nội bộ (ví dụ `KH001`, `SHOP-01`). Một mã khách gắn với đúng một mã máy; khách có máy thứ hai thì tạo mã khách khác. Không ghi tên thật, email hay tài khoản Ads vào sổ.

```powershell
python tools/vendor_ledger.py register --customer KH001 --device <MA MAY KHACH GUI>
```

## Bước 3 — Gửi thông tin chuyển khoản

**Gửi cho khách:** mẫu tin nhắn số 2 trong `MAU-TIN-NHAN.md` (ngân hàng, số tài khoản, chủ tài khoản, số tiền, cú pháp nội dung chuyển khoản chứa mã khách để đối chiếu).

Sau khi gửi, chưa cần ghi sổ — giao dịch chỉ được ghi nhận khi ký license ở bước 5. Nếu muốn theo dõi khách đang chờ thanh toán, ghi chú ngoài sổ [CHU SAN PHAM QUYET DINH: cách theo dõi khách chờ thanh toán — hiện vendor_ledger không có trạng thái "chờ chuyển khoản" riêng trước khi có license].

## Bước 4 — Tự xác nhận tiền về

Bên bán **tự kiểm tra** trên ứng dụng ngân hàng/sao kê của chính mình: đúng số tiền, đúng cú pháp nội dung (khớp mã khách). Không có bước tự động nào ở đây — `vendor_ledger.py` không đọc được số dư ngân hàng.

Chưa thấy tiền về thì **không ký license**. Nếu khách báo đã chuyển nhưng chưa thấy, chờ và kiểm tra lại; tuyệt đối không cấp trước "cho tiện".

Gán mã biên nhận nội bộ cho giao dịch, ví dụ `TT-KH001-001` (chỉ là chuỗi quản lý nội bộ — **không** nhập số tài khoản ngân hàng, số thẻ hay thông tin cá nhân vào sổ).

## Bước 5 — Ký license và ghi sổ

Ký license 30 ngày cho đúng mã máy đã đăng ký (lệnh hỏi mật khẩu khóa riêng — gõ trực tiếp, không ghi mật khẩu vào lệnh/file/script):

```powershell
python tools/license_issuer.py sign --private C:\LHMKeys\vendor-private-key.pem --expected-public C:\LHMKeys\vendor-public.b64 --device <MA MAY> --plan monthly --days 30 --out KH001-2026-11.json
```

Ghi nhận vào sổ kèm trạng thái đã xác nhận và mã biên nhận:

```powershell
python tools/vendor_ledger.py record --customer KH001 --license KH001-2026-11.json --public C:\LHMKeys\vendor-public.b64 --payment-status confirmed --receipt TT-KH001-001
```

Sổ sẽ tự xác minh chữ ký license bằng khóa công khai trước khi nhận; file giả, sai máy hoặc sai sản phẩm sẽ bị từ chối — nếu bị từ chối, kiểm tra lại mã máy và bộ khóa, đừng tìm cách "ghi ép".

Trường hợp đã ký và ghi sổ trước ở trạng thái chờ (ví dụ ghi `record` không kèm `--payment-status confirmed`), sau khi đối chiếu ngân hàng xong thì chốt bằng:

```powershell
python tools/vendor_ledger.py confirm-payment --license-id <LICENSE_ID> --receipt TT-KH001-001
```

## Bước 6 — Gửi license và hướng dẫn khách kích hoạt

**Gửi cho khách:** file JSON vừa ký + mẫu tin nhắn số 3 trong `MAU-TIN-NHAN.md` (đã nhận tiền + hướng dẫn kích hoạt từng bước: mở trang Bản quyền → dán nội dung file license.json → bấm Kích hoạt / Gia hạn).

Đề nghị khách phản hồi khi kích hoạt thành công và kiểm tra dòng **Trạng thái** ở trang Bản quyền hiện "Đã kích hoạt" cùng ngày hết hạn đúng như đã bán. Nếu khách báo lỗi kích hoạt, đối chiếu theo thứ tự: đúng file JSON chưa → đúng máy đã đăng ký chưa → đồng hồ Windows của máy khách có bị chỉnh lùi không (chỉnh lùi quá 5 phút sẽ bị chặn tính năng trả phí; đồng bộ lại giờ là khôi phục).

## Bước 7 — Vận hành hằng ngày/tuần

```powershell
python tools/vendor_ledger.py list
python tools/vendor_ledger.py due --within-days 7
python tools/vendor_ledger.py export --out danh-sach-gia-han.csv
```

Sao lưu sổ định kỳ (khi không có lệnh nào đang chạy), không ghi đè bản cũ, cất vào kho lưu mã hóa của bên bán — **không đưa file sổ lên GitHub/repo**:

```powershell
python tools/vendor_ledger.py backup --out C:\LHMKeys\customers-backup-2026-10.sqlite3
```

## Bước 8 — Nhắc và xử lý gia hạn

Lệnh `remind` liệt kê khách đã hết hạn hoặc sắp hết hạn; đây là nhắc cho **chính bên bán** (không tự gửi tới khách):

```powershell
python tools/vendor_ledger.py remind --within-days 7
```

Muốn nhận danh sách này qua Telegram của bên bán, đặt `VENDOR_TELEGRAM_BOT_TOKEN` và `VENDOR_TELEGRAM_CHAT_ID` trên máy bên bán rồi thêm `--send`. Có thể đặt lệnh này vào Task Scheduler chạy hằng ngày. Nội dung nhắc chỉ gồm mã khách nội bộ, gói, số ngày còn lại và trạng thái thanh toán.

Từ danh sách `remind`, gửi tay cho từng khách mẫu tin nhắn số 4 trong `MAU-TIN-NHAN.md` (nhắc trước 7 ngày, nhắc lại trước 1 ngày). Khách đồng ý gia hạn thì lặp lại bước 3–4 (chuyển khoản + tự xác nhận), rồi ký nối hạn — gia hạn sớm được **cộng dồn ngày** vào hạn hiện tại:

```powershell
python tools/license_issuer.py sign --private C:\LHMKeys\vendor-private-key.pem --expected-public C:\LHMKeys\vendor-public.b64 --device <MA MAY> --plan monthly --days 30 --renew-from KH001-2026-11.json --out KH001-2026-12.json
python tools/vendor_ledger.py record --customer KH001 --license KH001-2026-12.json --public C:\LHMKeys\vendor-public.b64 --payment-status confirmed --receipt TT-KH001-002
```

Không ghi đè file license cũ. Sổ sẽ từ chối bản gia hạn có hạn cuối thấp hơn hồ sơ đã ghi — đó là dấu hiệu sai mã máy hoặc sai file `--renew-from`, cần kiểm tra lại.

Khách không gia hạn: gửi mẫu tin nhắn số 5 (đã hết hạn). Nhấn mạnh đúng sự thật: **hết hạn không xóa dữ liệu** — khách vẫn mở phần mềm xem và xuất báo cáo được, chỉ các tính năng trả phí và giám sát nền dừng lại. Không có thao tác "khóa máy khách từ xa" và không cần làm gì thêm trong sổ.

## Bước 9 — Hỗ trợ đổi máy

Khách đổi/sửa máy thì mã máy thay đổi, license cũ không dùng được trên máy mới. Quy trình: khách gửi mã máy mới → bên bán đăng ký mã khách mới cho thiết bị mới (một mã khách = một thiết bị) → ký license theo mã máy mới với số ngày còn lại [CHU SAN PHAM QUYET DINH: chính sách đổi máy — số lần miễn phí, có tính phí hay không, tính ngày còn lại thế nào] → ghi sổ bằng `record` như bình thường → gửi khách theo mẫu tin nhắn số 6. Nhắc khách sao lưu dữ liệu mã hóa trước khi chuyển máy (trang Bản quyền → Kiểm tra sẵn sàng & Bảo vệ dữ liệu; xem `docs/CUSTOMER_BACKUP.md`) — license không tự chuyển theo dữ liệu.

---

## Những điều tuyệt đối không làm

- Không nhận, không lưu token quảng cáo, mật khẩu tài khoản Ads hay thông tin ngân hàng của khách trong sổ bán hàng.
- Không gửi khóa ký riêng hoặc mật khẩu khóa cho bất kỳ ai, không đưa lên GitHub/ChatGPT/CI.
- Không hứa: tự động xác nhận tiền về, tự thu tiền định kỳ, thu hồi license từ xa, giám sát khi máy khách tắt, hay tự động tối ưu quảng cáo không cần người duyệt — phần mềm hiện **không có** các khả năng này.
- Theo lựa chọn của chủ sở hữu, có thể giao **COMMERCIAL-UNSIGNED** sau khi đã kiểm chứng manifest Ed25519 và đủ nghiệm thu; phải thông báo trước Windows có thể cảnh báo Unknown Publisher/SmartScreen, không đổi tên Pilot để bán và không hướng dẫn khách tắt cơ chế bảo mật (xem `docs/COMMERCIAL_UNSIGNED.md`).
