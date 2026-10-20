/* FinPoint v2: local monitoring and approval data, no invented KPIs. */
(function(){
  let pending=false;
  const e=id=>document.getElementById(id);
  const dt=n=>n?new Date(Number(n)*1000).toLocaleString('vi-VN'):'Chưa có';
  const info=(id,s)=>{if(e(id))e(id).textContent=String(s??'—')};
  const showing=()=>e('shell')&&!e('shell').classList.contains('hidden')&&!e('page-dashboard')?.classList.contains('hidden');
  async function query(url){const r=await fetch(url,{credentials:'same-origin',headers:{Accept:'application/json'}});if(!r.ok)throw Error('HTTP '+r.status);return r.json()}
  function notice(id,txt,style){const x=e(id);if(x){x.textContent=txt;x.className='fp-v2-pill '+style}}
  function renderAlerts(a,m){
    const root=e('fp-v2-alerts');if(!root)return;root.replaceChildren();
    if(!a&&!m){info('fp-v2-note','Không truy vấn được nguồn cảnh báo.');return}
    const items=(a?.findings||[]).filter(x=>!x.acknowledged_at&&!x.resolved_at).map(x=>({name:x.account_label,msg:x.message,at:x.last_seen_at}))
      .concat((m?.alerts||[]).filter(x=>!x.resolved_at).map(x=>({name:x.label,msg:x.message,at:x.created_at})))
      .sort((x,y)=>Number(y.at||0)-Number(x.at||0)).slice(0,4);
    if(!items.length){const p=document.createElement('p');p.textContent='Chưa có cảnh báo cần xử lý.';p.className='muted';root.append(p);return}
    for(const item of items){const row=document.createElement('div');row.className='fp-v2-alert';const icon=document.createElement('span');icon.className='fp-v2-alert-icon';icon.textContent='!';const body=document.createElement('div');const title=document.createElement('strong');title.textContent=item.name||'Tài khoản cần kiểm tra';const desc=document.createElement('small');desc.textContent=item.msg||'Kiểm tra số liệu';body.append(title,desc);const time=document.createElement('time');time.textContent=dt(item.at);row.append(icon,body,time);root.append(row)}
  }
  async function refresh(){
    if(!showing()||pending)return;
    pending=true;
    try{
      const calls=['/api/monitor','/api/advisor/status','/api/license','/api/actions','/api/autopilot/plans','/api/studio/me'];
      const res=await Promise.allSettled(calls.map(query)),v=i=>res[i].status==='fulfilled'?res[i].value:null;
      const mon=v(0),adv=v(1),license=v(2),act=v(3),plans=v(4),me=v(5);
      const running=Boolean(adv?.agent?.running),enabled=Boolean(mon?.settings?.enabled);
      notice('fp-v2-agent',running?'Agent Windows đang chạy':enabled?'Chưa xác nhận agent đang chạy':'Giám sát nền chưa bật',running?'good':enabled?'warn':'off');
      notice('fp-v2-license',license?.active?'Giấy phép còn hạn':license?'Giấy phép hết hạn/chưa kích hoạt':'Chưa xác định bản quyền',license?.active?'good':'warn');
      info('fp-v2-scan',dt(adv?.agent?.last_seen_at));
      info('fp-v2-sample',mon?.samples?.length?dt(mon.samples[0].observed_at):'Chưa đồng bộ');
      info('fp-v2-alert-count',adv?(adv.findings||[]).filter(x=>!x.acknowledged_at&&!x.resolved_at).length:'—');
      info('fp-v2-approve-count',Array.isArray(act)&&Array.isArray(plans)?act.concat(plans).filter(x=>x.status==='pending').length:'—');
      info('fp-v2-cycle',mon?.settings?.poll_minutes?mon.settings.poll_minutes+' phút':'Chưa cấu hình');
      renderAlerts(adv,mon);
      if(e('fp-v2-stop'))e('fp-v2-stop').hidden=me?.role!=='admin';
    }finally{pending=false}
  }
  async function stop(){
    if(!window.confirm('Khóa quyền chỉnh quảng cáo của Autopilot trên máy này? Lệnh này KHÔNG tắt chiến dịch đang chạy trên Google hoặc Meta.'))return;
    const btn=e('fp-v2-stop');btn.disabled=true;
    try{const me=await query('/api/studio/me');if(me.role!=='admin'||!me.csrf)throw Error('Chỉ Admin được thao tác.');
      const r=await fetch('/api/autopilot/emergency-stop',{method:'POST',credentials:'same-origin',headers:{'X-CSRF-Token':me.csrf,Accept:'application/json'}});
      if(!r.ok)throw Error('Chưa thể dừng quyền ghi: HTTP '+r.status);
      info('fp-v2-message','Đã dừng quyền ghi Autopilot. Chiến dịch thực tế KHÔNG bị tạm dừng.');
    }catch(err){info('fp-v2-message',err.message||'Thao tác thất bại')}finally{btn.disabled=false}
  }
  function init(){
    const host=e('page-dashboard');if(!host||e('fp-v2'))return;
    const sec=document.createElement('section');sec.id='fp-v2';sec.className='fp-v2-grid';sec.setAttribute('aria-label','Trung tâm giám sát quảng cáo');
    sec.innerHTML='<article class="fp-v2-card"><header><div><span class="fp-v2-kicker">LOCAL OPERATIONS</span><h3>Trung tâm giám sát AI</h3><p>Dữ liệu từ tác nhân trên máy khách hàng</p></div><button type="button" id="fp-v2-refresh" class="fp-v2-btn">↻ Làm mới</button></header><div class="fp-v2-badges"><span class="fp-v2-pill" id="fp-v2-agent">Đang kiểm tra agent…</span><span class="fp-v2-pill" id="fp-v2-license">Đang kiểm tra giấy phép…</span></div><div class="fp-v2-kpis"><div><small>Cảnh báo chưa xử lý</small><strong id="fp-v2-alert-count">—</strong></div><div><small>Yêu cầu chờ duyệt</small><strong id="fp-v2-approve-count">—</strong></div><div><small>Đọc báo cáo gần nhất</small><strong id="fp-v2-sample">—</strong></div></div><p class="fp-v2-caption">Nhịp agent: <b id="fp-v2-scan">—</b> · Chu kỳ: <b id="fp-v2-cycle">—</b>. Giám sát dừng khi Windows tắt hoặc ngủ.</p><div class="fp-v2-actions"><button type="button" data-v2-page="accounts">Tài khoản Ads</button><button type="button" data-v2-page="approvals">Duyệt hành động</button><button type="button" data-v2-page="assistant">AI Center</button><button type="button" id="fp-v2-stop" class="danger" hidden>■ Dừng quyền tự chỉnh</button></div><p class="fp-v2-message" id="fp-v2-message" role="status"></p></article><article class="fp-v2-card"><header><div><span class="fp-v2-kicker">ADS WATCH</span><h3>Cảnh báo gần đây</h3><p>Đề xuất cần xác minh trước khi sửa Ads</p></div><button type="button" class="fp-v2-btn" data-v2-page="settings">Cài đặt →</button></header><div class="fp-v2-alerts" id="fp-v2-alerts" aria-live="polite">Đang tải…</div><p id="fp-v2-note" class="fp-v2-caption"></p></article>';
    const before=host.querySelector('.fp-ops');before?before.before(sec):host.append(sec);
    e('fp-v2-refresh').addEventListener('click',refresh);e('fp-v2-stop').addEventListener('click',stop);
    sec.querySelectorAll('[data-v2-page]').forEach(b=>b.addEventListener('click',()=>document.querySelector('.nav-link[data-page="'+b.dataset.v2Page+'"]')?.click()));
    new MutationObserver(()=>{if(showing())refresh()}).observe(e('shell'),{attributes:true,attributeFilter:['class']});
    document.addEventListener('click',x=>{if(x.target.closest('.nav-link[data-page="dashboard"]'))setTimeout(refresh,60)});
    setInterval(()=>{if(showing())refresh()},60000);refresh();
  }
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',init);else init();
})();
