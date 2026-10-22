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
import sys
import time
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

sys.path.insert(0, str(Path(__file__).resolve().parent))
try:  # Prefer the package module so tests and the CLI share one instance.
    from tools import payos as payos_module  # noqa: E402
    from tools import einvoice as einvoice_module  # noqa: E402
except ImportError:  # Running as a loose script outside the repo root.
    import payos as payos_module  # noqa: E402  (seller-side dormant PayOS integration)
    import einvoice as einvoice_module  # noqa: E402  (seller-side dormant e-invoice adapter)

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
    # Never chmod an existing --db parent: it may be shared by other tools.
    if not path.parent.exists():
        path.parent.mkdir(parents=True,mode=0o700)
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
    CREATE TABLE IF NOT EXISTS payment_orders(
        order_code INTEGER PRIMARY KEY,
        customer_ref TEXT NOT NULL REFERENCES customers(customer_ref),
        amount INTEGER NOT NULL,
        description TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'pending'
            CHECK(status IN ('pending','paid','cancelled','failed')),
        payment_link_id TEXT,
        checkout_url TEXT,
        reference TEXT,
        created_at INTEGER NOT NULL,
        paid_at INTEGER);
    ''')
    # Idempotent migration for ledgers created before e-invoice support:
    # buyer details captured on the order, plus the issued invoice record.
    existing={row[1] for row in db.execute('PRAGMA table_info(payment_orders)')}
    for column in ('buyer_name','buyer_address','buyer_tax_code','buyer_email',
                   'invoice_no','invoice_series'):
        if column not in existing:
            db.execute(f'ALTER TABLE payment_orders ADD COLUMN {column} TEXT')
    if 'invoice_issued_at' not in existing:
        db.execute('ALTER TABLE payment_orders ADD COLUMN invoice_issued_at INTEGER')
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

def renewal_reminders(db,within_days=7,now=None):
    """Customers whose latest subscription is expired or expiring soon.

    Seller-side only: contains internal customer references, never Ads data.
    """
    rows=subscriptions(db,within_days=within_days,now=now)
    return [{'customer_ref':row['customer_ref'],'license_id':row['license_id'],
             'plan':row['plan'],'state':row['state'],
             'days_remaining':row['days_remaining'],
             'payment_status':row['payment_status']}
            for row in rows
            if row['expires_at'] is not None and row['state'] in ('expired','expiring')]

def format_reminder_message(records):
    lines=['LHM Ads AI — nhắc gia hạn license:']
    for row in records:
        when=('đã hết hạn' if row['state']=='expired'
              else f"còn {row['days_remaining']} ngày")
        lines.append(f"- {row['customer_ref']}: gói {row['plan']}, {when}, "
                     f"thanh toán {row['payment_status']}")
    return '\n'.join(lines)

def send_telegram(text,bot_token,chat_id,opener=None):
    """POST one message to the seller's own Telegram chat (seller machine only)."""
    import urllib.request
    request=urllib.request.Request(
        f'https://api.telegram.org/bot{bot_token}/sendMessage',
        data=json.dumps({'chat_id':chat_id,'text':text}).encode('utf-8'),
        headers={'Content-Type':'application/json'},method='POST')
    open_fn=opener or urllib.request.urlopen
    with open_fn(request,timeout=15) as response:
        payload=json.loads(response.read().decode('utf-8'))
    if not payload.get('ok'):
        raise ValueError('Telegram rejected the reminder message')
    return True

def remind(db,within_days=7,send=False,environ=None,opener=None,now=None):
    records=renewal_reminders(db,within_days=within_days,now=now)
    result={'count':len(records),'reminders':records,'sent':False}
    if not records:
        return result
    message=format_reminder_message(records)
    result['message']=message
    if send:
        env=os.environ if environ is None else environ
        token=env.get('VENDOR_TELEGRAM_BOT_TOKEN','')
        chat_id=env.get('VENDOR_TELEGRAM_CHAT_ID','')
        if not token or not chat_id:
            raise ValueError('Set VENDOR_TELEGRAM_BOT_TOKEN and VENDOR_TELEGRAM_CHAT_ID '
                             'on the seller machine before using --send')
        send_telegram(message,token,chat_id,opener=opener)
        result['sent']=True
    return result

def create_payos_order(db,customer_ref,amount,now=None,order_code=None):
    """Register a pending PayOS order for a known customer (no network here)."""
    if not isinstance(amount,int) or amount<=0:
        raise ValueError('Amount must be a positive integer (VND)')
    customer=db.execute('SELECT device FROM customers WHERE customer_ref=?',
                        (customer_ref,)).fetchone()
    if not customer:raise ValueError('Customer must be registered first')
    ts=int(time.time()) if now is None else now
    code=payos_module.new_order_code(ts) if order_code is None else order_code
    description=(f'LHM Ads AI {customer_ref}')[:payos_module.MAX_DESCRIPTION]
    try:
        with db:
            db.execute('''INSERT INTO payment_orders(order_code,customer_ref,amount,
                description,status,created_at) VALUES(?,?,?,?,'pending',?)''',
                (code,customer_ref,amount,description,ts))
    except sqlite3.IntegrityError as exc:
        raise ValueError('Order code already exists; never overwrite orders') from exc
    return {'order_code':code,'customer_ref':customer_ref,'amount':amount,
            'description':description,'status':'pending'}

def create_payos_link(db,customer_ref,amount,environ=None,transport=None,now=None):
    """Create the order AND its PayOS checkout link. Requires merchant keys;
    raises PayosNotConfigured while the integration is dormant (manual bank
    transfer remains the active flow in that state)."""
    config=payos_module.load_config(environ)
    order=create_payos_order(db,customer_ref,amount,now=now)
    try:
        link=payos_module.create_payment_link(
            config,order_code=order['order_code'],amount=amount,
            description=order['description'],transport=transport)
    except Exception:
        with db:
            db.execute("UPDATE payment_orders SET status='failed' WHERE order_code=?",
                       (order['order_code'],))
        raise
    with db:
        db.execute('''UPDATE payment_orders SET payment_link_id=?,checkout_url=?
            WHERE order_code=?''',
            (link.get('payment_link_id'),link.get('checkout_url'),order['order_code']))
    return {**order,'checkout_url':link.get('checkout_url'),
            'payment_link_id':link.get('payment_link_id')}

def payments(db):
    rows=db.execute('''SELECT order_code,customer_ref,amount,description,status,
        payment_link_id,reference,created_at,paid_at,
        buyer_name,buyer_address,buyer_tax_code,buyer_email,
        invoice_no,invoice_series,invoice_issued_at FROM payment_orders
        ORDER BY created_at DESC,order_code DESC''').fetchall()
    return [dict(row) for row in rows]

def _einvoice_transport(method,url,headers,body):
    """The real HTTP transport for the e-invoice adapter (seller machine
    only, same urllib pattern as send_telegram). The adapter module
    itself performs no network I/O; this is the injected sender."""
    import urllib.request
    request=urllib.request.Request(
        url,data=json.dumps(body,ensure_ascii=False).encode('utf-8'),
        headers=headers,method=method)
    with urllib.request.urlopen(request,timeout=20) as response:
        return json.loads(response.read().decode('utf-8'))

def issue_einvoice(db,order_code,environ=None,issue_fn=None):
    """Issue the e-invoice for a PAID payment order and record the result.

    Gates, in order, and nothing is written before the provider confirms
    issuance: unknown order -> order not 'paid' -> order already invoiced
    -> provider not configured (dormant; EinvoiceNotConfigured propagates
    with the adapter's not-configured message) -> buyer fields the
    provider requires are missing. The ledger `amount` is the
    VAT-inclusive total the customer actually paid, so the invoice line
    is the derived pre-VAT subtotal and the adapter's own total check
    verifies the round-trip (failing closed on rounding drift).
    """
    row=db.execute('SELECT * FROM payment_orders WHERE order_code=?',
                   (order_code,)).fetchone()
    if not row:raise ValueError(f'Không tìm thấy đơn thanh toán với mã {order_code}')
    if row['status']!='paid':
        raise ValueError("Chỉ xuất hóa đơn cho đơn đã thanh toán (trạng thái 'paid'); "
                         f"đơn {order_code} đang ở trạng thái '{row['status']}'")
    if row['invoice_no']:
        raise ValueError(f"Đơn {order_code} đã có hóa đơn số {row['invoice_no']} "
                         f"(ký hiệu {row['invoice_series']}); không xuất lại — "
                         'hủy hoặc thay thế hóa đơn phải làm qua nhà cung cấp.')
    config=einvoice_module.load_config(environ)
    missing=[f'{key} ({label})' for key,label in
             (('buyer_name','tên người mua'),('buyer_address','địa chỉ người mua'))
             if not str(row[key] or '').strip()]
    if missing:
        raise ValueError('Thiếu thông tin bắt buộc để xuất hóa đơn cho đơn '
                         f"{order_code}: {', '.join(missing)}. Bổ sung thông tin "
                         'người mua vào đơn trong sổ rồi chạy lại; chưa ghi thay đổi nào.')
    rate=einvoice_module.DEFAULT_VAT_RATE
    subtotal=(row['amount']*100+(100+rate)//2)//(100+rate)
    order={'order_ref':str(row['order_code']),
           'buyer_name':row['buyer_name'],'buyer_address':row['buyer_address'],
           'buyer_tax_code':row['buyer_tax_code'],'buyer_email':row['buyer_email'],
           'items':[{'name':row['description'],'quantity':1,'unit_price':subtotal}],
           'vat_rate':rate,'total_amount':row['amount']}
    if issue_fn is None:
        issued=einvoice_module.issue_invoice(order,environ=environ,
                                             transport=_einvoice_transport)
    else:
        issued=issue_fn(order,environ=environ)
    if not isinstance(issued,dict) or not str(issued.get('invoice_no') or '').strip():
        raise ValueError('Nhà cung cấp không trả về số hóa đơn; chưa ghi gì vào sổ')
    invoice_no=str(issued['invoice_no']).strip()
    series=str(issued.get('series') or '').strip() or config['series']
    issued_at=issued.get('issued_at')
    if isinstance(issued_at,bool) or not isinstance(issued_at,int) or issued_at<=0:
        issued_at=int(time.time())
    with db:
        db.execute('''UPDATE payment_orders SET invoice_no=?,invoice_series=?,
            invoice_issued_at=? WHERE order_code=?''',
            (invoice_no,series,issued_at,order_code))
    return {'order_code':order_code,'customer_ref':row['customer_ref'],
            'amount':row['amount'],'invoice_no':invoice_no,
            'invoice_series':series,'invoice_issued_at':issued_at}

def apply_payos_webhook(db,payload,checksum_key,now=None):
    """Mark an order paid from a signature-verified webhook.

    This NEVER issues a license: the seller still signs licenses manually
    after seeing the paid order, exactly like a confirmed manual transfer.
    """
    data=payos_module.verify_webhook(payload,checksum_key)
    code=data.get('orderCode')
    row=db.execute('SELECT * FROM payment_orders WHERE order_code=?',(code,)).fetchone()
    if not row:raise ValueError('Webhook references an unknown order code')
    if int(data.get('amount',-1))!=row['amount']:
        raise ValueError('Webhook amount does not match the recorded order amount')
    if row['status']=='paid':
        return {'order_code':code,'status':'paid','already_paid':True,
                'customer_ref':row['customer_ref']}
    ts=int(time.time()) if now is None else now
    with db:
        db.execute("UPDATE payment_orders SET status='paid',paid_at=?,reference=? WHERE order_code=?",
                   (ts,str(data.get('reference',''))[:80] or None,code))
    return {'order_code':code,'status':'paid','already_paid':False,
            'customer_ref':row['customer_ref'],'amount':row['amount']}

def export_csv(path,records):
    """Explicit file export; cannot overwrite an existing customer registry."""
    fields=('customer_ref','device','license_id','plan','expires_at','days_remaining',
            'payment_status','receipt_ref','state')
    with Path(path).open('x',newline='',encoding='utf-8-sig') as fd:
        writer=csv.DictWriter(fd,fieldnames=fields,extrasaction='ignore')
        writer.writeheader()
        writer.writerows(records)

def backup_database(db,out_path):
    """Make a consistent SQLite backup without overwriting any earlier backup."""
    destination=Path(out_path).expanduser().resolve()
    if not destination.parent.is_dir():
        raise ValueError('Backup destination directory must exist')
    fd=os.open(destination,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600)
    os.close(fd)
    try:
        with sqlite3.connect(destination) as copy:
            db.backup(copy)
        if os.name!='nt':os.chmod(destination,0o600)
    except Exception:
        destination.unlink(missing_ok=True)
        raise
    return {'backup':str(destination),'contains_ads_tokens':False}

def _force_utf8_streams():
    # Windows consoles/pipes default to a legacy codepage (cp1252/cp437)
    # that cannot encode Vietnamese; these CLIs print Vietnamese status
    # text, so pin stdout/stderr to UTF-8 when the runtime allows it.
    import sys as _sys
    for stream in (_sys.stdout, _sys.stderr):
        try:
            stream.reconfigure(encoding='utf-8', errors='replace')
        except (AttributeError, ValueError):
            pass

def main(argv=None):
    _force_utf8_streams()
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
    backup=cmd.add_parser('backup',help='Consistent offline SQLite backup; never overwrites')
    backup.add_argument('--out',required=True,type=Path)
    exp=cmd.add_parser('export',help='Export pseudonymous customer/device CSV')
    exp.add_argument('--out',required=True,type=Path)
    rem=cmd.add_parser('remind',help='List expired/expiring subscriptions; optionally send one Telegram reminder to the seller')
    rem.add_argument('--within-days',type=int,default=7)
    rem.add_argument('--send',action='store_true',
                     help='Send via Telegram using VENDOR_TELEGRAM_BOT_TOKEN/VENDOR_TELEGRAM_CHAT_ID')
    cmd.add_parser('payos-status',help='Show whether PayOS merchant keys are configured (never prints secrets)')
    pc=cmd.add_parser('payos-create',help='Create a PayOS payment link for a registered customer (needs merchant keys)')
    pc.add_argument('--customer',required=True)
    pc.add_argument('--amount',required=True,type=int)
    cmd.add_parser('payments',help='List PayOS payment orders and their status')
    cmd.add_parser('einvoice-status',help='Show whether the e-invoice provider is configured (never prints secrets)')
    ei=cmd.add_parser('einvoice-issue',help='Issue the e-invoice for a PAID payment order and record its number/series (needs provider config)')
    ei.add_argument('--order',required=True,type=int,help='Payment order code (see: payments)')
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
            elif args.command=='backup':result=backup_database(db,args.out)
            elif args.command=='export':
                rows=subscriptions(db);export_csv(args.out,rows)
                result={'exported':len(rows),'path':str(args.out)}
            elif args.command=='remind':
                result=remind(db,within_days=args.within_days,send=args.send)
            elif args.command=='payos-status':
                result={'payos_configured':payos_module.is_configured(),
                        'manual_flow':'Chuyển khoản tài khoản bên bán, xác nhận tay rồi mới cấp license'}
            elif args.command=='payos-create':
                result=create_payos_link(db,args.customer,args.amount)
            elif args.command=='payments':result=payments(db)
            elif args.command=='einvoice-status':
                result={'einvoice_configured':einvoice_module.is_configured(),
                        'note':'Chỉ xuất hóa đơn sau khi đã xác nhận tiền trong sổ; xem docs/EINVOICE.md'}
            elif args.command=='einvoice-issue':
                result=issue_einvoice(db,args.order)
            else:raise ValueError('Unknown command')
        finally:db.close()
    except (ValueError,OSError,sqlite3.Error,
            payos_module.PayosNotConfigured,payos_module.PayosError,
            einvoice_module.EinvoiceNotConfigured,
            einvoice_module.EinvoiceError) as exc:
        parser.error(str(exc))
    print(json.dumps(result,ensure_ascii=False,indent=2))

if __name__=='__main__':main()
