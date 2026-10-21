# Hướng dẫn sử dụng LHM Ads AI (bản Windows)

Tài liệu này dành cho người dùng cuối: cài đặt, kết nối tài khoản quảng cáo, đọc số liệu, dùng AI và Autopilot, quản lý bản quyền và sao lưu. Mọi tên nút, tên trang trong tài liệu đều lấy đúng từ giao diện phần mềm.

**Hiểu đúng về phần mềm trước khi bắt đầu**

- LHM Ads AI chạy **ngay trên máy Windows của bạn**. Dữ liệu và token quảng cáo lưu mã hóa trên máy của bạn, không có máy chủ trung tâm của bên bán giữ dữ liệu quảng cáo của bạn.
- Phần mềm **không tự ý thay đổi quảng cáo**. Mọi lệnh thay đổi (tạm dừng chiến dịch, chỉnh ngân sách/giá thầu) đều phải có người quản trị bấm duyệt từng lần.
- Tính năng giám sát nền **chỉ đọc dữ liệu** để cảnh báo. Nó chỉ hoạt động khi máy đang bật, bạn đang đăng nhập Windows và máy có Internet. Tắt máy, máy ngủ hoặc mất mạng thì không có giám sát — đây không phải dịch vụ chạy 24/7 trên đám mây.

---

## 1. Cài đặt và mở phần mềm lần đầu

1. Nhận file `LHM-Ads-AI.exe` từ bên bán. Đây là file chạy trực tiếp (portable), không phải bộ cài đặt: bạn chỉ cần lưu file vào một thư mục cố định trên máy (ví dụ `D:\LHM Ads AI\`) và mở từ đó. Đừng chạy từ thư mục tạm hoặc USB nếu muốn dùng lâu dài.
2. Nhấp đúp vào `LHM-Ads-AI.exe`. Cửa sổ phần mềm mở ra ngay trên máy (không mở tab trình duyệt).
3. Lần mở đầu tiên, màn hình **Thiết lập tài khoản quản trị** xuất hiện. Điền:
   - **Email quản trị** — email bạn dùng để đăng nhập phần mềm sau này.
   - **Mật khẩu** — tối thiểu 12 ký tự; nên có chữ hoa, chữ thường, số và ký tự đặc biệt (thanh đo độ mạnh mật khẩu nằm ngay dưới ô nhập).
   - **Nhập lại mật khẩu** — gõ lại giống hệt.
4. Bấm **Tạo tài khoản & mở Dashboard**. Phần mềm tự đăng nhập và đưa bạn vào trang **Tổng quan**.
5. Từ lần sau, chỉ cần mở EXE và đăng nhập bằng email + mật khẩu vừa tạo tại màn hình **Đăng nhập** (nút **Đăng nhập →**).

Lưu ý:

- Dữ liệu của phần mềm nằm trong thư mục `%LOCALAPPDATA%\LHMAdsAI` trên máy. Đừng xóa thư mục này.
- Muốn tắt hẳn phần mềm: đóng cửa sổ LHM Ads AI. Nếu tiến trình nền vẫn còn, mở **Task Manager** của Windows và kết thúc tiến trình LHM Ads AI.
- Gặp lỗi khi mở app, bên hỗ trợ có thể cần xem file nhật ký `%LOCALAPPDATA%\LHMAdsAI\logs\startup.log`.

## 2. Bật xác thực hai lớp (MFA) — nên làm ngay

MFA khiến kẻ có mật khẩu của bạn cũng không đăng nhập được nếu không có điện thoại của bạn.

1. Vào **Cài đặt** → mục **Xác thực hai lớp (MFA)**.
2. Bấm **Thiết lập MFA**. Phần mềm hiện một khóa bí mật và một URI.
3. Mở ứng dụng xác thực trên điện thoại (Google Authenticator, Microsoft Authenticator…) → thêm tài khoản mới → nhập khóa thủ công hoặc dán URI.
4. Nhập mã 6 số đang hiển thị trên điện thoại vào ô **Mã 6 số từ ứng dụng**, bấm **Bật MFA**.
5. Từ lần đăng nhập sau, sau khi nhập email + mật khẩu đúng, ô **Mã MFA (6 số)** sẽ hiện ra — nhập mã trên điện thoại để vào.

Muốn tắt MFA: vẫn tại mục này, nhập **Mật khẩu hiện tại** và **Mã 6 số hiện tại** rồi bấm **Tắt MFA**. Phần mềm không có mã khôi phục dự phòng: mất điện thoại khi đang bật MFA thì xem mục xử lý sự cố trong `TROUBLESHOOTING.md`.

## 3. Kết nối Google Ads

Có 2 bước: cấu hình ứng dụng Google **một lần** trên máy, sau đó đăng nhập.

### 3.1. Cấu hình ứng dụng Google (làm một lần)

1. Vào **Cài đặt** → mục **Kết nối quảng cáo ngay trên máy này** → phần **Google Ads — OAuth Desktop**.
2. Bạn cần một **Google Cloud OAuth Client ID loại Desktop app** của chính bạn:
   - Mở https://console.cloud.google.com/apis/credentials (nút **Mở Google Cloud ↗** ở trang Tài khoản Ads cũng dẫn tới đây).
   - Tạo project, bật **Google Ads API**, tạo OAuth client loại **Desktop app**.
3. Dán **Client ID** vào ô tương ứng; nếu Google có cấp **Client Secret** thì dán vào ô Client Secret.
4. Bấm **Lưu ứng dụng Google trên máy**.

### 3.2. Đăng nhập và chọn tài khoản

1. Vào **Tài khoản Ads** → chọn thẻ **Google Ads**.
2. Bấm **↗ Đăng nhập Google Ads**. Trình duyệt mặc định của Windows mở trang đăng nhập Google chính thức — **đăng nhập và cấp quyền ngay trên trang của Google, không nhập mật khẩu Google vào phần mềm**.
3. Quay lại cửa sổ LHM Ads AI: danh sách tài khoản Google Ads mà bạn có quyền sẽ hiện ở mục chờ chọn. Đánh dấu các tài khoản cần dùng và bấm lưu.
4. Kiểm tra kết nối: trong danh sách tài khoản, bấm nút **Kiểm tra API** ở tài khoản vừa thêm. "Đã lưu token" mới chỉ nghĩa là đã lưu thông tin — **Kiểm tra API** mới xác nhận đọc được báo cáo thật.

Cách khác (nâng cao): nếu đã có OAuth JSON chứa `client_id`, `client_secret`, `refresh_token`, bấm **Đã có OAuth JSON? Nhập thủ công (nâng cao) →** và dán vào.

Lưu ý: quyền truy cập Google Ads API gắn với Google Cloud project của bạn. Nếu project chưa được duyệt quyền production, đăng nhập Google thành công vẫn có thể không đọc được tài khoản thật — đây là giới hạn của Google, không phải lỗi phần mềm.

## 4. Kết nối Meta Ads (Facebook)

Tương tự Google, gồm cấu hình app một lần rồi đăng nhập:

1. Vào **Cài đặt** → **Kết nối quảng cáo ngay trên máy này** → phần **Meta Ads — App riêng**: nhập **Meta App ID** và **Meta App Secret** của ứng dụng Meta do bạn (hoặc bên bán) tạo tại https://developers.facebook.com/apps/, bấm **Lưu ứng dụng Meta trên máy**.
2. Vào **Tài khoản Ads** → chọn thẻ **Meta Ads** → bấm **↗ Đăng nhập Meta Ads**.
3. Cấp quyền trên trang Facebook mở trong trình duyệt hệ thống. Không nhập mật khẩu Facebook vào phần mềm.
4. Quay lại app, chọn các tài khoản quảng cáo được cấp quyền, bấm lưu, rồi bấm **Kiểm tra API** để xác nhận đọc được dữ liệu.

Lưu ý quan trọng về Meta:

- Quyền `ads_read` chỉ để **đọc báo cáo**. Muốn dùng tính năng tạm dừng chiến dịch Meta cần thêm quyền `ads_management` và vẫn phải qua bước phê duyệt trong app.
- Meta có thể yêu cầu app ở chế độ Live phải qua xét duyệt (App Review) và dùng Redirect URI dạng HTTPS. Nếu đăng nhập Meta bị từ chối ở chế độ Live, bạn có thể dùng cách nâng cao: bấm **Đã có Access Token Meta? Nhập thủ công (nâng cao) →** và dán Access Token hợp lệ.
- ID tài khoản Meta phải là số hoặc dạng `act_` + số.

## 5. Tài khoản Demo — để làm quen

Bấm **+ Tạo tài khoản Demo** ở trang **Tài khoản Ads** để tạo một tài khoản minh họa. Dữ liệu Demo là số liệu giả lập có gắn nhãn rõ ràng, dùng để học cách xem báo cáo. Số liệu Demo **không bao giờ** được trộn vào số liệu thật khi bạn đã kết nối tài khoản thật, và không dùng để tạo cảnh báo hay kế hoạch thay đổi quảng cáo.

## 6. Đọc Dashboard (trang Tổng quan)

- Chọn kỳ xem ở ô cạnh nút **↻ Làm mới**: **7 ngày gần nhất** hoặc **Hôm qua**. Bấm **↓ Xuất CSV** để tải báo cáo.
- Hai nhãn trạng thái ngay đầu trang cho biết nguồn số liệu:
  - **"Nguồn: dữ liệu quảng cáo thật"** — số đang xem lấy từ API của tài khoản đã kết nối.
  - **"Nguồn: chưa kết nối tài khoản"** — bạn chưa kết nối tài khoản thật nào; số hiển thị (nếu có) là Demo.
  - **"BẢN XEM THỬ DEMO"** — đang ở chế độ xem thử.
- Các thẻ số chính: **Tổng chi phí quảng cáo**, **Lượt hiển thị**, **Lượt nhấp**, **Click-through rate (CTR)**. Lưu ý CTR là tỉ lệ nhấp trên hiển thị, **không phải** tỉ lệ chuyển đổi.
- Dải **Chuyển đổi / CPA / ROAS** chỉ xuất hiện khi API của nền tảng trả về số liệu chuyển đổi cùng định nghĩa:
  - **CPA** = chi phí ÷ số chuyển đổi (mỗi chuyển đổi tốn bao nhiêu tiền).
  - **ROAS** = giá trị chuyển đổi ÷ chi phí, là **hệ số** (ROAS 3 nghĩa là 1 đồng chi phí tạo 3 đồng giá trị chuyển đổi theo báo cáo của nền tảng — không phải doanh thu thực đã về tài khoản ngân hàng của bạn).
  - Nếu dải này không hiện, nghĩa là chưa có dữ liệu chuyển đổi đủ điều kiện — phần mềm không tự suy diễn hay điền số 0 giả.
- Biểu đồ **Xu hướng chi tiêu** chỉ cộng các tài khoản **cùng đơn vị tiền tệ**. Nếu bạn có tài khoản VND và USD, dùng ô chọn **Đơn vị** để xem riêng từng loại.
- Bảng **Hiệu suất theo tài khoản** liệt kê từng tài khoản; tài khoản mất kết nối sẽ hiện thông báo rõ ràng thay vì số liệu cũ.

## 7. AI Center (trang Trợ lý quảng cáo AI)

- Mặc định trợ lý phân tích **ngay trên máy** bằng quy tắc nội bộ, không gửi dữ liệu ra ngoài. Nhãn ở góc trang ghi **PHÂN TÍCH NỘI BỘ**.
- Gõ câu hỏi tiếng Việt vào ô chat (ví dụ "Tổng hợp chi phí quảng cáo 7 ngày vừa qua") và bấm **Gửi ↗**. Có sẵn các nút gợi ý: **Tổng hợp 7 ngày**, **Tài khoản chi nhiều**, **Gợi ý chỉ số**.
- Bấm **Xem trước dữ liệu gửi đi (chỉ trên máy)** để xem chính xác nội dung sẽ được gửi nếu dùng AI bên ngoài — thao tác này không gọi ra ngoài.

### Bật OpenRouter (AI bên ngoài, tùy chọn)

Chỉ quản trị viên (Admin) mới bật được, tại **Cài đặt** → **OpenRouter AI — quản lý quảng cáo**:

1. Dán **OpenRouter API key** của bạn (khóa lưu mã hóa trên máy).
2. Chọn **Model ID** (mặc định `openai/gpt-4.1-mini`).
3. Đặt **Giới hạn lượt AI/ngày** cho toàn bộ nhân sự (từ 1 đến 200; đây là giới hạn số lượt gọi, **không phải** giới hạn tiền — muốn chặn chi phí, đặt thêm hạn mức ngay trên tài khoản OpenRouter của bạn).
4. Tích ô đồng ý **"Tôi cho phép gửi câu hỏi và thống kê quảng cáo tổng hợp tới OpenRouter và đồng ý phát sinh phí API"**.
5. Bấm **Lưu cấu hình AI**.

Dữ liệu được gửi khi bật OpenRouter: **câu hỏi bạn gõ** và **thống kê quảng cáo đã tổng hợp** (chi phí, nhấp, hiển thị, chuyển đổi theo tài khoản/kỳ). **Không gửi**: token quảng cáo, mật khẩu, tên hay ID tài khoản. Phần mềm chỉ chọn nhà cung cấp có cam kết Zero Data Retention (ZDR); model không hỗ trợ ZDR sẽ báo lỗi thay vì gửi đi nơi khác. Dù vậy, đây vẫn là dịch vụ bên ngoài và **có tính phí theo tài khoản OpenRouter của bạn**.

Trợ lý AI chỉ phân tích và đề xuất. Nó **không** tự thay đổi chiến dịch, không tự duyệt lệnh.

Tắt/bỏ OpenRouter: bỏ tích ô đồng ý và bấm **Lưu cấu hình AI**; muốn xóa hẳn khóa, bấm **Xóa API key**.

## 8. Autopilot và Phê duyệt — thay đổi quảng cáo có kiểm soát

Hiểu đúng: **Autopilot không tự chạy**. Nó là nơi tạo *kế hoạch* thay đổi; kế hoạch chỉ được gửi đi sau khi Admin bấm duyệt, và sau khi gửi phần mềm còn đọc lại API để xác minh kết quả.

### 8.1. Chính sách an toàn (trang Autopilot)

- Mặc định là **Monitor Only** (chỉ theo dõi). 
- Admin có thể đặt theo từng tài khoản: **Cho phép kế hoạch ghi sau admin duyệt**, **Biên độ tối đa mỗi lần (%)**, **Số lượt chỉnh mỗi ngày**, rồi bấm **Lưu chính sách**.
- Nút **DỪNG MỌI CHỈNH SỬA** là dừng khẩn cấp: bật lên thì không kế hoạch ghi nào được thực thi nữa. "Dừng khẩn cấp (mặc định)" nghĩa là trạng thái an toàn là trạng thái mặc định của hệ thống.

### 8.2. Tạo và duyệt kế hoạch

1. Ở trang **Autopilot**, chọn tài khoản, loại thao tác và giá trị mới → **Tạo kế hoạch chờ duyệt**. Kế hoạch xuất hiện trong danh sách với trạng thái chờ (`pending`).
2. Admin kiểm tra kỹ: đúng tài khoản chưa, đúng đối tượng (ID) chưa, giá trị cũ → mới có hợp lý không, đúng đơn vị tiền tệ chưa.
3. Bấm **Duyệt** để gửi lệnh thật lên Google/Meta, hoặc **Từ chối** để hủy kế hoạch.
4. Sau khi duyệt, trạng thái đối soát cho biết kết quả đọc lại từ API: **Đã xác minh qua API** / **API còn giá trị cũ** / **Giá trị khác dự kiến** / **Chưa đọc được API**. Nếu chưa xác minh được, bấm **↻ Xác minh qua API** để phần mềm đọc lại (thao tác này chỉ đọc, không gửi lại lệnh).

### 8.3. Tạm dừng chiến dịch (trang Phê duyệt)

1. Vào **Phê duyệt** → mục **Tạo yêu cầu tạm dừng**: chọn tài khoản, nhập **Campaign ID**, bấm **Gửi yêu cầu**. Yêu cầu chưa thực thi ngay.
2. Admin xem danh sách yêu cầu và bấm duyệt — khi đó phần mềm mới gửi lệnh **PAUSED** qua API. Hãy đọc kỹ hộp thoại xác nhận vì đây là lệnh lên tài khoản quảng cáo thật.
3. Cũng tại trang Tài khoản Ads, nút **Thu hồi** trên một tài khoản sẽ xóa token đã lưu của tài khoản đó (báo cáo thật của tài khoản sẽ ngừng hoạt động cho đến khi kết nối lại).

## 9. Cảnh báo và giám sát nền

### 9.1. Cấu hình giám sát (trang Bản quyền)

1. Vào **Bản quyền** → mục **Giám sát quảng cáo chạy nền**.
2. Tích **Bật giám sát tài khoản đã kết nối**, chọn **Chu kỳ đọc báo cáo** (15 / 30 / 60 / 120 / 240 phút), bấm **Lưu cấu hình**.
3. Muốn tác nhân tự chạy mỗi khi bạn đăng nhập Windows: bấm **Chạy nền khi đăng nhập Windows**. Muốn tắt tự chạy: bấm **Tắt tự chạy**.
4. Giám sát chỉ chạy khi **bản quyền còn hiệu lực** và các điều kiện ở đầu tài liệu thỏa mãn (máy bật, đã đăng nhập Windows, có Internet).

### 9.2. Xem cảnh báo (trang Cảnh báo)

- **Cảnh báo tối ưu 24/7**: phần mềm quét báo cáo và ghi nhận các dấu hiệu cần xem xét, ví dụ CTR cực thấp dù đã có nhiều lượt nhấp/hiển thị, hoặc chiến dịch Google có nhiều nhấp nhưng không ghi nhận chuyển đổi. Đây là **gợi ý để bạn kiểm tra**, không phải kết luận chiến dịch có vấn đề và không tự động xử lý.
- Bấm **Quét cảnh báo ngay** để quét thủ công một tài khoản (quét thủ công cũng có thời gian nghỉ tối thiểu giữa hai lần), hoặc **Làm mới** để tải lại danh sách. Bấm **Đánh dấu đã xem** khi đã xử lý một cảnh báo.
- **Mục tiêu hiệu suất theo tài khoản**: đặt **CPA tối đa** hoặc **ROAS tối thiểu** cho từng tài khoản (với Meta phải chọn đúng một sự kiện chuyển đổi như Lead/Purchase; ROAS chỉ dùng với Purchase), đặt ngưỡng tối thiểu số click/chuyển đổi, tích **Bật cảnh báo theo mục tiêu**, bấm **Lưu mục tiêu**. Khi CPA vượt mục tiêu quá 20% hoặc ROAS thấp hơn mục tiêu quá 20%, cảnh báo sẽ xuất hiện; số liệu cải thiện trở lại thì cảnh báo chuyển **Đã phục hồi**.
- Nếu bên bán đã cấu hình Telegram cho hệ thống của bạn, cảnh báo mới và lỗi đọc dữ liệu có thể được gửi kèm tới Telegram của người vận hành (chỉ gồm mã cảnh báo và số thứ tự tài khoản nội bộ, không có token hay ID tài khoản quảng cáo).

## 10. Bản quyền: kích hoạt và gia hạn

1. Vào **Bản quyền**. Trang này hiện **Phiên bản**, **Trạng thái** và **Mã máy** của máy bạn.
2. Bấm **Sao chép mã máy** và gửi mã này cho bên bán. **Chỉ gửi mã máy — không bao giờ gửi token quảng cáo hay mật khẩu cho bên bán.**
3. Bên bán gửi lại cho bạn file `license.json` (sau khi xác nhận thanh toán theo thỏa thuận của bạn với bên bán).
4. Dán toàn bộ nội dung file vào ô **Nhập nội dung file license.json**, bấm **Kích hoạt / Gia hạn**. Trạng thái chuyển thành đã kích hoạt kèm ngày hết hạn. Kích hoạt không cần Internet.
5. Gia hạn: lặp lại đúng các bước trên với file license mới; gia hạn sớm được cộng dồn thêm ngày.
6. Khi giấy phép hết hạn: dữ liệu của bạn **không bị xóa**, bạn vẫn xem và xuất báo cáo được, nhưng các tính năng trả phí (trong đó có giám sát nền) sẽ dừng cho đến khi gia hạn.

## 11. Sao lưu và khôi phục dữ liệu

### 11.1. Tạo bản sao lưu (nên làm trước khi đổi máy/cài lại Windows)

1. Vào **Bản quyền** → mục **Kiểm tra sẵn sàng & bảo vệ dữ liệu**.
2. Nhập **Mật khẩu sao lưu** (ít nhất 16 ký tự — đây là mật khẩu riêng cho file sao lưu, khác mật khẩu đăng nhập) và nhập lại ở ô xác nhận.
3. Bấm **↓ Tải bản sao lưu .lhmbak đã mã hóa**.
4. Lưu file `.lhmbak` ở nơi an toàn và ghi mật khẩu sao lưu ở **một nơi khác** với file. Mất mật khẩu sao lưu là mất khả năng khôi phục. **Không gửi mật khẩu sao lưu hay file backup cho bên hỗ trợ.**

### 11.2. Khôi phục

Việc khôi phục hiện **không có nút tự làm trong phần mềm** — đây là thao tác có kỹ thuật viên hỗ trợ:

1. Đóng hoàn toàn LHM Ads AI và tác nhân giám sát trên máy đích.
2. Máy đích phải là một thư mục dữ liệu **trống** (khôi phục từ chối ghi đè thư mục đã có dữ liệu).
3. Kỹ thuật viên chạy công cụ khôi phục với file `.lhmbak` của bạn; **bạn tự nhập mật khẩu sao lưu**, không đọc cho kỹ thuật viên.
4. Sau khôi phục: đăng nhập bằng tài khoản nội bộ cũ của bạn; nếu là máy mới, máy sẽ có **Mã máy mới** — cần xin cấp lại license cho mã máy mới; Google/Meta có thể yêu cầu cấp quyền lại.
5. Chỉ xóa dữ liệu ở máy cũ **sau khi** đã kiểm tra máy mới chạy đúng.

## 12. Đổi máy

1. Trên máy cũ: tạo bản sao lưu `.lhmbak` (mục 11.1).
2. Mở EXE trên máy mới, ghi lại **Mã máy** ở trang Bản quyền, gửi cho bên bán để được cấp license cho máy mới (license gắn theo máy, không tự chuyển theo).
3. Nhờ hỗ trợ khôi phục dữ liệu theo mục 11.2.
4. Kết nối lại Google/Meta nếu được yêu cầu, kiểm tra **Kiểm tra API** từng tài khoản, bật lại giám sát nền và MFA theo nhu cầu.

## 13. Tài khoản người dùng trong phần mềm, đổi mật khẩu, đăng xuất

- **Vai trò**: Admin (quản trị toàn quyền), Operator (tạo yêu cầu), Reader (chỉ xem). Chỉ Admin thấy các mục **Nhân sự**, **Nhật ký** và các nút cấu hình.
- **Thêm người dùng**: Admin vào **Nhân sự** → điền email, chọn quyền → **Tạo tài khoản**. Mật khẩu tạm sẽ hiện một lần trong khung thông báo — gửi cho người đó và yêu cầu họ đổi ngay.
- **Đổi mật khẩu của bạn**: **Cài đặt** → **Đổi mật khẩu** → nhập mật khẩu hiện tại và mật khẩu mới (ít nhất 12 ký tự) → **Đổi mật khẩu**. Đổi xong, **toàn bộ phiên đăng nhập của bạn bị đăng xuất**, hãy đăng nhập lại.
- **Khóa người dùng**: Admin bấm nút vô hiệu hóa ở danh sách Nhân sự — tài khoản đó bị khóa và mọi phiên đăng nhập của họ bị hủy.
- **Đăng xuất**: bấm biểu tượng đăng xuất **↪** ở góc phải trên cùng màn hình.
- **Nhật ký**: trang **Nhật ký** ghi lại các thao tác quản trị, đăng nhập và phê duyệt để Admin tra cứu khi cần.

---

Gặp sự cố? Xem bảng xử lý trong [TROUBLESHOOTING.md](TROUBLESHOOTING.md). Khi liên hệ hỗ trợ, hãy mô tả: bạn đang ở trang nào, bấm nút gì, thông báo lỗi nguyên văn — và **không bao giờ** gửi mật khẩu, token quảng cáo, API key hay mật khẩu sao lưu.
