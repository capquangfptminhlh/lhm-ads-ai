# Nhật ký thay đổi — LHM Ads AI

Định dạng theo [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
phiên bản theo [Semantic Versioning](https://semver.org/lang/vi/).

**Phiên bản đang khai báo trong mã nguồn: 0.3** — "Private Studio 0.3"
(trang đầu `README.md` và `docs/STUDIO.md`). Nguồn phiên bản duy nhất nay
là `ads_core/version.py` (`__version__ = "0.3.0"`); chưa có git tag. Mọi
ghi chú dưới đây thuộc mục *Chưa phát hành* cho đến khi chủ phần mềm
quyết định số phiên bản kế tiếp (xem `docs/RELEASE_CHECKLIST.md`).

## [Chưa phát hành]

Các thay đổi đã hợp nhất vào `main` ngày 2026-10-21 và 2026-10-22, chuẩn
bị cho bản thương mại đầu tiên. **Toàn bộ các mục dưới đây mới chỉ nằm
trên `main`: chưa có git tag phát hành, chưa nằm trong bản EXE đã ký gửi
khách** — không được hiểu là đã phát hành. Trạng thái nghiệm thu trực
tiếp (live acceptance): **Google Ads — NOT_RUN; Meta Ads — NOT_RUN**
(chưa chạy với tài khoản thật; xem `docs/ACCEPTANCE.md`).

### Đã thêm

- **Xác thực hai lớp TOTP (MFA) tùy chọn cho từng người dùng** (PR #6):
  khóa bí mật được mã hóa AES-GCM; tắt MFA bắt buộc nhập lại mật khẩu kèm
  mã hợp lệ; màn hình đăng nhập Studio có ô nhập mã MFA.
- **Nhắc gia hạn cho bên bán** (PR #6): lệnh `vendor_ledger.py remind`
  liệt kê bản quyền đã hết hạn/sắp hết hạn, tùy chọn gửi một tin Telegram
  về chat của chính người bán.
- **Tích hợp PayOS ở trạng thái chờ (dormant)** (PR #7): `tools/payos.py`
  (ký HMAC-SHA256, kiểm chứng webhook), lệnh sổ bán hàng `payos-status`,
  `payos-create`, `payments` và máy chủ webhook `tools/payos_webhook_server.py`.
  Chưa có khóa merchant thì không tạo được gì; webhook chỉ đánh dấu *đã
  thanh toán*, **không bao giờ tự cấp bản quyền** — quy trình mặc định vẫn
  là khách chuyển khoản vào tài khoản của chủ phần mềm, chủ xác nhận nhận
  tiền rồi mới kích hoạt. Hướng dẫn: `docs/PAYOS.md`.
- **Font Inter đóng gói kèm phần mềm** (PR #9): font biến đổi (độ đậm
  100–900; subset Latin, Latin mở rộng và tiếng Việt) nhúng trong
  `static/fonts.css`, giấy phép SIL OFL tại `static/fonts/LICENSE-Inter.txt`.
  Trước đây máy Windows không có sẵn Inter nên giao diện lặng lẽ rơi về
  Segoe UI, mỗi máy hiển thị một khác.
- **Hiệu ứng chuyển động cho trang đăng nhập và các panel** (PR #9):
  màn hình đăng nhập xuất hiện mềm theo nhịp; mọi panel trong các trang
  làm việc dùng hiệu ứng vào `fp-card-arrive`; tôn trọng chế độ giảm
  chuyển động của hệ điều hành.
- **"LHM Vòng lặp Tối ưu" (LHM Optimization Loop)** (PR #14):
  `ads_core/optimization_playbook.py` — 13 quy tắc tối ưu quảng cáo theo
  chuẩn 2026 dạng dữ liệu (mỗi quy tắc có điều kiện, lý do, các bước xử lý
  và rào chắn an toàn), nối vào bộ tư vấn. Lớp độc quyền nằm ở cơ chế chạy
  trên dữ liệu của chính khách:
  - *Hồ sơ nền riêng từng tài khoản*: hệ thống lưu các kỳ quét gần nhất
    của mỗi tài khoản và phát hiện chiến dịch lệch khỏi CPA/ROAS trung vị
    của chính nó.
  - *Vòng kiểm chứng kết quả*: phát hiện từ 7 ngày trở lên được đối chiếu
    với kỳ đo mới nhất và nhận phán quyết (cải thiện / xấu đi / không đổi /
    chưa đủ dữ liệu; dải nhiễu ±5%). Phán quyết chỉ đo biến động của chỉ
    số, **không khẳng định quan hệ nhân quả**.
  - *Chống tự mâu thuẫn*: khuyến nghị mở rộng bị chặn khi cùng chiến dịch
    đang có cảnh báo cắt/giảm; các mã bị chặn được ghi lại.
  - Tài liệu: `docs/OPTIMIZATION_SKILL.md` và hai bản nghiên cứu nền tảng
    2026 trong `docs/research/` (mọi khẳng định đều ghi mức nguồn).
- **Adapter đọc thêm cấu hình đấu thầu thật từ nền tảng** (PR #15):
  Google Ads (GAQL): loại chiến lược giá thầu, target tCPA/tROAS thật,
  ngân sách chiến dịch (chỉ tính là ngân sách ngày khi chu kỳ là `DAILY`).
  Meta: chiến lược giá thầu và ngân sách ngày/trọn đời ở cấp chiến dịch
  (quy đổi từ đơn vị tiền nhỏ nhất). Target ở cấp nhóm quảng cáo (ad set)
  của Meta **chưa** được đọc — không suy ra, không điền thay.
- **Sprint hoàn thiện 20 luồng (PR #16)**: playbook 16 → 19 quy tắc
  (`budget_constrained_winner` từ tỉ lệ mất hiển thị vì ngân sách của
  Google; `adset_target_missed` từ trung vị bid_amount các ad set Meta —
  xấp xỉ có ghi rõ; `audience_fatigue_risk` từ tần suất hiển thị Meta);
  adapter Meta đọc thêm ad set + tần suất/reach, Google đọc thêm chỉ số
  mất hiển thị vì ngân sách. Kèm theo: sửa 5 lỗi thật trong playbook do
  test độ bền phát hiện (sập khi dữ liệu rác, bịa cảnh báo từ chỉ số âm);
  vá lỗ hổng backup không mang theo danh sách thu hồi giấy phép (khôi
  phục có thể âm thầm hủy thu hồi); giới hạn số lần thử cho token thiết
  lập lần đầu trên desktop; pin UTF-8 cho CLI tạo admin và launcher
  Windows (lỗi crash sau khi đã ghi thành công trên codepage cũ); lệnh
  xuất hóa đơn điện tử `einvoice-issue` (vẫn dormant cho tới khi có hợp
  đồng nhà cung cấp); CLI `tools/update_check.py` cho bộ kiểm tra cập
  nhật ký số (dormant); digest đếm cảnh báo theo mức trong giám sát nền;
  nguồn phiên bản duy nhất `ads_core/version.py`; giao diện hiển thị cấu
  hình đấu thầu cạnh mỗi chiến dịch.

### Đã thay đổi

- **Playbook tối ưu từ 13 lên 16 quy tắc** (PR #15): nhờ các trường đấu
  thầu adapter mới đọc về, thêm ba quy tắc phát hiện tự động —
  `platform_target_missed` (CPA/ROAS thực tế lệch xa target thật đang đặt
  trên nền tảng; chạy được cả khi tổ chức chưa đặt mục tiêu trong phần
  mềm), `platform_target_headroom` (dư địa mở rộng so với target nền
  tảng), và `manual_bidding_at_scale` (vẫn đấu thầu thủ công/bid cap
  nhưng đã ≥ 30 chuyển đổi/7 ngày — gợi ý thử nghiệm Smart Bidding có đối
  chứng). Ba quy tắc này tham gia đầy đủ cơ chế chống mâu thuẫn và vòng
  kiểm chứng kết quả của PR #14.
- **Bảng giá pilot đã chốt trong bộ tài liệu bán hàng** (PR #13, chốt
  2026-10-22): điền giá vào `docs/sales/BANG-GIA-MAU.md` — Pilot
  499.000đ/30 ngày/1 máy; 180 ngày 2.545.000đ (−15%); 12 tháng
  4.491.000đ (−25%), trả trước toàn bộ; giá niêm yết chính thức sau pilot
  799.000đ/30 ngày; gói Agency báo giá 1.500.000–2.500.000đ/máy/tháng theo
  số máy. Kèm ghi chú tham chiếu giá pilot trong mẫu tin nhắn 1 của
  `docs/sales/MAU-TIN-NHAN.md`. Đây là thay đổi tài liệu bán hàng, không
  thay đổi tính năng phần mềm; các quyết định còn mở (thông tin chuyển
  khoản, chính sách hoàn tiền/chuyển máy, kênh và giờ hỗ trợ, dùng thử
  miễn phí) vẫn để trống chờ chủ phần mềm.
- **Giới hạn đăng nhập bền vững trong SQLite** (PR #6): 5 lần sai theo
  email, 20 lần theo IP trong 15 phút — thay cho bộ đếm trong bộ nhớ của
  từng tiến trình (khởi động lại là mất).
- **Tổng hợp dữ liệu gửi OpenRouter đầy đủ hơn** (PR #5): payload nay gồm
  chuyển đổi, giá trị chuyển đổi, CPA và ROAS, chỉ tính từ các nhóm dữ
  liệu đầy đủ; thiếu dữ liệu thì ghi *chưa rõ*, không điền 0.
- **Cảnh báo giám sát và tư vấn tới được người vận hành** (PR #5): ngoài
  hiển thị trong app, cảnh báo lỗi nhà cung cấp và phát hiện mới của bộ
  tư vấn được gửi thêm tới Telegram của người vận hành (gộp theo nhịp
  chống spam; chỉ gửi mã lỗi và số tài khoản nội bộ).

### Đã sửa

- **Tài liệu mô tả sai khả năng thực tế** (PR #5): bảng nhà cung cấp trong
  README (Google Ads có thao tác tạm dừng/ngân sách qua phê duyệt, không
  phải "chỉ đọc"), mâu thuẫn về AI bên ngoài, và mục 0 của đặc tả 24/7 đã
  viết lại đúng với code hiện tại — giám sát là tác nhân nền trên máy
  khách, chỉ đọc, và mọi thay đổi quảng cáo đều cần người phê duyệt.
- **Sáu lỗi giao diện từ đợt rà soát bằng ảnh chụp** (PR #8):
  - Nguyên nhân gốc: CSP `style-src 'self'` của chính app chặn các style
    nội tuyến do JS tự phát ra — toàn bộ đã chuyển sang class CSS, trang
    Bản quyền hết vỡ bố cục, nhãn và ô dán giấy phép xếp dọc đầy đủ.
  - Trang Bản quyền không còn in lỗi đỏ "Cần đăng nhập tài khoản nội bộ"
    cho người đã đăng nhập.
  - Ô tích chọn đồng ý OpenRouter gắn liền với nhãn của nó.
  - Ô chọn tài khoản ở trang Chiến dịch có trạng thái trống rõ ràng, khóa
    nút phân tích và hướng dẫn nơi kết nối tài khoản trước.
  - Hai nhãn trạng thái trùng nhau ở Tổng quan đã gộp/tách nghĩa rõ ràng.
  - Bỏ vệt mờ cam ở góc thẻ KPI; logo đăng nhập bản mobile về đúng màu
    cam thương hiệu.

### Bảo mật

- MFA TOTP và giới hạn đăng nhập bền vững (xem trên) thu hẹp hai khoảng
  trống đã ghi nhận trong đợt kiểm toán bảo mật 2026-10-21.
- CSP chỉ nới đúng một điểm cho font đóng gói: `font-src 'self' data:`.

## [0.3]

Bản "Private Studio 0.3" đang khai báo trong `README.md`/`docs/STUDIO.md`:
dashboard phân tích chỉ đọc cho Meta/Google Ads, tạm dừng chiến dịch qua
phê duyệt quản trị, phân tích nội bộ tại máy (tùy chọn OpenRouter khi
quản trị bật), bản quyền ngoại tuyến ký Ed25519 theo máy, sổ bán hàng
ngoại tuyến cho bên bán. MCP đã bị loại bỏ hoàn toàn từ trước bản này vì
lý do bảo mật (các route `/mcp` trả 404 và có test khóa).
