# LHM Ads AI — Kiểm tra bản cập nhật đã ký (`tools/update_check.py`)

## Trạng thái: đã có CLI, đang TẮT theo mặc định (dormant)

Bộ kiểm chứng manifest cập nhật ký Ed25519 đã có sẵn trong code
(`ads_core/updater.py`) nhưng **cố ý chỉ kiểm chứng ngoại tuyến** — nó
không tải gì, không chạm mạng, không cài đặt gì. File này mô tả công cụ
phía bên bán `tools/update_check.py`: mảnh ghép "người gọi" duy nhất còn
thiếu, chạy trên máy bên bán để **tải manifest đã ký từ URL của chính bên
bán và đưa cho updater kiểm chứng**.

Công cụ này **chỉ báo cáo**. Nó không tải bản cài đặt (dù `download_url`
nằm trong manifest), không cài đặt, không thực thi. Cập nhật cho khách
vẫn là bước thủ công riêng, giống hệt nguyên tắc cấp license thủ
công/ngoại tuyến.

Chưa cấu hình thì công cụ ở trạng thái chờ: in rõ "chưa được kích hoạt",
thoát mã **2** và **không gọi mạng**. Hiện tại chủ phần mềm **chưa có**
cặp khóa ký cập nhật riêng và **chưa có** máy chủ manifest — vì vậy trạng
thái dormant là trạng thái đúng ở thời điểm này, không phải lỗi.

## Cách dùng

```powershell
# Chưa cấu hình (trạng thái hiện tại): báo dormant, thoát mã 2
python tools/update_check.py --current 1.2.3

# Đã cấu hình bằng cờ lệnh
python tools/update_check.py --current 1.2.3 `
  --url https://<miền-của-bạn>/lhm-update.json `
  --pubkey <hex-64-ký-tự | base64 | đường-dẫn-file-khóa>

# Hoặc bằng biến môi trường trên máy bên bán (không ghi vào repo)
$env:LHM_UPDATE_MANIFEST_URL = 'https://<miền-của-bạn>/lhm-update.json'
$env:LHM_UPDATE_PUBKEY = '<hex 64 ký tự của khóa công khai cập nhật>'
python tools/update_check.py --current 1.2.3
```

| Tham số | Biến môi trường | Ý nghĩa |
|---|---|---|
| `--current` (bắt buộc) | — | Phiên bản đang dùng, semver `X.Y.Z` |
| `--url` | `LHM_UPDATE_MANIFEST_URL` | URL manifest đã ký, hoặc đường dẫn file cục bộ để kiểm thử ngoại tuyến |
| `--pubkey` | `LHM_UPDATE_PUBKEY` | Khóa công khai Ed25519 của nhà phát hành cập nhật: hex 64 ký tự (32 byte thô), base64 của 32 byte thô, hoặc file chứa một trong hai dạng |

Cờ lệnh ưu tiên hơn biến môi trường. Để cấu hình không bị lệch với app,
biến gốc của `ads_core.updater` là `LHM_UPDATE_PUBLIC_KEY` (dạng base64)
cũng được CLI chấp nhận làm nguồn dự phòng cho khóa công khai khi
`LHM_UPDATE_PUBKEY` chưa đặt.

## Định dạng manifest trên máy chủ

URL chỉ cần phục vụ **một file JSON tĩnh**:

```json
{
  "manifest": {
    "version": "1.3.0",
    "download_url": "https://<miền-của-bạn>/LHM-Ads-AI-1.3.0-setup.exe",
    "sha256": "<64 ký tự hex thường của file cài đặt>",
    "notes": "Ghi chú phát hành hiển thị cho bên bán/khách.",
    "issued_at": 1760000000
  },
  "signature": "<base64: chữ ký Ed25519 tách rời>"
}
```

Chữ ký phủ lên **JSON canonical của riêng đối tượng `manifest`** — cùng
quy ước với license: `json.dumps(..., ensure_ascii=True, sort_keys=True,
separators=(',', ':'))`, xem `ads_core.updater.canonical_manifest`.
Manifest sai bất kỳ trường nào (thừa/thiếu trường, version không phải
semver `X.Y.Z`, `download_url` không phải https, `sha256` không đúng 64
hex thường, `issued_at` không phải epoch dương) đều bị updater từ chối
toàn bộ — không có kiểm chứng "một phần".

**Khóa riêng ký cập nhật** (cặp khóa riêng cho việc cập nhật, khác khóa
ký license) chỉ tồn tại trên máy ngoại tuyến của chủ phần mềm: không
nằm trong repo, không nằm trong EXE, không nằm trên máy chủ manifest.
Quy trình phát hành một bản mới:

1. Build và ký bản cài đặt theo `docs/RELEASE_CHECKLIST.md`, tính SHA256
   **sau khi ký**.
2. Trên máy ngoại tuyến: soạn manifest, ký bằng khóa riêng cập nhật, tạo
   file JSON đúng định dạng trên.
3. Đăng file JSON đó lên URL đã cấu hình. Xong — các máy chạy
   `update_check.py` sẽ thấy bản mới; việc tải/cài vẫn do người thực hiện.

## Kết quả và mã thoát

| Mã thoát | Tiền tố in ra | Ý nghĩa |
|---|---|---|
| 2 | `Kiểm tra cập nhật chưa được kích hoạt: ...` | Dormant: thiếu URL và/hoặc khóa. Không có lần gọi mạng nào. |
| 0 | `update_available: Có bản mới ...` | Manifest ký hợp lệ và mới hơn `--current`. In kèm phiên bản mới, địa chỉ tải, SHA256 và ghi chú để đối chiếu thủ công. |
| 0 | `up_to_date: Đang dùng bản mới nhất ...` | Manifest ký hợp lệ nhưng không mới hơn bản đang dùng. |
| 1 | `invalid: Manifest không hợp lệ: ...` | Tải lỗi, phong bì sai định dạng, chữ ký sai, manifest sai trường, hoặc khóa công khai không đọc được. **Không tin bất kỳ thông tin nào trong manifest đó.** |

## Kiểm thử ngoại tuyến bằng file cục bộ

`--url` chấp nhận đường dẫn file: bên bán kiểm chứng được file JSON sẽ
đăng lên máy chủ (đúng chữ ký, đúng phiên bản) trước khi đăng thật, hoàn
toàn không cần mạng:

```powershell
python tools/update_check.py --current 1.2.3 --url .\lhm-update.json --pubkey .\update-public.txt
```

## Ranh giới cố ý giữ nguyên

- CLI **không tự tải bản cài đặt và không tự cài đặt**: chữ ký manifest
  chỉ chứng minh "thông báo bản mới này là của nhà phát hành", còn file
  cài đặt vẫn phải được đối chiếu SHA256 và ký Authenticode theo quy
  trình phát hành hiện tại.
- Không có URL manifest hay khóa nào được ghi sẵn trong code: mọi cấu
  hình đều do chủ phần mềm tự đặt trên máy của mình.
- Việc tạo cặp khóa ký cập nhật và dựng máy chủ manifest là việc phía
  chủ phần mềm (ceremony khóa + hạ tầng), không phải việc của code này.
