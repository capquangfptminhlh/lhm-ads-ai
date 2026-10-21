# Bảng giá — MẪU (chưa phải giá chính thức)

> **Tài liệu nội bộ.** Đây là khung bảng giá để chủ sản phẩm điền. Mọi con số trong bảng đều là `[ ]` chờ quyết định — **chưa có giá nào được chốt**, và không được dùng bảng này để báo giá khách khi các ô còn trống. Điền giá xong phải đồng bộ vào Mẫu 1 và Mẫu 2 trong `MAU-TIN-NHAN.md`.

## Bảng giá theo gói

| Hạng mục | Pilot | Pro | Agency |
|---|---|---|---|
| Đối tượng gợi ý | Cá nhân / shop nhỏ dùng thử nghiêm túc trên 1 máy | Người chạy quảng cáo chuyên nghiệp, 1 máy chính | Team / agency nhiều máy |
| Số máy (mã máy) | 1 | [ ] | [ ] |
| Số tài khoản Ads kết nối | [ ] | [ ] | [ ] |
| Giám sát nền (đọc báo cáo, cần máy bật + có Internet) | Có | Có | Có |
| Trợ lý phân tích AI | [ ] | [ ] | [ ] |
| Hỗ trợ đổi máy | Theo chính sách đổi máy — xem FAQ | [ ] | [ ] |
| Kênh hỗ trợ / thời gian phản hồi | [ ] | [ ] | [ ] |
| Giá 30 ngày | [ ] đ | [ ] đ | [ ] đ |
| Giá 90 ngày (nếu bán) | [ ] đ | [ ] đ | [ ] đ |
| Giá 12 tháng (nếu bán) | [ ] đ | [ ] đ | [ ] đ |
| Giảm giá khi trả dài hạn | [ ] % | [ ] % | [ ] % |

> License ký theo gói `monthly` và số ngày (`--days`) trong `tools/license_issuer.py`; tên gói thương mại (Pilot/Pro/Agency) là cách gọi bán hàng — khi ký, ghi chú gói vào mã khách/sổ theo dõi để đối chiếu (xem `QUY-TRINH-BAN.md`). Nếu một gói cho nhiều máy, mỗi máy vẫn là một mã khách riêng trong sổ vì một mã khách chỉ gắn một mã máy.

## Chính sách đi kèm cần chốt cùng bảng giá

- [ ] Thời hạn license mặc định cho đợt pilot: [ ] ngày (hiện quy trình bán dùng 30 ngày).
- [ ] Có bán gói dùng thử miễn phí (`trial` trong sổ) không, và thử trong bao lâu: [ ].
- [ ] Chính sách đổi máy: số lần miễn phí / phí mỗi lần — đồng bộ với FAQ câu 8.
- [ ] Chính sách hoàn tiền — đồng bộ với FAQ câu 10.
- [ ] Ưu đãi cho khách pilot đầu tiên (nếu có): [ ] — ghi rõ điều kiện và ngày kết thúc ưu đãi để tránh hứa miệng không kiểm soát được.

## Gợi ý cho chủ sản phẩm khi neo giá pilot (chỉ là gợi ý, không phải quyết định)

1. **Pilot là đợt bán để học, không phải để tối đa doanh thu.** Mục tiêu của pilot: có khách thật trả tiền thật, chạy trên máy thật, và lộ ra các lỗi vận hành (kích hoạt, gia hạn, đổi máy, hỗ trợ). Giá pilot nên đủ thấp để khách quyết định nhanh, nhưng **phải thu tiền thật** — khách miễn phí không cho tín hiệu về giá trị và thường không phản hồi lỗi nghiêm túc.
2. **Neo giá vào thời gian tiết kiệm được, không vào tính năng.** Khách chạy quảng cáo so giá với "mỗi tuần tôi mất bao nhiêu giờ đọc báo cáo tay" hoặc với lương một nhân sự part-time phụ trách theo dõi tài khoản — đó là cái neo tự nhiên của sản phẩm này. Tránh neo vào "số tính năng" vì đối thủ luôn liệt kê dài hơn.
3. **Một mức giá pilot duy nhất, ít lựa chọn.** Đợt pilot chỉ nên có 1 gói (Pilot) và tối đa 2 kỳ hạn (30 ngày / 90 ngày). Nhiều gói quá sớm khiến khách phân vân và khiến sổ theo dõi phức tạp khi chưa có nhiều khách. Pro/Agency chỉ mở khi pilot đã có khách gia hạn thật.
4. **Chiết khấu kỳ hạn dài phải đổi lấy cam kết.** Giảm giá cho 90 ngày/12 tháng chỉ hợp lý khi khách trả trước toàn bộ và chấp nhận chính sách hoàn tiền đã chốt; đừng giảm giá kỳ hạn dài trong khi chính sách hoàn tiền còn để trống.
5. **Công bố trước là giá pilot sẽ thay đổi.** Nói rõ với khách pilot: giá này dành cho đợt đầu, giá chính thức khi ra mắt có thể khác, và [CHU SAN PHAM QUYET DINH: khách pilot được giữ giá cũ bao lâu khi gia hạn — ví dụ giữ giá pilot cho 1 lần gia hạn đầu]. Hứa miệng "giá này mãi mãi" sẽ khóa tay khi cần tăng giá.
6. **Đừng bán dưới ngưỡng khiến hỗ trợ thành lỗ.** Mỗi khách phát sinh việc thật: hướng dẫn lấy mã máy, đối chiếu chuyển khoản, ký license, nhắc gia hạn, hỗ trợ đổi máy — tất cả làm tay. Nếu giá một tháng thấp hơn chi phí thời gian hỗ trợ trung bình cho một khách, đợt pilot sẽ không bền dù bán được nhiều.
7. **Không cam kết tính năng để biện minh cho giá.** Giá phải đứng được trên khả năng hiện tại của phần mềm (chạy tại máy khách, giám sát chỉ khi máy bật, duyệt tay mọi thay đổi quảng cáo). Hứa tính năng chưa có (xác nhận tiền tự động, chạy 24/7 trên mây, thu hồi license từ xa) để đẩy giá cao hơn sẽ thành nợ hỗ trợ và rủi ro hoàn tiền về sau.
