# LHM Ads AI — cài và chạy trên chính máy khách hàng (không VPS)

## Máy Windows

1. Tải file `LHM-Ads-AI.exe` từ workflow Windows, kiểm tra nguồn tệp. Mở EXE, tạo Admin lần đầu.
2. EXE chỉ nghe `127.0.0.1:8765`; trình duyệt mở `http://localhost:8765/studio`.
3. Trong **Cài đặt → Kết nối quảng cáo ngay trên máy này**, nhập các thông số ứng dụng OAuth của **chính mình**.
4. Trong **Tài khoản quảng cáo**, nhấn Google Ads hoặc Meta Ads, đăng nhập trên **trình duyệt hệ thống**, chọn tài khoản để thêm.
5. Toàn bộ database và khóa mã hóa của phần mềm được lưu dưới `%LOCALAPPDATA%\LHMAdsAI` theo Windows user (hoặc `LHM_DATA_DIR`), không được đồng bộ tới VPS. Sao lưu cẩn thận và bảo vệ tài khoản Windows.

## Google Ads — Desktop OAuth + PKCE

- Tạo Google Cloud project, bật Google Ads API, cấu hình quyền API và OAuth Consent, tạo Client ID loại **Desktop app**; người dùng nhập Client ID và Client Secret (nếu được cấp) tại máy. Không đóng gói khóa bí mật nhà phát triển vào EXE.
- OAuth chạy bằng callback `http://localhost:8765/api/oauth/google/callback`, PKCE S256, state ràng buộc session.
- Từ 9/9/2026, Google Ads API đã sunset developer token: truy cập theo **quyền Google Cloud project**. Nếu chưa được duyệt quyền production, không thể dùng tài khoản Ads thật dù đã login Google thành công.
- Google OAuth client loại Desktop là public client; Client Secret không được xem là bí mật an toàn tuyệt đối trên PC.

## Meta Ads — giới hạn nền tảng

- Meta App ID + Secret do **người sở hữu ứng dụng** nhập tại máy; không nhúng chung vào EXE gửi cho người khác.
- Meta có thể cho phép redirect localhost HTTP trong **Development**, với người dùng được gán vai trò trên App. **Live app** và phân phối đại trà có thể bắt buộc redirect HTTPS được đăng ký, duyệt `ads_read` / `ads_management`. Vì thế không cam kết Meta production OAuth 1 chạm offline 100%.
- Với tài khoản của chính mình, lựa chọn thay thế là nhập API token được phép vào phần **Kết nối tài khoản** (lưu mã hóa tại máy). Không nhập mật khẩu Facebook.

## Quyền và an toàn

- Có MCP stdio chỉ đọc và yêu cầu khóa quản trị có hạn, không mở HTTP MCP trên Internet/LAN; ứng dụng web vẫn chỉ localhost. Không dùng cùng file database giữa các máy, không chép MASTER_KEY chung.
- Các secret ở trạng thái mã hóa bằng khóa ứng dụng trên máy nhưng thiết bị bị chiếm quyền có thể làm lộ khóa. Nên mã hóa ổ đĩa, có mật khẩu Windows và khóa màn hình.
- OpenRouter *không phải chạy local*: nếu người dùng tự bật và cho phép chia sẻ, câu hỏi và thống kê tổng hợp sẽ được gửi ra dịch vụ OpenRouter. Nếu không bật, phân tích hoạt động theo quy tắc nội bộ.
- Không có xác thực với account Ads thật trong CI. Test mock không thay thế duyệt quyền/app review của Google hoặc Meta.
