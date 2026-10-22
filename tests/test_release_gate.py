"""Commercial distribution gate must fail closed for any missing provenance."""
from datetime import datetime, timezone, timedelta
import base64
import hashlib
import json
from pathlib import Path
import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives import serialization

from tools import release_gate as gate


@pytest.fixture
def kit(tmp_path):
    public=Ed25519PrivateKey.generate().public_key().public_bytes(
        encoding=serialization.Encoding.Raw,format=serialization.PublicFormat.Raw)
    pubfile=tmp_path/'public.b64'
    pubfile.write_text(base64.b64encode(public).decode(),encoding='ascii')
    fingerprint=hashlib.sha256(public).hexdigest()
    exe=tmp_path/'LHM-Ads-AI.exe'
    exe.write_bytes(b'fake unsigned EXE CI fixture')
    sha=hashlib.sha256(exe.read_bytes()).hexdigest()
    checksum=tmp_path/'LHM-Ads-AI.sha256'
    checksum.write_text(f'{sha}  LHM-Ads-AI.exe\n',encoding='ascii')
    manifest=tmp_path/'release-manifest.json'
    payload={'product':'LHM Ads AI','source_commit':'a'*40,'product_version':'0.3.0',
        'edition':'commercial-candidate','executable':exe.name,'sha256':sha,
        'authenticode':'UNSIGNED','distribution':'NOT_APPROVED_FOR_SALE',
        'license_public_key_sha256':fingerprint}
    manifest.write_text(json.dumps(payload),encoding='utf-8')
    acceptance=tmp_path/'owner-acceptance.json'
    approved={'product':'LHM Ads AI','source_commit':'a'*40,'product_version':'0.3.0',
        'owner_approved':True,'approved_by':'LHM Vendor Owner',
        'approved_at_utc':(datetime.now(timezone.utc)-timedelta(minutes=1)).isoformat(),
        'checks':{k:{'passed':True,'evidence_ref':'LOCAL-EVIDENCE-'+k} for k in gate.REQUIRED_CHECKS}}
    acceptance.write_text(json.dumps(approved),encoding='utf-8')
    return exe,checksum,manifest,pubfile,acceptance


def test_gate_happy_path_checks_only_provenance_and_owner_attestation(kit):
    exe,checksum,manifest,pubfile,acceptance=kit
    assert gate.verify_candidate(exe,checksum,manifest,pubfile)['edition']=='commercial-candidate'
    assert gate.verify_approval(acceptance,gate.read_json(manifest))['owner_approved']


def test_gate_rejects_pilot_and_tampered_exe(kit):
    exe,checksum,manifest,pubfile,acceptance=kit
    item=gate.read_json(manifest)
    item['edition']='pilot'
    manifest.write_text(json.dumps(item))
    with pytest.raises(gate.ReleaseGateError,match='edition'):
        gate.verify_candidate(exe,checksum,manifest,pubfile)
    item['edition']='commercial-candidate'
    manifest.write_text(json.dumps(item))
    exe.write_bytes(b'changed EXE!')
    with pytest.raises(gate.ReleaseGateError,match='SHA256'):
        gate.verify_candidate(exe,checksum,manifest,pubfile)


def test_gate_rejects_wrong_vendor_key(kit,tmp_path):
    exe,checksum,manifest,pubfile,acceptance=kit
    different=Ed25519PrivateKey.generate().public_key().public_bytes(
        encoding=serialization.Encoding.Raw,format=serialization.PublicFormat.Raw)
    wrong=tmp_path/'wrong.b64'
    wrong.write_text(base64.b64encode(different).decode())
    with pytest.raises(gate.ReleaseGateError,match='public key fingerprint'):
        gate.verify_candidate(exe,checksum,manifest,wrong)


@pytest.mark.parametrize('key',gate.REQUIRED_CHECKS)
def test_gate_rejects_any_unproven_acceptance_item(kit,key):
    exe,checksum,manifest,pubfile,acceptance=kit
    data=gate.read_json(acceptance)
    data['checks'][key]['passed']=False
    acceptance.write_text(json.dumps(data))
    with pytest.raises(gate.ReleaseGateError,match='NOT_RUN or FAIL'):
        gate.verify_approval(acceptance,gate.read_json(manifest))


def test_gate_rejects_stale_commit_empty_evidence_and_no_owner(kit):
    exe,checksum,manifest,pubfile,acceptance=kit
    data=gate.read_json(acceptance)
    data['source_commit']='b'*40
    acceptance.write_text(json.dumps(data))
    with pytest.raises(gate.ReleaseGateError,match='commit'):
        gate.verify_approval(acceptance,gate.read_json(manifest))
    data['source_commit']='a'*40
    data['checks']['google_ads_live_read']['evidence_ref']=''
    acceptance.write_text(json.dumps(data))
    with pytest.raises(gate.ReleaseGateError,match='evidence'):
        gate.verify_approval(acceptance,gate.read_json(manifest))
    data['checks']['google_ads_live_read']['evidence_ref']='evidence-local'
    data['owner_approved']=False
    acceptance.write_text(json.dumps(data))
    with pytest.raises(gate.ReleaseGateError,match='not explicitly'):
        gate.verify_approval(acceptance,gate.read_json(manifest))


def test_gate_rejects_missing_public_fingerprint(kit):
    exe,checksum,manifest,pubfile,acceptance=kit
    data=gate.read_json(manifest)
    del data['license_public_key_sha256']
    manifest.write_text(json.dumps(data))
    with pytest.raises(gate.ReleaseGateError,match='fingerprint'):
        gate.verify_candidate(exe,checksum,manifest,pubfile)
