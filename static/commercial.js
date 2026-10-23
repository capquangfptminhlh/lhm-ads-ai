/* LHM Ads AI offline license activation + local background monitor settings.
   All calls are through the authenticated loopback API; never send license to OpenRouter. */
'use strict';
(() => {
  const el = id => document.getElementById(id);
  const show = (msg, bad=false) => {const p=el('commercial-message'); p.textContent=msg;p.className=bad?'commercial-error':'commercial-ok'};
  const fmtDate = sec => sec ? new Date(sec*1000).toLocaleString('vi-VN') : '—';
  // Dedicated license status box: three clear states computed ONLY from the
  // /api/license payload (active, plan, expires_at, reason). Styling lives
  // in workspace-pages.css (.license-status-*); the CSP blocks inline styles.
  function renderLicenseStatus(license) {
    const box=el('license-status-box'),line=el('license-status-line'),
      guidance=el('license-status-guidance'),steps=el('license-activate-steps');
    if(!box||!line)return;
    const days=license.active?Math.max(Math.ceil((license.expires_at-Date.now()/1000)/86400),0):null;
    let state='inactive',lineText='',guidanceText='';
    if(license.active&&days>7){
      state='active';
      lineText=`Bản quyền đang hoạt động · Gói ${license.plan} · Còn ${days} ngày · Hết hạn ${fmtDate(license.expires_at)}`;
    } else if(license.active){
      state='expiring';
      lineText=`Bản quyền sắp hết hạn · Gói ${license.plan} · Còn ${days} ngày · Hết hạn ${fmtDate(license.expires_at)}`;
      guidanceText='Gia hạn: gửi mã máy cho đơn vị cung cấp và chuyển khoản theo hướng dẫn đã nhận. Sau khi nhận file license.json mới, dán nội dung vào ô bên dưới và bấm "Kích hoạt / Gia hạn".';
    } else if(license.reason==='clock_rollback'){
      state='inactive';
      lineText='Bản quyền tạm dừng vì đồng hồ Windows bị chỉnh lùi.';
      guidanceText='Vui lòng đồng bộ giờ Windows cho chính xác rồi mở lại trang này. Không xóa dữ liệu ứng dụng.';
    } else if(license.reason==='clock_state_invalid'){
      state='inactive';
      lineText='Chưa kiểm tra được bản quyền vì dữ liệu kiểm tra thời gian bị lỗi.';
      guidanceText='Liên hệ hỗ trợ để được hướng dẫn. Không xóa dữ liệu ứng dụng.';
    } else if(license.reason==='revoked'){
      state='inactive';
      lineText='Giấy phép đã bị thu hồi.';
      guidanceText='Giấy phép này không còn hiệu lực theo danh sách thu hồi của đơn vị cung cấp. Dữ liệu của bạn vẫn còn nguyên; liên hệ đơn vị cung cấp để được làm rõ và cấp lại nếu có nhầm lẫn.';
    } else if(license.reason==='revocation_list_invalid'){
      state='inactive';
      lineText='Không kiểm chứng được danh sách thu hồi giấy phép.';
      guidanceText='File danh sách thu hồi trên máy không hợp lệ nên phần mềm tạm dừng để bảo toàn. Liên hệ hỗ trợ; không tự xóa file trong thư mục dữ liệu.';
    } else {
      state='inactive';
      lineText='Chưa kích hoạt hoặc giấy phép đã hết hạn.';
      guidanceText='Chế độ chỉ đọc: dữ liệu vẫn có thể xem và xuất báo cáo, nhưng các thao tác với quảng cáo (kết nối tài khoản, duyệt kế hoạch, giám sát nền) đang tạm dừng cho đến khi kích hoạt lại.';
    }
    box.className='license-status license-status-'+state;
    line.textContent=lineText;
    const overview=el('license-overview-state');
    if(overview){overview.textContent=license.active?'Đang hoạt động':state==='expiring'?'Sắp hết hạn':'Chưa kích hoạt / hết hạn';overview.dataset.tone=license.active?'ok':'warn';}
    const device=el('license-overview-device');
    if(device)device.textContent=license.device?'Đã nhận diện máy':'Chưa xác minh';
    if(guidance){guidance.textContent=guidanceText;guidance.classList.toggle('hidden',!guidanceText);}
    if(steps)steps.classList.toggle('hidden',!!license.active);
  }
  const escape = value => String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  async function refresh() {
    try {
      const [license, monitor] = await Promise.all([api('/api/license'),api('/api/monitor')]);
      el('license-device').textContent=license.device||'—';
      const edition=license.edition==='commercial'?'BẢN THƯƠNG MẠI':'BẢN PILOT / KIỂM THỬ';
      el('license-edition').textContent=edition;
      el('license-state').textContent=license.active?
        `Đã kích hoạt · ${license.plan} · Hết hạn ${fmtDate(license.expires_at)}`:
        license.reason==='clock_rollback'?'Đồng hồ Windows bị chỉnh lùi. Vui lòng đồng bộ giờ chính xác để tiếp tục sử dụng.':
        license.reason==='clock_state_invalid'?'Dữ liệu kiểm tra thời gian bị lỗi. Liên hệ hỗ trợ, không xóa dữ liệu ứng dụng.':
        'Chưa kích hoạt hoặc giấy phép hết hạn. Dữ liệu vẫn có thể xem và xuất báo cáo.';
      renderLicenseStatus(license);
      el('monitor-enable').checked=monitor.settings.enabled;
      el('monitor-interval').value=String(monitor.settings.poll_minutes);
      const rows=monitor.samples.slice(0,8).map(s=>`<tr><td>${escape(s.label)}</td><td>${fmtDate(s.observed_at)}</td><td>${escape(s.error_code||s.source||'—')}</td></tr>`).join('');
      el('monitor-samples').innerHTML=rows ? `<table><thead><tr><th>Tài khoản</th><th>Lần đọc</th><th>Nguồn / lỗi</th></tr></thead><tbody>${rows}</tbody></table>` : '<span class="muted">Chưa có dữ liệu giám sát.</span>';
      el('monitor-help').textContent=monitor.note||'';
      if(!license.active)el('monitor-enable').checked=false;
      const msg=el('commercial-message'); if(msg)msg.textContent='';
    } catch(e) {
      // The initial load runs before login; only surface errors once the
      // authenticated shell is actually visible, and clear them on success.
      const shell=el('shell');
      if(shell&&!shell.classList.contains('hidden'))show(e.message||String(e),true);
    }
  }
  let localDiagnostics=null;
  async function refreshReadiness(){
    const panel=el('desktop-local-ops');
    try{
      const data=await api('/api/desktop/readiness');
      localDiagnostics=data;
      panel.classList.remove('hidden');
      el('readiness-summary').textContent=data.ready_for_commercial_distribution?
        'Đã hoàn tất các kiểm tra cơ bản.':
        'Chưa nghiệm thu thương mại: '+data.reason;
      const labels={ok:'Đạt',configured:'Đã cấu hình · cần kiểm tra API',
        available:'Sẵn có',manual:'Thủ công',action_required:'Cần thực hiện',
        not_verified:'CHƯA XÁC MINH',blocked:'Lỗi'};
      const descriptions={
        local_storage:'Dữ liệu SQLite trên máy',
        license:'Giấy phép thuê bao theo máy',
        oauth_google:'Ứng dụng Google OAuth · chưa xác minh quyền Ads',
        oauth_meta:'Ứng dụng Meta · có thể cần xét duyệt',
        live_api:'Kết nối API quảng cáo thật',
        authenticode:'Chữ ký nhà phát hành file EXE',
        secure_backup:'Sao lưu được mã hóa bằng mật khẩu',
        billing:'Thanh toán và xuất hóa đơn'
      };
      const groups=[
        ['Bản quyền và thiết bị',['local_storage','license','authenticode']],
        ['Kết nối quảng cáo',['oauth_google','oauth_meta','live_api']],
        ['Dữ liệu và vận hành',['secure_backup','billing']]
      ];
      const checks=new Map(data.checks.map(x=>[x.code,x]));
      el('readiness-checks').innerHTML=groups.map(([title,codes])=>
        '<section class="license-check-group"><h4>'+escape(title)+'</h4>'+
        codes.filter(code=>checks.has(code)).map(code=>{
          const item=checks.get(code),kind=['ok','available'].includes(item.status)?'ok':
            item.status==='blocked'?'bad':item.status==='not_verified'?'unknown':'warn';
          return '<div class="license-check-row"><span>'+escape(descriptions[code]||item.detail)+'</span>'+
            '<span class="license-state-pill license-state-'+kind+'">'+escape(labels[item.status]||item.status)+'</span></div>';
        }).join('')+'</section>'
      ).join('');
      const licenseCheck=checks.get('license');
      const apiCheck=checks.get('live_api');
      const localCheck=checks.get('local_storage');
      const state=(id,text,tone)=>{
        const node=el(id);if(node){node.textContent=text;node.dataset.tone=tone;}
      };
      state('license-overview-device',localCheck?.status==='ok'?'Dữ liệu máy: Đạt':'Cần kiểm tra dữ liệu',localCheck?.status==='ok'?'ok':'warn');
      state('license-overview-provider',apiCheck?.status==='ok'?'API đã xác minh':'API chưa xác minh',apiCheck?.status==='ok'?'ok':'neutral');
      state('license-overview-data',checks.get('secure_backup')?.status==='available'?'Có thể sao lưu':'Cần kiểm tra sao lưu',checks.get('secure_backup')?.status==='available'?'ok':'warn');
      // Readiness and license status are independent; never infer a live Ads
      // connection from Google/Meta OAuth configuration alone.
    }catch(e){
      localDiagnostics=null;panel.classList.add('hidden');
    }
  }
  function downloadJsonDiagnostics(){
    if(!localDiagnostics){show('Chưa tải được thông tin kiểm tra.',true);return;}
    const content=new Blob([JSON.stringify(localDiagnostics,null,2)],{type:'application/json'});
    const link=document.createElement('a');
    const url=URL.createObjectURL(content);
    link.href=url;link.download='lhm-ads-readiness.json';
    document.body.append(link);link.click();link.remove();
    setTimeout(()=>URL.revokeObjectURL(url),60000);
  }
  async function exportBackup(){
    const first=el('secure-backup-password'),second=el('secure-backup-confirm');
    const button=el('secure-backup-export');
    const password=first.value;
    if(password.length<16||password.length>256||password!==second.value){
      show('Nhập mật khẩu sao lưu tối thiểu 16 ký tự và xác nhận trùng khớp.',true);
      first.value='';second.value='';return;
    }
    if(!session?.csrf){
      show('Cần đăng nhập tài khoản quản trị để sao lưu.',true);
      first.value='';second.value='';return;
    }
    button.disabled=true;
    try{
      const response=await fetch('/api/desktop/backup/export',{
        method:'POST',credentials:'same-origin',
        headers:{'Content-Type':'application/json','X-CSRF-Token':session.csrf},
        body:JSON.stringify({passphrase:password})
      });
      if(!response.ok){
        const error=await response.json().catch(()=>({detail:'Không thể tạo sao lưu mã hóa'}));
        throw Error(error.detail||'Không thể tạo sao lưu mã hóa');
      }
      const blob=await response.blob();
      const url=URL.createObjectURL(blob);
      const link=document.createElement('a');
      link.href=url;link.download='lhm-ads-backup-'+new Date().toISOString().slice(0,10)+'.lhmbak';
      document.body.append(link);link.click();link.remove();
      setTimeout(()=>URL.revokeObjectURL(url),60000);
      show('Đã xuất bản sao lưu mã hóa. Hãy lưu mật khẩu ở nơi khác; không gửi cho hỗ trợ.');
    }catch(e){show(e.message||String(e),true)}
    finally{first.value='';second.value='';button.disabled=false;}
  }
  document.addEventListener('DOMContentLoaded', () => {
    const target=el('page-license');
    if(!target)return;
    const panel=document.createElement('article');panel.className='panel';
    panel.innerHTML=`<h3>Trạng thái giấy phép</h3>
      <p class="muted tiny">Mỗi máy có mã riêng; gia hạn bằng giấy phép ký số. Không chuyển dữ liệu Ads về máy chủ cấp phép.</p>
      <div class="license-meta"><p><b>Phiên bản:</b> <span id="license-edition">Đang kiểm tra...</span></p><p><b>Gói sử dụng:</b> <span id="license-state">Đang kiểm tra...</span></p></div>
      <div id="license-status-box" class="license-status license-status-unknown" role="status" aria-live="polite">
        <p id="license-status-line" class="license-status-line">Đang kiểm tra trạng thái bản quyền...</p>
        <p id="license-status-guidance" class="license-status-guidance hidden"></p>
      </div>
      <div class="license-overview-grid" aria-label="Tóm tắt tình trạng phần mềm">
        <div class="license-overview-card"><small>Giấy phép</small><strong id="license-overview-state" data-tone="neutral">Đang kiểm tra</strong></div>
        <div class="license-overview-card"><small>Thiết bị và dữ liệu</small><strong id="license-overview-device" data-tone="neutral">Đang kiểm tra</strong></div>
        <div class="license-overview-card"><small>API quảng cáo thật</small><strong id="license-overview-provider" data-tone="neutral">Chưa xác minh</strong></div>
        <div class="license-overview-card"><small>Sao lưu</small><strong id="license-overview-data" data-tone="neutral">Đang kiểm tra</strong></div>
      </div>
      <p><b>Mã máy:</b> <code id="license-device" class="wrap-anywhere"></code>
      <button type="button" id="license-copy-device" class="btn secondary" title="Sao chép mã máy để gửi cho bên bán">Sao chép mã máy</button></p>
      <details id="license-activation-panel" class="license-disclosure" open><summary>Kích hoạt / gia hạn giấy phép <span>Nhận giấy phép theo mã máy</span></summary><div class="license-disclosure-body"><section id="license-activate-steps" class="license-steps hidden" aria-label="Các bước kích hoạt bản quyền">
        <h4>Làm theo 3 bước để kích hoạt</h4>
        <ol class="license-steps-list">
          <li><b>Bước 1:</b> Sao chép mã máy ở trên bằng nút "Sao chép mã máy".</li>
          <li><b>Bước 2:</b> Gửi mã máy cho đơn vị cung cấp và chuyển khoản theo hướng dẫn đã nhận.</li>
          <li><b>Bước 3:</b> Nhận file license.json, dán nội dung vào ô bên dưới và bấm "Kích hoạt / Gia hạn".</li>
        </ol>
      </section>
      <label>Nhập nội dung file license.json (do đơn vị cung cấp phát hành)
        <textarea id="license-input" rows="4" placeholder="Dán JSON giấy phép đã ký tại đây"></textarea></label>
      <button id="license-activate" type="button" class="btn primary">Kích hoạt / Gia hạn</button></div></details>
      <details id="license-monitor-panel" class="license-disclosure"><summary>Giám sát quảng cáo chạy nền <span>Tùy chọn nâng cao</span></summary><div class="license-disclosure-body"><h3>Cấu hình giám sát</h3>
      <p class="muted tiny">Chỉ đọc báo cáo Google/Meta qua API và ghi lỗi. Máy phải bật, đăng nhập Windows và có Internet. Không tự tăng ngân sách hay chỉnh giá thầu.</p>
      <label><input type="checkbox" id="monitor-enable"> Bật giám sát tài khoản đã kết nối</label>
      <label>Chu kỳ đọc báo cáo <select id="monitor-interval"><option value="15">15 phút</option><option value="30">30 phút</option><option value="60">60 phút</option><option value="120">120 phút</option><option value="240">240 phút</option></select></label>
      <div class="btn-row"><button type="button" class="btn primary" id="monitor-save">Lưu cấu hình</button>
      <button type="button" class="btn secondary" id="monitor-autostart">Chạy nền khi đăng nhập Windows</button>
      <button type="button" class="btn secondary" id="monitor-stop">Tắt tự chạy</button></div>
      <p id="monitor-help" class="muted tiny"></p><div id="monitor-samples" class="table-wrap"></div></div></details>
      <section id="desktop-local-ops" class="hidden" aria-label="Sẵn sàng thương mại và sao lưu">
      <div class="license-preflight-heading"><h3>Kiểm tra bảo vệ dữ liệu</h3><p id="readiness-summary" class="muted tiny" role="status" aria-live="polite"></p></div>
      <details id="license-readiness-detail" class="license-disclosure"><summary>Xem các mục kiểm tra <span>Chi tiết kỹ thuật và trạng thái</span></summary><div class="license-disclosure-body">
      <div id="readiness-checks" class="license-check-grid" tabindex="0"></div>
      <div class="inline-actions inline-actions-spaced">
        <button type="button" id="readiness-refresh" class="btn secondary">↻ Kiểm tra lại</button>
        <button type="button" id="readiness-export" class="btn secondary">↓ Xuất báo cáo không chứa token</button>
      </div></div></details>
      <details id="license-backup-detail" class="license-disclosure"><summary>Sao lưu dữ liệu có mã hóa <span>Mở khi cần xuất bản sao an toàn</span></summary><div class="license-disclosure-body"><h3>Tạo bản sao lưu</h3>
      <p class="muted tiny">Bản sao lưu chứa dữ liệu khách và khóa Ads đã được mã hóa bằng mật khẩu riêng của bạn. Không gửi mật khẩu hay file backup cho bên thứ ba. Không bao gồm giấy phép theo máy; đổi máy phải kích hoạt lại.</p>
      <label>Mật khẩu sao lưu (ít nhất 16 ký tự)<input type="password" id="secure-backup-password" autocomplete="new-password" minlength="16" maxlength="256"></label>
      <label>Nhập lại mật khẩu<input type="password" id="secure-backup-confirm" autocomplete="new-password" minlength="16" maxlength="256"></label>
      <button type="button" class="btn primary" id="secure-backup-export">↓ Tải bản sao lưu .lhmbak đã mã hóa</button>
      <p class="muted tiny">Khôi phục cần kỹ thuật hỗ trợ khi phần mềm đã đóng, trên thư mục trống, không ghi đè dữ liệu đang có.</p>
      </div></details></section>
      <p id="commercial-message" role="status" aria-live="polite"></p>`;
    target.append(panel);
    el('license-copy-device').addEventListener('click',async()=>{
      try{await navigator.clipboard.writeText(el('license-device').textContent);show('Đã sao chép mã máy. Chỉ gửi mã máy, không gửi token Ads.')}
      catch(e){show('Không thể sao chép tự động. Chọn và sao chép mã máy hiển thị ở trên.',true)}
    });
    el('readiness-refresh').addEventListener('click',refreshReadiness);
    el('readiness-export').addEventListener('click',downloadJsonDiagnostics);
    el('secure-backup-export').addEventListener('click',exportBackup);
    el('license-activate').addEventListener('click', async()=>{try{
      await api('/api/license/activate',{method:'POST',body:JSON.stringify({license_text:el('license-input').value.trim()})});
      el('license-input').value='';show('Kích hoạt/gia hạn thành công');refresh();
    }catch(e){show(e.message,true)}});
    el('monitor-save').addEventListener('click',async()=>{try{
      await api('/api/monitor/settings',{method:'PUT',body:JSON.stringify({enabled:el('monitor-enable').checked,poll_minutes:Number(el('monitor-interval').value)})});
      show('Đã lưu cấu hình giám sát');refresh();
    }catch(e){show(e.message,true)}});
    el('monitor-autostart').addEventListener('click',async()=>{try{
      await api('/api/monitor/agent/enable',{method:'POST'});show('Đã bật tác nhân giám sát khi đăng nhập Windows');
    }catch(e){show(e.message,true)}});
    el('monitor-stop').addEventListener('click',async()=>{try{
      await api('/api/monitor/agent/disable',{method:'POST'});show('Đã tắt giám sát nền');refresh();
    }catch(e){show(e.message,true)}});
    refresh();
    // Session may not be available at initial page load; refresh when settings selected.
    const nav=document.querySelector('[data-page="license"]');
    if(nav)nav.addEventListener('click',()=>setTimeout(()=>{
      refresh();refreshReadiness();
    },100));
    const watcher=new MutationObserver(()=>{
      if(!target.classList.contains('hidden')&&!el('shell').classList.contains('hidden')){
        refresh();refreshReadiness();
      }
    });
    watcher.observe(target,{attributes:true,attributeFilter:['class']});
  });
})();
