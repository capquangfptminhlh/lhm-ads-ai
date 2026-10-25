/* Google-only license UX for the trusted Windows pywebview shell.
 * The native bridge supplies only a fresh local proof, never Ads credentials.
 * Browser OAuth happens in the real system browser (not in WebView2).
 */
'use strict';
(() => {
 let proof='',busy=false,pollTimer=null,bootstrapping=false;
 let panel,caption,code,login,attach,logout;
 const stylesheet=[
  'body.lhm-native-cloud #login{display:none!important}',
  '#lhm-cloud-gate{position:fixed;inset:0;z-index:100000;background:#091526f5;',
  'display:grid;place-items:center;padding:16px;color:#193550;font:15px/1.6 system-ui}',
  '#lhm-cloud-gate[hidden]{display:none!important}',
  '#lhm-cloud-gate article{background:white;width:min(100%,480px);border:1px solid #dae7f5;',
  'padding:30px;border-radius:22px;box-shadow:0 24px 70px #0006}',
  '#lhm-cloud-gate h2{font-size:23px;margin:0 0 12px;color:#153753}',
  '#lhm-cloud-gate p{color:#4e6884}',
  '#lhm-cloud-gate button{border:0;border-radius:11px;background:#146fc8;color:white;',
  'padding:12px 17px;margin:8px 6px 0 0;font-weight:750;cursor:pointer}',
  '#lhm-cloud-gate button:disabled{opacity:.5}',
  '#lhm-cloud-gate .notice{background:#eaf4ff;padding:13px;border-radius:12px;overflow-wrap:anywhere}'
 ].join('');
 const report=(value)=>{if(caption)caption.textContent=String(value);};
 const show=()=>{if(panel)panel.hidden=false;};
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
     '<button id="lhm-cloud-signin" type="button">Đăng nhập bằng Google</button>',
     '<button id="lhm-cloud-attach" type="button" hidden>Tiếp tục sử dụng</button>',
     '<button id="lhm-cloud-logout" type="button" hidden>Đổi Gmail</button>',
     '<p style="font-size:12px">Dữ liệu và token quảng cáo chỉ lưu mã hóa trên máy tính.</p>',
     '</article>'
   ].join('');
   document.body.append(panel);
   caption=panel.querySelector('#lhm-cloud-status');
   code=panel.querySelector('#lhm-cloud-code');
   login=panel.querySelector('#lhm-cloud-signin');
   attach=panel.querySelector('#lhm-cloud-attach');
   logout=panel.querySelector('#lhm-cloud-logout');
   login.onclick=start;
   attach.onclick=async()=>{
     try{report('Đang kiểm tra lượt sử dụng…');const x=await request('/api/cloud-license/attach','POST');await present(x);}
     catch(e){report(e.message);}
   };
   logout.onclick=async()=>{
     try{
       await request('/api/cloud-license/logout','POST');
       code.textContent='';report('Đã đăng xuất. Đăng nhập Gmail để tiếp tục.');
       attach.hidden=true;logout.hidden=true;show();
       // Clear old UI-bound local session; the next login establishes a new tenant.
       window.dispatchEvent(new Event('lhm:local-logout'));
     }catch(e){report(e.message);}
   };
 }
 async function request(path,method='GET'){
   const headers={'Accept':'application/json','X-LHM-Native-Proof':proof};
   if(method==='POST')headers['Content-Type']='application/json';
   const response=await fetch(path,{
     method,headers,credentials:'same-origin',cache:'no-store',
     ...(method==='POST'?{body:'{}'}:{})
   });
   const data=await response.json().catch(()=>({}));
   if(!response.ok)throw Error(data.detail||data.error||'Không kết nối được máy chủ bản quyền');
   return data;
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
 async function present(data){
   if(data?.email)report('Gmail: '+data.email);
   if(data?.active===true){
     code.textContent='';attach.hidden=true;logout.hidden=false;
     report('Gói còn hạn. Đang mở Studio…');
     await localSession();
   }else{
     show();
     attach.hidden=!data?.paired;
     logout.hidden=!data?.paired;
     report(data?.paired
       ?'Đã đăng nhập Gmail. Bấm Tiếp tục để kiểm tra lại gói.'
       :'Đăng nhập Google và chọn gói dịch vụ để bắt đầu.');
   }
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
     await present(status);
   }catch(e){if(panel){report(e.message);show();}}
 }
 if(window.pywebview?.api?.get_local_license_proof)initialize();
 else window.addEventListener('pywebviewready',initialize,{once:true});
})();
