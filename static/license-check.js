/* Online-only, read-only subscription lookup; never store or log raw keys. */
'use strict';
(() => {
  const form=document.getElementById('license-check-form');
  const field=document.getElementById('license-key');
  const result=document.getElementById('license-check-result');
  if(!form||!field||!result)return;
  form.addEventListener('submit',async event=>{
    event.preventDefault();
    const key=field.value.trim();
    field.value='';
    const button=form.querySelector('button[type=submit]');
    button.disabled=true;
    result.textContent='Đang kiểm tra bản quyền…';
    try{
      const response=await fetch('/api/license/verify',{
        method:'POST',
        credentials:'same-origin',
        cache:'no-store',
        headers:{'Content-Type':'application/json'},
        body:JSON.stringify({key})
      });
      const data=await response.json();
      if(!response.ok)throw new Error('Máy chủ bản quyền chưa sẵn sàng ('+response.status+').');
      result.textContent=data.valid
        ? 'Key hợp lệ. Hạn sử dụng: '+new Date(data.expires_at).toLocaleDateString('vi-VN')+'.'
        : 'Key không hợp lệ, đã hết hạn hoặc đã bị thu hồi.';
    }catch(_){
      result.textContent='Không thể kiểm tra. Cần Internet và máy chủ Cloudflare D1 hoạt động.';
    }finally{button.disabled=false;}
  });
})();
