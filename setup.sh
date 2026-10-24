#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
if [[ -e .env ]]; then
  echo '.env đã tồn tại; không thay đổi khóa mã hóa hiện có.'
  exit 0
fi
umask 077
python3 - <<'PY'
import secrets,base64
from pathlib import Path
s=Path('.env.example').read_text()
s=s.replace('REPLACE_WITH_BASE64_32_BYTE_KEY',base64.b64encode(secrets.token_bytes(32)).decode())
s=s.replace('REPLACE_WITH_LONG_RANDOM_SECRET',secrets.token_urlsafe(48))
Path('.env').write_text(s)
PY
chmod 600 .env
echo 'Đã tạo file .env với MASTER_KEY và SESSION_SECRET ngẫu nhiên.'
echo 'Hãy lưu bản sao an toàn của MASTER_KEY.'
echo 'Triển khai HTTPS ads.lhm.com sau khi DNS và cổng 80/443 đã sẵn sàng:'
echo 'docker compose -f docker-compose.yml -f compose.ads-lhm-com.yml up -d --build'
