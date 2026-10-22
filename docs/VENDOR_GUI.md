# LHM Ads AI — Phần mềm quản lý bản quyền dành riêng bên bán

Repo cung cấp thêm **LHM-Ads-AI-Vendor.exe**: ứng dụng Windows tách biệt với EXE quản lý Google/Meta Ads của khách. Bản này **không tích hợp vào EXE khách hàng**, không giữ token Ads và không kết nối ngân hàng.

## Trên máy của chủ phần mềm

1. Lấy artifact GitHub Actions tên **LHM-Ads-AI-VENDOR-ONLY-Windows** từ workflow `Build LHM Vendor License Manager`. Chỉ chủ sở hữu/bộ phận phát hành sử dụng; không gửi file quản trị cho khách. EXE chưa ký Authenticode, Windows có thể cảnh báo Unknown Publisher.
2. Nếu chưa có bộ khóa ký license, chạy **một lần** `windows/vendor-start.ps1` theo `docs/VENDOR_ONE_CLICK.md` trên máy này để tạo bộ khóa riêng có mật khẩu và build đúng Commercial Candidate. **Không tạo lại khóa** sau khi có khách.
3. Chạy `LHM-Ads-AI-Vendor.exe`. Mọi file private và database chỉ nằm trong `%LOCALAPPDATA%\LHMAdsAI-Vendor`. Công cụ không đồng bộ dữ liệu lên GitHub hoặc công ty.
4. Khách mở bản **Commercial** của chính chủ, lấy Device ID tại Bản quyền rồi gửi **chỉ mã máy**. Trong GUI, điền `KH001` và Device ID → **Đăng ký khách**.
5. Kiểm tra **tiền đã thực nhận** tại ứng dụng ngân hàng của bên bán. Điền mã biên nhận nội bộ `TT-KH001-001`, mật khẩu bộ khóa ký, đánh dấu hộp *Tôi đã đối chiếu tiền thật vào ngân hàng*, rồi bấm **Ký & cấp / gia hạn 30 ngày**.
6. GUI tạo file `.json` tại `%LOCALAPPDATA%\LHMAdsAI-Vendor\issued-licenses\KH001\<LICENSE_ID>.json`. Chỉ gửi file JSON cho khách để dán vào Bản quyền. Không gửi `vendor-private-key.pem` hoặc mật khẩu.
7. Khi gia hạn, chọn khách, dùng **mã biên nhận mới** sau thanh toán; công cụ dùng license gần nhất để cộng thêm 30 ngày. Nếu mất license gốc, phải khôi phục bản sao lưu, không tự đặt lại hạn.
8. Các nút **Xuất CSV**, **Sao lưu sổ** dùng để lưu bản sao ngoại tuyến riêng của bên bán. File `.sqlite3` sao lưu nên lưu trong kho mã hóa riêng, không gửi qua GitHub/Zalo.

## Chính sách an toàn

- Mỗi lần cấp license yêu cầu thao tác xác nhận tiền của người bán. **Không có kết nối ngân hàng tự động**; checkbox chỉ là lời xác nhận của nhân viên, không phải bằng chứng thanh toán độc lập.
- Không cho phép dùng lại cùng mã biên nhận đã ghi, ký bằng khóa không khớp public, gia hạn từ license cũ hơn hoặc tự động ghi đè license hiện có.
- Chủ sở hữu phải sao lưu khóa riêng mã hóa ít nhất hai nơi an toàn.
- Bản Commercial của khách vẫn cần được nghiệm thu live Google/Meta API và ký duyệt thủ công trước bán.
- EXE quản lý bên bán cũng chưa ký số Windows Authenticode theo lựa chọn chủ sở hữu.

[Quy trình phát hành Commercial không chứng thư](COMMERCIAL_UNSIGNED.md) · [Đăng ký/khởi tạo khóa](VENDOR_ONE_CLICK.md)
