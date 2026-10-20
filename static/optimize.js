/* Real read-only campaign report + conservative rules; requests always require admin approval. */
'use strict';
(() => {
  const el = id => document.getElementById(id);
  const escHtml = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const show = (message, error=false) => { const node=el('optimization-message'); node.textContent=message; node.style.color=error?'#b91c1c':'inherit'; };
  const actionForm = () => el('pause-form');
  async function inspect() {
    const accountId=Number(el('opt-account').value);
    if (!accountId) return;
    const output=el('optimization-result'); output.textContent='Đang đọc chiến dịch qua API chính thức...';
    try {
      const data=await api('/api/optimizations/accounts/'+accountId);
      const cur=data.currency;
      const fmt=(v)=>v===null||v===undefined?'Chưa có dữ liệu':Number(v).toLocaleString('vi-VN',{maximumFractionDigits:2});
      let html=`<p class="muted tiny">${escHtml(data.note)}</p><div class="table-wrap"><table><thead><tr><th>Chiến dịch</th><th>Trạng thái</th><th>Chi phí 7 ngày</th><th>CTR</th><th>Chuyển đổi</th><th>Thao tác</th></tr></thead><tbody>`;
      for (const campaign of data.campaigns) {
        html+=`<tr><td><b>${escHtml(campaign.name)}</b><br><small>${escHtml(campaign.id)}</small></td><td>${escHtml(campaign.status)}</td><td>${fmt(campaign.spend)} ${escHtml(cur)}</td><td>${campaign.ctr_percent===null?'—':fmt(campaign.ctr_percent)+'%'}</td><td>${fmt(campaign.conversions)}</td><td>${(campaign.status==='ENABLED'||campaign.status==='ACTIVE')?`<button class="small-btn" data-opt-request="${escHtml(campaign.id)}">Đề nghị tạm dừng</button>`:'—'}</td></tr>`;
      }
      html+='</tbody></table></div>';
      if(data.recommendations.length){html+='<h4>Điểm cần kiểm tra</h4><ul>'+data.recommendations.map(r=>`<li><b>${escHtml(r.campaign_id)}</b>: ${escHtml(r.message)}</li>`).join('')+'</ul>';}
      else html+='<p class="muted">Chưa có cảnh báo từ quy tắc cơ bản; không đồng nghĩa chiến dịch đã tối ưu.</p>';
      output.innerHTML=html;
      show('Đã đọc '+data.campaigns.length+' chiến dịch; không có lệnh ghi Ads được gửi.');
    } catch(e) {output.textContent='';show(e.message||String(e),true)}
  }
  async function populate() {
    if(!el('opt-account')) return;
    try {
      const accounts=await api('/api/accounts');
      const previous=el('opt-account').value;
      el('opt-account').innerHTML=accounts.filter(a=>['meta','google'].includes(a.platform)&&a.connected)
        .map(a=>`<option value="${a.id}">${escHtml(a.platform.toUpperCase())}: ${escHtml(a.label)}</option>`).join('');
      if(previous && [...el('opt-account').options].some(o=>o.value===previous))el('opt-account').value=previous;
    } catch(e) {show(e.message||String(e),true)}
  }
  document.addEventListener('DOMContentLoaded',()=>{
    const view=el('page-approvals'); if(!view)return;
    const article=document.createElement('article');article.className='panel';
    article.innerHTML='<h3>Trung tâm phân tích chiến dịch</h3><p class="muted tiny">Đọc hiệu suất Google/Meta 7 ngày, tìm điểm cần xem xét. Khuyến nghị không tự chỉnh quảng cáo hoặc ngân sách. Tạm dừng chỉ được thực hiện khi admin duyệt riêng.</p><div class="inline-actions"><select id="opt-account" aria-label="Tài khoản cần phân tích"></select><button id="opt-inspect" class="btn primary" type="button">Phân tích chiến dịch</button></div><p id="optimization-message" role="status" class="muted tiny"></p><div id="optimization-result" class="table-wrap"></div>';
    view.append(article);
    el('opt-inspect').addEventListener('click',inspect);
    el('optimization-result').addEventListener('click',async e=>{
      const b=e.target.closest('[data-opt-request]');if(!b)return;
      const campaignId=b.dataset.optRequest;
      const accountId=Number(el('opt-account').value);
      if(!confirm('Tạo yêu cầu TẠM DỪNG chiến dịch '+campaignId+'? Quản trị viên vẫn phải duyệt trước khi gửi đến API.'))return;
      try{await api('/api/actions',{method:'POST',body:JSON.stringify({account_id:accountId,campaign_id:campaignId})});show('Đã tạo yêu cầu chờ duyệt, không thay đổi quảng cáo.');if(typeof loadActions==='function')await loadActions();}
      catch(err){show(err.message||String(err),true)}
    });
    const link=document.querySelector('[data-page="approvals"]');if(link)link.addEventListener('click',()=>setTimeout(populate,100));
  });
})();
