"""Seller-only offline registry: device IDs, licenses and manually verified payments.

Never bundle into customer EXE or store Ads tokens/passwords. This SQLite file
belongs on the vendor's own workstation, outside the source repository.
"""
from __future__ import annotations
import argparse
import base64
import csv
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import time
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

PRODUCT='LHM_ADS_AI'
DEVICE=re.compile(r'^[a-f0-9]{32}$')
REF=re.compile(r'^[A-Za-z0-9][A-Za-z0-9._-]{1,63}$')
LICENSE_ID=re.compile(r'^[A-Za-z0-9][A-Za-z0-9._-]{7,79}$')
PAYMENTS={'pending','confirmed','trial'}
PLANS={'monthly','trial','annual'}
KEYS={'product','device','plan','license_id','issued_at','expires_at'}

def default_database():
    override=os.getenv('LHM_VENDOR_LEDGER_PATH')
    if override:return Path(override).expanduser().resolve()
    home=Path(os.environ.get('LOCALAPPDATA',str(Path.home()))) if os.name=='nt' else Path.home()/'.local'/'share'
    return home/'LHMAdsAI-Vendor'/'customers.sqlite3'

def connect(path):
    path=Path(path).expanduser().resolve()
    path.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
    if os.name!='nt':os.chmod(path.parent,0o700)
    db=sqlite3.connect(path,timeout=10)
    db.row_factory=sqlite3.Row
    db.execute('PRAGMA foreign_keys=ON')
    db.execute('PRAGMA busy_timeout=10000')
    db.executescript('''
    CREATE TABLE IF NOT EXISTS customers(
        customer_ref TEXT PRIMARY KEY,device TEXT NOT NULL UNIQUE,created_at INTEGER NOT NULL);
    CREATE TABLE IF NOT EXISTS licenses(
        license_id TEXT PRIMARY KEY,
        customer_ref TEXT NOT NULL REFERENCES customers(customer_ref),
        device TEXT NOT NULL,plan TEXT NOT NULL,
        issued_at INTEGER NOT NULL,expires_at INTEGER NOT NULL,
        signature_sha256 TEXT NOT NULL,
        payment_status TEXT NOT NULL DEFAULT 'pending',
        receipt_ref TEXT,recorded_at INTEGER NOT NULL,
        CHECK(payment_status IN ('pending','confirmed','trial')));
    CREATE INDEX IF NOT EXISTS idx_license_customer_expiry
        ON licenses(customer_ref,expires_at DESC);
    ''')
    if os.name!='nt':os.chmod(path,0o600)
    return db

def register(db,customer_ref,device,now=None):
    if not REF.fullmatch(customer_ref):
        raise ValueError('Customer reference must be 2-64 letters, digits, dot, underscore or dash')
    if not DEVICE.fullmatch(device):
        raise ValueError('Device ID must be exactly 32 lowercase hex characters')
    try:
        with db:
            db.execute('INSERT INTO customers(customer_ref,device,created_at) VALUES(?,?,?)',
                       (customer_ref,device,int(time.time()) if now is None else now))
    except sqlite3.IntegrityError as exc:
        raise ValueError('Customer reference or device already exists; never overwrite records') from exc
    return {'customer_ref':customer_ref,'device':device}

def verify_license(file_path,public_path):
    path=Path(file_path)
    if path.stat().st_size>4096:raise ValueError('License file exceeds 4 KiB')
    try:
        data=json.loads(path.read_text(encoding='utf-8'))
        if not isinstance(data,dict) or set(data)!={'payload','signature'}:
            raise ValueError('Invalid license envelope')
        payload=data['payload']
        if not isinstance(payload,dict) or set(payload)!=KEYS:
            raise ValueError('Invalid license fields')
        if payload['product']!=PRODUCT or payload['plan'] not in PLANS:
            raise ValueError('Wrong product/plan')
        if not isinstance(payload['device'],str) or not DEVICE.fullmatch(payload['device']):
            raise ValueError('Invalid device ID')
        if not isinstance(payload['license_id'],str) or not LICENSE_ID.fullmatch(payload['license_id']):
            raise ValueError('Invalid license ID')
        start,end=payload['issued_at'],payload['expires_at']
        if type(start) is not int or type(end) is not int or start>=end or end-start>370*86400:
            raise ValueError('Invalid license timestamps')
        public=base64.b64decode(Path(public_path).read_text(encoding='ascii').strip(),validate=True)
        signature=base64.b64decode(data['signature'],validate=True)
        if len(public)!=32 or len(signature)!=64:
            raise ValueError('Invalid Ed25519 lengths')
        content=json.dumps(payload,sort_keys=True,ensure_ascii=True,separators=(',',':')).encode('utf-8')
        Ed25519PublicKey.from_public_bytes(public).verify(signature,content)
    except (InvalidSignature,UnicodeError,ValueError,KeyError,TypeError) as exc:
        raise ValueError('License signature, format or public key invalid') from exc
    return payload,hashlib.sha256(signature).hexdigest()

def record(db,customer_ref,license_file,public_file,payment_status='pending',receipt_ref=None,now=None):
    if payment_status not in PAYMENTS:
        raise ValueError('Unknown payment status')
    if receipt_ref is not None and not REF.fullmatch(receipt_ref):
        raise ValueError('Receipt must be a short non-sensitive reference')
    if payment_status=='confirmed' and not receipt_ref:
        raise ValueError('Manual payment confirmation requires a receipt reference')
    payload,signature_hash=verify_license(license_file,public_file)
    if (payload['plan']=='trial')!=(payment_status=='trial'):
        raise ValueError('Trial license must have trial payment status, and vice versa')
    customer=db.execute('SELECT device FROM customers WHERE customer_ref=?',(customer_ref,)).fetchone()
    if not customer:raise ValueError('Customer must be registered first')
    if customer['device']!=payload['device']:
        raise ValueError('Signed license is for another registered device')
    expiry=db.execute('SELECT MAX(expires_at) AS e FROM licenses WHERE customer_ref=?',
                      (customer_ref,)).fetchone()['e']
    if expiry is not None and payload['expires_at']<expiry:
        raise ValueError('New license expires earlier than existing subscription')
    try:
        with db:
            db.execute('''INSERT INTO licenses(license_id,customer_ref,device,plan,issued_at,
                expires_at,signature_sha256,payment_status,receipt_ref,recorded_at)
                VALUES(?,?,?,?,?,?,?,?,?,?)''',
                (payload['license_id'],customer_ref,payload['device'],payload['plan'],
                 payload['issued_at'],payload['expires_at'],signature_hash,payment_status,
                 receipt_ref,int(time.time()) if now is None else now))
    except sqlite3.IntegrityError as exc:
        raise ValueError('License already recorded; duplicate entries rejected') from exc
    return {'customer_ref':customer_ref,'license_id':payload['license_id'],
            'expires_at':payload['expires_at'],'payment_status':payment_status}

def confirm_payment(db,license_id,receipt_ref):
    if not REF.fullmatch(receipt_ref):
        raise ValueError('Manual payment receipt reference is required')
    with db:
        row=db.execute('SELECT payment_status FROM licenses WHERE license_id=?',(license_id,)).fetchone()
        if not row:raise ValueError('Unknown license ID')
        if row['payment_status']!='pending':
            raise ValueError('Only pending payments can be confirmed')
        db.execute('UPDATE licenses SET payment_status=?,receipt_ref=? WHERE license_id=?',
                   ('confirmed',receipt_ref,license_id))
    return {'license_id':license_id,'payment_status':'confirmed','receipt_ref':receipt_ref}

def subscriptions(db,within_days=None,now=None):
    if within_days is not None and not 0<=within_days<=3650:
        raise ValueError('within-days must be 0..3650')
    ts=int(time.time()) if now is None else now
    rows=db.execute('''SELECT c.customer_ref,c.device,c.created_at,
            l.license_id,l.plan,l.expires_at,l.payment_status,l.receipt_ref
            FROM customers c LEFT JOIN licenses l ON l.license_id=(
                SELECT l2.license_id FROM licenses l2 WHERE l2.customer_ref=c.customer_ref
                ORDER BY l2.expires_at DESC,l2.recorded_at DESC,l2.license_id DESC LIMIT 1)
            ORDER BY c.customer_ref''').fetchall()
    results=[]
    for row in rows:
        item=dict(row)
        item['days_remaining']=((item['expires_at']-ts+86399)//86400
                                if item['expires_at'] is not None else None)
        item['state']=('not_activated' if item['expires_at'] is None else
                       'expired' if item['expires_at']<=ts else
                       'expiring' if item['expires_at']<=ts+7*86400 else 'active')
        if within_days is None or item['expires_at'] is None or item['expires_at']<=ts+within_days*86400:
            results.append(item)
    return results

def export_csv(path,records):
    """Explicit file export; cannot overwrite an existing customer registry."""
    fields=('customer_ref','device','license_id','plan','expires_at','days_remaining',
            'payment_status','receipt_ref','state')
    with Path(path).open('x',newline='',encoding='utf-8-sig') as fd:
        writer=csv.DictWriter(fd,fieldnames=fields,extrasaction='ignore')
        writer.writeheader()
        writer.writerows(records)

def main(argv=None):
    parser=argparse.ArgumentParser(description='LHM Ads AI local seller ledger (no Ads tokens)')
    parser.add_argument('--db',type=Path,default=default_database())
    cmd=parser.add_subparsers(dest='command',required=True)
    reg=cmd.add_parser('register',help='Register a pseudonymous customer/device')
    reg.add_argument('--customer',required=True)
    reg.add_argument('--device',required=True)
    rec=cmd.add_parser('record',help='Verify and track a signed subscription')
    rec.add_argument('--customer',required=True)
    rec.add_argument('--license',required=True,type=Path)
    rec.add_argument('--public',required=True,type=Path)
    rec.add_argument('--payment-status',choices=sorted(PAYMENTS),default='pending')
    rec.add_argument('--receipt')
    paid=cmd.add_parser('confirm-payment',help='Mark paid only after separate bank verification')
    paid.add_argument('--license-id',required=True)
    paid.add_argument('--receipt',required=True)
    cmd.add_parser('list',help='Display latest subscription status for all devices')
    due=cmd.add_parser('due',help='Show renewals due soon')
    due.add_argument('--within-days',type=int,default=7)
    exp=cmd.add_parser('export',help='Export pseudonymous customer/device CSV')
    exp.add_argument('--out',required=True,type=Path)
    args=parser.parse_args(argv)
    try:
        db=connect(args.db)
        try:
            if args.command=='register':result=register(db,args.customer,args.device)
            elif args.command=='record':
                result=record(db,args.customer,args.license,args.public,args.payment_status,args.receipt)
            elif args.command=='confirm-payment':
                result=confirm_payment(db,args.license_id,args.receipt)
            elif args.command=='list':result=subscriptions(db)
            elif args.command=='due':result=subscriptions(db,within_days=args.within_days)
            elif args.command=='export':
                rows=subscriptions(db);export_csv(args.out,rows)
                result={'exported':len(rows),'path':str(args.out)}
            else:raise ValueError('Unknown command')
        finally:db.close()
    except (ValueError,OSError,sqlite3.Error) as exc:
        parser.error(str(exc))
    print(json.dumps(result,ensure_ascii=False,indent=2))

if __name__=='__main__':main()
