# Kỹ năng tối ưu quảng cáo — LHM Vòng lặp Tối ưu

Tài liệu này mô tả playbook tối ưu trong `ads_core/optimization_playbook.py`: triết lý vận hành, toàn bộ danh mục quy tắc, giới hạn trung thực của công cụ, phần độc quyền của LHM, và checklist chiến thuật 2026.

## 1. Triết lý

1. **Bằng chứng trước, hành động sau.** Mọi quy tắc chỉ kích hoạt khi có đủ lượng dữ liệu (số lượt nhấp / số chuyển đổi tối thiểu theo từng quy tắc). Dữ liệu thiếu (chưa có số liệu, nền tảng chưa trả về) thì quy tắc im lặng — công cụ không bao giờ biến "không biết" thành "bằng 0" để kết luận.
2. **Tracking trước tiên.** Chi tiền mà không ghi nhận chuyển đổi là tín hiệu kiểm tra đo lường trước hết, không phải bằng chứng lãng phí. Không quy tắc nào khuyên tự động tắt/dừng quảng cáo.
3. **Tôn trọng pha học.** Thuật toán đấu thầu của Google/Meta cần thời gian và lượng chuyển đổi để học. Mỗi lần chỉnh giá thầu/ngân sách đều khởi động lại một phần quá trình học — vì vậy mọi bước chỉnh đều nhỏ và phải chờ đủ lâu trước khi đánh giá tiếp.
4. **Bước nhỏ ≤ 20%.** Mọi đề xuất thay đổi giá thầu hoặc ngân sách đều giới hạn ở mức tối đa 20% mỗi bước, và chỉ đổi một biến mỗi lần.
5. **Người duyệt mọi thay đổi.** Hệ thống chỉ tư vấn. Mọi thay đổi thật do người phụ trách thực hiện trong trình quản lý quảng cáo. Không có lời khuyên nào trong playbook này là lời hứa về kết quả.

## 2. Danh mục quy tắc

Ký hiệu mức độ: `critical` (cần xử lý sớm), `review` (cần xem xét), `opportunity` (cơ hội cải thiện/mở rộng). Ngưỡng là giá trị heuristic mặc định của ngành, khai báo tập trung ở đầu module để chỉnh theo tài khoản.

| Mã quy tắc | Nhóm | Mức | Điều kiện kích hoạt (dữ liệu 7 ngày) | Hướng xử lý chính |
|---|---|---|---|---|
| `spend_no_conversions` | tracking | review | ≥ 50 lượt nhấp, chi > 0, 0 chuyển đổi (cả hai nền tảng) | Kiểm chứng tracking/CAPI, độ trễ quy đổi, trang đích — trước mọi kết luận khác |
| `cpa_above_target` | bid_cost | review / critical | Có mục tiêu CPA; ≥ ngưỡng chuyển đổi của mục tiêu; CPA > 1,2× mục tiêu (review), > 1,5× (critical) | Hạ tCPA/giá thầu từng bước ≤ 20%, chuyển ngân sách sang chiến dịch đạt mục tiêu |
| `cpa_well_below_target_scale` | scale | opportunity | CPA < 0,8× mục tiêu và ≥ 10 chuyển đổi | Tăng ngân sách hoặc nới tCPA từng bước ≤ 20% để mua thêm chuyển đổi |
| `roas_below_target` | roas | review / critical | Có mục tiêu ROAS và doanh thu đã ghi nhận; ROAS < mục tiêu (review), < 0,7× (critical) | Đối chiếu doanh thu thực trước; giảm tốc từng bước ≤ 20% |
| `roas_above_target_scale` | scale | opportunity | ROAS > 1,3× mục tiêu, ≥ 10 chuyển đổi, có chi tiêu | Tăng ngân sách từng bước ≤ 20% hoặc nới tROAS một bước nhỏ |
| `low_ctr` | structure | review | ≥ 100 lượt nhấp, ≥ 1.000 hiển thị, CTR < 0,5% | Rà soát thông điệp quảng cáo, creative, độ khớp đối tượng/trang đích |
| `high_ctr_no_conversions` | tracking | review | CTR ≥ 1%, ≥ 100 lượt nhấp, 0 chuyển đổi | Lệch phễu: kiểm tra trang đích, form/thanh toán và sự kiện chuyển đổi |
| `low_conversion_volume_for_smart_bidding` | bid_cost | review | 0 < chuyển đổi < 15 trong 7 ngày, có chi tiêu | Gộp chiến dịch/nhóm quảng cáo phân mảnh, đánh giá theo cửa sổ 14–30 ngày (diễn đạt riêng cho Google Smart Bidding và giai đoạn học của Meta) |
| `dead_campaign` | structure | review | Chiến dịch đang bật, chi tiêu = 0 và hiển thị = 0 trong 7 ngày | Checklist phân phối: ngân sách dùng chung, sàn giá thầu, đối tượng, lịch/vị trí, trạng thái duyệt |
| `cpa_drift_vs_baseline` | bid_cost | review / critical | CPA lệch > +25% so với CPA trung vị của chính chiến dịch (critical ở > +50%), ≥ 5 chuyển đổi | Tìm thay đổi gây lệch (creative, đối tượng, trang đích), kiểm chứng tracking, giảm tốc ≤ 20% |
| `roas_drift_vs_baseline` | roas | review / critical | ROAS tụt dưới 0,8× ROAS trung vị của chính chiến dịch (critical ở < 0,65×), ≥ 5 chuyển đổi | Đối chiếu doanh thu, tìm thời điểm bắt đầu tụt, giảm tốc phần kém nhất |
| `platform_target_missed` | bid_cost | review / critical | Target THẬT trên nền tảng (adapter đọc về): CPA > 1,3× tCPA (review), > 1,6× (critical); hoặc ROAS < tROAS/1,3 (review), < tROAS/1,6 (critical); ≥ 5 chuyển đổi | Hiệu chỉnh target về gần thực tế theo bước ≤ 20%; Google: lưu ý hành vi kéo-về-target từ 17/8/2026 |
| `platform_target_headroom` | scale | opportunity | CPA < 0,8× tCPA nền tảng hoặc ROAS > 1,25× tROAS nền tảng, ≥ 10 chuyển đổi | Tăng ngân sách hoặc nới/hạ target từng bước ≤ 20%, theo dõi 3–7 ngày |
| `manual_bidding_at_scale` | structure | review | Google: bid tay (MANUAL_CPC/CPM/CPV) với ≥ 30 chuyển đổi/7 ngày; Meta: bid cap với ≥ 30 chuyển đổi/7 ngày | Thử nghiệm Smart Bidding / cost per result goal có đối chứng (experiment), không chuyển thẳng 100% |
| `budget_constrained_winner` | scale | opportunity | Google: mất ≥ 20% impression share vì ngân sách, đồng thời đang đạt ít nhất một mốc (mục tiêu nội bộ hoặc target nền tảng), ≥ 10 chuyển đổi | Tăng ngân sách ≤ 20%/bước hoặc dồn ngân sách từ chiến dịch yếu — CHỈ sau khi xác nhận là chiến dịch Search (công cụ không thấy loại chiến dịch) |
| `adset_target_missed` | bid_cost | review / critical | Meta: CPA > 1,3× (review) / 1,6× (critical) so với TRUNG VỊ bid_amount các ad set của chiến dịch, ≥ 5 chuyển đổi, không có target cấp chiến dịch | Rà soát từng ad set trong Ads Manager; giá trị trung vị chỉ là xấp xỉ (bid_amount là trần giá ở bid cap, là mục tiêu chi phí ở cost cap) |
| `audience_fatigue_risk` | structure | review | Meta: tần suất 7 ngày ≥ 4,0 kèm CTR < 1%, hoặc ≥ 6,0 bất kể CTR; ≥ 1.000 hiển thị | Checklist làm mới creative / mở rộng đối tượng — công cụ không thấy dữ liệu từng mẫu quảng cáo |
| `account_fragmentation` | structure | opportunity | Cấp tài khoản: ≥ 4 chiến dịch đang chạy đều dưới 15 chuyển đổi/7 ngày | Gộp các chiến dịch cùng mục tiêu theo từng cụm nhỏ |
| `account_budget_reallocation` | scale | opportunity | Cấp tài khoản: > 40% tổng chi dồn vào chiến dịch không đạt mục tiêu (CPA > 1,5× mục tiêu hoặc ROAS < mục tiêu) | Tái phân bổ dần ≤ 20%/bước sang chiến dịch đạt mục tiêu |

Quy tắc theo mục tiêu chỉ chạy khi tổ chức đã đặt mục tiêu CPA/ROAS cho tài khoản (`ads_core/goals.py`) và mục tiêu đang bật, đúng tiền tệ. Chưa đặt mục tiêu thì các quy tắc đó im lặng; các quy tắc ngưỡng/tracking/cấu trúc vẫn hoạt động.

## 3. Công cụ KHÔNG nhìn thấy gì — và vì vậy chỉ tư vấn dạng checklist

Dữ liệu đầu vào của playbook là số liệu tổng hợp cấp chiến dịch trong 7 ngày: chi tiêu, lượt nhấp, hiển thị, CTR, chuyển đổi, doanh thu, CPA, ROAS — **cộng cấu hình đấu thầu cấp chiến dịch** mà adapter đọc về: loại chiến lược giá thầu, target tCPA/tROAS thật trên nền tảng, và ngân sách (Google: campaign budget theo ngày; Meta: ngân sách ngày/trọn đời cấp chiến dịch). Nhờ vậy các quy tắc `platform_target_*` so được hiệu quả thực tế với chính con số nhà quảng cáo đã khai với nền tảng, kể cả khi tổ chức chưa đặt mục tiêu trong phần mềm.

Từ sprint 20, adapter còn đọc: tỉ lệ mất hiển thị vì ngân sách của Google (`search_budget_lost_impression_share` — chỉ số của mạng Search; hành vi với chiến dịch ngoài Search chưa kiểm chứng trên tài khoản thật), bid_amount các ad set của Meta (chỉ dùng dạng TRUNG VỊ làm xấp xỉ trong `adset_target_missed`), và tần suất/reach của Meta từ insights. Xem bản đồ đầy đủ ở `docs/research/bid-surfaces-note.md`.

Công cụ **vẫn không** có:

- Target chi tiết **từng ad set** trên Meta để kết luận cho một ad set cụ thể (chỉ có trung vị cấp chiến dịch) và trạng thái "bị giới hạn bởi ngân sách" dạng nhãn của Google (chỉ có chỉ số mất hiển thị làm proxy); ngân sách dùng chung (shared budget) và chiến lược danh mục (portfolio) khiến target/ngân sách cấp chiến dịch có thể không phải con số vận hành thật;

- Cụm từ tìm kiếm (search terms) và truy vấn thực tế của người dùng;
- Dữ liệu cấp quảng cáo: từng mẫu quảng cáo/creative nào đang chạy, tần suất, độ mệt của creative;
- Phân rã theo đối tượng, thiết bị, vị trí hiển thị, khung giờ;
- Lý do quảng cáo bị từ chối, trạng thái duyệt chi tiết;
- Dữ liệu sau nhấp: hành vi trên trang đích, chất lượng lead sau bán hàng.

Mọi lời khuyên đụng tới các lớp dữ liệu trên đều được viết dưới dạng **checklist để người phụ trách tự kiểm tra trong trình quản lý quảng cáo**, không phải kết luận. Khi cần bằng chứng ở các lớp đó, phải xem trực tiếp trong Google Ads / Meta Ads Manager.

## 4. Phần độc quyền của LHM — cơ chế, không phải chiêu thức

Nói thẳng: các chiến thuật tối ưu ở mục 5 là **kiến thức công khai của ngành** — bất kỳ chuyên gia quảng cáo nào cũng biết, và đối thủ cũng có. Đó là điều kiện tối thiểu (table stakes), không phải lợi thế của LHM.

Phần độc quyền của LHM là **cơ chế vận hành trên dữ liệu riêng của từng khách**, chạy ngay trong bản cài đặt trên máy khách:

1. **Hồ sơ nền riêng từng tài khoản (account baselines).** Hệ thống lưu các kỳ snapshot và tính, cho từng chiến dịch, CPA/ROAS trung vị và biên dao động của chính nó. Nhờ vậy hệ thống phát hiện được "chiến dịch này đang xấu đi so với chính nó" (quy tắc `*_drift_vs_baseline`) — thứ mà ngưỡng chung toàn ngành không bắt được, vì một CPA "bình thường" với tài khoản khác có thể là bất thường với chính chiến dịch này.
2. **Vòng kiểm chứng kết quả (outcome verification).** Đề xuất không kết thúc ở lúc đưa ra. Luồng vận hành là một vòng kín: **đề xuất → người duyệt và thực hiện → hệ thống đo lại kỳ sau → phán quyết** `improved` / `worsened` / `unchanged` / `insufficient_data` bằng chỉ số đúng của từng loại đề xuất (CPA giảm là tốt với đề xuất CPA; ROAS tăng là tốt với đề xuất ROAS; chuyển đổi hồi phục là tốt với đề xuất tracking). Phán quyết có kỷ luật: biến động trong ±5% coi là nhiễu, và thiếu lượng chuyển đổi tối thiểu thì phán quyết trung thực là "chưa đủ dữ liệu" thay vì đoán.
3. **Chống tự mâu thuẫn (conflict guard).** Kết quả một lần quét không bao giờ đồng thời khuyên mở rộng và cắt giảm cùng một chiến dịch. Khi cả hai cùng kích hoạt, cơ hội mở rộng bị chặn, finding nghiêm trọng hơn được giữ lại và mã bị chặn được ghi rõ trong trường `suppressed`. Công cụ tư vấn thông thường (và chatbot) rất hay tự mâu thuẫn kiểu này; vòng lặp của LHM loại bỏ nó theo thiết kế.
4. **Học thuyết rào chắn (guardrail doctrine).** Mọi đề xuất đều kèm rào chắn: tôn trọng pha học, bước chỉnh ≤ 20%, tracking kiểm chứng trước, người duyệt mọi thay đổi, không hứa kết quả. Rào chắn là một phần của sản phẩm, không phải chữ nhỏ.

Ba cơ chế đầu chạy trên dữ liệu của chính khách hàng, tích lũy theo thời gian sử dụng: càng dùng lâu, hồ sơ nền càng đáng tin và vòng kiểm chứng càng có nhiều phán quyết làm bằng chứng. Đây là phần đối thủ sao chép khó nhất — không phải vì bí mật, mà vì nó nằm trong dữ liệu và kỷ luật vận hành của từng tài khoản.

## 5. Checklist chiến thuật 2026 — hướng dẫn tham khảo, KHÔNG phải số liệu đo được

> Mục này là kiến thức ngành công khai, dùng làm checklist rà soát định kỳ. Không mục nào dưới đây là tính năng đã đo lường hay cam kết của phần mềm.

- **Chọn chiến lược đấu thầu theo lượng chuyển đổi:** lượng chuyển đổi còn thấp → ưu tiên tối đa chuyển đổi/giới hạn biến động; khi lượng ổn định (tham chiếu ~30 chuyển đổi/tháng trở lên cho một chiến dịch) mới siết dần bằng tCPA/tROAS. Đừng đặt mục tiêu chặt ngay từ đầu trên dữ liệu thưa.
- **Điều kiện tiên quyết của đấu thầu theo giá trị (value-based bidding):** doanh thu phải được ghi nhận đầy đủ và đúng (giá trị đơn hàng thật, trừ hoàn/hủy), sự kiện chuyển đổi ổn định, cửa sổ quy đổi phù hợp với chu kỳ mua hàng. Thiếu một trong các điều kiện này, tROAS sẽ tối ưu theo tín hiệu sai.
- **Gộp (consolidation) thay vì phân mảnh:** ít chiến dịch hơn, mỗi chiến dịch nhiều tín hiệu hơn thường thắng nhiều chiến dịch nhỏ thiếu dữ liệu — ở cả Google (cấu trúc gọn theo chủ đề/mục tiêu) lẫn Meta (ít ad set hơn, ngân sách tập trung).
- **Meta — đa dạng creative:** chuẩn bị nhiều biến thể creative thật sự khác nhau (góc thông điệp, định dạng, hook) thay vì một mẫu duy nhất; hệ thống phân phối của Meta (Advantage+/phân phối mở rộng) cần "nguyên liệu" đa dạng để tìm đúng người. Theo dõi độ mệt của creative bằng tần suất và CTR theo thời gian.
- **Chất lượng tracking/CAPI:** với Meta, gửi sự kiện máy chủ (Conversions API) song song pixel, khử trùng lặp bằng event ID, và kiểm tra điểm chất lượng khớp sự kiện (Event Match Quality). Với Google, dùng đo lường nâng cao (enhanced conversions) và nhập chuyển đổi ngoại tuyến (offline conversion import) từ CRM khi chu kỳ bán hàng dài.
- **Kỷ luật thay đổi:** một thay đổi lớn mỗi lần, ghi lại ngày thay đổi, chờ đủ một chu kỳ học trước khi thay đổi tiếp theo. Đây chính là điều kiện để vòng kiểm chứng kết quả ở mục 4 phán quyết được.
- **Ngân sách theo tầng:** giữ phần ngân sách cốt lõi cho các chiến dịch đã chứng minh hiệu quả, và một phần thử nghiệm tách riêng cho thử nghiệm mới — không trộn hai mục đích trong cùng một chiến dịch.

### 5.1. Cập nhật nền tảng 2026 bắt buộc phải biết (chi tiết: `docs/research/`)

- **Google — thay đổi đặt giá 17/8/2026:** chiến dịch tCPA/tROAS bị giới hạn ngân sách nay được đặt giá hướng về *đúng target đã khai* thay vì dưới target như trước. Chiến dịch đang "thắng" target nhờ ngân sách hẹp có thể bị bid lên và hết rẻ — hiệu chỉnh target về mức thực tế 30 ngày trước khi kết luận phần mềm/quảng cáo có vấn đề.
- **Google — AI Max for Search:** auto-upgrade bắt buộc từ 9/2026 cho chiến dịch còn dùng broad match cấp chiến dịch / Automatically Created Assets (DSA: 2/2027), không có opt-out. Số hiệu quả Google công bố là số marketing; phân tích độc lập ghi nhận ROAS traffic AI Max có thể thấp hơn đáng kể — kỷ luật mới: rà search terms theo match type "AI Max" hằng tuần và phủ định đều tay.
- **Google — ngưỡng chính thức:** đánh giá tCPA ở ≥30 conversions, tROAS ở ≥50 conversions có giá trị đa dạng; các con số ~15 conversions/tháng là mức tối thiểu cho goal bid theo tài liệu value bidding của Google. Dưới ngưỡng thì ưu tiên gom chiến dịch thay vì siết target.
- **Meta — Andromeda:** tầng retrieval mới khiến *creative là cơ chế targeting chính* — đa dạng hoá creative theo concept thật sự khác nhau (hook, format, persona) thay cho interest stacking. Số liệu Meta công bố là cấp hệ thống; nghiên cứu độc lập ghi nhận ROAS trung bình giảm trong đợt rollout — không hứa hẹn "bật Advantage+ là tốt".
- **Meta — learning:** mỗi ad set cần ~50 optimization events/7 ngày để thoát learning phase (tài liệu Help của Meta). Gộp thay đổi thành đợt, tăng ngân sách theo bậc nhỏ, không kết luận từ dữ liệu <72 giờ.
- **Meta — đổi định nghĩa attribution 2026:** tháng 1/2026 bỏ cửa sổ 7d/28d view khỏi API; tháng 3/2026 click attribution chỉ tính link click (tương tác khác chuyển sang engage-through). **Không so sánh CPA/ROAS xuyên hai mốc này bằng cùng một định nghĩa** — số giảm một phần là do đo lường, không phải hiệu quả. Advisor của LHM dùng cửa sổ cố định 7d_click nên nhất quán nội bộ, nhưng người đọc phải hiểu ngữ cảnh này.
