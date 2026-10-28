# AGENT BRIEF — Đăng nhập Gmail + gói theo Gmail cho PWA và EXE PC

> Tài liệu giao việc cho agent lập trình. Đọc hết trước khi sửa code.
> Lịch tổng thể, việc của chủ sản phẩm và các mốc kiểm tra: `docs/KE_HOACH_TONG_THE.md`. Việc của agent bị chặn bởi việc của chủ sản phẩm (secret, client OAuth, cấu hình Meta) → làm phần không bị chặn trước, ghi rõ trong báo cáo đang chờ gì.
> Repo: `capquangfptminhlh/lhm-ads-ai` · Viết ngày 2026-10-25 · Nền: PR #46 (`feature/google-seat-subscription-20261025`, commit `9eadba5`) và issue #47.

---

## Trạng thái thực hiện (cập nhật 2026-10-25)

| GĐ | Trạng thái | Ghi chú |
|---|---|---|
| 0 | Xong (trừ staging) | `main` xanh (PR #48), PR #46 xanh, 401→402 đúng. `[env.staging]` **chưa làm**: cần D1 staging do chủ sản phẩm tạo. |
| 1 | Xong | Migration 0006, so khớp Gmail §4.2, API khách/admin, cron. Lease ký số trả **trong phản hồi `/api/auth/seat`** của PC (không tách `/api/auth/lease`) để lease luôn gắn với seat vừa xác nhận. |
| 2 | Xong | Chọn gói, QR VietQR, chờ kích hoạt, giới hạn máy + "Dùng trên máy này", banner, khóa cứng. |
| 2B | Xong (Google + Meta) | Khác brief: **giữ Python làm nguồn chuẩn**, không tách `shared/rules/playbook.json`; thay vào đó `tools/gen_core_fixtures.py` sinh 1.145 ca từ chính code Python và CI bắt JS khớp từng byte. Cùng mục đích chống lệch, không đụng code PC đang chạy. |
| 3 | Xong, **trừ Nuitka** | Lease 72h, chống lùi giờ, khóa cứng mọi cổng tính năng (advisor/autopilot/monitoring/OpenRouter/MCP), takeover, giao diện. Build Nuitka **chưa làm**: cần thử trên runner Windows với pywebview/pythonnet. |
| 4 | Xong | Trang admin mới (6 tab) + nhập hàng loạt khách pilot. |
| 5 | Xong | Khác brief: công cụ xuất CSV, admin dán vào trang (dùng phiên Access của admin) thay vì script tự gọi API (cần service token Access). |
| 6 | Xong (khung pháp lý) | `/dieu-khoan`, `/bao-mat` là bản nháp có ô [CẦN ĐIỀN]; tài liệu, FAQ, ACCEPTANCE §E cập nhật. |

Còn mở: staging, Nuitka, nội dung pháp lý, mọi mục nghiệm thu thật (ACCEPTANCE §E = NOT_RUN).

---

## 0. Mục tiêu một câu

Khách **đăng nhập bằng Gmail** (trên PWA hoặc EXE PC) → **chọn và mua gói** → admin **xác nhận tiền và kích hoạt gói cho đúng Gmail đó** → khách đăng nhập **đúng Gmail ấy trên bất kỳ máy nào** là dùng được, trong giới hạn số máy của gói. Không có mật khẩu riêng, khách không bao giờ phải gõ key.

### Hai mục tiêu của đợt này
1. **Đăng ký / đăng nhập phần mềm bằng Gmail** + mua gói (PWA và PC) — §3–§8.
2. **PWA chạy Ads tốt như bản PC.** Bản PC đã chạy tốt toàn bộ (chủ sản phẩm xác nhận 2026-10-25) và là **chuẩn tham chiếu**; PWA hiện chỉ có vỏ giao diện, chưa gọi Google/Meta — §7.4.

### Quyết định chủ sản phẩm đã chốt
- Đăng nhập **chỉ bằng Gmail** trên cả PWA và EXE PC; không giữ đăng nhập email + mật khẩu.
- **PWA gọi thẳng Google Ads API và Meta Graph API từ trình duyệt**, không qua Cloudflare (đã kiểm tra CORS 2026-10-25: `googleads.googleapis.com`, `oauth2.googleapis.com` trả `Access-Control-Allow-Origin: https://ads.lhmcrm.com`; `graph.facebook.com` trả `*`). Giữ nguyên chính sách device-only.
- Gói gán theo Gmail; khách đăng nhập đúng Gmail trên máy nào cũng dùng được (trong giới hạn số máy của gói).
- **Hết hạn / thu hồi / bị khoá = KHOÁ CỨNG** (§3.5), không có chế độ chỉ xem.
- Hạ tầng giữ **GitHub + Cloudflare** (Worker, D1, Access, R2), không VPS.
- Repo **public trong lúc xây dựng**, **chuyển private trước khi phát hành** (§10).
- Thu tiền: chuyển khoản QR VietQR + admin duyệt; PayOS để sau.

---

## 1. Luật cứng — KHÔNG được vi phạm

1. **Device-only Ads data.** Không gửi, lưu, log token Google Ads/Meta, ID tài khoản Ads, báo cáo, campaign lên Cloudflare (Worker, D1, KV, R2, logs, analytics). Xem `docs/DEVICE_ONLY_ADS_DATA.md`. D1 chỉ chứa: khách (Google sub, email, tên), đơn, gói, seat (hash), phiên, nhật ký admin.
2. **Danh tính = Google `sub`.** Email chỉ dùng để *gặp nhau lần đầu*. Sau khi gắn `sub`, mọi tra cứu theo `sub`.
3. **Không nạp script bên thứ ba vào PWA.** Giữ CSP `script-src 'self'` (bảo vệ kho mã hoá). Không dùng Google One Tap / GIS JS. Giữ luồng redirect OAuth hiện có.
4. **PC không đăng nhập Google trong WebView2.** Luôn mở **trình duyệt hệ thống** + mã ghép nối 6 số (issue #47).
5. **Secret không vào git / EXE / frontend.** `GOOGLE_CLIENT_SECRET`, khoá ký lease → Cloudflare Worker Secrets. Khoá ký license/update cũ → chỉ ở máy chủ sản phẩm.
6. **Không tự kích hoạt gói khi chưa có xác nhận tiền** (admin bấm, hoặc webhook PayOS đã xác minh chữ ký — PayOS để sau).
7. **Không đánh dấu PASS/production-ready** cho phần cần nghiệm thu thật (OAuth thật, máy Windows thật, điện thoại thật, Ads thật). Ghi `NOT_RUN` đúng sự thật.
8. **Không xoá test để CI xanh.** Sửa code hoặc sửa test có lý do ghi trong commit.
9. **Không deploy production.** Chỉ deploy **staging**. Production do chủ sản phẩm quyết.
10. **Hết hạn / thu hồi / bị khoá = KHOÁ CỨNG**, chặn ở backend theo allowlist (§3.5). Không có chế độ "chỉ xem", không có ngoại lệ ân hạn sau ngày hết gói.
11. **Không phá luồng kết nối Google Ads trên PC đang chạy tốt** (chủ sản phẩm xác nhận ngày 2026-10-25). Trước khi sửa `ads_core/oauth_connect.py`, `providers.py` hay luồng OAuth trên PC: viết test hồi quy giữ hành vi hiện tại; mọi thay đổi luồng này phải nêu rõ trong báo cáo. Việc chuyển `docs/ACCEPTANCE.md` từ `NOT_RUN` sang `PASS` do chủ sản phẩm ghi kèm bằng chứng, agent không tự đổi.
12. **Không sửa tay binding D1 trong `wrangler.toml`** — binding production do `tools/persist_commerce_binding.py` / workflow `deploy-commerce.yml` quản lý.

---

## 2. Cấu hình mặc định (để dạng cấu hình, chủ sản phẩm có thể đổi)

| Khoá | Mặc định | Ở đâu |
|---|---|---|
| Gói | `personal`: 2 máy đồng thời · `team`: 5 máy đồng thời | bảng D1 `plans` |
| Kỳ hạn bán | 1, 6, 12 tháng | bảng D1 `plans` |
| Giá | Lấy từ `docs/sales/BANG-GIA-MAU.md` cho `personal` (499.000đ/30 ngày pilot); `team` = tắt (báo giá riêng) | bảng D1 `plans`, admin sửa được |
| Heartbeat | 300 giây | hằng số Worker + client |
| Seat TTL | 600 giây | hằng số Worker |
| PC offline grace | 72 giờ (lease ký số) | env `LEASE_GRACE_HOURS` |
| Đơn chờ tự huỷ | 48 giờ | env `ORDER_PENDING_HOURS` |
| Khi đủ máy | **Hỏi khách xác nhận** rồi mới đá máy cũ nhất (KHÔNG tự đá) | logic |
| Khi hết hạn | **KHOÁ CỨNG** — chủ sản phẩm đã chốt, không phải cấu hình. Xem §3.5 | logic |

---

## 3. Luồng nghiệp vụ đích

### 3.1 Khách — PWA
1. `ads.lhmcrm.com` → nút **Đăng nhập bằng Google** → Google → callback → phiên LHM (cookie HttpOnly 7 ngày).
2. Chưa có gói → màn **Chọn gói** (giá từ server).
3. Chọn → tạo đơn `pending` với `payment_code` (vd `LHM7K3Q9`) → màn **Thanh toán**: QR VietQR, số tiền, nội dung CK = `payment_code`, trạng thái "Đang chờ xác nhận", tự gọi `/api/auth/session` mỗi 15 giây.
4. Admin kích hoạt → client tự chuyển sang app (không cần tải lại).
5. Máy mới cùng Gmail → vào được ngay; hiện hướng dẫn "Dữ liệu Ads nằm trên từng máy — kết nối lại hoặc khôi phục file sao lưu".

### 3.2 Khách — EXE PC
1. Lần đầu: một nút **Đăng nhập bằng Google** → PC gọi `/api/desktop/pair/start` → mở trình duyệt hệ thống tới `/desktop/pair/?id=…`, PC hiện mã 6 số.
2. Trình duyệt: đăng nhập Gmail → nếu chưa có gói thì đi tiếp màn Chọn gói / Thanh toán như PWA → khi có gói: trang xác nhận "Cho phép máy này" (đối chiếu mã 6 số).
3. PC poll `/api/desktop/pair/claim` → nhận token (DPAPI, 30 ngày) → xin seat + lease ký số → vào app.
4. Lần sau mở app vào thẳng; heartbeat 300 giây; mất mạng vẫn dùng tới hết lease (≤ 72 giờ, không quá ngày hết gói).

### 3.3 Admin
- **Cách A (chuẩn):** tab **Đơn chờ** → thấy `payment_code`, số tiền, Gmail ✓ đã xác minh → đối chiếu ngân hàng → nút **Duyệt & kích hoạt** (một thao tác: ghi mã giao dịch → paid → cấp mới hoặc gia hạn → nhật ký).
- **Cách B (ngoại lệ):** **Cấp gói theo Gmail**: nhập Gmail, gói, số tháng/số ngày, mã giao dịch, ghi chú. Gmail chưa từng đăng nhập → cảnh báo + bắt nhập lại lần 2.

### 3.4 Bảng trạng thái (phải nhất quán PWA / PC / API)

| Trạng thái | Mã API | PWA / PC hiển thị | API Ads trên máy |
|---|---|---|---|
| Chưa đăng nhập | 401 `SIGNIN_REQUIRED` | Màn đăng nhập | khoá |
| Chưa có gói | 402 `SUBSCRIPTION_REQUIRED` | Chọn gói | khoá |
| Chờ thanh toán | 402 `PAYMENT_PENDING` | QR + chờ | khoá |
| Đang dùng | 200 | App + hạn dùng góc màn hình | mở |
| ≤ 7 ngày | 200 + `expiring_soon` | Banner + nút Gia hạn | mở |
| Hết hạn | 402 `SUBSCRIPTION_EXPIRED` | Màn khoá "Gói đã hết hạn" + Gia hạn | **khoá toàn bộ** (§3.5) |
| Đủ máy | 409 `SEAT_LIMIT` | "Dùng trên máy này? Máy *X* sẽ bị đăng xuất" | khoá tới khi xác nhận |
| Bị máy khác chiếm | 409 `SEAT_REPLACED` | "Gmail đang dùng trên máy khác" + nút Dùng trên máy này | khoá |
| PC offline trong grace | — | Banner "Offline — dùng được đến …" | mở |
| Bị khoá / thu hồi | 403 `ACCOUNT_BLOCKED` / `LICENSE_REVOKED` | "Liên hệ hỗ trợ" | khoá |

**Thứ tự kiểm tra bắt buộc:** chưa đăng nhập (401) **trước**, rồi mới tới gói (402). Thứ tự này đã được sửa trên PR #46 (CI xanh ở commit `9eadba5`); mọi thay đổi sau phải giữ nguyên.

### 3.5 Hết hạn = KHOÁ CỨNG (đã chốt)

Gói hết hạn, bị thu hồi hoặc tài khoản bị khoá → khách **không dùng được bất cứ tính năng nào**, chỉ còn đường để gia hạn.

**Còn dùng được — allowlist duy nhất, ngoài danh sách này là chặn:**
- Màn khoá: ảnh + Gmail, ngày hết hạn, nút **Gia hạn** → Chọn gói → Thanh toán QR → trạng thái đơn.
- Đăng xuất, Đổi Gmail.
- (PC) Kiểm tra và cài bản cập nhật; thông tin phiên bản và liên hệ hỗ trợ.

**Bị chặn, không ngoại lệ:** Dashboard, xem báo cáo và dữ liệu cũ, xuất CSV, xuất file sao lưu, kết nối/thêm/xoá tài khoản Ads, mọi lời gọi Ads API, kế hoạch và duyệt thay đổi, autopilot, bộ thu thập nền, cảnh báo và Web Push, AI/OpenRouter, MCP stdio.

**Cách thực thi — phải chặn ở backend, không chỉ ẩn nút:**
- **PC:** middleware `require_online_subscription` chuyển sang kiểu **mặc định chặn**: mọi `/api/*` trả 402 `SUBSCRIPTION_EXPIRED`, chỉ cho qua allowlist (`/api/cloud-license/*`, health, kiểm tra cập nhật, đăng xuất). Thread bộ thu thập nền, monitoring và MCP stdio tự kiểm tra trạng thái mỗi chu kỳ và **dừng** khi hết hạn. Test: gọi từng route nhạy cảm khi hết hạn đều phải nhận 402.
- **PC offline:** `valid_until` của lease không bao giờ vượt ngày hết gói, nên dù offline vẫn khoá đúng giờ hết hạn; chống lùi đồng hồ theo §6.3.
- **PWA:** khi `/api/auth/session` báo hết hạn hoặc không xác minh được phiên → không mở kho mã hoá, chỉ render màn khoá. Service worker không trả trang app từ cache cho phiên hết hạn. Giới hạn thật: khoá trên PWA là khoá ở tầng ứng dụng; người rành kỹ thuật can thiệp JS trên chính máy họ thì chỉ đọc được dữ liệu của chính họ — chấp nhận và ghi vào tài liệu, không quảng cáo là "không thể vượt qua".
- **Không xoá dữ liệu:** dữ liệu Ads đã mã hoá giữ nguyên trên máy. Gia hạn xong mở lại đầy đủ như cũ. Khách tự bấm "Xoá dữ liệu trên máy này" thì vẫn cho (trong màn khoá, có xác nhận) — đây là quyền của khách với dữ liệu của họ.
- **Báo trước:** banner từ 7 ngày; nhắc nổi bật ở 3 ngày và 1 ngày; ngày cuối hiện giờ khoá chính xác ("Khoá lúc 14:30 hôm nay").

---

## 4. So khớp Gmail ↔ khách (chống nhầm khách)

### 4.1 Chuẩn hoá email → `email_key`
```
normalize(email):
  e = trim(lowercase(email))
  local, domain = split(e, '@')
  if domain in ('gmail.com', 'googlemail.com'):
      local = local.split('+')[0].replace('.', '')
      domain = 'gmail.com'
  return local + '@' + domain
```
Viết **một** hàm dùng chung cho Worker (JS). Có unit test cho: hoa/thường, dấu chấm, `+tag`, `googlemail.com`, domain khác giữ nguyên dấu chấm.

### 4.2 Thuật toán khi callback Google (thay logic hiện tại trong `workers/ads-api/src/google-subscription.js`)
```
claims đã xác minh: sub, email (email_verified = true), name, picture
key = normalize(email)

1. c = customers WHERE google_sub = sub
   → có: nếu c.status = 'blocked' → 403 ACCOUNT_BLOCKED
         cập nhật email hiển thị, name; tạo phiên. XONG.
2. c = customers WHERE email_key = key AND google_sub IS NULL
   → có: UPDATE … SET google_sub = sub WHERE id = c.id AND google_sub IS NULL (điều kiện chống race)
         audit 'google_linked'; tạo phiên. XONG.
3. c = customers WHERE email_key = key AND google_sub <> sub
   → 403 GOOGLE_ACCOUNT_MISMATCH: "Gmail này đã gắn với tài khoản Google khác, liên hệ hỗ trợ".
4. Không có → INSERT khách mới (google_sub = sub, email_key = key), chưa có gói.
```
Lỗi hiện tại phải hết: tra theo email trước khiến khách đổi email bị 503 do trùng `google_sub`.

### 4.3 Công cụ sửa nhầm cho admin
- **Gỡ liên kết Google** (`google_sub = NULL`, xoá mọi phiên/seat/desktop session) — bắt buộc nhập lý do, ghi nhật ký.
- **Chuyển gói sang Gmail khác** — giữ nguyên ngày hết hạn và số máy, đá mọi seat cũ, ghi nhật ký.

---

## 5. Thay đổi dữ liệu — `migrations/0006_gmail_entitlements.sql`

Một migration, chạy được trên DB đã có 0001–0005, có backfill. Viết test migration kiểu `tests/test_google_seats_migration.py`.

- `customers`: thêm `email_key TEXT` (backfill bằng chuẩn hoá trong SQL cho trường hợp đơn giản; script backfill JS/Python cho gmail), `UNIQUE INDEX` trên `email_key`; thêm `picture_url TEXT`, `updated_at`. Dùng cột `status` có sẵn (`active` / `blocked`).
- `plans` mới: `code`, `name`, `seat_limit`, `months`, `price_vnd`, `active`, `sort`. Seed theo mục 2.
- `orders`: thêm `plan_code`, `payment_code TEXT UNIQUE`, `expires_at` (đơn chờ), `source` (`self_service` / `admin_grant` / `pilot_migration`).
- `licenses`: **mỗi khách tối đa 1 license `active`** (partial unique index `WHERE status='active'`). `key_hash` giữ để tương thích nhưng sinh ngẫu nhiên nội bộ, **không hiển thị, không trả về**. Thêm `plan_code`.
- `license_seats`: thêm `platform` (`pwa` / `windows`), `device_label` (chung chung: "Windows PC", "Chrome Android", "Safari iPhone" — không lưu fingerprint), `first_seen_at`.
- `customer_notes` mới: `id`, `customer_id`, `actor`, `note`, `at`.
- `payment_code`: 8 ký tự, bảng chữ không gây nhầm (bỏ `0 O 1 I L`), tiền tố `LHM`.

---

## 6. API Worker (`workers/ads-api/src`)

### 6.1 Khách (`google-subscription.js`)
| Endpoint | Việc |
|---|---|
| `GET /api/auth/google/start`, `/callback` | Giữ PKCE/state/nonce; thay logic so khớp theo §4.2 |
| `GET /api/auth/session` | `{authenticated, email, name, picture, plan:{code,name,seat_limit,expires_at,expiring_soon}, pending_order, seats:{occupied,limit}}` |
| `GET /api/auth/plans` | Đọc bảng `plans` (chỉ `active`) |
| `POST /api/auth/plan` | Tạo đơn; trả `payment_code`, số tiền, thông tin ngân hàng, URL ảnh VietQR |
| `POST /api/auth/order/cancel` | Khách huỷ đơn chờ của mình |
| `POST /api/auth/seat` | `mode: attach / heartbeat / takeover`. Đủ máy + `attach` → 409 `SEAT_LIMIT` kèm danh sách máy đang dùng; chỉ `takeover` mới đá máy cũ nhất |
| `GET /api/auth/devices`, `POST /api/auth/devices/signout-all` | Khách xem máy và đăng xuất mọi máy |
| `POST /api/auth/lease` | (PC) trả lease ký Ed25519 — §6.3 |

Thông tin ngân hàng: env `BANK_BIN`, `BANK_ACCOUNT_NO`, `BANK_ACCOUNT_NAME` (không phải secret). QR: link ảnh VietQR theo chuẩn công khai, `amount` + `addInfo=payment_code`. Thiếu env → API trả 503 rõ ràng, UI hiện "Chưa cấu hình thanh toán".

### 6.2 Admin (`admin.js`, bảo vệ bởi Cloudflare Access như hiện tại)
| Endpoint | Việc |
|---|---|
| `GET /api/admin/orders?status=pending` | Đơn chờ kèm Gmail, ✓ đã xác minh (có `google_sub`), `payment_code`, số tiền |
| `POST /api/admin/orders/activate` | `{order_id, reference}` → một `db.batch`: payment_review + paid + issue/renew + fulfillment + audit. Idempotent theo `order_id` |
| `POST /api/admin/grant` | `{email, plan_code, months? , days?, reference, note, confirm_email}` → `confirm_email` phải bằng `email`; upsert khách theo `email_key`; tạo đơn `source=admin_grant` đã paid; issue/renew; audit. Trả `linked: true/false` |
| `GET /api/admin/customers?q=&cursor=` | Tìm theo email/tên, phân trang |
| `GET /api/admin/customers/:id` | Chi tiết: gói, hạn, máy, đơn, ghi chú, nhật ký |
| `POST /api/admin/customers/:id/block` / `unblock` | Khoá → xoá phiên, seat, desktop session |
| `POST /api/admin/customers/:id/unlink-google` | §4.3 |
| `POST /api/admin/licenses/:id/transfer` | §4.3 |
| `POST /api/admin/seats/kick`, `POST /api/admin/customers/:id/signout-all` | Đá máy |
| `POST /api/admin/customers/:id/notes` | Ghi chú |
| `GET/PUT /api/admin/plans` | Sửa giá/gói |
| `GET /api/admin/expiring?days=7` | Sắp hết hạn |

Gia hạn: cộng từ `max(now, expires_at)` — giữ cách tính trong SQL như `licenses/renew` hiện tại. Bỏ trả về key `LHM-…`.

### 6.3 Lease ký số cho PC
- Payload: `{customer_id, client_hash, plan_code, seat_limit, license_expires_at, valid_until, issued_at}`, `valid_until = min(now + LEASE_GRACE_HOURS, license_expires_at)`.
- Ký Ed25519 bằng secret `LEASE_SIGNING_KEY` (Worker Secret). Khoá công khai nhúng vào EXE lúc build (`tools/prepare_commercial_build.py`, biến `LHM_LEASE_PUBLIC_KEY_B64`).
- PC: `ads_core/cloud_license.py::active()` = token hợp lệ **và** (heartbeat thành công < TTL **hoặc** lease còn hạn và chữ ký đúng). Chống lùi giờ: lưu `max_seen_time` đã mã hoá DPAPI; thời gian hiện tại < `max_seen_time` − 5 phút → coi như hết grace.
- Server trả `SEAT_REPLACED` / `LICENSE_REVOKED` / `ACCOUNT_BLOCKED` → PC xoá lease ngay.

### 6.4 Hạ tầng Worker
- Hằng số heartbeat 300 s / TTL 600 s; cập nhật cả `static/customer-login.js` (đang `60000`) và `cloud_license.py::heartbeat_loop` (đang 55 s).
- `wrangler.toml`: thêm `[env.staging]` (name `lhm-ads-cloudflare-api-staging`, route staging, D1 staging riêng). Không đụng block production.
- Cron Trigger hằng ngày: huỷ đơn chờ quá hạn; dọn phiên/seat/pairing hết hạn. (Gửi email nhắc gia hạn: để TODO, cần chủ sản phẩm chọn nhà cung cấp email.)

---

## 7. Giao diện

### 7.1 PWA (`static/customer-login.js`, `customer-login.css`, `device-studio.html`, `device-studio.js`)
Màn: **Chào mừng** → **Chọn gói** → **Thanh toán** (QR, số tiền, nội dung CK có nút copy, đếm giờ đơn hết hạn, nút Huỷ / Đổi gói) → **Kích hoạt thành công** → app.
Thêm trang **Tài khoản & gói**: ảnh + Gmail, gói, hạn, máy đang dùng/tối đa + danh sách, Gia hạn, Đăng xuất, Đăng xuất mọi máy.
Gmail chưa có gói → *"`x@gmail.com` chưa có gói. Bạn đã mua bằng Gmail khác? [Đổi Gmail]"*.
Banner theo §3.4. Tiếng Việt, ngắn, không thuật ngữ kỹ thuật. Không inline style (CSP).

### 7.2 PC (`windows/desktop_window.py`, `windows/launcher.py`, `static/desktop-cloud-login.js`, `ads_core/desktop_onboarding.py`, `ads_core/desktop_cloud_license.py`, `ads_core/cloud_license.py`)
- Bản **commercial** build mặc định `LHM_CLOUD_LICENSE_MODE=required` (ghi lúc build). Bản dev giữ như cũ.
- Màn đầu: 1 nút Google + mã 6 số + nút "Mở lại trình duyệt" + trạng thái chờ.
- Banner offline có đếm ngược; banner SEAT_REPLACED + nút "Dùng trên máy này" (`takeover`).
- Hết hạn → **khoá cứng theo §3.5**: chỉ còn màn khoá + Gia hạn + Đăng xuất/Đổi Gmail; **cập nhật online vẫn chạy**.
- Bộ thu thập nền, monitoring, MCP stdio **dừng ngay** khi hết gói / hết grace / bị thu hồi / bị khoá (không chờ người dùng mở app).
- Đổi Gmail / đăng xuất: giữ cách ly `org_id=google:<uuid>`.

### 7.4 PWA chạy Ads như PC (mục tiêu 2)

**Nguyên tắc:** bản PC là chuẩn. PWA phải cho **cùng kết quả** với PC trên cùng dữ liệu (số liệu, báo cáo, khuyến nghị, kế hoạch thay đổi). Không sửa hành vi PC trong lúc làm PWA.

**Bảng đối chiếu tính năng**

| Trang PC (`static/studio.html`) | Logic PC | PWA |
|---|---|---|
| Tài khoản Ads | `oauth_connect.py`, `providers.py`, `permissions.py` | **Làm**: kết nối Google/Meta trong trình duyệt, liệt kê tài khoản, nút Kiểm tra API |
| Tổng quan, Báo cáo, xuất CSV | `providers.py`, `report_dates.py`, `extended.py`, `reconciliation.py` | **Làm** |
| Chiến dịch + Duyệt thay đổi | `optimizations.py`, `google_mutations.py` | **Làm**, giữ nguyên rào chắn: mọi thay đổi phải tạo kế hoạch → người dùng xác nhận lần 2 → kiểm tra lại sau khi áp dụng (`docs/POST_MUTATION_VERIFICATION.md`) |
| Trợ lý / AI Center | `advisor.py`, `optimization_playbook.py`, `local_ai.py`, `openrouter_ai.py` | **Làm** (OpenRouter tuỳ chọn, khoá của khách lưu trong kho mã hoá) |
| Cảnh báo, KPI, mục tiêu | `goals.py`, `budget_push.py`, `monitoring.py` | **Làm khi app đang mở**; không có giám sát nền |
| Autopilot, giám sát 24/7, MCP | `autopilot.py`, `monitor_worker.py`, `mcp_*` | **Không làm** — hiện "Chỉ có trên bản PC" (giới hạn nền tảng, xem `docs/DEVICE_ONLY_ADS_DATA.md`) |
| Bản quyền | `licensing.py` | Thay bằng trang **Tài khoản & gói** (§7.1) |
| Nhóm, nhật ký | `extended.py`, audit | Một người dùng mỗi Gmail; nhật ký thao tác lưu trong kho mã hoá |
| Cài đặt, sao lưu | `secure_backup.py` | Đã có (`device-vault*.js`); giữ |

**Kết nối Ads trong trình duyệt — không secret, không server:**
- **Google Ads:** OAuth client loại *Web application* **cùng Cloud project** với bản PC (để dùng chung mức truy cập Basic/Standard và màn đồng ý đã xác minh). Dùng luồng client-side `response_type=token`, scope `https://www.googleapis.com/auth/adwords`, chuyển trang toàn cửa sổ (không popup, không iframe, không thư viện Google). Access token sống 1 giờ, lưu trong kho mã hoá; hết hạn thì tự chuyển trang `prompt=none` để lấy token mới (người dùng không phải bấm nếu vẫn đăng nhập Google). Không có refresh token trên PWA — chấp nhận.
- **Meta:** luồng đăng nhập thủ công `response_type=token`, quyền `ads_read` (+ `ads_management` khi App Review duyệt). Token ngắn hạn, hết hạn thì chuyển trang đăng nhập lại (Meta tự quay về nếu đã cấp quyền). Không dùng Facebook JS SDK, không đổi sang token dài hạn (cần App Secret).
- **Đường dẫn quay về cố định:** Google → `https://ads.lhmcrm.com/local/oauth/google`, Meta → `https://ads.lhmcrm.com/local/oauth/meta` (staging tương ứng). Trang quay về chỉ đọc token từ phần `#fragment`, xoá ngay khỏi thanh địa chỉ (`history.replaceState`), kiểm tra `state`, ghi vào kho mã hoá rồi chuyển về trang trước. Service worker không được cache hai trang này.
- OAuth client Web cho Ads tên `LHM Ads PWA` (khác client `LHM Login` dùng cho đăng ký). Client ID đưa vào bản build PWA qua biến build `LHM_GOOGLE_ADS_WEB_CLIENT_ID`; Meta App ID qua `LHM_META_APP_ID` (cả hai không phải secret).
- Tài khoản Google dùng để **đăng ký LHM** và tài khoản Google **quản lý quảng cáo** có thể khác nhau — UI ghi rõ hai mục riêng.
- CSP: giữ `script-src 'self'`; `connect-src` thêm đúng `https://googleads.googleapis.com https://graph.facebook.com` (và `https://openrouter.ai` nếu bật AI). Sửa trong `tools/build_github_pages.py`.

**Chống lệch logic giữa PC (Python) và PWA (JS) — bắt buộc:**
1. **Trước khi viết JS:** tạo bộ dữ liệu chuẩn `tests/fixtures/core/*.json` từ **chính code Python hiện tại** (đầu vào: phản hồi API Google/Meta mẫu, chiến dịch, mục tiêu; đầu ra: số liệu chuẩn hoá, báo cáo, khuyến nghị playbook, kế hoạch thay đổi).
2. Tách **quy tắc** của `optimization_playbook.py` (điều kiện, ngưỡng, lý do, bước xử lý, rào chắn) ra `shared/rules/playbook.json`; Python đọc JSON này. Test cũ + fixtures phải ra **đúng y kết quả cũ**.
3. Viết lõi JS dạng ES module, không bundler, trong `static/core/`: `google-ads.js`, `meta-ads.js`, `report-dates.js`, `metrics.js`, `playbook.js` (đọc cùng `playbook.json`), `advisor.js`, `mutations.js`, `goals.js`, `csv.js`. Phiên bản API dùng chung `shared/api-versions.json` (Python cũng đọc).
4. CI chạy **cùng fixtures** cho Python (`pytest`) và JS (`node --test`); khác nhau một số là đỏ.
5. Test Chromium cho PWA với Google/Meta **giả lập bằng chặn request** (không gọi API thật trong CI): kết nối → báo cáo → khuyến nghị → tạo kế hoạch tạm dừng → xác nhận → kiểm tra sau áp dụng; xác minh không request nào đi tới `ads.lhmcrm.com` chứa token/ID/báo cáo.

**Khoá cứng trên PWA:** mọi hàm trong `static/core/` gọi Google/Meta phải qua một cổng kiểm tra gói (`session` còn hạn); hết hạn → không gọi API, không mở kho (§3.5).

### 7.3 Admin (`static/admin.html`, `static/admin.js`)
Tab: **Đơn chờ** (mặc định) · **Khách hàng** (tìm + trang chi tiết) · **Cấp gói theo Gmail** · **Sắp hết hạn** (nút copy tin nhắn nhắc) · **Bảng giá** · **Nhật ký**. Mọi nơi hiện Gmail + nhãn ✓ đã xác minh / ⚠ chưa đăng nhập. Thao tác nguy hiểm (khoá, thu hồi, gỡ liên kết, chuyển gói) có hộp xác nhận nhập lại Gmail.

---

## 8. Thứ tự làm và tiêu chí xong

Làm tuần tự. Mỗi việc = 1 commit rõ ràng. Hết mỗi giai đoạn: push, CI xanh, cập nhật mô tả PR #46 (phần checklist), rồi mới sang giai đoạn sau.

| GĐ | Việc | Xong khi |
|---|---|---|
| **0** | (a) ĐÃ XONG: PR #48 sửa `tools/device_vault_smoke.py` trên `main`. (b) ĐÃ XONG: PR #46 xanh, thứ tự 401→402 đúng. (c) Workers Builds đỏ ở commit chỉ sửa tài liệu (`96bf756`) → lỗi phía Cloudflare, cần chủ sản phẩm đọc log trong dashboard; agent không tự đổi cấu hình Cloudflare. (d) Merge `main` vào nhánh PR #46 sau khi PR #48 vào `main`. (e) `[env.staging]`. | `main` xanh; PR #46 xanh toàn bộ job; staging deploy được bằng `wrangler deploy --env staging` |
| **1** | Migration 0006 + `normalize()` + so khớp §4.2 + API khách §6.1 + API admin §6.2 + lease §6.3 + cron | Test Python/Node cho từng endpoint, migration, race (2 request gắn `sub` cùng lúc, 2 lần activate cùng đơn), chuẩn hoá Gmail; `worker_commerce_smoke.test.mjs` mở rộng |
| **2** | UI PWA §7.1 | Test Chromium (kiểu `tools/device_vault_smoke.py`) cho: chọn gói → QR → giả lập admin activate → tự mở khoá; đổi Gmail không mở kho Gmail khác |
| **2B** | PWA chạy Ads như PC §7.4, theo đúng thứ tự 1→5 trong mục "Chống lệch logic" | Fixtures tạo từ Python trước; Python vẫn ra kết quả cũ sau khi tách `playbook.json`; JS khớp Python trên mọi fixture; test Chromium với API giả lập xanh; bảng đối chiếu tính năng §7.4 đánh dấu từng dòng xong / chưa |
| **3** | PC §7.2 + chống bẻ khoá lớp 1 (§11) | `tests/test_google_only_desktop.py` mở rộng: grace offline, chống lùi giờ, takeover, **hết hạn khoá cứng: mọi route ngoài allowlist §3.5 trả 402, thread nền dừng**, revoke xoá lease |
| **4** | Admin UI §7.3 | Test SQL/handler cho mọi thao tác; xác nhận nhập lại Gmail |
| **5** | Công cụ chuyển khách pilot: `tools/migrate_pilot_to_gmail.py` đọc `vendor_ledger`, nhận CSV `customer_ref,gmail` do chủ sản phẩm điền, gọi `/api/admin/grant` với **số ngày còn lại**, chế độ `--dry-run` mặc định | Dry-run in bảng đối chiếu; không gửi gì khi thiếu cờ `--apply` |
| **6** | Trang tĩnh `/dieu-khoan` và `/bao-mat` (nội dung do chủ sản phẩm cung cấp; chưa có thì để khung + `TODO`, không tự viết nội dung pháp lý). Tài liệu: cập nhật `README.md` (bỏ hướng dẫn VPS khỏi phần đầu), `docs/GOOGLE_SUBSCRIPTION_ROLLOUT.md`, `docs/sales/FAQ-KHACH-HANG.md` (câu 1, 8, 13 theo mô hình Gmail), `docs/ACCEPTANCE.md` (thêm ma trận §9, mặc định `NOT_RUN`) | Tài liệu khớp code; không còn chỗ hứa "license offline vĩnh viễn" hay "24/7" |

Chạy trước mỗi lần push: `python -m pytest -q` và các lệnh `node --check` / `node --test` trong `.github/workflows/ci.yml`.

---

## 9. Ma trận nghiệm thu (agent viết test tự động được phần nào thì viết; phần thật ghi `NOT_RUN`)

1. Gmail mới → chưa có gói → đặt đơn → activate → mở khoá ≤ 15 s (PWA và PC).
2. Admin cấp trước cho `Nguyen.Van.A@gmail.com` → khách đăng nhập `nguyenvana@gmail.com` → nhận đúng gói.
3. Gmail **không** được cấp → không vào được, có nút Đổi Gmail.
4. Gia hạn khi còn hạn → cộng dồn đúng; thu hồi; gỡ liên kết; chuyển gói.
4b. **Hết hạn = khoá cứng:** đúng giờ hết hạn (kể cả PC đang offline) → không mở được Dashboard, báo cáo cũ, xuất CSV/sao lưu, kết nối Ads, AI, autopilot; bộ thu thập nền và MCP dừng; chỉ còn màn khoá + Gia hạn + Đăng xuất + cập nhật app. Gia hạn xong → mở lại đầy đủ, dữ liệu cũ còn nguyên.
5. Gói 2 máy: PC + điện thoại OK; máy thứ 3 → hỏi xác nhận → máy cũ nhất bị đăng xuất ở heartbeat sau.
6. PC offline 1 giờ dùng được; 80 giờ bị khoá; lùi đồng hồ máy không kéo dài được.
7. Khởi động lại PC giữ trạng thái; đăng xuất xoá token và lease.
8. Hai Gmail trên cùng PC / cùng trình duyệt → không lộ dữ liệu Ads của nhau.
9. Network log: không request nào tới Cloudflare chứa token/ID/báo cáo Ads.
11. **PWA so với PC trên cùng tài khoản Ads thật:** tổng chi tiêu, số chuyển đổi, CPA/ROAS từng chiến dịch, danh sách khuyến nghị và kế hoạch tạm dừng giống nhau giữa PWA và PC (cùng khoảng ngày) — **chủ sản phẩm chạy**, agent chuẩn bị bảng so sánh.
12. PWA để quá 1 giờ rồi thao tác → tự lấy token Google mới, không mất dữ liệu đang xem.
10. Thiết bị thật: Android Chrome, iPhone Safari (PWA cài lên màn hình), Windows 10 và 11 sạch — **chủ sản phẩm chạy**.

---

## 10. Việc của chủ sản phẩm (agent KHÔNG làm, chỉ nhắc trong báo cáo)

- Repo đang public trong giai đoạn xây dựng (chủ sản phẩm đã chọn). **Chuyển private là điều kiện bắt buộc trước khi phát hành bản thương mại đầu tiên**; bật branch protection `main`. Trong lúc repo còn public, agent tuyệt đối không commit secret, khoá riêng, token, dữ liệu khách hay danh sách Gmail khách.
- Cloudflare: Workers Paid; Workers Builds chỉ `main` → production; tạo D1 staging; đặt Worker Secrets (`GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `LEASE_SIGNING_KEY`) và env ngân hàng; R2 `download.lhmcrm.com` cho EXE + `lhm-update.json`.
- Google Cloud: OAuth client staging (Testing) và production; consent screen tên "LHM Ads AI", logo, link điều khoản/bảo mật; xác minh domain `lhmcrm.com`; xác minh thương hiệu.
- Nộp Google Ads developer token mức Basic; Meta Business Verification + App Review `ads_read`, `ads_management`.
- Viết Điều khoản dịch vụ, Chính sách bảo mật, chính sách hoàn tiền.
- Thu Gmail của khách pilot cũ cho GĐ 5.
- Nghiệm thu thật mục 9.10 và ký biên bản.

---

## 11. Chống bẻ khoá EXE / PWA

Mục tiêu thực tế: **không phần mềm chạy trên máy khách nào "100% không bẻ được"**. Mục tiêu là làm giả license là không thể (server ký số), còn sửa app để bỏ kiểm tra thì tốn nhiều công hơn tiền gói và bản crack kém giá trị hơn bản thật. Không ghi "không thể crack" trong tài liệu bán hàng.

**Lớp 1 — làm trong GĐ 3 (agent làm):**
- Build EXE commercial bằng **Nuitka** thay PyInstaller `--onefile` (sửa `.github/workflows/windows-exe.yml`; giữ PyInstaller cho bản dev nếu Nuitka chưa ổn định). Ghi rõ nếu chưa đạt.
- Kiểm tra quyền dùng ở **nhiều chỗ độc lập**: middleware API, bộ thu thập nền, monitoring, MCP stdio, UI; mỗi chỗ tự xác minh chữ ký lease, không chỉ đọc một biến cờ.
- **Không nhúng secret thật vào EXE**: không `META_APP_SECRET`, không khoá ký nào, không secret của OAuth client loại Web. (OAuth client Desktop của Google được phép đóng vào bản build — xem §12.)
- Ký Authenticode do chủ sản phẩm làm (§10); agent chỉ giữ nguyên quy trình `windows/package-commercial-release.ps1`.

**Lớp 2 — làm SAU khi repo chuyển private (agent làm, có lệnh của chủ sản phẩm):**
- Bản cập nhật chỉ phát cho Gmail còn hạn: manifest cập nhật trả link tải có chữ ký, có thời hạn, sau khi kiểm tra phiên.
- Bộ quy tắc tối ưu (`ads_core/optimization_playbook.py`) phát dạng gói quy tắc mã hoá gắn lease, hết hạn theo lease; gói chỉ chứa quy tắc, **không chứa dữ liệu Ads**.
- PWA: Worker chỉ trả mã app (`/local/` và JS của app) cho phiên Gmail còn hạn; trang đăng nhập/chọn gói/thanh toán vẫn công khai.

**Lớp 3 — chủ sản phẩm:** điều khoản cấm bẻ khoá/chia sẻ, theo dõi bất thường (một Gmail đổi máy liên tục), gửi yêu cầu gỡ bản crack.

---

## 12. Câu hỏi mở — agent KHÔNG tự quyết, hỏi chủ sản phẩm

1. **Thông tin xác thực Google/Meta cho bản thương mại.** Google Ads API **đã bỏ developer token từ 9/9/2026**; quyền truy cập (Test/Explorer/Basic/Standard) gắn với **Google Cloud project** tạo ra OAuth client. Hệ quả:
   - **PC (EXE):** dùng OAuth client loại *Desktop app* thuộc Cloud project của chủ sản phẩm (đã được duyệt Basic). Theo Google, secret của client Desktop không được coi là bí mật → được đóng vào bản build qua biến build, không commit vào git. PC gọi thẳng Google Ads API, không qua Cloudflare.
   - **PWA:** dùng luồng client-side (`response_type=token`) theo §7.4 → **không cần client secret, không cần Worker**. Đánh đổi: không có refresh token, token 1 giờ được làm mới bằng chuyển trang `prompt=none`.
   - **Meta:** `META_APP_SECRET` không được đóng vào EXE/PWA. PWA dùng token ngắn hạn theo §7.4. Bản PC giữ nguyên cách đang chạy tốt.
   - Bỏ phụ thuộc `GOOGLE_ADS_DEVELOPER_TOKEN` (header tuỳ chọn, Google sẽ từ chối ở bản API lớn sau) — gỡ khỏi `ads_core/providers.py`, `optimizations.py`, `permissions.py`, `oauth_connect.py`, `tools/acceptance_preflight.py`, kèm test, **không làm đổi hành vi PC đang chạy** (luật §1.11).
   - Chỉ khi chủ sản phẩm yêu cầu PWA phải có refresh token / token Meta dài hạn mới cần endpoint Worker trung chuyển — việc đó phải được duyệt nới chính sách device-only trước; agent không tự làm.
2. Giá gói `team` và có bán kỳ 6/12 tháng ngay từ đầu không.
3. Nhà cung cấp email để nhắc gia hạn (Cron đã chừa chỗ).

---

## 13. Cách báo cáo

Cuối mỗi giai đoạn gửi: danh sách commit, kết quả test (số passed/failed, dán nguyên dòng tổng kết), link CI run, những gì **chưa** làm hoặc `NOT_RUN`, và câu hỏi cần chủ sản phẩm quyết. Gặp mâu thuẫn giữa brief này và luật ở §1 → luật §1 thắng, dừng lại hỏi.
