'use strict';
const $=id=>document.getElementById(id);
const esc=x=>String(x??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const fmt=x=>Number(x||0).toLocaleString('vi-VN',{maximumFractionDigits:2});
const money=(v,c='VND')=>v==null?'—':fmt(v)+' '+esc(c||'');
const empty=(cols,msg)=>`<tr><td colspan="${cols}" class="empty">${esc(msg)}</td></tr>`;
const table=(headers,rows)=>`<table><thead><tr>${headers.map(x=>`<th>${esc(x)}</th>`).join('')}</tr></thead><tbody>${rows.length?rows.join(''):empty(headers.length,'Chưa có dữ liệu')}</tbody></table>`;
const status=(text,type='pending')=>`<span class="status ${type}">${esc(text)}</span>`;
const names={dashboard:'Tổng quan',accounts:'Tài khoản Ads',campaigns:'Chiến dịch',assistant:'AI Center',autopilot:'Autopilot',alerts:'Cảnh báo',reports:'Báo cáo',approvals:'Phê duyệt',team:'Nhân sự',audit:'Nhật ký',settings:'Cài đặt',license:'Bản quyền'};
let session=null, cache=[], current='dashboard', actions=[], toastTimeout;
function notify(msg,error=false){const el=$('toast');el.textContent=msg;el.classList.remove('hidden');el.classList.toggle('error',error);clearTimeout(toastTimeout);toastTimeout=setTimeout(()=>el.classList.add('hidden'),5500)}
async function api(url,options={}){const headers={'Accept':'application/json',...options.headers};if(options.body)headers['Content-Type']='application/json';if(session?.csrf&&options.method&&!['GET','HEAD'].includes(options.method))headers['X-CSRF-Token']=session.csrf;let r;try{r=await fetch(url,{credentials:'same-origin',...options,headers})}catch{throw Error('Không thể kết nối server')};const ct=r.headers.get('content-type')||'';const data=ct.includes('application/json')?await r.json():await r.text();if(!r.ok){if(r.status===401){session=null;showLogin()}throw Error(typeof data==='object'?(typeof data.detail==='string'?data.detail:JSON.stringify(data.detail||data)):String(data).slice(0,220))}return data}
function isAdmin(){return session?.role==='admin'}function showLogin(){stopNetworkMonitor();$('shell').classList.add('hidden');$('login').classList.remove('hidden')}
function showApp(){$('login').classList.add('hidden');$('shell').classList.remove('hidden');$('user-name').textContent=session.email;document.querySelectorAll('.admin-only').forEach(x=>x.classList.toggle('hidden',!isAdmin()));const oauth=new URLSearchParams(location.search).get('oauth');history.replaceState(null,'','/studio');go(oauth?'accounts':'dashboard');beginNetworkMonitor();if(oauth&&oauth!=='ready')notify(({cancelled:'Đã hủy đăng nhập OAuth',no_accounts:'Không tìm thấy tài khoản quảng cáo được cấp quyền',provider_error:'Không kết nối được API quảng cáo. Kiểm tra quyền OAuth và ứng dụng.'})[oauth]||'Không hoàn thành kết nối OAuth',true)}
function go(page){if(!names[page])return;if(['team','audit'].includes(page)&&!isAdmin())return;current=page;$('page-title').textContent=names[page];document.querySelectorAll('.view').forEach(el=>el.classList.toggle('hidden',el.id!=='page-'+page));document.querySelectorAll('.nav-link').forEach(el=>el.classList.toggle('active',el.dataset.page===page));$('sidebar').classList.remove('open');({dashboard:loadDashboard,accounts:loadAccounts,approvals:loadActions,team:loadTeam,audit:loadAudit,settings:()=>{loadAISettings();loadDesktopProviders()},assistant:loadAISettings})[page]?.()}
async function initialize(){try{session=await api('/api/studio/me');showApp()}catch{showLogin()}}
async function loadDashboard(){const chart=$('chart');chart.classList.add('loading');chart.textContent='Đang đọc dữ liệu...';try{const [s,accounts]=await Promise.all([api('/api/summary?period='+encodeURIComponent($('period').value)),api('/api/accounts')]);cache=accounts;const t=s.totals;$('k-spend').textContent=t.spend===null?'Đa tiền tệ':fmt(t.spend)+(t.currency?' '+t.currency:'');$('k-currency').textContent=t.currency?'Đơn vị '+t.currency:'Không cộng chi phí khác loại';$('k-impressions').textContent=fmt(t.impressions);$('k-clicks').textContent=fmt(t.clicks);$('k-ctr').textContent=fmt(t.ctr)+'%';const bad=s.accounts.filter(x=>x.error);const note=$('source-warning');note.classList.toggle('hidden',!(t.contains_demo||bad.length));note.textContent=[t.contains_demo?'DỮ LIỆU DEMO được đánh dấu riêng, không phải hiệu suất thật.':'',bad.length?`${bad.length} nguồn không lấy được dữ liệu / chưa hỗ trợ.`:''].filter(Boolean).join(' ');
const platformIcon={meta:'∞',google:'G',tiktok:'♪',openai:'✧',demo:'◈'};$('platform-stats').innerHTML=Object.keys(platformIcon).map(p=>`<div class="platform-stat"><span><i class="platform-icon ${p}">${platformIcon[p]}</i>${esc(({meta:'Meta Ads',google:'Google Ads',tiktok:'TikTok Ads',openai:'OpenAI Ads',demo:'Demo'})[p])}</span><b>${accounts.filter(a=>a.platform===p&&!a.label.startsWith('[REVOKED]')).length}</b></div>`).join('');
const dayMap={};for(const a of s.accounts){const r=a.result;if(!r||r.currency!==t.currency||!r.daily)continue;for(const d of r.daily){dayMap[d.date]=(dayMap[d.date]||0)+Number(d.spend)}}const entries=Object.entries(dayMap).sort(([a],[b])=>a.localeCompare(b));if(!entries.length){chart.innerHTML='<div class="empty">Không có dữ liệu biểu đồ đủ điều kiện cùng loại tiền tệ.</div>'}else{const max=Math.max(...entries.map(x=>x[1]),1);chart.innerHTML=window.LHMFinpointChart?window.LHMFinpointChart(entries,t.currency):entries.map(([d,v])=>`<div class="chart-col" title="${esc(d)}: ${esc(money(v,t.currency))}"><div class="chart-bar" style="height:${Math.max(3,Math.round(100*v/max))}%"></div><span class="chart-date">${esc(d.slice(5))}</span></div>`).join('')}
const rows=s.accounts.map(a=>{const r=a.result;return `<tr><td><strong>${esc(a.label)}</strong></td><td>${esc(a.platform.toUpperCase())}</td><td>${r?esc(money(r.spend,r.currency)):'—'}</td><td>${r?fmt(r.clicks):'—'}</td><td>${r?fmt(r.ctr)+'%':'—'}</td><td>${r?status(r.source==='demo'?'Demo':'API thực',r.source==='demo'?'pending':'success'):status('Không khả dụng','error')}</td><td title="${esc(a.error||'')}">${esc((a.error||'').slice(0,70))}</td></tr>`});$('overview-table').innerHTML=table(['Tài khoản','Nền tảng','Chi tiêu','Clicks','CTR','Nguồn','Ghi chú'],rows);window.LHMFinpointSummary?.(t,accounts,s)}catch(e){chart.textContent='';notify(e.message,true)}finally{chart.classList.remove('loading')}}
function applyAccountSearch(){const el=$('global-account-search');const q=(el?.value||'').trim().toLocaleLowerCase('vi');const platform=window.lhmAccountFilter||'all';document.querySelectorAll('#accounts-table tbody tr').forEach(tr=>{tr.hidden=(!!q&&!tr.textContent.toLocaleLowerCase('vi').includes(q))||(platform!=='all'&&tr.dataset.platform!==platform)})}
async function loadAccounts(){if(isAdmin())await loadOAuthStatusAndPending();try{cache=await api('/api/accounts');const rows=cache.map(a=>`<tr data-platform="${esc(a.platform)}"><td><strong>${esc(a.label)}</strong></td><td>${esc(a.platform.toUpperCase())}</td><td>${esc(a.external_id)}</td><td>${esc(a.currency)}</td><td>${status(a.platform==='demo'?'Demo':a.connected?'Đã lưu token':'Đã thu hồi',a.platform==='demo'?'pending':a.connected?'success':'error')}</td><td>${isAdmin()&&!a.label.startsWith('[REVOKED]')?`<button class="small-btn" data-revoke="${a.id}">Thu hồi</button>`:''}</td></tr>`);$('accounts-table').innerHTML=table(['Tài khoản','Nền tảng','ID','Tiền tệ','Trạng thái',''],rows);window.lhmProviderUI?.renderCounts?.(cache);applyAccountSearch();document.dispatchEvent(new CustomEvent('lhm:accounts-loaded',{detail:{accounts:cache}}))}catch(e){notify(e.message,true)}}
async function loadActions(){try{[actions,cache]=await Promise.all([api('/api/actions'),api('/api/accounts')]);const pending=actions.filter(x=>x.status==='pending').length;$('nav-pending').textContent=pending;$('nav-pending').classList.toggle('hidden',!pending);const names={pending:'Chờ duyệt',executing:'Đang xử lý',completed:'Đã xong',failed:'Thất bại',rejected:'Từ chối'};const rows=actions.map(a=>`<tr><td>#${a.id}</td><td><strong>${esc(a.account_label)}</strong></td><td>${esc(a.target_id)}</td><td>${esc(a.created_at)}</td><td>${status(names[a.status]||a.status,a.status==='completed'?'success':a.status==='pending'?'pending':'error')}</td><td>${isAdmin()&&a.status==='pending'?`<button class="btn primary" data-approve="${a.id}">Duyệt</button> <button class="small-btn" data-reject="${a.id}">Từ chối</button>`:esc(a.failure_reason||'')}</td></tr>`);$('actions-table').innerHTML=table(['Mã','Tài khoản','Campaign ID','Ngày tạo','Trạng thái','Thao tác'],rows);$('pause-account').innerHTML=cache.filter(x=>['meta','google'].includes(x.platform)&&x.connected).map(x=>`<option value="${x.id}">${esc(x.label)} (${esc(x.external_id)})</option>`).join('')}catch(e){notify(e.message,true)}}
async function loadTeam(){try{const list=await api('/api/team');$('team-table').innerHTML=table(['ID','Email','Quyền','Trạng thái',''],list.map(u=>`<tr><td>#${u.id}</td><td><strong>${esc(u.email)}</strong></td><td>${esc(u.role)}</td><td>${status(u.disabled?'Đã khóa':'Đang hoạt động',u.disabled?'error':'success')}</td><td>${u.id!==session.id&&!u.disabled?`<button class="small-btn" data-disable="${u.id}">Khóa</button>`:''}</td></tr>`))}catch(e){notify(e.message,true)}}
async function loadAudit(){try{const arr=await api('/api/audit');$('audit-table').innerHTML=table(['Ngày giờ','Sự kiện','Actor','Chi tiết'],arr.map(x=>`<tr><td>${esc(x.created_at)}</td><td><strong>${esc(x.event)}</strong></td><td>${esc(x.actor_id)}</td><td>${esc(x.detail)}</td></tr>`))}catch(e){notify(e.message,true)}}
function chatBubble(txt,user=false){const d=document.createElement('div');d.className='chat-bubble '+(user?'user':'bot');if(user){d.textContent=txt}else{const icon=document.createElement('span');icon.className='bot-icon';icon.textContent='✧';const content=document.createElement('div');content.textContent=txt;d.append(icon,content)}$('chat-messages').append(d);$('chat-messages').scrollTop=$('chat-messages').scrollHeight;return d}
async function chat(text){if(!text.trim())return;chatBubble(text,true);$('chat-input').value='';$('chat-send').disabled=true;const bubble=chatBubble('Đang phân tích dữ liệu...');try{const r=await api('/api/assistant/chat',{method:'POST',body:JSON.stringify({message:text,period:$('period').value})});bubble.lastChild.textContent=r.reply+'\n\n'+(r.disclaimer||''); if(r.mode==='openrouter')$('ai-provider-label').textContent='OPENROUTER: '+r.model}catch(e){bubble.lastChild.textContent=e.message}finally{$('chat-send').disabled=false;$('chat-messages').scrollTop=$('chat-messages').scrollHeight}}
function accountDialog(open){$('account-dialog').classList.toggle('hidden',!open);if(open){$('account-form').reset();$('acc-platform').dispatchEvent(new Event('change'))}}
document.querySelectorAll('[data-page]').forEach(e=>e.addEventListener('click',()=>go(e.dataset.page)));document.querySelectorAll('[data-go]').forEach(e=>e.addEventListener('click',()=>go(e.dataset.go)));$('menu').onclick=()=>$('sidebar').classList.toggle('open');$('global-account-search')?.addEventListener('input',()=>{if(current!=='accounts')go('accounts');applyAccountSearch()});$('refresh-dashboard').onclick=loadDashboard;$('period').onchange=()=>{if(current==='dashboard')loadDashboard()};$('export').onclick=()=>{location.href='/api/export/reports?period='+encodeURIComponent($('period').value)};
$('login-form').onsubmit=async e=>{e.preventDefault();$('login-error').textContent='';try{await api('/api/login',{method:'POST',body:JSON.stringify({email:$('login-email').value,password:$('login-pass').value})});session=await api('/api/studio/me');$('login-pass').value='';showApp()}catch(ex){$('login-error').textContent=ex.message}};
$('logout').onclick=async()=>{try{await api('/api/logout',{method:'POST'})}catch{}session=null;showLogin()};$('add-account').onclick=()=>accountDialog(true);$('close-dialog').onclick=()=>accountDialog(false);$('cancel-account').onclick=()=>accountDialog(false);$('account-dialog').onclick=e=>{if(e.target===$('account-dialog'))accountDialog(false)};
$('acc-platform').onchange=()=>{let p=$('acc-platform').value;let textarea=$('acc-token');textarea.disabled=p==='demo';textarea.required=p!=='demo';$('token-instruction').textContent=p==='demo'?'Demo hoàn toàn tách biệt số liệu thực.':p==='google'?'Google cần OAuth JSON gồm client_id, client_secret, refresh_token.':'Sử dụng token API chính thức. Meta yêu cầu ID số hoặc act_ID.'};
$('account-form').onsubmit=async e=>{e.preventDefault();const body=Object.fromEntries(new FormData(e.currentTarget));body.token=body.token||'';try{await api('/api/accounts',{method:'POST',body:JSON.stringify(body)});accountDialog(false);notify('Đã thêm tài khoản thành công');loadAccounts()}catch(err){notify(err.message,true)}};
$('refresh-actions').onclick=loadActions;$('pause-form').onsubmit=async e=>{e.preventDefault();try{await api('/api/actions',{method:'POST',body:JSON.stringify({account_id:Number($('pause-account').value),campaign_id:$('pause-campaign').value})});$('pause-campaign').value='';notify('Đã tạo yêu cầu. Chờ admin duyệt.');loadActions()}catch(err){notify(err.message,true)}};
$('chat-form').onsubmit=e=>{e.preventDefault();chat($('chat-input').value)};document.querySelectorAll('[data-prompt]').forEach(b=>b.onclick=()=>chat(b.dataset.prompt));
$('team-form').onsubmit=async e=>{e.preventDefault();try{const r=await api('/api/team',{method:'POST',body:JSON.stringify({email:$('team-email').value,role:$('team-role').value})});$('team-created').classList.remove('hidden');$('team-created').textContent='Mật khẩu tạm (chỉ hiển thị lần này): '+r.temporary_password+' — Hãy chuyển cho nhân viên bằng kênh riêng an toàn.';$('team-email').value='';loadTeam();notify('Đã tạo nhân viên')}catch(err){notify(err.message,true)}};
$('password-form').onsubmit=async e=>{e.preventDefault();try{await api('/api/me/password',{method:'POST',body:JSON.stringify({old_password:$('old-password').value,new_password:$('new-password').value})});session=null;$('password-form').reset();showLogin();notify('Đổi mật khẩu thành công. Vui lòng đăng nhập lại.')}catch(err){notify(err.message,true)}};
document.addEventListener('click',async e=>{const b=e.target.closest('[data-revoke],[data-approve],[data-reject],[data-disable]');if(!b)return;let id,path,method='POST',success='',reload=()=>{};if(b.dataset.revoke){if(!confirm('Thu hồi token của tài khoản? Các báo cáo thật sẽ không hoạt động.'))return;id=b.dataset.revoke;path='/api/accounts/'+id;method='DELETE';success='Đã thu hồi token';reload=loadAccounts}else if(b.dataset.approve){if(!confirm('XÁC NHẬN: Gửi lệnh PAUSED lên tài khoản quảng cáo THẬT? Kiểm tra kỹ Campaign ID và tài khoản.'))return;id=b.dataset.approve;path='/api/actions/'+id+'/approve';success='API đã tiếp nhận lệnh tạm dừng (chờ đồng bộ trạng thái)';reload=loadActions}else if(b.dataset.reject){if(!confirm('Từ chối yêu cầu này?'))return;path='/api/actions/'+b.dataset.reject+'/reject';success='Đã từ chối yêu cầu';reload=loadActions}else if(b.dataset.disable){if(!confirm('Vô hiệu hóa nhân viên này và hủy các phiên đăng nhập?'))return;path='/api/team/'+b.dataset.disable+'/disable';success='Đã khóa tài khoản';reload=loadTeam}try{await api(path,{method});notify(success);reload()}catch(err){notify(err.message,true)}});
initialize();

async function loadAISettings(){
  try{const r=await api('/api/ai/settings');
    $('ai-provider-label').textContent=r.enabled?'OPENROUTER: '+r.model:'PHÂN TÍCH NỘI BỘ';
    $('ai-model').value=r.model;
    $('ai-enabled').checked=r.enabled;
    $('ai-daily-limit').value=r.daily_limit||30;
    $('ai-settings-status').textContent=r.configured?'Đã lưu API key an toàn (không hiển thị lại). '+(r.enabled?'OpenRouter đang bật.':'OpenRouter đang tắt.'):'Chưa lưu API key.';
    $('ai-settings-status').textContent+=' Hôm nay (UTC): '+(r.used_today||0)+'/'+(r.daily_limit||30)+' lượt.';
    $('ai-disclaimer').textContent=r.enabled?'Đã bật OpenRouter: câu hỏi và thống kê tổng hợp sẽ gửi sang dịch vụ ngoài, phát sinh phí API. Không gửi token, tên hoặc ID tài khoản.':'Chế độ nội bộ; không gửi số liệu quảng cáo sang OpenRouter.';
  }catch(e){notify(e.message,true)}
}
$('ai-config-form').onsubmit=async e=>{e.preventDefault();if(!isAdmin())return;
  if($('ai-enabled').checked&&!confirm('Bạn đồng ý gửi câu hỏi và số liệu quảng cáo TỔNG HỢP tới OpenRouter (dịch vụ bên ngoài), có thể phát sinh chi phí?'))return;
  try{await api('/api/ai/settings',{method:'PUT',body:JSON.stringify({api_key:$('ai-api-key').value,model:$('ai-model').value.trim(),enabled:$('ai-enabled').checked,daily_limit:Number($('ai-daily-limit').value)})});
    $('ai-api-key').value='';notify('Đã cập nhật OpenRouter');loadAISettings();
  }catch(ex){notify(ex.message,true)}
};
$('ai-revoke').onclick=async()=>{if(!isAdmin()||!confirm('Xóa API key OpenRouter và tắt AI bên ngoài?'))return;
  try{await api('/api/ai/settings',{method:'DELETE'});$('ai-api-key').value='';notify('Đã thu hồi khóa OpenRouter');loadAISettings()}catch(ex){notify(ex.message,true)}
};

$('ai-preview-btn').onclick=async()=>{
  const p=$('ai-preview-output'); const question=$('chat-input').value.trim()||'Phân tích chi phí quảng cáo';
  try{const data=await api('/api/ai/preview',{method:'POST',body:JSON.stringify({message:question,period:$('period').value})});
    p.textContent=JSON.stringify(data,null,2);p.classList.remove('hidden');
  }catch(err){notify(err.message,true)}
};

// First-party OAuth connections with server-side provider credentials.
async function loadOAuthStatusAndPending(){
  try {
    const [status,pending]=await Promise.all([api('/api/oauth/status'),api('/api/oauth/pending')]);
    for(const provider of ['google','meta'])$('oauth-'+provider).disabled=!status[provider].configured;
    window.lhmProviderUI?.renderStatus?.(status);
    const unavailable=['google','meta'].filter(p=>!status[p].configured);
    $('oauth-status').textContent=unavailable.length?
       'Nền tảng chưa cấu hình: '+unavailable.map(p=>p==='google'?'Google Ads':'Meta Ads').join(', ')+'. Chọn một nền tảng ở trên rồi nhấn Cấu hình.':
       'Google và Meta đã có cấu hình OAuth riêng trên máy. Chọn nền tảng, đăng nhập và cấp quyền.';
    const container=$('oauth-pending-list');container.textContent='';
    for(const flow of pending){
      const box=document.createElement('div');box.className='oauth-choice-box';box.dataset.pendingProvider=flow.provider;box.classList.toggle('hidden',window.lhmSelectedProvider!==undefined&&flow.provider!==window.lhmSelectedProvider);
      const title=document.createElement('strong');title.textContent='Chọn tài khoản '+(flow.provider==='google'?'Google Ads':'Meta Ads')+' để thêm';box.append(title);
      const list=document.createElement('div');list.className='oauth-choice-list';
      for(const account of flow.accounts){
        const label=document.createElement('label');label.className='oauth-choice';
        const checkbox=document.createElement('input');checkbox.type='checkbox';checkbox.checked=true;checkbox.value=account.id;
        const display=document.createElement('span');display.textContent=account.label+' ('+account.id+') — '+account.currency;
        label.append(checkbox,display);list.append(label);
      }
      box.append(list);
      const submit=document.createElement('button');submit.type='button';submit.className='btn primary';submit.textContent='Lưu tài khoản đã chọn';
      submit.onclick=async()=>{
        const ids=Array.from(list.querySelectorAll('input:checked')).map(x=>x.value);
        if(!ids.length)return notify('Chọn ít nhất một tài khoản',true);
        submit.disabled=true;
        try{const response=await api('/api/oauth/pending/'+encodeURIComponent(flow.id)+'/import',
          {method:'POST',body:JSON.stringify({account_ids:ids})});
          notify('Đã kết nối '+response.imported+' tài khoản '+response.provider+'.');await loadAccounts();
        }catch(e){notify(e.message,true);submit.disabled=false;}
      };
      const dismiss=document.createElement('button');dismiss.type='button';dismiss.className='btn secondary';dismiss.textContent='Hủy';
      dismiss.onclick=async()=>{try{await api('/api/oauth/pending/'+encodeURIComponent(flow.id),{method:'DELETE'});await loadOAuthStatusAndPending();}catch(e){notify(e.message,true)}};
      const row=document.createElement('div');row.className='oauth-buttons';row.append(submit,dismiss);box.append(row);container.append(box);
    }
  }catch(e){$('oauth-status').textContent=e.message}
}
for(const provider of ['google','meta'])$('oauth-'+provider).onclick=async()=>{
  try{
    const reply=await api('/api/oauth/'+provider+'/start',{method:'POST'});
    const url=new URL(reply.authorization_url);
    if(!['https://accounts.google.com','https://www.facebook.com'].includes(url.origin))throw Error('URL OAuth không đáng tin cậy');
    // External system browser is REQUIRED for Google/Meta OAuth.
    // Embedded WebView2 login is unsupported by Google's OAuth policy.
    if(window.pywebview?.api?.open_oauth_url){
      const launched=await window.pywebview.api.open_oauth_url(url.href);
      if(!launched)throw Error('Không mở được trình duyệt đăng nhập OAuth.');
      notify('Trình duyệt đăng nhập đã mở. Khi hoàn tất, quay lại ứng dụng để chọn tài khoản.');
      const waitForAccounts=setInterval(()=>{
        if(!session||current!=='accounts'){clearInterval(waitForAccounts);return}
        loadOAuthStatusAndPending();
      },6000);
      setTimeout(()=>clearInterval(waitForAccounts),10*60*1000);
    } else {
      location.assign(url.href);
    }
  }catch(e){notify(e.message,true)}
};

// Provider applications are configured per Windows installation; never upload secrets to GitHub.
async function loadDesktopProviders(){
  const panel=$('desktop-provider-panel');if(!panel||!isAdmin())return;
  try{const data=await api('/api/desktop/providers');
    panel.classList.toggle('hidden',!data.desktop);
    for(const p of ['google','meta']){
      $('desktop-'+p+'-id').value=data[p].client_id||'';
      $('desktop-'+p+'-status').textContent=(data[p].configured?'Đã cấu hình trên máy. ':'Chưa cấu hình. ')+
       (data[p].secret_saved?'Khóa đã lưu mã hóa. ':'')+'Địa chỉ callback: '+data[p].callback_url;
    }
  }catch(e){panel.classList.add('hidden')}
}
for(const p of ['google','meta']){
  $('desktop-'+p+'-form').onsubmit=async e=>{
    e.preventDefault();if(!isAdmin())return;
    try{await api('/api/desktop/providers/'+p,{method:'PUT',body:JSON.stringify({
      client_id:$('desktop-'+p+'-id').value.trim(),client_secret:$('desktop-'+p+'-secret').value.trim()})});
      $('desktop-'+p+'-secret').value='';notify('Đã lưu cấu hình '+p+' trên máy.');
      await loadDesktopProviders();await loadOAuthStatusAndPending();
    }catch(ex){notify(ex.message,true)}
  };
  $('desktop-'+p+'-clear').onclick=async()=>{
    if(!isAdmin()||!confirm('Xóa thông tin ứng dụng '+p+' trên máy? Các tài khoản đã kết nối vẫn còn dữ liệu token riêng.'))return;
    try{await api('/api/desktop/providers/'+p,{method:'DELETE'});notify('Đã xóa cấu hình '+p);loadDesktopProviders();loadOAuthStatusAndPending()}catch(ex){notify(ex.message,true)}
  };
}


// The Windows EXE uses the current Windows Internet connection automatically.
// This monitor only calls our local backend, which checks fixed public HTTPS URLs
// without sending advertising credentials, session cookies or provider tokens.
let networkTimer = null;
let networkInFlight = false;
let networkWasOnline = null;
function renderNetworkStatus(online) {
  const badge = $('network-status');
  if (!badge) return;
  const label = badge.querySelector('[data-network-label]');
  badge.classList.toggle('offline', online === false);
  badge.classList.toggle('checking', online === null);
  label.textContent = online === null ? 'ĐANG KIỂM TRA MẠNG' :
     (online ? 'INTERNET ONLINE' : 'CHƯA XÁC NHẬN INTERNET');
  badge.title = online === null ? 'Đang kiểm tra Internet bằng HTTPS' :
      (online ? 'Máy tính đang truy cập được Internet' :
       'Không truy cập được các điểm kiểm tra HTTPS; giao diện cục bộ vẫn sử dụng được.');
}
async function checkInternet() {
  if (!session || networkInFlight) return;
  networkInFlight = true;
  try {
    const result = await api('/api/network/status');
    const online = result.online === true;
    const wasOnline = networkWasOnline;
    networkWasOnline = online;
    renderNetworkStatus(online);
    if (wasOnline === false && online) {
      notify('Internet đã kết nối lại. Đang cập nhật dữ liệu quảng cáo.');
      if (current === 'dashboard') await loadDashboard();
      else if (current === 'accounts') await loadAccounts();
    }
  } catch {
    if (session) {
      networkWasOnline = false;
      renderNetworkStatus(false);
    }
  } finally {
    networkInFlight = false;
  }
}
function stopNetworkMonitor() {
  if (networkTimer !== null) clearInterval(networkTimer);
  networkTimer = null;
  networkWasOnline = null;
}
function beginNetworkMonitor() {
  stopNetworkMonitor();
  renderNetworkStatus(null);
  checkInternet();
  networkTimer = setInterval(checkInternet, 45000);
}
window.addEventListener('online', () => { if (session) checkInternet(); });
window.addEventListener('offline', () => {
  if (session) { networkWasOnline = false; renderNetworkStatus(false); }
});
