/* Google account + paid subscription gate. Never forwards Ads credentials.
 * Hard lock: the app and the device vault open only while the Gmail has an
 * active plan and this device holds a seat. */
'use strict';
(()=>{
 const $=id=>document.getElementById(id);
 const box=$('customer-login-box'),portal=$('pwa-login-portal'),logout=$('customer-cloud-logout');
 if(!box||!portal)return;
 const root=document.body;
 const status=$('customer-login-status'),login=$('customer-google-signin'),account=$('customer-account');
 const purchase=$('customer-purchase'),plans=$('customer-plans'),action=$('customer-plan-submit');
 const payment=$('customer-payment'),seatPanel=$('customer-seat-limit'),note=$('customer-state-note');
 const localIdKey='lhm-license-client-v1';
 const UUID=/^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;
 const money=n=>new Intl.NumberFormat('vi-VN').format(n)+'đ';
 const day=s=>new Date(s).toLocaleDateString('vi-VN');
 let session=null,ready=false,heartbeat=null,poll=null,chosen='';
 let seatExpiryTimer=null,verifiedUntil=0,missedBeats=0,authRevision=0;
 const msg=s=>{if(status)status.textContent=String(s||'');};
 const show=(el,on)=>{if(el)el.hidden=!on;};

 class ApiError extends Error{constructor(data,status){super(data.error||'Máy chủ đang bận');this.code=data.code;this.status=status;this.data=data;}}
 async function api(path,options={}){
   let response;
   try{response=await fetch(path,{credentials:'same-origin',cache:'no-store',...options});}
   catch(_){throw new ApiError({error:'Cần Internet để xác minh gói. Kiểm tra kết nối rồi thử lại.',code:'OFFLINE'},0);}
   const data=await response.json().catch(()=>({error:'Không đọc được phản hồi máy chủ'}));
   if(!response.ok)throw new ApiError(data,response.status);
   return data;
 }
 const post=(url,data)=>api(url,{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify(data||{})});
 function clientId(){
   let id=null;
   try{id=localStorage.getItem(localIdKey);}catch(_){}
   if(!UUID.test(id||'')){id=crypto.randomUUID();try{localStorage.setItem(localIdKey,id);}catch(_){}}
   return id;
 }
 function deviceLabel(){
   const ua=navigator.userAgent;
   const os=/Android/.test(ua)?'Android':/iPhone|iPad/.test(ua)?'iPhone':/Windows/.test(ua)?'Windows':/Mac OS/.test(ua)?'Mac':'Thiết bị';
   const app=/Edg\//.test(ua)?'Edge':/Chrome\//.test(ua)?'Chrome':/Firefox\//.test(ua)?'Firefox':/Safari\//.test(ua)?'Safari':'Trình duyệt';
   return app+' '+os;
 }

 function lock(message){
   authRevision++;verifiedUntil=0;missedBeats=0;
   clearTimeout(seatExpiryTimer);seatExpiryTimer=null;
   ready=false;clearInterval(heartbeat);heartbeat=null;
   root.classList.add('customer-locked');
   box.hidden=false;portal.hidden=true;
   if(window.LHMDeviceVault?.isUnlocked())window.LHMDeviceVault.lock();
   window.dispatchEvent(new Event('lhm:vault-locked'));
   if(message!==undefined)msg(message);
 }
 function unlock(){
   ready=true;root.classList.remove('customer-locked');box.hidden=true;
   portal.hidden=false;show(logout,true);
   window.dispatchEvent(new Event('lhm:customer-ready'));
 }
 function panels(which){
   show(purchase,which==='purchase');show(payment,which==='payment');show(seatPanel,which==='seats');
 }
 function stateNote(text){note.textContent=text||'';show(note,Boolean(text));}

 function renderAccount(s){
   show(login,!s);show(account,Boolean(s));show(logout,Boolean(s));
   if(!s)return;
   $('customer-email').textContent=s.email;
   const avatar=$('customer-avatar');
   if(s.picture){avatar.src=s.picture;avatar.hidden=false;}else avatar.hidden=true;
   $('customer-plan-line').textContent=s.plan
     ?' · '+(s.plan.name||s.plan.seat_limit+' máy')+' · hết hạn '+day(s.plan.expires_at)
     :'';
   const mine=$('lhm-my-plan');
   if(mine)mine.textContent=s.plan
     ?'Gmail: '+s.email+' · '+(s.plan.name||'')+' · tối đa '+s.plan.seat_limit+' máy cùng lúc · hết hạn '+day(s.plan.expires_at)
       +' (còn '+s.plan.days_left+' ngày)'
     :'Gmail: '+s.email+' · Chưa có gói đang hoạt động.';
   const banner=$('lhm-plan-banner');
   if(banner){
     const soon=s.plan?.expiring_soon;
     banner.hidden=!soon;
     if(soon){
       const left=Date.parse(s.plan.expires_at)-Date.now();
       $('lhm-plan-banner-text').textContent=left<86400000
         ?'Gói hết hạn lúc '+new Date(s.plan.expires_at).toLocaleTimeString('vi-VN',{hour:'2-digit',minute:'2-digit'})+' hôm nay. Sau đó phần mềm sẽ khoá.'
         :'Gói còn '+s.plan.days_left+' ngày (hết hạn '+day(s.plan.expires_at)+'). Gia hạn để không bị gián đoạn.';
       banner.classList.toggle('urgent',left<3*86400000);
     }
   }
 }

 async function renderPlans(){
   const result=await api('/api/auth/plans');
   plans.replaceChildren();
   for(const plan of result.plans||[]){
     const label=document.createElement('label');
     label.className='customer-plan';
     const input=document.createElement('input');
     input.type='radio';input.name='customer-plan';input.value=plan.code;
     input.addEventListener('change',()=>{chosen=plan.code;action.disabled=false;});
     const name=document.createElement('b');name.textContent=plan.name;
     const meta=document.createElement('small');
     meta.textContent=money(plan.price_vnd)+' · tối đa '+plan.seat_limit+' máy cùng lúc';
     label.append(input,name,meta);plans.append(label);
   }
   const first=plans.querySelector('input');
   if(first){first.checked=true;chosen=first.value;action.disabled=false;}
   else{action.disabled=true;msg('Chưa có gói đang mở bán. Liên hệ quản trị viên.');}
 }

 function renderPayment(order){
   stateNote('');
   const pay=order.payment||{};
   $('customer-pay-plan').textContent=order.plan_name||order.plan_code||'';
   $('customer-pay-amount').textContent=money(order.amount_vnd);
   $('customer-pay-code').textContent=order.payment_code;
   $('customer-pay-bank').textContent=pay.configured?pay.account_no+' · '+pay.account_name:'Quản trị viên sẽ gửi số tài khoản';
   const qr=$('customer-qr');
   if(pay.configured&&pay.qr_url){qr.src=pay.qr_url;qr.hidden=false;}else qr.hidden=true;
   $('customer-order-cancel').dataset.order=order.id;
   $('customer-pay-note').textContent='Ghi đúng nội dung '+order.payment_code+'. Đơn giữ đến '+
     new Date(order.expires_at).toLocaleString('vi-VN')+'. Trang này tự cập nhật khi gói được kích hoạt.';
   panels('payment');
   clearInterval(poll);
   poll=setInterval(async()=>{
     try{const s=await api('/api/auth/session');if(s.state!=='pending'){clearInterval(poll);reload();}}catch(_){}
   },15000);
 }

 function renderSeats(devices){
   stateNote('');
   const list=$('customer-seat-list');list.replaceChildren();
   for(const d of devices||[]){
     const li=document.createElement('li');
     li.textContent=d.label+' · hoạt động '+new Date(d.last_seen_at).toLocaleString('vi-VN');
     list.append(li);
   }
   panels('seats');
 }

 async function acquire(mode){
   const revision=authRevision;
   const result=await post('/api/auth/seat',{client_id:clientId(),mode,device_label:deviceLabel()});
   // A delayed response must not re-open a vault after an account change/lock.
   if(revision!==authRevision)throw new ApiError({error:'Phiên đăng nhập đã thay đổi',code:'STALE'},409);
   if(!result.active)throw new ApiError({error:'Chưa có quyền sử dụng phần mềm'},403);
   const ttl=Number(result.ttl_seconds),planEnd=Date.parse(result.expires_at);
   if(!Number.isFinite(ttl)||ttl<1||ttl>600||!Number.isFinite(planEnd)||planEnd<=Date.now())
     throw new ApiError({error:'Máy chủ không trả về thời hạn xác minh gói hợp lệ.',code:'INVALID_LEASE'},503);
   // PWA seats are online-only. Their maximum offline window is the shorter
   // of the server's TTL and the paid subscription expiry, never the PC's 72h.
   verifiedUntil=Math.min(Date.now()+ttl*1000,planEnd);
   missedBeats=0;
   clearTimeout(seatExpiryTimer);
   const deadline=verifiedUntil;
   seatExpiryTimer=setTimeout(()=>{
     // A real timer still locks after its TTL even if the wall clock is rolled back.
     if(ready&&verifiedUntil===deadline)
       lock('Phiên bản quyền đã hết hạn xác minh. Kết nối Internet để kiểm tra lại gói.');
   },Math.max(0,deadline-Date.now()));
   // A heartbeat must not re-decrypt/remount the local Ads vault.
   if(mode==='heartbeat'&&ready)return result;
   const opened=await window.LHMDeviceVault?.autoUnlock?.();
   if(revision!==authRevision)throw new ApiError({error:'Phiên đăng nhập đã thay đổi',code:'STALE'},409);
   unlock();
   if(opened?.legacy_password_required)msg('Kho dữ liệu cũ cần mở bằng mật khẩu lần cuối.');
   clearInterval(heartbeat);
   heartbeat=setInterval(beat,(session?.heartbeat_seconds||300)*1000);
   return result;
 }
 async function beat(){
   if(!ready)return;
   try{await acquire('heartbeat');}
   catch(e){
     if(e.code==='STALE')return;
     if(e.code==='OFFLINE'){
       // Permit one brief network blip, but never leave the PWA open indefinitely.
       // A second failed heartbeat locks even after clock rollback.
       missedBeats++;
       if(missedBeats>=2||Date.now()>=verifiedUntil)
         lock('Mất kết nối quá lâu. Hãy kết nối Internet để xác minh lại gói.');
       return;
     }
     lock();reload();
   }
 }
 document.addEventListener('visibilitychange',()=>{
   if(!document.hidden&&ready){
     if(Date.now()>=verifiedUntil)lock('Phiên bản quyền đã hết hạn xác minh. Kết nối lại để tiếp tục.');
     else beat().catch(()=>{});
   }
 });

 async function reload(){
   clearInterval(poll);
   lock('Đang kiểm tra tài khoản Google và gói dịch vụ…');
   panels('none');stateNote('');
   try{session=await api('/api/auth/session');}
   catch(e){
     session=null;renderAccount(null);
     if(e.code==='ACCOUNT_BLOCKED'){stateNote(e.message);show(logout,true);msg('');return;}
     msg(e.code==='OFFLINE'?e.message:'Đăng nhập bằng Google để bắt đầu.');
     return;
   }
   renderAccount(session);
   if(window.LHMDeviceVault?.setNamespace)window.LHMDeviceVault.setNamespace(session.account_id);
   if(session.state==='active'){
     try{await acquire('attach');msg('Gói hợp lệ. Kho dữ liệu trên thiết bị đã mở.');}
     catch(e){
       if(e.code==='SEAT_LIMIT'){renderSeats(e.data.devices);msg('');}
       else lock(e.message);
     }
     return;
   }
   if(session.state==='pending'&&session.pending_order){renderPayment(session.pending_order);msg('Đang chờ xác nhận thanh toán…');return;}
   if(session.state==='revoked'){stateNote('Gói của Gmail này đã bị thu hồi. Liên hệ hỗ trợ để được kiểm tra.');msg('');return;}
   stateNote(session.state==='expired'
     ?'Gói đã hết hạn'+(session.expired_at?' ngày '+day(session.expired_at):'')+'. Phần mềm đang khoá; dữ liệu trên máy vẫn còn và mở lại ngay khi gia hạn.'
     :'Gmail này chưa có gói. Đã mua bằng Gmail khác? Bấm "Đổi Gmail".');
   panels('purchase');msg('');
   await renderPlans().catch(e=>msg(e.message));
 }

 action?.addEventListener('click',async()=>{
   if(!chosen)return;
   action.disabled=true;
   try{const order=await post('/api/auth/plan',{plan_code:chosen});renderPayment(order);msg('Đã tạo đơn '+order.payment_code+'.');}
   catch(e){
     if(e.code==='PAYMENT_PENDING'&&e.data.pending_order)renderPayment(e.data.pending_order);
     else msg(e.message);
   }finally{action.disabled=false;}
 });
 $('customer-order-cancel')?.addEventListener('click',async e=>{
   try{await post('/api/auth/order/cancel',{order_id:e.currentTarget.dataset.order});}catch(err){msg(err.message);}
   reload();
 });
 $('customer-takeover')?.addEventListener('click',async()=>{
   try{await acquire('takeover');panels('none');msg('Đã chuyển sang dùng trên máy này.');}
   catch(e){msg(e.message);}
 });
 box.addEventListener('click',e=>{
   const id=e.target?.dataset?.copy;if(!id)return;
   navigator.clipboard?.writeText($(id).textContent).then(()=>msg('Đã sao chép nội dung chuyển khoản.')).catch(()=>{});
 });
 const signOut=async()=>{
   try{await post('/api/auth/logout',{});}catch(_){}
   session=null;lock();location.assign('/local/');
 };
 $('customer-switch')?.addEventListener('click',async()=>{
   try{await post('/api/auth/logout',{});}catch(_){}
   location.assign('/api/auth/google/start');
 });
 logout?.addEventListener('click',signOut);
 window.addEventListener('lhm:pwa-signout',signOut);

 // Settings page: renewal, devices and sign-out everywhere.
 const renew=async()=>{lock();panels('purchase');stateNote('Chọn gói để gia hạn. Thời gian được cộng nối tiếp từ ngày hết hạn hiện tại.');
   await renderPlans().catch(e=>msg(e.message));};
 $('lhm-renew')?.addEventListener('click',renew);
 $('lhm-plan-banner-renew')?.addEventListener('click',renew);
 $('lhm-signout-all')?.addEventListener('click',async()=>{
   if(!confirm('Đăng xuất Gmail này trên mọi máy và trình duyệt?'))return;
   try{await post('/api/auth/devices/signout-all',{});}catch(_){}
   session=null;lock();location.assign('/local/');
 });
 window.addEventListener('lhm:pwa-view',async e=>{
   if(e.detail!=='settings'||!ready)return;
   const list=$('lhm-my-devices');if(!list)return;
   try{
     const r=await api('/api/auth/devices?client_id='+encodeURIComponent(clientId()));
     list.replaceChildren(...r.devices.map(d=>{const li=document.createElement('li');
       li.textContent=d.label+(d.current?' (máy này)':'')+' · '+new Date(d.last_seen_at).toLocaleString('vi-VN');return li;}));
   }catch(_){}
 });
 window.LHMCustomer={reload,get state(){return session?.state||null;}};
 reload().catch(e=>lock(e.message));
})();
