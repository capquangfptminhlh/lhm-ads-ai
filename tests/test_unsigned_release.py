"""Commercial release can be issued without Authenticode, but NEVER without
the owner's Ed25519 signing key, live acceptance and integrity checks.
"""
from datetime import datetime,timezone,timedelta
import base64,hashlib,json,zipfile
import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives import serialization
from tools import package_unsigned_release as pack
from tools.release_gate import REQUIRED_CHECKS,ReleaseGateError

@pytest.fixture
def parts(tmp_path):
    key=Ed25519PrivateKey.generate()
    password='an-offline-vendor-secret-password-2026'
    private=tmp_path/'vendor-private.pem'
    private.write_bytes(key.private_bytes(
        serialization.Encoding.PEM,serialization.PrivateFormat.PKCS8,
        serialization.BestAvailableEncryption(password.encode())))
    raw=key.public_key().public_bytes(serialization.Encoding.Raw,
                                      serialization.PublicFormat.Raw)
    pub=tmp_path/'vendor-public.b64'
    pub.write_text(base64.b64encode(raw).decode(),encoding='ascii')
    exe=tmp_path/'LHM-Ads-AI.exe'
    exe.write_bytes(b'CI-fixture-windows-exe')
    sha=hashlib.sha256(exe.read_bytes()).hexdigest()
    ck=tmp_path/'LHM-Ads-AI.sha256'
    ck.write_text(f'{sha}  LHM-Ads-AI.exe\n',encoding='ascii')
    manifest=tmp_path/'candidate.json'
    entry={'product':'LHM Ads AI','source_commit':'a'*40,'product_version':'0.3.0',
            'edition':'commercial-candidate','authenticode':'UNSIGNED',
            'distribution':'NOT_APPROVED_FOR_SALE','executable':'LHM-Ads-AI.exe',
            'sha256':sha,'license_public_key_sha256':hashlib.sha256(raw).hexdigest()}
    manifest.write_text(json.dumps(entry),encoding='utf-8')
    acceptance=tmp_path/'acceptance.json'
    approved={'product':'LHM Ads AI','source_commit':'a'*40,'product_version':'0.3.0',
        'owner_approved':True,'approved_by':'LHM Owner',
        'approved_at_utc':(datetime.now(timezone.utc)-timedelta(minutes=1)).isoformat(),
        'checks':{x:{'passed':True,'evidence_ref':'EVIDENCE-LOCAL-'+x}
                  for x in REQUIRED_CHECKS}}
    acceptance.write_text(json.dumps(approved),encoding='utf-8')
    out=tmp_path/'LHM-Ads-AI-0.3.0-COMMERCIAL-UNSIGNED.zip'
    return locals()

def run(p,**overrides):
    params=dict(exe=p['exe'],checksum=p['ck'],manifest=p['manifest'],
                public_file=p['pub'],acceptance=p['acceptance'],
                private_file=p['private'],password=p['password'],out=p['out'],
                accept_unsigned=True)
    params.update(overrides)
    return pack.create_package(**params)

def test_unsigned_release_is_signed_by_vendor_key_and_checks_exe(parts):
    created=run(parts)
    assert created['authenticode']=='UNSIGNED'
    data=pack.verify_package(parts['out'],parts['pub'])
    assert data['sha256']==hashlib.sha256(parts['exe'].read_bytes()).hexdigest()
    assert data['edition']=='commercial-unsigned'
    with zipfile.ZipFile(parts['out']) as released:
        assert 'no Microsoft Authenticode' in released.read('README-CUSTOMER.txt').decode()
    with pytest.raises(FileExistsError):
        run(parts)

def test_no_optin_and_unapproved_release_are_blocked(parts):
    with pytest.raises(ReleaseGateError,match='explicitly'):
        run(parts,accept_unsigned=False)
    approved=json.loads(parts['acceptance'].read_text())
    approved['checks']['google_ads_live_read']['passed']=False
    parts['acceptance'].write_text(json.dumps(approved))
    with pytest.raises(ReleaseGateError,match='NOT_RUN'):
        run(parts)
    assert not parts['out'].exists()

def test_wrong_vendor_key_and_wrong_passphrase(parts):
    with pytest.raises(ReleaseGateError,match='unlock'):
        run(parts,password='incorrect-password')
    other=Ed25519PrivateKey.generate()
    alternative=parts['tmp_path']/'mismatched.pem'
    alternative.write_bytes(other.private_bytes(
        serialization.Encoding.PEM,serialization.PrivateFormat.PKCS8,
        serialization.BestAvailableEncryption(parts['password'].encode())))
    with pytest.raises(ReleaseGateError,match='does not match'):
        run(parts,private_file=alternative)

def test_pilot_cannot_be_repackaged(parts):
    manifest=json.loads(parts['manifest'].read_text())
    manifest['edition']='pilot'
    parts['manifest'].write_text(json.dumps(manifest))
    with pytest.raises(ReleaseGateError,match='edition'):
        run(parts)

def test_package_tampering_and_untrusted_public_are_rejected(parts):
    run(parts)
    other=Ed25519PrivateKey.generate().public_key().public_bytes(
        serialization.Encoding.Raw,serialization.PublicFormat.Raw)
    alt=parts['tmp_path']/'other-pub.b64'
    alt.write_text(base64.b64encode(other).decode())
    with pytest.raises(ReleaseGateError,match='fingerprint'):
        pack.verify_package(parts['out'],alt)
    tampered=parts['tmp_path']/'tampered.zip'
    with zipfile.ZipFile(parts['out'],'r') as original:
        with zipfile.ZipFile(tampered,'w') as changed:
            for name in pack.EXPECTED_MEMBERS:
                data=original.read(name)
                if name=='LHM-Ads-AI.exe':data+=b'sneaky'
                changed.writestr(name,data)
    with pytest.raises(ReleaseGateError,match='SHA256 mismatch'):
        pack.verify_package(tampered,parts['pub'])
