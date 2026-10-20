/* Read-only Google Ads / Meta Ads access checks, no raw tokens in browser. */
'use strict';
(() => {
  const find=id=>document.getElementById(id);
  const fields=[['token','Token còn hoạt động'],['account_read','Đọc tài khoản Ads'],
    ['report_read','Đọc báo cáo'],['scope_read','Scope API đọc'],
    ['scope_manage','Scope API quản lý'],['campaign_write','Sửa/tắt chiến dịch'],
    ['bid_write','Thay đổi giá thầu'],['budget_write','Thay đổi ngân sách'],
    ['strategy_write','Thay đổi chiến lược giá thầu']];
  const statuses={confirmed:'Đã xác minh',denied:'Bị từ chối / thiếu quyền',unverified:'Chưa xác minh'};
  const colors={confirmed:'#15803d',denied:'#b91c1c',unverified:'#a16207'};
  const asCell=(row,value)=>{
    let td=document.createElement('td');
    if(value instanceof Node)td.appendChild(value);else td.textContent=String(value??'—');
    row.appendChild(td);
  };
  function render(data){
    const container=find('permission-result');
    container.replaceChildren();
    let title=document.createElement('p');title.textContent=
      'Kết quả '+(data.platform==='google'?'Google Ads':'Meta Ads')+
      ' · '+new Date(data.checked_at).toLocaleString('vi-VN');container.appendChild(title);
    let table=document.createElement('table');
    let head=document.createElement('thead'),hr=document.createElement('tr');
    ['Chức năng','Trạng thái','Chi tiết'].forEach(x=>asCell(hr,x));
    head.appendChild(hr);table.appendChild(head);
    let body=document.createElement('tbody');
    for(const [key,label] of fields){
      let d=data[key]||{status:'unverified',detail:'Chưa có dữ liệu'};
      let s=statuses[d.status]?d.status:'unverified';
      let row=document.createElement('tr');
      asCell(row,label);
      let status=document.createElement('strong');status.textContent=statuses[s];status.style.color=colors[s];
      asCell(row,status);asCell(row,d.detail);body.appendChild(row);
    }
    table.appendChild(body);
    let wrap=document.createElement('div');wrap.className='table-wrap';wrap.appendChild(table);
    let scopes=document.createElement('p');scopes.className='muted tiny';
    scopes.textContent='Scopes đã xác nhận: '+(data.granted_scopes?.length?data.granted_scopes.join(', '):'Chưa có thông tin');
    let note=document.createElement('p');note.className='notice warning';note.textContent=data.note||'';
    container.append(wrap,scopes,note);
  }
  async function refresh(){
    let sel=find('permission-account');if(!sel)return;
    let value=sel.value;sel.replaceChildren(new Option('Chọn tài khoản đã kết nối',''));
    try{
      let accounts=await api('/api/accounts');
      for(const a of accounts){
        if(!['google','meta'].includes(a.platform)||!a.connected||String(a.label).startsWith('[REVOKED]'))continue;
        sel.add(new Option((a.platform==='google'?'Google Ads':'Meta Ads')+' · '+a.label+' ('+a.external_id+')',String(a.id)));
      }
      if([...sel.options].some(x=>x.value===value))sel.value=value;
    }catch(e){find('permission-result').textContent='Không tải được tài khoản: '+e.message}
  }
  document.addEventListener('DOMContentLoaded',()=>{
    const page=find('page-accounts');if(!page)return;
    const card=document.createElement('article');card.className='panel admin-only';
    const title=document.createElement('h3');title.textContent='Kiểm tra quyền API & Token';
    const explain=document.createElement('p');explain.className='muted tiny';
    explain.textContent='Kiểm tra token và quyền đọc báo cáo qua API chính thức. Scope quản lý không đồng nghĩa có quyền sửa. Không tạo lệnh thay đổi quảng cáo.';
    const row=document.createElement('div');row.className='form-row';
    const lbl=document.createElement('label');lbl.textContent='Tài khoản quảng cáo';
    const sel=document.createElement('select');sel.id='permission-account';lbl.appendChild(sel);
    const btn=document.createElement('button');btn.type='button';btn.className='btn primary';
    btn.textContent='Kiểm tra quyền ngay';row.append(lbl,btn);
    const result=document.createElement('div');result.id='permission-result';result.setAttribute('role','status');
    card.append(title,explain,row,result);page.appendChild(card);
    if(typeof isAdmin==='function'&&!isAdmin())card.classList.add('hidden');
    btn.addEventListener('click',async()=>{
      if(!sel.value){result.textContent='Vui lòng chọn tài khoản';return}
      btn.disabled=true;result.textContent='Đang xác thực quyền qua API...';
      try{render(await api('/api/permissions/probe/'+encodeURIComponent(sel.value),{method:'POST'}))}
      catch(e){result.textContent='Chưa kiểm tra được: '+e.message}
      finally{btn.disabled=false}
    });
    document.querySelector('[data-page="accounts"]')?.addEventListener('click',()=>setTimeout(refresh,150));
    find('refresh-accounts')?.addEventListener('click',()=>setTimeout(refresh,150));
    document.addEventListener('click',e=>{
      if(e.target.closest('[data-provider-choice],#oauth-google,#oauth-meta,#manual-submit'))setTimeout(refresh,800);
    });
    setTimeout(refresh,450);
  });
})();
