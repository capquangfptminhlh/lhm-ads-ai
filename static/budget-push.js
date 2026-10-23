/* User-initiated daily budget and Web Push enrollment; no background polling in PWA. */
'use strict';
(() => {
  const page=document.getElementById('page-settings');
  if (!page) return;
  const box=document.createElement('section');
  box.className='lhm-budget-settings';
  box.innerHTML=`<article class="panel">
    <h3>🔔 Cảnh báo ngân sách hằng ngày</h3>
    <p class="muted tiny">Đặt ngưỡng cho mỗi tài khoản. Chỉ phát cảnh báo khi API Google/Meta trả về chi tiêu HÔM NAY đã vượt ngưỡng; số liệu có thể chậm hoặc lệch múi giờ. Cần bật giám sát trên máy chủ chạy liên tục.</p>
    <form id="lhm-budget-form">
      <label>Tài khoản Ads <select id="lhm-budget-account" required></select></label>
      <label>Ngưỡng chi tiêu/ngày <input id="lhm-budget-amount" type="number" min="1" max="1000000000000" step="1" required placeholder="Ví dụ 200000"></label>
      <label class="lhm-budget-check"><input id="lhm-budget-enabled" type="checkbox" checked> Bật ngưỡng này</label>
      <button class="btn primary" type="submit">Lưu ngưỡng</button>
    </form><p id="lhm-budget-status" role="status" class="muted tiny"></p>
    <h3>Thông báo trên điện thoại</h3>
    <p class="muted tiny">Android: mở bằng Chrome. iPhone: cài ứng dụng lên màn hình chính rồi mở ứng dụng. Trình duyệt phải hỗ trợ Web Push và bạn phải đồng ý nhận thông báo. Không có quyền thông báo sẽ không gửi.</p>
    <button type="button" class="btn secondary" id="lhm-push-enable">Bật thông báo trên thiết bị này</button>
    <button type="button" class="btn secondary" id="lhm-push-disable">Tắt thông báo thiết bị này</button>
    <button type="button" class="btn secondary" id="lhm-push-test">Gửi thử thông báo</button>
    <p id="lhm-push-status" class="muted tiny" role="status"></p>
  </article>
  <article class="panel lhm-mcp-admin">
    <h3>🔗 MCP — kết nối trợ lý AI (chỉ đọc)</h3>
    <p class="muted tiny">Tạo khóa cho MCP client cài trên cùng máy có quyền truy cập dữ liệu LHM. AI chỉ được liệt kê tài khoản, đọc báo cáo và cảnh báo; không được sửa ngân sách, giá thầu hay chiến dịch. Không chia sẻ khóa cho người khác.</p>
    <label>Khóa hết hạn sau <select id="lhm-mcp-days"><option value="1">1 ngày</option><option value="7" selected>7 ngày</option><option value="30">30 ngày</option></select></label>
    <button class="btn secondary" type="button" id="lhm-mcp-create">Tạo khóa MCP</button>
    <div class="lhm-mcp-once hidden" id="lhm-mcp-once"><label>Khóa chỉ hiển thị một lần <input readonly type="password" id="lhm-mcp-secret"></label>
      <button class="btn secondary" type="button" id="lhm-mcp-copy">Sao chép khóa</button>
      <button class="btn secondary" type="button" id="lhm-mcp-clear">Ẩn khóa</button></div>
    <div id="lhm-mcp-list" role="status" class="muted tiny"></div>
    <p class="muted tiny">Cấu hình AI client: command <code>python</code>, args <code>["-m","ads_core.mcp_stdio"]</code>, env <code>LHM_MCP_ACCESS_TOKEN</code> là khóa vừa tạo. Chạy tại máy có LHM backend và đúng DB_PATH/MASTER_KEY. Không có MCP HTTP công khai.</p>
  </article>`;
  const settingAfter=page.querySelector('.section-heading');
  if (settingAfter)settingAfter.insertAdjacentElement('afterend',box);
  const id=name=>document.getElementById(name);
  const status=(name,value)=>{id(name).textContent=value;};
  let csrf=null,accountRules=[];
  async function request(path,options={}){
    if(!csrf){
      const res=await fetch('/api/studio/me',{credentials:'same-origin'});
      if(!res.ok)throw new Error('Đăng nhập để cài đặt thông báo');
      const me=await res.json();csrf=me.csrf;
      box.querySelector('.lhm-mcp-admin').classList.toggle('hidden',me.role!=='admin');
      id('lhm-budget-form').querySelector('button[type="submit"]').disabled=me.role!=='admin';
    }
    const headers={'Accept':'application/json',...options.headers};
    if(options.body)headers['Content-Type']='application/json';
    if(options.method && !['GET','HEAD'].includes(options.method))headers['X-CSRF-Token']=csrf;
    const resp=await fetch(path,{credentials:'same-origin',...options,headers});
    const data=await resp.json().catch(()=>({}));
    if(resp.status===401){csrf=null;throw new Error('Phiên đăng nhập hết hạn');}
    if(!resp.ok)throw new Error(data.detail||'Không thực hiện được thao tác');
    return data;
  }
  function setSelected(){
    const a=accountRules.find(x=>String(x.account_id)===id('lhm-budget-account').value);
    id('lhm-budget-amount').value=a?.threshold||'';
    id('lhm-budget-enabled').checked=Boolean(a?.enabled);
    if(a)status('lhm-budget-status','Ngưỡng dùng '+a.currency+'. Tài khoản '+a.platform+'.');
  }
  async function refresh(){
    try {
      const data=await request('/api/budgets');
      accountRules=data.rules||[];
      const sel=id('lhm-budget-account'), previous=sel.value;
      sel.replaceChildren(...accountRules.map(x=>{
        const o=document.createElement('option');
        o.value=String(x.account_id);o.textContent=x.label+' (#'+x.account_id+', '+x.currency+')';
        return o;
      }));
      if(accountRules.some(x=>String(x.account_id)===previous))sel.value=previous;
      id('lhm-budget-form').querySelector('button[type="submit"]').disabled=!accountRules.length;
      setSelected();
      if(!accountRules.length)status('lhm-budget-status','Chưa có tài khoản Google/Meta Ads thực đã kết nối.');
      const cfg=await request('/api/push/config');
      id('lhm-push-enable').disabled=!cfg.available;
      status('lhm-push-status',cfg.available?
        'Máy chủ đã cấu hình Push. Nhấn Bật để cho phép thiết bị nhận thông báo.':
        'Máy chủ chưa cấu hình VAPID nên chưa thể gửi Push.');
      await listKeys();
    } catch(e){status('lhm-budget-status',e.message);}
  }
  id('lhm-budget-account').addEventListener('change',setSelected);
  id('lhm-budget-form').addEventListener('submit',async e=>{
    e.preventDefault();
    const acc=id('lhm-budget-account').value;
    const threshold=Number(id('lhm-budget-amount').value);
    if(!acc||!Number.isFinite(threshold)||threshold<=0)return;
    try{
      await request('/api/budgets/'+encodeURIComponent(acc),{method:'PUT',
        body:JSON.stringify({threshold,enabled:id('lhm-budget-enabled').checked})});
      status('lhm-budget-status','Đã lưu ngưỡng. Cảnh báo được kiểm tra ở chu kỳ giám sát kế tiếp.');
      await refresh();
    }catch(err){status('lhm-budget-status',err.message);}
  });
  function urlBase64ToBytes(s){
    const t=(s+'='.repeat((4-s.length%4)%4)).replace(/-/g,'+').replace(/_/g,'/');
    const str=atob(t);return Uint8Array.from(str,c=>c.charCodeAt(0));
  }
  id('lhm-push-enable').addEventListener('click',async()=>{
    try{
      if(!('PushManager' in window)||!('serviceWorker' in navigator)||!('Notification' in window))
        throw Error('Trình duyệt này chưa hỗ trợ Web Push');
      const config=await request('/api/push/config');
      if(!config.available)throw Error('Chưa có cấu hình VAPID');
      const permission=await Notification.requestPermission();
      if(permission!=='granted')throw Error('Thiết bị chưa được cấp quyền thông báo');
      const worker=await navigator.serviceWorker.ready;
      let subscription=await worker.pushManager.getSubscription();
      if(!subscription)subscription=await worker.pushManager.subscribe({
        userVisibleOnly:true,applicationServerKey:urlBase64ToBytes(config.public_key)
      });
      await request('/api/push/subscriptions',{method:'POST',
        body:JSON.stringify(subscription.toJSON())});
      status('lhm-push-status','Đã đăng ký Push trên thiết bị. Chỉ gửi khi có cảnh báo mới từ agent.');
    }catch(err){status('lhm-push-status',err.message);}
  });
  id('lhm-push-test').addEventListener('click',async()=>{
    try{
      const result=await request('/api/push/test',{method:'POST'});
      status('lhm-push-status',result.accepted>0
        ? 'Đã gửi '+result.accepted+' yêu cầu Push; hãy kiểm tra thông báo trên thiết bị.'
        : 'Không có thiết bị nào nhận được yêu cầu Push; kiểm tra quyền/khóa VAPID và đăng ký lại.');
    }catch(err){status('lhm-push-status',err.message);}
  });
  id('lhm-push-disable').addEventListener('click',async()=>{
    try{
      const worker=await navigator.serviceWorker.ready;
      const sub=await worker.pushManager.getSubscription();
      if(sub){
        await request('/api/push/subscriptions',{method:'DELETE',
          body:JSON.stringify(sub.toJSON())});
        await sub.unsubscribe();
      }
      status('lhm-push-status','Đã tắt thông báo trên thiết bị.');
    }catch(err){status('lhm-push-status',err.message);}
  });
  async function listKeys(){
    if(box.querySelector('.lhm-mcp-admin').classList.contains('hidden'))return;
    try {
      const data=await request('/api/mcp/local/tokens');
      const list=id('lhm-mcp-list');list.replaceChildren();
      for(const item of data.tokens){
        const line=document.createElement('div');line.className='lhm-mcp-token';
        const state=item.revoked_at?'Đã thu hồi':item.expires_at<Date.now()/1000?'Đã hết hạn':'Còn hiệu lực';
        const span=document.createElement('span');
        span.textContent='Khóa #'+item.id+' · '+state+' · hết hạn '+new Date(item.expires_at*1000).toLocaleString('vi-VN');
        line.append(span);
        if(!item.revoked_at){
          const btn=document.createElement('button');btn.type='button';btn.className='btn secondary';
          btn.textContent='Thu hồi';btn.addEventListener('click',async()=>{
            try{await request('/api/mcp/local/tokens/'+item.id,{method:'DELETE'});await listKeys();}
            catch(err){list.textContent=err.message;}
          });line.append(btn);
        }
        list.append(line);
      }
    }catch(err){status('lhm-mcp-list',err.message);}
  }
  id('lhm-mcp-create').addEventListener('click',async()=>{
    try{
      const result=await request('/api/mcp/local/tokens',{method:'POST',
        body:JSON.stringify({days:Number(id('lhm-mcp-days').value)})});
      id('lhm-mcp-secret').value=result.token;
      id('lhm-mcp-once').classList.remove('hidden');
      await listKeys();
    }catch(err){status('lhm-mcp-list',err.message);}
  });
  id('lhm-mcp-copy').addEventListener('click',async()=>{
    try{await navigator.clipboard.writeText(id('lhm-mcp-secret').value);
      status('lhm-mcp-list','Đã sao chép khóa. Giữ kín trong trình quản lý mật khẩu.');}
    catch(_){status('lhm-mcp-list','Không thể sao chép tự động.');}
  });
  id('lhm-mcp-clear').addEventListener('click',()=>{
    id('lhm-mcp-secret').value='';id('lhm-mcp-once').classList.add('hidden');
  });
  let visible=false;
  const observer=new MutationObserver(()=>{
    const now=!page.classList.contains('hidden');
    if(now&&!visible){csrf=null;refresh();}
    if(!now&&visible){id('lhm-mcp-secret').value='';id('lhm-mcp-once').classList.add('hidden');}
    visible=now;
  });
  observer.observe(page,{attributes:true,attributeFilter:['class']});
  if(!page.classList.contains('hidden'))refresh();
})();
