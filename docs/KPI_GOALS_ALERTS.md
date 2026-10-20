# Mục tiêu CPA / ROAS riêng từng tài khoản Ads

**Chức năng:** Theo dõi mức độ đạt mục tiêu kinh doanh ngay trên máy Windows của khách hàng, thông qua số liệu API quảng cáo được cấp quyền. Tạo cảnh báo xem xét, **không tự đổi giá thầu, ngân sách hay chiến lược**.

## Thao tác trong LHM Ads AI
1. Cài EXE, kích hoạt bản quyền và kết nối tài khoản Google Ads bằng OAuth có quyền đọc báo cáo.
2. Vào **Cảnh báo → Mục tiêu hiệu suất theo tài khoản**. Chọn đúng khách hàng, tiền tệ, chỉ tiêu CPA tối đa hoặc ROAS tối thiểu.
3. Điền mục tiêu và ngưỡng tối thiểu: mặc định ít nhất 100 click và 5 chuyển đổi trong 7 ngày. Bật cảnh báo, bấm **Lưu mục tiêu**.
4. Bấm **Quét cảnh báo ngay**, hoặc bật tác nhân giám sát Windows để chương trình quét định kỳ (bộ quét chiến dịch chỉ tối đa một lần mỗi ngày/tài khoản; nút quét thủ công vẫn tuân thủ thời gian nghỉ).
5. Nếu CPA cao hơn mục tiêu trên 20%, hoặc ROAS thấp hơn mục tiêu trên 20%, sẽ xuất hiện cảnh báo kèm mức độ. Người quản trị xem thông tin trước khi quyết định kế hoạch chỉnh sửa.
6. Khi chiến dịch được quét lại và số liệu đã cải thiện, cảnh báo của chiến dịch đó chuyển **Đã phục hồi**. Không tự kết luận đã hết vấn đề nếu chiến dịch không nằm trong kết quả API trả về.

## Giới hạn dữ liệu
- Hiện hỗ trợ **Google Ads** với `metrics.conversions` và `metrics.conversions_value` cấp chiến dịch. Cần thiết lập conversion tracking và xác thực attribution trước khi dùng chỉ số kinh doanh.
- **Meta Ads:** chưa chuẩn hóa hành động chuyển đổi và doanh thu theo mục tiêu từng tài khoản. Vì vậy không cho bật CPA/ROAS alert trên Meta, tránh báo sai. Vẫn có các quy tắc cảnh báo cơ bản khác.
- Số liệu Google là kỳ **7 ngày gần nhất**, có thể bị trễ chuyển đổi và không tương đương doanh thu thực tế. ROAS là *hệ số* (3 = 300%), không phải tỷ lệ % nhập 300.
- Biên độ cảnh báo mặc định là 20%. Nếu CPA vượt gấp 1,5 lần mục tiêu hoặc ROAS còn không quá một nửa mục tiêu, đánh dấu mức độ cao để người quản lý ưu tiên xem xét.
- Cảnh báo **không phải AI tự tăng/giảm ngân sách**; AI OpenRouter là tùy chọn và không được cấp quyền API ghi.

## Bảo mật
- Mục tiêu và cảnh báo lưu vào SQLite của chính người dùng; chỉ người quản trị có thể sửa.
- Mọi API đều giới hạn dữ liệu theo đơn vị `org_id`. Token Google/Meta không được đưa vào thông báo cảnh báo.
- Dữ liệu demo không được dùng để tạo cảnh báo kinh doanh và không được dùng để thực thi thay đổi.
- Khi máy ngủ/tắt/mất Internet thì không thể bảo đảm giám sát 24/7; không cần dùng VPS tập trung nhưng phải duy trì máy Windows luôn chạy.

**Kiểm thử:** Có bài test cho mục tiêu theo khách hàng, CSRF, quyền sửa của admin, Meta không hỗ trợ, thiếu chuyển đổi, chéo tiền tệ, cảnh báo phục hồi và việc không xóa cảnh báo khi chiến dịch vắng khỏi lần quét.
