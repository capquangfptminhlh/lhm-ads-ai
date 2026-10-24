/* Soft-depth authentication microinteractions.
 * No network calls, no credential reads, no changed auth semantics.
 */
'use strict';
(() => {
  const login=document.querySelector('#login.login-layout');
  if(!login)return;
  const password=document.getElementById('login-pass');
  if(password && !password.closest('.lhm-soft-password')){
    const wrap=document.createElement('div');
    wrap.className='lhm-soft-password';
    password.parentElement.insertBefore(wrap,password);
    wrap.append(password);
    const eye=document.createElement('button');
    eye.type='button';
    eye.className='lhm-soft-eye';
    eye.setAttribute('aria-label','Hiện mật khẩu');
    eye.setAttribute('aria-pressed','false');
    eye.setAttribute('aria-controls','login-pass');
    eye.textContent='◉';
    eye.addEventListener('click',()=>{
      const visible=password.type==='password';
      password.type=visible?'text':'password';
      eye.setAttribute('aria-label',visible?'Ẩn mật khẩu':'Hiện mật khẩu');
      eye.setAttribute('aria-pressed',String(visible));
      eye.textContent=visible?'◎':'◉';
      password.focus({preventScroll:true});
    });
    wrap.append(eye);
  }
  // Only the Cloudflare *static* build has an offline /local/ workspace.
  // Desktop FastAPI must never link to an endpoint it does not serve.
  if(document.getElementById('lhm-static-api-guard')){
    const box=login.querySelector('.login-box');
    const install=box?.querySelector('#pwa-install-button');
    if(box && install && !box.querySelector('.lhm-soft-local-link')){
      const link=document.createElement('a');
      link.href='/local/';
      link.className='lhm-soft-local-link';
      link.textContent='Tiếp tục với dữ liệu trên thiết bị';
      const arrow=document.createElement('span');
      arrow.textContent='→';
      arrow.setAttribute('aria-hidden','true');
      link.append(arrow);
      install.before(link);
    }
  }
})();
