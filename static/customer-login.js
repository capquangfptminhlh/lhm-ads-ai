/* Customer sign-in protects the online session. Device vault remains local. */
'use strict';
(()=>{
 const box=document.getElementById('customer-login-box'),portal=document.getElementById('pwa-login-portal');
 if(!box||!portal)return;
 const root=document.body;
 const out=document.getElementById('customer-login-status');
 const submit=document.getElementById('customer-submit');
 const activation=document.getElementById('customer-activation-key');
 const form=document.getElementById('customer-form');
 const logout=document.getElementById('customer-cloud-logout');
 const msg=s=>out.textContent=s;
 async function api(path,body){
  const res=await fetch(path,{method:'POST',headers:{'content-type':'application/json'},credentials:'same-origin',cache:'no-store',body:JSON.stringify(body)});
  const data=await res.json();if(!res.ok)throw Error(data.error||'Không thể đăng nhập');return data;
 }
 const unlocked=()=>{
  root.classList.remove('customer-locked');
  box.hidden=true;portal.hidden=false;
  if(logout)logout.hidden=false;
 };
 const locked=()=>{
  root.classList.add('customer-locked');
  box.hidden=false;portal.hidden=true;
  if(logout)logout.hidden=true;
 };
 locked();
 fetch('/api/customer/session',{credentials:'same-origin',cache:'no-store'})
  .then(r=>{if(!r.ok)throw Error('Not signed in');return r.json()})
  .then(data=>{if(data.authenticated)unlocked();else locked()}).catch(()=>locked());
 document.getElementById('customer-mode').addEventListener('change',e=>{
  const on=e.target.value==='activate';
  activation.hidden=!on;activation.required=on;
  submit.textContent=on?'Kích hoạt tài khoản':'Đăng nhập';
  msg(on?'Cần email khách hàng và key do Admin cấp.':'');
 });
 form.addEventListener('submit',async e=>{
  e.preventDefault();submit.disabled=true;msg('Đang xử lý…');
  const mode=document.getElementById('customer-mode').value;
  const payload={email:document.getElementById('customer-email').value,password:document.getElementById('customer-password').value};
  if(mode==='activate')payload.key=activation.value;
  try{
   await api(mode==='activate'?'/api/customer/activate':'/api/customer/login',payload);
   activation.value='';document.getElementById('customer-password').value='';
   if(mode==='activate'){
    document.getElementById('customer-mode').value='login';
    activation.hidden=true;activation.required=false;submit.textContent='Đăng nhập';
    msg('Kích hoạt thành công. Hãy đăng nhập bằng email và mật khẩu vừa tạo.');
   }else{msg('Đăng nhập thành công. Mở khóa kho riêng trên thiết bị để tiếp tục.');unlocked();}
  }catch(e){msg(e.message||'Có lỗi xảy ra');}finally{submit.disabled=false;}
 });
 if(logout)logout.addEventListener('click',async()=>{
  try{await api('/api/customer/logout',{});}finally{
   if(window.LHMDeviceVault?.isUnlocked())document.getElementById('lhm-vault-lock')?.click();
   locked();msg('Đã đăng xuất tài khoản.');
  }
 });
})();
