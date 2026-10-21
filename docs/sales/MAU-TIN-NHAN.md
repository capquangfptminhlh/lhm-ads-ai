# Mẫu tin nhắn gửi khách — LHM Ads AI

Copy, thay các chỗ trong `[NGOAC VUONG]` rồi gửi. Trước khi dùng lần đầu, bên bán phải điền sẵn các thông tin cố định (ngân hàng, cú pháp chuyển khoản, giá) và chốt các mục ghi `[CHU SAN PHAM QUYET DINH]`.

**Nguyên tắc viết trong mọi mẫu:** chỉ hứa đúng khả năng phần mềm. Không viết "tự động xác nhận thanh toán", "giám sát 24/7 kể cả khi tắt máy", "bên em có thể khóa/mở máy anh chị từ xa" — phần mềm không có các tính năng đó. Giám sát nền chỉ chạy khi máy khách đang bật, đã đăng nhập Windows và có Internet.

Danh sách placeholder dùng chung:

- `[TEN KHACH]` — tên/xưng hô với khách
- `[MA KHACH]` — mã khách nội bộ bên bán cấp (ví dụ KH001)
- `[GOI]` — tên gói khách mua
- `[SO TIEN]` — số tiền phải chuyển
- `[NGAY HET HAN]` — ngày license hết hạn
- `[SO NGAY CON LAI]` — số ngày còn lại tới khi hết hạn
- `[KENH HO TRO]` — kênh liên hệ hỗ trợ (Zalo/Messenger/email của bên bán)

---

## Mẫu 1 — Báo giá + hướng dẫn lấy mã máy

### Bản Zalo / Messenger (thân mật)

```
Chào [TEN KHACH], em gửi thông tin gói LHM Ads AI như sau ạ:

- Gói: [GOI] — [SO TIEN] / [THOI HAN, VI DU: 30 NGAY]
- Phần mềm cài trên máy của [TEN KHACH], dữ liệu quảng cáo và token ở lại máy mình, không gửi về bên em.
- Giám sát nền chỉ đọc báo cáo và chỉ chạy khi máy đang bật + có Internet. Mọi thay đổi ngân sách/giá thầu đều cần người duyệt, phần mềm không tự chỉnh quảng cáo.

Để kích hoạt, em cần MÃ MÁY của máy sẽ dùng phần mềm:
1. Cài và mở LHM Ads AI (file em gửi kèm).
2. Vào trang "Bản quyền" ở menu bên trái.
3. Bấm nút "Sao chép mã máy" rồi gửi lại mã đó cho em.

Lưu ý: chỉ gửi mã máy, không gửi token hay mật khẩu tài khoản quảng cáo cho bất kỳ ai ạ.
Nhận được mã máy, em sẽ gửi thông tin chuyển khoản để mình thanh toán.
```

### Bản email (trang trọng)

```
Kính gửi [TEN KHACH],

Cảm ơn anh/chị đã quan tâm LHM Ads AI. Thông tin gói như sau:

- Gói: [GOI]
- Giá: [SO TIEN] / [THOI HAN]
- Hình thức: phần mềm cài đặt trên máy của khách hàng; dữ liệu quảng cáo và thông tin đăng nhập API lưu tại máy khách, không chuyển về máy chủ của chúng tôi.
- Tính năng giám sát nền hoạt động khi máy khách đang bật, đã đăng nhập Windows và có kết nối Internet; các thay đổi đối với chiến dịch quảng cáo luôn yêu cầu người dùng phê duyệt.

Để tiến hành, anh/chị vui lòng:
1. Cài đặt và mở phần mềm theo file đính kèm.
2. Mở trang "Bản quyền", bấm "Sao chép mã máy".
3. Gửi lại mã máy cho chúng tôi qua email này.

Chúng tôi chỉ cần mã máy; anh/chị không gửi token quảng cáo hay mật khẩu tài khoản cho bất kỳ ai.

Trân trọng,
[TEN BEN BAN / NGUOI PHU TRACH]
[KENH HO TRO]
```

---

## Mẫu 2 — Thông tin chuyển khoản

### Bản Zalo / Messenger

```
[TEN KHACH] chuyển khoản giúp em theo thông tin này ạ:

- Ngân hàng: [TEN NGAN HANG]
- Số tài khoản: [SO TAI KHOAN]
- Chủ tài khoản: [CHU TAI KHOAN]
- Số tiền: [SO TIEN]
- Nội dung chuyển khoản (ghi đúng cú pháp để em đối chiếu nhanh): [CU PHAP NOI DUNG — MAC DINH: LHM <MA KHACH>, VI DU: LHM KH001]

Chuyển xong [TEN KHACH] chụp màn hình giao dịch gửi em. Em kiểm tra tiền về trên tài khoản của bên em rồi mới kích hoạt (bước này em xác nhận thủ công nên có thể mất tới [THOI GIAN XU LY TOI DA — CHU SAN PHAM QUYET DINH] trong giờ làm việc). Nhận được tiền, em gửi file kích hoạt ngay ạ.
```

### Bản email

```
Kính gửi [TEN KHACH],

Thông tin thanh toán cho gói [GOI]:

- Ngân hàng: [TEN NGAN HANG]
- Số tài khoản: [SO TAI KHOAN]
- Chủ tài khoản: [CHU TAI KHOAN]
- Số tiền: [SO TIEN]
- Nội dung chuyển khoản: [CU PHAP NOI DUNG — MAC DINH: LHM <MA KHACH>]

Sau khi chuyển khoản, anh/chị vui lòng phản hồi email này kèm ảnh chụp giao dịch. Chúng tôi tự đối chiếu trên tài khoản ngân hàng của mình và chỉ phát hành license sau khi tiền đã về tài khoản. File license sẽ được gửi trong vòng [THOI GIAN XU LY TOI DA — CHU SAN PHAM QUYET DINH] giờ làm việc kể từ khi xác nhận được tiền.

Trân trọng,
[TEN BEN BAN / NGUOI PHU TRACH]
```

---

## Mẫu 3 — Đã nhận tiền + gửi file license + hướng dẫn kích hoạt

Dùng cho cả Zalo/Messenger/email; đính kèm file `[TEN FILE LICENSE].json` khi gửi.

```
Chào [TEN KHACH], em đã nhận được [SO TIEN] cho gói [GOI]. Mã khách của mình: [MA KHACH]. License có hiệu lực tới [NGAY HET HAN].

Em gửi kèm file license. Kích hoạt như sau:
1. Mở LHM Ads AI, vào trang "Bản quyền".
2. Mở file license em gửi, sao chép toàn bộ nội dung, dán vào ô "Nhập nội dung file license.json".
3. Bấm "Kích hoạt / Gia hạn".
4. Thấy dòng Trạng thái hiện "Đã kích hoạt" và ngày hết hạn [NGAY HET HAN] là xong.

Lưu ý:
- File license chỉ dùng được trên đúng máy đã gửi mã máy cho em. Đổi máy thì nhắn em cấp lại, đừng chia sẻ file cho máy khác (sẽ không kích hoạt được).
- Giờ trên máy cần để đúng giờ thực tế; nếu máy bị chỉnh lùi giờ, phần mềm sẽ tạm chặn tính năng trả phí — chỉ cần đồng bộ lại giờ Windows là dùng tiếp.

Kích hoạt xong [TEN KHACH] nhắn lại giúp em một tiếng để em ghi nhận. Có lỗi gì, chụp màn hình gửi em qua [KENH HO TRO].
```

---

## Mẫu 4 — Nhắc gia hạn

### Nhắc trước 7 ngày (Zalo/Messenger)

```
Chào [TEN KHACH], license LHM Ads AI (mã khách [MA KHACH]) của mình còn [SO NGAY CON LAI] ngày, hết hạn vào [NGAY HET HAN].

Gia hạn sớm thì số ngày mới được cộng dồn tiếp vào hạn hiện tại, không bị mất ngày. [TEN KHACH] muốn gia hạn thì nhắn em, em gửi lại thông tin chuyển khoản; tiền về là em ký file gia hạn gửi ngay, mình dán vào trang Bản quyền như lần đầu là xong.
```

### Nhắc trước 1 ngày (Zalo/Messenger, ngắn)

```
[TEN KHACH] ơi, license LHM Ads AI của mình hết hạn ngày mai ([NGAY HET HAN]). Nếu đang chạy giám sát nền thì sau khi hết hạn phần giám sát sẽ dừng (dữ liệu vẫn còn nguyên, xem và xuất báo cáo bình thường). Mình gia hạn luôn không ạ? Cộng dồn ngày, không mất ngày nào.
```

### Bản email (dùng cho cả mốc 7 ngày và 1 ngày)

```
Kính gửi [TEN KHACH],

License LHM Ads AI của anh/chị (mã khách: [MA KHACH], gói: [GOI]) sẽ hết hạn vào [NGAY HET HAN] — còn [SO NGAY CON LAI] ngày.

Gia hạn trước hạn sẽ được cộng dồn thêm ngày vào thời hạn hiện tại. Để gia hạn, anh/chị chỉ cần phản hồi email này; chúng tôi sẽ gửi thông tin chuyển khoản, và ngay khi xác nhận được tiền, file license gia hạn sẽ được gửi để anh/chị dán vào trang "Bản quyền" trong phần mềm.

Sau khi hết hạn, dữ liệu của anh/chị không bị xóa: phần mềm vẫn mở để xem và xuất báo cáo, chỉ các tính năng trả phí và giám sát nền tạm dừng cho tới khi gia hạn.

Trân trọng,
[TEN BEN BAN / NGUOI PHU TRACH]
[KENH HO TRO]
```

---

## Mẫu 5 — Đã hết hạn

```
Chào [TEN KHACH], license LHM Ads AI (mã khách [MA KHACH]) của mình đã hết hạn từ [NGAY HET HAN].

Em báo rõ để mình yên tâm: dữ liệu quảng cáo của mình KHÔNG bị xóa. [TEN KHACH] vẫn mở phần mềm để xem và xuất báo cáo bình thường; chỉ các tính năng trả phí và giám sát nền đang tạm dừng.

Khi nào muốn dùng tiếp, mình chỉ cần gia hạn: chuyển khoản như trước, em xác nhận tiền về rồi gửi file license mới, dán vào trang "Bản quyền" là mọi thứ chạy lại. Cần hỗ trợ gì thêm cứ nhắn em qua [KENH HO TRO].
```

---

## Mẫu 6 — Hỗ trợ đổi máy

```
Chào [TEN KHACH], license được gắn với từng máy qua mã máy nên khi đổi máy mình cần cấp lại file mới — file cũ sẽ không kích hoạt được trên máy mới ạ.

[TEN KHACH] làm giúp em các bước sau:
1. Trên máy MỚI: cài LHM Ads AI, vào trang "Bản quyền", bấm "Sao chép mã máy" và gửi mã mới cho em.
2. Nếu cần mang dữ liệu sang: trên máy CŨ, vào "Bản quyền → Kiểm tra sẵn sàng & Bảo vệ dữ liệu" để xuất bản sao lưu có mã hóa, và giữ kỹ mật khẩu sao lưu (mật khẩu này chỉ mình biết, em không khôi phục hộ được).
3. Em ký license cho mã máy mới theo chính sách đổi máy: [CHINH SACH DOI MAY — CHU SAN PHAM QUYET DINH: SO LAN MIEN PHI / PHI NEU CO / CACH TINH NGAY CON LAI], rồi gửi file mới để mình dán kích hoạt như lần đầu.

Lưu ý: license không tự chuyển theo dữ liệu sao lưu, nên cứ gửi mã máy mới cho em trước là chắc chắn nhất.
```
