# LHM Ads AI — một lệnh khởi tạo bản Commercial (không chứng thư Windows)

Chạy **chỉ trên máy Windows của chủ phần mềm**, không chạy trên VPS, GitHub CI hoặc máy khách. Cần cài **Python 3.12+**, thư viện `cryptography` (`python -m pip install cryptography`), và **GitHub CLI** từ https://cli.github.com/.

Trong PowerShell ở thư mục mã nguồn dự án:

```powershell
.\windows\vendor-start.ps1
```

Chương trình tự: tạo private Ed25519 được bảo vệ bằng mật khẩu ở `%LOCALAPPDATA%\LHMAdsAI-Vendor\keys` (nếu chưa có); giữ nguyên khóa nếu đã tồn tại; đăng nhập GitHub trong trình duyệt nếu cần; chuyển **duy nhất PUBLIC KEY** vào secret `LHM_COMMERCIAL_PUBLIC_KEY_B64`; chạy workflow `commercial=true` trên `main`; theo dõi CI; tải và kiểm tra SHA256, commit/version, public key và trạng thái `commercial-candidate`.

Không đưa private PEM hay mật khẩu lên GitHub, chat, Zalo hoặc CI. Lưu 2 bản sao lưu private PEM **đã mã hóa** ở nơi offline riêng; mật khẩu cũng phải giữ riêng.

Chạy riêng từng bước:

```powershell
.\windows\vendor-start.ps1 -Action setup
.\windows\vendor-start.ps1 -Action build
.\windows\vendor-start.ps1 -Action status
```

**Chỉ sau khi** đã nghiệm thu thật Google/Meta API trên tài khoản được ủy quyền, Windows reboot/sleep/backup, ký duyệt `owner-acceptance.json`, mới đóng gói ZIP thương mại `COMMERCIAL-UNSIGNED` theo `docs/COMMERCIAL_UNSIGNED.md`. Khách phải được thông báo Windows có thể cảnh báo Unknown Publisher/SmartScreen; không yêu cầu khách tắt bảo vệ.

Khách trả tiền thật rồi mới cấp license trên máy chủ:

```powershell
python tools/license_issuer.py sign --private "$env:LOCALAPPDATA\LHMAdsAI-Vendor\keys\vendor-private-key.pem" --expected-public "$env:LOCALAPPDATA\LHMAdsAI-Vendor\keys\vendor-public.b64" --device <DEVICE_ID_32_HEX> --days 30 --plan monthly --out KH001-30ngay.json
```

Script sẽ hỏi mật khẩu private key một cách riêng tư. License ký theo Device ID và có thể gia hạn theo tháng. Không có chứng thư Authenticode nên Windows không xác minh nhà phát hành qua hệ chứng thư của Windows. Chữ ký Ed25519 trên release manifest chỉ có ý nghĩa khi khách lấy public key từ nguồn chính thức độc lập với ZIP.
