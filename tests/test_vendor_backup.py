"""Seller encrypted vault: complete recovery, wrong password and tamper fail closed."""
from __future__ import annotations

import base64
from contextlib import closing
from pathlib import Path
import sqlite3

import pytest

from tools import vendor_backup as vault
from tools import vendor_ledger as ledger
from tools import vendor_sales as sales
from tools.license_issuer import create_vendor_keys


@pytest.fixture
def seller(tmp_path):
    private=tmp_path/'keys'/'vendor-private.pem'
    public=tmp_path/'keys'/'vendor-public.b64'
    signing_password='private-signing-password-long-2026'
    backup_password='completely-separate-backup-password-2026'
    create_vendor_keys(private,public,signing_password)
    dbpath=tmp_path/'live'/'customers.sqlite3'
    with closing(ledger.connect(dbpath)) as db:
        ledger.register(db,'KH001','a'*32)
        ledger.register(db,'KH002','b'*32)
    directory=tmp_path/'issued'
    def issue(customer,receipt,now):
        return sales.issue_paid_license(
            customer_ref=customer,receipt_ref=receipt,
            passphrase=signing_password,private_file=private,
            public_file=public,db_path=dbpath,license_directory=directory,
            payment_confirmed=True,now=now)
    first=issue('KH001','TT-KH001-001',1792670400)
    second=issue('KH001','TT-KH001-002',1792670400+86400)
    third=issue('KH002','TT-KH002-001',1792670400)
    return locals()


def test_full_encrypted_backup_and_restore_then_renew(seller):
    s=seller
    destination=s['tmp_path']/'encrypted.lhmvault'
    info=vault.export_vault(s['dbpath'],s['directory'],s['public'],
                            destination,s['backup_password'])
    assert info['encrypted'] is True
    assert info['contains_private_key'] is False
    assert info['licenses']==3
    raw=destination.read_bytes()
    assert raw.startswith(vault.MAGIC)
    assert b'TT-KH001-001' not in raw
    assert b'KH001' not in raw
    assert s['signing_password'].encode() not in raw
    restored=s['tmp_path']/'restored-vendor'
    result=vault.restore_vault(destination,s['backup_password'],restored,s['public'])
    assert result['licenses']==3
    assert result['requires_original_private_key'] is True
    assert not (restored/'keys').exists()
    assert not (restored/'vendor-private.pem').exists()
    with sqlite3.connect(restored/'customers.sqlite3') as db:
        assert db.execute('SELECT COUNT(*) FROM licenses').fetchone()[0]==3
    previous=s['second']
    renewed=sales.issue_paid_license(
        customer_ref='KH001',receipt_ref='TT-KH001-003',
        passphrase=s['signing_password'],private_file=s['private'],
        public_file=restored/'vendor-public.b64',
        db_path=restored/'customers.sqlite3',
        license_directory=restored/'issued-licenses',
        payment_confirmed=True,now=1792670400+2*86400)
    assert renewed['expires_at']==previous['expires_at']+30*86400


def test_wrong_password_and_changed_ciphertext_never_create_target(seller):
    s=seller
    backup=s['tmp_path']/'safe.lhmvault'
    vault.export_vault(s['dbpath'],s['directory'],s['public'],
                       backup,s['backup_password'])
    target=s['tmp_path']/'not-restored'
    with pytest.raises(vault.VendorVaultError,match='mật khẩu'):
        vault.restore_vault(backup,'wrong-password-value!',target,s['public'])
    assert not target.exists()
    raw=bytearray(backup.read_bytes())
    raw[-17]^=1
    backup.write_bytes(raw)
    with pytest.raises(vault.VendorVaultError,match='đã bị thay đổi'):
        vault.restore_vault(backup,s['backup_password'],target,s['public'])
    assert not target.exists()


def test_wrong_public_key_and_overwrite_refused(seller):
    s=seller
    backup=s['tmp_path']/'key-check.lhmvault'
    vault.export_vault(s['dbpath'],s['directory'],s['public'],
                       backup,s['backup_password'])
    another=s['tmp_path']/'other-key.b64'
    another.write_bytes(base64.b64encode(b'A'*32))
    target=s['tmp_path']/'wrong-public'
    with pytest.raises(vault.VendorVaultError,match='Khóa'):
        vault.restore_vault(backup,s['backup_password'],target,another)
    assert not target.exists()
    vault.restore_vault(backup,s['backup_password'],target,s['public'])
    with pytest.raises(FileExistsError,match='CHƯA TỒN TẠI'):
        vault.restore_vault(backup,s['backup_password'],target,s['public'])
    with pytest.raises(FileExistsError):
        vault.export_vault(s['dbpath'],s['directory'],s['public'],
                           backup,s['backup_password'])


def test_missing_or_tampered_issued_license_cannot_be_backed_up(seller):
    s=seller
    target=s['tmp_path']/'no-backup.lhmvault'
    missing=Path(s['second']['path'])
    missing.unlink()
    with pytest.raises(vault.VendorVaultError,match='Thiếu'):
        vault.export_vault(s['dbpath'],s['directory'],s['public'],
                           target,s['backup_password'])
    assert not target.exists()


def test_vault_password_minimum_enforced_before_writing(seller):
    s=seller
    out=s['tmp_path']/'weak.lhmvault'
    with pytest.raises(vault.VendorVaultError,match='16 ký tự'):
        vault.export_vault(s['dbpath'],s['directory'],s['public'],out,'123')
    assert not out.exists()


def test_empty_seller_ledger_backup_supported(tmp_path):
    private=tmp_path/'key.pem'
    public=tmp_path/'key.b64'
    create_vendor_keys(private,public,'a-long-private-key-password')
    dbpath=tmp_path/'fresh.sqlite3'
    with closing(ledger.connect(dbpath)):
        pass
    outfile=tmp_path/'blank.lhmvault'
    data=vault.export_vault(dbpath,tmp_path/'not-yet-issued',
                            public,outfile,'secure-enough-backup-secret')
    assert data['licenses']==0
    dest=tmp_path/'restored-blank'
    assert vault.restore_vault(outfile,'secure-enough-backup-secret',
                               dest,public)['licenses']==0
