"""Windows DPAPI local user vault for MASTER_KEY and SESSION_SECRET.

Protects settings on disk using the Windows account. Not suitable for sharing a DB
between machines or for protecting against malware running under the same user.
"""
from __future__ import annotations

import base64
import ctypes
from ctypes import wintypes
import json
import os
from pathlib import Path
import secrets


class _DATA_BLOB(ctypes.Structure):
    _fields_=[('cbData',wintypes.DWORD),('pbData',ctypes.POINTER(ctypes.c_byte))]


def _dpapi_call(method: str, payload: bytes) -> bytes:
    if os.name != 'nt':
        raise RuntimeError('Windows DPAPI chỉ hoạt động trên hệ điều hành Windows')
    raw=(ctypes.c_byte*len(payload)).from_buffer_copy(payload)
    data=_DATA_BLOB(len(payload),ctypes.cast(raw,ctypes.POINTER(ctypes.c_byte)))
    out=_DATA_BLOB()
    crypt32=ctypes.windll.crypt32
    kernel32=ctypes.windll.kernel32
    crypt32.CryptProtectData.argtypes=(ctypes.POINTER(_DATA_BLOB),ctypes.c_wchar_p,
                                       ctypes.c_void_p,ctypes.c_void_p,ctypes.c_void_p,
                                       wintypes.DWORD,ctypes.POINTER(_DATA_BLOB))
    crypt32.CryptProtectData.restype=wintypes.BOOL
    crypt32.CryptUnprotectData.argtypes=(ctypes.POINTER(_DATA_BLOB),ctypes.c_void_p,
                                         ctypes.c_void_p,ctypes.c_void_p,ctypes.c_void_p,
                                         wintypes.DWORD,ctypes.POINTER(_DATA_BLOB))
    crypt32.CryptUnprotectData.restype=wintypes.BOOL
    fn=getattr(crypt32,method)
    # CRYPTPROTECT_UI_FORBIDDEN; user-context scoped, not portable to another Windows user.
    if not fn(ctypes.byref(data),None,None,None,None,1,ctypes.byref(out)):
        raise OSError(ctypes.get_last_error(), 'Không thể giải mã/lưu Windows DPAPI')
    kernel32.LocalFree.argtypes=[ctypes.c_void_p]
    kernel32.LocalFree.restype=ctypes.c_void_p
    try:
        return ctypes.string_at(out.pbData,out.cbData)
    finally:
        kernel32.LocalFree(ctypes.cast(out.pbData,ctypes.c_void_p))


def dpapi_encrypt(data:bytes)->str:
    return base64.b64encode(_dpapi_call('CryptProtectData',data)).decode('ascii')


def dpapi_decrypt(ciphertext:str)->bytes:
    try:
        packed=base64.b64decode(ciphertext,validate=True)
    except (ValueError,TypeError) as exc:
        raise ValueError('Dữ liệu DPAPI không hợp lệ') from None
    return _dpapi_call('CryptUnprotectData',packed)


def _save_settings(path:Path,values:dict):
    if os.name == 'nt':
        blob=json.dumps(values,sort_keys=True).encode('utf-8')
        output={'format':'windows-dpapi-v1','ciphertext':dpapi_encrypt(blob)}
    else:
        # Linux development and CI use a private file; Windows release always DPAPI.
        output=values
    tmp=path.with_name(path.name+'.tmp')
    with os.fdopen(os.open(tmp,os.O_WRONLY|os.O_CREAT|os.O_TRUNC,0o600),'w',encoding='utf-8') as fd:
        json.dump(output,fd)
        fd.flush()
        os.fsync(fd.fileno())
    os.replace(tmp,path)
    if os.name != 'nt':
        os.chmod(path,0o600)


def read_or_create_settings(path:Path) -> dict:
    """Load or safely migrate existing settings; never silently rotate old master key."""
    path.parent.mkdir(parents=True,exist_ok=True)
    if path.exists():
        content=json.loads(path.read_text(encoding='utf-8'))
        if isinstance(content,dict) and content.get('format')=='windows-dpapi-v1':
            values=json.loads(dpapi_decrypt(content['ciphertext']).decode('utf-8'))
        elif isinstance(content,dict) and all(k in content for k in ('MASTER_KEY','SESSION_SECRET')):
            values={k:content[k] for k in ('MASTER_KEY','SESSION_SECRET')}
            if os.name=='nt':_save_settings(path,values)
        else:
            raise RuntimeError('Tệp cấu hình bảo mật bị hỏng hoặc không hỗ trợ: không tự tạo lại khóa')
    else:
        values={'MASTER_KEY':base64.b64encode(secrets.token_bytes(32)).decode('ascii'),
                'SESSION_SECRET':secrets.token_urlsafe(48)}
        _save_settings(path,values)
    if (not isinstance(values,dict) or not isinstance(values.get('MASTER_KEY'),str)
            or not isinstance(values.get('SESSION_SECRET'),str)
            or len(values['SESSION_SECRET'])<32):
        raise RuntimeError('Không thể mở khóa ứng dụng Windows; tránh tạo lại khóa')
    try:
        if len(base64.b64decode(values['MASTER_KEY'],validate=True))!=32:
            raise ValueError('Invalid key size')
    except (ValueError,TypeError):
        raise RuntimeError('MASTER_KEY bị hỏng; không tự tạo lại để tránh mất token') from None
    return values
