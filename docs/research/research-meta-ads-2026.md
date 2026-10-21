# Nghiên cứu: Tối ưu Meta Ads 2025–2026 — giảm CPA, tăng ROAS

> Phạm vi: best practice hiện hành (cuối 2025 → 2026) cho Meta Ads (Facebook/Instagram), phục vụ việc nâng cấp bộ máy tư vấn (advisor) của một công cụ quản lý quảng cáo cho SMB/agency Việt Nam.
> Bối cảnh dữ liệu của advisor hiện tại: **chỉ có aggregate cấp campaign trong 7 ngày gần nhất** — spend, clicks, impressions, CTR, conversions (một sự kiện được chọn, quy attribution 7d_click), conversion value, CPA, ROAS, status — cộng thêm (tuỳ chọn) target CPA / target ROAS do nhà quảng cáo đặt.
>
> Quy ước gắn nhãn độ tin cậy cho mọi khẳng định:
> - **[A — Meta chính thức]**: Meta tài liệu hoá / công bố (Business Help Center, Engineering at Meta, báo cáo earnings, phát biểu của nhân sự Meta).
> - **[B — Đồng thuận practitioner]**: nhiều agency/media buyer uy tín cùng quan sát, không có tài liệu chính thức.
> - **[C — Tranh cãi / marketing]**: con số do Meta tự báo cáo chưa kiểm chứng độc lập, hoặc nguồn độc lập cho kết quả ngược lại, hoặc chỉ một nguồn duy nhất.
>
> Quy ước cột "Nhận diện từ aggregate 7 ngày": **Có** = suy ra được trực tiếp từ các field hiện có; **Một phần** = thấy được dấu hiệu/hệ quả nhưng không thấy nguyên nhân hay cấu hình gây ra; **Không** = cấu hình/hiện tượng hoàn toàn vô hình với dữ liệu hiện tại.

---

## 1) Thay đổi nền tảng 2025–2026 (khiến lời khuyên cũ hết đúng)

### 1.1 Andromeda — tầng retrieval mới: creative thay thế targeting làm đòn bẩy chính
- **[A]** Andromeda là hệ thống retrieval (chọn shortlist quảng cáo trước khâu ranking/auction) dùng deep neural network, công bố bởi Engineering at Meta tháng 12/2024, chạy trên NVIDIA Grace Hopper + chip MTIA của Meta. Meta báo cáo: dung lượng mô hình retrieval tăng ~10.000 lần, **+6% retrieval recall** và **+8% ads quality** trên các segment được chọn. Đây là số liệu cấp hệ thống của Meta, không phải cam kết hiệu quả cho từng tài khoản.
- **[B]** Hệ quả vận hành được practitioner đồng thuận rộng rãi: hệ thống "đọc" nội dung creative (người trên hình, hook, format, bối cảnh, thông điệp) để quyết định quảng cáo hợp với ai; targeting thủ công hẹp và interest stacking mất dần tác dụng. "Creative diversity" — nhiều **concept thật sự khác nhau** (góc tiếp cận, format, persona, pain point) — trở thành đòn bẩy targeting chính. Meta không công bố con số creative tối thiểu; khoảng làm việc phổ biến của practitioner là **8–20 concept phân biệt mỗi campaign**; 10 biến thể của cùng một ý tưởng bị hệ thống coi như 1 (gộp theo Entity ID).
- **[C]** Nghiên cứu độc lập của Confect (3.014 nhà quảng cáo e-commerce, ~834 triệu USD spend) ghi nhận ROAS trung bình **giảm ~7%** trong giai đoạn Andromeda rollout, và các tài khoản trước đó thắng nhờ targeting thủ công hẹp bị ảnh hưởng nặng nhất. Một nghiên cứu của một vendor, tương quan không phải nhân quả — nhưng đủ để bác bỏ khẳng định "Andromeda tự động làm mọi tài khoản tốt lên".
- **[A]** Đi cùng chiều: GEM (Generative Ads Recommendation Model, Meta mô tả 11/2025) — Meta nói GEM tăng conversions **+5% trên Instagram, +3% trên Facebook Feed** trong Q2 2025 ở khâu ranking. Cả retrieval lẫn ranking nay đều là mô hình AI lớn; phần nhà quảng cáo kiểm soát thực chất còn: tín hiệu chuyển đổi, creative, ngân sách, mục tiêu.

### 1.2 Advantage+ trở thành mặc định, không còn là tuỳ chọn
- **[A]** Advantage+ Shopping Campaigns được đổi tên thành **Advantage+ Sales Campaigns** (mở rộng khỏi e-commerce: dùng cho cả leads/app). Advantage+ Sales nay hỗ trợ **nhiều ad set trong một campaign** (mỗi ad set tối đa 50 ads), xoá bỏ giới hạn cấu trúc cũ của ASC. **Existing Customer Budget Cap bị loại bỏ** khi chuyển đổi (practitioner ghi nhận từ 2/2025) — muốn tách khách mới/khách cũ thì tách ad set và loại trừ custom audience thủ công.
- **[A/C]** Số liệu Meta tự công bố về Advantage+: nhà quảng cáo dùng ASC thấy **ROAS cao hơn ~22%** (số liệu Meta, WARC dẫn lại); một bài test toàn cầu được nhân sự Meta trình bày cho kết quả **cost per result thấp hơn ~20%**; Meta cũng từng nêu Advantage+ sales cho cost per conversion tốt hơn ~9% trung bình. Tất cả đều là **số Meta tự đo trên hệ quy chiếu của Meta**.
- **[C]** Kiểm chứng độc lập cho kết quả trái chiều: phân tích 640 thí nghiệm incrementality của Haus cho thấy **58% số brand đạt incremental return cao hơn với campaign thủ công** (dẫn lại trong tổng hợp của Ryze). Kết luận trung thực: Advantage+ thắng *trung bình theo cách Meta đo*, nhưng không thắng mọi tài khoản theo incrementality.
- **[B]** Khi nào Advantage+ Sales thắng manual (đồng thuận practitioner): tài khoản e-commerce/catalog, có Pixel/CAPI tốt, ngân sách và lượng conversion đủ lớn (thường được nêu ở mức ≥50 conversion/tuần và ngân sách từ ~100 USD/ngày trở lên). Manual vẫn hơn khi: ngách rất hẹp cần kiểm soát đối tượng chặt, ngân sách nhỏ, tài khoản mới chưa có lịch sử conversion, cần test creative trong điều kiện kiểm soát.
- **[A]** Từ 2025, luồng tạo campaign trong Ads Manager mặc định đi theo Advantage+; cấu trúc Advantage+ hợp nhất (unified) được cho là bắt buộc với Marketing API v25.0 từ 18/2/2026 (PPC Land đưa tin; đây là thay đổi phía API, ảnh hưởng công cụ bên thứ ba nhiều hơn người dùng Ads Manager).

### 1.3 Attribution thay đổi mạnh trong 2026 — số liệu "tự nhiên giảm" không hẳn do hiệu quả giảm
- **[A/B]** **Incremental attribution**: Meta công bố 8/2024 (opt-in), mở rộng toàn cầu ~6/2025. Thay cửa sổ cố định bằng mô hình ML dự đoán conversion nào *sẽ không xảy ra nếu không có quảng cáo*, và cho phép tối ưu delivery theo conversion tăng thêm (incremental). Meta tuyên bố trong test: trung bình **+46% incremental conversions** so với attribution chuẩn (PPC Land dẫn số liệu Meta); tại earnings Q4 2025, CFO Susan Li nói incremental attribution đạt **+24% incremental conversions** so với standard. Vẫn là Meta tự đo hiệu quả của Meta. Hệ quả phụ: chọn incremental attribution thì **không sửa được attribution window** trên ad set đó nữa.
- **[A/B]** **Tháng 1/2026**: Meta loại bỏ cửa sổ **7-day view và 28-day view** khỏi Ads Insights API (giữ click và 1-day view). Số conversion báo cáo giảm một phần vì thay đổi này, không phải vì hiệu quả giảm.
- **[A/B]** **Tháng 3/2026**: click-through attribution chỉ còn tính **link click**. Tương tác khác (like, share, save, comment) chuyển sang nhóm mới **engage-through attribution** với cửa sổ 1 ngày. Conversion "click" báo cáo có thể giảm đột ngột sau mốc này trong khi tổng conversion (click + engage-through) gần như không đổi.
- Hệ quả cho việc đọc dữ liệu: so sánh CPA/ROAS xuyên các mốc 1/2026 và 3/2026 bằng cùng một định nghĩa là **so sánh sai**. Advisor dùng attribution 7d_click cố định thì ít nhất nhất quán nội bộ, nhưng phải hiểu conversion value trong dữ liệu đã là số "sau khi Meta siết định nghĩa".

### 1.4 Các thay đổi nền khác
- **[A/B]** **Opportunity Score** (0–100) ra mắt toàn cầu 6/2025: chấm mức độ áp dụng khuyến nghị của Meta; Meta nói test cho thấy cải thiện CPA **7–9%** khi áp dụng các khuyến nghị (số Meta tự báo cáo — [C] ở mức độ tin cậy, [A] ở việc tính năng tồn tại).
- **[A/B]** Tháng 1/2025: Meta **loại bỏ detailed targeting exclusions** ở ad set mới. Loại trừ nay chủ yếu qua custom audience.
- **[B]** **Value rules**: cho phép điều chỉnh bid theo segment (tuổi, giới tính, placement…) bên trong khung tự động hoá, thay dần các kiểm soát thủ công cũ. Có báo cáo 8/2026 về việc tuỳ chọn manual placements biến mất ở một số tài khoản và chỉ còn value rules (giảm bid tối đa 90%) — **chưa có thông báo chính thức**, Help Center vẫn mô tả manual placements là khả dụng [C cho phần "bị loại bỏ"].
- **[A]** Advantage+ **placements** là mặc định; Meta tự báo cáo placements tự động cho CPA thấp hơn trung bình ~11,7% (số self-reported, dẫn qua PPC Land) [C].
- **[A]** Daily budget: Meta có thể chi **vượt tối đa 75% ngân sách ngày** trong một ngày có cơ hội tốt, với trần tuần = 7 × ngân sách ngày (tài liệu Help của Meta, được Ryze dẫn lại). Advisor không được coi ngày chi vượt ngân sách là "lỗi".

---

## 2) Chiến thuật giảm CPA

Với mỗi chiến thuật: cơ chế — điều kiện áp dụng — rủi ro — nhãn nguồn — khả năng nhận diện từ aggregate 7 ngày cấp campaign.

### 2.1 Gộp campaign/ad set, chống phân mảnh (consolidation & audience fragmentation)
- **Cơ chế**: mỗi ad set cần khoảng **50 optimization events trong 7 ngày** để thoát learning phase [A — Help Center của Meta: "typically around 50 optimization events within 7 days"]. Ad set bị **learning limited** khi bị giới hạn bởi: audience quá nhỏ, ngân sách thấp, bid/cost control quá thấp, quá nhiều ads, hoặc auction overlap cao — phần lớn là tự gây ra do chia nhỏ [A]. Chia ngân sách cho nhiều ad set/campaign khiến không đơn vị nào đủ tín hiệu, CPA dao động và cao dai dẳng.
- **Áp dụng**: gộp các campaign/ad set cùng mục tiêu, cùng sự kiện tối ưu, cùng biên lợi nhuận thành ít đơn vị lớn; tách chỉ
...[truncated 15308 chars]