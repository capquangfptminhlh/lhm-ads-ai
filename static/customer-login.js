/* Google account + paid subscription gate. Never forwards Ads credentials. */
'use strict';
(()=>{
 const box=document.getElementById('customer-login-box');
 const portal=document.getElementById('pwa-login-portal');
 const logout=document.getElementById('customer-cloud-logout');
 if(!box||!portal)return;
 const root=document.body;
 const status=document.getElementById('customer-login-status');
 const login=document.getElementById('customer-google-signin');
 const account=document.getElementById('customer-account');
 const purchase=document.getElementById('customer-purchase');
 const plans=document.getElementById('customer-plans');
 const action=document.getElementById('customer-plan-submit');
 const localIdKey='lhm-license-client-v1';
 let subscribed=false,authenticated=false,ready=false;
 const msg=s=>{if(status)status.textContent=String(s);};
 const lock=(message)=>{
   ready=false;root.classList.add('customer-locked');
   box.hidden=false;portal.hidden=true;
   if(logout)logout.hidden=!authenticated;
   if(window.LHMDeviceVault?.isUnlocked())window.LHMDeviceVault.lock();
   window.dispatchEvent(new Event('lhm:vault-locked'));
   if(message)msg(message);
 };
 const unlock=()=>{
   ready=true;root.classList.remove('customer-locked');box.hidden=true;
   portal.hidden=false;if(logout)logout.hidden=false;
   window.dispatchEvent(new Event('lhm:customer-ready'));
 };
 async function api(path,options={}){
   const response=await fetch(path,{credentials:'same-origin',cache:'no-store',...options});
   const data=await response.json().catch(()=>({error:'Không đọc được phản hồi máy chủ'}));
   if(!response.ok)throw Error(data.error||'Máy chủ đang bận');
   return data;
 }
 const post=(url,data)=>api(url,{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify(data)});
 function clientId(){
   let id=localStorage.getItem(localIdKey);
   if(!/^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i.test(id||'')){
     id=crypto.randomUUID();localStorage.setItem(localIdKey,id);
   }
   return id;
 }
 async function acquire(mode){
   const result=await post('/api/auth/seat',{client_id:clientId(),mode});
   if(!result.active)throw Error('Chưa có quyền sử dụng phần mềm');
   // Google subscription is the only normal sign-in. The AES key remains on this device.
   const opened=await window.LHMDeviceVault?.autoUnlock?.();
   unlock();
   if(opened?.legacy_password_required)msg('Kho dữ liệu cũ cần mở bằng mật khẩu lần cuối.');
 }
 async function loadPlans(){
   const result=await api('/api/auth/plans');
   plans.replaceChildren();
   for(const plan of result.plans||[]){
     const option=document.createElement('option');
     option.value=String(plan.seats);
     option.disabled=!plan.available;
     option.textContent=plan.seats+' phiên đồng thời · '+(plan.available
      ?new Intl.NumberFormat('vi-VN').format(plan.price_vnd)+'đ / tháng'
      :'Chưa có giá, liên hệ quản trị');
     plans.append(option);
   }
   const available=[...plans.options].find(x=>!x.disabled);
   if(available)plans.value=available.value;
   action.disabled=!available;
 }
 async function reload(){
   lock('Đang kiểm tra tài khoản Google và bản quyền…');
   let state;
   try{state=await api('/api/auth/session');}
   catch(_){
     authenticated=false;subscribed=false;
     login.hidden=false;account.hidden=true;purchase.hidden=true;
     if(logout)logout.hidden=true;
     lock('Vui lòng đăng nhập bằng Google để bắt đầu.');
     return;
   }
   authenticated=true;subscribed=state.subscribed;
   login.hidden=true;account.hidden=false;
   account.textContent='Đã đăng nhập: '+state.email;
   if(window.LHMDeviceVault?.setNamespace)window.LHMDeviceVault.setNamespace(state.account_id);
   if(!subscribed){
     purchase.hidden=false;
     if(state.pending_order){
       action.disabled=true;
       msg('Đơn hàng đang chờ xác nhận thanh toán. Mã đơn: '+state.pending_order.id);
     }else{
       msg('Hãy chọn gói và hoàn tất thanh toán trước khi thêm tài khoản quảng cáo.');
       await loadPlans().catch(err=>msg(err.message));
     }
     return;
   }
   purchase.hidden=true;
   try{
     await acquire('attach');
     msg('Bản quyền hợp lệ. Có thể mở kho dữ liệu trên thiết bị.');
   }catch(e){lock(e.message);}
 }
 action?.addEventListener('click',async()=>{
   action.disabled=true;
   try{
     const result=await post('/api/auth/plan',{seats:Number(plans.value)});
     msg('Đã tạo đơn hàng '+result.order_id+'. Chờ quản trị xác nhận chuyển khoản; chưa thu tiền tự động.');
   }catch(e){msg(e.message);}
   finally{action.disabled=false;}
 });
 const googleLogout=async()=>{
   try{await post('/api/auth/logout',{});}catch(_){}
   authenticated=false;subscribed=false;lock();
   location.assign('/local/');
 };
 logout?.addEventListener('click',googleLogout);
 window.addEventListener('lhm:pwa-signout',googleLogout);
 // Heartbeat only refreshes an EXISTING seat, never silently steals another session.
 setInterval(async()=>{
   if(!ready)return;
   try{await acquire('heartbeat');}
   catch(_){lock('Phiên sử dụng đã hết hạn hoặc bị thay thế. Đăng nhập lại để tiếp tục.');}
 },60000);
 reload().catch(e=>lock(e.message));
})();
