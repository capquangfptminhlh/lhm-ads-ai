# Câu hỏi thường gặp — LHM Ads AI (dành cho khách hàng)

> Ghi chú cho bên bán (không gửi phần này cho khách): các câu trả lời dưới đây chỉ nêu đúng khả năng hiện tại của phần mềm. Những chỗ ghi **[CHU SAN PHAM QUYET DINH]** là chính sách bán hàng chưa chốt — chủ sản phẩm phải quyết định và điền xong mới được gửi bản FAQ này cho khách. Không tự hứa thêm ngoài văn bản đã chốt.

---

### 1. Một license dùng chung cho nhiều máy được không?

Không. Mỗi license gắn với **một máy** thông qua mã máy (Device ID) mà phần mềm hiển thị ở trang **Bản quyền**. Muốn dùng thêm máy, bạn cần đăng ký thêm license cho máy đó. File license gửi cho máy này sẽ không kích hoạt được trên máy khác.

### 2. Vì sao phần mềm cần mã máy? Mã máy có chứa dữ liệu cá nhân không?

Mã máy là một mã định danh của thiết bị, dùng để bên bán ký license đúng cho máy của bạn và chống phát hành tràn lan. Khi mua, bạn chỉ cần gửi mã máy — **không bao giờ phải gửi token quảng cáo, mật khẩu tài khoản Ads hay thông tin ngân hàng cho bên bán**. Dữ liệu quảng cáo và token API lưu trên chính máy của bạn, không chuyển về máy chủ của bên bán.

### 3. Hết hạn license thì dữ liệu của tôi có mất không?

Không. Hết hạn license **không xóa dữ liệu**. Bạn vẫn mở phần mềm để xem và xuất báo cáo bình thường; chỉ các tính năng trả phí (bao gồm giám sát nền) tạm dừng cho tới khi bạn gia hạn. Bạn cũng có thể tự xuất bản sao lưu dữ liệu có mã hóa ngay trong phần mềm (trang Bản quyền → Kiểm tra sẵn sàng & Bảo vệ dữ liệu).

### 4. Tôi thanh toán bằng cách nào?

Hiện tại thanh toán bằng **chuyển khoản vào tài khoản ngân hàng của bên bán**. Quy trình:

1. Bạn gửi mã máy cho bên bán.
2. Bên bán gửi thông tin chuyển khoản kèm cú pháp nội dung chuyển tiền (có mã khách của bạn để đối chiếu).
3. Bên bán **tự kiểm tra tiền về** trên tài khoản của mình — bước này làm thủ công, không phải hệ thống tự động, nên có thể cần một khoảng thời gian trong giờ làm việc: **[CHU SAN PHAM QUYET DINH: thời gian xử lý tối đa cam kết, ví dụ "tối đa 4 giờ làm việc"]**.
4. Tiền về tài khoản, bên bán ký file license và gửi cho bạn; bạn dán vào trang Bản quyền để kích hoạt, không cần thao tác gì thêm.

Phần mềm không lưu thông tin thẻ/tài khoản ngân hàng của bạn và bên bán không yêu cầu bạn cung cấp các thông tin đó.

### 5. Gia hạn như thế nào? Gia hạn sớm có bị mất ngày không?

Bạn liên hệ bên bán trước khi hết hạn, chuyển khoản như lần đầu; bên bán xác nhận tiền về rồi gửi file license gia hạn. **Gia hạn sớm được cộng dồn ngày** vào thời hạn còn lại — bạn không mất ngày nào. Bên bán có theo dõi hạn dùng và sẽ chủ động nhắc bạn trước khi hết hạn **[CHU SAN PHAM QUYET DINH: các mốc nhắc — hiện mẫu tin nhắn có mốc 7 ngày và 1 ngày]**.

### 6. Tính năng giám sát nền có chạy khi tôi tắt máy không?

Không. Giám sát nền chỉ **đọc** báo cáo quảng cáo qua API và chỉ hoạt động **khi máy của bạn đang bật, đã đăng nhập Windows và có Internet**. Tắt máy, mất điện hoặc mất mạng thì quãng đó không có giám sát; khi máy chạy lại, phần mềm tiếp tục đọc như bình thường. Đây là phần mềm cài trên máy của bạn, không phải dịch vụ đám mây chạy thay bạn 24/7.

### 7. Phần mềm có tự động thay đổi ngân sách hay giá thầu của tôi không?

Không tự ý. Các thay đổi đối với chiến dịch luôn cần người dùng phê duyệt theo từng kế hoạch; giám sát nền chỉ đọc dữ liệu và cảnh báo.

### 8. Tôi đổi máy tính thì sao?

Bạn cài phần mềm trên máy mới, lấy mã máy mới ở trang Bản quyền và gửi cho bên bán để được cấp lại license theo mã máy mới; dữ liệu thì bạn tự chuyển bằng bản sao lưu có mã hóa xuất từ máy cũ. Chi tiết chính sách đổi máy: **[CHU SAN PHAM QUYET DINH: số lần đổi máy miễn phí trong một kỳ thuê bao, phí đổi máy nếu vượt, và cách tính số ngày còn lại khi cấp lại]**.

### 9. Nếu máy bị chỉnh sai giờ thì có dùng được không?

Phần mềm có kiểm tra chống chỉnh lùi đồng hồ. Nếu đồng hồ Windows bị chỉnh lùi quá 5 phút, tính năng trả phí sẽ tạm bị chặn; bạn chỉ cần đồng bộ lại đúng giờ Windows là dùng tiếp bình thường.

### 10. Tôi muốn hoàn tiền thì sao?

**[CHU SAN PHAM QUYET DINH — chủ sản phẩm điền chính sách hoàn tiền chính thức vào đây trước khi gửi FAQ cho khách. Các điểm cần chốt: (a) có hoàn tiền hay không; (b) thời hạn được yêu cầu hoàn tiền kể từ ngày kích hoạt; (c) các trường hợp được/không được hoàn (ví dụ: chưa kích hoạt lần nào, lỗi kỹ thuật từ phía phần mềm không khắc phục được); (d) thời gian xử lý hoàn tiền; (e) cách gửi yêu cầu.]**

### 11. Tôi cần hóa đơn thì sao?

**[CHU SAN PHAM QUYET DINH: có xuất hóa đơn điện tử hay không, xuất qua nhà cung cấp nào và khách cần cung cấp thông tin gì. Lưu ý nội bộ: hệ thống hiện chưa có xuất hóa đơn tự động — xem docs/COMMERCIAL_LICENSE.md.]**

### 12. Phần mềm có cập nhật tự động không? Khi có bản mới tôi làm gì?

Hiện phần mềm **chưa có cơ chế tự cập nhật có ký số**. Khi có bản cập nhật, bên bán sẽ thông báo và hướng dẫn cách cài bản mới qua kênh hỗ trợ: **[CHU SAN PHAM QUYET DINH: kênh thông báo cập nhật và cam kết hỗ trợ phiên bản cũ trong bao lâu]**.

### 13. Bên bán có tắt license của tôi từ xa được không?

Không. License là file ký số hoạt động ngoại tuyến trên máy của bạn; bên bán **không có cơ chế thu hồi hay tắt license từ xa**. License của bạn dùng được tới đúng ngày hết hạn ghi trong file.

### 14. Tôi liên hệ hỗ trợ ở đâu và trong bao lâu thì được trả lời?

**[CHU SAN PHAM QUYET DINH: kênh hỗ trợ chính thức (Zalo/Messenger/email), giờ hỗ trợ, và thời gian phản hồi cam kết.]**

### 15. Phần mềm có tự sửa quảng cáo của tôi không?

Không. Tính năng tư vấn tối ưu ("Vòng lặp Tối ưu") chỉ **đọc** số liệu chiến dịch qua API, phân tích và đưa ra đề xuất kèm lý do và các bước gợi ý. Phần mềm **không tự thay đổi** giá thầu, ngân sách hay bất kỳ cấu hình nào trong tài khoản quảng cáo của bạn. Mọi thay đổi thật đều do chính bạn xem xét và thực hiện thủ công trong Google Ads / Meta Ads Manager. Nếu bạn không đồng ý với một đề xuất, bạn cứ bỏ qua — không có gì tự diễn ra sau lưng bạn.

### 16. Phần mềm này khác gì các công cụ tối ưu miễn phí hay gợi ý có sẵn của Google/Meta?

Các chiến thuật tối ưu (chỉnh giá thầu theo bước nhỏ, gộp chiến dịch phân mảnh, kiểm tra tracking trước...) là kiến thức chung của ngành — chúng tôi không nhận đó là bí quyết riêng. Khác biệt của LHM nằm ở **cơ chế chạy trên dữ liệu của chính tài khoản bạn**:

- **Hồ sơ nền riêng từng tài khoản:** phần mềm lưu các kỳ số liệu và tính CPA/ROAS trung vị của *từng chiến dịch của bạn*, nên phát hiện được khi một chiến dịch "đang xấu đi so với chính nó" — kể cả khi con số đó vẫn nằm trong ngưỡng "bình thường" chung của ngành.
- **Kiểm chứng kết quả sau 7 ngày trở lên:** đề xuất không kết thúc ở lúc đưa ra. Sau khi bạn thực hiện thay đổi, phần mềm đo lại ở các kỳ quét sau và đưa ra phán quyết rõ ràng: số liệu *cải thiện*, *xấu đi*, *không đổi* hay *chưa đủ dữ liệu* (biến động trong ±5% được coi là nhiễu, không vội kết luận).
- **Không tự mâu thuẫn:** trong cùng một lần quét, phần mềm không bao giờ vừa khuyên mở rộng vừa khuyên cắt giảm cùng một chiến dịch; trường hợp xung đột, gợi ý mở rộng bị chặn và cảnh báo nghiêm trọng hơn được ưu tiên.
- **So với target thật trên nền tảng:** phần mềm đọc được target tCPA/tROAS bạn đã đặt trong Google Ads / Meta và so hiệu quả thực tế với chính các con số đó — kể cả khi bạn chưa đặt mục tiêu nào trong phần mềm.

Trung thực về giới hạn: phần mềm chỉ nhìn số liệu tổng hợp **cấp chiến dịch** trong 7 ngày gần nhất. Nó không thấy cụm từ tìm kiếm, từng mẫu quảng cáo, phân rã theo đối tượng/thiết bị/giờ, cũng không thấy target ở cấp nhóm quảng cáo (ad set) trên Meta — các lớp đó phần mềm chỉ gợi ý dạng checklist để bạn tự kiểm tra trong trình quản lý quảng cáo.

### 17. Dùng phần mềm có cam kết tăng ROAS hay giảm CPA không?

Không. Chúng tôi **không cam kết kết quả quảng cáo** dưới bất kỳ hình thức nào — hiệu quả phụ thuộc vào sản phẩm, thị trường, ngân sách, trang đích và cách bạn vận hành, những yếu tố nằm ngoài phần mềm.

Cái phần mềm làm được và làm rõ ràng là: khi bạn thực hiện một thay đổi theo đề xuất, hệ thống sẽ đo lại và **phán quyết trung thực** thay đổi đó đi kèm với cải thiện, xấu đi hay chưa đủ dữ liệu để kết luận (xem câu 16). Nói cách khác, bạn nhìn thấy đề xuất nào từng gắn với kết quả tốt trên chính tài khoản của mình, thay vì phải tin lời hứa. Mọi đề xuất đều kèm rào chắn an toàn: chỉnh từng bước tối đa 20%, mỗi lần chỉ đổi một biến, tôn trọng giai đoạn học của nền tảng, và quyết định cuối cùng luôn là của bạn.
