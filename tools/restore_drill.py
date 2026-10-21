"""Diễn tập sao lưu → khôi phục end-to-end bằng CHÍNH code của LHM Ads AI.

Chạy:  python tools/restore_drill.py
Thoát: 0 nếu mọi kiểm tra PASS, 1 nếu có FAIL.

Drill này gọi đúng các hàm mà endpoint desktop /api/desktop/backup/export
và công cụ hỗ trợ tools/customer_restore.py sử dụng
(ads_core.secure_backup.sqlite_snapshot / encrypt_snapshot /
restore_into_empty_directory). Lớp cổng desktop (đăng nhập admin + loopback
+ desktop mode) không chạy trong drill headless này — phần đó đã có test
riêng trong tests/test_secure_backup.py. Không có crypto nào được viết lại
ở đây.
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import sys
import tempfile

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

DRILL_EMAIL = "drill-admin@local.test"
DRILL_USER_PASSWORD = "drill_login_password_2026"
DRILL_PASSPHRASE = "drill backup passphrase 2026"
DRILL_MASTER_KEY = base64.b64encode(b"D" * 32).decode()


def _tables(db_path: Path) -> dict[str, int]:
    with sqlite3.connect(db_path) as db:
        names = [r[0] for r in db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' "
            "AND name NOT LIKE 'sqlite_%' ORDER BY name")]
        return {n: db.execute(f'SELECT COUNT(*) FROM "{n}"').fetchone()[0]
                for n in names}


def run_drill(base: Path) -> list[tuple[str, bool, str]]:
    """Trả về danh sách (nhãn, đạt?, chi tiết). Không raise cho lỗi kỳ vọng."""
    checks: list[tuple[str, bool, str]] = []

    def check(label: str, ok: bool, detail: str = ""):
        checks.append((label, bool(ok), detail))

    from ads_core.db import DB_PATH, connection, init_db
    from ads_core.security import hash_password, master_key, verify_password
    from ads_core import secure_backup

    # --- (a) Thư mục dữ liệu nguồn + DB seed bằng hàm init của dự án -------
    source_dir = base / "may-goc"
    db_file = source_dir / "data" / "lhm-ads.sqlite3"
    os.environ["DB_PATH"] = str(db_file)
    os.environ["MASTER_KEY"] = DRILL_MASTER_KEY
    init_db()
    with connection() as db:
        db.execute(
            "INSERT INTO users(email,password_hash,org_id,role) VALUES (?,?,?,?)",
            (DRILL_EMAIL, hash_password(DRILL_USER_PASSWORD), "drill-org", "admin"))
        db.execute(
            "INSERT INTO accounts(org_id,platform,label,external_id,currency) "
            "VALUES (?,?,?,?,?)",
            ("drill-org", "demo", "Tài khoản demo diễn tập", "demo-drill-1", "VND"))
    check("Tạo dữ liệu nguồn (1 admin + 1 tài khoản demo)", db_file.is_file(),
          str(db_file))
    source_counts = _tables(db_file)

    # --- (b) Xuất backup mã hoá — đúng 2 hàm endpoint desktop gọi ----------
    backup_file = base / "lhm-ads-backup-drill.lhmbak"
    try:
        snapshot = secure_backup.sqlite_snapshot(Path(DB_PATH()))
        blob = secure_backup.encrypt_snapshot(snapshot, master_key(), DRILL_PASSPHRASE)
        backup_file.write_bytes(blob)
        check("Xuất backup .lhmbak mã hoá (sqlite_snapshot + encrypt_snapshot)",
              blob.startswith(secure_backup.MAGIC), f"{len(blob)} bytes")
    except Exception as exc:  # noqa: BLE001 - drill phải báo FAIL, không sập
        check("Xuất backup .lhmbak mã hoá", False, f"{type(exc).__name__}: {exc}")
        return checks

    # --- (c) Khôi phục vào thư mục trống thứ hai ---------------------------
    restore_dir = base / "may-moi"
    try:
        result = secure_backup.restore_into_empty_directory(
            backup_file.read_bytes(), DRILL_PASSPHRASE, restore_dir)
        check("Khôi phục vào thư mục trống (restore_into_empty_directory)",
              result.get("restored") is True, str(result))
    except Exception as exc:  # noqa: BLE001
        check("Khôi phục vào thư mục trống", False, f"{type(exc).__name__}: {exc}")
        return checks

    restored_db = restore_dir / "data" / "lhm-ads.sqlite3"
    if not restored_db.is_file():
        check("File DB sau khôi phục tồn tại", False, str(restored_db))
        return checks

    # --- (d) Kiểm chứng ------------------------------------------------------
    with sqlite3.connect(restored_db) as db:
        row = db.execute("SELECT password_hash, role FROM users WHERE email=?",
                         (DRILL_EMAIL,)).fetchone()
    check("User admin có mặt sau khôi phục", row is not None, DRILL_EMAIL)
    if row:
        check("Mật khẩu đăng nhập kiểm chứng được (verify_password)",
              verify_password(row[0], DRILL_USER_PASSWORD), f"role={row[1]}")

    with sqlite3.connect(db_file) as db:
        src_acc = db.execute(
            "SELECT org_id,platform,label,external_id,currency FROM accounts").fetchall()
    with sqlite3.connect(restored_db) as db:
        new_acc = db.execute(
            "SELECT org_id,platform,label,external_id,currency FROM accounts").fetchall()
    check("Dòng tài khoản khớp bản gốc", src_acc == new_acc and len(new_acc) == 1,
          f"{new_acc}")

    restored_counts = _tables(restored_db)
    mismatches = {t: (source_counts.get(t), restored_counts.get(t))
                  for t in set(source_counts) | set(restored_counts)
                  if source_counts.get(t) != restored_counts.get(t) and t != "sessions"}
    check("Số dòng mọi bảng khớp (trừ sessions bị xoá có chủ đích)",
          not mismatches, f"sai lệch: {mismatches}" if mismatches else
          f"{len(restored_counts)} bảng")
    check("Sessions không được chuyển sang máy mới (đăng nhập lại bắt buộc)",
          restored_counts.get("sessions", 0) == 0,
          f"sessions={restored_counts.get('sessions', 0)}")

    _key, plain = secure_backup.decrypt_snapshot(backup_file.read_bytes(),
                                                 DRILL_PASSPHRASE)
    digest_src = hashlib.sha256(plain).hexdigest()
    digest_new = hashlib.sha256(restored_db.read_bytes()).hexdigest()
    check("SHA-256 DB khôi phục == SHA-256 snapshot trong backup",
          digest_src == digest_new, digest_new[:16] + "…")

    settings_file = restore_dir / "local-settings.json"
    try:
        settings = json.loads(settings_file.read_text(encoding="utf-8"))
        if settings.get("format") == "windows-dpapi-v1":
            check("local-settings.json được tạo (DPAPI trên Windows)", True,
                  "định dạng windows-dpapi-v1")
        else:
            same_key = settings.get("MASTER_KEY") == DRILL_MASTER_KEY
            check("MASTER_KEY khôi phục khớp máy gốc (mở được token đã seal)",
                  same_key, "khớp" if same_key else "KHÁC")
            check("SESSION_SECRET mới được cấp (không chuyển session)", 
                  len(settings.get("SESSION_SECRET", "")) >= 32, "")
    except Exception as exc:  # noqa: BLE001
        check("local-settings.json được tạo", False, f"{type(exc).__name__}: {exc}")

    # --- Hành vi fail-closed --------------------------------------------------
    try:
        secure_backup.decrypt_snapshot(backup_file.read_bytes(),
                                       "sai mat khau dien tap 2026")
        check("Sai mật khẩu sao lưu -> bị từ chối", False, "không hề báo lỗi!")
    except ValueError:
        check("Sai mật khẩu sao lưu -> bị từ chối", True, "ValueError")
    tampered = bytearray(backup_file.read_bytes())
    tampered[-8] ^= 1
    try:
        secure_backup.decrypt_snapshot(bytes(tampered), DRILL_PASSPHRASE)
        check("File backup bị sửa 1 byte -> bị từ chối", False, "không hề báo lỗi!")
    except ValueError:
        check("File backup bị sửa 1 byte -> bị từ chối", True, "ValueError (AES-GCM)")
    try:
        secure_backup.restore_into_empty_directory(
            backup_file.read_bytes(), DRILL_PASSPHRASE, restore_dir)
        check("Khôi phục đè lên thư mục đã có dữ liệu -> bị từ chối", False,
              "không hề báo lỗi!")
    except FileExistsError:
        check("Khôi phục đè lên thư mục đã có dữ liệu -> bị từ chối", True,
              "FileExistsError")

    return checks


def _force_utf8_streams():
    # Windows consoles/pipes default to a legacy codepage (cp1252/cp437)
    # that cannot encode Vietnamese; these CLIs print Vietnamese status
    # text, so pin stdout/stderr to UTF-8 when the runtime allows it.
    import sys as _sys
    for stream in (_sys.stdout, _sys.stderr):
        try:
            stream.reconfigure(encoding='utf-8', errors='replace')
        except (AttributeError, ValueError):
            pass

def main() -> int:
    _force_utf8_streams()
    print("DIỄN TẬP SAO LƯU / KHÔI PHỤC — LHM Ads AI")
    print("Dùng code thật: ads_core.secure_backup (AES-256-GCM + Scrypt).")
    print("Lớp cổng desktop (admin/loopback) không nằm trong drill headless này.")
    with tempfile.TemporaryDirectory(prefix="lhm-restore-drill-") as tmp:
        checks = run_drill(Path(tmp))
    failed = 0
    for label, ok, detail in checks:
        print(f"[{'PASS' if ok else 'FAIL'}] {label}" + (f" — {detail}" if detail else ""))
        failed += 0 if ok else 1
    print(f"KẾT QUẢ: {len(checks) - failed}/{len(checks)} PASS"
          + (" — DIỄN TẬP ĐẠT" if not failed else f" — {failed} FAIL"))
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
