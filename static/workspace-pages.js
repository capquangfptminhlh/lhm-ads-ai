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
      if((r.source==='demo')!==(summary.totals?.data_mode==='demo'))continue;
      for(const d of r.daily){
        if(!/^\d{4}-\d{2}-\d{2}$/.test(String(d.date||'')))continue;
        buckets.set(d.date,(buckets.get(d.date)||0)+Number(d.spend||0));
      }
    }
    return [...buckets.entries()].filter(([,v])=>Number.isFinite(v)).sort((a,b)=>a[0].localeCompare(b[0]));
  };
  const onReports=()=>$('page-reports')&&!$('page-reports').classList.contains('hidden')&&$('shell')&&!$('shell').classList.contains('hidden');
  let busy=false;
  let activeReport=null;
  function drawReportChart(result){
    const currencies=Object.keys(result.totals.by_currency||{}).sort();
    const selector=$('ws-report-currency-choice');
    const previous=selector.value;
    selector.replaceChildren(...currencies.map(c=>{const opt=document.createElement('option');opt.value=c;opt.textContent=c;return opt}));
    selector.value=currencies.includes(previous)?previous:(result.totals.currency||currencies[0]||'');
    $('ws-report-currency-wrap').classList.toggle('hidden',currencies.length<2);
    const days=selector.value?chartData(result,selector.value):[];
    $('ws-report-chart').innerHTML=days.length&&window.LHMFinpointChart?
      window.LHMFinpointChart(days,selector.value):'<p class="muted">Chưa có dữ liệu cùng tiền tệ để vẽ biểu đồ.</p>';
  }
  async function load(){
    if(!onReports()||busy)return;
    busy=true;activeReport=null;const box=$('ws-report-notice');box.textContent='Đang đọc báo cáo qua API nội bộ…';
    for(const id of ['ws-report-spend','ws-report-clicks','ws-report-impressions','ws-report-ctr'])$(id).textContent='—';
    $('ws-report-chart').replaceChildren();$('ws-report-table').replaceChildren();
    $('ws-report-currency-wrap').classList.add('hidden');
    try{
      const q=window.LHMReportDates?.ensureReady('ws-report-period');
      if(!q){box.textContent='Hãy chọn khoảng ngày và bấm Áp dụng.';return;}
      const result=await api('/api/summary?'+q);
      const t=result.totals;
      $('ws-report-spend').textContent=t.spend===null?(Object.keys(t.by_currency||{}).length>1?'Đa tiền tệ':'—'):fmt(t.spend)+(t.currency?' '+t.currency:'');
      $('ws-report-currency').textContent=t.currency?'Đơn vị '+t.currency:
        Object.entries(t.by_currency||{}).map(([c,v])=>fmt(v.spend)+' '+c).join(' · ')||'Chưa có dữ liệu thật';
      $('ws-report-clicks').textContent=t.included_accounts?fmt(t.clicks):'—';
      $('ws-report-impressions').textContent=t.included_accounts?fmt(t.impressions):'—';
      $('ws-report-ctr').textContent=t.included_accounts?fmt(t.ctr)+'%':'—';
      activeReport=result;
      drawReportChart(result);
      const rows=(result.accounts||[]).map(a=>{
        const r=a.result;
        return '<tr><td><strong>'+esc(a.label)+'</strong></td><td>'+esc(a.platform)+'</td><td>'+
          (r?esc(fmt(r.spend)+' '+r.currency):'—')+'</td><td>'+(r?fmt(r.clicks):'—')+'</td><td>'+
          (r?fmt(r.ctr)+'%':'—')+'</td><td>'+esc(r?(r.source==='demo'?'DEMO':'API'):('Lỗi: '+String(a.error||'Không khả dụng').slice(0,90)))+'</td></tr>';
      });
      $('ws-report-table').innerHTML='<table><thead><tr><th>Tài khoản</th><th>Nền tảng</th><th>Chi tiêu</th><th>Clicks</th><th>CTR</th><th>Nguồn</th></tr></thead><tbody>'+ (rows.join('')||'<tr><td colspan="6">Chưa có tài khoản được kết nối</td></tr>') +'</tbody></table>';
      const failures=(result.accounts||[]).filter(x=>x.error).length;
      box.textContent=[t.contains_demo?'BẢN DEMO: không phải số liệu thật.':
        t.has_demo_accounts?'Đã loại tài khoản Demo khỏi số tổng thực.':'',
        failures?failures+' tài khoản chưa lấy được báo cáo.':'',
        'Không suy đoán CPA/ROAS khi không có dữ liệu chuyển đổi.'].filter(Boolean).join(' ');
    }catch(e){box.textContent='Không tải được báo cáo: '+String(e.message||e);$('ws-report-chart').replaceChildren();$('ws-report-table').replaceChildren();}
    finally{busy=false}
  }
  document.addEventListener('DOMContentLoaded',()=>{
    const page=$('page-reports');if(!page)return;
    $('ws-report-period').addEventListener('change',load);
    document.addEventListener('lhm:report-dates-applied',load);
    $('ws-report-currency-choice').addEventListener('change',()=>{if(activeReport)drawReportChart(activeReport)});
    $('ws-report-refresh').addEventListener('click',load);
    $('ws-report-export').addEventListener('click',()=>{
      const q=window.LHMReportDates?.ensureReady('ws-report-period');if(!q)return;
      const period=$('ws-report-period').value;
      const link=document.createElement('a');
      link.href='/api/export/reports?'+q;
      link.download='lhm-ads-'+period+'.csv';link.rel='noopener';link.click();
    });
    document.querySelectorAll('.nav-link[data-page="reports"]').forEach(x=>x.addEventListener('click',()=>setTimeout(load,0)));
  });
})();
