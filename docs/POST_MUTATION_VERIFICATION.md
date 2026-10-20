# LHM Ads AI — Đối soát sau chỉnh sửa Ads (Read-only Reconciliation)

## Tại sao cần bước đối soát?

Google Ads và Meta Marketing API có thể tiếp nhận lệnh sửa ngân sách / giá thầu trong khi bản đọc sau đó chưa trả về giá trị mới. Không được mặc định **API đã nhận = thay đổi thành công**, và không được tự gửi lại lệnh vì có thể khiến quảng cáo bị điều chỉnh lặp.

## Tính năng đã triển khai

- Sau khi quản trị viên phê duyệt một thay đổi, nếu kết quả được ghi là `accepted_unverified` hoặc `needs_review`, người quản trị có thể bấm **Xác minh qua API** trên trang **Autopilot**.
- Chức năng `POST /api/autopilot/plans/{id}/verify` chỉ đọc lại giá trị hiện tại bằng API chính thức. Không gọi Google mutate hay Meta update.
- Nếu giá trị khớp đề xuất: `completed` / `verified_new`. Nếu còn giá trị cũ: `accepted_unverified` / `still_old`. Nếu khác cả cũ và mới: `needs_review` / `unexpected_value`. Nếu API lỗi: giữ trạng thái và ghi `api_unavailable` mà không lưu thông báo chứa token.
- Lưu ngày kiểm tra, số lần, giá trị thực quan sát được và nhật ký audit theo từng đơn vị. Người dùng không thể đối soát kế hoạch thuộc đơn vị khác.
- Agent Windows đang bật giám sát có thể tự đọc lại **tối đa 10 kế hoạch mỗi lượt**, mỗi kế hoạch cách nhau tối thiểu **15 phút**, tối đa **12 lần**. Quá ngưỡng sẽ chờ người quản trị xử lý, không tiếp tục gửi truy vấn vô hạn.

## Điều kiện hoạt động

Người dùng cần kết nối Google/Meta bằng OAuth/token hợp lệ. Muốn tác nhân tự kiểm tra, bật **Giám sát chạy nền** trong trang Bản quyền và bảo đảm máy Windows hoạt động, Internet ổn định. Không cần VPS chung.

**Quan trọng:** Đối soát không phải rollback. Thay đổi ngoài app bởi người khác có thể khiến giá trị khác dự kiến, lúc đó phải kiểm tra thủ công. Phần mềm không tự sửa chiến lược Smart Bidding hoặc tăng chi ngân sách dựa trên trạng thái đối soát. Các API ghi hiện vẫn phải có phê duyệt quản trị và giới hạn rủi ro.

## Kiểm thử an toàn

Các bài test xác nhận: token lỗi được che nội dung, CSRF và quyền admin, chặn chéo khách hàng, chỉ xác nhận `completed` khi đọc được giá trị mới, không gửi lại lệnh Ads, giữ trạng thái khi API lỗi, hạn mức truy vấn nền và không chạy khi chưa bật giám sát. Tài khoản quảng cáo thật chưa được thử trong các bài test tự động.
