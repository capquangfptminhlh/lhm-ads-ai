# LHM Ads AI — Quy trình phát hành thương mại Windows

**Cập nhật 21/10/2026.** Phần mềm dùng license offline, dữ liệu Ads và token ở máy khách. Không có VPS lưu tập trung.

## Trạng thái sản phẩm

- CI push lên main tự build bản **PILOT** để kiểm thử, không phải EXE thương mại.
- **COMMERCIAL** chỉ build bằng cách chạy thủ công GitHub Actions với commercial=true và có public key riêng của chủ phần mềm.
- EXE chỉ chứa khóa CÔNG KHAI Ed25519. Khóa RIÊNG phải cất ngoài repo, cloud, EXE và máy khách.
- Đã có MFA TOTP tùy chọn cho từng tài khoản (Cài đặt → Xác thực hai lớp) và giới hạn đăng nhập sai lưu bền trong cơ sở dữ liệu theo email + IP. Bên bán có lệnh `vendor_ledger.py remind [--send]` để liệt kê khách sắp/đã hết hạn và gửi một tin nhắc tới Telegram của chính bên bán.
- Thu tiền hiện tại bằng chuyển khoản vào tài khoản bên bán + xác nhận tay; tích hợp PayOS đã có sẵn dạng chờ kích hoạt bằng khóa merchant của bên bán (xem PAYOS.md). Chưa có hóa đơn tự động, cập nhật phần mềm có ký số hay hệ thống thu hồi license từ xa.
- Chưa xác thực hoàn chỉnh API của tài khoản quảng cáo thật. Không quảng cáo tự động thay bid/budget/strategy 24/7 khi chưa nghiệm thu.

## Bước 1 — Tạo khóa phát hành trên máy bên bán (chỉ một lần)

Trên máy riêng của bên bán có Python và cryptography, chạy:

```bash
python tools/license_issuer.py keygen --private /secure/vendor-private-key.pem --public /secure/vendor-public.b64
```

Chương trình yêu cầu mật khẩu ít nhất 16 ký tự và xuất private key được mã hóa. Sao lưu khóa riêng ở hai nơi tách biệt, bảo quản mật khẩu riêng. Tuyệt đối không gửi private key/mật khẩu lên GitHub, ChatGPT hoặc cho khách. Không thay bộ khóa sau khi đã bán, nếu không bản EXE cũ sẽ không xác minh được license mới.

## Bước 2 — Cấu hình GitHub và build

1. Tại GitHub repository → Settings → Secrets and variables → Actions, tạo repository secret `LHM_COMMERCIAL_PUBLIC_KEY_B64` chứa đúng một dòng trong `vendor-public.b64`. Đây chỉ là khóa CÔNG KHAI.
2. GitHub → Actions → Build and test Windows EXE → Run workflow → chọn main → commercial=true.
3. Workflow sẽ fail nếu không có public key hợp lệ. Workflow tạo artifact `LHM-Ads-AI-COMMERCIAL-CANDIDATE-UNSIGNED` **CHƯA KÝ SỐ** để thử nội bộ. Không gửi khách, không gọi đây là bản phát hành chính thức.
4. Artifact có EXE, SHA256, `release-manifest.json` (ghi rõ unsigned) và hướng dẫn. Chủ phần mềm phải ký Authenticode bằng chứng thư riêng **ngoài GitHub**, rồi kiểm tra bằng `windows/verify-release.ps1 -Exe .\\LHM-Ads-AI.exe -ExpectedThumbprint <PUBLISHER_CERT_SHA1> -HashOut .\\LHM-Ads-AI-signed.sha256`. Chỉ mã SHA256 **sau khi ký** mới dùng cho bản gửi khách. Không tự xuất bản file unsigned.

## Bước 3 — Cấp và gia hạn license 30 ngày

Khách mở EXE, vào Bản quyền, sao chép Mã máy rồi gửi bên bán. Không gửi token quảng cáo.

```bash
python tools/license_issuer.py sign --private /secure/vendor-private-key.pem --expected-public /secure/vendor-public.b64 --device <DEVICE_ID> --plan monthly --days 30 --out customer-nov.json
```

Gửi file JSON đã ký cho khách; khách dán vào Kích hoạt/Gia hạn. Không cần Internet. Gia hạn sớm được cộng dồn ngày:

```bash
python tools/license_issuer.py sign --private /secure/vendor-private-key.pem --expected-public /secure/vendor-public.b64 --device <DEVICE_ID> --plan monthly --days 30 --renew-from customer-nov.json --out customer-dec.json
```

Quản lý riêng sổ bán hàng: mã khách, Device ID, license ID, ngày hết hạn, tiền đã thu, hóa đơn và filename JSON. Không lưu access token quảng cáo trong sổ kinh doanh.

## Bảo mật và giới hạn

- Windows master key được bảo vệ bằng DPAPI theo người dùng. API token lưu mã hóa AES-GCM trong SQLite ở máy khách.
- Mốc thời gian đã xác minh được lưu có mã hóa; khi chỉnh lùi đồng hồ quá 5 phút, tính năng trả phí bị chặn. Đồng bộ giờ Windows để khôi phục. Đây không phải DRM không thể bẻ khóa, vì chủ máy có thể sửa chương trình.
- Hết hạn license không xóa dữ liệu quảng cáo. Giám sát nền chỉ đọc API và chỉ hoạt động khi máy có điện, Windows chạy và Internet sẵn.
- Không cam kết API Google/Meta production nếu chưa có quyền hợp lệ và được nhà cung cấp cho phép.

## Checklist trước khi thu tiền khách hàng diện rộng

- [ ] Public/private key của chính bên bán đã được sao lưu; build COMMERCIAL thực có thể cấp, kích hoạt và gia hạn license trên Windows sạch.
- [ ] GitHub CI và native WebView2 EXE smoke đều thành công; hash kiểm chứng chính xác.
- [ ] Đã test Google Ads + Meta Ads với quyền thật và đối chiếu số liệu đúng nền tảng.
- [ ] Kiểm tra khôi phục dữ liệu, máy Windows 10/11, restart, offline, hết hạn, gia hạn sớm, chỉnh giờ.
- [ ] Có chứng thư ký mã EXE Authenticode, trang tải chính thức, điều khoản sử dụng, bảo mật, chính sách giá và hỗ trợ kỹ thuật.
- [ ] Có quy trình thu phí, xuất hóa đơn và bảo mật thông tin khách hàng; phần hóa đơn/thanh toán chưa tích hợp tự động.

**Không chuyển private vendor key cho đội hỗ trợ, khách hoặc CI.**

## Thu tiền tự động — phần cần tài khoản/cấp phép của chủ phần mềm

Các mục dưới đây **không thể hoàn thành bằng code trong repo**, vì chúng gắn với danh tính pháp lý và tài khoản của chính bên bán:

1. **Cổng thanh toán**: quy trình đang dùng là chuyển khoản vào tài khoản của chính bên bán, bên bán tự xác nhận tiền về rồi mới cấp license. Tích hợp **PayOS đã viết sẵn và đang tắt** (xem [PAYOS.md](PAYOS.md)): chỉ cần bên bán đăng ký merchant PayOS bằng pháp nhân/tài khoản của mình và đặt `PAYOS_CLIENT_ID`/`PAYOS_API_KEY`/`PAYOS_CHECKSUM_KEY` trên máy bên bán là tạo được link thanh toán và nhận webhook xác minh chữ ký — webhook chỉ đánh dấu đơn `paid`, việc ký license vẫn ở máy bên bán. Lưu ý đánh đổi kiến trúc: muốn license được cấp *tự động ngay khi tiền về* thì khóa ký riêng phải nằm trên một máy chủ trực tuyến, làm yếu mô hình "khóa ký chỉ ở máy bên bán ngoại tuyến" hiện tại.
2. **Hóa đơn điện tử**: cần hợp đồng với nhà cung cấp hóa đơn (Viettel Invoice, VNPT Invoice, MISA meInvoice…) và thông tin xuất hóa đơn của bên bán.
3. **Ký số EXE (Authenticode)**: mua chứng thư code-signing từ CA (DigiCert/Sectigo…) đứng tên bên bán; quy trình ký và kiểm chứng đã có sẵn trong tài liệu này.
4. **Thu hồi license từ xa**: mô hình offline hiện tại không hỗ trợ; muốn có phải chuyển sang kiểm tra license trực tuyến định kỳ — một thay đổi kiến trúc cần quyết định riêng, đánh đổi quyền riêng tư/ngoại tuyến của khách.

## Vận hành khách thuê

Xem [VENDOR_OPERATIONS.md](VENDOR_OPERATIONS.md) để đăng ký mã máy, xác minh file license, ghi nhận thanh toán thủ công, lọc khách sắp hết hạn và xuất báo cáo CSV ngoại tuyến. Không thu thập token Ads, không tự xác nhận giao dịch ngân hàng.

## Sao lưu dữ liệu khách

Bản Windows có trang **Bản quyền → Kiểm tra sẵn sàng & Bảo vệ dữ liệu** để tải bản backup mã hóa AES-GCM/Scrypt. Quy trình khôi phục ngoại tuyến và giới hạn chi tiết xem [CUSTOMER_BACKUP.md](CUSTOMER_BACKUP.md). Không sao chép DPAPI local-settings giữa máy và không giả định giấy phép tự chuyển máy.
