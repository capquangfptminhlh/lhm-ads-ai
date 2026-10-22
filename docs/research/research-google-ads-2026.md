# Nghiên cứu: Tối ưu Google Ads 2025–2026 — Giảm giá thầu/CPA, tăng ROAS

**Ngày nghiên cứu:** 2026-10-22
**Phạm vi:** Best practice hiện hành (cuối 2025 – 2026) cho Google Ads, phục vụ việc xây "skill" tối ưu cho công cụ quản lý quảng cáo SMB/agency tại Việt Nam.
**Giới hạn dữ liệu của công cụ (advisor):** chỉ nhìn được aggregate cấp campaign trong 7 ngày gần nhất — chi tiêu (spend), clicks, impressions, CTR, conversions, conversion value, CPA, ROAS, trạng thái campaign — cộng tuỳ chọn mục tiêu target CPA / target ROAS do người dùng đặt. Mọi đánh giá "detect được hay không" trong tài liệu này đều xét trên đúng tập dữ liệu đó.

**Quy ước mức độ tin cậy (dùng xuyên suốt tài liệu):**
- **[A] Chính thức từ Google** — tài liệu Google Ads Help, Google Ads Developer Blog, hoặc phát biểu chính thức của nhân sự Google (podcast Ads Decoded do Google sản xuất).
- **[B] Đồng thuận giới thực hành** — nhiều nguồn practitioner uy tín cùng khẳng định, không có văn bản chính thức tương đương.
- **[C] Tranh cãi / số liệu marketing** — con số do Google hoặc bên bán công cụ công bố để quảng bá, hoặc có nguồn độc lập cho kết quả trái ngược. Không dùng làm ngưỡng cứng.

> Lưu ý trung thực: một số blog "2026" trên web chứa nội dung AI kém chất lượng, thậm chí mâu thuẫn nhau (ví dụ một blog nói Google cắt 4 attribution model vào "tháng 7/2026" trong khi việc này thực tế hoàn tất năm 2023). Tài liệu này chỉ lấy số liệu khi có nguồn nêu rõ và ghi rõ mức tin cậy.

---

## 1) Thay đổi nền tảng 2025–2026 (làm thay đổi lời khuyên cũ)

### 1.1. AI Max for Search — từ tuỳ chọn thành gần như bắt buộc
- **[A]** AI Max for Search ra mắt dạng open beta ngày 6/5/2025; **thoát beta ngày 15/4/2026**. Đây là một *cài đặt* trên campaign Search có sẵn (không phải loại campaign mới), gồm 3 tính năng: **search term matching** (mở rộng truy vấn vượt danh sách keyword bằng broad match + công nghệ keywordless), **text customization** (AI viết lại headline/description theo truy vấn), **final URL expansion** (chọn landing page phù hợp nhất trên site). Kèm công cụ lái: brand controls, location controls, text guidelines.
- **[A]** **Tự động nâng cấp (auto-upgrade) từ 1–30/9/2026**: mọi campaign Search còn dùng *campaign-level broad match* hoặc *Automatically Created Assets (ACA)* đều bị chuyển sang AI Max, **không có opt-out**; từ 3/8/2026 không tạo mới được hai dạng legacy này. **Dynamic Search Ads (DSA)** bị chuyển sau: tháng **2/2027**.
- **[C]** Google công bố số liệu nội bộ: dùng trọn bộ AI Max cho "+7% conversions/conversion value ở CPA/ROAS tương đương" so với chỉ dùng search term matching (dữ liệu nội bộ 2026, nhà quảng cáo phi bán lẻ); lúc beta là "+14% conversions". Đây là số marketing của Google.
- **[C — có kiểm chứng độc lập trái chiều]** Các phân tích độc lập năm 2025 ghi nhận mặt trái: một test tháng 8/2025 thấy ~99% impressions từ AI Max không tạo conversion trên ~30.000 search terms; phân tích >250 campaign bán lẻ (11/2025) thấy ROAS của traffic AI Max thấp hơn ~35%; Search Partner Network trong AI Max bị báo cáo ROAS thấp hơn ~37%. Kết luận thực hành: AI Max **không phải "bật là tốt"** — phải soi search terms theo match type "AI Max" hằng tuần và phủ định (negatives) đều tay (xem mục 2.6).
- **[A]** Quảng cáo trong **AI Overviews / AI Mode** được lấy từ chính các campaign Search (broad match/AI Max), Performance Max, Shopping hiện có — không có cài đặt loại trừ (opt-out) cho vị trí này.

### 1.2. Tháng 6/2026: Target CPA / Target ROAS quay lại thành chiến lược độc lập (standalone)
- **[A]** Từ tháng 6/2026, Google Ads khôi phục nhãn **Target CPA** và **Target ROAS** thành chiến lược đặt giá độc lập, tách khỏi nhãn gộp "Maximize conversions with a Target CPA" / "Maximize conversion value with a Target ROAS" nhiều năm trước đó. Google khẳng định đây **chỉ là thay đổi nhãn hiển thị — logic đặt giá không đổi**, không cần thao tác gì từ nhà quảng cáo.
- **[A — quan trọng với nhà phát triển công cụ]** Google Ads Developer Blog (16/6/2026) làm rõ khác biệt hành vi ở tầng API: chiến lược có target sẽ **tập trung đạt target đã đặt thay vì tự hạ bid để tối đa hoá volume khi ngân sách bị giới hạn**. Các enum `TARGET_CPA` / `TARGET_ROAS` được ưu tiên trở lại trong API — công cụ nào đọc/ghi bid strategy qua API phải xử lý cả hai dạng nhãn (cũ gộp, mới độc lập) trong giai đoạn chuyển đổi.

### 1.3. Thay đổi đặt giá ngày 17/8/2026: campaign bị giới hạn ngân sách bị kéo VỀ target
- **[A]** Từ **17/8/2026**, các campaign dùng Target CPA / Target ROAS mà bị *giới hạn bởi ngân sách* (budget-capped) trên Search, Shopping, Performance Max, Demand Gen và Travel sẽ **đặt giá hướng về đúng target đã khai**, thay vì hành vi cũ là đặt giá *dưới* target để "kéo giãn" ngân sách hạn hẹp.
- **Hệ quả thực tế [A/B]:** campaign đang "thắng" target (CPA thực tế thấp hơn target CPA) sẽ **không còn giữ được khoản tiết kiệm đó** — hệ thống sẽ bid mạnh lên tới target. Người dùng thấy CPA *tăng lên gần target* sau 17/8/2026 không hẳn là tài khoản xấu đi, mà là hành vi nền tảng đã đổi. Lời khuyên cũ "đặt target thấp hơn thực tế để tiết kiệm" nay phản tác dụng: muốn chi ít hơn thì phải **hạ target hoặc hạ ngân sách**, và Google (Ginny Marvin, 8/2026) nói rõ target nay là "đòn bẩy hiệu quả" (efficiency lever) trong campaign bị cap ngân sách.
- **[A]** Khung quyết định mà Google đưa ra (Ads Decoded, 10/2026): có ràng buộc hiệu quả → dùng Target CPA/Target ROAS và điều chỉnh target để lấy reach/hiệu quả; có ngân sách cố định và không ràng buộc → dùng Maximize Conversions/Maximize Conversion Value và để ngân sách làm đòn bẩy.

### 1.4. Tháng 10/2026: Google PM nói "đổi target/ngân sách trên campaign ổn định KHÔNG gây learning period"
- **[A — phát biểu chính thức, nhưng mâu thuẫn với tài liệu viết cũ]** Tal Akabas (Director of Product Management, Google Ads) trên podcast Ads Decoded (15/10/2026): với campaign đã ở trạng thái ổn định (steady state), **thay đổi target hoặc ngân sách không tạo learning period** — hệ thống scale bid tỉ lệ trực tiếp theo thay đổi target vì đã có sẵn dữ liệu "bid landscapes"; chỉ campaign **mới tinh** mới có learning thực sự. Thay đổi cấu trúc (assets mới, targeting mới, đổi bid strategy) thì không nằm trong khẳng định này.
- **[A — phần còn hiệu lực]** Dù không "reset học", Google vẫn khuyên **chờ ít nhất 1 chu kỳ chuyển đổi (conversion cycle)** sau khi đổi target mới đánh giá/đổi tiếp (Ads Decoded 3/2026), và **chờ 1–2 chu kỳ chuyển đổi** sau khi tăng ngân sách mới phán xét hiệu quả (thông điệp 6/2026 quanh thay đổi 17/8). Đây là vấn đề *đo lường* (conversion lag), không phải học lại.
- **[B]** Giới thực hành phần lớn vẫn giữ kỷ luật thay đổi nhỏ (xem mục 2.3) vì tài liệu Help viết vẫn mô tả learning status và vì khẳng định của PM chưa kèm dữ liệu công bố. **Trạng thái trung thực: đang tranh cãi giữa phát biểu PM 10/2026 [A] và thói quen/tài liệu cũ [A cũ + B].**

### 1.5. Bộ công cụ ngân sách mới 2026
- **[A] Campaign total budgets**: đặt ngân sách cho cả "flight" thay vì theo ngày, Google tự pacing tới ngày kết thúc; open beta từ 15/1/2026 cho Search/PMax/Shopping, flight **3–90 ngày**, **chỉ áp được cho campaign mới** (không bật được trên campaign có sẵn).
- **[A] Promotion mode**: lên lịch cửa sổ khuyến mãi **3–14 ngày** với độ dung sai ROAS (ROAS tolerance) nới lỏng + ngân sách ngày tăng thêm, tự tắt khi hết cửa sổ; beta 15/6/2026 cho Search/PMax, đang thoát beta tháng 10/2026. Chi tiết mới (10/2026): trong cửa sổ promotion, Google **bật kèm Smart Bidding Exploration**.
- **[A] Smart Bidding Exploration**: cho phép campaign vượt target một khoảng dung sai ROAS nhỏ để săn auction tăng thêm mà bình thường không vào được; Google báo cáo (qua PPC Land, 5/2026) trung bình **+27% unique converting users** cho Search **[C — số của Google]**. Đã mở cho PMax không kèm feed; PMax bán lẻ (có product feed) đang rollout 10/2026; Shopping sắp tới. Điều kiện: ngân sách **không bị cap**, nếu không hệ thống bị bó.
- **[A] Channel prioritization + budget allocation** (công bố 14/10/2026): trong campaign đa kênh (PMax/Demand Gen…), xếp kênh High/Low priority; kênh Low bị **cap theo % ngân sách ngày trung bình** (ví dụ 10%); kênh High được cấp tiền trước. Dùng được cùng shared budgets. Lưu ý: tài liệu Help và podcast lệch nhau về việc Demand Gen có hỗ trợ budget allocation hay không — chưa ngã ngũ.
- **[A] Demand-led budgets** (khái niệm Google thúc đẩy 2026): để ngân sách "mở" cho nhu cầu biến động, hiệu quả do target quản, thay vì khoá cứng ngân sách ngày — đây là định hướng truyền thông của Google, **không phải cơ chế bắt buộc**; SMB ngân sách cố định vẫn dùng ngân sách ngày bình thường.

### 1.6. Attribution: chỉ còn Data-Driven và Last Click
- **[A]** Bốn model quy tắc (First Click, Linear, Time Decay, Position-Based) đã bị loại bỏ: không chọn được cho conversion action mới từ 6/2023 và **tự động migrate sang Data-Driven Attribution (DDA) từ 9/2023** (lý do Google nêu: <3% conversions dùng các model này). Một số blog 2026 viết sai thời điểm này thành "giữa 2026" — không đúng với thông báo gốc của Google.
- **[A/B]** DDA là mặc định và là model nuôi Smart Bidding chính xác nhất; Google đã bỏ ngưỡng cứng tối thiểu để dùng DDA, nhưng giới thực hành lưu ý DDA cần lượng dữ liệu đáng kể mới phân bổ credit "ra hồn" — con số thường được trích là khoảng **200–300 conversions / 30 ngày** (có nguồn nói Google khuyến nghị ~200 conversions + 2.000 ad interactions / 30 ngày) — **[B]**, không có ngưỡng cứng chính thức hiện hành.
- **[A]** Đổi attribution model có hiệu lực **hồi tố** (re-credit lịch sử): ROAS/CPA lịch sử có thể nhảy sau khi đổi model mà không có sale mới — khi tư vấn phải cảnh báo điều này.

### 1.7. Demand Gen nuốt Video Action Campaigns; các thay đổi kênh khác
- **[A/B]** Video Action Campaigns ngừng tạo mới từ 4/2025 và **tự động chuyển sang Demand Gen từ 7/2025** (Demand Gen phủ YouTube, Shorts, Discover, Gmail; đa định dạng image + video).
- **[A — phát biểu PM]** Trên Ads Decoded 1/10/2026, một PM của Google gọi **$100/ngày là "sàn" (floor)** cho một campaign Demand Gen — đây là phát biểu định hướng, không phải yêu cầu kỹ thuật cứng.
- **[A]** Performance Planner **ngừng hỗ trợ Display và Video từ 9/3/2026**.
- **[A]** Customer lifecycle goals mở rộng: new customer acquisition (value mode / new-customer-only mode / **reporting-only mode** mới rollout 10/2026 — xem số liệu khách mới mà không đổi bidding), **win-back mode** (PMax + Search), **re-engagement only mode** (ra mắt PMax 10/2026, Search/Shopping theo sau), **loyalty mode** (GA trên PMax + Shopping).
- **[A]** Seasonality adjustments: Google (2026) nhấn mạnh các sự kiện lớn quen thuộc (Black Friday…) hệ thống **đã tự nhận biết**, chỉ nên dùng seasonality adjustment khi khuyến mãi *lớn hơn hẳn năm trước* hoặc *lệch chu kỳ*; cửa sổ ngắn (ví dụ flash sale ~48 giờ). Data exclusions dùng khi dữ liệu hỏng (tracking outage, hết hàng) để loại giai đoạn nhiễu khỏi mô hình học.

---

## 2) Chiến thuật giảm giá thầu / CPA

> Mỗi chiến thuật ghi: cơ chế — điều kiện áp dụng — ngưỡng số liệu (chỉ khi có nguồn) — **Detect từ aggregate campaign 7 ngày?** (Yes / Partially / No).

### 2.1. Chọn đúng bid strategy theo lượng conversion (nền tảng của mọi tối ưu)
- **Cơ chế:** Smart Bidding đặt bid theo từng auction (auction-time bidding) dựa trên tín hiệu device, location, time of day, browser, OS, remarketing list… Chọn sai "hàm mục tiêu" (volume vs. efficiency) là lỗi tốn tiền phổ biến nhất.
- **Điều kiện / ngưỡng [A — Google khuyến nghị trong tài liệu Help, được PPC Land trích dẫn 2026]:**
  - **Target CPA:** đánh giá trên giai đoạn tích lũy **≥ 30 conversions** (khoảng ≥ 1 tháng). Google Ads Help về value-based bidding: chọn goal có **≥ 15 conversions/tháng** và độ trễ chuyển đổi ngắn làm mục tiêu bid chính.
  - **Target ROAS:** Google khuyến nghị **≥ 50 conversions** trong giai đoạn đánh giá, và conversions phải mang **giá trị tiền tệ đa dạng, có ý nghĩa** (giá trị đồng nhất = hệ thống không có gì để tối ưu).
  - **Maximize Conversions / Maximize Conversion Value:** không có ngưỡng cứng; là lựa chọn khởi động (cold start) — chính Google (Ads Decoded 3 & 10/2026) khuyên **đi thẳng vào chiến lược theo conversion ngay từ đầu**, không qua Maximize Clicks; chạy không target để lấy CPA/ROAS thực tế, sau đó gắn target. Tháng 3/2026 Google còn nói rõ: có thể **bắt đầu ngay bằng chiến lược đích** (kể cả có target) nếu đã có cơ sở đặt target.
  - **[B]** Đồng thuận practitioner: < ~15–30 conversions/30 ngày/campaign thì tCPA/tROAS nhiễu mạnh; gom dữ liệu (hợp nhất campaign, mục 2.5) hoặc dùng Maximize Conversions không target trong lúc chờ đủ volume. Một số nguồn cực đoan khuyên Manual CPC dưới ngưỡng — đây là **[B thiểu số]**, trái với khuyến nghị hiện hành của Google.
- **Detect?** **Partially.** Từ aggregates tính được *pace* conversion (conversions 7 ngày × ~4,3 ≈ pace 30 ngày) → cảnh báo được "campaign chạy quá ít conversion để nuôi target-based bidding" (< ~7 conversions/7 ngày ≈ <30/tháng). Nhưng công cụ **không thấy bid strategy** trong aggregates → chỉ flag được dạng "nghi ngờ thiếu dữ liệu cho Smart Bidding có target" và gợi ý kiểm tra, không kết luận chắc chắn.

### 2.2. Hiệu chỉnh target CPA/ROAS về mức thực tế (target "không tưởng" là nguyên nhân nghẽn volume số 1)
- **Cơ chế:** Target thấp hơn xa khả năng thực tế → hệ thống bỏ qua phần lớn auction → mất volume, CPA dao động; target cao hơn xa thực tế → sau thay đổi 17/8/2026, hệ thống sẽ bid lên tới target và *đốt* khoản chênh. Target đúng = neo theo hiệu quả thực tế 30 ngày gần nhất.
- **Điều kiện / ngưỡng:**
  - **[B]** Đặt target khởi đầu ở mức CPA/ROAS thực tế (hoặc nới ~10–20% so với thực tế) rồi siết dần.
  - **[A]** Nếu campaign ở trạng thái "Limited by budget" (bị giới hạn ngân sách): hoặc bỏ target và để ngân sách quản chi tiêu, hoặc đặt target **bằng đúng hiệu quả đã đạt trong 30 ngày qua** và tăng ngân sách đủ rộng để hết bị limit (khuyến nghị ngay trong trang Help của Google).
- **Detect?** **Yes (khi có target của người dùng).** So CPA 7 ngày với target CPA người dùng đặt trong công cụ: lệch > ~20–30% kéo dài → flag "target không thực tế so với hiệu quả hiện tại". ROAS tương tự. Lưu ý conversion lag: với chu kỳ chuyển đổi dài, 7 ngày có thể chưa đủ conversions ghi nhận — nên ghi kèm cảnh báo về độ trễ (xem 4.5).

### 2.3. Kỷ luật thay đổi target/ngân sách: nhỏ, thưa, chờ đủ chu kỳ chuyển đổi
- **Cơ chế:** Thay đổi lớn/dồn dập làm nhiễu đo lường và (theo tài liệu cũ) có thể đưa campaign về learning; thay đổi nhỏ từng bước giữ hệ thống ổn định và cho phép quy kết nhân quả.
- **Ngưỡng:**
  - **[A — tài liệu Help chính thức hiện hành, trang quản lý Smart Bidding cho Display/Search]** Google viết: *"tăng hoặc giảm bid 20% và chờ một tuần giữa các lần thay đổi"*; thay đổi target CPA/ROAS nhỏ và thưa thì ít gây vấn đề; ad group có > 100 conversions/ngày thì đổi thường xuyên hơn được.
  - **[B]** Giới thực hành phổ biến hoá thành "quy tắc 20%": mỗi lần đổi ngân sách/target **≤ 15–20%**, cách nhau **3–7 ngày** (nhiều nguồn: ngân sách không đổi quá ~20%/tuần).
  - **[A — mới, tranh cãi với hai điểm trên]** PM Google 10/2026 nói đổi target/ngân sách trên campaign ổn định **không** gây learning period (mục 1.4). Kỷ luật 20% do đó nên hiểu là kỷ luật *đo lường và rủi ro* (tránh sốc chi tiêu), không còn là "tránh reset thuật toán" một cách chắc chắn. Khi tư vấn: khuyên thay đổi vừa phải + **chờ ≥ 1 chu kỳ chuyển đổi** rồi mới đánh giá [A].
- **Detect?** **No.** Aggregates 7 ngày không cho biết lịch sử thay đổi cài đặt (change history nằm ngoài phạm vi dữ liệu) → chỉ đưa vào checklist hướng dẫn.

### 2.4. Xử lý campaign "đốt tiền, 0 conversion"
- **Cơ chế:** Spend > 0 mà conversions = 0 trong cửa sổ đủ dài là rò rỉ rõ nhất: sai tracking, sai targeting, search terms rác, hoặc offer/landing không chuyển đổi. Mỗi ngày chạy thêm là mất tiền nguyên vẹn.
- **Điều kiện:** Cần xét conversion lag trước khi kết luận (ngành có chu kỳ chốt dài thì 7 ngày chưa đủ). Nếu tracking hỏng thì conversions = 0 là *triệu chứng của tracking*, không phải của traffic — phải kiểm tra tracking trước khi tắt campaign.
- **Detect?** **Yes — đây là tín hiệu detect sạch nhất từ aggregates.** Flag: spend vượt một ngưỡng có ý nghĩa (ví dụ ≥ 1–2× target CPA của người dùng, hoặc ngưỡng tiền tuyệt đối) mà conversions = 0 trong 7 ngày → cảnh báo mức cao kèm checklist kiểm tra tracking trước, rồi mới tới targeting/search terms.

### 2.5. Hợp nhất cấu trúc campaign (consolidation) — gom tín hiệu, giảm phân mảnh
- **Cơ chế:** Smart Bidding học theo campaign; chia ngân sách thành nhiều campaign nhỏ làm mỗi campaign thiếu conversion để học, đồng thời các campaign tự đấu giá cạnh tranh và phân mảnh ngân sách. Xu hướng 2025–2026: **ít campaign hơn, rộng hơn** — broad match + Smart Bidding có target, gom theo mục tiêu kinh doanh/địa lý/biên lợi nhuận thay vì theo từng keyword.
- **Điều kiện / ngưỡng:**
  - **[A]** Broad match "đặc biệt hợp" với target-based Smart Bidding: hệ thống đặt bid riêng cho từng auction của từng query (tài liệu Google, dẫn qua PPC Land 2026).
  - **[B]** Quy tắc thực hành: campaign nào không đạt nổi ~15–30 conversions/tháng là ứng viên bị gom. Tách campaign chỉ khi có lý do kinh doanh thật (ngân sách riêng, địa lý, biên lợi nhuận khác biệt rõ) — lúc đó dùng **portfolio bid strategy** hoặc shared budget để vẫn gom tín hiệu/quản trị chung.
  - **[A]** Shared budgets (ngân sách dùng chung) được Google nêu như cách để tiền tự chảy tới nơi có nhu cầu trong một pool cố định — phù hợp triết lý demand-led mà không cần nới tổng ngân sách.
- **Detect?** **Partially.** Từ danh sách campaign toàn tài khoản: đếm được số campaign có conversions rất thấp (pace < 30/tháng) và tỉ lệ ngân sách bị chia nhỏ → flag "nghi ngờ phân mảnh cấu trúc". Không thấy được cấu trúc ad group/keyword bên trong → mức độ chi tiết dừng ở gợi ý.

### 2.6. Kiểm soát lãng phí search terms & negative keywords
- **Cơ chế:** Broad match/AI Max mở rộng truy vấn — phần mở rộng không liên quan vẫn tính tiền theo click. Rà search terms report + thêm negative keywords (cấp ad group/campaign/account negative lists) là cách cắt CPC lãng phí trực tiếp nhất trong kỷ nguyên broad.
- **Điều kiện / thực hành [B]:**
  - Rà search terms **hằng tuần**; với AI Max, lọc riêng theo match type "AI Max" (báo cáo AI Max của Google) — lưu ý bộ lọc này bỏ sót nhóm "Other search terms" nên có thể đánh giá thấp chi tiêu AI Max thực tế.
  - Ưu tiên phủ định các truy vấn có spend cao + 0 conversion, và các cụm ý định sai rõ ràng (miễn phí/free, tuyển dụng, tự làm/DIY… tuỳ ngành).
  - Đừng phủ định thái quá theo kiểu exact-match từng từ đơn lẻ: với Smart Bidding, phủ định quá tay làm hẹp tín hiệu học; phủ định theo *chủ đề/ý định* hiệu quả hơn.
  - **[C]** Các con số kiểu "X% ngân sách Google Ads bị lãng phí vì search terms" lưu hành trong marketing của các công cụ audit — **không có nguồn độc lập đáng tin, không dùng làm ngưỡng**.
- **Detect?** **No (trực tiếp) / Partially (gián tiếp).** Aggregates không chứa search terms. Gián tiếp: CTR rất thấp so với mặt bằng tài khoản + CPA cao + conversions thấp là *gợi ý* traffic không liên quan → đưa vào checklist "rà search terms & negatives" khi campaign có các dấu hiệu này, không kết luận thay người dùng.

### 2.7. Ngân sách & pacing: đừng để campaign tốt bị "chết đói", campaign xấu ăn hết
- **Cơ chế:** Ngân sách ngày khoá cứng + target (sau 17/8/2026) khiến campaign hiệu quả bị cap và bỏ lỡ auction tốt; ngược lại campaign kém vẫn tiêu hết phần của nó nếu tách ngân sách riêng. Pacing hợp lý = phân bổ theo hiệu quả biên.
- **Thực hành:**
  - **[A]** Dùng **shared budgets** cho nhóm campaign cùng mục tiêu để tiền chảy theo nhu cầu [A]; cân nhắc **campaign total budgets** cho chiến dịch có ngày kết thúc rõ (flight 3–90 ngày, chỉ campaign mới) [A].
  - **[A/B]** Campaign đang đạt target mà bị limited by budget = cơ hội rẻ nhất để tăng volume: tăng ngân sách từng bước ≤ ~20%/lần hoặc nới target — và sau 17/8/2026 phải ý thức hệ thống sẽ bid tới target (mục 1.3).
  - **[A]** **Promotion mode** cho các đợt cao điểm ngắn (3–14 ngày) thay vì sửa target/ngân sách thủ công rồi quên khôi phục [A].
  - **[B]** Rà soát phân bổ ngân sách theo ROAS/CPA biên giữa các campaign mỗi tuần; cắt ngân sách campaign dưới target kéo dài để dồn cho campaign đạt target mà đang bị cap.
- **Detect?** **Partially/No.** Aggregates **không có trường ngân sách** → không biết campaign có bị limited by budget hay không. Detect được phần phân bổ lệch: campaign ROAS cao nhưng spend nhỏ vs. campaign ROAS thấp ngốn spend lớn → flag "nghi ngờ phân bổ ngân sách chưa theo hiệu quả" (mức gợi ý). Trạng thái "Limited by budget" lấy được qua API (bid strategy status) nhưng **ngoài tập dữ liệu hiện tại** — ghi nhận là khoảng trống dữ liệu nên bổ sung.

### 2.8. Ngừng "vặn" các núm bid adjustment không còn tác dụng với Smart Bidding
- **Cơ chế / sự thật nền tảng [A — Google Ads Help "About bid adjustments"]:** Với các chiến lược Smart Bidding theo conversion (Target CPA, Target ROAS, Maximize Conversions, Maximize Conversion Value):
  - **Bid adjustment theo location, ad schedule, audience, demographic: bị bỏ qua** — hệ thống đã tự tối ưu theo các tín hiệu đó ở cấp auction. Ad schedule vẫn có tác dụng ở khía cạnh *chặn/giờ chạy* (campaign chỉ chạy trong khung giờ đã đặt), nhưng % điều chỉnh giá trong khung giờ không được dùng.
  - **Device bid adjustment:** với Target CPA, device adjustment **không đổi bid mà đổi chính target CPA theo device** (mobile/desktop/tablet có thể đặt target riêng) [A]; với Target ROAS, ngoại lệ duy nhất còn tác dụng là mobile **−100%** (tắt hẳn mobile) [A — qua tài liệu Help được Optmyzr trích dẫn].
- **Hệ quả tư vấn:** Thời gian chỉnh % bid adjustment là thời gian lãng phí; đòn bẩy đúng là target, ngân sách, conversion value và exclusions. Nếu người dùng phàn nàn "đã tăng +30% cho khu vực tốt mà không đổi gì" — đó là *đúng thiết kế*, không phải lỗi.
- **Detect?** **No.** Cài đặt bid adjustment không nằm trong aggregates → checklist/hướng dẫn.

### 2.9. Ad strength & RSA: ảnh hưởng CPC gián tiếp qua Quality Score — đừng thần thánh hoá
- **Sự thật nền tảng:**
  - **[A/B]** **Ad Strength KHÔNG phải yếu tố xếp hạng**: không ảnh hưởng trực tiếp Ad Rank hay Quality Score; RSA bị chấm "Poor" vẫn thắng auction bình thường. Ad Strength là công cụ chẩn đoán độ đa dạng/khớp từ khoá của asset.
  - **[A/C]** Google công bố cải thiện Ad Strength từ Poor → Excellent *liên quan tới* ~12% impressions hơn (một số tài liệu Google khác nêu ~15% clicks/conversions) — đây là tương quan trung bình do Google công bố, không phải cam kết **[C]**.
  - CPC thực tế bị chi phối bởi **Ad Rank = bid × Quality Score** (expected CTR, ad relevance, landing page experience) — asset đa dạng và khớp ý định giúp hai thành phần đầu **[A về cơ chế QS]**.
- **Thực hành [B]:** Đủ **15 headlines + 4 descriptions** với nội dung *khác biệt thật* (từ khoá, lợi ích, bằng chứng xã hội, CTA, giá, brand); ghim (pin) tối thiểu — chỉ ghim brand vào vị trí 1 hoặc nội dung pháp lý bắt buộc, và ghim 2–3 phương án cho cùng một vị trí để hệ thống còn lựa chọn; mục tiêu thực tế là Ad Strength **"Good"**, đừng bóp méo headline để đuổi "Excellent"; có ~2 RSA/ad group với thông điệp khác nhau (Google công bố RSA thứ hai liên quan +6,6% conversions ở CPA tương đương — **[C] số của Google**); thay asset bị chấm "Low" vài cái một lần sau mỗi 4–6 tuần.
- **Detect?** **No.** Ad strength/asset không có trong aggregates. Gián tiếp: CTR campaign thấp bất thường kéo dài là gợi ý yếu về creative/độ liên quan → checklist. **Không được kết luận "CPC cao vì ad strength kém" từ aggregates.**

### 2.10. Seasonality adjustments & data exclusions (đòn bẩy ngắn hạn, dùng đúng dịp)
- **Cơ chế [A]:** Seasonality adjustment báo trước cho Smart Bidding biết conversion rate sắp lệch bất thường trong cửa sổ ngắn (khuyến mãi lớn hơn năm trước, flash sale ~48 giờ, lệch chu kỳ). Data exclusion loại các ngày dữ liệu hỏng (tracking chết, web sập, hết hàng) khỏi dữ liệu học.
- **Điều kiện:** Sự kiện định kỳ quen thuộc thì hệ thống tự xử lý [A]; lạm dụng seasonality adjustment cho giai đoạn dài sẽ làm sai lệch target.
- **Detect?** **No** → checklist theo mùa vụ/sự kiện của doanh nghiệp.

---

## 3) Chiến thuật tăng ROAS

### 3.1. Value-based bidding đúng nghĩa: cho hệ thống thấy GIÁ TRỊ thật, không phải số đếm
- **Cơ chế:** Maximize Conversion Value / Target ROAS chỉ tối ưu đúng khi conversion value phản ánh giá trị kinh doanh thật và *khác nhau giữa các conversion*. Giá trị đồng nhất/placeholder → hai chiến lược này suy biến thành Maximize Conversions.
- **Thực hành [A — trang "Value-based bidding best practices" của Google]:**
  - Ecommerce: truyền **giá trị đơn hàng động** theo từng giao dịch (nâng cao: biên lợi nhuận thay vì doanh thu gộp — hướng practitioner [B] gọi là profit-based bidding).
  - Lead gen: gán giá trị theo giai đoạn phễu (lead → qualified lead → khách hàng) = giá trị hợp đồng × tỉ lệ chốt; chỉ chọn **một giai đoạn phễu** làm goal bid chính — giai đoạn có độ trễ ngắn và ≥ 15 conversions/tháng [A].
- **Detect?** **Partially.** Detect được lỗi chí tử: **conversions > 0 nhưng conversion value = 0** (hoặc ROAS không tính được) → mọi tư vấn ROAS đều vô nghĩa, flag ưu tiên cao. Không detect được *phân bố* giá trị (đồng nhất hay đa dạng) từ tổng aggregate.

### 3.2. Offline conversion import + Enhanced Conversions for Leads — đòn bẩy ROAS lớn nhất cho lead gen
- **Cơ chế [A]:** Gửi ngược kết quả CRM (qualified, chốt đơn, doanh thu thật) về Google Ads qua **offline conversion import** (khớp bằng gclid; cửa sổ import tới **90 ngày** từ click) hoặc **Enhanced Conversions for Leads** (khớp bằng email/số điện thoại đã hash SHA-256 — không bị giới hạn bởi hạn gclid, hợp chu kỳ bán dài). Smart Bidding từ đó tối ưu theo *doanh thu* thay vì theo *form rẻ*.
- **Điều kiện [A/B]:** Cần kỷ luật dữ liệu: upload **thường xuyên, lý tưởng hằng ngày** [A]; mỗi giai đoạn phễu là một conversion action riêng; khi đã có offline conversions, **hạ form fill xuống secondary** để tín hiệu rẻ không lấn át tín hiệu tiền [B]; form phải có chống spam vì bot fill cũng thành "conversion" và dạy hệ thống săn traffic rác [B].
- **Detect?** **No.** Trạng thái import/enhanced conversions không có trong aggregates → đây là mục checklist tiên quyết số 1 cho tài khoản lead gen (mục 4).

### 3.3. Siết target ROAS theo bậc thang, dựa trên ROAS thực tế
- **Cơ chế:** Target ROAS đặt cao hơn xa thực tế → volume sụp; đặt thấp → sau 17/8/2026 hệ thống tiêu tới mức target cho phép. Siết dần theo hiệu quả thật (cùng kỷ luật mục 2.2/2.3) là cách tăng ROAS bền.
- **Detect?** **Yes (khi có target ROAS của người dùng).** ROAS 7 ngày vs. target: cao hơn target nhiều + spend bị nhỏ → gợi ý siết target lên để thu hiệu quả (hoặc nới ngân sách nếu muốn volume); thấp hơn target kéo dài → gợi ý nới target về thực tế hoặc rà soát giá trị conversion. Kèm cảnh báo conversion lag và nhiễu khi conversions ít (ROAS trên < ~15 conversions/7 ngày rất nhiễu) **[B]**.

### 3.4. Phân bổ lại ngân sách theo ROAS biên giữa các campaign
- **Cơ chế:** Tổng ROAS tăng khi tiền chảy từ campaign ROAS thấp (đã hết auction tốt) sang campaign ROAS cao đang bị giới hạn. Xem thêm mục 2.7.
- **Detect?** **Partially.** So sánh được ROAS × spend giữa các campaign trong cùng tài khoản từ aggregates → flag cặp "ROAS cao/spend thấp" vs "ROAS thấp/spend cao". Không biết trần ngân sách từng campaign nên chỉ ở mức gợi ý.

### 3.5. Vai trò Performance Max vs. Search — phân vai rõ, chống ăn thịt lẫn nhau (cannibalization)
- **Đồng thuận thực hành [B] + khung của Google [A]:**
  - **Search** = bắt nhu cầu có ý định rõ (brand + non-brand high-intent), kiểm soát qua search terms/negatives tốt nhất.
  - **Performance Max** = mở rộng phủ đa kênh (YouTube, Display, Discover, Gmail, Maps, Search) theo goal conversion/value, mạnh cho ecommerce có feed và cho mở rộng incremental; dùng **asset groups theo chủ đề/lợi nhuận**, **audience signals**, **brand exclusions** và **account-level negative lists** để PMax không nuốt traffic brand rẻ mà Search đang xử lý tốt — nếu không, ROAS "đẹp" của PMax phần lớn là ăn lại nhu cầu sẵn có.
  - **[A]** PMax dùng chung hệ Smart Bidding (tCPA/tROAS); các tính năng 2026 như channel prioritization/budget allocation (mục 1.5) và customer lifecycle modes áp dụng mạnh cho PMax.
  - **[B]** SMB ngân sách nhỏ: chạy tốt **một** hệ thống trước (thường là Search cho lead gen, PMax cho ecommerce có feed) thay vì chia mỏng cả hai dưới ngưỡng học.
- **Detect?** **Partially/No.** Aggregates có thể cho thấy nhiều campaign cùng chạy với conversion lác đác (gợi ý chia mỏng — mục 2.5), nhưng **không phân biệt được loại campaign** (Search/PMax/Demand Gen) trong tập dữ liệu mô tả → không kết luận về chồng lấn kênh; checklist là chính.

### 3.6. Smart Bidding Exploration & Promotion mode cho giai đoạn đẩy tăng trưởng có kiểm soát
- **Cơ chế [A]:** Exploration chấp nhận lệch ROAS trong dung sai nhỏ để mở auction mới (Google báo +27% unique converting users trên Search — **[C]**); Promotion mode (3–14 ngày) nới dung sai ROAS + tăng ngân sách có lịch tắt tự động, bật kèm exploration.
- **Điều kiện:** Ngân sách không bị cap; chỉ dùng khi nền tảng (tracking, value) đã chuẩn — exploration trên dữ liệu bẩn chỉ mua thêm rác đắt tiền.
- **Detect?** **No** → tính năng nâng cao, đưa vào checklist "khi đã sẵn sàng tăng trưởng".

### 3.7. Tín hiệu vòng đời khách hàng (customer lifecycle) cho ROAS dài hạn
- **[A]** New customer acquisition (value mode: khai LTV chênh lệch của khách mới), win-back, loyalty mode — bid theo giá trị vòng đời thay vì giá trị đơn đầu. Reporting-only mode (10/2026) cho phép đo tỉ lệ khách mới trước khi đổi bidding.
- **Detect?** **No** → checklist nâng cao, phụ thuộc Customer Match/CRM (mục 4).

---

## 4) Điều kiện tiên quyết (tracking & dữ liệu) — không có thì mọi chiến thuật trên đều mù

1. **Conversion tracking phải đúng và là primary goal thật [A].** Smart Bidding tối ưu đúng thứ được khai là conversion. Chỉ đếm *một* hành động chính phản ánh giá trị kinh doanh (mua hàng / lead đủ chuẩn); các hành động phụ (xem trang, micro-conversion) để secondary — không cho bid theo. Kiểm tra: tag/Google Tag Manager bắn đúng, không đếm trùng, không đếm cả bước trung gian.
2. **Enhanced Conversions (web + leads) bật và đạt match rate tốt [A].** Google khuyến nghị dùng enhanced conversions để đo lường bền vững trong bối cảnh cookie bên thứ ba suy giảm (dù Chrome đã giữ lại third-party cookies — quyết định 4/2025 — hướng first-party vẫn là chuẩn [A/B]).
3. **Conversion value đầy đủ [A].** Mọi conversion dùng cho value bidding phải có value; value = 0 hoặc thiếu là lỗi chặn (blocking) cho mọi tư vấn ROAS (detect được — mục 3.1).
4. **Offline data chảy đều [A/B].** CRM → Google Ads import hằng ngày/hằng tuần; trễ dữ liệu = bid theo tín hiệu cũ. Với chu kỳ bán > 90 ngày, bắt buộc Enhanced Conversions for Leads thay cho gclid import thuần.
5. **Tôn trọng conversion lag khi đánh giá [A].** Cửa sổ đánh giá phải ≥ 1 chu kỳ chuyển đổi của ngành; dữ liệu 7 ngày gần nhất luôn *thiếu* conversions của các click cuối cửa sổ. Mọi so sánh CPA/ROAS 7 ngày trong công cụ phải kèm lưu ý này, đặc biệt với ngành chu kỳ dài (B2B, dịch vụ giá trị cao).
6. **Attribution để DDA [A].** Không còn lựa chọn model quy tắc; kiểm tra conversion action nào còn ở Last Click có chủ đích hay không, và nhớ đổi model làm số liệu lịch sử nhảy hồi tố.
7. **Ngân sách và target nhất quán với nhau [A].** Target có ý nghĩa khi ngân sách không bóp nghẹt (và ngược lại, sau 17/8/2026 target là đòn bẩy hiệu quả chính khi bị cap). "Limited by budget" + target tham vọng = cấu hình mâu thuẫn cần xử lý theo mục 2.2.
8. **Dữ liệu công cụ còn thiếu (khoảng trống nên bổ sung vào adapter):** bid strategy + target ngay trong Google Ads, trạng thái bid strategy ("Learning"/"Limited by budget"), ngân sách campaign, loại campaign (Search/PMax/Demand Gen…), search terms, ad strength. Có các trường này, phần lớn mục "Partially/No" ở trên sẽ thành "Yes".

---

## 5) Nguồn

**Google chính thức (qua tài liệu Help / Developer Blog / podcast Ads Decoded):**
- Google Ads Help — *Value-based bidding best practices* (ngưỡng ≥15 conversions/tháng cho goal bid chính, enhanced conversions, upload dữ liệu thường xuyên): https://support.google.com/google-ads/answer/14792795
- Google Ads Help — *About bid adjustments* (Smart Bidding bỏ qua bid adjustment location/schedule/audience; ngoại lệ device): https://support.google.com/google-ads/answer/2732132
- Google Ads Help — *Manage your Smart Bidding strategy* (khuyên đổi bid ±20% và chờ một tuần giữa các lần): https://support.google.com/google-ads/answer/10276704
- PPC Land — *Google brings back Target CPA and Target ROAS as standalone bidding strategies* (trích dẫn Help Center + Developer Blog 16/6/2026; ngưỡng đánh giá ≥30 conversions cho tCPA, ≥50 cho tROAS): https://ppc.land/google-brings-back-target-cpa-and-target-roas-as-standalone-bidding-strategies/
- PPC Land — *Google Ads PM says target or budget changes cause no learning period* (Ads Decoded 15/10/2026: thay đổi 17/8/2026, campaign total budgets, promotion mode, Smart Bidding Exploration, channel prioritization, chờ 1–2 chu kỳ chuyển đổi): https://ppc.land/google-ads-pm-says-target-or-budget-changes-cause-no-learning-period/

**Bao phủ AI Max / thay đổi nền tảng:**
- PPC Land — *Google Ads broad match campaigns face AI Max auto-upgrade on September 1* (timeline đầy đủ 2025–2027, gồm các phân tích độc lập trái chiều về ROAS của AI Max): https://ppc.land/google-ads-broad-match-campaigns-face-ai-max-auto-upgrade-on-september-1/
- Brandstart — *Google and Microsoft Ads Changes: Autumn 2026* (hướng dẫn rà AI Max, trạng thái "Limited by budget"): https://brandstart.ie/resources/google-bing-ads-updates/
- Improvado — *Google Ads AI Max: What Changes in Your Reporting* (thay đổi reporting/API khi nâng cấp AI Max, kiểm chứng theo tài liệu Google 9/2026): https://improvado.io/blog/google-ads-ai-max-september-2026-upgrade

**Attribution & dữ liệu:**
- Wicked Reports — *Google Ads Data-Driven Attribution Explained (2026)* (chỉ còn DDA + Last Click; ngưỡng dữ liệu thực hành của DDA): https://www.wickedreports.com/blog/data-driven-conversion-attribution-in-google-ads?hs_amp=true
- Aubado — *Value-Based Bidding in Google Ads* (enhanced conversions for leads vs. offline import, cửa sổ gclid 90 ngày): https://www.aubado.com/blog/value-based-bidding-google-ads
- Upraw Media — *Offline Conversion Events for SaaS PPC* (phân tầng primary/secondary, hạ form fill khi đã có offline data): https://www.uprawmedia.com/blog/offline-conversion-events-saas-ppc

**Bid adjustments / RSA / thực hành:**
- Optmyzr — *The Right Bid Adjustments for Your Google Ads Bid Strategy* (bảng đối chiếu theo tài liệu Help): https://www.optmyzr.com/blog/which-bid-adjustments-work-with-my-bid-strategy-on-google-ads/
- SF Digital — *Smart Bidding Ignores Half the Settings You're Still Fiddling With*: https://www.sfdigital.co.uk/blog/google-ads-smart-bidding-ignores-manual-settings/
- Pace Ads — *Responsive Search Ads: Best Practices and Examples* (ad strength không phải yếu tố xếp hạng; số +12% impressions do Google công bố): https://paceads.com/blog/responsive-search-ads-best-practices-examples-and-strategy
- AdCrunch — *Responsive Search Ads: A Practical Guide for 2026* (số liệu RSA thứ hai/thứ ba do Google công bố): https://adcrunch.dev/blog/responsive-search-ads/

**Ghi chú về độ tin cậy của nguồn:** PPC Land là nguồn trade-press bám sát thông cáo/podcast chính thức của Google và thường trích nguyên văn tài liệu Help — độ tin cậy cao cho sự kiện nền tảng. Các blog agency (Groas, Aimers, GoGoChimp…) chỉ được dùng cho nội dung [B]/[C] và đã loại bỏ các khẳng định mâu thuẫn với tài liệu Google (ví dụ mốc thời gian attribution). Hai truy vấn tìm kiếm về "consolidation/shared budgets" và "wasted spend statistics" gặp lỗi công cụ trong phiên nghiên cứu; các mục tương ứng (2.5, 2.6, 2.7) được viết dựa trên tài liệu Google đã thu thập được trong các nguồn trên + đồng thuận thực hành chuẩn, và cố ý không trích con số thống kê lãng phí nào vì không kiểm chứng được nguồn độc lập.
