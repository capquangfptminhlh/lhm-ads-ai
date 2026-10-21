# Nghiệm thu trực tiếp (Live Acceptance) — LHM Ads AI

Tài liệu này là quy trình nghiệm thu bằng **tài khoản quảng cáo thật** và
**máy Windows thật**. Các bước này chỉ chủ sở hữu thực hiện được (cần tài
khoản Google/Meta của chủ sở hữu, quyền duyệt ứng dụng của hai nền tảng và
máy Windows cá nhân). Mọi mục trong tài liệu này mặc định là **NOT_RUN**
cho tới khi chủ sở hữu chạy và ghi kết quả vào bảng ký duyệt ở mục D.

## 0. Tiền nghiệm thu tự động (chạy trước, trên máy bất kỳ)

```bat
python tools\acceptance_preflight.py
```

Công cụ này kiểm tra offline mọi thứ kiểm tra được mà không cần tài khoản
thật: app khởi động và trả `/healthz`, biến môi trường lõi
(`MASTER_KEY`, `SESSION_SECRET`), tên biến môi trường đúng như code đọc
(Google: `GOOGLE_OAUTH_CLIENT_ID`, `GOOGLE_OAUTH_CLIENT_SECRET`,
`GOOGLE_ADS_DEVELOPER_TOKEN`; Meta: `META_APP_ID`, `META_APP_SECRET`),
tài nguyên tĩnh (gồm font Inter đóng gói), tính nhất quán phiên bản API
mặc định, và vòng ký–xác minh giấy phép bằng khóa dùng một lần.
Mã thoát khác 0 khi có dòng FAIL — sửa hết FAIL trước khi đi tiếp.
Thiếu cấu hình nhà cung cấp chỉ là NOT_RUN (chưa cấu hình), không phải lỗi.

Bằng chứng cần lưu: ảnh chụp/toàn văn bảng kết quả preflight, kèm mã SHA
của bản build đang nghiệm thu (`git rev-parse HEAD` hoặc file
`LHM-Ads-AI.sha256` đi cùng EXE).

## A. Google Ads — nghiệm thu trực tiếp

Điều kiện tiên quyết:

- Google Cloud project đã bật Google Ads API; OAuth client đã tạo
  (theo `docs/OAUTH_CONNECT.md` và `docs/CONNECT_PROVIDERS.md`).
- Quyền truy cập Google Ads API ở mức production đã được duyệt cho
  project/token (lưu ý thay đổi mô hình truy cập được ghi trong
  `docs/LOCAL_DESKTOP.md`). Nếu quyền mới ở mức test/explorer thì chỉ
  nghiệm thu được trên tài khoản test — ghi rõ vào bảng ký duyệt.
- Có sẵn **một tài khoản Google Ads TEST** (test account) riêng cho
  nghiệm thu. Mọi thao tác ghi chỉ làm trên tài khoản test này.
- Biến môi trường đã đặt trên máy chạy app: `GOOGLE_OAUTH_CLIENT_ID`,
  `GOOGLE_OAUTH_CLIENT_SECRET`, `GOOGLE_ADS_DEVELOPER_TOKEN`
  (tùy chọn `GOOGLE_ADS_API_VERSION`, mặc định `v25`).

Các bước trong app:

1. Mở app → **Tài khoản Ads** → thẻ **Google Ads** → **Cấu hình Google
   OAuth** (nếu được yêu cầu) → **Đăng nhập Google Ads**, cấp quyền ở
   trình duyệt hệ thống.
2. Quay lại app, chọn đúng tài khoản TEST, bấm lưu.
3. Bấm **Kiểm tra API**: báo cáo 7 ngày phải trả về dữ liệu (kể cả 0 dòng
   có cấu trúc hợp lệ) mà không báo lỗi quyền/token.
4. Mở **Tổng quan**: số liệu của tài khoản test xuất hiện, chip nguồn ghi
   dữ liệu quảng cáo thật.
5. Thao tác ghi có kiểm soát: ở **Chiến dịch**, tạo một kế hoạch tạm dừng
   (pause plan) cho một chiến dịch của tài khoản TEST → duyệt kế hoạch →
   xác nhận trong Google Ads (giao diện chính thức) rằng chiến dịch đã
   tạm dừng thật. Sau đó khôi phục trạng thái nếu cần.
6. Chụp bằng chứng: (a) màn hình Kiểm tra API thành công; (b) dòng báo cáo
   trả về; (c) kế hoạch tạm dừng + trạng thái đã duyệt trong app;
   (d) trạng thái chiến dịch tương ứng phía Google Ads.

Đạt khi: đọc báo cáo thật thành công và một thay đổi đã duyệt áp dụng
đúng lên tài khoản test. Ngoài tài khoản test: **không** thao tác ghi.

## B. Meta Ads — nghiệm thu trực tiếp

Điều kiện tiên quyết:

- Meta Developer App đã tạo; App ID/Secret đã cấu hình
  (`META_APP_ID`, `META_APP_SECRET`; tùy chọn `META_GRAPH_VERSION`,
  mặc định `v24.0`).
- App Review đã duyệt hai quyền: `ads_read` (đọc) và `ads_management`
  (cho tính năng tạm dừng có duyệt). Đặt
  `META_OAUTH_SCOPES=ads_read,ads_management` **chỉ sau khi** app đã được
  duyệt cả hai quyền. Nếu mới duyệt `ads_read`, phần ghi của mục này ghi
  NOT_RUN — không coi là đạt.
- Một tài khoản quảng cáo Meta dùng riêng cho nghiệm thu (test/thử
  nghiệm), không dùng tài khoản đang chạy doanh thu thật cho bước ghi.

Các bước trong app:

1. **Tài khoản Ads** → thẻ **Meta Ads** → **Cấu hình Meta App** →
   **Đăng nhập Meta Ads**, cấp quyền ở trình duyệt hệ thống.
2. Chọn tài khoản nghiệm thu, bấm lưu, bấm **Kiểm tra API**: Insights
   7 ngày trả về dữ liệu hợp lệ.
3. Mở **Tổng quan** xác nhận số liệu Meta hiển thị.
4. Thao tác ghi có kiểm soát (chỉ khi có `ads_management`): tạo kế hoạch
   tạm dừng một chiến dịch của tài khoản nghiệm thu → duyệt → xác nhận
   phía Meta Ads Manager rằng chiến dịch đã tạm dừng thật.
5. Bằng chứng như mục A: ảnh Kiểm tra API, dòng Insights, kế hoạch + duyệt
   trong app, trạng thái tương ứng phía Meta.

## C. Windows EXE — nghiệm thu trên máy Windows thật

Dùng đúng artifact từ workflow build Windows (file `LHM-Ads-AI.exe` +
`LHM-Ads-AI.sha256`; đối chiếu hash trước khi cài). Ghi lại: bản build là
pilot hay thương mại (mục EDITION trong kiểm tra sẵn sàng của app).

1. **Cài đặt/khởi chạy lần đầu**: chạy EXE, hoàn thành thiết lập tài
   khoản quản trị đầu tiên (trang setup), đăng nhập được vào Studio.
2. **Khởi động lại máy (reboot)**: sau khi reboot, mở lại EXE → dữ liệu,
   tài khoản Ads đã kết nối và giấy phép vẫn còn nguyên; đăng nhập lại
   bình thường.
3. **Đóng giao diện, giám sát vẫn chạy**: bật Giám sát nền + **Chạy nền
   khi đăng nhập Windows** (khóa Run ở HKCU) ở trang Bản quyền; đóng cửa
   sổ app; chờ qua ít nhất một chu kỳ đọc báo cáo; mở lại app và kiểm tra
   ở trang Bản quyền có mẫu giám sát mới ghi trong lúc giao diện đóng.
   Lưu ý đúng bản chất: giám sát chỉ chạy khi máy bật, đã đăng nhập
   Windows và có Internet — không phải 24/7 tuyệt đối.
4. **Ngủ/thức (sleep/wake)**: cho máy ngủ ít nhất 15 phút rồi đánh thức;
   app mở lại được, giám sát tiếp tục ghi mẫu mới, không treo tiến trình
   (kiểm tra Task Manager không còn tiến trình mồ côi chiếm cổng 8765).
5. **Sao lưu → gỡ cài đặt → cài lại → khôi phục**: xuất bản sao lưu mã
   hóa (.lhmbak) ở trang Bản quyền (mật khẩu ≥ 16 ký tự, lưu riêng);
   gỡ/xóa bản cài đặt; cài lại EXE; khôi phục theo quy trình hỗ trợ
   trong `docs/CUSTOMER_BACKUP.md` trên thư mục dữ liệu trống; đăng nhập
   và xác nhận dữ liệu quay lại đầy đủ. Giấy phép theo máy phải kích hoạt
   lại nếu đổi máy — cùng máy thì kiểm tra trạng thái giấy phép còn hạn.

Bằng chứng: ảnh chụp từng bước chính + ghi thời gian bắt đầu/kết thúc,
phiên bản Windows, và mọi thông báo lỗi gặp phải (kể cả không có lỗi).

## D. Bảng ký duyệt

| # | Hạng mục | Kết quả (PASS/FAIL/NOT_RUN) | Ngày | Build SHA | Bằng chứng (đường dẫn/ảnh) | Ghi chú |
|---|----------|------------------------------|------|-----------|------------------------------|---------|
| 0 | Preflight tự động (`tools/acceptance_preflight.py`) | NOT_RUN | | | | |
| A1 | Google: đăng nhập OAuth + chọn tài khoản test | NOT_RUN | | | | |
| A2 | Google: Kiểm tra API đọc báo cáo thật | NOT_RUN | | | | |
| A3 | Google: kế hoạch tạm dừng được duyệt áp dụng đúng trên tài khoản test | NOT_RUN | | | | |
| B1 | Meta: đăng nhập OAuth + chọn tài khoản nghiệm thu | NOT_RUN | | | | |
| B2 | Meta: Kiểm tra API đọc Insights thật | NOT_RUN | | | | |
| B3 | Meta: kế hoạch tạm dừng được duyệt áp dụng đúng (cần `ads_management`) | NOT_RUN | | | | |
| C1 | EXE: cài đặt + thiết lập lần đầu + đăng nhập | NOT_RUN | | | | |
| C2 | EXE: reboot — dữ liệu/giấy phép còn nguyên | NOT_RUN | | | | |
| C3 | EXE: đóng giao diện, giám sát nền vẫn ghi mẫu mới | NOT_RUN | | | | |
| C4 | EXE: sleep/wake — app và giám sát hồi phục | NOT_RUN | | | | |
| C5 | EXE: sao lưu → gỡ → cài lại → khôi phục thành công | NOT_RUN | | | | |

Người nghiệm thu: ______________________  Ngày ký: ______________

**Trạng thái hiện tại:** toàn bộ các mục A, B, C đều **NOT_RUN** — chúng
chưa từng được thực thi bằng tài khoản thật/máy Windows thật trong quá
trình phát triển (test tự động của repo dùng HTTP mock). Chỉ mục 0 có thể
chuyển sang PASS bằng máy móc; các mục còn lại chỉ chuyển trạng thái khi
chủ sở hữu chạy đúng quy trình trên và lưu bằng chứng. Không dùng kết quả
CI xanh thay cho nghiệm thu trực tiếp.
