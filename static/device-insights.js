/* Device-only analytics importer. No network requests, no Ads API shortcuts. */
'use strict';
(() => {
  function parseCSV(input){
    if(typeof input!=='string'||input.length>1_000_000)throw Error('CSV quá lớn (tối đa 1 MB).');
    const src=input.charCodeAt(0)===0xFEFF?input.slice(1):input;
    let rows=[],row=[],value='',quoted=false;
    for(let i=0;i<src.length;i++){
      const ch=src[i];
      if(quoted){
        if(ch==='"'&&src[i+1]==='"'){value+='"';i++;}
        else if(ch==='"')quoted=false;
        else value+=ch;
      }else if(ch==='"'){
        if(value!=='')throw Error('CSV có dấu ngoặc kép không hợp lệ.');
        quoted=true;
      }else if(ch===','){row.push(value);value='';}
      else if(ch==='\n'||ch==='\r'){
        if(ch==='\r'&&src[i+1]==='\n')i++;
        row.push(value);value='';
        if(row.some(col=>col.trim()!==''))rows.push(row);
        row=[];
      }else value+=ch;
    }
    if(quoted)throw Error('CSV có ô trích dẫn chưa đóng.');
    row.push(value);
    if(row.some(col=>col.trim()!==''))rows.push(row);
    if(rows.length<2||rows.length>367)throw Error('CSV cần tiêu đề và 1–366 dòng dữ liệu.');
    const headers=rows[0].map(s=>s.trim().toLowerCase());
    const required=['date','spend','clicks','impressions','currency'];
    if(headers.length!==5||required.some((k,i)=>headers[i]!==k))
      throw Error('Tiêu đề CSV phải là: date,spend,clicks,impressions,currency');
    const known=new Set();
    return rows.slice(1).map((cols,index)=>{
      if(cols.length!==5)throw Error('CSV sai số cột ở dòng '+(index+2));
      const [date,spend,clicks,impressions,currency]=cols.map(s=>s.trim());
      if(!/^\d{4}-\d{2}-\d{2}$/.test(date))throw Error('Ngày phải YYYY-MM-DD, dòng '+(index+2));
      const day=new Date(date+'T00:00:00Z');
      if(!Number.isFinite(day.getTime())||day.toISOString().slice(0,10)!==date||known.has(date))
        throw Error('Ngày sai hoặc trùng tại dòng '+(index+2));
      known.add(date);
      const num=x=>{
        if(!/^(?:0|[1-9]\d*)(?:\.\d{1,4})?$/.test(x))throw Error('Số không hợp lệ, dòng '+(index+2));
        return Number(x);
      };
      const s=num(spend),c=num(clicks),im=num(impressions);
      if([s,c,im].some(x=>!Number.isFinite(x)||x>1e12)||!Number.isInteger(c)||!Number.isInteger(im))
        throw Error('Chỉ số quá lớn hoặc click/impressions không nguyên.');
      if(!/^[A-Za-z]{3}$/.test(currency))throw Error('Đơn vị tiền tệ sai ở dòng '+(index+2));
      return {date,spend:s,clicks:c,impressions:im,currency:currency.toUpperCase()};
    });
  }
  const safeError=e=>e instanceof Error?e.message:'Không đọc được CSV.';
  const root=document.getElementById('lhm-vault-unlocked');
  if(!root||!window.LHMDeviceVault)return;
  const api=window.LHMDeviceVault;
  const section=document.createElement('section');
  section.className='lhm-local-insights';
  section.innerHTML=`<h4>📊 Báo cáo cục bộ & cảnh báo ngân sách</h4>
    <p>Chỉ phân tích dữ liệu CSV anh/chị tự nhập trên điện thoại này. <strong>Không phải dữ liệu Ads realtime.</strong></p>
    <form id="lhm-local-import">
      <label>Tài khoản<select id="lhm-local-account" required></select></label>
      <label>CSV báo cáo ngày (tối đa 366 ngày)
        <input id="lhm-local-csv" type="file" accept=".csv,text/csv" required></label>
      <button type="submit" class="btn primary">Nhập & mã hóa báo cáo</button>
    </form>
    <p class="lhm-local-example">Định dạng CSV: <code>date,spend,clicks,impressions,currency</code>
      Ví dụ: <code>2026-10-24,210000,25,1000,VND</code>. Dùng dấu chấm cho số thập phân, không dùng dấu phân cách hàng nghìn.</p>
    <form id="lhm-local-budget">
      <label>Ngưỡng chi tiêu mỗi ngày (theo tiền tệ tài khoản)
        <input id="lhm-local-threshold" type="number" min="1" max="1000000000000" step="0.01" required placeholder="200000"></label>
      <label class="lhm-local-check"><input id="lhm-local-rule-enabled" type="checkbox" checked> Bật cảnh báo trong PWA</label>
      <button class="btn secondary" type="submit">Lưu ngưỡng</button>
    </form>
    <div id="lhm-local-status" role="status" aria-live="polite"></div>
    <div class="lhm-local-metrics" id="lhm-local-metrics"></div>
    <div class="lhm-local-alerts"><h4>Cảnh báo phát hiện từ CSV</h4>
      <div id="lhm-local-alert-list"></div></div>
    <div class="lhm-local-report"><h4>7 ngày báo cáo gần nhất đã nhập</h4>
      <div id="lhm-local-rows"></div></div>
    <p class="lhm-vault-footer">Cảnh báo chỉ hiện khi mở kho PWA; dữ liệu không được gửi lên Cloudflare hoặc nhận bằng thông báo đẩy khi PWA bị đóng.</p>`;
  root.insertBefore(section,document.getElementById('lhm-vault-destroy'));
  const el=id=>document.getElementById(id);
  let chosenId='';
  function setText(parent,tag,content){
    const child=document.createElement(tag);
    child.textContent=content;parent.append(child);return child;
  }
  function format(n){
    return new Intl.NumberFormat('vi-VN',{maximumFractionDigits:2}).format(n);
  }
  function refresh(){
    if(!api.isUnlocked())return;
    const accounts=api.listAccounts(),selector=el('lhm-local-account');
    const old=chosenId||selector.value;
    selector.replaceChildren();
    for(const a of accounts){
      const opt=document.createElement('option');opt.value=a.localId;
      opt.textContent=a.label+' ('+a.platform+', '+a.currency+')';
      selector.append(opt);
    }
    chosenId=accounts.some(a=>a.localId===old)?old:(accounts[0]?.localId||'');
    selector.value=chosenId;
    for(const control of section.querySelectorAll('button'))control.disabled=!chosenId;
    const rules=api.listDailyBudgets(),r=rules.find(x=>x.localId===chosenId);
    el('lhm-local-threshold').value=r?.threshold||'';
    el('lhm-local-rule-enabled').checked=r?.enabled??true;
    const metrics=el('lhm-local-metrics'),alerts=el('lhm-local-alert-list'),table=el('lhm-local-rows');
    metrics.replaceChildren();alerts.replaceChildren();table.replaceChildren();
    if(!chosenId){setText(metrics,'p','Thêm một tài khoản vào kho trước khi nhập báo cáo.');return;}
    const rows=api.listDailyReports(chosenId);
    if(rows.length){
      const total=rows.reduce((a,x)=>({spend:a.spend+x.spend,clicks:a.clicks+x.clicks,
        impressions:a.impressions+x.impressions}),{spend:0,clicks:0,impressions:0});
      const c=accounts.find(a=>a.localId===chosenId)?.currency||'VND';
      setText(metrics,'strong','Tổng '+rows.length+' ngày đã nhập: '+format(total.spend)+' '+c);
      setText(metrics,'span',format(total.clicks)+' click · '+format(total.impressions)+' hiển thị');
      setText(metrics,'small','Nguồn: CSV thủ công, không xác minh với Google/Meta/TikTok');
      for(const row of rows.slice(0,7))
        setText(table,'p',row.date+' · '+format(row.spend)+' '+row.currency+
          ' · '+format(row.clicks)+' click');
    }else setText(metrics,'p','Chưa có báo cáo CSV trên thiết bị này.');
    const found=api.listLocalAlerts().filter(x=>x.localId===chosenId);
    if(!found.length)setText(alerts,'p','Chưa có ngày nào vượt ngưỡng từ dữ liệu đã nhập.');
    for(const a of found){
      setText(alerts,'p',a.date+' — Chi '+format(a.spend)+' '+a.currency+
        ', vượt ngưỡng '+format(a.threshold)+' '+a.currency+' (CSV thủ công)');
    }
  }
  el('lhm-local-account').addEventListener('change',e=>{
    chosenId=e.target.value;refresh();
  });
  el('lhm-local-import').addEventListener('submit',async e=>{
    e.preventDefault();const file=el('lhm-local-csv').files?.[0];
    if(!file)return;
    if(file.size>1_000_000){el('lhm-local-status').textContent='CSV vượt 1 MB.';return;}
    const btn=e.currentTarget.querySelector('button[type="submit"]');btn.disabled=true;
    try{
      const rows=parseCSV(await file.text());
      const result=await api.importDailyReport(chosenId,rows);
      el('lhm-local-status').textContent='Đã mã hóa '+result.imported+' ngày báo cáo trên thiết bị.';
      el('lhm-local-csv').value='';refresh();
    }catch(err){el('lhm-local-status').textContent=safeError(err);}
    finally{btn.disabled=false;}
  });
  el('lhm-local-budget').addEventListener('submit',async e=>{
    e.preventDefault();const btn=e.currentTarget.querySelector('button[type="submit"]');
    btn.disabled=true;
    try{
      await api.setDailyBudget(chosenId,Number(el('lhm-local-threshold').value),
        el('lhm-local-rule-enabled').checked);
      el('lhm-local-status').textContent='Đã lưu ngưỡng ngân sách đã mã hóa trên thiết bị.';
      refresh();
    }catch(err){el('lhm-local-status').textContent=safeError(err);}
    finally{btn.disabled=false;}
  });
  window.addEventListener('lhm:vault-change',refresh);
  Object.defineProperty(window,'LHMOfflineCSV',{value:Object.freeze({parseCSV}),configurable:false});
  refresh();
})();
