# LHM Ads AI — Cập nhật online cho Windows (Pilot 0.3.1)

## Người dùng

- Với **EXE cũ 0.3.0**: bắt buộc nâng cấp **một lần** sang EXE mới có updater. Mã cũ không thể tự thêm chức năng cập nhật vào chính nó.
- Từ bản đã có updater: sau khi đăng nhập, ứng dụng kiểm tra thông báo cập nhật HTTPS của nhà phát hành nếu cấu hình đã được nhúng trong EXE. Vào **Cài đặt → Cập nhật phần mềm online** để kiểm tra lại hoặc xem phiên bản mới.
- Khi có bản mới, bấm **Tải và xác minh** rồi **Cài & khởi động lại**. Phần mềm kiểm chữ ký Ed25519 và SHA-256, tải EXE mới vào thư mục cập nhật trong AppData, đóng GUI/API cục bộ, sau đó tác vụ Windows thay tệp và khởi chạy phiên bản mới.
- **Không có cập nhật âm thầm**: phần tải/cài cần người dùng xác nhận. Không cần đăng nhập lại Google/Meta chỉ vì thay EXE; token và SQLite vẫn nằm trong `%LOCALAPPDATA%\LHMAdsAI`.
- Máy cần Internet, Windows PowerShell và quyền ghi lên thư mục chứa `LHM-Ads-AI.exe`. Nếu đặt trong Program Files cần quyền quản trị phù hợp; updater **không tự nâng quyền**.
- Một bản sao EXE cũ dạng `.backup-<phiên bản>` được giữ cạnh EXE để có thể phục hồi khi cần. Nếu SmartScreen/Defender cảnh báo nhà phát hành chưa được xác minh, **không tắt cơ chế bảo vệ** chỉ để hoàn tất nâng cấp.

## Chủ phần mềm — thiết lập chuỗi tin cậy trước khi phân phối

**Chưa cấu hình nghĩa là không cập nhật:** repo hiện không chứa khóa ký riêng, địa chỉ manifest hay bản phát hành chính thức có chữ ký. Không thể tuyên bố có cập nhật online thực tế chỉ vì CI đã build.

1. Trên **máy ngoại tuyến do chủ phần mềm quản lý**, tạo khóa Ed25519 riêng dành cho cập nhật (tách khỏi khóa license), bằng quy trình keygen của `tools/license_issuer.py` hoặc công cụ tương đương. Mã hóa private PEM bằng mật khẩu dài, sao lưu ngoại tuyến; **tuyệt đối không đưa private PEM, mật khẩu, API Ads lên GitHub/ChatGPT hoặc EXE**.
2. Đăng hai **GitHub Actions repository variables công khai**: `LHM_UPDATE_PUBLIC_KEY_B64` (base64 của đúng 32 byte raw public key) và `LHM_UPDATE_MANIFEST_URL` (HTTPS URL chứa JSON signed envelope, ví dụ `https://updates.tenmien.vn/lhm-update.json`). Build Windows EXE trên `main` sẽ nhúng hai giá trị này; thiếu một thì bản build không có chức năng kiểm tra mạng.
3. Trước khi xuất bản phiên bản mới, tăng `ads_core/version.py` và đồng bộ tài liệu, chạy CI Windows và kiểm thử live theo `docs/RELEASE_CHECKLIST.md`. Chỉ phân phối bản Pilot cho thử nghiệm, không đánh dấu unsigned là bán chính thức.
4. Sao chép EXE đã kiểm thử về máy ký ngoại tuyến và tạo signed envelope (không đưa private key lên CI):

   ```powershell
   python tools/sign_update_manifest.py --exe .\LHM-Ads-AI.exe --version 0.3.2 --download-url https://updates.tenmien.vn/LHM-Ads-AI.exe --private C:\LHMKeys\update-private.pem --notes "Sửa lỗi" --out .\lhm-update.json
   ```

5. Tải **EXE đúng bản đã ký SHA-256** cùng `lhm-update.json` lên HTTPS origin của nhà phát hành, bảo đảm URL không tự redirect. Phiên bản trong manifest phải **lớn hơn** phiên bản khách đang dùng. Có thể dùng static hosting/CDN riêng, không dùng link GitHub Actions artifact cần đăng nhập hoặc hết hạn sau 14 ngày.
6. Từ máy thử nghiệm, tải manifest, kiểm chữ ký bằng `tools/update_check.py`, thử cập nhật thật và phục hồi file sao lưu nếu cần, trước khi gửi rộng rãi.

## Bảo mật và giới hạn

- Manifest phải có **đúng** năm trường: `version`, `download_url`, `sha256`, `notes`, `issued_at`; chữ ký Ed25519 trên JSON canonical riêng của `manifest`.
- HTTPS chưa đủ: ứng dụng luôn kiểm chữ ký đúng khóa công khai đã nhúng. File EXE phải khớp SHA-256, có tiêu đề PE `MZ`, và được kiểm lại trước khi thay.
- Không tải từ link người dùng nhập, không dùng GitHub artifact như nguồn cập nhật tự động và không tự ghi đè EXE khi đang chạy.
- Nếu PowerShell bị chính sách máy công ty chặn, ổ đĩa hết chỗ, file không ghi được, hoặc signature sai, không bỏ qua kiểm tra. Bản cũ vẫn được giữ. Có thể cần hỗ trợ cài thủ công nếu máy đặt trong thư mục chỉ đọc.
- Pilot chưa ký Windows Authenticode; chữ ký manifest không thay thế chứng thư Authenticode. Bản cập nhật online không thay đổi trạng thái nghiệm thu API Google/Meta thực tế.
