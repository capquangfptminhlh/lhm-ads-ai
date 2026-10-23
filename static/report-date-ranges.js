/* Shared report period picker: explicit date parameters across UI/API/CSV.
 * Only the user's deliberate Apply submits custom dates.
 */
'use strict';
window.LHMReportDates=(()=>{
  const config={
    period:{form:'dashboard-custom-dates',from:'dashboard-date-from',to:'dashboard-date-to',status:'dashboard-date-status'},
    'ws-report-period':{form:'report-custom-dates',from:'report-date-from',to:'report-date-to',status:'report-date-status'}
  };
  const byId=id=>document.getElementById(id);
  const pad=n=>String(n).padStart(2,'0');
  const localToday=()=>{
    const d=new Date();return d.getFullYear()+'-'+pad(d.getMonth()+1)+'-'+pad(d.getDate());
  };
  const toDay=value=>{
    if(!/^\d{4}-\d{2}-\d{2}$/.test(value||''))return NaN;
    const [y,m,d]=value.split('-').map(Number);
    const n=Date.UTC(y,m-1,d),actual=new Date(n);
    return actual.getUTCFullYear()===y&&actual.getUTCMonth()===m-1&&actual.getUTCDate()===d?n:NaN;
  };
  const today=localToday();
  const applied={};
  const message=(id,value)=>{
    const n=byId(config[id].status);
    if(n)n.textContent=value;
  };
  function validate(id){
    const c=config[id];if(!c)return null;
    const from=byId(c.from)?.value||'',to=byId(c.to)?.value||'';
    const start=toDay(from),end=toDay(to),max=toDay(localToday());
    if(!Number.isFinite(start)||!Number.isFinite(end)){
      message(id,'Hãy nhập đủ ngày bắt đầu và kết thúc.');return null;
    }
    if(start>end||end>max||(end-start)/86400000>365){
      message(id,'Ngày không hợp lệ, ở tương lai hoặc khoảng dài quá 366 ngày.');return null;
    }
    message(id,'Đã chọn '+from+' đến '+to+'.');
    return {from,to};
  }
  function query(id){
    const select=byId(id);if(!select)return null;
    const period=select.value;
    const q=new URLSearchParams({period});
    if(period==='custom'){
      const range=applied[id];
      if(!range)return null;
      if(range.from!==byId(config[id].from).value||range.to!==byId(config[id].to).value)return null;
      q.set('date_from',range.from);q.set('date_to',range.to);
    }
    return q.toString();
  }
  function ensureReady(id){
    const q=query(id);
    if(!q){
      message(id,'Chọn ngày bắt đầu và kết thúc, rồi bấm Áp dụng.');
      return null;
    }
    return q;
  }
  function initialize(id){
    const c=config[id],select=byId(id),panel=byId(c.form);
    if(!select||!panel)return;
    for(const field of [c.from,c.to]){
      const input=byId(field);input.max=localToday();
      input.value=localToday();
      input.addEventListener('input',()=>{delete applied[id];message(id,'Bấm Áp dụng để tải đúng khoảng ngày.')});
    }
    function updateVisibility(){
      panel.classList.toggle('hidden',select.value!=='custom');
      if(select.value==='custom')message(id,'Chọn khoảng ngày và bấm Áp dụng.');
    }
    select.addEventListener('change',updateVisibility);
    panel.addEventListener('submit',event=>{
      event.preventDefault();
      const dates=validate(id);if(!dates)return;
      applied[id]=dates;
      if(id==='period'&&typeof window.loadDashboard==='function')window.loadDashboard();
      else if(id==='ws-report-period')
        document.dispatchEvent(new CustomEvent('lhm:report-dates-applied'));
    });
    updateVisibility();
  }
  document.addEventListener('DOMContentLoaded',()=>Object.keys(config).forEach(initialize));
  return {query,ensureReady,validate,localToday};
})();
