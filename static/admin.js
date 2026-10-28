'use strict';let data={customers:[],orders:[],licenses:[],audit:[],plans:[]};
const $=x=>document.getElementById(x),fmt=x=>new Intl.NumberFormat('vi-VN').format(x||0);
const el=(tag,t,cls)=>{const n=document.createElement(tag);n.textContent=String(t??'');if(cls)n.className=cls;return n;};
const day=s=>s?new Date(String(s).replace(' ','T')+(/Z|[+-]\d\d:?\d\d$/.test(s)?'':'Z')).toLocaleDateString('vi-VN'):'—';
const when=s=>s?new Date(String(s).replace(' ','T')+(/Z|[+-]\d\d:?\d\d$/.test(s)?'':'Z')).toLocaleString('vi-VN'):'—';
const willExpireSoon=l=>l.status==='active'&&Date.parse(l.expires_at)>Date.now()&&Date.parse(l.expires_at)-Date.now()<=7*86400000;
const SOURCE={self_service:'Khách tự đặt',admin_grant:'Admin cấp',pilot_migration:'Chuyển pilot',admin:'Admin tạo'};
const STATUS={pending:'Chờ tiền',paid:'Đã thanh toán',cancelled:'Đã huỷ'};
function msg(s,error=false){
 const n=$('message');n.textContent=s;n.className='show'+(error?' error':'');
 n.setAttribute('role',error?'alert':'status');
}
async function api(path,payload,method){
 const opts=payload===undefined?{}:{method:method||'POST',headers:{'content-type':'application/json'},body:JSON.stringify(payload)};
 const r=await fetch('/api/admin/'+path,{credentials:'same-origin',cache:'no-store',...opts});
 let x;try{x=await r.json()}catch{x={error:'Server did not return JSON'}}
 if(!r.ok){
  if(r.status===401)throw Error('Bạn chưa được xác thực hoặc chưa có quyền quản trị qua Cloudflare Access.');
  if(r.status===503)throw Error('API quản trị chưa kết nối Cloudflare D1 hoặc cấu hình môi trường còn thiếu.');
  throw Error(x.error||'Yêu cầu không thực hiện được (HTTP '+r.status+').');
 }
 return x;
}
function cells(tbody,values){const tr=document.createElement('tr');values.forEach(v=>tr.append(v instanceof Node?wrap(v):el('td',v)));tbody.append(tr);return tr;}
function wrap(node){const td=document.createElement('td');td.append(node);return td;}
function button(label,onclick,cls){const b=el('button',label,cls);b.type='button';b.onclick=onclick;return b;}
function gmail(email,linked){
 const span=el('span',email);
 const tag=el('small',linked?' ✓ đã đăng nhập':' ⚠ chưa đăng nhập',linked?'tag-success admin-tag':'tag-pending admin-tag');
 tag.title=linked?'Gmail đã xác minh với Google':'Khách chưa đăng nhập Gmail này lần nào; kiểm tra chính tả';
 const box=document.createElement('span');box.append(span,tag);return box;
}
const planName=code=>data.plans.find(p=>p.code===code)?.name||code||'Tuỳ chỉnh';
async function act(label,fn){
 try{await fn();msg(label);await refresh();}catch(e){msg(e.message,true);}
}
function filterTable(kind){
 const table=$(kind+'-list'),input=$(kind+'-search'),empty=$(kind+'-empty');
 if(!table||!input||!empty)return;
 const q=input.value.trim().toLocaleLowerCase('vi');let count=0;
 for(const tr of table.querySelectorAll('tr')){const show=tr.textContent.toLocaleLowerCase('vi').includes(q);tr.hidden=!show;if(show)count++;}
 empty.hidden=count>0;
}

/* Đơn chờ */
let reviewingOrderId='';
function openActivate(order){
 reviewingOrderId=order.id;
 $('payment-review-form').reset();
 $('payment-dialog-caption').textContent='Mã CK '+(order.payment_code||order.id.slice(0,8))+' · '+order.customer_email+
  ' · '+planName(order.plan_code)+' · '+fmt(order.amount_vnd)+'đ. Chỉ bấm kích hoạt khi app ngân hàng đã có giao dịch đúng mã và đủ số tiền.';
 $('payment-dialog').showModal();$('payment-reference').focus();
}
function renderOrders(){
 const pending=data.orders.filter(x=>x.status==='pending');
 $('order-list').replaceChildren();
 for(const x of pending){
  cells($('order-list'),[x.payment_code||x.id.slice(0,8),gmail(x.customer_email,x.customer_linked),
   planName(x.plan_code)+' · '+(x.seat_limit||1)+' máy',fmt(x.amount_vnd)+'đ',when(x.created_at),
   button('Duyệt & kích hoạt',()=>openActivate(x),'primary-action')]);
 }
 $('order-empty').hidden=pending.length>0;
 $('history-list').replaceChildren();
 for(const x of data.orders.filter(o=>o.status!=='pending').slice(0,30))
  cells($('history-list'),[x.payment_code||x.id.slice(0,8),x.customer_email,planName(x.plan_code),fmt(x.amount_vnd)+'đ',STATUS[x.status]||x.status,SOURCE[x.source]||x.source||'']);
 filterTable('order');
}

/* Khách hàng */
function renderCustomers(rows){
 $('customer-list').replaceChildren();
 for(const x of rows){
  // Search results carry the active plan inline; the overview list is matched against licenses.
  const lic='expires_at' in x?(x.expires_at?x:null):data.licenses.find(l=>l.customer_id===x.id&&l.status==='active');
  cells($('customer-list'),[x.name,gmail(x.email,x.linked),lic?.plan_code?planName(lic.plan_code):(lic?'Có gói':'—'),
   lic?day(lic.expires_at):'—',x.status==='blocked'?'Đang khoá':'Hoạt động',button('Xem',()=>openCustomer(x.id))]);
 }
 $('customer-empty').hidden=rows.length>0;
}
let currentCustomer=null;
async function openCustomer(id){
 try{
  const d=await api('customers/'+id);currentCustomer=d;
  const c=d.customer,active=d.licenses.find(l=>l.status==='active'&&Date.parse(l.expires_at)>Date.now());
  $('cd-name').textContent=c.name;
  $('cd-email').replaceChildren(gmail(c.email,c.linked));
  $('cd-plan').textContent=active?planName(active.plan_code)+' · tối đa '+active.seat_limit+' máy · hết hạn '+day(active.expires_at)
   :'Không có gói đang hoạt động'+(d.licenses[0]?' (gói gần nhất: '+(d.licenses[0].status==='revoked'?'đã thu hồi':'hết hạn '+day(d.licenses[0].expires_at))+')':'');
  const planActions=$('cd-plan-actions');planActions.replaceChildren();
  planActions.append(button('Gia hạn / cấp gói',()=>{
   const f=$('grant-form');f.reset();f.email.value=c.email;f.confirm_email.value=c.email;f.name.value=c.name;
   document.querySelector('[data-tab="grant"]').click();syncGrant();f.reference.focus();
  }));
  if(active){
   planActions.append(button('Chuyển gói sang Gmail khác',()=>transfer(active.id,c.email)));
   planActions.append(button('Thu hồi gói',()=>{if(confirm('Thu hồi gói của '+c.email+'? Phần mềm của khách sẽ khoá ngay ở lần kiểm tra tiếp theo.'))
     act('Đã thu hồi gói',()=>api('licenses/revoke',{license_id:active.id})).then(()=>openCustomer(id));},'danger'));
  }
  $('cd-status').textContent=(c.status==='blocked'?'Đang khoá':'Hoạt động')+' · '+(c.linked?'đã liên kết Google':'chưa đăng nhập Google')+(c.phone?' · '+c.phone:'');
  const acc=$('cd-account-actions');acc.replaceChildren();
  acc.append(c.status==='blocked'
   ?button('Mở khoá tài khoản',()=>act('Đã mở khoá',()=>api('customers/'+id+'/unblock',{})).then(()=>openCustomer(id)))
   :button('Khoá tài khoản',()=>{const reason=prompt('Lý do khoá '+c.email+':');if(reason!==null)
     act('Đã khoá và đăng xuất mọi máy',()=>api('customers/'+id+'/block',{reason})).then(()=>openCustomer(id));},'danger'));
  acc.append(button('Đăng xuất mọi máy',()=>{if(confirm('Đăng xuất '+c.email+' trên mọi máy?'))
   act('Đã đăng xuất mọi máy',()=>api('customers/'+id+'/signout-all',{})).then(()=>openCustomer(id));}));
  if(c.linked)acc.append(button('Gỡ liên kết Google',()=>{
   const reason=prompt('Chỉ gỡ khi đã xác minh khách là chủ Gmail (ví dụ khách tạo lại tài khoản Google). Lý do:');
   if(reason)act('Đã gỡ liên kết; lần đăng nhập tới sẽ gắn lại Google ID',()=>api('customers/'+id+'/unlink-google',{reason})).then(()=>openCustomer(id));}));
  $('cd-devices').replaceChildren();
  for(const s of d.devices)cells($('cd-devices'),[s.device_label||'—',s.platform==='windows'?'PC Windows':'PWA',when(s.last_seen_at),
   button('Đá máy',()=>act('Đã đăng xuất máy',()=>api('seats/kick',{license_id:s.license_id,device_id:s.id})).then(()=>openCustomer(id)))]);
  if(!d.devices.length)cells($('cd-devices'),['Không có máy nào đang dùng','','','']);
  $('cd-orders').replaceChildren();
  for(const o of d.orders)cells($('cd-orders'),[o.payment_code||o.id.slice(0,8),STATUS[o.status]||o.status,fmt(o.amount_vnd)+'đ',
   o.days?o.days+' ngày':o.months+' tháng',SOURCE[o.source]||o.source||'',o.reference||'',day(o.created_at)]);
  $('cd-notes').replaceChildren(...d.notes.map(n=>el('li',when(n.at)+' · '+n.note)));
  $('customer-detail').hidden=false;$('customer-detail').scrollIntoView({behavior:'smooth',block:'start'});
 }catch(e){msg(e.message,true);}
}
function transfer(licenseId,from){
 const to=prompt('Chuyển gói của '+from+' sang Gmail:');if(!to)return;
 const again=prompt('Nhập lại Gmail nhận gói:');if(again===null)return;
 const reason=prompt('Lý do (ví dụ: gõ nhầm Gmail lúc cấp):')||'';
 act('Đã chuyển gói sang '+to,()=>api('licenses/'+licenseId+'/transfer',{to_email:to,confirm_email:again,reason}))
  .then(()=>currentCustomer&&openCustomer(currentCustomer.customer.id));
}

/* Cấp gói */
function syncGrant(){
 const custom=$('grant-plan').value==='';
 document.querySelectorAll('.grant-custom').forEach(n=>n.hidden=!custom);
}
function renderPlansSelect(){
 const s=$('grant-plan'),keep=s.value;s.replaceChildren();
 for(const p of data.plans){const o=el('option',p.name+' · '+p.seat_limit+' máy · '+p.months+' tháng'+(p.active?'':' (đang tắt)'));o.value=p.code;s.append(o);}
 const custom=el('option','Tuỳ chỉnh (tự nhập số máy và số ngày)');custom.value='';s.append(custom);
 // Keep the admin's choice across refreshes; default to the first real plan, never "custom".
 if(keep&&[...s.options].some(o=>o.value===keep))s.value=keep;
 else if(data.plans.length)s.value=(data.plans.find(p=>p.active)||data.plans[0]).code;
 syncGrant();
}

/* Sắp hết hạn */
async function renderExpiring(){
 const r=await api('expiring?days=7');
 $('expiring-list').replaceChildren();
 for(const l of r.licenses){
  const left=Math.max(0,Math.ceil((Date.parse(l.expires_at)-Date.now())/86400000));
  const text='Chào '+l.name+', gói LHM Ads AI của Gmail '+l.email+' sẽ hết hạn ngày '+day(l.expires_at)+
   '. Anh/chị vào https://ads.lhmcrm.com/local/ → Cài đặt → Gia hạn gói để không bị gián đoạn. Cảm ơn anh/chị!';
  cells($('expiring-list'),[l.name,l.email,l.phone||'—',day(l.expires_at),left+' ngày',
   button('Sao chép tin nhắn',()=>navigator.clipboard.writeText(text).then(()=>msg('Đã sao chép tin nhắn nhắc gia hạn')).catch(()=>msg(text)))]);
 }
 $('expiring-empty').hidden=r.licenses.length>0;
}

/* Bảng giá */
function planRow(p){
 const tr=document.createElement('tr');
 const input=(name,value,type='text',attrs={})=>{const i=document.createElement('input');i.name=name;i.type=type;i.value=value??'';
  Object.assign(i,attrs);i.setAttribute('aria-label',name);return i;};
 const code=input('code',p.code,'text',{readOnly:Boolean(p.code),pattern:'[a-z0-9-]{2,40}'});
 const fields=[code,input('name',p.name),input('seat_limit',p.seat_limit??2,'number',{min:1,max:20}),
  input('months',p.months??1,'number',{min:1,max:36}),input('price_vnd',p.price_vnd??0,'number',{min:0}),
  input('active','', 'checkbox',{checked:Boolean(p.active)}),input('sort',p.sort??0,'number')];
 for(const f of fields)tr.append(wrap(f));
 tr.append(wrap(button('Lưu',()=>{
  const v=Object.fromEntries(fields.map(f=>[f.name,f.type==='checkbox'?f.checked:f.type==='number'?Number(f.value):f.value.trim()]));
  if(v.active&&!v.price_vnd){msg('Gói đang bật phải có giá lớn hơn 0',true);return;}
  act('Đã lưu gói '+v.code,()=>api('plans',v,'PUT'));
 })));
 return tr;
}
function renderPlans(){$('plan-list').replaceChildren(...data.plans.map(planRow));renderPlansSelect();}

function render(){
 $('m-customers').textContent=data.customers.length;
 $('m-orders').textContent=data.orders.filter(x=>x.status==='pending').length;
 $('m-licenses').textContent=data.licenses.filter(x=>x.status==='active'&&new Date(x.expires_at)>new Date()).length;
 $('m-expiring').textContent=data.licenses.filter(willExpireSoon).length;
 renderOrders();
 if(!$('customer-search').value.trim())renderCustomers(data.customers);
 renderPlans();
 $('audit-list').replaceChildren();data.audit.forEach(x=>cells($('audit-list'),[when(x.at),x.actor,x.action,x.target_id,x.detail||'']));
 filterTable('audit');
}
async function refresh(){
 const b=$('refresh-admin');b.disabled=true;b.textContent='Đang cập nhật…';
 try{data=await api('overview');$('unavailable').hidden=true;$('workspace').hidden=false;render();}
 finally{b.disabled=false;b.textContent='↻ Làm mới dữ liệu';}
}

document.querySelectorAll('nav button').forEach(b=>b.addEventListener('click',()=>{
 document.querySelectorAll('nav button').forEach(n=>n.removeAttribute('aria-current'));b.setAttribute('aria-current','page');
 document.querySelectorAll('.view').forEach(n=>n.classList.toggle('active',n.id===b.dataset.tab));
 if(b.dataset.tab==='expiring')renderExpiring().catch(e=>msg(e.message,true));
}));
$('customer-search-form').addEventListener('submit',async e=>{
 e.preventDefault();const q=$('customer-search').value.trim();
 if(!q){renderCustomers(data.customers);return;}
 try{renderCustomers((await api('customers?q='+encodeURIComponent(q))).customers);}catch(err){msg(err.message,true);}
});
$('customer-form').addEventListener('submit',async e=>{
 e.preventDefault();const v=Object.fromEntries(new FormData(e.target));
 await act('Đã thêm khách hàng',()=>api('customers',v));e.target.reset();
});
$('cd-close').addEventListener('click',()=>{$('customer-detail').hidden=true;currentCustomer=null;});
$('cd-note-form').addEventListener('submit',async e=>{
 e.preventDefault();if(!currentCustomer)return;const id=currentCustomer.customer.id;
 try{await api('customers/'+id+'/notes',{note:e.target.note.value});e.target.reset();openCustomer(id);}catch(err){msg(err.message,true);}
});
$('grant-plan').addEventListener('change',syncGrant);
$('grant-form').addEventListener('submit',async e=>{
 e.preventDefault();
 const f=e.target,v=Object.fromEntries(new FormData(f));
 const payload={email:v.email,confirm_email:v.confirm_email,name:v.name||undefined,reference:v.reference,note:v.note||undefined,
  source:v.pilot?'pilot_migration':'admin_grant'};
 if(v.plan_code)payload.plan_code=v.plan_code;else payload.seat_limit=Number(v.seat_limit);
 if(v.days)payload.days=Number(v.days);else if(!v.plan_code){msg('Gói tuỳ chỉnh cần số ngày',true);return;}
 if(v.amount_vnd!=='')payload.amount_vnd=Number(v.amount_vnd);
 if(!confirm('Cấp '+(v.plan_code?planName(v.plan_code):payload.seat_limit+' máy')+(payload.days?' · '+payload.days+' ngày':'')+' cho '+v.email+'?'))return;
 const b=f.querySelector('button[type=submit]');b.disabled=true;
 try{
  const r=await api('grant',payload);
  $('grant-result').hidden=false;
  $('grant-result').textContent=(r.renewed?'Đã gia hạn':'Đã cấp gói')+' cho '+v.email+' · hết hạn '+day(r.license.expires_at)+'. '+
   (r.linked?'Khách đã đăng nhập Gmail này: phần mềm tự mở khoá.':'Khách chưa đăng nhập Gmail này: gói sẽ tự gắn khi khách đăng nhập đúng Gmail.');
  f.reset();syncGrant();msg('Đã lưu thành công');await refresh();
 }catch(err){msg(err.message,true);}finally{b.disabled=false;}
});
/* Pilot migration: lines from tools/migrate_pilot_to_gmail.py --out */
$('bulk-run').addEventListener('click',async()=>{
 const lines=$('bulk-csv').value.split(/\r?\n/).map(l=>l.trim()).filter(l=>l&&!/^gmail,/i.test(l));
 const rows=[],bad=[];
 for(const line of lines){
  const [email,days,reference,...rest]=line.split(',');
  const d=Number(days);
  if(!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email||'')||!Number.isInteger(d)||d<1||d>1100||!(reference||'').trim())bad.push(line);
  else rows.push({email:email.trim(),days:d,reference:reference.trim(),note:rest.join(',').trim()});
 }
 if(bad.length){msg('Dòng không hợp lệ: '+bad.slice(0,3).join(' | '),true);return;}
 const plan=data.plans.find(p=>p.active)||data.plans[0];
 if(!rows.length||!plan||!confirm('Cấp '+planName(plan.code)+' theo số ngày còn lại cho '+rows.length+' Gmail?'))return;
 const out=$('bulk-result');out.replaceChildren();
 for(const r of rows){
  try{
   const x=await api('grant',{email:r.email,confirm_email:r.email,plan_code:plan.code,days:r.days,
     reference:r.reference,note:r.note||undefined,source:'pilot_migration'});
   out.append(el('li',r.email+' · '+r.days+' ngày · hết hạn '+day(x.license.expires_at)+(x.linked?'':' · chờ khách đăng nhập Gmail')));
  }catch(e){out.append(el('li',r.email+' · LỖI: '+e.message));}
 }
 msg('Đã xử lý '+rows.length+' dòng.');await refresh();
});
$('plan-add').addEventListener('click',()=>$('plan-list').append(planRow({code:'',name:'',seat_limit:2,months:1,price_vnd:0,active:false,sort:50})));
$('order-search').addEventListener('input',()=>filterTable('order'));
$('audit-search').addEventListener('input',()=>filterTable('audit'));
$('refresh-admin').addEventListener('click',()=>refresh().catch(e=>msg(e.message,true)));
$('payment-cancel').addEventListener('click',()=>$('payment-dialog').close());
$('payment-review-form').addEventListener('submit',async event=>{
 event.preventDefault();
 const b=$('payment-review-form').querySelector('button[type=submit]');
 if(b.disabled)return;
 const reference=$('payment-reference').value.trim();
 if(reference.length<3||!reviewingOrderId)return;
 b.disabled=true;
 try{
  const r=await api('orders/activate',{order_id:reviewingOrderId,reference,note:$('payment-note').value.trim()});
  $('payment-dialog').close();
  msg((r.renewed?'Đã gia hạn':'Đã kích hoạt')+' gói đến '+day(r.license.expires_at)+'. Phần mềm của khách tự mở khoá trong vài giây.');
  await refresh();
 }catch(err){msg(err.message,true)}
 finally{b.disabled=false}
});
refresh().catch(e=>{
 $('readiness-title').textContent='Quản trị chưa sẵn sàng';
 $('status').textContent=e.message;
});
