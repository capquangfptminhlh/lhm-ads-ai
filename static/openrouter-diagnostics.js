/* User-triggered, non-billable OpenRouter diagnostics. No keys in browser. */
'use strict';
(() => {
  const $=id=>document.getElementById(id);
  const nodes=[];
  let busy=false;
  const keyMessages={
    not_configured:'Chưa lưu API key OpenRouter.',
    local_decryption_failed:'Không giải mã được key đã lưu trên máy. Kiểm tra cấu hình và sao lưu.',
    invalid:'API key không hợp lệ hoặc đã bị thu hồi (HTTP 401).',
    rejected:'OpenRouter từ chối quyền của key (HTTP 403).',
    rate_limited:'OpenRouter giới hạn kiểm tra (HTTP 429).',
    provider_unavailable:'Không đọc được trạng thái key từ OpenRouter.',
    invalid_response:'Dịch vụ trả về dữ liệu key không hợp lệ.',
    network_error:'Không thể kết nối dịch vụ. Kiểm tra Internet/Tường lửa.',
    valid:'API key đã được OpenRouter xác thực thành công.'
  };
  const modelMessages={
    not_checked:'Chưa thể kiểm tra model vì key chưa được xác thực.',
    not_found:'Model không xuất hiện trong danh sách OpenRouter được trả về. Kiểm tra Model ID.',
    zdr_unavailable:'Model có tồn tại nhưng chưa có tuyến Zero Data Retention (ZDR) tương thích. Chọn model khác hoặc kiểm tra nhà cung cấp.',
    zdr_available:'Model có tuyến Zero Data Retention được OpenRouter công bố.',
    provider_unavailable:'Không đọc được danh sách model từ OpenRouter.',
    invalid_response:'Danh sách model trả về không hợp lệ.',
    network_error:'Không kết nối được danh sách model.'
  };
  function createPanel(host, id){
    if(!host||$(id))return;
    const article=document.createElement('section');
    article.id=id;article.className='or-diagnostics';
    article.innerHTML='<header><div><h3>Kiểm tra kết nối OpenRouter</h3><p>Kiểm tra key, model ZDR, hạn mức và giấy phép ngay trên máy. Không gửi câu hỏi hoặc tính lượt chat.</p></div></header>'+
      '<div class="or-diagnostics-actions"><button type="button" class="btn secondary admin-only" data-or-check>↻ Kiểm tra OpenRouter thật</button>'+
      '<button type="button" class="btn secondary" data-or-settings>⚙ Cấu hình</button>'+
      '<button type="button" class="btn secondary" data-or-license>◇ Bản quyền</button></div>'+
      '<p data-or-status role="status" aria-live="polite">Chưa kiểm tra. Bấm nút để xác minh API key và model với OpenRouter.</p>'+
      '<div data-or-details class="or-diagnostics-details"></div>'+
      '<p class="or-diagnostics-caption">Kết quả là kiểm tra miễn phí qua API key và danh sách model, KHÔNG phải thử sinh câu trả lời. Khi chat thật vẫn có thể phát sinh phí API.</p>';
    host.append(article);nodes.push(article);
    article.querySelector('[data-or-check]').addEventListener('click',run);
    article.querySelector('[data-or-settings]').addEventListener('click',()=>typeof go==='function'&&go('settings'));
    article.querySelector('[data-or-license]').addEventListener('click',()=>typeof go==='function'&&go('license'));
  }
  function paintStatus(s){for(const n of nodes)n.querySelector('[data-or-status]').textContent=s}
  function clear(){for(const n of nodes)n.querySelector('[data-or-details]').replaceChildren()}
  function row(name,message,kind){
    const node=document.createElement('div');
    node.className='or-diagnostics-row '+kind;
    const title=document.createElement('strong');title.textContent=name;
    const value=document.createElement('span');value.textContent=message;
    node.append(title,value);return node;
  }
  function show(result){
    const license=result.license||{};
    const rights=license.active?'Giấy phép hợp lệ cho chức năng AI.':
      'Giấy phép Windows chưa hoạt động ('+(license.reason||'không xác định')+'). Vào Bản quyền để kích hoạt/gia hạn.';
    const used=Number(result.used_today||0),limit=Number(result.daily_limit||0);
    const left=Math.max(0,limit-used);
    const statuses=[
      ['Cấu hình',result.enabled?'OpenRouter đã bật':'OpenRouter đang tắt. Vào Cài đặt để bật nếu cần.',
        result.enabled?'ok':'warn'],
      ['API key',keyMessages[result.key_status]||'Không xác định',
        result.key_status==='valid'?'ok':'warn'],
      ['Model '+(result.model||''),modelMessages[result.model_status]||'Chưa rõ tình trạng model.',
        result.model_status==='zdr_available'?'ok':'warn'],
      ['Giấy phép',rights,license.active?'ok':'warn'],
      ['Hạn mức','Còn '+left+'/'+limit+' lượt chat nội bộ hôm nay (UTC). Đây không phải số dư OpenRouter.',
        left>0?'ok':'warn']
    ];
    if(result.key_limit_exhausted===true)
      statuses.push(['Hạn mức key','OpenRouter báo giới hạn chi tiêu riêng của key đã hết.','warn']);
    const summary=result.ready_for_ai?
      'Đã xác minh key và model ZDR; đủ điều kiện thử chat trong LHM. Chưa thực hiện lệnh sinh AI.':
      'Chưa sẵn sàng chat OpenRouter. Kiểm tra các mục cảnh báo bên dưới.';
    paintStatus(summary);
    for(const n of nodes){
      const box=n.querySelector('[data-or-details]');box.replaceChildren();
      for(const [name,message,kind] of statuses)box.append(row(name,message,kind));
    }
  }
  async function run(){
    if(busy)return;
    if(typeof isAdmin==='function'&&!isAdmin()){
      paintStatus('Chỉ quản trị viên được kiểm tra key và quyền nhà cung cấp.');return;
    }
    busy=true;clear();paintStatus('Đang xác minh API key và model ZDR với OpenRouter…');
    for(const n of nodes)n.querySelector('[data-or-check]').disabled=true;
    try{
      const r=await api('/api/ai/diagnostics',{method:'POST',body:'{}'});
      show(r);
      window.lhmRefreshAILicense?.();
    }catch(e){
      paintStatus('Không thể kiểm tra: '+String(e.message||e));
    }finally{
      busy=false;
      for(const n of nodes)n.querySelector('[data-or-check]').disabled=false;
    }
  }
  document.addEventListener('DOMContentLoaded',()=>{
    const settings=$('ai-config-panel');
    if(settings)createPanel(settings,'or-diagnostics-settings');
    const assistant=$('page-assistant');
    const hub=$('fp-ai-hub');
    if(assistant)createPanel(hub||assistant,'or-diagnostics-ai');
  });
})();
