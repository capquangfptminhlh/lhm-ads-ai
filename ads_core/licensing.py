"""LHM Ads AI offline, signed 30-day subscriptions; never ship the private issuer key.

Renewal is manual through a signed license file so customer ad accounts and API
credentials never need to pass through a central licensing VPS.
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
from pathlib import Path
import time
import uuid

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from cryptography.exceptions import InvalidSignature
from fastapi import Depends, HTTPException
from pydantic import BaseModel, Field

from .app import app, browser_admin, identify
from .db import audit, connection
from . import license_revocation
from .security import (
    LICENSE_ACTIVATION_MAX_ATTEMPTS,
    attempt_blocked, attempt_failed, attempt_succeeded,
    license_activation_scope, seal, unseal,
)
from .release_info import EDITION

PUBLIC_KEY_B64 = 'wfIl1u1iuW0wmtfnpoUIhMUNgWRmnn4wub36hTRzaGg='
PRODUCT = 'LHM_ADS_AI'
MAX_FILE_SIZE = 4096


def license_folder() -> Path:
    """Co-locate licensing with existing database, never with PyInstaller bundle."""
    return Path(os.environ.get('DB_PATH', './data/lhm-ads.sqlite3')).resolve().parent / 'licensing'


def _read_install_id() -> str:
    path = license_folder() / 'install-id.txt'
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        value=path.read_text(encoding='ascii').strip()
        if len(value) == 36:
            try:
                return str(uuid.UUID(value))
            except ValueError:
                pass
        raise RuntimeError('Install ID bị hỏng; liên hệ hỗ trợ thay vì tự thay đổi')
    value = str(uuid.uuid4())
    try:
        fd=os.open(path, os.O_CREAT|os.O_EXCL|os.O_WRONLY, 0o600)
        with os.fdopen(fd,'w',encoding='ascii') as f:f.write(value)
    except FileExistsError:
        return _read_install_id()
    return value


def device_id() -> str:
    install=_read_install_id()
    machine=''
    if os.name == 'nt':
        try:
            import winreg
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r'SOFTWARE\Microsoft\Cryptography') as key:
                machine=str(winreg.QueryValueEx(key,'MachineGuid')[0])
        except OSError:
            machine=''
    return hashlib.sha256((PRODUCT+'|'+install+'|'+machine).encode()).hexdigest()[:32]


def canonical(payload: dict) -> bytes:
    return json.dumps(payload,ensure_ascii=True,sort_keys=True,separators=(',',':')).encode('utf-8')


def verify_signed_license(raw: str, *, now: int | None = None) -> dict:
    """Verify token without accessing Internet. Expired licenses never authorize writes."""
    if not isinstance(raw,str) or len(raw)>MAX_FILE_SIZE:
        raise ValueError('File giấy phép không hợp lệ')
    try:
        data=json.loads(raw)
        if not isinstance(data,dict) or set(data)!={'payload','signature'}:
            raise ValueError('Bad envelope')
        payload=data['payload']
        if not isinstance(payload,dict) or set(payload)!={'product','device','license_id','issued_at','expires_at','plan'}:
            raise ValueError('Bad payload')
        if payload['product']!=PRODUCT or payload['device']!=device_id():
            raise ValueError('License belongs to another device or product')
        if payload['plan'] not in ('monthly','trial','annual'):
            raise ValueError('Unknown plan')
        if not isinstance(payload['issued_at'],int) or not isinstance(payload['expires_at'],int):
            raise ValueError('Bad timestamps')
        if not isinstance(payload['license_id'],str) or not 8<=len(payload['license_id'])<=80:
            raise ValueError('Bad ID')
        if payload['issued_at']>=payload['expires_at'] or payload['expires_at']-payload['issued_at']>370*86400:
            raise ValueError('Invalid duration')
        sig=base64.b64decode(data['signature'],validate=True)
        Ed25519PublicKey.from_public_bytes(base64.b64decode(PUBLIC_KEY_B64)).verify(sig,canonical(payload))
        current=int(time.time()) if now is None else now
        if payload['issued_at']>current+300:
            raise ValueError('License begins in the future')
        if payload['expires_at']<=current:
            raise ValueError('License expired')
        return payload
    except (InvalidSignature, ValueError, TypeError, KeyError, OverflowError, json.JSONDecodeError) as exc:
        raise ValueError('Giấy phép không hợp lệ, hết hạn hoặc không thuộc máy này') from None


def trusted_clock(now: int | None = None) -> tuple[bool,str | None]:
    """Persist a sealed max-seen wall time; reject large backward clock jumps.

    Not tamper-proof against a machine owner; prevents accidental clock rewind
    and simple JSON edits without exposing or rotating the Ads encryption key.
    """
    current=int(time.time()) if now is None else int(now)
    anchor=license_folder()/'clock-anchor.json'
    previous=0
    if anchor.exists():
        try:
            blob=json.loads(anchor.read_text(encoding='utf-8'))
            if not isinstance(blob,dict) or set(blob)!={'sealed'}:
                raise ValueError('Invalid clock anchor envelope')
            previous=int(unseal(blob['sealed'],f'license-clock:{device_id()}'))
            if previous<=0 or previous>4102444800:
                raise ValueError('Invalid clock timestamp')
        except Exception:
            return False,'clock_state_invalid'
    if current+300<previous:
        return False,'clock_rollback'
    if current>previous+60:
        ciphertext=seal(str(current),f'license-clock:{device_id()}')
        tmp=anchor.with_name(anchor.name+'.tmp')
        with os.fdopen(os.open(tmp,os.O_WRONLY|os.O_CREAT|os.O_TRUNC,0o600),'w',encoding='utf-8') as f:
            json.dump({'sealed':ciphertext},f)
            f.flush();os.fsync(f.fileno())
        os.replace(tmp,anchor)
    return True,None


def read_license() -> dict:
    from .cloud_license import licensing_required, entitlement
    if licensing_required():
        # Gmail mode: every feature gate follows the Gmail plan and its signed lease.
        state=entitlement()
        status={'active':state['active'],'device':device_id(),'edition':EDITION,'mode':'gmail',
                'plan':state.get('plan') or 'gmail','expires_at':state.get('expires_at') or '',
                'offline_until':state.get('offline_until') or ''}
        if not state['active']:
            status['reason']=state.get('reason') or 'SUBSCRIPTION_REQUIRED'
        return status
    path=license_folder()/'license.json'
    if not path.is_file():
        return {'active':False,'reason':'missing','device':device_id(),'edition':EDITION}
    try:
        payload=verify_signed_license(path.read_text(encoding='utf-8'))
    except (ValueError,UnicodeError,OSError):
        return {'active':False,'reason':'expired_or_invalid','device':device_id(),'edition':EDITION}
    # Revocation (offline model): the signed list lives next to license.json
    # unless LHM_REVOCATION_FILE points elsewhere. No file = no revocations;
    # a file that fails verification fails closed.
    rev_path=os.environ.get('LHM_REVOCATION_FILE') or str(license_folder()/'revocations.json')
    try:
        revocations=license_revocation.load_revocation_list(rev_path)
    except license_revocation.RevocationError:
        return {'active':False,'reason':'revocation_list_invalid','device':device_id(),'edition':EDITION}
    revoked,_entry=license_revocation.is_revoked(revocations,payload)
    if revoked:
        return {'active':False,'reason':'revoked','device':device_id(),'edition':EDITION}
    safe,reason=trusted_clock()
    if not safe:
        return {'active':False,'reason':reason,'device':device_id(),'edition':EDITION}
    return {'active':True,'device':device_id(),'edition':EDITION,
            **{k:payload[k] for k in ('plan','license_id','expires_at')}}


def license_required() -> dict:
    status=read_license()
    if not status['active']:
        raise HTTPException(402,'Gói sử dụng đã hết hạn hoặc chưa kích hoạt. Gia hạn để tiếp tục tự động hóa.')
    return status


class Activation(BaseModel):
    license_text: str = Field(min_length=50,max_length=MAX_FILE_SIZE)


@app.get('/api/license')
def license_status(ident=Depends(identify)):
    del ident
    return read_license()


@app.post('/api/license/activate')
def activate_license(body:Activation, ident=Depends(browser_admin)):
    scope=license_activation_scope(ident['id'])
    with connection() as db:
        if attempt_blocked(db,scope,LICENSE_ACTIVATION_MAX_ATTEMPTS):
            raise HTTPException(429,'Đã thử kích hoạt quá nhiều lần. Vui lòng đợi 15 phút rồi thử lại.')
    try:
        payload=verify_signed_license(body.license_text)
    except ValueError:
        with connection() as db:
            attempt_failed(db,scope)
        raise HTTPException(422,'Giấy phép không hợp lệ, hết hạn hoặc không thuộc máy này') from None
    rev_path=os.environ.get('LHM_REVOCATION_FILE') or str(license_folder()/'revocations.json')
    try:
        revocations=license_revocation.load_revocation_list(rev_path)
    except license_revocation.RevocationError:
        raise HTTPException(422,'Danh sách thu hồi giấy phép không hợp lệ; liên hệ hỗ trợ') from None
    revoked,entry=license_revocation.is_revoked(revocations,payload)
    if revoked:
        with connection() as db:
            attempt_failed(db,scope)
        raise HTTPException(422,'Giấy phép đã bị thu hồi'+(f": {entry.get('reason')}" if entry and entry.get('reason') else '')+'. Liên hệ đơn vị cung cấp.')
    clock_ok, clock_reason=trusted_clock()
    if not clock_ok:
        raise HTTPException(409,'Đồng hồ Windows bị chỉnh lùi hoặc dữ liệu kiểm tra thời gian hỏng; đồng bộ lại giờ và liên hệ hỗ trợ')
    old=read_license()
    # Never replace a still-valid newer license with an older expiry, avoiding accidental downgrade.
    if old['active'] and payload['expires_at']<old['expires_at']:
        raise HTTPException(409,'Giấy phép mới không được có ngày hết hạn sớm hơn giấy phép hiện tại')
    target=license_folder()/'license.json'
    tmp=target.with_suffix('.json.tmp')
    fd=os.open(tmp,os.O_CREAT|os.O_TRUNC|os.O_WRONLY,0o600)
    with os.fdopen(fd,'w',encoding='utf-8') as f:
        f.write(body.license_text)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp,target)
    with connection() as db:
        attempt_succeeded(db,scope)
        audit(db,ident,'license.activate',f'License ID={payload["license_id"]}, expiry={payload["expires_at"]}')
    return read_license()
