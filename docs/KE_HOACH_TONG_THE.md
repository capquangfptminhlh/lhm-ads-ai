# Kế hoạch tổng thể — LHM Ads AI: đăng ký bằng Gmail + PWA chạy như PC

> Bản dành cho **chủ sản phẩm**. Phần việc giao cho agent lập trình nằm trong `docs/AGENT_BRIEF_GMAIL_LICENSE.md` (gọi tắt là **Brief**); tài liệu này chỉ tham chiếu số mục của Brief, không lặp lại chi tiết kỹ thuật.
> Lập ngày 2026-10-25.

---

## 1. Mục tiêu

1. Khách **đăng ký và đăng nhập phần mềm bằng Gmail** (PWA và PC), **mua gói** rồi mới dùng được; admin kích hoạt gói **theo Gmail**; khách đăng nhập đúng Gmail trên máy nào cũng dùng được; **hết hạn là khoá cứng**.
2. **PWA chạy Ads tốt như bản PC** (bản PC đã chạy tốt toàn bộ và là chuẩn so sánh).

## 2. Hiện trạng (2026-10-25)

| Hạng mục | Tình trạng |
|---|---|
| Bản PC (EXE) | Chạy tốt toàn bộ, kể cả kết nối Google Ads |
| PWA | Có vỏ giao diện, kho mã hoá, đăng nhập Gmail (PR #46); **chưa gọi Google/Meta** |
| Đăng ký Gmail + gói | Khoảng 60% trong PR #46 (nháp, chưa merge, chưa deploy) |
| CI | PR #46 xanh. `main` đỏ ở smoke test kho → đã có PR #48 sửa. Cloudflare Workers Builds đỏ ở commit chỉ sửa tài liệu → lỗi phía Cloudflare, cần đọc log trong dashboard |
| Trình duyệt gọi thẳng Google Ads / Meta | **Được** — đã kiểm tra CORS từ `ads.lhmcrm.com` |
| Developer token Google Ads | Google đã bỏ từ 9/9/2026; quyền theo Google Cloud project |

## 3. Quyết định đã chốt

- Chỉ đăng nhập bằng Gmail, không mật khẩu, không key.
- Gói gán theo Gmail (nhận diện bằng Google ID, không phải chuỗi email).
- Số máy dùng cùng lúc theo gói: Cá nhân 2 máy, Team 5 máy (Team mở sau pilot). Đủ máy thì hỏi khách trước khi đá máy cũ.
- Hết hạn / thu hồi / bị khoá = **khoá cứng**; dữ liệu trên máy giữ nguyên, gia hạn xong mở lại.
- PC dùng offline tối đa 72 giờ, không vượt ngày hết gói.
- Thu tiền: chuyển khoản QR VietQR + admin duyệt một nút; PayOS để sau.
- Dữ liệu Ads chỉ nằm trên máy khách; PWA gọi thẳng Google/Meta, không qua Cloudflare.
- Hạ tầng GitHub + Cloudflare, không VPS. Repo public lúc xây dựng, **private trước khi phát hành**.
- Giá pilot gói Cá nhân theo bảng giá đã chốt (499.000đ/30 ngày; 6 và 12 tháng giảm 15% / 25%).
- Nhắc gia hạn đợt pilot: banner trong app + tab "Sắp hết hạn" trong admin để nhắn Zalo; email để sau.

## 4. Kiến trúc đích

```
                   ┌──────────── Cloudflare (ads.lhmcrm.com) ────────────┐
Khách ──Gmail──▶   │ Worker: đăng nhập Google, gói, seat, ghép nối PC,   │
                   │         lease ký số, API admin                      │
                   │ D1: khách, đơn, gói, seat, phiên, nhật ký            │
                   │ Access: bảo vệ /admin   ·  R2: file EXE + cập nhật   │
                   └─────────────────────────────────────────────────────┘
                        ▲ chỉ thông tin gói/phiên, KHÔNG dữ liệu Ads
        ┌───────────────┴───────────────┐
   PWA (trình duyệt)                 PC (EXE)
   kho mã hoá IndexedDB              SQLite mã hoá DPAPI
        │                                 │
        └──── gọi thẳng ────▶ Google Ads API · Meta Graph API ◀──── gọi thẳng
```

Hai việc dùng Google, tách riêng:

| | Đăng ký LHM | Kết nối Google Ads |
|---|---|---|
| Quyền | `openid email profile` | `adwords` |
| OAuth client | `LHM Login` (Web) | PC: Desktop (đang chạy) · PWA: `LHM Ads PWA` (Web) |
| Ai xử lý | Worker | Máy khách |

---

## 5. Lộ trình theo tuần

Hai luồng chạy song song: **Chủ sản phẩm (CSP)** và **Agent**. Ô "Cần trước" là việc phải xong thì việc đó mới bắt đầu được.

| Tuần | Chủ sản phẩm | Agent (Brief §8) | Mốc kiểm tra |
|---|---|---|---|
| **1** | A1–A3, B1–B4, D1, E1 (bắt đầu viết) | **GĐ 0**: CI xanh, sửa 401/402, staging | **M0**: `main` và PR #46 xanh; staging deploy được |
| **2** | A4–A5, B5–B6, F1 | **GĐ 1**: migration 0006, so khớp Gmail, API khách/admin, lease, cron | **M1**: trên staging, Gmail test đăng nhập → đặt gói → admin duyệt → mở khoá |
| **3** | E1 xong, A6 (gửi xác minh thương hiệu) | **GĐ 2**: PWA chọn gói / thanh toán QR / tài khoản / màn khoá · **GĐ 4**: trang admin | **M2**: luồng mua gói đầy đủ trên PWA staging, có QR thật |
| **4–5** | A7 (client Ads PWA), D2 | **GĐ 2B**: PWA chạy Ads như PC | **M3**: PWA và PC ra cùng số liệu trên tài khoản test |
| **5** | — | **GĐ 3**: PC đăng nhập Gmail, lease 72h, khoá cứng, Nuitka | **M4**: EXE commercial staging chạy Gmail end-to-end |
| **6** | G1, chạy nghiệm thu thiết bị thật (§7) | **GĐ 5–6**: công cụ chuyển khách pilot, tài liệu | **M5**: biên bản nghiệm thu ký |
| **7** | H1–H6 (phát hành) | Sửa lỗi từ nghiệm thu | **M6**: mở bán pilot |

Thời gian chờ Google (xác minh thương hiệu, mức truy cập API) và Meta (Business Verification, App Review) có thể kéo dài hơn lịch trên — đó là lý do phải nộp ngay tuần 1.

---

## 6. Việc của chủ sản phẩm — làm từng bước

### A. Google Cloud Console (dùng **cùng project** với bản PC)

- [ ] **A1. Kiểm tra mức truy cập Google Ads API** của project: Google Cloud Console → trang Google Ads API. Cần **Basic** trở lên để bán cho khách (Test chỉ chạy tài khoản test). Chưa có thì nộp đơn ngay.
- [ ] **A2. Branding** (Google Auth Platform → Branding): tên `LHM Ads AI`, email hỗ trợ, logo, trang chủ `https://ads.lhmcrm.com`, link Chính sách bảo mật và Điều khoản (điền khi E1 xong), authorized domain `lhmcrm.com`.
- [ ] **A3. Audience**: External, để **Testing**, thêm Gmail của bạn và 3–5 Gmail test.
- [ ] **A4. Tạo client `LHM Login`** (Clients → Create → Web application):
  - JavaScript origins: `https://ads.lhmcrm.com` (+ domain staging)
  - Redirect URIs: `https://ads.lhmcrm.com/api/auth/google/callback` (+ bản staging)
  - Data Access: `openid`, `email`, `profile`
  - Lưu Client ID/Secret để làm B5. **Không dán vào chat, không commit.**
- [ ] **A5. Xác minh domain** `lhmcrm.com` trong Google Search Console.
- [ ] **A6. Gửi xác minh thương hiệu** sau khi có trang Chính sách bảo mật/Điều khoản. Xong thì **Publish app** (bỏ giới hạn 100 Gmail test).
- [ ] **A7. Tạo client `LHM Ads PWA`** (Web application) cho GĐ 2B:
  - JavaScript origins: `https://ads.lhmcrm.com`
  - Redirect URI: `https://ads.lhmcrm.com/local/oauth/google`
  - Scope `adwords` dùng chung màn đồng ý với bản PC.

### B. Cloudflare

- [ ] **B1. Kiểm tra Workers Builds**: Worker `lhm-ads-cloudflare-api` → Settings → Builds → chỉ nhánh `main` được deploy production; nhánh khác chỉ preview. (Đang có dấu hiệu PR deploy thẳng — kiểm tra ngay.)
- [ ] **B2. Lên Workers Paid** (5 USD/tháng).
- [ ] **B3. Tạo D1 staging** và domain staging cho Worker (agent cấu hình `[env.staging]` trong GĐ 0).
- [ ] **B4. Sao lưu D1 production** trước mọi migration; bật D1 Time Travel.
- [ ] **B5. Đặt Worker Secrets** (staging trước, production sau):
  ```bash
  npx wrangler secret put GOOGLE_CLIENT_ID
  ```
  ```bash
  npx wrangler secret put GOOGLE_CLIENT_SECRET
  ```
  ```bash
  npx wrangler secret put LEASE_SIGNING_KEY
  ```
  (`LEASE_SIGNING_KEY` agent sẽ hướng dẫn cách tạo ở GĐ 1; khoá công khai tương ứng đưa vào GitHub Variables `LHM_LEASE_PUBLIC_KEY_B64`.)
- [ ] **B6. Biến thanh toán** (không phải secret): `BANK_BIN`, `BANK_ACCOUNT_NO`, `BANK_ACCOUNT_NAME`.
- [ ] **B7. R2** bucket + domain `download.lhmcrm.com` cho EXE và `lhm-update.json` (cần trước M4).
- [ ] **B8. Cloudflare Access** cho `/admin/*` và `/api/admin/*` đã đúng email admin (đã có; kiểm tra lại).

### C. GitHub

- [ ] **C1.** Thêm Variables cho build EXE: `LHM_LEASE_PUBLIC_KEY_B64`, URL cập nhật trên R2.
- [ ] **C2.** Trước phát hành: chuyển repo **private**, bật branch protection `main` (bắt buộc PR + CI xanh), kiểm tra quota phút Actions (runner Windows tính gấp đôi).

### D. Meta

- [ ] **D1. Business Verification** và **App Review** cho `ads_read` (và `ads_management` nếu cần tạm dừng/sửa ngân sách). Nộp ngay tuần 1.
- [ ] **D2. Cấu hình cho PWA** (trước GĐ 2B): App Domains `lhmcrm.com`; bật Client OAuth Login và Web OAuth Login; Valid OAuth Redirect URIs thêm `https://ads.lhmcrm.com/local/oauth/meta`.

### E. Pháp lý

- [ ] **E1.** Viết **Điều khoản dịch vụ**, **Chính sách bảo mật**, **Chính sách hoàn tiền**; đăng tại `https://ads.lhmcrm.com/dieu-khoan` và `/bao-mat` (agent dựng trang tĩnh, bạn cung cấp nội dung). Điều khoản nên có: cấm bẻ khoá và chia sẻ tài khoản, hết hạn thì khoá, dữ liệu Ads nằm trên máy khách.
- [ ] **E2.** Hoá đơn điện tử nếu bán cho doanh nghiệp (cần hợp đồng nhà cung cấp; code đang chờ sẵn).

### F. Thanh toán

- [ ] **F1.** Chọn tài khoản ngân hàng nhận tiền; quyết định nội dung chuyển khoản = mã đơn `LHMxxxxx`; thử quét QR VietQR trên staging (M2).

### G. Khách pilot cũ

- [ ] **G1.** Nhắn từng khách xin Gmail; điền file `customer_ref,gmail` cho công cụ của GĐ 5; chạy thử `--dry-run` rồi mới `--apply`.

### H. Phát hành (tuần 7)

- [ ] **H1.** Repo private (C2).
- [ ] **H2.** Áp migration lên D1 production (sau B4), đặt secret production, deploy production.
- [ ] **H3.** Build EXE commercial qua CI, ký Authenticode (nếu đã mua chứng thư), tải lên R2.
- [ ] **H4.** Google: Publish app (A6). Meta: app ở chế độ Live.
- [ ] **H5.** Chạy lại 5 bài kiểm tra quan trọng nhất (§7 mục 1, 2, 5, 6, 8) trên production bằng Gmail của bạn.
- [ ] **H6.** Mời 3–5 khách pilot; theo dõi tab Đơn chờ và Nhật ký mỗi ngày tuần đầu.

---

## 7. Nghiệm thu (bạn chạy, agent chuẩn bị)

Danh sách đầy đủ: Brief §9. Những bài **bắt buộc bạn tự chạy trên thiết bị thật**:

1. Gmail mới → đặt gói → bạn duyệt → máy khách mở khoá trong 15 giây (PWA và PC).
2. Cấp gói cho Gmail gõ khác dấu chấm/hoa thường → khách vẫn nhận đúng gói.
3. Gmail không được cấp → không vào được.
4. Hết hạn → khoá cứng đúng giờ, kể cả PC đang rút mạng.
5. Gói 2 máy: PC + điện thoại OK; máy thứ 3 hỏi xác nhận.
6. PC rút mạng 1 giờ vẫn dùng; quá 72 giờ bị khoá.
7. **PWA và PC cùng một tài khoản Ads thật, cùng khoảng ngày → cùng số liệu và khuyến nghị.**
8. Hai Gmail trên cùng máy không thấy dữ liệu của nhau.
9. Thiết bị: Android Chrome, iPhone Safari (PWA cài ra màn hình), Windows 10 và 11 sạch.

Ghi kết quả vào `docs/ACCEPTANCE.md` kèm ảnh chụp; mục nào chưa chạy giữ `NOT_RUN`.

---

## 8. Rủi ro và cách xử lý

| Rủi ro | Ảnh hưởng | Cách xử lý |
|---|---|---|
| Google/Meta duyệt chậm | Lùi ngày mở bán | Nộp tuần 1; pilot đầu chỉ với nền tảng đã duyệt |
| PWA lệch số liệu với PC | Khách mất tin | Bộ dữ liệu mẫu tạo từ Python + CI so Python/JS (Brief §7.4) |
| Sửa code làm hỏng bản PC đang chạy | Mất khách hiện có | Luật Brief §1.11: test hồi quy trước khi sửa; agent báo mọi thay đổi |
| Migration D1 lỗi trên production | Mất dữ liệu khách | Chạy staging trước; sao lưu + Time Travel (B4) |
| Một Gmail chia cho nhiều người | Thất thu | Giới hạn máy dùng cùng lúc; theo dõi bất thường |
| EXE bị bẻ khoá | Thất thu | Nuitka, kiểm tra nhiều chỗ, ký số; lớp 2 sau khi private (Brief §11) |
| Token PWA 1 giờ, phải làm mới | Khó chịu nhẹ | Tự làm mới bằng chuyển trang; nếu khách phàn nàn mới xét refresh token qua Worker (phải nới chính sách) |
| Vượt quota Cloudflare | Gián đoạn | Workers Paid; heartbeat 5 phút |

## 9. Chi phí vận hành dự kiến

| Khoản | Mức |
|---|---|
| Cloudflare Workers Paid | 5 USD/tháng (đã gồm D1/R2 ở mức nhỏ) |
| Google Cloud (OAuth, Ads API) | 0đ |
| Meta App | 0đ |
| GitHub private | 0đ với gói Free nếu đủ phút Actions; thiếu thì mua thêm phút |
| Chứng thư ký số EXE | Tuỳ nhà cung cấp, trả theo năm — mua khi bán rộng |
| Email nhắc gia hạn (sau pilot) | Gói miễn phí của nhà cung cấp email là đủ lúc đầu |

## 10. Câu hỏi còn mở

1. Giá gói Team (5 máy) khi mở sau pilot.
2. Có cần PWA giữ đăng nhập Google Ads lâu hơn 1 giờ không (nếu có: phải nới chính sách để Worker trung chuyển token).
3. Thời điểm mua chứng thư ký số EXE.
