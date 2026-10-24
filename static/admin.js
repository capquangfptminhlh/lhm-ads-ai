'use strict';let data={customers:[],orders:[],licenses:[],audit:[],fulfilled_order_ids:[]},issuedKey='';
const $=x=>document.getElementById(x),fmt=x=>new Intl.NumberFormat('vi-VN').format(x||0);
const el=(tag,t)=>{const n=document.createElement(tag);n.textContent=String(t??'');return n;};
function msg(s,error=false){
 const n=$('message');n.textContent=s;n.className='show'+(error?' error':'');
 n.setAttribute('role',error?'alert':'status');
}
async function api(path,payload){const opts=payload===undefined?{}:{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify(payload)};const r=await fetch('/api/admin/'+path,{credentials:'same-origin',cache:'no-store',...opts});let x;try{x=await r.json()}catch{x={error:'Server did not return JSON'}}if(!r.ok){
 if(r.status===401||r.status===403)throw Error('Bạn chưa được xác thực hoặc chưa có quyền quản trị qua Cloudflare Access.');
 if(r.status===503)throw Error('API quản trị chưa kết nối Cloudflare D1 hoặc cấu hình môi trường còn thiếu.');
 throw Error(x.error||'Yêu cầu không thực hiện được (HTTP '+r.status+').');
}return x;}
function options(select,items,label){select.replaceChildren();for(const item of items){const o=el('option',label(item));o.value=item.id;select.append(o);}}
function cells(tbody,values){const tr=document.createElement('tr');values.forEach(v=>tr.append(el('td',v)));tbody.append(tr);return tr;}
function syncRenewOrders(){
 const license=data.licenses.find(x=>x.id===$('license-choice').value);
 const spent=new Set(data.fulfilled_order_ids||[]);
 options($('paid-order-choice'),data.orders.filter(x=>x.status==='paid'&&!spent.has(x.id)
  && license&&x.customer_id===license.customer_id),x=>x.customer_name+' · '+x.id.slice(0,8));
}
function filterTable(kind){
 const table=$(kind+'-list'),input=$(kind+'-search'),empty=$(kind+'-empty');
 if(!table||!input||!empty)return;
 const q=input.value.trim().toLocaleLowerCase('vi');
 let count=0;
 for(const tr of table.querySelectorAll('tr')){
  const show=tr.textContent.toLocaleLowerCase('vi').includes(q);
  tr.hidden=!show;
  if(show)count++;
 }
 empty.hidden=count>0;
}
function filterAll(){for(const kind of ['customer','order','license','audit'])filterTable(kind);}
let reviewingOrderId='';
function openPaymentReview(orderId){
 reviewingOrderId=orderId;
 $('payment-review-form').reset();
 $('payment-dialog').showModal();
 $('payment-reference').focus();
}
function render(){
  const spent=new Set(data.fulfilled_order_ids||[]);
  $('m-customers').textContent=data.customers.length;$('m-orders').textContent=data.orders.filter(x=>x.status==='pending').length;
  $('m-licenses').textContent=data.licenses.filter(x=>x.status==='active'&&new Date(x.expires_at)>new Date()).length;
  $('customer-list').replaceChildren();data.customers.forEach(x=>cells($('customer-list'),[x.name,x.email,x.phone||'—',x.status]));
  document.querySelectorAll('.customer-choices').forEach(s=>options(s,data.customers,x=>x.name+' · '+x.email));
  $('order-list').replaceChildren();
  data.orders.forEach(x=>{const tr=cells($('order-list'),[x.id.slice(0,8),x.customer_name,x.months+' tháng',fmt(x.amount_vnd)+'đ',x.status]);const td=el('td','');
 const pill=el('span',x.status==='paid'?'Đã thanh toán':x.status==='pending'?'Chờ duyệt':'Đã hủy');
 pill.className='admin-tag '+(x.status==='paid'?'tag-success':x.status==='pending'?'tag-pending':'tag-muted');
 tr.children[4].replaceChildren(pill);
    if(x.status==='pending'){const a=el('button','Ghi nhận chuyển khoản');a.onclick=async()=>{openPaymentReview(x.id)};const b=el('button','Duyệt đã nhận tiền');b.onclick=async()=>{if(!confirm('Đã đối soát tiền vào ngân hàng? Duyệt đơn '+x.id.slice(0,8)+'?'))return;try{await api('payments/approve',{order_id:x.id});msg('Đã duyệt thanh toán');await refresh()}catch(e){msg(e.message,true)}};td.append(a,b)}
    if(x.status==='paid'&&!spent.has(x.id)){const b=el('button','Cấp key');b.onclick=async()=>{if(!confirm('Cấp key từ đơn '+x.id.slice(0,8)+'?'))return;try{const k=await api('licenses/issue',{order_id:x.id});issuedKey=k.key;$('issued-key').textContent=k.key+'\nHết hạn: '+k.expires_at;$('issued').hidden=false;msg('Đã cấp key. Vào tab Bản quyền để lưu key.');document.querySelector('[data-tab="licenses"]').click();await refresh()}catch(e){msg(e.message,true)}};td.append(b)}tr.append(td)});
  options($('license-choice'),data.licenses,x=>x.customer_name+' · '+x.key_hint);
  syncRenewOrders();
  $('license-list').replaceChildren();data.licenses.forEach(x=>{const tr=cells($('license-list'),[x.customer_name,'•••• '+x.key_hint,new Date(x.expires_at).toLocaleDateString('vi-VN'),x.status]);const td=el('td','');if(x.status==='active'){const b=el('button','Thu hồi');b.onclick=async()=>{if(!confirm('Thu hồi key của '+x.customer_name+'?'))return;try{await api('licenses/revoke',{license_id:x.id});msg('Đã thu hồi');await refresh()}catch(e){msg(e.message,true)}};td.append(b)}tr.append(td)});
  $('audit-list').replaceChildren();data.audit.forEach(x=>cells($('audit-list'),[x.at,x.actor,x.action,x.target_id]));
  filterAll();
}
async function refresh(){
 const button=$('refresh-admin');
 button.disabled=true;button.textContent='Đang cập nhật…';
 try{
  data=await api('overview');
  $('unavailable').hidden=true;$('workspace').hidden=false;render();
 }finally{button.disabled=false;button.textContent='↻ Làm mới dữ liệu';}
}
document.querySelectorAll('nav button').forEach(b=>b.addEventListener('click',()=>{document.querySelectorAll('nav button').forEach(n=>n.removeAttribute('aria-current'));b.setAttribute('aria-current','page');document.querySelectorAll('.view').forEach(n=>n.classList.toggle('active',n.id===b.dataset.tab));}));
function submit(form,path,transform){form.addEventListener('submit',async e=>{
 e.preventDefault();
 const submitButton=form.querySelector('button[type=submit]');
 if(submitButton.disabled)return;
 const payload=Object.fromEntries(new FormData(form));
 submitButton.disabled=true;
 try{
  await api(path,transform?transform(payload):payload);
  msg('Đã lưu thành công');form.reset();await refresh();
 }catch(err){msg(err.message,true)}
 finally{submitButton.disabled=false}
})}
submit($('customer-form'),'customers');submit($('order-form'),'orders',v=>({...v,months:Number(v.months),amount_vnd:Number(v.amount_vnd)}));submit($('renew-form'),'licenses/renew');
$('copy-key').onclick=()=>{if(issuedKey)navigator.clipboard.writeText(issuedKey).then(()=>msg('Đã sao chép key')).catch(()=>msg('Không thể sao chép tự động',true))};
$('license-choice').addEventListener('change',syncRenewOrders);
for(const kind of ['customer','order','license','audit']){
 $(kind+'-search').addEventListener('input',()=>filterTable(kind));
}
$('refresh-admin').addEventListener('click',()=>refresh().catch(e=>msg(e.message,true)));
$('payment-cancel').addEventListener('click',()=>$('payment-dialog').close());
$('payment-review-form').addEventListener('submit',async event=>{
 event.preventDefault();
 const button=$('payment-review-form').querySelector('button[type=submit]');
 if(button.disabled)return;
 const reference=$('payment-reference').value.trim();
 if(!reference||!reviewingOrderId)return;
 button.disabled=true;
 try{
  await api('payments/review',{order_id:reviewingOrderId,reference,note:$('payment-note').value.trim()});
  $('payment-dialog').close();
  msg('Đã ghi nhận mã giao dịch. Chỉ duyệt sau khi đối soát sao kê ngân hàng.');
 }catch(err){msg(err.message,true)}
 finally{button.disabled=false}
});
refresh().catch(e=>{
 $('readiness-title').textContent='Quản trị chưa sẵn sàng';
 $('status').textContent=e.message;
});
