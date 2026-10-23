"""Apply an already SHA256-verified signed update AFTER the running EXE exits.

A detached Windows PowerShell worker waits for the native app to close,
backs up the previous binary, installs the new one in the same directory,
and starts it again. User data under LOCALAPPDATA is not touched.
"""
from __future__ import annotations

import base64
import hashlib
import os
from pathlib import Path
import subprocess
import sys

from windows.online_update import staged_update, UpdateError


def _ps_string(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def _powershell_script(current: Path, staged: Path, digest: str, version: str,
                       process_id: int) -> str:
    target = _ps_string(str(current))
    source = _ps_string(str(staged))
    expected = _ps_string(digest)
    backup = _ps_string(str(current) + '.backup-' + version)
    # A same-directory temporary file avoids cross-volume moves. Rename the
    # old file to a backup only after the new file is fully copied/hashed.
    return f"""
$ErrorActionPreference = 'Stop'
$target = {target}
$source = {source}
$expected = {expected}
$backup = {backup}
$next = $target + '.updating'
$oldProcessId = {process_id}
for ($i = 0; $i -lt 120; $i++) {{
  if (-not (Get-Process -Id $oldProcessId -ErrorAction SilentlyContinue)) {{ break }}
  Start-Sleep -Milliseconds 500
}}
if (Get-Process -Id $oldProcessId -ErrorAction SilentlyContinue) {{ exit 4 }}
if (-not (Test-Path -LiteralPath $source -PathType Leaf)) {{ exit 5 }}
if ((Get-FileHash -LiteralPath $source -Algorithm SHA256).Hash.ToLowerInvariant() -ne $expected) {{ exit 6 }}
if (Test-Path -LiteralPath $backup) {{ exit 7 }}
if (Test-Path -LiteralPath $next) {{ exit 8 }}
try {{
  Copy-Item -LiteralPath $source -Destination $next -ErrorAction Stop
  if ((Get-FileHash -LiteralPath $next -Algorithm SHA256).Hash.ToLowerInvariant() -ne $expected) {{
    throw 'Updated EXE does not match SHA256'
  }}
  Rename-Item -LiteralPath $target -NewName ([IO.Path]::GetFileName($backup)) -ErrorAction Stop
  try {{
    Rename-Item -LiteralPath $next -NewName ([IO.Path]::GetFileName($target)) -ErrorAction Stop
  }} catch {{
    Rename-Item -LiteralPath $backup -NewName ([IO.Path]::GetFileName($target)) -ErrorAction SilentlyContinue
    throw
  }}
  Start-Process -FilePath $target -WorkingDirectory ([IO.Path]::GetDirectoryName($target))
}} catch {{
  if (Test-Path -LiteralPath $next) {{ Remove-Item -LiteralPath $next -Force -ErrorAction SilentlyContinue }}
  if ((-not (Test-Path -LiteralPath $target)) -and (Test-Path -LiteralPath $backup)) {{
    Rename-Item -LiteralPath $backup -NewName ([IO.Path]::GetFileName($target)) -ErrorAction SilentlyContinue
  }}
  exit 9
}}
"""


def spawn_install_after_exit(data_folder: Path, executable: Path):
    if sys.platform != 'win32' or not getattr(sys, 'frozen', False):
        raise UpdateError('Tự cài đặt chỉ hoạt động trong Windows EXE chính thức.')
    exe = Path(executable).resolve()
    if exe.name.lower() != 'lhm-ads-ai.exe' or not exe.is_file():
        raise UpdateError('Không thể cập nhật tệp EXE không đúng tên.')
    staged = staged_update(data_folder)
    if staged is None:
        raise UpdateError('Không có bản cập nhật hợp lệ đã xác minh.')
    binary, sha256, version = staged
    script = _powershell_script(exe, binary.resolve(), sha256, version, os.getpid())
    encoded = base64.b64encode(script.encode('utf-16le')).decode('ascii')
    flags = getattr(subprocess, 'CREATE_NO_WINDOW', 0) | getattr(
        subprocess, 'DETACHED_PROCESS', 0)
    subprocess.Popen(['powershell.exe', '-NoLogo', '-NoProfile', '-NonInteractive',
                      '-EncodedCommand', encoded],
                     close_fds=True, creationflags=flags,
                     cwd=str(exe.parent))
