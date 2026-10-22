# LHM Ads AI — phát hành thương mại KHÔNG cần chứng thư Windows

**Quyết định của chủ sở hữu:** không mua chứng thư Authenticode. Đây là lựa chọn phát hành EXE không ký số Windows, **không** làm Windows tự động tin cậy phần mềm. Khách có thể nhìn thấy **Unknown publisher** hoặc Microsoft Defender SmartScreen. Không hướng dẫn tắt Defender/SmartScreen hay bỏ qua cảnh báo bảo mật.

## 1. Khóa bán phần mềm theo máy vẫn bắt buộc

Trên máy **riêng của bên bán**, cài Python 3.12 và cryptography rồi tạo Ed25519 một lần:

```powershell
python tools/license_issuer.py keygen --private C:\LHMKeys\vendor-private-key.pem --public C:\LHMKeys\vendor-public.b64
```

Private PEM được mã hóa bằng mật khẩu (ít nhất 16 ký tự). **Không gửi private PEM/mật khẩu lên GitHub, ChatGPT, Zalo hay cho khách**. Sao lưu offline tối thiểu 2 bản, giữ mật khẩu riêng. Không tạo lại khóa khi đã có khách, vì license cấp bằng khóa mới sẽ không tương thích EXE cũ.

Vào GitHub repo → Settings → Secrets and variables → Actions → New repository secret, đặt `LHM_COMMERCIAL_PUBLIC_KEY_B64` bằng **chuỗi base64 công khai** trong `vendor-public.b64`. Chỉ public, tuyệt đối không upload private.

## 2. Build bản Commercial chưa ký số

GitHub → Actions → **Build and test Windows EXE** → **Run workflow** → chọn nhánh `main`, `commercial=true`. Workflow lấy public key, nhúng vào EXE và ghi `edition=commercial-candidate`, `authenticode=UNSIGNED`, fingerprint khóa cấp license, SHA256 EXE và semver vào manifest.

Tải artifact **LHM-Ads-AI-COMMERCIAL-CANDIDATE-UNSIGNED**. Giải nén vào thư mục riêng có đúng các file `LHM-Ads-AI.exe`, `LHM-Ads-AI.sha256`, `release-manifest.json`. KHÔNG lấy bản Pilot rồi đổi tên hoặc lấy EXE từ commit khác.

## 3. Nghiệm thu thật trước khi giao khách trả tiền

Chạy checklist `docs/ACCEPTANCE.md` trên máy Windows thật bằng tài khoản Google/Meta được ủy quyền. Đặc biệt test OAuth, API đọc báo cáo, reboot, sleep/wake, sao lưu/khôi phục và cấp/gia hạn license. Không cần mua chứng thư, nhưng những mục này **không thể bỏ qua**.

Tạo bản sao `docs/COMMERCIAL_ACCEPTANCE_TEMPLATE.json` ở máy bên bán, điền SHA commit và version đúng manifest; chỉ tự chuyển `passed=true` sau khi có `evidence_ref` của từng mục, chủ sở hữu duyệt `owner_approved=true`, `approved_by` và thời gian UTC thực.

## 4. Đóng gói không cần chứng thư Authenticode

Chạy trên máy bên bán, từ thư mục mã nguồn của **đúng phiên bản**:

```powershell
python tools/package_unsigned_release.py package --exe C:\LHM\candidate\LHM-Ads-AI.exe --checksum C:\LHM\candidate\LHM-Ads-AI.sha256 --manifest C:\LHM\candidate\release-manifest.json --vendor-public C:\LHMKeys\vendor-public.b64 --acceptance C:\LHM\owner-acceptance.json --private C:\LHMKeys\vendor-private-key.pem --out C:\LHM\releases\LHM-Ads-AI-0.3.0-COMMERCIAL-UNSIGNED.zip --accept-unsigned-windows
```

Công cụ hỏi mật khẩu private key theo cách nhập ẩn. Sau khi so sánh checksum gốc CI, public key đã nhúng, đúng commit/version và đủ hồ sơ nghiệm thu, nó ký manifest bằng Ed25519 theo thông điệp riêng và tạo gói ZIP. **Private key không nằm trong ZIP hay GitHub.** Bất kỳ bước nào thất bại sẽ không tạo gói bán.

## 5. Kiểm tra ZIP trước khi gửi khách

```powershell
python tools/package_unsigned_release.py verify --zip C:\LHM\releases\LHM-Ads-AI-0.3.0-COMMERCIAL-UNSIGNED.zip --trusted-vendor-public C:\LHMKeys\vendor-public.b64
```

**Quan trọng:** người nhận phải lấy public key và fingerprint từ một kênh chính thức độc lập với file ZIP (ví dụ website tên miền của bên bán). Không xem public key chỉ có trong ZIP là bằng chứng nhà phát hành thật. Script `verify` kiểm tra chữ ký Ed25519 và SHA-256 của EXE, **không** tạo chứng thư Windows hoặc chứng minh file không có mã độc. Khách không nên chạy nếu Windows chặn và họ chưa xác minh nguồn gốc.

## 6. Bán 30 ngày và gia hạn

Sau khi đối chiếu khách đã thanh toán thật, nhận Device ID từ trang Bản quyền rồi cấp license:

```powershell
python tools/license_issuer.py sign --private C:\LHMKeys\vendor-private-key.pem --expected-public C:\LHMKeys\vendor-public.b64 --device <MA_MAY> --days 30 --plan monthly --out KH001-30ngay.json
```

Khách dán nội dung JSON vào màn hình Kích hoạt. Ghi sổ bằng `tools/vendor_ledger.py`, chỉ chốt tiền khi đã xem sao kê thực. Gia hạn dùng `--renew-from` theo `docs/VENDOR_OPERATIONS.md`. Không gửi token Google/Meta về bên bán.

## Giới hạn và trách nhiệm

Không có Authenticode: không có tên nhà phát hành được Windows xác minh, SmartScreen có thể cảnh báo và một số môi trường doanh nghiệp có thể chặn chạy EXE. Ed25519 ký manifest giúp kiểm chứng file từ đúng bên giữ private key **khi** khách tin cậy public key qua kênh độc lập, không thay thế chữ ký code-signing. Không cam kết sẽ vượt SmartScreen, Defender, Antivirus hay chính sách doanh nghiệp.

Không có tài khoản test và quyền Google/Meta thật, bộ phát hành vẫn dừng ở bước nghiệm thu. Không giả tạo bằng chứng test hay chuyển `NOT_RUN` thành `PASS`.

## Tự động thiết lập & build lần đầu

Cách ít thao tác hơn: chạy `windows/vendor-start.ps1` trên **chính máy của bên bán**. Script tạo khóa riêng mã hóa ngay trên máy đó, chỉ gửi public key lên GitHub, chạy workflow `commercial=true`, tải artifact và kiểm tra tính nhất quán. Xem [VENDOR_ONE_CLICK.md](VENDOR_ONE_CLICK.md). Không chạy trên VPS hoặc CI; không chia sẻ private PEM/mật khẩu.
