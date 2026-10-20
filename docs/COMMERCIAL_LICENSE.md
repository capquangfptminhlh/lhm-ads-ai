# LHM Ads AI — thương mại bản Windows, không gom Ads lên VPS

## Ranh giới thực tế

- Phần mềm `.exe` chạy trên máy mỗi khách; API Google Ads, Meta Ads và OpenRouter (nếu bật) kết nối HTTPS trực tiếp ra Internet.
- Không có MCP hoặc kho token quảng cáo tập trung. **Bản quyền vận hành offline**, không cần VPS hay máy chủ thanh toán để kiểm tra quyền.
- Mỗi máy được cấp một **Device ID** riêng. License JSON ký Ed25519; app chỉ chứa **public key**, bí mật phát hành ở công cụ bên bán.
- Mặc định chưa có giấy phép: **không chạy collector nền**, không duyệt thao tác có thể thay đổi quảng cáo thật. Có thể đăng nhập/xem dữ liệu/xuất báo cáo của chính khách để tránh khóa dữ liệu.
- Giấy phép hết hạn khóa tác vụ trả phí, không xóa dữ liệu hay token, có thể gia hạn ngay. Ngày hết hạn tính theo UTC.

## Quy trình bán và gia hạn tháng

1. Khách tải EXE, tự tạo Admin, vào **Cài đặt → Bản quyền thuê bao theo tháng**, gửi **Mã máy** cho bên bán (không gửi mật khẩu/token Google/Meta).
2. Thu phí theo chính sách bán hàng của chủ dự án. **Chưa tích hợp cổng thanh toán và hóa đơn tự động**.
3. Trên máy bên bán **khác máy khách**, bảo quản riêng khóa Ed25519 `vendor-private-key.pem`:

   ```sh
   python tools/license_issuer.py sign --private /safe/vendor-private-key.pem \
     --device <MA_MAY_KHACH> --days 30 --out customer-2026-11.json
   ```

4. Gửi **file JSON đã ký** cho khách (Zalo/email). Khách mở và dán nội dung vào màn hình kích hoạt; máy tự xác minh chữ ký, không cần Internet.
5. Trước khi hết hạn, phát hành giấy phép gia hạn:

   ```sh
   python tools/license_issuer.py sign --private /safe/vendor-private-key.pem \
     --device <MA_MAY_KHACH> --days 30 --renew-from customer-2026-11.json \
     --out customer-2026-12.json
   ```

   Nếu khách gia hạn sớm, ngày còn lại được cộng dồn. Mỗi lần cấp mới sẽ có license ID mới.

**Cực kỳ quan trọng:** khóa **private** không bao giờ upload lên GitHub, gửi cho khách, nhúng EXE hoặc đặt trong website. Sao lưu offline mã hóa ở ít nhất 2 nơi; mất khóa đồng nghĩa không thể gia hạn giấy phép cho EXE dùng public key hiện tại. Tránh cấp lại key công khai khác khi đã có khách.

## Giám sát nền

- Đăng nhập Windows, bật cấu hình giám sát và chọn chu kỳ 15–240 phút. Bấm **Chạy nền khi đăng nhập Windows** để tự đăng ký HKCU Run (không đòi quyền Admin máy).
- Tác nhân `--agent-only` chỉ đọc API, không tạo inbound server, không gọi OpenRouter và không thay đổi bid/budget. Windows vẫn có thể suspend tác nhân khi sleep.
- Dữ liệu giám sát hiện là báo cáo **7 ngày gần nhất**, chưa phải realtime conversions/ROAS/campaign-level. Đọc 20 tài khoản mỗi chu kỳ, ưu tiên tài khoản lâu chưa kiểm tra.
- Tắt giám sát trong Cài đặt để xóa HKCU Run. Dừng ngay mọi tiến trình nền hiện còn chạy nếu muốn ngừng tức thì. Emergency Stop hoàn chỉnh chưa được triển khai.

## Chính sách giá / thuê bao

Các gói và giá bán chưa được người sở hữu chỉ định. Đề xuất gói theo **số lượng tài khoản Ads**, số lượt OpenRouter, quyền Auto-limited và số máy được cấp; cấu hình đơn giá sau. Không tự áp mức tiền cụ thể.

## Giới hạn bảo mật trước khi thương mại rộng rãi

- Không nên quảng cáo là DRM không thể bẻ khóa. Một EXE Python offline vẫn có thể bị chỉnh sửa, đồng hồ Windows có thể bị thay đổi; cần bổ sung chống tua lùi đồng hồ, xác minh thời gian an toàn, ký số Authenticode và bảo vệ khóa bằng DPAPI.
- **Private key ký giấy phép là tài sản quan trọng nhất của bên bán.** Khóa MASTER_KEY của khách hiện được lưu cục bộ và chưa áp dụng DPAPI hoàn chỉnh; máy bị nhiễm mã độc có thể lộ dữ liệu.
- Chưa triển khai cổng thanh toán, quản lý công nợ, gia hạn tự động, mã giảm giá, chuyển máy, thu hồi license offline, cập nhật EXE đã ký số.
- Chưa có write API Google bid/budget/strategy, Meta bid/budget hoặc khả năng AI tự tối ưu. Chưa thử quyền OAuth trên tài khoản quảng cáo thực tế. **Không được cam kết tối ưu tự động 24/7 trước khi các phân hệ này đạt nghiệm thu.**
