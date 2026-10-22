# Phát hành bản thương mại LHM Ads AI — hướng dẫn thực thi

Đây là quy trình *khóa cứng* để **không thể đóng gói bán** một bản Pilot/EXE chưa ký, chưa khớp khóa cấp phép hoặc chưa có bằng chứng nghiệm thu. **Chưa có chứng thư Authenticode hay tài khoản quảng cáo thật thì chỉ có thể phân phối Pilot để thử nghiệm.**

## A. Việc cần do chủ phần mềm sở hữu

1. **Tạo khóa bản quyền Ed25519 trên máy cá nhân** theo `docs/COMMERCIAL_LICENSE.md`. Giữ private key đã mã hóa ngoài repo/GitHub và sao lưu ngoại tuyến.
2. Tại GitHub Actions, đặt secret `LHM_COMMERCIAL_PUBLIC_KEY_B64` chỉ chứa khóa *công khai*. Chạy workflow `Build and test Windows EXE` thủ công với `commercial=true` từ `main`. Tải artifact `LHM-Ads-AI-COMMERCIAL-CANDIDATE-UNSIGNED` — **chưa phải bản bán**.
3. **Mua chứng thư code signing Authenticode** đứng tên chủ phần mềm. Cài chứng thư/hardware token lên chính máy Windows của nhà phát hành, có Windows SDK `signtool.exe`; **không gửi PFX/private key vào repo hay CI**.
4. **Nghiệm thu trên máy Windows thật**, gồm đăng nhập lại sau reboot, tắt UI mà giám sát vẫn chạy, sleep/wake, backup/restore, Google Ads test account, Meta Ads test account, cấp/gia hạn license, điều khoản dịch vụ, chính sách bảo mật và đối soát tiền/hóa đơn. Xem `docs/ACCEPTANCE.md`.
5. Sau khi từng bước thật đạt, tạo bản sao `docs/COMMERCIAL_ACCEPTANCE_TEMPLATE.json`, điền `source_commit` và `product_version` đúng `release-manifest.json` của candidate; đánh dấu `passed=true`, nhập `evidence_ref` phi nhạy cảm cho **8 mục**, tên người phê duyệt và `approved_at_utc` theo ISO 8601 UTC. Chỉ chủ sở hữu xác nhận; **không tự đổi NOT_RUN thành PASS**.

## B. Đóng gói ngoại tuyến trên chính máy ký số

Chạy PowerShell với quyền người dùng có chứng thư code-signing. Giả sử `C:\LHM\candidate` có EXE, `.sha256` và manifest tải từ cùng GitHub artifact:

```powershell
.\windows\package-commercial-release.ps1 -CandidateDir C:\LHM\candidate -VendorPublicFile C:\LHMKeys\vendor-public.b64 -AcceptanceFile C:\LHM\owner-acceptance.json -PublisherThumbprint <THUMBPRINT_40_HEX> -TimestampUrl https://timestamp.digicert.com -OutputDir C:\LHM\releases\v0.3.0
```

Script bắt buộc kiểm tra: EXE và SHA256 của CI khớp; edition đúng `commercial-candidate`; fingerprint public license trùng khóa của bên bán; phiên bản/commit nghiệm thu khớp; đủ 8 chứng cứ được chủ sở hữu ký duyệt thủ công; chứng thư code signing trong Windows Store có private key, đúng thumbprint và Code Signing EKU. Sau đó script mới sao chép EXE, ký Authenticode bằng `signtool`, kiểm tra trust + signer và tạo ZIP có SHA256 **sau ký** cùng manifest.

Script **không** ký file bằng khóa Ed25519 cấp license: đây là hai hệ khóa độc lập (license Ed25519 vs Windows Authenticode). Nếu thiếu bất kỳ điều kiện nào thì dừng, không xuất bản file thương mại.

## C. Sau khi tạo ZIP

Đối chiếu thêm trên máy Windows sạch bằng `windows/verify-release.ps1` và chạy đăng nhập/thao tác đọc Ads trên bản đã ký. Đăng ký kênh tải chính thức thuộc quyền chủ phần mềm; chỉ công bố đúng ZIP và SHA256 của bản **SIGNED**. Lưu bản unsigned gốc, checklist và bằng chứng nghiệm thu nội bộ, không đăng file chứa token/người dùng.

**Giới hạn:** Script kiểm tra tính đầy đủ và sự nhất quán của biên bản do chủ phần mềm xác nhận; nó **không thể tự chứng minh** các ảnh/bằng chứng Google/Meta là thật. CI cũng không thể tự cung cấp merchant key, chứng thư do CA cấp, hay App Review/Ads API production.
