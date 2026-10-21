/* Native SVG visualization for actual, same-currency daily Ads reports only.
   No placeholder metrics, calls, remote assets, persistence or control APIs. */
'use strict';
(function(){
  const safe=(x)=>String(x??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const money=(v,c)=>Number(v).toLocaleString('vi-VN',{maximumFractionDigits:2})+' '+String(c||'');
  function smooth(points){
    if(points.length===1) return `M ${points[0][0]} ${points[0][1]}`;
    let s=`M ${points[0][0]} ${points[0][1]}`;
    for(let i=0;i<points.length-1;i++){
      const p=points[i],n=points[i+1],mx=(p[0]+n[0])/2;
      s+=` C ${mx} ${p[1]}, ${mx} ${n[1]}, ${n[0]} ${n[1]}`;
    }
    return s;
  }
  window.LHMFinpointChart=function(entries,currency){
    if(!Array.isArray(entries)||!entries.length)return '<div class="empty">Chưa có dữ liệu chi tiêu theo ngày để vẽ biểu đồ.</div>';
    const values=entries.map(e=>Number(e[1])).filter(Number.isFinite);
    if(values.length!==entries.length)return '<div class="empty">Dữ liệu không đủ điều kiện để vẽ biểu đồ.</div>';
    const max=Math.max(1,...values), width=960, top=24, bottom=217, left=24, right=930;
    const pt=entries.map(([day,value],i)=>[
      Math.round(left+(right-left)*(entries.length===1?.5:i/(entries.length-1))),
      Math.round(bottom-(Number(value)/max)*(bottom-top))
    ]);
    const line=smooth(pt);
    const first=pt[0],last=pt[pt.length-1];
    const area=`${line} L ${last[0]} ${bottom} L ${first[0]} ${bottom} Z`;
    const guides=[.25,.5,.75,1].map(f=>`<line class="gridline" x1="${left}" y1="${Math.round(bottom-(bottom-top)*f)}" x2="${right}" y2="${Math.round(bottom-(bottom-top)*f)}"/>`).join('');
    const labels=entries.map(([day],i)=>`<text x="${pt[i][0]}" y="250" text-anchor="middle">${safe(String(day).slice(5))}</text>`).join('');
    const circles=entries.map(([day,value],i)=>`<circle class="dot" cx="${pt[i][0]}" cy="${pt[i][1]}" style="--fp-point:${i}" r="4.5"><title>${safe(day)}: ${safe(money(value,currency))}</title></circle>`).join('');
    return `<svg class="fp-chart" viewBox="0 0 ${width} 268" role="img" aria-label="Biểu đồ chi tiêu ${safe(String(currency))} theo ngày, sử dụng báo cáo thực hoặc dữ liệu demo được đánh dấu riêng" preserveAspectRatio="none">
      <defs><linearGradient id="fpArea" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stop-color="#ff5b35" stop-opacity=".35"/><stop offset="100%" stop-color="#ff5b35" stop-opacity="0"/></linearGradient></defs>
      ${guides}<path class="area" d="${area}"/><path class="trendline" d="${line}"/>${circles}${labels}
    </svg>`;
  };
  window.LHMFinpointSummary=function(total,accounts,summary){
    const id=(x)=>document.getElementById(x);
    const connected=Array.isArray(accounts)?accounts.filter(a=>a.connected&&!String(a.label||'').startsWith('[REVOKED]')).length:0;
    const issues=Array.isArray(summary?.accounts)?summary.accounts.filter(a=>a.error).length:0;
    if(id('fp-ops-connected'))id('fp-ops-connected').textContent=String(connected)+' tài khoản';
    if(id('fp-ops-failed'))id('fp-ops-failed').textContent=issues?String(issues)+' nguồn cần kiểm tra':'Không có lỗi báo cáo';
    if(id('fp-data-source'))id('fp-data-source').textContent=total?.data_mode==='demo'?'DỮ LIỆU DEMO':
      total?.included_accounts?'Dữ liệu quảng cáo thật':'Chưa có dữ liệu thực';
  };
})();
