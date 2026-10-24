/* Independent PWA command center. Reuses device vault data only.
   No Ads tokens, API fetch, desktop process or server session involved. */
'use strict';
(() => {
  const vault=window.LHMDeviceVault;
  const root=document.getElementById('lhm-local-workspace');
  if(!root||!vault)return;
  const $=id=>document.getElementById(id);
  const pages=[...document.querySelectorAll('.pwa-page[data-view]')];
  const navs=[...document.querySelectorAll('[data-go]')];
  const names={dashboard:'Tổng quan',accounts:'Tài khoản Ads',reports:'Báo cáo',alerts:'Cảnh báo',assistant:'AI Center',settings:'Cài đặt'};
  let selectedAccount='',page='dashboard',previousUnlocked=false;
  const login=document.getElementById('login');
  const loginPortal=document.getElementById('pwa-login-portal');
  const accountPage=document.querySelector('.pwa-page[data-view="accounts"]');
  const gate=document.getElementById('pwa-access-gate');
  // Moving the SAME vault form preserves all registered event handlers and cryptographic state.
  // No authentication token/session is stored in Cloudflare or browser localStorage.
  function syncAccessGate(){
    const unlocked=isOpen();
    root.classList.toggle('pwa-gated',!unlocked);
    gate.hidden=unlocked;
    if(unlocked){
      if(login.parentElement!==accountPage)accountPage.append(login);
      if(!previousUnlocked){previousUnlocked=true;go('dashboard',false);}
    }else{
      previousUnlocked=false;
      if(login.parentElement!==loginPortal)loginPortal.append(login);
      if(page!=='dashboard')go('dashboard',false);
    }
  }
  const dateLabel=x=>String(x||'').slice(5);
  const fmt=(n,opt={})=>new Intl.NumberFormat('vi-VN',{maximumFractionDigits:2,...opt}).format(n);
  const text=(id,value)=>{const n=$(id);if(n)n.textContent=String(value);};
  const element=(tag,cls,value)=>{const n=document.createElement(tag);if(cls)n.className=cls;if(value!==undefined)n.textContent=String(value);return n;};
  const empty=(parent,message)=>{parent.replaceChildren(element('div','pwa-empty',message));};
  const isOpen=()=>vault.isUnlocked();
  function closeMenu(){
    $('pwa-sidebar').classList.remove('open');
    $('pwa-overlay').classList.remove('active');
    $('pwa-menu-toggle').setAttribute('aria-expanded','false');
  }
  function go(to,focus=true){
    if(!names[to])return;
    page=to;
    for(const section of pages){
      const active=section.dataset.view===to;
      section.classList.toggle('active',active);
      section.hidden=!active;
    }
    for(const button of navs){
      const active=button.dataset.go===to;
      button.classList.toggle('active',active);
      if(active)button.setAttribute('aria-current','page');
      else button.removeAttribute('aria-current');
    }
    text('pwa-page-title',names[to]);
    closeMenu();
    if(to==='accounts'||to==='reports'||to==='alerts'||to==='dashboard')refresh();
    if(focus){
      window.scrollTo({top:0,behavior:matchMedia('(prefers-reduced-motion: reduce)').matches?'instant':'smooth'});
      const heading=document.querySelector('.pwa-page.active h1');
      if(heading){heading.setAttribute('tabindex','-1');heading.focus({preventScroll:true});}
    }
  }
  for(const n of navs)n.addEventListener('click',()=>go(n.dataset.go));
  $('pwa-menu-toggle').addEventListener('click',()=>{
    const open=$('pwa-sidebar').classList.toggle('open');
    $('pwa-overlay').classList.toggle('active',open);
    $('pwa-menu-toggle').setAttribute('aria-expanded',String(open));
  });
  $('pwa-overlay').addEventListener('click',closeMenu);
  document.addEventListener('keydown',e=>{if(e.key==='Escape')closeMenu();});
  function allData(){
    if(!isOpen())return {accounts:[],days:0,alerts:[],recent:[]};
    const accounts=vault.listAccounts();
    let days=0;
    const recent=[];
    for(const account of accounts){
      const rows=vault.listDailyReports(account.localId);
      days+=rows.length;
      for(const row of rows)recent.push({...row,accountLabel:account.label,localId:account.localId});
    }
    recent.sort((a,b)=>b.date.localeCompare(a.date));
    return {accounts,days,alerts:vault.listLocalAlerts(),recent};
  }
  function accountOption(selected){
    const select=$('pwa-report-selector');
    const accounts=isOpen()?vault.listAccounts():[];
    const prev=selected||selectedAccount||select.value;
    select.replaceChildren();
    for(const a of accounts){
      const opt=document.createElement('option');
      opt.value=a.localId;
      opt.textContent=a.label+' · '+a.currency;
      select.append(opt);
    }
    selectedAccount=accounts.some(a=>a.localId===prev)?prev:(accounts[0]?.localId||'');
    select.value=selectedAccount;
    select.disabled=!accounts.length;
    return accounts.find(a=>a.localId===selectedAccount);
  }
  function drawChart(rows,currency){
    const chart=$('pwa-spend-chart');chart.replaceChildren();
    if(!rows.length){empty(chart,'Chưa có dữ liệu chi tiêu. Mở Tài khoản Ads để nhập CSV.');return;}
    const seven=rows.slice(0,7).reverse();
    const max=Math.max(...seven.map(x=>x.spend),1);
    for(const data of seven){
      const column=element('div','pwa-chart-col');
      const bar=element('div','pwa-chart-bar');
      bar.style.height=Math.max(4,data.spend/max*172)+'px';
      bar.title=data.date+' · '+fmt(data.spend)+' '+currency;
      bar.setAttribute('aria-label',bar.title);
      const day=element('small','',dateLabel(data.date));
      column.append(bar,day);chart.append(column);
    }
  }
  function drawAccounts(accounts){
    const mount=$('pwa-account-preview');mount.replaceChildren();
    if(!accounts.length){empty(mount,'Chưa có tài khoản nào được lưu trong kho mã hóa.');return;}
    for(const a of accounts.slice(0,5)){
      const item=element('div','pwa-account-item');
      const left=element('div','');
      const name=element('div','pwa-account-title',a.label);
      const sub=element('div','pwa-account-sub',a.accountId+' · '+a.currency);
      left.append(name,sub);
      const badge=element('span','pwa-platform',a.platform.toUpperCase());
      item.append(left,badge);mount.append(item);
    }
  }
  function drawReports(account){
    const mount=$('pwa-report-rows');mount.replaceChildren();
    if(!account){
      text('pwa-report-summary','Kho đang khóa hoặc chưa có tài khoản để hiển thị báo cáo.');
      empty(mount,'Mở kho rồi thêm tài khoản để xem báo cáo.');return;
    }
    const rows=vault.listDailyReports(account.localId);
    const total=rows.reduce((s,r)=>({spend:s.spend+r.spend,clicks:s.clicks+r.clicks,impressions:s.impressions+r.impressions}),
      {spend:0,clicks:0,impressions:0});
    text('pwa-report-summary',rows.length
      ?'Đã nhập '+rows.length+' ngày · Tổng chi '+fmt(total.spend)+' '+account.currency+
       ' · '+fmt(total.clicks)+' lượt nhấp · CTR '+
       (total.impressions?(total.clicks/total.impressions*100).toFixed(2)+'%':'—')
      :'Chưa nhập dữ liệu CSV cho tài khoản này.');
    drawChart(rows,account.currency);
    if(!rows.length){empty(mount,'Chưa có báo cáo CSV. Dữ liệu không tự đồng bộ từ Google/Meta/TikTok.');return;}
    for(const row of rows.slice(0,14)){
      const container=element('div','pwa-event');
      const date=element('span','',row.date);
      const stat=element('strong','',fmt(row.spend)+' '+row.currency+' · '+fmt(row.clicks)+' click');
      container.append(date,stat);mount.append(container);
    }
  }
  function drawAlerts(alerts,accounts){
    const mount=$('pwa-alert-items');mount.replaceChildren();
    if(!alerts.length){empty(mount,'Chưa ghi nhận ngày vượt ngưỡng từ CSV thủ công.');return;}
    const labels=new Map(accounts.map(x=>[x.localId,x.label]));
    for(const a of alerts.slice(0,35)){
      const item=element('div','pwa-alert');
      item.append(element('strong','',labels.get(a.localId)||'Tài khoản đã xóa'),
        element('div','',a.date+' · Chi '+fmt(a.spend)+' '+a.currency+
          ' / Ngưỡng '+fmt(a.threshold)+' '+a.currency));
      mount.append(item);
    }
  }
  function refresh(){
    const active=isOpen(),data=allData();
    if(!active)selectedAccount='';
    syncAccessGate();
    text('pwa-session-label',active?'KHO ĐÃ MỞ KHÓA':'KHO ĐANG KHÓA');
    text('pwa-overview-accounts',data.accounts.length);
    text('pwa-overview-days',data.days);
    text('pwa-overview-alerts',data.alerts.length);
    text('pwa-overview-security',active?'Đã mở':'Đã khóa');
    text('pwa-account-caption',active
      ?'Thông tin đã mã hóa; chưa đồng nghĩa tài khoản đã kết nối API.'
      :'Mở khóa kho bên dưới để quản lý tài khoản đã lưu trên thiết bị.');
    text('pwa-summary-status',active
      ?'Dữ liệu chỉ trên thiết bị này. Báo cáo nhập từ CSV thủ công.'
      :'Dữ liệu được mã hóa. Mở kho trong mục Tài khoản Ads để xem.');
    $('pwa-alert-locked').hidden=active;
    $('pwa-report-locked').hidden=active;
    drawAccounts(data.accounts);
    const account=accountOption();
    drawReports(account);
    drawAlerts(data.alerts,data.accounts);
    text('pwa-offline-total',data.accounts.length+' tài khoản · '+data.days+' ngày CSV');
    text('pwa-alert-count',String(data.alerts.length));
  }
  $('pwa-signout').addEventListener('click',()=>{
    vault.lock();
    window.dispatchEvent(new Event('lhm:vault-locked'));
    refresh();
    window.scrollTo(0,0);
  });
  $('pwa-report-selector').addEventListener('change',e=>{selectedAccount=e.target.value;refresh();});
  window.addEventListener('lhm:vault-change',refresh);
  window.addEventListener('lhm:vault-locked',refresh);
  window.addEventListener('pageshow',refresh);
  go('dashboard',false);
  refresh();
})();
