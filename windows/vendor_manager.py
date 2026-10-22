"""Private seller Windows console. NEVER include in customer EXE.

Only internal customer reference and device ID are collected. Seller confirms
real payment independently in their bank and explicitly checks its box. The
app does NOT connect to banks, Ads APIs, payment gateways, or any cloud.
"""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import sys
import time
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, simpledialog

if not getattr(sys,'frozen',False):
    sys.path.insert(0,str(Path(__file__).resolve().parents[1]))

from tools import vendor_ledger as ledger
from tools import vendor_sales as sales
from tools import vendor_backup as vault

BG='#F2F5FA'
SURFACE='#FFFFFF'
DARK='#13223A'
MUTED='#64748B'
BLUE='#2463EB'
SUCCESS='#168452'
BORDER='#DCE4EE'


def _created_session() -> None:
    """Dependency check without generating keys, touching disk or printing data."""
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    assert len(Ed25519PrivateKey.generate().private_bytes_raw()) == 32


class VendorWindow(tk.Tk):
    def __init__(self,window_smoke=False):
        super().__init__()
        self.title('LHM Ads AI | Quản lý bản quyền — Bên bán')
        self.geometry('1160x740')
        self.minsize(960,610)
        self.configure(bg=BG)
        self.window_smoke=window_smoke
        self.customer=tk.StringVar()
        self.device=tk.StringVar()
        self.receipt=tk.StringVar()
        self.passphrase=tk.StringVar()
        self.payment_verified=tk.BooleanVar(value=False)
        self.stats=tk.StringVar(value='Chưa tải dữ liệu')
        self.notice=tk.StringVar(value='Chỉ tạo license sau khi đã xác minh tiền vào ngân hàng.')
        self._make_styles()
        self._make_page()
        self.refresh()
        if window_smoke:
            self.after(1100,self.destroy)

    def _make_styles(self):
        st=ttk.Style(self)
        st.theme_use('clam')
        st.configure('Sales.Treeview',background=SURFACE,foreground=DARK,
                     fieldbackground=SURFACE,rowheight=37,borderwidth=0,
                     font=('Segoe UI',10))
        st.configure('Sales.Treeview.Heading',background='#E9F0FC',
                     foreground=DARK,font=('Segoe UI Semibold',10),
                     padding=10,borderwidth=0)
        st.map('Sales.Treeview',background=[('selected','#DBEAFE')],
               foreground=[('selected',DARK)])

    def _label(self,parent,text,**kwargs):
        return tk.Label(parent,text=text,font=('Segoe UI',10),
                        bg=kwargs.get('bg',SURFACE),
                        fg=kwargs.get('fg',DARK),anchor='w')

    def _entry(self,parent,variable,show=None):
        ent=tk.Entry(parent,textvariable=variable,show=show,
                     font=('Segoe UI',11),relief='solid',bd=1,
                     highlightthickness=1,highlightbackground=BORDER,
                     highlightcolor=BLUE,fg=DARK,bg='#FFFFFF')
        return ent

    def _button(self,parent,text,command,primary=False):
        c=BLUE if primary else '#E8EEF8'
        f='#FFFFFF' if primary else DARK
        return tk.Button(parent,text=text,command=command,bd=0,bg=c,fg=f,
                         activebackground='#194FBE' if primary else '#D5E2F6',
                         activeforeground='#FFFFFF' if primary else DARK,
                         cursor='hand2',font=('Segoe UI Semibold',10),
                         padx=18,pady=12)

    def _make_page(self):
        head=tk.Frame(self,bg=DARK,height=90)
        head.pack(fill='x')
        tk.Label(head,text='LHM  /  ADS AI',font=('Segoe UI Semibold',18),
                 fg='white',bg=DARK).pack(side='left',padx=(24,12),pady=22)
        tk.Label(head,text='SELLER CONSOLE  •  CHỈ TRÊN MÁY BÊN BÁN',
                 font=('Segoe UI',10),fg='#A9C0DF',bg=DARK).pack(side='left')
        self._button(head,'↻  Làm mới',self.refresh).pack(side='right',padx=25)

        pad=tk.Frame(self,bg=BG)
        pad.pack(fill='both',expand=True,padx=23,pady=19)
        stat=tk.Frame(pad,bg=SURFACE,highlightbackground=BORDER,
                      highlightthickness=1)
        stat.pack(fill='x',pady=(0,14))
        tk.Label(stat,textvariable=self.stats,bg=SURFACE,fg=DARK,
                 font=('Segoe UI Semibold',12)).pack(anchor='w',padx=17,pady=14)
        body=tk.Frame(pad,bg=BG)
        body.pack(fill='both',expand=True)

        left=tk.Frame(body,bg=SURFACE,highlightbackground=BORDER,
                      highlightthickness=1)
        left.pack(side='left',fill='both',expand=True,padx=(0,14))
        top=tk.Frame(left,bg=SURFACE)
        top.pack(fill='x',padx=18,pady=(18,13))
        tk.Label(top,text='Khách hàng & hạn bản quyền',
                 font=('Segoe UI Semibold',14),bg=SURFACE,fg=DARK).pack(side='left')
        self._button(top,'Sao lưu mã hóa',self.backup).pack(side='right')
        self._button(top,'Khôi phục',self.restore_backup).pack(side='right',padx=(0,7))
        self._button(top,'Xuất CSV',self.export_csv).pack(side='right',padx=(0,7))
        columns=('customer','device','state','remaining','payment')
        self.tree=ttk.Treeview(left,columns=columns,show='headings',
                               style='Sales.Treeview',selectmode='browse')
        for key,title,width in [('customer','Mã khách',130),
                                ('device','Mã máy (rút gọn)',155),
                                ('state','Trạng thái',115),
                                ('remaining','Còn lại',100),
                                ('payment','Thanh toán',110)]:
            self.tree.heading(key,text=title)
            self.tree.column(key,width=width,anchor='w',stretch=key=='customer')
        scroll=ttk.Scrollbar(left,orient='vertical',command=self.tree.yview)
        self.tree.configure(yscrollcommand=scroll.set)
        scroll.pack(side='right',fill='y',pady=(0,12))
        self.tree.pack(fill='both',expand=True,padx=(14,0),pady=(0,12))
        self.tree.bind('<<TreeviewSelect>>',self.on_select)

        right=tk.Frame(body,bg=SURFACE,width=390,highlightbackground=BORDER,
                       highlightthickness=1)
        right.pack(side='right',fill='y')
        right.pack_propagate(False)
        fields=tk.Frame(right,bg=SURFACE)
        fields.pack(fill='x',padx=19,pady=(18,0))
        tk.Label(fields,text='Đăng ký / cấp license 30 ngày',
                 font=('Segoe UI Semibold',14),bg=SURFACE,fg=DARK).pack(anchor='w')
        self._label(fields,'Mã khách (VD: KH001)').pack(anchor='w',pady=(16,3))
        self._entry(fields,self.customer).pack(fill='x',ipady=8)
        self._label(fields,'Mã máy 32 ký tự hex').pack(anchor='w',pady=(11,3))
        self._entry(fields,self.device).pack(fill='x',ipady=8)
        self._button(fields,'+ Đăng ký khách / mã máy',self.register).pack(fill='x',pady=(10,14))
        tk.Frame(fields,bg=BORDER,height=1).pack(fill='x')
        self._label(fields,'Mã biên nhận nội bộ (VD: TT-KH001-001)').pack(anchor='w',pady=(12,3))
        self._entry(fields,self.receipt).pack(fill='x',ipady=8)
        self._label(fields,'Mật khẩu khóa riêng LHM (không lưu)').pack(anchor='w',pady=(11,3))
        self._entry(fields,self.passphrase,show='•').pack(fill='x',ipady=8)
        tk.Checkbutton(fields,text='Tôi đã đối chiếu tiền thật vào ngân hàng',
                       variable=self.payment_verified,bg=SURFACE,
                       activebackground=SURFACE,fg=DARK,
                       selectcolor='#E7F0FD',font=('Segoe UI',10),
                       wraplength=330,justify='left').pack(fill='x',pady=(13,5))
        self._button(fields,'Ký & cấp / gia hạn 30 ngày',self.issue,True).pack(fill='x',pady=8)
        self._label(fields,'Không tự thu tiền hoặc sửa Ads. Gia hạn được cộng dồn.',
                    fg=MUTED).pack(anchor='w',pady=(3,0))
        foot=tk.Frame(pad,bg=BG)
        foot.pack(fill='x',pady=(12,0))
        tk.Label(foot,textvariable=self.notice,fg=MUTED,bg=BG,
                 font=('Segoe UI',10),anchor='w',
                 wraplength=1060,justify='left').pack(fill='x')

    def _db(self):
        return ledger.connect(ledger.default_database())

    def refresh(self):
        try:
            db=self._db()
            try:
                records=ledger.subscriptions(db)
            finally:
                db.close()
            self.tree.delete(*self.tree.get_children())
            for record in records:
                remaining=record['days_remaining']
                remain_label='Chưa cấp' if remaining is None else f'{remaining} ngày'
                state={'not_activated':'Chưa cấp',
                       'expired':'Hết hạn','expiring':'Sắp hết','active':'Đang dùng'}[record['state']]
                self.tree.insert('',tk.END,iid=record['customer_ref'],
                                 values=(record['customer_ref'],
                                         record['device'][:10]+'…'+record['device'][-4:],
                                         state,remain_label,
                                         record['payment_status'] or '—'))
            active=sum(x['state']=='active' for x in records)
            due=sum(x['state'] in ('expiring','expired') for x in records)
            self.stats.set(f'{len(records)} khách hàng       •       {active} đang dùng       •       {due} cần gia hạn')
            self.notice.set('Sổ khách hàng chỉ nằm trên máy bên bán. Không chứa token Google/Meta.')
        except Exception as exc:
            self.notice.set('Không thể đọc sổ: '+str(exc))
            messagebox.showerror('Lỗi dữ liệu',str(exc),parent=self)

    def on_select(self,event=None):
        selection=self.tree.selection()
        if not selection:
            return
        ref=selection[0]
        db=self._db()
        try:
            row=db.execute('SELECT device FROM customers WHERE customer_ref=?',
                           (ref,)).fetchone()
        finally:
            db.close()
        if row:
            self.customer.set(ref)
            self.device.set(row['device'])
            self.receipt.set('')
            self.payment_verified.set(False)

    def register(self):
        db=self._db()
        try:
            result=ledger.register(db,self.customer.get().strip(),
                                   self.device.get().strip())
            self.notice.set(f"Đã đăng ký {result['customer_ref']} — chờ xác nhận thanh toán.")
            self.refresh()
        except Exception as exc:
            messagebox.showerror('Không thể đăng ký',str(exc),parent=self)
        finally:
            db.close()

    def issue(self):
        password=self.passphrase.get()
        self.passphrase.set('')
        try:
            result=sales.issue_paid_license(
                customer_ref=self.customer.get().strip(),
                receipt_ref=self.receipt.get().strip(),
                passphrase=password,
                private_file=sales.vendor_keys_dir()/'vendor-private-key.pem',
                public_file=sales.vendor_keys_dir()/'vendor-public.b64',
                db_path=ledger.default_database(),
                license_directory=sales.vendor_license_dir(),
                payment_confirmed=self.payment_verified.get(),
            )
        except Exception as exc:
            messagebox.showerror('Chưa thể cấp license',str(exc),parent=self)
            return
        self.payment_verified.set(False)
        self.receipt.set('')
        self.refresh()
        self.notice.set('Cấp thành công: '+result['path'])
        messagebox.showinfo('Đã cấp / gia hạn 30 ngày',
                            'Đã ký bản quyền cho '+result['customer_ref']+
                            '\nHạn tới: '+result['expires_at_utc']+
                            '\n\nGửi file JSON sau cho khách:\n'+result['path']+
                            '\n\nĐừng gửi file private key của bên bán.',parent=self)

    def export_csv(self):
        name='lhm-customers-'+time.strftime('%Y%m%d-%H%M%S')+'.csv'
        path=filedialog.asksaveasfilename(parent=self,title='Xuất danh sách nội bộ',
              defaultextension='.csv',initialfile=name,
              filetypes=[('CSV','*.csv')])
        if not path:return
        try:
            db=self._db()
            try: ledger.export_csv(path,ledger.subscriptions(db))
            finally: db.close()
            messagebox.showinfo('Đã xuất CSV',path,parent=self)
        except Exception as exc:
            messagebox.showerror('Không thể xuất CSV',str(exc),parent=self)

    def backup(self):
        """Never export plaintext customer ledger by the seller GUI."""
        name='lhm-vendor-'+time.strftime('%Y%m%d-%H%M%S')+'.lhmvault'
        path=filedialog.asksaveasfilename(parent=self,title='Sao lưu MÃ HÓA sổ và toàn bộ license',
             defaultextension='.lhmvault',initialfile=name,
             filetypes=[('LHM encrypted seller backup','*.lhmvault')])
        if not path:return
        password=simpledialog.askstring('Mật khẩu sao lưu',
             'Nhập mật khẩu MỚI ít nhất 16 ký tự; cất riêng với file backup.',
             parent=self,show='•')
        if password is None:return
        confirm=simpledialog.askstring('Xác nhận mật khẩu sao lưu',
             'Nhập lại mật khẩu mã hóa .lhmvault:',parent=self,show='•')
        if confirm is None:return
        if password != confirm:
            messagebox.showerror('Sao lưu bị từ chối',
                'Hai mật khẩu không trùng; chưa tạo bản sao lưu.',parent=self)
            return
        try:
            info=vault.export_vault(
                db_path=ledger.default_database(),
                license_dir=sales.vendor_license_dir(),
                public_file=sales.vendor_keys_dir()/'vendor-public.b64',
                destination=Path(path),password=password)
            messagebox.showinfo('Sao lưu mã hóa thành công',
                'Đã lưu sổ + '+str(info['licenses'])+' license tại:\n'+path+
                '\n\nKHÔNG bao gồm private key. Phải sao lưu riêng private key đã mã hóa '
                'và mật khẩu. Cất backup ở ổ riêng, không gửi GitHub.',parent=self)
            self.notice.set('Sổ và license đã được bảo vệ bằng backup mã hóa.')
        except Exception as exc:
            messagebox.showerror('Không thể sao lưu',str(exc),parent=self)

    def restore_backup(self):
        """Recover into a NEW directory only; do not mutate live seller data."""
        source=filedialog.askopenfilename(parent=self,title='Chọn backup mã hóa',
             filetypes=[('LHM encrypted seller backup','*.lhmvault')])
        if not source:return
        parent=filedialog.askdirectory(parent=self,
             title='Chọn thư mục CHA chứa dữ liệu KHÔI PHỤC (ngoài nơi đang dùng)')
        if not parent:return
        directory=Path(parent).expanduser().resolve()
        live=sales.vendor_keys_dir().parent.resolve()
        if directory==live or directory.is_relative_to(live):
            messagebox.showerror('Từ chối ghi đè',
                'Không khôi phục vào hoặc bên trong thư mục bên bán đang dùng. '
                'Chọn ổ/thư mục khác để kiểm chứng dữ liệu.',parent=self)
            return
        target=directory/('LHMAdsAI-Vendor-RESTORED-'+time.strftime('%Y%m%d-%H%M%S'))
        password=simpledialog.askstring('Mật khẩu khôi phục',
             'Nhập mật khẩu của file .lhmvault (không phải mật khẩu login):',
             parent=self,show='•')
        if password is None:return
        try:
            info=vault.restore_vault(
                vault=Path(source),password=password,target=target,
                trusted_public_file=sales.vendor_keys_dir()/'vendor-public.b64')
            messagebox.showinfo('Khôi phục đã kiểm chứng',
                'Đã khôi phục '+str(info['licenses'])+' license và sổ tại:\n'+
                str(target)+'\n\nDỮ LIỆU ĐANG DÙNG CHƯA THAY ĐỔI.\n'
                'Muốn chuyển máy, cần khôi phục riêng private key GỐC và làm '
                'theo hướng dẫn hỗ trợ; không tạo khóa mới.',parent=self)
            self.notice.set('Khôi phục vào thư mục mới, chưa thay đổi sổ hiện tại.')
        except Exception as exc:
            messagebox.showerror('Không thể khôi phục',str(exc),parent=self)


def main(argv=None):
    parser=argparse.ArgumentParser(description='LHM Ads AI PRIVATE vendor license manager')
    parser.add_argument('--self-test',action='store_true',
                        help='CI only: check dependencies, do not touch customer data')
    parser.add_argument('--window-smoke',action='store_true',
                        help='CI only: open and close vendor GUI automatically')
    args=parser.parse_args(argv)
    if args.self_test:
        _created_session()
        print('PASS: vendor Ed25519 engine ready (no keys read/written)')
        return
    window=VendorWindow(window_smoke=args.window_smoke)
    window.mainloop()

if __name__=='__main__':
    main()
