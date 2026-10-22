/* Private on-device campaign alert center. Read-only; no ad mutation button. */
'use strict';
(() => {
  const $=id=>document.getElementById(id);
  const e=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const time=v=>v?new Date(v*1000).toLocaleString('vi-VN'):'Chưa có';
  const status=message=>{const node=$('advisor-message');if(node)node.textContent=message};
  async function loadAdvisor(){
    if(!$('advisor-list'))return;
    try {
      const [data, accounts]=await Promise.all([api('/api/advisor/status'),api('/api/accounts')]);
      const agent=data.agent;
      $('advisor-agent').textContent=agent.running?
        `Giám sát nền hoạt động · Nhận tín hiệu ${time(agent.last_seen_at)}`:
        `Chưa phát hiện giám sát nền đang chạy · Lần cuối ${time(agent.last_seen_at)}`;
      $('advisor-select').innerHTML=accounts.filter(a=>['google','meta'].includes(a.platform)&&a.connected)
        .map(a=>`<option value="${Number(a.id)}">${e(a.label)} (${e(a.platform)})</option>`).join('');
      const list=data.findings||[];
      const outcomeText={improved:'Kiểm chứng sau 7+ ngày: chỉ số đã cải thiện',worsened:'Kiểm chứng sau 7+ ngày: chỉ số xấu đi',unchanged:'Kiểm chứng sau 7+ ngày: chưa thay đổi đáng kể',insufficient_data:'Kiểm chứng: chưa đủ dữ liệu để phán quyết'};
      const renderDetail=f=>{
        let d=null; try{d=f.detail?JSON.parse(f.detail):null;}catch(_err){d=null;}
        let html='';
        if(d&&d.playbook){
          const p=d.playbook;
          if(p.why)html+=`<p class="muted tiny">${e(p.why)}</p>`;
          if(Array.isArray(p.actions)&&p.actions.length)
            html+=`<ul class="tiny">`+p.actions.slice(0,5).map(a=>`<li>${e(a)}</li>`).join('')+`</ul>`;
          if(Array.isArray(p.guardrails)&&p.guardrails.length)
            html+=`<p class="muted tiny">Rào chắn: ${p.guardrails.map(g=>e(g)).join(' · ')}</p>`;
        }
        if(f.outcome&&outcomeText[f.outcome])html+=`<p class="tiny"><b>${e(outcomeText[f.outcome])}</b></p>`;
        return html;
      };
      $('advisor-count').textContent=String(list.filter(f=>!f.acknowledged_at&&!f.resolved_at).length);
      $('advisor-list').innerHTML=list.length?`<table><thead><tr><th>Tài khoản</th><th>Chiến dịch</th><th>Cảnh báo</th><th>Phát hiện</th><th>Thao tác</th></tr></thead><tbody>`+
        list.map(f=>`<tr><td>${e(f.account_label)}</td><td>${e(f.campaign_id)}</td>`+
          `<td><b>${e(f.rule_code)}</b><p class="muted tiny">${e(f.message)}</p>${renderDetail(f)}</td><td>${time(f.last_seen_at)}</td>`+
          `<td>${f.resolved_at?'Đã phục hồi':f.acknowledged_at?'Đã xem':`<button type="button" class="btn secondary" data-ack-finding="${Number(f.id)}">Đánh dấu đã xem</button>`}</td></tr>`).join('')+
        '</tbody></table>':`<p class="muted">Chưa có cảnh báo. Bật giám sát nền tại Cài đặt hoặc quét tài khoản để kiểm tra.</p>`;
      $('advisor-warning').textContent='Cảnh báo theo quy tắc, không phải AI tự ra lệnh. Không tự dừng chiến dịch hoặc đổi ngân sách.';
    } catch(err){status(err.message||String(err));}
  }
  document.addEventListener('DOMContentLoaded',()=>{
    const area=$('page-alerts'); if(!area)return;
    const panel=document.createElement('article');panel.className='panel';
    panel.innerHTML=`<div class="panel-title"><div><h3>Cảnh báo tối ưu 24/7</h3><p class="muted tiny">Dữ liệu giữ trên máy; quét tối đa hằng ngày mỗi tài khoản khi máy bật và có Internet.</p></div><span class="pill"><span id="advisor-count">0</span> cần xem</span></div>
      <p id="advisor-agent" class="muted tiny">Đang kiểm tra tác nhân nền...</p>
      <div class="inline-actions admin-only"><select id="advisor-select" aria-label="Tài khoản Ads cần quét"></select><button class="btn secondary" id="advisor-scan" type="button">Quét cảnh báo ngay</button><button class="btn secondary" id="advisor-refresh" type="button">Làm mới</button></div>
      <p id="advisor-warning" class="muted tiny"></p><p id="advisor-message" role="status" class="muted tiny"></p>
      <div id="advisor-list" class="table-wrap"></div>`;
    area.append(panel);
    $('advisor-refresh').addEventListener('click',loadAdvisor);
    $('advisor-scan').addEventListener('click',async()=>{
      const aid=Number($('advisor-select').value); if(!Number.isSafeInteger(aid)||aid<=0)return;
      try{const result=await api('/api/advisor/accounts/'+aid+'/scan',{method:'POST'});
        status(result.scanned?`Đã quét; ${result.recommendations} vấn đề cần xem.`:
          `Chưa quét lại: ${result.reason}. Giới hạn một lượt quét mỗi giờ.`);await loadAdvisor();}
      catch(err){status(err.message||String(err));}
    });
    panel.addEventListener('click',async(event)=>{
      const b=event.target.closest('[data-ack-finding]');if(!b)return;
      try{await api('/api/advisor/findings/'+Number(b.dataset.ackFinding)+'/acknowledge',{method:'POST'});
          await loadAdvisor();status('Đã đánh dấu xem cảnh báo. Không có thay đổi nào gửi đến tài khoản Ads.');}
      catch(err){status(err.message||String(err));}
    });
    const nav=document.querySelector('[data-page="alerts"]');if(nav)nav.addEventListener('click',()=>setTimeout(loadAdvisor,50));
  });
})();