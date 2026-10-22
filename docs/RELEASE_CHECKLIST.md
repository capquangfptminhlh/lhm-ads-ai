# Danh sách kiểm tra phát hành — LHM Ads AI

Quy trình cổng phát hành lặp lại cho mọi bản gửi khách. **Không bỏ qua
mục nào; mục nào chưa đạt thì ghi rõ lý do trong ghi chú phát hành.**
Người duy nhất quyết định phát hành và số phiên bản là chủ phần mềm.

## 0. Phiên bản

- [ ] Phiên bản hiện khai báo: **0.3** — chỉ có ở hai nơi dạng văn bản:
      tiêu đề `README.md` ("Private Studio 0.3") và `docs/STUDIO.md`.
      Repo **chưa có** hằng số phiên bản trong code, chưa có git tag.
- [ ] Khi tăng phiên bản: sửa **đồng thời cả hai nơi trên cùng một commit**,
      thêm mục mới vào `CHANGELOG.md`, và tạo git tag `v<x.y.z>` sau khi
      merge. Không để hai nơi lệch nhau.
- [ ] Đặt phiên bản ở **file nguồn phiên bản** `ads_core/version.py` (tạo
      file này nếu bản đang phát hành chưa có) và xác nhận số trong đó
      **khớp** với `README.md` và `docs/STUDIO.md`. Cả ba nơi lệch nhau
      thì chưa được gắn tag.
- [ ] Đề xuất dài hạn (chưa làm, không tự ý làm trong bản này): thêm hằng
      số phiên bản duy nhất trong code và để README/UI đọc từ đó.

## 1. Kiểm thử tự động

- [ ] Chạy toàn bộ test tại máy phát hành từ thư mục gốc repo:
      `python -m pytest tests/ -q` — yêu cầu: **0 failed** (số passed
      phải bằng hoặc cao hơn bản trước; ghi lại con số).
- [ ] CI trên GitHub cho commit phát hành: job **test** xanh.
- [ ] Không merge khi còn test đỏ, dù "chỉ đỏ ở máy khác".
- [ ] **Trước khi gắn tag**: tạo lại báo cáo tiền kiểm nghiệm thu bằng
      `python tools/acceptance_preflight.py` trên đúng commit sẽ phát
      hành và lưu kết quả kèm hồ sơ phát hành; mục nào `NOT_RUN` phải
      xuất hiện nguyên trạng trong ghi chú phát hành (xem mục 8).
- [ ] **Trước khi gắn tag**: chạy lại bài diễn tập khôi phục
      `python tools/restore_drill.py` — yêu cầu đạt toàn bộ (14/14 ở lần
      ghi nhận gần nhất); drill đỏ thì không phát hành.

## 2. Rà soát giao diện bằng ảnh chụp

- [ ] Chạy app thật, chụp lại tối thiểu các màn hình: đăng nhập (desktop
      + mobile), Tổng quan, Tài khoản Ads, Chiến dịch, AI Center, Cài đặt,
      Bản quyền, Autopilot.
- [ ] Đối chiếu với bộ ảnh của bản trước: bố cục không vỡ, không tràn
      ngang, không còn style nội tuyến bị CSP chặn (xem console — lỗi
      "Applying inline style violates..." phải bằng 0).
- [ ] Kiểm tra font: `document.fonts.check('700 20px Inter')` phải là
      `true` (font Inter đóng gói trong `static/fonts.css` đã tải).

## 3. Build EXE qua CI

- [ ] Build bằng GitHub Actions job **windows-exe** trên đúng commit sẽ
      phát hành (không build tay ở máy lạ rồi gửi khách).
- [ ] Job windows-exe xanh, gồm cả bước chạy thử EXE thật trên Windows
      runner và bước xuất SHA256 + `release-manifest.json`.
- [ ] Tải artifact về, lưu kèm file checksum của CI.

## 4. Tên artifact — quy tắc trung thực về chữ ký số

- [ ] Artifact từ CI hiện mang tên
      **`LHM-Ads-AI-COMMERCIAL-CANDIDATE-UNSIGNED`** (bản thương mại) hoặc
      `LHM-Ads-AI-PILOT`. **Giữ nguyên chữ `UNSIGNED`** trong mọi tên file,
      thư mục và ghi chú chừng nào chưa có chứng thư Authenticode.
- [ ] **Không tự phát hành file unsigned cho khách trả tiền** (theo
      `docs/COMMERCIAL_LICENSE.md`): bản gửi khách phải là bản đã ký.
- [ ] Ngày có chứng thư Authenticode, thay đổi đúng các việc sau:
      1. Ký EXE bằng chứng thư của chủ phần mềm **ngoài GitHub**.
      2. Kiểm tra chữ ký bằng `windows/verify-release.ps1 -Exe .\LHM-Ads-AI.exe
         -ExpectedThumbprint <PUBLISHER_CERT_SHA1> -HashOut .\LHM-Ads-AI-signed.sha256`.
      3. Tính lại SHA256 **sau khi ký** — checksum của bản unsigned chỉ còn
         giá trị nội bộ, không dùng cho bản gửi khách.
      4. Khi đó (và chỉ khi đó) mới bỏ chữ `UNSIGNED` khỏi tên artifact và
         ghi chú phát hành, đồng thời ghi rõ nhà phát hành theo chứng thư.

## 5. Khóa cấp bản quyền — nơi giữ và kỷ luật

- [ ] Khóa riêng Ed25519 của bên phát hành (`vendor-private-key.pem`)
      **không bao giờ** nằm trong repo, trong EXE, trong CI hay trong thư
      mục đồng bộ đám mây; chỉ ở máy của chủ phần mềm, có sao lưu mã hóa
      ngoại tuyến.
- [ ] Trước khi ký bản quyền, luôn chạy `license_issuer.py` kèm
      `--expected-public` để đối chiếu đúng bộ khóa.
- [ ] Mất khóa riêng = không cấp/gia hạn được bản quyền cho toàn bộ khách
      hiện hữu; lộ khóa riêng = ai cũng tự cấp được bản quyền. Cả hai đều
      là sự cố nghiêm trọng, xử lý trước mọi việc khác.

## 6. Sổ bán hàng — sao lưu trước phát hành

- [ ] Sao lưu sổ bên bán trước mỗi đợt phát hành:
      `python tools/vendor_ledger.py backup --out <đường-dẫn-ngoài-repo>`
      (xem `docs/VENDOR_OPERATIONS.md`), lưu bản sao lưu **ngoài repo**.
- [ ] Chạy `python tools/vendor_ledger.py remind` để nắm danh sách khách
      sắp hết hạn trong kỳ phát hành.

## 7. Thanh toán — trạng thái hiện tại (không nói quá)

- [ ] Quy trình mặc định đang áp dụng: khách chuyển khoản vào tài khoản
      của chủ phần mềm → chủ **tự xác nhận đã nhận tiền** → mới ký và kích
      hoạt bản quyền. Ghi đúng câu này trong ghi chú phát hành nếu có thay
      đổi về cách thanh toán.
- [ ] PayOS đã tích hợp ở trạng thái chờ (`docs/PAYOS.md`): chỉ bật khi
      chủ phần mềm có khóa merchant thật. Webhook PayOS **chỉ đánh dấu đã
      thanh toán, không tự cấp bản quyền** — bước kích hoạt vẫn qua tay chủ.

## 8. Nghiệm thu trực tiếp — bắt buộc nêu trong mọi ghi chú phát hành

- [ ] Trạng thái nghiệm thu sống phải xuất hiện **nguyên văn** trong ghi
      chú phát hành (mẫu ở mục 9), không được bỏ qua hay viết mơ hồ:
      - Google Ads live: **NOT_RUN** — cho đến khi chủ phần mềm chạy thật
        bằng developer token + tài khoản kiểm thử theo `docs/ACCEPTANCE.md`.
      - Meta Ads live: **NOT_RUN** — cho đến khi app được duyệt quyền
        `ads_read`/`ads_management` và chạy thật theo `docs/ACCEPTANCE.md`.
      - Windows EXE qua khởi động lại/đóng giao diện/ngủ đông: theo
        `docs/ACCEPTANCE.md`.
- [ ] Chỉ khi đã chạy thật và có bằng chứng mới đổi NOT_RUN thành ngày
      tháng + kết quả. "Test tự động xanh" **không** thay thế nghiệm thu
      trực tiếp.

## 9. Mẫu ghi chú phát hành GitHub (dán và điền)

```markdown
## LHM Ads AI <PHIÊN BẢN> — <YYYY-MM-DD>

### Trạng thái nghiệm thu trực tiếp (bắt buộc đọc)
- Google Ads live: NOT_RUN
- Meta Ads live: NOT_RUN
- Bản EXE này: UNSIGNED — chưa ký Authenticode, không dùng cho khách trả tiền
  <!-- Thay dòng trên bằng "Đã ký Authenticode, SHA256 sau ký ở file đính kèm"
       chỉ sau khi hoàn thành mục 4 của docs/RELEASE_CHECKLIST.md -->

### Thay đổi chính
- <tóm tắt từ CHANGELOG.md, mục của phiên bản này>

### Kiểm chứng đã thực hiện
- Test tự động: <số> passed, <số> skipped, 0 failed
- CI: test ✅ · windows-exe ✅ (commit <sha ngắn>)
- Rà soát giao diện bằng ảnh chụp: đạt

### Thanh toán & kích hoạt
- Chuyển khoản vào tài khoản của bên bán; bên bán xác nhận nhận tiền rồi
  mới kích hoạt bản quyền theo mã máy của khách.

### Tệp đính kèm
- EXE + SHA256 + release-manifest.json từ job windows-exe của đúng commit này
```

## 10. Sau phát hành

- [ ] Gắn tag phiên bản trên đúng commit đã build (mục 0).
- [ ] Lưu trữ artifact + checksum + ghi chú ở một nơi ngoài GitHub.
- [ ] Cập nhật `CHANGELOG.md`: chuyển mục *Chưa phát hành* thành mục có
      số phiên bản và ngày phát hành.


### Phương án khác: chủ sở hữu chọn không ký Authenticode

Nếu bên bán chính thức chọn EXE **COMMERCIAL-UNSIGNED**, áp dụng quy trình [COMMERCIAL_UNSIGNED.md](COMMERCIAL_UNSIGNED.md) thay mục bắt buộc ký Authenticode. **Giữ nguyên** toàn bộ kiểm thử và bằng chứng nghiệm thu API thật, so khớp khóa ký license, SHA256 và xác minh Ed25519 release manifest. Trong ghi chú bán hàng phải có câu **"EXE chưa có chữ ký số được Windows tin cậy; Windows có thể cảnh báo Unknown publisher/SmartScreen"**. Không gắn tên SIGNED, không tuyên bố chứng thư đã được cấp.
