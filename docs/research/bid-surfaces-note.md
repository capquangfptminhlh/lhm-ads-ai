# Ghi chú kỹ thuật nội bộ — Bản đồ bề mặt dữ liệu giá thầu & ngân sách

> **Mục đích:** ghi lại MỌI bề mặt dữ liệu giá thầu/ngân sách mà sản phẩm hiện đang đọc, để các agent/đợt làm việc sau không phải hỏi lại "công cụ có thấy X không?".
> **Phạm vi nguồn:** CHỈ dựa trên repo này (base = main `654df96`): `ads_core/optimizations.py`, `ads_core/optimization_playbook.py`, `ads_core/autopilot.py` (luồng đọc-để-sửa), `docs/OPTIMIZATION_SKILL.md`, `docs/research/research-google-ads-2026.md`, `docs/research/research-meta-ads-2026.md`, `tests/test_bid_fields.py`. Không có nghiên cứu ngoài, không có khẳng định nào ngoài repo.
> **Kỷ luật tên trường:** mọi tên trường API trong tài liệu này đều xuất hiện nguyên văn trong code/docs của repo. Chỗ nào cần nhắc tới một trường/lời gọi CHƯA có trong repo, nó được ghi rõ là **ĐỀ XUẤT — chưa kiểm chứng** và không được trích dẫn như sự thật.

Có hai luồng đọc khác nhau, đừng trộn:

- **Luồng advisor (chỉ đọc, phân tích):** `google_campaigns` / `meta_campaigns` trong `ads_core/optimizations.py` → chuẩn hoá thành dict chiến dịch → `ads_core/optimization_playbook.py` tiêu thụ.
- **Luồng autopilot (đọc-để-sửa, có người duyệt):** `_google_read` / `_meta_read` trong `ads_core/autopilot.py` → đọc giá trị gốc của ĐÚNG một đối tượng sắp sửa, giữ nguyên đơn vị provider. Luồng này không nuôi playbook.

---

## 1. Bảng ánh xạ: trường API → khóa chuẩn hoá → quy tắc tiêu thụ

### 1.1 Google — luồng advisor (GAQL, `googleAds:searchStream`, `FROM campaign`, `segments.date DURING LAST_7_DAYS`, phiên bản API mặc định `v25`)

| Trường yêu cầu từ API (nguyên văn trong query) | Khóa chuẩn hoá | Chuyển đổi | Quy tắc / nơi tiêu thụ |
|---|---|---|---|
| `campaign.bidding_strategy_type` | `bidding_strategy` | Chuỗi thô; rỗng → `None` | `manual_bidding_at_scale` (nhánh Google khớp đúng `MANUAL_CPC` / `MANUAL_CPM` / `MANUAL_CPV`); lưu vào snapshot |
| `campaign.target_cpa.target_cpa_micros` | `bid_target_cpa` (nguồn ưu tiên 1) | micros / 1.000.000 | `platform_target_missed` (nhánh CPA), `platform_target_headroom` (nhánh CPA), `verify_outcome` |
| `campaign.maximize_conversions.target_cpa_micros` | `bid_target_cpa` (nguồn dự phòng 2) | micros / 1.000.000; chuỗi `or`: chỉ dùng khi nguồn 1 trống/0 | Như trên |
| `campaign.target_roas.target_roas` | `bid_target_roas` (nguồn ưu tiên 1) | `float(...)` trực tiếp — đây là TỈ LỆ, không phải micros | `platform_target_missed` (nhánh ROAS), `platform_target_headroom` (nhánh ROAS), `verify_outcome` (chọn chỉ số phán quyết theo sự hiện diện của khóa này trong snapshot nền) |
| `campaign.maximize_conversion_value.target_roas` | `bid_target_roas` (nguồn dự phòng 2) | Như trên; chuỗi `or` sau nguồn 1 | Như trên |
| `campaign_budget.amount_micros` + `campaign_budget.period` | `daily_budget` | micros / 1.000.000, **chỉ khi `period` ∈ {`DAILY`, `None`}**; period khác → `None` | **Không quy tắc playbook nào tiêu thụ.** Chỉ được trả ra qua `/api/optimizations/accounts/{id}` và nằm trong snapshot. Xem điểm mù 2.2 |
| `metrics.cost_micros` | `spend` | micros / 1.000.000 | Mọi quy tắc hiệu quả; phái sinh `cpa`, `roas` |
| `metrics.clicks`, `metrics.impressions` | `clicks`, `impressions` | Nguyên giá trị | `ctr_percent` (phái sinh), `low_ctr`, `high_ctr_no_conversions`, `spend_no_conversions`, `dead_campaign`, `rule_suggestions` |
| `metrics.conversions` | `conversions` | `float` | Điều kiện lượng tối thiểu của gần như mọi quy tắc (CPA ≥ 5, scale ≥ 10, bid-tay ≥ 30 chuyển đổi/7 ngày) |
| `metrics.conversions_value` | `conversion_value` | Dùng NGUYÊN giá trị — **không phải micros** (xem caveat 3.1) | Phái sinh `roas`; `roas_below_target`, `roas_above_target_scale` |
| `campaign.id`, `campaign.name`, `campaign.status` | `id`, `name`, `status` | name cắt 100 ký tự | Định danh finding/snapshot; `dead_campaign` và điều kiện "đang chạy" (`ENABLED`) |

Khóa phái sinh tại adapter: `cpa` = spend/conversions (chỉ khi conversions > 0), `roas` = conversion_value/spend (chỉ khi spend > 0), `ctr_percent` = clicks×100/impressions.

### 1.2 Google — luồng autopilot (`_google_read` trong `ads_core/autopilot.py`, đọc theo ID đối tượng)

| Truy vấn | Trường | Dùng để |
|---|---|---|
| `FROM campaign_budget WHERE campaign_budget.id = …` | `campaign_budget.id`, `campaign_budget.amount_micros`, `campaign_budget.explicitly_shared` | Giá trị gốc (micros, KHÔNG chuẩn hoá) cho kế hoạch sửa ngân sách ngày. `explicitly_shared` không phải `False` → **từ chối sửa** (HTTP 422, ngân sách dùng chung). Lưu ý: truy vấn này KHÔNG chọn `campaign_budget.period` |
| `FROM ad_group WHERE ad_group.id = …` | `ad_group.id`, `ad_group.cpc_bid_micros`, `campaign.bidding_strategy_type` | Giá trị gốc cho kế hoạch sửa CPC thủ công; chỉ cho sửa khi `bidding_strategy_type == 'MANUAL_CPC'` |

### 1.3 Meta — luồng advisor (`meta_campaigns` trong `ads_core/optimizations.py`, Graph API mặc định `v24.0`)

**Endpoint `/campaigns`** — `fields = id,name,status,effective_status,bid_strategy,daily_budget,lifetime_budget`:

| Trường yêu cầu từ API | Khóa chuẩn hoá | Chuyển đổi | Quy tắc / nơi tiêu thụ |
|---|---|---|---|
| `bid_strategy` | `bidding_strategy` | Chuỗi thô; rỗng → `None` | `manual_bidding_at_scale` (nhánh Meta khớp đúng chuỗi `LOWEST_COST_WITH_BID_CAP`); lưu vào snapshot |
| `daily_budget` | `daily_budget` | `_meta_money`: `int(raw)/100` (minor units → đơn vị chính); không phải số → `None` | **Không quy tắc playbook nào tiêu thụ** (như Google) |
| `lifetime_budget` | `lifetime_budget` | `_meta_money` như trên | **Không quy tắc nào tiêu thụ**; khóa này chỉ có ở Meta |
| — (không có trường API nào được đọc) | `bid_target_cpa`, `bid_target_roas` | Code gán cứng `None` cho MỌI campaign Meta, kèm comment: cấu hình ở đây là cấp campaign (CBO/Advantage+), số tiền bid cấp ad set là bề mặt riêng, ngoài phạm vi | Hệ quả trực tiếp: `platform_target_missed` và `platform_target_headroom` **không bao giờ kích hoạt cho Meta**. Xem điểm mù 2.1 |
| `id`, `name`, `status`, `effective_status` | cùng tên | name cắt 100 ký tự | Điều kiện "đang chạy" của Meta cần cả `status` và `effective_status` = `ACTIVE`; `dead_campaign` |

**Endpoint `/insights`** — `level=campaign`, `date_preset=last_7d`, `fields = campaign_id,spend,clicks,impressions` (cộng `actions,action_values,account_currency` **chỉ khi** tổ chức đã cấu hình `meta_action_type` trong `ads_core/goals.py`; kèm `action_attribution_windows=["7d_click"]`, `action_report_time=conversion`):

| Trường | Khóa | Chuyển đổi / điều kiện | Tiêu thụ |
|---|---|---|---|
| `spend` | `spend` | `float(...)` trực tiếp — **đơn vị chính, KHÔNG chia 100** (khác họ ngân sách, xem caveat 3.1) | Mọi quy tắc hiệu quả; phái sinh `cpa` |
| `clicks`, `impressions` | cùng tên | Nguyên giá trị | `ctr_percent`, các quy tắc CTR/dead |
| `actions` | `conversions` (+ `conversion_action_type`, `conversion_source='meta_actions_7d_click'`) | `_meta_action_number`: đúng MỘT action khớp loại đã chọn, lấy `7d_click` (dự phòng `value`); **chỉ gán khi `account_currency` của insights khớp tiền tệ tài khoản đã lưu** — không khớp thì để `None` | `cpa` phái sinh và mọi quy tắc cần conversions |
| `action_values` | `conversion_value` → `roas` | Chỉ khi action đã chọn thuộc `META_PURCHASE_ACTIONS` | Các quy tắc ROAS phía Meta |

### 1.4 Meta — luồng autopilot (`_meta_read` trong `ads_core/autopilot.py`)

`GET /{ad_set_id}` với `fields = id,account_id,daily_budget,bid_amount,bid_strategy,status,effective_status`:

| Trường | Dùng để |
|---|---|
| `daily_budget` | Giá trị gốc (minor units nguyên) cho kế hoạch `adset_daily_budget` |
| `bid_amount` | Giá trị gốc cho kế hoạch `adset_bid_cap`; **chỉ được sửa khi `bid_strategy` ∈ {`LOWEST_COST_WITH_BID_CAP`, `COST_CAP`}**, ngoài ra từ chối (422). Xem caveat 3.3 về ngữ nghĩa của trường này |
| `bid_strategy`, `status`, `effective_status`, `account_id` | Kiểm tra điều kiện sửa và quyền sở hữu (ad set phải thuộc đúng tài khoản) |

> Đây là nơi DUY NHẤT trong sản phẩm đọc dữ liệu cấp ad set của Meta — và nó đọc đúng MỘT ad set theo ID để phục vụ sửa, không quét, không phân tích.

### 1.5 Bảng tổng hợp theo khóa chuẩn hoá (trả lời nhanh "ai dùng khóa này?")

| Khóa chuẩn hoá | Quy tắc tiêu thụ |
|---|---|
| `bidding_strategy` | `manual_bidding_at_scale` (cả hai nền tảng, khớp chuỗi theo enum của từng nền tảng) |
| `bid_target_cpa` | `platform_target_missed` (CPA > 1,3× → review; > 1,6× → critical; cần ≥ 5 conversions), `platform_target_headroom` (CPA < 0,8× target; ≥ 10 conversions), `verify_outcome` |
| `bid_target_roas` | `platform_target_missed` (ROAS < target/1,3 → review; < target/1,6 → critical), `platform_target_headroom` (ROAS > 1,25× target), `verify_outcome` |
| `daily_budget` | **Không quy tắc nào** — chỉ hiển thị + snapshot |
| `lifetime_budget` (Meta) | **Không quy tắc nào** — chỉ hiển thị + snapshot |
| `cpa`, `roas` (phái sinh) | `cpa_above_target`, `cpa_well_below_target_scale`, `roas_below_target`, `roas_above_target_scale` (so với mục tiêu nội bộ ở `goals.py`); `cpa_drift_vs_baseline`, `roas_drift_vs_baseline` (so với trung vị lịch sử); hai quy tắc `platform_target_*` (so với target nền tảng); `account_budget_reallocation` |
| `median_cpa`, `median_roas` (từ `compute_baselines` trên các snapshot đã lưu) | `cpa_drift_vs_baseline`, `roas_drift_vs_baseline` — đây là "nền" duy nhất phía Meta cho các phán đoán kiểu target (xem 2.1) |
| `spend`, `clicks`, `impressions`, `conversions`, `ctr_percent` | `spend_no_conversions`, `low_ctr`, `high_ctr_no_conversions`, `low_conversion_volume_for_smart_bidding`, `dead_campaign`, `account_fragmentation`, `rule_suggestions` (heuristic cũ trong `optimizations.py`: `low_ctr` + `no_reported_conversions`, riêng `no_reported_conversions` chỉ cho Google) |

---

## 2. Điểm mù — hiện trạng, lý do mù, và lời gọi API sẽ cần (đề xuất)

### 2.1 Meta: cost goal cấp ad set (cost per result goal / mục tiêu ROAS tối thiểu) — điểm mù lớn nhất phía Meta

**Hiện trạng chính xác.** Luồng advisor không bao giờ đọc ad set. `meta_campaigns` gán cứng `bid_target_cpa = bid_target_roas = None` cho mọi campaign Meta (comment trong code đã nói rõ: bid amount cấp ad set là "a separate surface and stay out of scope for campaign findings").

**"Bao phủ một phần" hiện có là gì — và không phải là gì.** Hai cơ chế sau đây là toàn bộ những gì đang tồn tại gần điểm mù này; không có cơ chế nào đọc được con số cost goal thật:

1. `manual_bidding_at_scale` nhánh Meta chỉ cần `bidding_strategy == 'LOWEST_COST_WITH_BID_CAP'` (cấp campaign) + ≥ 30 conversions/7 ngày → hệ thống biết RẰNG campaign đang chạy kiểu bid cap, nhưng **không biết cap là bao nhiêu tiền**.
2. Khi không có target thật, phán đoán kiểu "CPA có lệch mục tiêu không" được thay bằng so sánh với **trung vị lịch sử của chính campaign**: `compute_baselines` tính `median_cpa` / `median_roas` từ các snapshot 7 ngày đã lưu của chính campaign đó, và `cpa_drift_vs_baseline` / `roas_drift_vs_baseline` cảnh báo khi CPA lệch > +25% (critical > +50%) hoặc ROAS tụt dưới 0,8× (critical < 0,65×) trung vị. Đây là **xấp xỉ bằng hành vi quá khứ** ("xấu đi so với chính nó"), KHÔNG phải đọc cấu hình — một campaign đặt cost goal sai ngay từ đầu và chạy đều đều ở mức sai đó sẽ không bao giờ bị bắt bởi cơ chế này.

**Code hiện KHÔNG làm những việc sau (liệt kê để khỏi ai giả định ngược lại):**

- Không gọi bất kỳ endpoint danh sách ad set nào trong luồng đọc advisor (không liệt kê ad set thuộc campaign).
- Không đọc `bid_amount` cho mục đích phân tích — `bid_amount` chỉ xuất hiện trong luồng autopilot, đọc đúng một ad set theo ID khi người dùng tạo kế hoạch sửa.
- Không tổng hợp nhiều ad set thành một "cost goal hiệu dụng" cho campaign — không tồn tại bất kỳ phép tổng hợp nào (min / median / trung bình theo trọng số chi tiêu đều chưa có).
- Không đọc bất kỳ trường mục tiêu ROAS tối thiểu nào ở cấp ad set.
- Không phân biệt campaign CBO (ngân sách/bid ở cấp campaign) với ABO (ở cấp ad set) — dấu hiệu duy nhất là `daily_budget` cấp campaign vắng mặt → `None`, và `None` đó không được diễn giải thêm ở đâu cả.

**Sẽ cần gì — ĐỀ XUẤT, chưa kiểm chứng:** một lời gọi đọc danh sách ad set của campaign kèm các trường ngân sách/giá thầu cấp ad set (tiền lệ tên trường đã có trong repo ở luồng autopilot: `daily_budget`, `bid_amount`, `bid_strategy` trên object ad set), cộng một định nghĩa tổng hợp tường minh do người thiết kế quyết định. **Repo không nêu tên bất kỳ trường "cost per result goal" hay "ROAS floor" nào ở cấp ad set** — không được khẳng định tên trường cho tới khi đối chiếu tài liệu Meta Marketing API thật.

### 2.2 Google: trạng thái "Limited by budget" (bị giới hạn bởi ngân sách)

**Hiện trạng.** GAQL của advisor không chọn bất kỳ trường trạng thái nào của chiến lược giá thầu, và dù `daily_budget` đã được đọc, **không quy tắc nào so `spend` với `daily_budget`** — nên hệ thống không suy ra được campaign có đang bị cap ngân sách hay không. Playbook chỉ *nhắc con người tự kiểm tra*: action text của `platform_target_missed` (nhánh Google) yêu cầu kiểm tra trạng thái giới hạn ngân sách trước khi chỉnh target, vì hành vi kéo-về-target từ 17/8/2026 (nghiên cứu Google §1.3). `docs/OPTIMIZATION_SKILL.md` §3 cũng liệt kê trạng thái này vào danh sách "vẫn không có".

**Về proxy impression share.** Hiện trong repo **không tồn tại bất kỳ proxy định lượng nào** cho việc bị cap ngân sách: query không chứa metric impression share nào. Tín hiệu gián tiếp duy nhất là `platform_target_headroom` (CPA đang tốt hơn target với lượng conversions đủ) — nó gợi ý "còn dư địa" nhưng không phân biệt được "bị cap ngân sách" với "thị trường hết nhu cầu".

Tài liệu nghiên cứu Google (§2.7 và §4 mục 8) khẳng định trạng thái "Limited by budget" "lấy được qua API (bid strategy status)" — đó là khẳng định của tài liệu nghiên cứu; **repo không chứa tên trường cụ thể nào** cho trạng thái này.

Tên trường `metrics.search_budget_lost_impression_share` **không xuất hiện ở bất kỳ đâu trong repo** (code, docs, tests). Nếu muốn dùng tỉ lệ hiển thị mất vì ngân sách làm proxy, đó là **ĐỀ XUẤT — chưa kiểm chứng**: phải đối chiếu tên trường và tính tương thích của nó với `FROM campaign` trong tài liệu Google Ads API thật trước khi đưa vào GAQL (một trường sai sẽ làm hỏng toàn bộ truy vấn đọc).

### 2.3 Google: ngân sách dùng chung (shared budgets)

**Hiện trạng.** GAQL luồng advisor không chọn `campaign_budget.explicitly_shared`. Hệ quả: `daily_budget` của một campaign có thể thực chất là ngân sách CHUNG của nhiều campaign mà hệ thống không hề biết — bất kỳ ai cộng dồn `daily_budget` theo tài khoản sẽ đếm trùng. Hiện chưa có quy tắc nào cộng dồn ngân sách nên rủi ro đang nằm ở tầng hiển thị/diễn giải, chưa thành finding sai.

**Tương phản với luồng autopilot:** ở đó trường này ĐÃ được đọc — `_google_read` chọn `campaign_budget.explicitly_shared` và từ chối sửa ngân sách khi giá trị không phải `False` (422). Tức sản phẩm có ý thức về shared budget ở đường sửa, nhưng đường đọc advisor thì mù.

**Sẽ cần gì — ĐỀ XUẤT, độ rủi ro thấp nhưng vẫn chưa kiểm chứng trong luồng này:** bổ sung chính trường `campaign_budget.explicitly_shared` (đã có tiền lệ nguyên văn trong repo) vào GAQL của advisor để gắn cờ "ngân sách dùng chung" cho `daily_budget`. Research Google §2.5/§2.7 cũng mô tả shared budgets là cơ chế có thật của nền tảng [A trong tài liệu nghiên cứu].

### 2.4 Google: portfolio bid strategies (chiến lược giá thầu danh mục)

**Hiện trạng.** Advisor chỉ đọc target ở cấp campaign (`campaign.target_cpa…`, `campaign.maximize_conversions…`, v.v.). Khi campaign dùng portfolio strategy, target nằm trên đối tượng chiến lược dùng chung chứ không nằm trên campaign — các struct target ở cấp campaign có thể trống và adapter sẽ cho `bid_target_cpa = bid_target_roas = None` dù campaign thực tế đang bị một target ràng buộc. Code không đọc định danh/resource của chiến lược gắn trên campaign, không truy vấn đối tượng chiến lược. (Tài liệu nghiên cứu Google §2.5 nhắc portfolio bid strategy như một chiến thuật tổ chức cấu trúc, không mô tả bề mặt API của nó.)

**Hệ quả.** `platform_target_missed` / `platform_target_headroom` **im lặng giả tạo** (false silence) với campaign portfolio: hệ thống không phân biệt được "campaign không có target" với "target nằm ở nơi khác chưa đọc".

**Sẽ cần gì — ĐỀ XUẤT, chưa kiểm chứng:** đọc thêm định danh chiến lược gắn trên campaign rồi truy vấn đối tượng chiến lược đó để lấy target của nó. Tên trường/resource cụ thể không có trong repo — phải kiểm chứng với tài liệu Google Ads API trước khi viết code.

### 2.5 Điểm mù phụ

- **Campaign total budgets (ngân sách trọn kỳ/flight):** tài liệu nghiên cứu Google §1.5 mô tả loại ngân sách này (flight 3–90 ngày). Trong code: `period` khác `DAILY` → `daily_budget = None`; số tiền ngân sách trọn kỳ không được đọc ở bất kỳ đâu (luồng autopilot cũng không chọn `period`). Campaign dùng ngân sách trọn kỳ trông hệt campaign "không có ngân sách".
- **Loại campaign (Search / Performance Max / Demand Gen…):** không trường loại/kênh nào được đọc ở cả hai nền tảng — mọi quy tắc áp dụng đồng nhất. Tài liệu nghiên cứu Google §3.5/§4 đã tự ghi nhận khoảng trống này.
- **Meta ABO (ngân sách ở ad set):** campaign không có `daily_budget` cấp campaign → `None`; tổng ngân sách hiệu dụng của campaign không suy ra được (cùng gốc với 2.1).
- **Trạng thái học (learning / learning limited):** không nền tảng nào được đọc trường trạng thái học; mọi kỷ luật "tôn trọng pha học" chỉ tồn tại dưới dạng câu chữ guardrail trong finding.

---

## 3. Cảnh báo toàn vẹn dữ liệu (data-integrity caveats)

### 3.1 Hai họ đơn vị tiền — micros / minor units / đơn vị chính

- **Google, họ micros:** `metrics.cost_micros`, `campaign.target_cpa.target_cpa_micros`, `campaign.maximize_conversions.target_cpa_micros`, `campaign_budget.amount_micros` đều được chia 1.000.000. **Ngoại lệ nguy hiểm:** `metrics.conversions_value` KHÔNG phải micros — adapter dùng nguyên giá trị (đơn vị tiền chính). Nhầm lẫn hai họ này là sai lệch 10⁶ lần, và chúng nằm cạnh nhau trong cùng một query.
- **Google `target_roas`:** là tỉ lệ thuần (ví dụ 4.0), không chia gì cả — đặt cạnh `bid_target_cpa` (tiền) rất dễ nhầm đơn vị khi viết quy tắc mới.
- **Meta, hai quy ước trong cùng một hàm:** trường ngân sách trên object campaign (`daily_budget`, `lifetime_budget`) là số nguyên **minor units** → `_meta_money` chia 100 **vô điều kiện**; trong khi insights `spend` là số thập phân **đơn vị chính** → dùng `float(...)` trực tiếp, không chia. Ai viết code mới phải xác định trường mình đọc thuộc họ nào trước.
- **Meta, giả định 2 số thập phân:** phép chia 100 không hề nhìn vào tiền tệ của tài khoản. Repo không chứa bảng số chữ số thập phân theo tiền tệ nào — với tiền tệ có số thập phân khác 2, kết quả sẽ sai mà không có cảnh báo. `_meta_money` cũng nuốt mọi lỗi định dạng thành `None` (đúng triết lý "thiếu ≠ 0", nhưng đồng nghĩa lỗi dữ liệu phía API sẽ im lặng biến thành "không có ngân sách").
- **Autopilot giữ đơn vị gốc:** kế hoạch sửa ghi `unit` là `google_currency_micros` hoặc `meta_api_minor_units`. Không bao giờ so sánh trực tiếp số của tầng autopilot (gốc) với số của tầng advisor (đã chuẩn hoá sang đơn vị chính).

### 3.2 Ngữ nghĩa "ngân sách ngày"

- `daily_budget` (Google) được gán khi `campaign_budget.period` ∈ {`DAILY`, vắng mặt/`None`} — period vắng mặt cũng bị coi là ngân sách ngày (xem thêm ghi nhận bất nhất ở SUMMARY kèm theo). Period khác (ngân sách trọn kỳ…) → `None` dù `amount_micros` có giá trị thật.
- `daily_budget` (Meta) chỉ tồn tại khi campaign dùng ngân sách cấp campaign (CBO). Vắng mặt ≠ campaign không có ngân sách (có thể nằm ở ad set — điểm mù 2.1/2.5).
- Theo tài liệu nghiên cứu Meta §1.4 [A — Help của Meta]: Meta có thể chi vượt tối đa 75% ngân sách ngày trong một ngày, với trần tuần = 7 × ngân sách ngày. Đừng coi "chi vượt ngân sách ngày" là lỗi dữ liệu; và vì advisor dùng cửa sổ 7 ngày, so sánh hợp lệ nhất là tổng chi 7 ngày với 7 × `daily_budget` — hiện chưa có quy tắc nào làm phép so này.

### 3.3 `bid_amount` và target đổi nghĩa theo `bid_strategy` đi kèm

- **Meta `bid_amount` (chỉ luồng autopilot đọc):** cùng một trường, hai ngữ nghĩa — với `LOWEST_COST_WITH_BID_CAP` nó là trần giá cho TỪNG phiên đấu giá (bid cap); với `COST_CAP` nó là mục tiêu chi phí TRUNG BÌNH mỗi kết quả (cost cap). Code cho phép sửa ở cả hai trường hợp và xử lý giá trị như số nguyên minor units "mờ" — mọi diễn giải đều phải đọc kèm `bid_strategy` của chính ad set đó. Với các strategy khác, `bid_amount` không mang hai nghĩa trên và không được đọc cho mục đích gì trong sản phẩm.
- **Google `ad_group.cpc_bid_micros` (chỉ luồng autopilot đọc):** chỉ có nghĩa khi campaign ở `MANUAL_CPC` — autopilot ép kiểm tra `bidding_strategy_type` trước khi cho sửa. Dưới Smart Bidding, bid cấp ad group không lái phân phối (tài liệu nghiên cứu Google §2.8); đọc được con số không có nghĩa con số đó đang có tác dụng.
- **Google, chuỗi dự phòng target:** `bid_target_cpa` lấy `target_cpa` trước, `maximize_conversions` sau bằng toán tử `or` (tương tự cho ROAS). Trong giai đoạn nền tảng chuyển đổi nhãn chiến lược (nghiên cứu Google §1.2: từ 6/2026 `TARGET_CPA`/`TARGET_ROAS` quay lại thành chiến lược độc lập), cả hai struct có thể cùng có mặt — code ưu tiên struct độc lập. Hệ quả phụ của `or`: giá trị 0 bị đối xử như "không có" (chấp nhận được vì target 0 vốn vô nghĩa, nhưng phải biết).
- **`bidding_strategy` là chuỗi thô, hai hệ enum khác nhau:** Google (`TARGET_CPA`, `MANUAL_CPC`, …) và Meta (`LOWEST_COST_WITH_BID_CAP`, `COST_CAP`, …) không dùng chung bảng giá trị; playbook so khớp chuỗi chính xác theo từng nền tảng. Nếu provider đổi tên/bổ sung enum, quy tắc liên quan sẽ **im lặng không khớp** thay vì báo lỗi — lỗi "mù êm" khó phát hiện nhất của bề mặt này.

### 3.4 Caveat còn lại

- **Cửa sổ 7 ngày:** mọi con số đều là aggregate 7 ngày (Google `LAST_7_DAYS`, Meta `date_preset=last_7d`). Mọi suy luận "theo tháng" (ví dụ ngưỡng ~30 conversions/tháng của nghiên cứu Google §2.1) là ngoại suy của người đọc, không phải dữ liệu.
- **Conversions của Meta phụ thuộc cấu hình nội bộ:** chỉ tồn tại khi tổ chức đã chọn `meta_action_type` trong goals VÀ `account_currency` của insights khớp tiền tệ đã lưu của tài khoản. Không khớp → `conversions`/`conversion_value` để `None` một cách im lặng và toàn bộ quy tắc CPA/ROAS phía Meta tắt theo — đừng diễn giải là "Meta không có chuyển đổi".
- **Làm tròn tại nguồn:** adapter làm tròn tiền tới 2 chữ số, `roas` tới 3 chữ số ngay khi chuẩn hoá; snapshot và baseline (trung vị) kế thừa số đã làm tròn này.
- **Fail-closed khi dữ liệu thiếu:** phân trang Meta lỗi/trùng cursor/vượt 500 dòng → hủy toàn bộ lần quét (HTTP 409/502), không kết luận từ dữ liệu dở; Google vượt 500 campaign cũng 409. Một lần quét thiếu là KHÔNG có finding mới, không phải "mọi thứ đều ổn".
