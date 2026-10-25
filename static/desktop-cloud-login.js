/* Windows first-party cloud licensing: only license metadata is exchanged.
 * The Ads APIs are gated independently by the local Python backend.
 */
'use strict';
(() => {
 let enabled=false,active=false,busy=false,timer=null,csrf='';
 let overlay,codeLabel,statusText,emailLabel,signin,attach,signout;
 const css=[
 '#lhm-cloud-gate{position:fixed;inset:0;z-index:100000;background:rgba(8,18,35,.94);',
 'display:flex;align-items:center;justify-content:center;padding:20px;color:#172f4b;font:15px/1.6 system-ui}',
 '#lhm-cloud-gate[hidden]{display:none!important}',
 '#lhm-cloud-gate .lhm-cloud-card{width:min(100%,480px);padding:30px;border:1px solid #d8e6f4;',
 'border-radius:20px;background:#fff;box-shadow:0 25px 80px #020d2144}',
 '#lhm-cloud-gate h2{font-size:23px;line-height:1.3;margin:0 0 10px;color:#1b3858}',
 '#lhm-cloud-gate p{color:#526882;margin:10px 0}',
 '#lhm-cloud-gate button{background:#166dc6;color:#fff;border:0;border-radius:12px;',
 'padding:12px 16px;font-size:14px;font-weight:750;margin:8px 8px 0 0;cursor:pointer}',
 '#lhm-cloud-gate button:disabled{opacity:.55}',
 '#lhm-cloud-gate .lhm-cloud-muted{background:#edf5ff;border-radius:10px;padding:12px}'
 ].join('');
 function render(){
   if(!enabled||!overlay)return;
   const localLoggedIn=!document.getElementById('shell')?.classList.contains('hidden');
   overlay.hidden=!localLoggedIn||active;
   emailLabel.textContent=window.lhmCloudEmail||'';
 }
 function create(){
   if(overlay)return;
   const s=document.createElement('style');s.textContent=css;document.head.append(s);
   overlay=document.createElement('section');overlay.id='lhm-cloud-gate';overlay.hidden=true;
   overlay.setAttribute('aria-label','Kích hoạt bản quyền LHM Ads AI');
   overlay.innerHTML=[
     '<div class="lhm-cloud-card" role="dialog" aria-modal="true">',
     '<h2>Đăng nhập Google để sử dụng LHM Ads AI</h2>',
     '<p>Phần mềm kiểm tra gói còn hạn và số phiên đồng thời trên máy chủ LHM.</p>',
     '<p id="lhm-cloud-email"></p>',
     '<p class="lhm-cloud-muted" id="lhm-cloud-status">Chưa kích hoạt.</p>',
     '<p id="lhm-cloud-code"></p>',
     '<button id="lhm-cloud-signin" type="button">Đăng nhập bằng Google</button>',
     '<button id="lhm-cloud-attach" type="button" hidden>Tiếp tục trên máy này</button>',
     '<button id="lhm-cloud-signout" type="button" hidden>Đổi tài khoản Google</button>',
     '<p style="font-size:12px">Không gửi token Google Ads, Meta Ads hoặc dữ liệu chiến dịch về LHM.</p>',
     '</div>'
   ].join('');
   document.body.append(overlay);
   codeLabel=overlay.querySelector('#lhm-cloud-code');
   statusText=overlay.querySelector('#lhm-cloud-status');
   emailLabel=overlay.querySelector('#lhm-cloud-email');
   signin=overlay.querySelector('#lhm-cloud-signin');
   attach=overlay.querySelector('#lhm-cloud-attach');
   signout=overlay.querySelector('#lhm-cloud-signout');
   signin.onclick=start;
   attach.onclick=async()=>{
     try{const x=await api('/api/cloud-license/attach','POST');update({...x,paired:true});
       if(!x.active)statusText.textContent='Chưa có quyền sử dụng. Kiểm tra gói và thử lại.';}
     catch(e){statusText.textContent=e.message;}
   };
   signout.onclick=async()=>{
     try{await api('/api/cloud-license/logout','POST');active=false;window.lhmCloudEmail='';update({active:false,paired:false});}
     catch(e){statusText.textContent=e.message;}
   };
 }
 async function api(path,method='GET'){
   const headers={Accept:'application/json'};
   if(method!=='GET'){headers['content-type']='application/json';headers['x-csrf-token']=csrf;}
   const response=await fetch(path,{method,credentials:'same-origin',headers,
     ...(method==='POST'?{body:'{}'}:{}),cache:'no-store'});
   const data=await response.json().catch(()=>({}));
   if(!response.ok)throw Error(data?.detail||data?.error||'Không thể xác thực bản quyền');
   return data;
 }
 function update(x){
   active=!!x.active;
   if(x.email)window.lhmCloudEmail=x.email;
   attach.hidden=!x.paired;
   signout.hidden=!x.paired;
   statusText.textContent=x.active?'Bản quyền đã kích hoạt':x.paired?
     'Đã đăng nhập Google. Bấm Tiếp tục trên máy này.':'Đăng nhập Google và chọn gói nếu chưa mua.';
   if(x.active){
     codeLabel.textContent='';
     if(timer)clearInterval(timer);
     timer=null;
     window.dispatchEvent(new Event('lhm:cloud-license-active'));
   }
   render();
 }
 async function start(){
   if(busy)return;
   busy=true;signin.disabled=true;
   try{
     const d=await api('/api/cloud-license/start','POST');
     codeLabel.textContent='Mã đối chiếu PC: '+d.code;
     statusText.textContent='Đang chờ Google xác nhận trên trình duyệt…';
     const url=new URL(d.url);
     if(url.origin!=='https://ads.lhmcrm.com'||url.pathname!=='/desktop/pair/')throw Error('Liên kết không hợp lệ');
     if(window.pywebview?.api?.open_license_url){
       if(!await window.pywebview.api.open_license_url(url.href))throw Error('Không mở được trình duyệt');
     }else window.open(url.href,'_blank','noopener,noreferrer');
     if(timer)clearInterval(timer);
     let attempts=0;
     timer=setInterval(async()=>{
       attempts++;
       if(attempts>35){clearInterval(timer);timer=null;statusText.textContent='Mã đã hết hạn. Bấm đăng nhập lại.';return;}
       try{
         const x=await api('/api/cloud-license/poll','POST');
         if(x.status==='authorized'){clearInterval(timer);timer=null;update({...x,paired:true});}
       }catch(e){clearInterval(timer);timer=null;statusText.textContent=e.message;}
     },5000);
   }catch(e){statusText.textContent=e.message;}
   finally{busy=false;signin.disabled=false;}
 }
 async function check(){
   try{
     const profile=await api('/api/studio/me');csrf=profile.csrf||'';
     const state=await api('/api/cloud-license/status');
     enabled=!!state.enabled;
     if(enabled){create();update(state);}
   }catch(_){/* Requires the local vault session, no fake authorization. */}
 }
 window.addEventListener('lhm:local-login',check);
 window.addEventListener('lhm:local-logout',()=>{if(overlay)overlay.hidden=true;});
 check();
})();
