# LHM Ads AI — Sao lưu và khôi phục dữ liệu an toàn

## Trên máy khách Windows

1. Đăng nhập Admin → trang **Bản quyền** → **Kiểm tra sẵn sàng & Bảo vệ dữ liệu**.
2. Nhập mật khẩu sao lưu riêng từ 16 ký tự, xác nhận rồi chọn tải file `.lhmbak`.
3. Lưu file backup trên ổ ngoài mã hóa và lưu mật khẩu ở một nơi khác. **Không gửi mật khẩu cho hỗ trợ, không đăng file lên GitHub/Zalo.**
4. Thực hiện sao lưu trước khi đổi phiên bản EXE, đổi máy hoặc cài lại Windows.

Ứng dụng sao lưu một snapshot SQLite nhất quán và xóa phiên đăng nhập từ snapshot. Database cùng master key cần để giải mã Ads token được bảo vệ bằng AES-256-GCM; khóa dẫn xuất qua Scrypt từ mật khẩu backup. Không sao lưu Device ID, license theo máy, session secret hoặc Windows autostart. Giới hạn hiện khoảng 64 MB; database lớn hơn cần quy trình riêng.

## Khôi phục offline có người hỗ trợ

Thoát hoàn toàn LHM Ads AI và tác nhân giám sát. Trên máy Windows đích cần Python và các thư viện trong `requirements.txt` của repo. Người dùng phải tự nhập mật khẩu backup, không gửi mật khẩu cho kỹ thuật viên.

```powershell
python tools/customer_restore.py --backup D:\Backups\customer.lhmbak --destination C:\Path\To\NEW-EMPTY\LHMAdsAI
```

Công cụ khôi phục kiểm tra AEAD, tính toàn vẹn của SQLite và từ chối ghi vào thư mục không trống; tạo local-settings theo Windows user mới bằng DPAPI. Sau đó đăng nhập bằng tài khoản nội bộ cũ. Cần cấp lại license cho Device ID mới nếu chuyển máy; Google/Meta có thể yêu cầu cấp lại quyền. **Không tự xóa dữ liệu máy cũ trước khi nghiệm thu trên máy mới.**

**Lưu ý:** Đây là công cụ Python hỗ trợ kỹ thuật offline, chưa phải nút khôi phục tự động trong EXE. Chỉ dùng khi khách đồng ý. Sao lưu mã hóa chứa Ads credentials, nên bảo vệ mật khẩu là yêu cầu quan trọng.

## Báo cáo kiểm tra trước thương mại

Màn hình Bản quyền cung cấp JSON chỉ chứa trạng thái: edition, trạng thái license, SQLite integrity check, cấu hình OAuth, số lượng tài khoản và các mục chưa xác minh. **Không** có Ads token, Customer ID, email, mật khẩu hay Device ID.

Trạng thái OAuth `configured` chỉ là đã lưu cấu hình, **không** xác nhận Meta/Google API thật hoạt động. Bản preflight cũng không tự chứng minh EXE đã ký số Authenticode hoặc hệ thống thanh toán hoạt động. Các bước này cần nghiệm thu bên ngoài.
