/* LHM Ads AI offline license activation + local background monitor settings.
   All calls are through the authenticated loopback API; never send license to OpenRouter. */
'use strict';
(() => {
  const el = id => document.getElementById(id);
  const show = (msg, bad=false) => {const p=el('commercial-message'); p.textContent=msg;p.style.color=bad?'#b91c1c':'#15803d'};
  const fmtDate = sec => sec ? new Date(sec*1000).toLocaleString('vi-VN') : '—';
  const escape = value => String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  async function refresh() {
    try {
      const [license, monitor] = await Promise.all([api('/api/license'),api('/api/monitor')]);
      el('license-device').textContent=license.device||'—';
      el('license-state').textContent=license.active?
        `Đã kích hoạt · ${license.plan} · Hết hạn ${fmtDate(license.expires_at)}`:
        'Chưa kích hoạt hoặc giấy phép hết hạn. Dữ liệu vẫn có thể xem và xuất báo cáo.';
      el('monitor-enable').checked=monitor.settings.enabled;
      el('monitor-interval').value=String(monitor.settings.poll_minutes);
      const rows=monitor.samples.slice(0,8).map(s=>`<tr><td>${escape(s.label)}</td><td>${fmtDate(s.observed_at)}</td><td>${escape(s.error_code||s.source||'—')}</td></tr>`).join('');
      el('monitor-samples').innerHTML=rows ? `<table><thead><tr><th>Tài khoản</th><th>Lần đọc</th><th>Nguồn / lỗi</th></tr></thead><tbody>${rows}</tbody></table>` : '<span class="muted">Chưa có dữ liệu giám sát.</span>';
      el('monitor-help').textContent=monitor.note||'';
      if(!license.active)el('monitor-enable').checked=false;
    } catch(e) {show(e.message||String(e),true)}
  }
  document.addEventListener('DOMContentLoaded', () => {
    const target=el('page-license');
    if(!target)return;
    const panel=document.createElement('article');panel.className='panel';
    panel.innerHTML=`<h3>Bản quyền thuê bao theo tháng</h3>
      <p class="muted tiny">Mỗi máy có mã riêng; gia hạn bằng giấy phép ký số. Không chuyển dữ liệu Ads về máy chủ cấp phép.</p>
      <p><b>Trạng thái:</b> <span id="license-state">Đang kiểm tra...</span></p>
      <p><b>Mã máy:</b> <code id="license-device" style="overflow-wrap:anywhere"></code></p>
      <label>Nhập nội dung file license.json (do đơn vị cung cấp phát hành)
        <textarea id="license-input" rows="4" placeholder="Dán JSON giấy phép đã ký tại đây"></textarea></label>
      <button id="license-activate" type="button" class="btn primary">Kích hoạt / Gia hạn</button>
      <hr><h3>Giám sát quảng cáo chạy nền</h3>
      <p class="muted tiny">Chỉ đọc báo cáo Google/Meta qua API và ghi lỗi. Máy phải bật, đăng nhập Windows và có Internet. Không tự tăng ngân sách hay chỉnh giá thầu.</p>
      <label><input type="checkbox" id="monitor-enable"> Bật giám sát tài khoản đã kết nối</label>
      <label>Chu kỳ đọc báo cáo <select id="monitor-interval"><option value="15">15 phút</option><option value="30">30 phút</option><option value="60">60 phút</option><option value="120">120 phút</option><option value="240">240 phút</option></select></label>
      <div style="display:flex;gap:8px;flex-wrap:wrap;margin:10px 0"><button type="button" class="btn primary" id="monitor-save">Lưu cấu hình</button>
      <button type="button" class="btn secondary" id="monitor-autostart">Chạy nền khi đăng nhập Windows</button>
      <button type="button" class="btn secondary" id="monitor-stop">Tắt tự chạy</button></div>
      <p id="monitor-help" class="muted tiny"></p><div id="monitor-samples" class="table-wrap"></div>
      <p id="commercial-message" role="status" aria-live="polite"></p>`;
    target.append(panel);
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
    const nav=document.querySelector('[data-page="license"]');if(nav)nav.addEventListener('click',()=>setTimeout(refresh,100));
  });
})();
