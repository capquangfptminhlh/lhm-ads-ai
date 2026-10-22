"""Seller GUI's offline issuance core — no real bank, Ads token, or vendor key."""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from tools import vendor_ledger as ledger
from tools import vendor_sales as sales
from tools.license_issuer import create_vendor_keys


@pytest.fixture
def vendor(tmp_path):
    private = tmp_path/'keys'/'vendor-private-key.pem'
    public = tmp_path/'keys'/'vendor-public.b64'
    secret='carefully-stored-local-only-secret-2026'
    create_vendor_keys(private,public,secret)
    dbpath=tmp_path/'vendor.sqlite3'
    db=ledger.connect(dbpath)
    try:
        ledger.register(db,'KH001','a'*32)
        ledger.register(db,'KH002','b'*32)
    finally:
        db.close()
    return {'private_file':private,'public_file':public,'passphrase':secret,
            'db_path':dbpath,'license_directory':tmp_path/'issued',
            'payment_confirmed':True,'customer_ref':'KH001',
            'receipt_ref':'TT-KH001-001','now':1792670400}


def issue(vendor,**change):
    options=dict(vendor)
    options.update(change)
    return sales.issue_paid_license(**options)


def test_real_signature_confirmed_receipt_and_ledger(vendor):
    issued=issue(vendor)
    path=Path(issued['path'])
    assert path.is_file()
    assert issued['payment_status']=='confirmed'
    payload, signature=ledger.verify_license(path,vendor['public_file'])
    assert payload['license_id']==issued['license_id']
    assert payload['expires_at']-payload['issued_at']==30*86400
    assert payload['device']=='a'*32
    assert len(signature)==64
    conn=sqlite3.connect(vendor['db_path'])
    try:
        row=conn.execute('SELECT payment_status,receipt_ref FROM licenses').fetchone()
        assert row==('confirmed','TT-KH001-001')
    finally:
        conn.close()
    assert not (vendor['license_directory']/'private.pem').exists()


def test_renewal_accumulates_existing_days(vendor):
    first=issue(vendor)
    second=issue(vendor,receipt_ref='TT-KH001-002',now=vendor['now']+86400)
    assert second['expires_at']==first['expires_at']+30*86400
    assert first['license_id']!=second['license_id']
    assert Path(first['path']).exists() and Path(second['path']).exists()
    current=issue(vendor,receipt_ref='TT-KH001-003',now=vendor['now']+2*86400)
    assert current['expires_at']==second['expires_at']+30*86400


@pytest.mark.parametrize('change,error',[
    ({'payment_confirmed':False},'ngân hàng'),
    ({'receipt_ref':''},'biên nhận'),
    ({'customer_ref':'INVALID!'},'không hợp lệ'),
    ({'customer_ref':'GUEST'},'chưa đăng ký'),
    ({'passphrase':'wrong'},'Sai mật khẩu'),
])
def test_fail_closed_without_verified_payment_or_keys(vendor,change,error):
    with pytest.raises(ValueError,match=error):
        issue(vendor,**change)
    assert not vendor['license_directory'].exists()


def test_second_use_of_bank_receipt_is_blocked(vendor):
    original=issue(vendor)
    with pytest.raises(ValueError,match='đã được dùng'):
        issue(vendor,customer_ref='KH002')
    assert len(list(vendor['license_directory'].glob('**/*.json')))==1


def test_renewal_requires_latest_recorded_license(vendor):
    older=issue(vendor)
    newer=issue(vendor,receipt_ref='TT-KH001-002',now=vendor['now']+86400)
    with pytest.raises(ValueError,match='MỚI NHẤT'):
        issue(vendor,receipt_ref='TT-KH001-003',renewal_source=Path(older['path']),
              now=vendor['now']+2*86400)
    assert Path(newer['path']).is_file()


def test_missing_old_license_never_restarts_subscription(vendor):
    first=issue(vendor)
    Path(first['path']).unlink()
    with pytest.raises(ValueError,match='Không tìm thấy license cũ'):
        issue(vendor,receipt_ref='TT-KH001-002',now=vendor['now']+86400)
    with sqlite3.connect(vendor['db_path']) as db:
        assert db.execute('SELECT COUNT(*) FROM licenses').fetchone()[0]==1


def test_rejects_public_private_mismatch(vendor,tmp_path):
    wrong_private=tmp_path/'another'/'private.pem'
    wrong_public=tmp_path/'another'/'public.b64'
    create_vendor_keys(wrong_private,wrong_public,vendor['passphrase'])
    with pytest.raises(ValueError,match='KHÔNG khớp'):
        issue(vendor,private_file=wrong_private)
    assert not vendor['license_directory'].exists()


def test_paid_issue_refuses_inconsistent_existing_license(vendor):
    first=issue(vendor)
    path=Path(first['path'])
    document=json.loads(path.read_text())
    document['payload']['expires_at']+=86400
    path.write_text(json.dumps(document))
    with pytest.raises(ValueError,match='License signature'):
        issue(vendor,receipt_ref='TT-KH001-002',now=vendor['now']+86400)


def test_gui_import_does_not_touch_db_or_create_secret(tmp_path,monkeypatch):
    monkeypatch.setenv('LOCALAPPDATA',str(tmp_path))
    from windows import vendor_manager
    vendor_manager._created_session()
    assert not list(tmp_path.iterdir())
