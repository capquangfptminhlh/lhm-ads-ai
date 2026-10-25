/* On-device encrypted vault UI. No remote endpoints or credential exports. */
'use strict';
(() => {
  const api=window.LHMDeviceVault;
  const host=document.querySelector('#login .login-box');
  if(!api||!host||(!document.getElementById('lhm-static-api-guard')&&!document.getElementById('lhm-local-workspace')))return;
  const section=document.createElement('section');
  section.id='device-only-vault';
  section.className='lhm-vault-panel';
  // All labels are static. Never interpolate customer input into HTML.
  section.innerHTML=`<div class="lhm-vault-head">
    <span class="lhm-vault-mark" aria-hidden="true">🔐</span>
    <div><h3>Kho tài khoản Ads trên thiết bị</h3>
    <p>100% cục bộ và mã hóa. Không đồng bộ tài khoản hay token lên Cloudflare.</p></div></div>
    <p class="lhm-vault-warning">Bản PWA đang thử nghiệm: đây là kho dữ liệu cục bộ, <strong>chưa kết nối API Google, Meta hoặc TikTok</strong>. Không cần nhập access token vào giai đoạn này.</p>
    <div id="lhm-vault-status" role="status" aria-live="polite"></div>
    <form id="lhm-vault-access" autocomplete="off">
      <label>Mật khẩu riêng của kho (ít nhất 12 ký tự)
        <input id="lhm-vault-password" type="password" minlength="12" maxlength="512"
          autocomplete="new-password" required placeholder="Mật khẩu chỉ được dùng trên thiết bị này"></label>
      <button id="lhm-vault-access-action" class="btn primary" type="submit">Đang kiểm tra…</button>
    </form>
    <div id="lhm-vault-unlocked" class="hidden">
      <p class="lhm-vault-ok">Đã mở khóa. Dữ liệu ở lại trên thiết bị này.</p>
      <div class="lhm-vault-actions">
        <button class="btn secondary" id="lhm-vault-lock" type="button">Khóa ngay</button>
        <button class="btn secondary" id="lhm-vault-backup" type="button">Tải bản sao lưu mã hóa</button>
        <label class="lhm-vault-import">Khôi phục kho mã hóa <input type="file" id="lhm-vault-import" accept="application/json,.json"></label>
      </div>
      <form id="lhm-vault-add" autocomplete="off">
        <h4>Thêm thông tin tài khoản Ads</h4>
        <label>Nền tảng<select id="lhm-vault-platform"><option value="google">Google Ads</option>
          <option value="meta">Meta Ads</option><option value="tiktok">TikTok Ads</option></select></label>
        <label>ID tài khoản Ads<input id="lhm-vault-account" maxlength="128" required
            autocapitalize="off" autocomplete="off" placeholder="ID tài khoản của bạn"></label>
        <label>Tiền tệ<input id="lhm-vault-currency" maxlength="3" pattern="[A-Za-z]{3}" value="VND" required
            autocomplete="off" placeholder="VND hoặc USD"></label>
        <label>Tên gợi nhớ<input id="lhm-vault-label" maxlength="150" required
            autocomplete="off" placeholder="Ví dụ: Cửa hàng 1"></label>
        <button class="btn primary" type="submit">Lưu mã hóa trên thiết bị</button>
      </form>
      <div class="lhm-vault-list" aria-label="Tài khoản quảng cáo được lưu cục bộ">
        <h4>Danh sách cục bộ <span id="lhm-vault-count"></span></h4>
        <div id="lhm-vault-accounts"></div>
      </div>
      <button id="lhm-vault-destroy" class="btn secondary" type="button">Xóa toàn bộ kho trên thiết bị</button>
    </div>
    <p class="lhm-vault-footer">Quên mật khẩu thì không giải mã được dữ liệu. Xóa dữ liệu trình duyệt có thể làm mất kho; bản sao lưu mã hóa phải giữ an toàn. Khi khóa màn hình, trình duyệt có thể tạm dừng PWA nên không thể giám sát Ads liên tục.</p>`;
  host.append(section);
  const get=id=>document.getElementById(id);
  const status=s=>{get('lhm-vault-status').textContent=s;};
  const action=get('lhm-vault-access-action'),password=get('lhm-vault-password');
  let exists=false,busy=false,lastActive=Date.now();
  const resetPasswords=()=>{password.value='';};
  async function refreshAccess(){
    exists=await api.exists();
    action.textContent=exists?'Mở khóa kho':'Tạo kho mã hóa trên thiết bị';
    get('lhm-vault-access').classList.toggle('hidden',api.isUnlocked());
    get('lhm-vault-unlocked').classList.toggle('hidden',!api.isUnlocked());
    if(api.isUnlocked())render();
    else window.dispatchEvent(new Event('lhm:vault-locked'));
  }
  function render(){
    if(!api.isUnlocked())return;
    const entries=api.listAccounts();
    window.dispatchEvent(new Event('lhm:vault-change'));
    get('lhm-vault-count').textContent='('+entries.length+'/100)';
    const list=get('lhm-vault-accounts');
    list.replaceChildren();
    if(!entries.length){
      const empty=document.createElement('p');empty.textContent='Chưa lưu tài khoản Ads nào trên thiết bị này.';
      list.append(empty);return;
    }
    for(const x of entries){
      const row=document.createElement('div');row.className='lhm-vault-account';
      const txt=document.createElement('span');
      txt.textContent=x.label+' · '+x.platform.toUpperCase()+' · '+x.accountId;
      const del=document.createElement('button');del.type='button';del.className='btn secondary';
      del.textContent='Xóa';
      del.addEventListener('click',async()=>{
        if(!window.confirm('Xóa thông tin tài khoản '+x.label+' khỏi thiết bị này?'))return;
        try{await api.removeAccount(x.localId);render();status('Đã xóa cục bộ.');}
        catch(err){status(err.message);}
      });
      row.append(txt,del);list.append(row);
    }
  }
  get('lhm-vault-access').addEventListener('submit',async e=>{
    e.preventDefault();if(busy)return;
    busy=true;action.disabled=true;
    try{
      if(exists){await api.unlock(password.value);status('Đã mở khóa kho dữ liệu trên thiết bị.');}
      else{await api.create(password.value);status('Đã tạo kho dữ liệu mã hóa cục bộ.');}
      resetPasswords();lastActive=Date.now();await refreshAccess();
    }catch(err){status(err.message);}
    finally{busy=false;action.disabled=false;}
  });
  const lock=async reason=>{
    api.lock();resetPasswords();get('lhm-vault-add').reset();
    await refreshAccess();status(reason||'Kho đã khóa.');
  };
  get('lhm-vault-lock').addEventListener('click',()=>lock('Đã khóa và xóa khóa giải mã khỏi phiên ứng dụng.'));
  get('lhm-vault-add').addEventListener('submit',async e=>{
    e.preventDefault();
    const button=e.currentTarget.querySelector('button[type="submit"]');
    button.disabled=true;
    try{
      await api.upsertAccount({
        platform:get('lhm-vault-platform').value,
        accountId:get('lhm-vault-account').value,
        label:get('lhm-vault-label').value,
        currency:get('lhm-vault-currency').value
      });
      get('lhm-vault-add').reset();render();status('Thông tin đã lưu mã hóa cục bộ; chưa đồng nghĩa đã kết nối API.');
    }catch(err){status(err.message);}
    finally{button.disabled=false;}
  });
  get('lhm-vault-backup').addEventListener('click',async()=>{
    try{
      const data=await api.encryptedBackup();
      const link=document.createElement('a'),url=URL.createObjectURL(
        new Blob([data],{type:'application/json'}));
      link.href=url;link.download='lhm-ads-device-only-encrypted.json';
      document.body.append(link);link.click();link.remove();
      setTimeout(()=>URL.revokeObjectURL(url),1000);
      status('Đã xuất bản mã hóa. Giữ file và mật khẩu an toàn.');
    }catch(err){status(err.message);}
  });
  get('lhm-vault-import').addEventListener('change',async e=>{
    const file=e.currentTarget.files?.[0];e.currentTarget.value='';
    if(!file)return;
    if(file.size>4_000_000){status('Tệp sao lưu quá lớn.');return;}
    if(!window.confirm('Khôi phục sẽ GHI ĐÈ toàn bộ kho trên thiết bị này. Tiếp tục?'))return;
    try{
      await api.importBackup(await file.text());
      await refreshAccess();status('Đã nạp tệp mã hóa. Hãy mở khóa bằng mật khẩu bản sao lưu.');
    }catch(err){status(err.message);}
  });
  get('lhm-vault-destroy').addEventListener('click',async()=>{
    if(!window.confirm('Xóa vĩnh viễn toàn bộ kho Ads trên thiết bị này? Không thể hoàn tác.'))return;
    try{await api.destroy();await refreshAccess();status('Đã xóa toàn bộ dữ liệu kho cục bộ.');}
    catch(err){status(err.message);}
  });
  const activity=()=>{lastActive=Date.now();};
  for(const evt of ['pointerdown','keydown','touchstart']){
    section.addEventListener(evt,activity,{passive:true});
  }
  document.addEventListener('visibilitychange',()=>{
    if(document.visibilityState==='visible'&&api.isUnlocked()&&Date.now()-lastActive>5*60*1000)
      lock('Phiên kho đã được khóa khi bạn rời ứng dụng.');
  });
  setInterval(()=>{
    if(api.isUnlocked()&&Date.now()-lastActive>15*60*1000)
      lock('Kho tự khóa sau 15 phút không thao tác.');
  },60000);
  window.addEventListener('lhm:customer-ready',()=>refreshAccess().catch(err=>status(err.message)));
  refreshAccess().catch(err=>status(err.message));
})();
