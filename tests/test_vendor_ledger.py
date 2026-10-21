"""Verify offline seller subscription bookkeeping without live Ads APIs."""
import base64
import csv
import json
import os
import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives import serialization
from tools import vendor_ledger as v

@pytest.fixture
def store(tmp_path):
    db=v.connect(tmp_path/'private'/'customers.sqlite3')
    yield db,tmp_path
    db.close()

@pytest.fixture
def issuer(tmp_path):
    private=Ed25519PrivateKey.generate()
    raw=private.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,format=serialization.PublicFormat.Raw)
    path=tmp_path/'vendor-public.b64'
    path.write_text(base64.b64encode(raw).decode(),encoding='ascii')
    return private,path

def signed(tmp,private,device,expiry,license_id='license-012345',plan='monthly',start=1795000000):
    payload={'product':v.PRODUCT,'device':device,'plan':plan,'license_id':license_id,
             'issued_at':start,'expires_at':expiry}
    data=json.dumps(payload,sort_keys=True,ensure_ascii=True,separators=(',',':')).encode()
    file=tmp/(license_id+'.json')
    file.write_text(json.dumps({'payload':payload,'signature':base64.b64encode(
        private.sign(data)).decode()}),encoding='utf-8')
    return file

def test_register_unique_and_private(store):
    db,tmp=store
    v.register(db,'SHOP-001','a'*32)
    with pytest.raises(ValueError):v.register(db,'SHOP-002','a'*32)
    with pytest.raises(ValueError):v.register(db,'SHOP-001','b'*32)
    with pytest.raises(ValueError):v.register(db,'Bad customer!','b'*32)
    with pytest.raises(ValueError):v.register(db,'SHOP-002','not-a-device')
    assert v.subscriptions(db)[0]['state']=='not_activated'
    if os.name!='nt':
        assert (tmp/'private'/'customers.sqlite3').stat().st_mode & 0o077==0

def test_signed_record_renewal_due_and_export(store,issuer):
    db,tmp=store;private,pub=issuer
    v.register(db,'S001','a'*32)
    file=signed(tmp,private,'a'*32,1797592000)
    r=v.record(db,'S001',file,pub)
    assert r['payment_status']=='pending'
    with pytest.raises(ValueError):v.record(db,'S001',file,pub)
    clock=1797592000-3*86400
    assert v.subscriptions(db,now=clock)[0]['days_remaining']==3
    assert not v.subscriptions(db,within_days=2,now=clock)
    assert len(v.subscriptions(db,within_days=7,now=clock))==1
    assert v.confirm_payment(db,r['license_id'],'BANKREF-043')['payment_status']=='confirmed'
    assert v.subscriptions(db,now=1797592000+1)[0]['state']=='expired'
    dest=tmp/'ledger.csv'
    v.export_csv(dest,v.subscriptions(db))
    output=dest.read_text(encoding='utf-8-sig')
    assert 'BANKREF-043' in output and 'access_token' not in output
    with pytest.raises(FileExistsError):v.export_csv(dest,[])

def test_wrong_device_tampering_and_other_public_key(store,issuer):
    db,tmp=store;key,pub=issuer
    v.register(db,'S001','a'*32)
    with pytest.raises(ValueError,match='another'):
        v.record(db,'S001',signed(tmp,key,'b'*32,1797592000),pub)
    file=signed(tmp,key,'a'*32,1797592000,'license-correct')
    obj=json.loads(file.read_text());obj['payload']['expires_at']+=100
    file.write_text(json.dumps(obj))
    with pytest.raises(ValueError,match='signature'):v.record(db,'S001',file,pub)
    other=Ed25519PrivateKey.generate()
    other_pub=tmp/'other.b64'
    other_pub.write_text(base64.b64encode(other.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,format=serialization.PublicFormat.Raw)).decode())
    with pytest.raises(ValueError):
        v.record(db,'S001',signed(tmp,key,'a'*32,1797592000,'license-good444'),other_pub)
    assert db.execute('SELECT COUNT(*) FROM licenses').fetchone()[0]==0

def test_never_assume_payment_and_never_downgrade(store,issuer):
    db,tmp=store;key,pub=issuer
    v.register(db,'S001','a'*32)
    one=signed(tmp,key,'a'*32,1797592000,'license-first01')
    with pytest.raises(ValueError,match='receipt'):
        v.record(db,'S001',one,pub,payment_status='confirmed')
    with pytest.raises(ValueError,match='Trial license'):
        v.record(db,'S001',one,pub,payment_status='trial')
    v.record(db,'S001',one,pub)
    with pytest.raises(ValueError):v.confirm_payment(db,'license-first01','')
    two=signed(tmp,key,'a'*32,1798592000,'license-second2')
    v.record(db,'S001',two,pub,payment_status='confirmed',receipt_ref='BANKREF-04')
    with pytest.raises(ValueError,match='earlier'):
        v.record(db,'S001',signed(tmp,key,'a'*32,1797700000,'license-rollback'),pub)
    assert v.subscriptions(db)[0]['license_id']=='license-second2'

def test_trial_explicit_and_term_validation(store,issuer):
    db,tmp=store;key,pub=issuer
    v.register(db,'TRIAL-1','a'*32)
    trial=signed(tmp,key,'a'*32,1795691200,'license-trial22',plan='trial')
    v.record(db,'TRIAL-1',trial,pub,payment_status='trial')
    with pytest.raises(ValueError):v.confirm_payment(db,'license-trial22','BANKREF-04')
    excessive=signed(tmp,key,'a'*32,1795000000+371*86400,'license-longterm')
    with pytest.raises(ValueError):v.record(db,'TRIAL-1',excessive,pub)


def test_vendor_backup_and_existing_parent_permission(store):
    db,tmp=store
    v.register(db,'BK01','a'*32)
    destination=tmp/'vendor-backup.sqlite3'
    result=v.backup_database(db,destination)
    assert result['contains_ads_tokens'] is False
    with pytest.raises(FileExistsError):v.backup_database(db,destination)
    imported=v.connect(destination)
    assert v.subscriptions(imported)[0]['customer_ref']=='BK01'
    imported.close()
    if os.name!='nt':
        existing=tmp/'external-directory'
        existing.mkdir(mode=0o755)
        before=existing.stat().st_mode & 0o777
        other=v.connect(existing/'local-ledger.sqlite3')
        other.close()
        assert (existing.stat().st_mode & 0o777)==before
