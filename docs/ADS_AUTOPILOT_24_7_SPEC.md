# LHM Ads AI — Định hướng sản phẩm: AI Ads Autopilot 24/7

**Mục tiêu do chủ dự án xác nhận (20/10/2026):** Phần mềm Windows cài trên máy từng khách hàng (không cần VPS) để quản lý nhiều tài khoản Google Ads / Meta Ads, AI giám sát 24/7, phân tích và tối ưu chiến dịch, có khả năng **thực sự** thay đổi giá thầu, ngân sách, chiến lược đặt giá thầu và trạng thái chiến dịch **qua API chính thức**.

## 0. Tình trạng hiện có — KHÔNG ĐƯỢC GỌI LÀ AUTOPILOT HOÀN CHỈNH

_Cập nhật 21/10/2026 theo code trên main (bản trước của mục này đã lỗi thời):_

- Windows native-window EXE / local loopback, giao diện, đăng nhập nội bộ và lưu trữ SQLite mã hóa: đã có mã nguồn.
- Google/Meta OAuth và báo cáo: đã có mã nguồn; **chưa xác nhận bằng tài khoản Ads thật và cấp quyền thật** (Google ghi rõ "not live-validated").
- OpenRouter: phân tích nhóm chỉ số tổng hợp khi người dùng bật; không có quyền ra lệnh thay đổi quảng cáo.
- Meta và Google: đều đã có mã *pause campaign* sau duyệt admin, và thay đổi ngân sách/giá thầu qua kế hoạch có giới hạn (autopilot plans) mà admin phải duyệt **từng** kế hoạch; không có thực thi tự động không người duyệt, không đổi chiến lược đặt giá thầu.
- Báo cáo theo campaign đã có conversions, conversion_value, CPA, ROAS (Google đầy đủ; Meta chỉ từ một sự kiện chuyển đổi được chọn, cửa sổ 7d_click, đúng tiền tệ).
- Đã có background agent Windows (`--agent-only`, tự chạy qua HKCU Run khi người dùng bật, cần license còn hạn): poll báo cáo theo chu kỳ 15–240 phút và quét advisor 1 lần/ngày/tài khoản, chỉ đọc, không sửa chiến dịch. Agent chỉ chạy khi máy bật/đăng nhập/có mạng — **không phải** Windows service và không giám sát được khi máy tắt hoặc ngủ.
- **Chưa** có: thay đổi chiến lược đặt giá thầu, auto-limited không người duyệt, rollback tự động, và bằng chứng nghiệm thu live trên Windows với tài khoản thật (reboot, đóng UI, sleep/wake).
- Không kết nối MCP; không lưu khóa API khách hàng trong repo hoặc chia sẻ một khóa chung giữa các EXE.

## 1. Năm phân hệ cốt lõi

1. **Trung tâm tài khoản:** Đại lý -> khách hàng -> tài khoản Ads -> chiến dịch -> nhóm quảng cáo -> keyword/adset; phân quyền và health trạng thái OAuth.
2. **Data Collector 24/7:** Đồng bộ lịch sử theo kỳ và số liệu mới, rate limit/backoff theo API; mỗi tài khoản có độ trễ và timestamp nguồn. Theo dõi spend, clicks, CPC, conversions, conversion value, CPA, ROAS, frequency (Meta), impression share/search terms (Google) khi được cấp quyền.
3. **Phân tích AI:** Phát hiện lãng phí/bất thường bằng quy tắc xác định + AI giải thích, so sánh 3/7/14/30 ngày và độ trễ chuyển đổi; không quyết định chỉ từ CTR, không dùng dữ liệu demo để thao tác thật.
4. **Policy & Execution:** Tạo đề xuất dạng JSON đã kiểm kiểu; kiểm tra quyền tài khoản, allowed action, hạn mức và trạng thái chiến lược; dry-run; phê duyệt hoặc auto-limited tùy tài khoản; gọi API chính thức; verify kết quả, ghi audit.
5. **Cảnh báo và khôi phục:** Cảnh báo tại app/Windows, tùy chọn email hoặc Zalo qua cấu hình người dùng; nhật ký trước/sau, snapshot cấu hình, rollback khi có thể và nút Emergency Stop.

## 2. Quy tắc vận hành tự động

Chế độ mặc định khi cài đặt là **Monitor Only**; chủ tài khoản có thể bật:
- **Advisor:** AI đọc số liệu và tạo đề xuất; không đổi chiến dịch.
- **Approval:** người quản trị duyệt từng đề xuất mới thực hiện.
- **Auto-limited:** tự thực thi một tập hành động *được cho phép rõ ràng theo từng tài khoản* sau dry-run; không tự mặc định quyền khi cập nhật phần mềm.

Các biện pháp bắt buộc cho Auto-limited:
- Cho phép theo account/campaign/action; cấm chéo tài khoản; không cho AI tự cấp quyền.
- Giới hạn +/- thay đổi giá thầu/budget theo phần trăm và giá trị tuyệt đối; trần chi/ngày; số lần mutate/ngày; cooldown; min data sample.
- **Không tự chuyển loại chiến lược** Smart Bidding, không đổi portfolio strategy, không tăng ngân sách hàng loạt hoặc thay đổi nhiều tài khoản khi chưa được duyệt cụ thể.
- Không thay đổi chiến dịch thiếu conversion tracking khi đề xuất dựa trên CPA/ROAS; không tự đoán doanh thu hoặc chuyển đổi.
- Nếu OAuth hết hạn, API lỗi, tỷ giá thiếu, số liệu trễ, account thay đổi bên ngoài hoặc trạng thái Learning: **fail-closed, cảnh báo thay vì thực thi**.
- Mọi tác vụ có idempotency key, read-before-write, read-after-write, audit trail, người dùng có thể dừng khẩn và vô hiệu hóa tự động.
- Giá thầu thủ công chỉ có hiệu lực trong chiến lược cho phép; Smart Bidding phải dùng đúng target/override và field mask theo Google Ads API.

**Không nên dùng AI để liên tục tăng/giảm bid từng vài phút.** Một số đổi chiến lược đẩy campaign vào giai đoạn Learning; theo dõi thường xuyên ≠ thay đổi thường xuyên.

## 3. Điều kiện 24/7 trên máy khách hàng

- Không VPS: cần Windows scheduled background agent chạy khi khởi động máy / đăng nhập (tùy chính sách máy), hoạt động tách khỏi cửa sổ UI; UI đóng không làm tắt collector.
- Agent chỉ mở outbound HTTPS tới Google/Meta/OpenRouter; API/UI local bind 127.0.0.1; **không mở MCP hay cổng Internet vào máy**.
- Khi máy tắt, ngủ hoặc mất Internet: **không giám sát được**; phải ghi downtime, retry/bù dữ liệu khi online lại. Muốn 24/7 tuyệt đối dù máy tắt phải có thiết bị/máy luôn bật khác.
- Check Internet không đồng nghĩa OAuth hay API Ads khỏe; từng connector phải có health/error cụ thể.
- Tải/cập nhật nhà cung cấp tuân thủ rate limits; không gửi access/refresh token tới LLM. Secret storage nên tiến tới Windows DPAPI và quản lý khóa cẩn thận.

## 4. Quy trình hành động có kiểm soát

1. Poll Ads API -> lưu nguồn, timestamp và snapshot.
2. Tính chỉ số / phát hiện bất thường bằng policy engine.
3. AI có thể diễn giải, đề xuất **không phải quyền write**.
4. ActionValidator kiểm loại chiến lược, data freshness, quyền, max delta, daily budget, min conversions, cooldown, trạng thái Learning.
5. Dry-run và hiển thị before/after + mức rủi ro.
6. Human approval hoặc auto-limited nếu opt-in còn hiệu lực.
7. Apply qua provider-specific adapter, verify từ API, audit + cảnh báo.
8. Theo dõi hậu thay đổi 24–72h; rollback khả thi nếu diễn biến xấu, không giả định mọi thay đổi đều rollback được.

## 5. Thứ tự thực hiện và nghiệm thu

### P1 — Monitoring thật (ưu tiên cao nhất)
- Windows background agent (Task Scheduler/tray) độc lập UI.
- Poll schedule (ví dụ 15 phút; configurable) với backoff/rate-limit; đồng bộ sau offline.
- Chiến dịch và chỉ số conversions, CPA, ROAS theo nguồn được API hỗ trợ; dashboard cảnh báo, history.
- Offline mocked tests; xác minh Windows runner khởi động lại, báo cáo đúng nguồn.

### P2 — Engine tối ưu kiểu đề xuất
- Định nghĩa mục tiêu theo tài khoản: leads CPA, ecommerce ROAS, traffic CPC/CTR, giới hạn chi phí, chiến dịch cấm can thiệp.
- Gợi ý phân loại: pause/rule, bid, target CPA/ROAS, daily budget, search terms/negative keywords.
- Giải thích trước/sau và nguồn dữ liệu; không hallucinate; approval workflow có audit.

### P3 — Mutate API chính thức và rollback
- Google Campaign/CampaignBudget/AdGroupCriterion/Strategy **tùy tương thích**.
- Meta Campaign/AdSet/adset bid/budget **tùy campaign setup và API permissions**.
- Dry-run, policy guard, idempotency, verify, audit, emergency-stop; fake HTTP tests và test bằng tài khoản sandbox/test thật có ủy quyền.

### P4 — Auto-limited có cho phép tường minh
- Bật riêng từng account + loại hành động; giới hạn thay đổi và cooldown.
- Can thiệp từ UI để ngắt lập tức; test tình huống rate-limit, token expired, stale data, rollback failures.
- Audit độc lập + số liệu hậu thay đổi; không tuyên bố tăng ROAS/giảm CPA khi chưa đo được.

## 6. Điều kiện bắt buộc trước khi quảng cáo 'tự động 24/7'
- Xác nhận trên Windows EXE thực với agent hoạt động khi đóng UI, reboot và máy online liên tục.
- Có tài khoản test Google/Meta chính thức; phạm vi quyền đọc/ghi được xác minh; không dùng token/secret fake trong bản thương mại.
- Ở Auto-limited: kiểm thử dữ liệu thưa, chuyển đổi trễ, campaign Learning, lỗi API, replay, concurrency, ngân sách vượt trần, đổi trạng thái ngoài app.
- Định nghĩa rõ tiền tệ, múi giờ, timestamp, timezone của quảng cáo và nơi tính ngày ngân sách.
- Cập nhật hướng dẫn sử dụng, cảnh báo rủi ro tài chính và chính sách riêng tư trước khi bán cho khách.

**Ghi chú:** Đây là đặc tả sản phẩm, không phải bằng chứng các tính năng trên đã được triển khai.