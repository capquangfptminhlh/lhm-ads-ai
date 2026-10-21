# Sao lưu & khôi phục dữ liệu — LHM Ads AI

Tài liệu này nói đúng những gì đã được kiểm chứng bằng diễn tập tự động
(`tools/restore_drill.py`, test: `tests/test_restore_drill.py`), những gì
chưa được chứng minh, và quy trình khôi phục cho khách hàng **như nó tồn
tại hôm nay**.

## 1. Cơ chế sao lưu hiện tại

- Trong ứng dụng desktop: mục **Bản quyền → Sao lưu dữ liệu có mã hóa**,
  xuất file `lhm-ads-backup.lhmbak`.
- File chứa: một bản chụp nhất quán của database SQLite **và** MASTER_KEY
  của máy (để mở lại các token Ads đã lưu dạng mã hoá).
- Bảo vệ bằng mật khẩu **riêng do khách đặt** (16–256 ký tự): khoá dẫn
  xuất bằng Scrypt, mã hoá AES-256-GCM (`ads_core/secure_backup.py`).
- Không bao giờ chứa: session đăng nhập đang hoạt động (bị xoá khỏi bản
  chụp có chủ đích), giấy phép bản quyền theo máy, file cấu hình DPAPI
  của Windows, token Ads dạng thô.

## 2. Diễn tập đã chứng minh điều gì

Drill chạy end-to-end bằng chính code của sản phẩm (không viết lại mã
hoá): tạo dữ liệu → xuất backup → khôi phục vào thư mục trống khác →
kiểm chứng. Kết quả lần chạy ghi nhận: **14/14 PASS**:

- User admin còn nguyên sau khôi phục và **mật khẩu đăng nhập kiểm chứng
  được** bằng hàm của sản phẩm.
- Dòng tài khoản khớp từng trường với bản gốc; số dòng mọi bảng khớp
  (trừ `sessions` = 0 vì bị loại có chủ đích).
- SHA-256 của file DB sau khôi phục **trùng khớp** SHA-256 của snapshot
  bên trong file backup — dữ liệu không lệch một byte.
- MASTER_KEY khôi phục khớp máy gốc nên token Ads đã lưu vẫn mở được;
  SESSION_SECRET được cấp mới.
- Hành vi "fail-closed": **sai mật khẩu → bị từ chối**; **sửa 1 byte**
  trong file backup → **bị từ chối** (toàn vẹn AES-GCM); khôi phục đè lên
  thư mục đã có dữ liệu → **bị từ chối** (không bao giờ ghi đè).

Có sẵn trong bộ test cũ (`tests/test_secure_backup.py`): đường xuất
backup qua HTTP phải có đăng nhập admin + CSRF + máy desktop + loopback,
và nội dung backup không lộ token thô khi quét byte.

## 3. Diễn tập KHÔNG chứng minh điều gì

- **Chưa chạy trên Windows thật**: drill chạy headless trên Linux, nơi
  `local-settings.json` lưu dạng JSON thường (chmod 0600). Trên Windows,
  file đó được bọc bằng **DPAPI** theo tài khoản Windows — nhánh code đó
  chỉ chạy được trên Windows và cần nghiệm thu trên máy Windows thật.
- **Không qua giao diện desktop**: drill gọi trực tiếp các hàm mà
  endpoint desktop và công cụ hỗ trợ sử dụng; lớp cổng đăng nhập/loopback
  do test HTTP riêng bao phủ, không nằm trong drill này.
- **Chưa thử với dữ liệu lớn**: giới hạn hiện tại là database ≤ 64 MB;
  lớn hơn sẽ bị từ chối và cần quy trình hỗ trợ riêng.
- Dữ liệu seed là tối thiểu (1 admin + 1 tài khoản demo). Các bảng do
  module advisor/autopilot tạo lười (lazy) sẽ có mặt trong backup của
  khách thật vì snapshot chụp toàn bộ file DB, nhưng drill không seed
  dữ liệu cho từng bảng đó.

## 4. Quy trình khôi phục cho khách — như hiện nay

Khôi phục hiện là **thao tác hỗ trợ có người hướng dẫn**, chưa có nút
"Khôi phục" trong ứng dụng:

1. Cài LHM Ads AI trên máy mới (hoặc chuẩn bị **một thư mục dữ liệu
   hoàn toàn trống**). Không khôi phục đè lên thư mục đang có dữ liệu —
   công cụ sẽ từ chối.
2. **Đóng hẳn ứng dụng** trên máy đích.
3. Chạy công cụ hỗ trợ:
   `python tools/customer_restore.py --backup <file.lhmbak> --destination <thư mục trống>`
   và **tự nhập mật khẩu sao lưu** khi được hỏi (mật khẩu bị ẩn khi gõ).
4. Mở lại ứng dụng, **đăng nhập lại** bằng tài khoản cũ (session không
   được chuyển sang).
5. **Xin cấp lại bản quyền** cho mã máy mới: giấy phép gắn theo máy,
   không chuyển theo backup — đây là chủ đích thiết kế, không phải lỗi.
6. Kiểm tra danh sách tài khoản Ads đã trở lại; các token đã lưu vẫn dùng
   được nhờ MASTER_KEY đi kèm trong backup.

Thời gian thao tác thuần tuý: vài phút cho database thông thường, cộng
thời gian chờ cấp lại bản quyền.

## 5. Mật khẩu sao lưu — cảnh báo giữ gìn

- **Quên mật khẩu sao lưu = mất backup vĩnh viễn.** Không có khoá dự
  phòng, không có "quên mật khẩu", bên bán cũng không khôi phục hộ được
  — đây là tính chất của mã hoá đầu-cuối, không phải thiếu sót hỗ trợ.
- **Không bao giờ gửi mật khẩu sao lưu cho hỗ trợ.** Quy trình chuẩn:
  khách tự gõ mật khẩu trên máy của mình. Ai xin mật khẩu sao lưu của
  bạn đều không phải quy trình của LHM.
- Không gửi kèm file `.lhmbak` và mật khẩu qua cùng một kênh (ví dụ cùng
  một email/chat). Lưu mật khẩu trong trình quản lý mật khẩu hoặc két
  riêng, tách khỏi nơi lưu file backup.
- Mỗi lần xuất backup là một file độc lập với muối (salt) và nonce ngẫu
  nhiên riêng; đổi mật khẩu sao lưu nghĩa là xuất file mới.

## 6. Kỳ vọng khôi phục — nói thẳng

| Tình huống | Kết quả thực tế |
|---|---|
| Mất máy / hỏng ổ, còn file backup + nhớ mật khẩu | Khôi phục được toàn bộ dữ liệu tài khoản, cấu hình; phải đăng nhập lại và xin cấp lại bản quyền cho máy mới |
| Còn file backup, quên mật khẩu | **Không khôi phục được.** Không có ngoại lệ kỹ thuật |
| Mất cả file backup | Không có bản sao nào khác — phần mềm chạy local-first, bên bán không giữ dữ liệu của khách |
| Database > 64 MB | Công cụ từ chối; liên hệ hỗ trợ để có quy trình riêng |
| Muốn khôi phục đè lên cài đặt đang chạy | Không được — phải dùng thư mục trống và đóng ứng dụng |

Khuyến nghị vận hành: xuất backup sau mỗi thay đổi quan trọng (thêm tài
khoản, đổi cấu hình), giữ tối thiểu 2 bản ở 2 nơi khác nhau, và thử
khôi phục định kỳ bằng drill này trước khi cần đến thật.
