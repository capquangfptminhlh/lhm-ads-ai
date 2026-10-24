# LHM Marketing Intelligence Engine — bản thiết kế triển khai

**Ngày lập:** 24/10/2026 • **Trạng thái:** tài liệu triển khai + skill lõi đọc-only v0.1; **chưa** tích hợp giám sát Ads 24/7 / Zalo approval / AI tự tạo experiments thực tế.

## 1. Mục tiêu sản phẩm

Không bán thêm một chatbot đọc CPA/ROAS. Bán một trợ lý marketing có **quy trình chuyên môn**, **trí nhớ theo từng khách**, **kiểm chứng bằng thử nghiệm** và **quyền phê duyệt rõ ràng**. Đích đo lường của khách: đơn đã xác nhận, lợi nhuận sau chi phí, CAC/CPA đủ chất lượng, tỉ lệ chốt, thời gian xử lý khách; báo cáo CPC/CTR chỉ hỗ trợ chẩn đoán. Không cam kết tự động giảm giá quảng cáo hoặc thắng đấu giá.

**Định nghĩa vòng lặp:** nguồn dữ liệu đã kiểm chứng → chẩn đoán đủ bối cảnh → đề xuất có bằng chứng → gửi Zalo → khách duyệt hoặc từ chối → *thiết bị khách trực tuyến* thực hiện thay đổi đã duyệt → so sánh với đối chứng → cập nhật tri thức.

## 2. Tình trạng mã nguồn trước đề xuất

- `ads_core/optimization_playbook.py`: đã có quy tắc ngưỡng, baseline, conflict guard, kiểm chứng outcome; tận dụng chứ không viết lại.
- `ads_core/advisor.py`: quét Ads theo kỳ, tạo finding; chưa thu thập đủ cohort theo giờ và dữ liệu CRM thật.
- `ads_core/monitoring.py`: collector read-only, 15–240 phút khi agent Windows được bật và máy đang chạy; báo cáo hiện là **LAST_7_DAYS**, không phải tín hiệu realtime.
- `ads_core/autopilot.py`: đã có kế hoạch sửa ngân sách/bid sau phê duyệt admin trong app, giới hạn thay đổi và dừng khẩn cấp; không có đường duyệt Zalo đã nghiệm thu.
- `docs/DEVICE_ONLY_ADS_DATA.md`: ràng buộc **không gửi Ads credentials, ID Ads, báo cáo thô lên Cloudflare/LHM**. SaaS control-plane có thể giữ thuê bao và request ID vô danh; data-plane Ads nằm trên thiết bị khách.
- **Mới trong nhánh này:** `ads_core/growth_intelligence.py` và `tests/test_growth_intelligence.py` là core read-only để xét đủ điều kiện đề xuất, chưa tự kết nối API hay ghi Ads.

## 3. Thư viện skill LHM: lấy kiến thức từ đâu?

Tất cả skill phải có **skill_id, version, người đánh giá, nguồn, đầu vào bắt buộc, điều kiện không áp dụng, hành động được phép, bằng chứng trước/sau và bộ test**. Không chấp nhận prompt tìm trên mạng làm quyền tự sửa tài khoản.

| Skill | Đầu vào được xác minh | Kết luận/đầu ra | Ưu tiên |
|---|---|---|---|
| Conversion Integrity | conversion actions, Tag/GA4, đơn CRM và attribution lag | tracking đúng/sai/chưa đủ dữ liệu | P0 |
| Learning & Change Guard | trạng thái bid strategy, change history, conversion cycle | quan sát / điều tra / có thể lập đề xuất | P0 (đã có lõi v0.1) |
| Website & CRO Audit | PageSpeed, Core Web Vitals, mobile UX, form, giỏ hàng | checklist vấn đề trang đích có bằng chứng | P1 |
| Offer & Pricing | giá niêm yết công khai, phí vận chuyển, lợi nhuận gộp do khách cung cấp | giả thuyết ưu đãi/giá, không tự đổi giá | P1 |
| Sales Funnel | leads có consent, phản hồi chăm sóc, tỉ lệ đơn thực | nút thắt trước/sau cuộc gọi chốt khách | P1 |
| Time & Seasonality | **cohort theo giờ nhấp và múi giờ Ads**, nhiều ngày so sánh, conversions đã đủ lag | khung giờ cần điều tra; không tự chỉnh ad schedule | P0 (lõi v0.1) |
| Google / Meta Execution | API capabilities, ngân sách/bid hiện tại và quyền truy cập | kế hoạch thay đổi theo từng loại chiến dịch | P2 |
| Experiments | mục tiêu, đối chứng, lưu lượng, attribution window | test A/B được hỗ trợ, giả thuyết và điều kiện dừng | P2 |
| Outcome Memory | before/after, account riêng, yếu tố mùa vụ, bài học thất bại | playbook versioned áp dụng có điều kiện | P2 |
| Zalo Human Approval | người duyệt có quyền, proposal ID vô danh | chấp thuận/từ chối/hết hạn an toàn | P1 |

**Nguồn học có thể kiểm toán:** (1) tài liệu chính thức của Google/Meta và GA4; (2) chuyên gia thực chiến diễn giải tình huống + reviewer ký duyệt; (3) kết quả thí nghiệm có đối chứng và dữ liệu đã đủ thời gian ghi nhận chuyển đổi. Từ (3), LHM chỉ phổ biến **quy tắc tổng quát đã được đánh giá và được phép chia sẻ**, không gửi dữ liệu khách khác vào model.

## 4. Nguyên tắc không can thiệp quá sớm

- **Sự cố thật** (site down, form hỏng, thanh toán hỏng, vượt hạn mức bất thường): gửi **cảnh báo khẩn cấp**, không chờ 14 ngày. Không đồng nghĩa tự dừng Ads.
- **Không xác minh tracking/CRM hoặc website:** điều tra trước, không kết luận "đốt tiền" chỉ vì conversion bằng 0.
- **Bid strategy đang learning hoặc chưa biết status:** không đề xuất thay đổi tùy tiện; theo dõi.
- **Không biết chu kỳ chuyển đổi và lần chỉnh gần nhất:** chưa đủ điều kiện đề xuất.
- **Chu kỳ chuyển đổi chưa khép / dữ liệu ít:** quan sát tiếp; không kết luận từ báo cáo giờ/ngày lẻ.
- **Skill v0.1 dùng ngưỡng pilot thận trọng:** cửa sổ quan sát ít nhất **max(14 ngày, 2 chu kỳ chuyển đổi)**, ít nhất 10 chuyển đổi đã trưởng thành để *xem xét đề xuất*. **Đây không phải điều kiện mang tính thống kê để tuyên bố thử nghiệm thành công**, cũng không phải quy tắc cố định của Google. Ngành ít đơn cần thiết kế đo lường khác.
- **Không mặc định các thay đổi ngân sách luôn reset learning:** Google nêu Learning status do thay đổi cấu trúc/mục tiêu; thay đổi ngân sách/target có thể tác động tới hiệu quả mà không tạo Learning status. Đánh giá tác động dựa trên conversion lag (1–2 cycles), không chỉ cái nhãn Learning.

Tài liệu tham chiếu (cần kiểm tra lại khi nâng Google Ads API): [Smart Bidding learning](https://support.google.com/google-ads/answer/13020501), [Target adjustments](https://support.google.com/google-ads/answer/10433846), [Experiments API](https://developers.google.com/google-ads/api/docs/experiments/overview).

## 5. Zalo Approval Agent — luồng bảo mật

1. Agent **trên thiết bị khách** phân tích Ads, tạo proposal cụ thể: vấn đề, chứng cứ, mục tiêu, chi phí/tổng ngân sách, rủi ro, rollback, `expires_at`, `skill_version`.
2. Chỉ sau khi khách **đồng ý nhận thông báo**, LHM gửi OA/bot theo **quyền gửi tin được Zalo chấp thuận**. Message không chứa Ads ID, tên chiến dịch, số liệu khách nếu chưa có cơ chế riêng đảm bảo chính sách bảo mật. Mặc định chỉ gửi "Có đề xuất mới" + link mở PWA/thiết bị khách.
3. Nút **Xem và duyệt** mở trang bảo mật có đăng nhập + MFA/step-up khi cần. Không coi click trên một link công khai hay webhook tự nhận là chứng minh chủ tài khoản.
4. Phê duyệt gắn **opaque proposal_id, actor có quyền, revision, phạm vi chính xác, nonce một lần, thời hạn**, dùng trạng thái CAS/idempotent; từ chối/hết hạn đóng yêu cầu và không thực thi.
5. Khi người dùng duyệt, **thiết bị khách đang online** nhận trạng thái đã xác thực; so lại quyền, tình trạng Ads thực tế, giới hạn và lần thay đổi gần nhất. Nếu giá trị thay đổi hoặc proposal quá cũ: lập lại proposal, KHÔNG ghi Ads.
6. Execute qua provider API **chỉ trên thiết bị**, validate-only nơi hỗ trợ, kiểm tra kết quả, lưu audit cục bộ. Gửi kết quả/thất bại về notification đã opt-in bằng thông tin không nhạy cảm.
7. Kịch bản **Từ chối**: ghi lý do tùy chọn cục bộ; tiếp tục theo dõi, không nhắc lại cùng đề xuất liên tục. Kịch bản **không phản hồi**: hết hạn = không hành động.

**Trạng thái:** observed → diagnosed → proposed → notified → approved/rejected/expired → executing → accepted_unverified/verified/needs_review → learning. Chỉ `approved` hợp lệ mới được chuyển sang `executing`. **Zalo API/đăng ký OA, mẫu tin, quyền bot, webhook và chi phí cần xác minh thực tế** trước khi bật cho khách.

## 6. Kiến trúc & giới hạn theo dõi

- **Data-plane:** desktop Windows local (token vault của khách, Ads API, marketing skills, proposal và audit có dữ liệu Ads); mặc định không đưa token lên server LHM.
- **Control-plane:** Cloudflare Workers + D1 quản lý license, trạng thái thiết bị vô danh, thông báo/approval không nhạy cảm, giới hạn thao tác; tuyệt đối không nhận token, Ads ID, raw reporting.
- **Zalo:** kênh thông báo và yêu cầu hành động theo quyền OA/consent; không phải nơi lưu báo cáo thô.
- **24/7 là mục tiêu có điều kiện:** phải có một tiến trình agent trên thiết bị khách **luôn bật, luôn có mạng**. Mobile PWA bị hệ điều hành tạm dừng thì không tiếp tục theo dõi Ads. Máy ở nhà của chủ LHM không được tự nhận hoặc giữ Ads token của toàn bộ khách trái chính sách device-only. Khi agent offline: đợi online, không giả vờ đã thực thi.
- **Chống spam:** gộp sự kiện trùng, cooldown theo tổ chức/tài khoản, giới hạn thông báo, yên lặng ban đêm trừ sự cố có cấu hình.

## 7. Experiment Engine: không chạy thử tùy tiện

- Có **một giả thuyết chính / một biến chính** mỗi thử nghiệm; xác định KPI trước khi triển khai, đối chứng và quy tắc dừng.
- Chỉ dùng loại experiment mà **Google Ads API hỗ trợ cho loại campaign/feature đó**; không hứa mọi chiến dịch đều có split 80/20. Không tự chi thêm tiền ngoài mức đã phê duyệt.
- Tính đến attribution delay, doanh thu hoàn hủy, lịch ngày trong tuần, mùa vụ và ảnh hưởng các thay đổi đồng thời.
- Tính cỡ mẫu/độ tin cậy phù hợp trước khi kết luận "thắng"; nếu dữ liệu ít trả "không kết luận", không ép chọn.
- Rollback các thao tác có thể đảo ngược; với hành động không hoàn tác hoàn toàn, phải cảnh báo và yêu cầu phê duyệt mạnh hơn.

## 8. Lộ trình có điều kiện nghiệm thu

**P0 — Đã tạo trong PR này (chưa release):** skill mã hóa điều kiện `proposal_ready/observe_only/diagnose_first/urgent_review`; hour-of-click cohort filter; test fail-closed. Bộ mã **không gọi API, không tự áp dụng thay đổi**. CI cần xanh trước khi merge.

**P1 — Data quality & UI:** bổ sung collector đối chiếu click-hour cohort (theo múi giờ tài khoản và conversion lag), kiểm tra website (desktop/mobile/form), kết nối CRM opt-in, lưu change history; hiển thị "tại sao chờ" và "bằng chứng" trong Studio. Nghiệm thu: dữ liệu giả/thiếu không tạo đề xuất sai; tách tenant hoàn chỉnh.

**P2 — Zalo:** OA đã được duyệt, giới hạn và mẫu tin được xác minh; link secure auth; trạng thái duyệt/từ chối/hết hạn; chống phát lại/double click, cross-tenant, offline, đổi proposal sau duyệt. Nghiệm thu: 100% thay đổi cần approval thực từ đúng chủ; không lộ credentials/account ID lên Cloudflare.

**P3 — Experiments:** Google API capability matrix, pilot Search được hỗ trợ, tạo test với quyền quản trị, read-back, audit, so sánh mature conversion với control; chưa bật auto-budgeting. Nghiệm thu: demo end-to-end trên tài khoản thử nghiệm, rollback và failsafe; không thay đổi Ads chưa được duyệt.

**P4 — Commercial:** dashboard một trang dễ hiểu, key/gia hạn, skill versions có changelog & rollback, 10 khách pilot 30 ngày; đo phí vận hành, churn, số đề xuất có ích, tác động lên cost per **đơn đã xác nhận** (không chỉ leads) so với nhóm/baseline thích hợp. Chỉ sau kiểm chứng mới định giá chính thức.

## 9. Việc không được tuyên bố là xong

- Chưa có Zalo callback/approval production thực tế; kết nối OA và quyền nhắn tin là dependency.
- Chưa có lịch sử click-hour cohorts đã xác thực / analytics theo đơn CRM thật để áp dụng trực tiếp.
- Chưa có AI tự tổ chức experiment, chưa có Google Ads test thật trên account được cấp quyền.
- Chưa có bảo đảm "24/7 khi tắt máy", giảm chi phí hay tăng lợi nhuận.
- Chưa tích hợp `growth_intelligence.py` vào pipeline `advisor.scan_account`; đây là **lõi thuật toán read-only được test**, không phải trải nghiệm người dùng đã bật.

## 10. Tiêu chí đóng PR / phát hành

1. CI Python/Node/UI smoke thành công, security review và secrets scan.
2. Unit tests: nhiễu/số liệu thiếu, chưa đủ chu kỳ, incident khẩn cấp, sai timezone, nhỏ mẫu, thiếu quyền, reject, replay và expiry.
3. Cập nhật UI giải thích rõ "quan sát / điều tra / đề xuất", không hứa tối ưu từ báo cáo 7 ngày là realtime.
4. E2E có giấy phép thật: login khách → kết nối Ads → đánh giá → Zalo → xác thực chủ → đồng ý hoặc từ chối → execute tại thiết bị → provider read-back → báo kết quả.
5. Audit chứng minh Ads data và token không rời thiết bị trái chính sách `DEVICE_ONLY_ADS_DATA.md`.

**Nguyên tắc xuất bản:** mỗi giai đoạn phải đạt gate trước khi gọi là production; không biến giai đoạn thiết kế thành tính năng đã sẵn sàng bán.
