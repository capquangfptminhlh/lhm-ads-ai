/* Google-only license UX for the trusted Windows pywebview shell.
 * The native bridge supplies only a fresh local proof, never Ads credentials.
 * Browser OAuth happens in the real system browser (not in WebView2).
 * Hard lock: the gate covers the app whenever the local API reports no active
 * plan; the local API itself refuses Ads/AI/automation calls (see
 * ads_core/desktop_cloud_license.py), so the overlay is not the only barrier.
 */
'use strict';
(() => {
 let proof='',busy=false,pollTimer=null,watchTimer=null,bootstrapping=false;
 let panel,caption,code,login,attach,takeover,renew,logout,devices,offline;
 const REASONS={
  SIGNIN_REQUIRED:'Đăng nhập Google và chọn gói dịch vụ để bắt đầu.',
  SUBSCRIPTION_REQUIRED:'Gmail này chưa có gói. Bấm "Mua / gia hạn gói" để chọn gói, rồi bấm Tiếp tục.',
  PAYMENT_PENDING:'Đơn hàng đang chờ xác nhận thanh toán. Bấm Tiếp tục sau khi quản trị viên kích hoạt.',
  SUBSCRIPTION_EXPIRED:'Gói đã hết hạn nên phần mềm đang khoá. Dữ liệu trên máy vẫn còn; gia hạn để mở lại.',
  LICENSE_REVOKED:'Gói của Gmail này đã bị thu hồi. Liên hệ hỗ trợ.',
  ACCOUNT_BLOCKED:'Tài khoản đang bị tạm khoá. Liên hệ hỗ trợ.',
  SEAT_LIMIT:'Gmail này đang dùng trên đủ số máy của gói.',
  SEAT_REPLACED:'Gmail này vừa được dùng trên máy khác.',
  OFFLINE_LOCKED:'Đã quá thời gian dùng offline. Kết nối Internet rồi bấm Tiếp tục.',
  GOOGLE_ACCOUNT_MISMATCH:'Gmail trên máy không khớp với máy chủ. Hãy đăng nhập lại.'
 };
 const stylesheet=[
  'body.lhm-native-cloud #login{display:none!important}',
  '#lhm-cloud-gate{position:fixed;inset:0;z-index:100000;background:#091526f5;',
  'display:grid;place-items:center;padding:16px;color:#193550;font:15px/1.6 system-ui}',
  '#lhm-cloud-gate[hidden],#lhm-cloud-gate [hidden]{display:none!important}',
  '#lhm-cloud-gate article{background:white;width:min(100%,480px);border:1px solid #dae7f5;',
  'padding:30px;border-radius:22px;box-shadow:0 24px 70px #0006}',
  '#lhm-cloud-gate h2{font-size:23px;margin:0 0 12px;color:#153753}',
  '#lhm-cloud-gate p{color:#4e6884}',
  '#lhm-cloud-gate button{border:0;border-radius:11px;background:#146fc8;color:white;',
  'padding:12px 17px;margin:8px 6px 0 0;font-weight:750;cursor:pointer}',
  '#lhm-cloud-gate button.secondary{background:#eaf2fb;color:#1b4d7a}',
  '#lhm-cloud-gate button:disabled{opacity:.5}',
  '#lhm-cloud-gate .notice{background:#eaf4ff;padding:13px;border-radius:12px;overflow-wrap:anywhere}',
  '#lhm-cloud-gate ul{margin:6px 0;padding-left:18px;font-size:13px;color:#2c4964}',
  '#lhm-cloud-gate small{font-size:12px;color:#5d7690}',
  '#lhm-cloud-offline{position:fixed;right:14px;bottom:14px;z-index:99999;background:#fff6ea;',
  'border:1px solid #f1d2a8;color:#7a4b12;border-radius:12px;padding:9px 13px;font:13px/1.4 system-ui;',
  'box-shadow:0 8px 24px #0002}',
  '#lhm-cloud-offline[hidden]{display:none}'
 ].join('');
 const report=(value)=>{if(caption)caption.textContent=String(value);};
 const show=()=>{if(panel)panel.hidden=false;};
 const when=s=>new Date(s).toLocaleString('vi-VN',{hour:'2-digit',minute:'2-digit',day:'2-digit',month:'2-digit'});
 function create(){
   if(panel)return;
   const s=document.createElement('style');s.textContent=stylesheet;document.head.append(s);
   document.body.classList.add('lhm-native-cloud');
   panel=document.createElement('section');
   panel.id='lhm-cloud-gate';
   panel.setAttribute('aria-label','Đăng nhập Google và kích hoạt gói');
   panel.innerHTML=[
     '<article role="dialog" aria-modal="true">',
     '<h2>LHM Ads AI — Đăng nhập Google</h2>',
     '<p>Chỉ cần Gmail đã đăng ký gói. Không phải nhập key hay mật khẩu LHM.</p>',
     '<p class="notice" id="lhm-cloud-status" role="status">Đang kiểm tra bản quyền…</p>',
     '<p id="lhm-cloud-code"></p>',
     '<ul id="lhm-cloud-devices" hidden></ul>',
     '<button id="lhm-cloud-signin" type="button">Đăng nhập bằng Google</button>',
     '<button id="lhm-cloud-takeover" type="button" hidden>Dùng trên máy này</button>',
     '<button id="lhm-cloud-attach" type="button" hidden>Tiếp tục</button>',
     '<button id="lhm-cloud-renew" class="secondary" type="button" hidden>Mua / gia hạn gói</button>',
     '<button id="lhm-cloud-logout" class="secondary" type="button" hidden>Đổi Gmail</button>',
     '<p><small>Dữ liệu và token quảng cáo chỉ lưu mã hóa trên máy tính.</small></p>',
     '</article>'
   ].join('');
   document.body.append(panel);
   offline=document.createElement('div');offline.id='lhm-cloud-offline';offline.hidden=true;offline.setAttribute('role','status');
   document.body.append(offline);
   caption=panel.querySelector('#lhm-cloud-status');
   code=panel.querySelector('#lhm-cloud-code');
   devices=panel.querySelector('#lhm-cloud-devices');
   login=panel.querySelector('#lhm-cloud-signin');
   attach=panel.querySelector('#lhm-cloud-attach');
   takeover=panel.querySelector('#lhm-cloud-takeover');
   renew=panel.querySelector('#lhm-cloud-renew');
   logout=panel.querySelector('#lhm-cloud-logout');
   login.onclick=start;
   attach.onclick=()=>seat('attach');
   takeover.onclick=()=>seat('takeover');
   renew.onclick=()=>window.pywebview?.api?.open_license_url('https://ads.lhmcrm.com/local/');
   logout.onclick=async()=>{
     try{
       await request('/api/cloud-license/logout','POST');
       code.textContent='';report('Đã đăng xuất. Đăng nhập Gmail để tiếp tục.');
       buttons({paired:false});show();
       // Clear old UI-bound local session; the next login establishes a new tenant.
       window.dispatchEvent(new Event('lhm:local-logout'));
     }catch(e){report(e.message);}
   };
 }
 async function request(path,method='GET',body={}){
   const headers={'Accept':'application/json','X-LHM-Native-Proof':proof};
   if(method==='POST')headers['Content-Type']='application/json';
   const response=await fetch(path,{
     method,headers,credentials:'same-origin',cache:'no-store',
     ...(method==='POST'?{body:JSON.stringify(body)}:{})
   });
   const data=await response.json().catch(()=>({}));
   if(!response.ok)throw Error(data.detail||data.error||'Không kết nối được máy chủ bản quyền');
   return data;
 }
 async function seat(mode){
   try{report('Đang kiểm tra gói và số máy…');await present({...await request('/api/cloud-license/attach','POST',{mode}),paired:true});}
   catch(e){report(e.message);}
 }
 async function localSession(){
   if(bootstrapping)return;
   bootstrapping=true;
   try{
     const previous=await fetch('/api/studio/me',{cache:'no-store',credentials:'same-origin'});
     if(previous.ok){panel.hidden=true;return;}
     await request('/api/cloud-license/local-session','POST');
     location.reload();
   }catch(e){report(e.message);show();}
   finally{bootstrapping=false;}
 }
 function buttons({paired,reason}){
   login.hidden=Boolean(paired);
   logout.hidden=!paired;
   attach.hidden=!paired||reason==='SEAT_LIMIT'||reason==='LICENSE_REVOKED'||reason==='ACCOUNT_BLOCKED';
   takeover.hidden=!(paired&&(reason==='SEAT_LIMIT'||reason==='SEAT_REPLACED'));
   renew.hidden=!paired||!['SUBSCRIPTION_REQUIRED','SUBSCRIPTION_EXPIRED','PAYMENT_PENDING'].includes(reason);
 }
 function offlineBanner(data){
   const on=data?.active===true&&data?.reason==='OFFLINE'&&data?.offline_until;
   offline.hidden=!on;
   if(on)offline.textContent='Đang offline — phần mềm dùng được đến '+when(data.offline_until)+'. Kết nối Internet để gia hạn thời gian này.';
 }
 async function present(data){
   offlineBanner(data);
   if(data?.active===true){
     code.textContent='';devices.hidden=true;buttons({paired:true,reason:''});attach.hidden=true;
     report('Gói còn hạn. Đang mở Studio…');
     watch();
     await localSession();
     return;
   }
   show();
   const reason=data?.paired?(data?.reason||'SUBSCRIPTION_REQUIRED'):'SIGNIN_REQUIRED';
   buttons({paired:data?.paired,reason});
   devices.replaceChildren();
   for(const d of data?.devices||[]){
     const li=document.createElement('li');li.textContent=d.label+(d.last_seen_at?' · '+when(d.last_seen_at):'');devices.append(li);
   }
   devices.hidden=!devices.children.length;
   report((data?.email?'Gmail: '+data.email+'. ':'')+(REASONS[reason]||REASONS.SUBSCRIPTION_REQUIRED)+
     (reason==='SEAT_LIMIT'?' Bấm "Dùng trên máy này": máy hoạt động lâu nhất sẽ bị đăng xuất.':''));
 }
 // Re-check every minute so an expiry, revocation or block locks an open window too.
 function watch(){
   if(watchTimer)return;
   watchTimer=setInterval(async()=>{
     try{
       const state=await request('/api/cloud-license/status');
       if(state.active!==true){await present(state);}
       else offlineBanner(state);
     }catch(_){}
   },60000);
 }
 async function start(){
   if(busy)return;
   busy=true;login.disabled=true;
   try{
     const info=await request('/api/cloud-license/start','POST');
     const url=new URL(info.url);
     if(url.origin!=='https://ads.lhmcrm.com'||url.pathname!=='/desktop/pair/')
       throw Error('Liên kết Google không hợp lệ');
     code.textContent='Mã đối chiếu trên PC: '+info.code;
     report('Đang chờ xác nhận trên trình duyệt…');
     if(!await window.pywebview.api.open_license_url(url.href))
       throw Error('Không mở được trình duyệt. Hãy thử lại.');
     if(pollTimer)clearInterval(pollTimer);
     let tries=0,waiting=false;
     pollTimer=setInterval(async()=>{
       if(waiting)return;
       if(++tries>60){clearInterval(pollTimer);pollTimer=null;report('Mã hết hạn, vui lòng đăng nhập lại.');return;}
       waiting=true;
       try{
         const next=await request('/api/cloud-license/poll','POST');
         if(next.status==='authorized'){
           clearInterval(pollTimer);pollTimer=null;
           await present({...next,paired:true});
         }
       }catch(e){clearInterval(pollTimer);pollTimer=null;report(e.message);}
       finally{waiting=false;}
     },5000);
   }catch(e){report(e.message);}
   finally{login.disabled=false;busy=false;}
 }
 async function initialize(){
   if(!window.pywebview?.api?.get_local_license_proof)return;
   try{
     proof=await window.pywebview.api.get_local_license_proof();
     if(!proof)return; // Old Windows builds continue their unchanged local login.
     create();show();
     const status=await request('/api/cloud-license/status');
     // First check after start-up re-attaches this PC's seat when the window opens.
     await present(status.paired&&!status.active?{...await request('/api/cloud-license/attach','POST',{mode:'attach'}),paired:true}:status);
   }catch(e){if(panel){report(e.message);show();}}
 }
 if(window.pywebview?.api?.get_local_license_proof)initialize();
 else window.addEventListener('pywebviewready',initialize,{once:true});
})();
