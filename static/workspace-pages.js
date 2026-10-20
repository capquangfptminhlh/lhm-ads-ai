/* FinPoint workspace: report page only. All data from local authenticated API. */
'use strict';
(()=>{
  const $=id=>document.getElementById(id);
  const esc=x=>String(x??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const fmt=x=>Number(x||0).toLocaleString('vi-VN',{maximumFractionDigits:2});
  const chartData=(summary,currency)=>{
    const buckets=new Map();
    for(const a of summary.accounts||[]){
      const r=a.result;
      if(!r||r.currency!==currency||!Array.isArray(r.daily))continue;
      for(const d of r.daily){
        if(!/^\d{4}-\d{2}-\d{2}$/.test(String(d.date||'')))continue;
        buckets.set(d.date,(buckets.get(d.date)||0)+Number(d.spend||0));
      }
    }
    return [...buckets.entries()].filter(([,v])=>Number.isFinite(v)).sort((a,b)=>a[0].localeCompare(b[0]));
  };
  const onReports=()=>$('page-reports')&&!$('page-reports').classList.contains('hidden')&&$('shell')&&!$('shell').classList.contains('hidden');
  let busy=false;
  async function load(){
    if(!onReports()||busy)return;
    busy=true;const box=$('ws-report-notice');box.textContent='Đang đọc báo cáo qua API nội bộ…';
    try{
      const period=$('ws-report-period').value;
      const result=await api('/api/summary?period='+encodeURIComponent(period));
      const t=result.totals;
      $('ws-report-spend').textContent=t.spend===null?'Đa tiền tệ':fmt(t.spend)+(t.currency?' '+t.currency:'');
      $('ws-report-currency').textContent=t.currency?'Đơn vị '+t.currency:'Không cộng tiền tệ khác nhau';
      $('ws-report-clicks').textContent=fmt(t.clicks);
      $('ws-report-impressions').textContent=fmt(t.impressions);
      $('ws-report-ctr').textContent=fmt(t.ctr)+'%';
      const days=t.currency?chartData(result,t.currency):[];
      const graph=$('ws-report-chart');
      graph.innerHTML=days.length&&window.LHMFinpointChart?
        window.LHMFinpointChart(days,t.currency):'<p class="muted">Chưa có dữ liệu cùng tiền tệ để vẽ biểu đồ.</p>';
      const rows=(result.accounts||[]).map(a=>{
        const r=a.result;
        return '<tr><td><strong>'+esc(a.label)+'</strong></td><td>'+esc(a.platform)+'</td><td>'+
          (r?esc(fmt(r.spend)+' '+r.currency):'—')+'</td><td>'+(r?fmt(r.clicks):'—')+'</td><td>'+
          (r?fmt(r.ctr)+'%':'—')+'</td><td>'+esc(r?(r.source==='demo'?'DEMO':'API'):('Lỗi: '+String(a.error||'Không khả dụng').slice(0,90)))+'</td></tr>';
      });
      $('ws-report-table').innerHTML='<table><thead><tr><th>Tài khoản</th><th>Nền tảng</th><th>Chi tiêu</th><th>Clicks</th><th>CTR</th><th>Nguồn</th></tr></thead><tbody>'+ (rows.join('')||'<tr><td colspan="6">Chưa có tài khoản được kết nối</td></tr>') +'</tbody></table>';
      const failures=(result.accounts||[]).filter(x=>x.error).length;
      box.textContent=[t.contains_demo?'Có dữ liệu DEMO minh họa.':'',failures?failures+' tài khoản chưa lấy được báo cáo.':'','Chỉ hiển thị chỉ số đang hỗ trợ; không suy đoán CPA/ROAS.'].filter(Boolean).join(' ');
    }catch(e){box.textContent='Không tải được báo cáo: '+String(e.message||e);$('ws-report-chart').replaceChildren();$('ws-report-table').replaceChildren();}
    finally{busy=false}
  }
  document.addEventListener('DOMContentLoaded',()=>{
    const page=$('page-reports');if(!page)return;
    $('ws-report-period').addEventListener('change',load);
    $('ws-report-refresh').addEventListener('click',load);
    $('ws-report-export').addEventListener('click',()=>{
      const period=$('ws-report-period').value;
      if(!['last_7d','yesterday'].includes(period))return;
      const link=document.createElement('a');
      link.href='/api/export/reports?period='+encodeURIComponent(period);
      link.download='lhm-ads-'+period+'.csv';link.rel='noopener';link.click();
    });
    document.querySelectorAll('.nav-link[data-page="reports"]').forEach(x=>x.addEventListener('click',()=>setTimeout(load,0)));
  });
})();
