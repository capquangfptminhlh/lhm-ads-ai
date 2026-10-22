# Sao lưu và khôi phục sổ khách hàng LHM Ads AI

Bản Windows Vendor License Manager có hai nút Sao lưu mã hóa và Khôi phục. Công cụ sử dụng AES-256-GCM và Scrypt (N=32768) tạo file có đuôi .lhmvault.

**File .lhmvault chứa:** snapshot SQLite nhất quán, public key Ed25519 bên bán và mọi license JSON đã ghi sổ. Mỗi license được đối chiếu chữ ký số Ed25519, mã máy, hạn sử dụng và hash với sổ trước khi sao lưu và sau khi khôi phục.

**File .lhmvault KHÔNG chứa private key ký license.** Chủ phần mềm phải sao lưu riêng private key đã mã hóa nằm trong thư mục LOCALAPPDATA/LHMAdsAI-Vendor/keys và giữ mật khẩu riêng ở nơi an toàn ngoại tuyến. Mất private key gốc đồng nghĩa không thể ký/gia hạn với bộ khóa cũ. Không tự tạo khóa mới khi đã có khách.

## Sao lưu từ giao diện Windows

Mở ứng dụng Vendor License Manager, bấm Sao lưu mã hóa, chọn vị trí ngoài thư mục cài đặt, rồi nhập mật khẩu sao lưu MỚI ít nhất 16 ký tự và xác nhận lần hai. Cất hai bản sao lưu trên hai phương tiện khác nhau. Không gửi file cho khách, không tải lên kho mã nguồn hoặc dịch vụ không được phép.

Nếu một license đã ghi sổ bị mất file JSON hoặc chữ ký sai, tác vụ sẽ từ chối sao lưu; không cố tạo backup thiếu dữ liệu.

## Khôi phục từ giao diện Windows

Chuẩn bị lại public key GỐC của bên bán trên máy; mở Vendor License Manager, bấm Khôi phục, chọn file .lhmvault và thư mục CHA đích nằm ngoài kho bên bán đang dùng, sau đó nhập mật khẩu sao lưu. Dữ liệu sẽ được giải mã, kiểm tra SQLite/giấy phép, rồi khôi phục dưới một thư mục MỚI tên dạng LHMAdsAI-Vendor-RESTORED-YYYYmmdd-HHMMSS.

Nút Khôi phục **không thay đổi dữ liệu đang dùng**. Sau khi kiểm chứng, cần có private key gốc, đối soát sổ và chuyển dữ liệu theo hướng dẫn hỗ trợ trước khi dùng làm kho chính. Không sao chép dữ liệu đè trong lúc chương trình đang mở.

## CLI dành cho chủ phần mềm

Chạy lệnh trong checkout của repo. Cả hai lệnh hỏi mật khẩu ẩn, tuyệt đối không nhập mật khẩu dưới dạng tham số dòng lệnh:

    python tools/vendor_backup.py backup --db D:\Seller\customers.sqlite3 --license-dir D:\Seller\issued-licenses --public D:\Seller\keys\vendor-public.b64 --out E:\Backup\vendor-20261022.lhmvault
    python tools/vendor_backup.py restore --vault E:\Backup\vendor-20261022.lhmvault --public D:\Seller\keys\vendor-public.b64 --target E:\Recovery\LHMVendorRestored

Đường dẫn restore PHẢI chưa tồn tại và có thư mục cha sẵn. Sai mật khẩu, sai public key hoặc backup bị thay đổi sẽ không tạo sổ đã khôi phục. Không có tính năng ghi đè sổ đang vận hành.

## Những gì chưa được sao lưu

Kho này **không** chứa Ed25519 private key, mật khẩu khóa ký, merchant PayOS, thông tin phát hành hóa đơn điện tử, GitHub secrets, token Google/Meta Ads, hay dữ liệu khách nằm trên máy khách. Từng loại phải có quy trình sao lưu riêng, được phân quyền và mã hóa thích hợp.

Quy trình sao lưu cũ bằng vendor_ledger.py backup vẫn tạo SQLite thuần không mã hóa, chỉ phù hợp bảo trì nội bộ trên ổ đã mã hóa. Nên sử dụng bản .lhmvault mặc định của GUI để dự phòng vận hành.
