/* CPA / ROAS targets for each authorized Ads account, local-first. */
'use strict';
(()=>{
  const $=id=>document.getElementById(id);
  const safe=str=>String(str??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const on=()=>!$('page-alerts')?.classList.contains('hidden');
  let accounts=[],loaded=false;

  function mount(){
    const page=$('page-alerts');if(!page||$('goal-panel'))return;
    const div=document.createElement('article');div.className='panel';div.id='goal-panel';
    div.innerHTML=`<div class="panel-title"><div><h3>🎯 Mục tiêu hiệu suất theo tài khoản</h3>
      <p class="muted tiny">Đặt CPA/ROAS mục tiêu cho Google Ads. Bộ giám sát chỉ tạo cảnh báo khi đủ chuyển đổi; không tự thay đổi giá thầu.</p></div></div>
    <form id="goal-form" class="form-row">
      <label>Tài khoản<select id="goal-account" required></select></label>
      <label>Mục tiêu<select id="goal-objective"><option value="cpa">CPA tối đa</option><option value="roas">ROAS tối thiểu (hệ số)</option></select></label>
      <label id="goal-meta-wrapper" hidden>Chuyển đổi Meta (chọn 1 loại)
        <select id="goal-meta-action">
          <option value="">— Chưa chọn sự kiện —</option>
          <option value="lead">Lead</option>
          <option value="offsite_conversion.fb_pixel_lead">Pixel Lead</option>
          <option value="purchase">Purchase</option>
          <option value="offsite_conversion.fb_pixel_purchase">Pixel Purchase</option>
          <option value="omni_purchase">Omni Purchase</option>
        </select></label>
      <label>Giá trị mục tiêu<input id="goal-target" type="number" min="0.001" step="any" required placeholder="Ví dụ: 50000"></label>
      <label>Chuyển đổi tối thiểu<input id="goal-conversions" type="number" min="3" max="1000" value="5" required></label>
      <label>Clicks tối thiểu<input id="goal-clicks" type="number" min="20" max="100000" value="100" required></label>
      <label class="fp-goal-toggle"><input id="goal-enabled" type="checkbox"> Bật cảnh báo theo mục tiêu</label>
      <button id="goal-save" type="submit" class="btn primary">Lưu mục tiêu</button>
    </form><p class="muted tiny" id="goal-guidance">Cảnh báo mang tính gợi ý, không chứng minh chiến dịch kém hiệu quả nếu tracking/attribution chưa đầy đủ.</p>
    <p id="goal-message" role="status" class="muted tiny"></p>`;
    page.prepend(div);
    const sel=$('goal-account');
    sel.addEventListener('change',readGoal);
    $('goal-objective').addEventListener('change',updateHint);
    $('goal-meta-action').addEventListener('change',updateHint);
    div.querySelector('form').addEventListener('submit',async e=>{
      e.preventDefault();
      if(typeof isAdmin==='function'&&!isAdmin())return;
      const id=Number(sel.value);
      if(!Number.isSafeInteger(id)||id<=0)return;
      const payload={enabled:$('goal-enabled').checked,objective:$('goal-objective').value,
         target:Number($('goal-target').value),
         min_conversions:Number($('goal-conversions').value),
         min_clicks:Number($('goal-clicks').value),
         meta_action_type:$('goal-meta-wrapper').hidden?null:($('goal-meta-action').value||null)};
      $('goal-save').disabled=true;$('goal-message').textContent='Đang lưu mục tiêu cục bộ…';
      try{const updated=await api('/api/goals/accounts/'+id,{method:'PUT',body:JSON.stringify(payload)});
        $('goal-message').textContent=updated.goal?.enabled?
        'Đã bật mục tiêu. Những lần quét tiếp theo sẽ xét KPI và tạo cảnh báo để xem xét.':
        'Đã lưu mục tiêu (chưa bật).';
      }catch(e){$('goal-message').textContent='Không thể lưu: '+String(e.message||e)}
      finally{$('goal-save').disabled=false}
    });
    document.querySelectorAll('[data-page="alerts"]').forEach(x=>x.addEventListener('click',()=>setTimeout(refresh,100)));
  }
  function updateHint(){
    const isRoas=$('goal-objective')?.value==='roas';
    const item=accounts.find(a=>String(a.id)===$('goal-account')?.value);
    const currency=item?.currency||'tiền tệ của tài khoản';
    const meta=item?.platform==='meta';
    $('goal-meta-wrapper').hidden=!meta;
    const action=$('goal-meta-action').value;
    const purchase=['purchase','offsite_conversion.fb_pixel_purchase','omni_purchase'].includes(action);
    $('goal-guidance').textContent=meta?
      'Meta: chọn đúng một sự kiện chuyển đổi. Cửa sổ quy đổi 7 ngày sau click (7d_click). '+
      (isRoas?'ROAS chỉ dùng Purchase và cần action_values chứa doanh thu.':'CPA dựa trên số chuyển đổi đúng loại đã chọn.')+
      ' Nếu Insights thiếu chuyển đổi hoặc tiền tệ không khớp, sẽ không tạo cảnh báo.':
      isRoas?'ROAS là doanh thu / chi phí, ví dụ 3 = 300%. Cần đủ chuyển đổi và xác nhận tracking.':
      'CPA mục tiêu tính theo '+currency+'. Cần đủ chuyển đổi/click và xem xét độ trễ quy đổi.';
    $('goal-enabled').disabled=(typeof isAdmin!=='function'||!isAdmin()) || (meta&&(!action||(isRoas&&!purchase)));
    if($('goal-enabled').disabled)$('goal-enabled').checked=false;
  }
  async function readGoal(){
    const id=Number($('goal-account')?.value);
    if(!Number.isSafeInteger(id)||id<=0)return;
    try{const response=await api('/api/goals/accounts/'+id),g=response.goal;
      $('goal-objective').value=g?.objective||'cpa';
      $('goal-meta-action').value=g?.meta_action_type||'';
      $('goal-target').value=g?.target||'';
      $('goal-conversions').value=g?.min_conversions||5;
      $('goal-clicks').value=g?.min_clicks||100;
      $('goal-enabled').checked=!!g?.enabled;
      $('goal-message').textContent=g?'Mục tiêu đã lưu trên máy · '+response.currency:'Chưa cấu hình mục tiêu cho tài khoản này.';
      updateHint();
    }catch(e){$('goal-message').textContent='Không tải được cấu hình: '+String(e.message||e)}
  }
  async function refresh(){
    if(!on()||!$('goal-account'))return;
    const old=$('goal-account').value;
    try{accounts=(await api('/api/accounts')).filter(a=>['google','meta'].includes(a.platform)&&a.connected&&!String(a.label).startsWith('[REVOKED]'));
      const sel=$('goal-account');
      sel.replaceChildren();
      for(const a of accounts)sel.add(new Option(a.label+' ('+a.platform+', '+a.currency+')',String(a.id)));
      if(accounts.some(a=>String(a.id)===old))sel.value=old;
      const permitted=typeof isAdmin==='function'&&isAdmin();
      for(const id of ['goal-objective','goal-target','goal-conversions','goal-clicks','goal-meta-action','goal-enabled','goal-save'])
        $(id).disabled=!permitted;
      $('goal-save').hidden=!permitted;
      if(accounts.length)await readGoal();
      else $('goal-message').textContent='Chưa có tài khoản Google/Meta đã kết nối.';
    }catch(e){$('goal-message').textContent='Không đọc được tài khoản: '+String(e.message||e)}
  }
  document.addEventListener('DOMContentLoaded',mount);
})();
