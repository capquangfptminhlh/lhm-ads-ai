/* Provider connection assistant. Runs LOCALLY: no model API, no credential upload,
   no token logging, no pretending to authorize without provider consent. */
'use strict';
(() => {
  const byId = id => document.getElementById(id);
  const root = byId('provider-connect-guide');
  if (!root) return;
  const body = byId('connection-guide-body');
  const status = byId('connection-guide-status');
  const providers = ['google', 'meta'];
  let provider = 'google';
  let step = 0;
  let mode = 'api';
  const readiness = {google:false,meta:false};
  const callbacks = {google:'',meta:''};
  const GOOGLE_ID = /^[A-Za-z0-9._-]{8,200}\.apps\.googleusercontent\.com$/;
  const META_ID = /^\d{5,40}$/;
  const official = {
    google:'https://console.cloud.google.com/apis/credentials',
    meta:'https://developers.facebook.com/apps/'
  };

  function copy(text) {
    if (!text) return;
    if (navigator.clipboard?.writeText) {
      navigator.clipboard.writeText(text).then(() => feedback('Đã sao chép địa chỉ callback.'))
        .catch(() => feedback('Chọn đoạn callback bên trên để tự sao chép.'));
    } else feedback('Chọn đoạn callback bên trên để tự sao chép.');
  }
  function feedback(value, warning=false) {
    const box = body.querySelector('#connection-inline-message');
    if (box) {
      box.textContent = value;
      box.classList.toggle('warning',warning);
    }
    status.textContent = value;
  }
  function currentId() { return (byId('desktop-'+provider+'-id')?.value||'').trim(); }
  function currentSecret() { return (byId('desktop-'+provider+'-secret')?.value||'').trim(); }
  function validId() { return (provider==='google'?GOOGLE_ID:META_ID).test(currentId()); }
  function diagnostic() {
    if (!validId()) return provider==='google'
      ? 'Chưa có Client ID Desktop hợp lệ. Tạo OAuth Client ở Google Cloud hoặc nhập file JSON.'
      : 'App ID Meta cần là một dãy số. Hãy tạo ứng dụng trong Meta Developers.';
    if (provider==='meta'&&!currentSecret()&&!readiness.meta)
      return 'Thiếu App Secret của Meta. Secret được lưu mã hóa trên máy sau khi bạn bấm Lưu.';
    if (readiness[provider]) return 'Đã lưu cấu hình trên máy. Tiếp theo đăng nhập và cấp quyền từ nhà cung cấp.';
    return 'Thông tin có vẻ hợp lệ. Bấm Lưu ứng dụng để hoàn thành bước cấu hình.';
  }
  const templates = {
    google: [
      `<h4>Bước 1 · Tạo Google OAuth trong tài khoản của bạn</h4>
       <ol><li>Mở <a href="https://console.cloud.google.com/" target="_blank" rel="noopener noreferrer">Google Cloud Console</a>, chọn hoặc tạo dự án do bạn quản lý.</li>
       <li>Vào API Library, tìm <strong>Google Ads API</strong> và bật API cho dự án.</li>
       <li>Thiết lập màn hình đồng ý OAuth (Google Auth Platform): tên ứng dụng, email hỗ trợ, đối tượng dùng, người dùng thử nghiệm và phạm vi truy cập theo yêu cầu.</li>
       <li>Vào <a href="https://console.cloud.google.com/apis/credentials" target="_blank" rel="noopener noreferrer">Credentials</a>, tạo <strong>OAuth Client ID → Desktop app</strong>, sau đó tải file JSON.</li>
       </ol>
       <p class="connection-tip">Để đọc số liệu Google Ads bằng API, dự án/tài khoản phải có quyền truy cập API phù hợp. Từ 09/09/2026 Google không yêu cầu developer token cho Google Ads API. Trong Google Cloud, dự án cần được cấp Explorer (hoặc Basic/Standard) để đọc tài khoản thật; chỉ có OAuth Client ID chưa đủ.</p>
       <div class="connection-action-row"><a class="btn secondary" href="https://console.cloud.google.com/apis/credentials" target="_blank" rel="noopener noreferrer">Mở trang tạo OAuth ↗</a></div>`,
      `<h4>Bước 2 · Nhập OAuth tự động từ file JSON</h4>
       <p>Không cần gõ Client ID hay Secret thủ công. Chọn file JSON <strong>Desktop app</strong> vừa tải từ Google. File được đọc ngay trong ứng dụng, không đưa cho AI hoặc máy chủ bên ngoài.</p>
       <div class="connection-action-row"><button type="button" class="btn secondary" id="connection-import-json">📄 Chọn file JSON trên máy</button>
       <input type="file" id="connection-json-file" accept=".json,application/json" aria-label="Chọn OAuth Client JSON Google"></div>
       <p class="connection-tip">Ứng dụng chỉ nhận trường <code>installed.client_id</code> và <code>installed.client_secret</code> của OAuth Desktop. Không nhập file khóa service account hay mật khẩu Google.</p>
       <div class="connection-action-row"><button type="button" class="btn secondary" id="connection-focus-fields">Hoặc nhập thủ công phía dưới ↓</button></div>
       <div id="connection-inline-message" class="connection-diagnostic" role="status"></div>`,
      `<h4>Bước 3 · Kiểm tra trước khi kết nối Google</h4>
       <p>Trợ lý kiểm tra định dạng Client ID và trạng thái lưu trên máy. Không thể xác minh quyền truy cập Google Cloud nếu bạn chưa cấp quyền OAuth.</p>
       <div id="connection-inline-message" class="connection-diagnostic" role="status"></div>
       <div class="connection-action-row"><button type="button" class="btn primary" id="connection-save">Lưu ứng dụng Google trên máy</button></div>
       <p class="connection-tip">Nếu báo lỗi <strong>access_denied</strong>, hãy kiểm tra tài khoản được thêm vào danh sách người dùng thử nghiệm, quyền Ads và cấu hình OAuth. Nếu kết nối thành công nhưng báo cáo chưa đọc được, kiểm tra cấp quyền Google Ads API và developer token.</p>`,
      `<h4>Bước 4 · Đăng nhập Google Ads chính thức</h4>
       <p>Nhấn nút dưới để sang màn hình tài khoản và hoàn tất đăng nhập. Google mở trong trình duyệt hệ thống để bạn tự chọn tài khoản và đồng ý cấp quyền; trợ lý không biết mật khẩu.</p>
       <div id="connection-inline-message" class="connection-diagnostic" role="status"></div>
       <div class="connection-action-row"><button type="button" class="btn primary" id="connection-open-oauth">Đến nút đăng nhập Google Ads →</button></div>
       <p>Đăng nhập xong, chọn các tài khoản Ads cần nhập vào Studio rồi dùng nút <strong>Kiểm tra API</strong> để xác nhận số liệu thật.</p>`
    ],
    meta: [
      `<h4>Bước 1 · Tạo ứng dụng Meta do bạn sở hữu</h4>
       <ol><li>Truy cập <a href="https://developers.facebook.com/apps/" target="_blank" rel="noopener noreferrer">Meta for Developers</a>, tạo app thích hợp để đăng nhập và quản lý tài khoản quảng cáo của chính bạn.</li>
       <li>Thiết lập Facebook Login/Business Login theo sản phẩm được Meta cung cấp; kiểm tra vai trò và quyền <strong>ads_read</strong> hoặc <strong>ads_management</strong> khi cần.</li>
       <li>Trong cấu hình Facebook Login, khai báo Redirect URI dưới đây <strong>nếu chế độ app cho phép</strong>. App Live có thể yêu cầu HTTPS/App Review; localhost không luôn được chấp nhận.</li></ol>
       <code class="connection-callback" data-connection-callback>Đang đọc callback cục bộ…</code>
       <div class="connection-action-row"><button type="button" class="btn secondary" id="connection-copy-callback">Sao chép Redirect URI</button><a class="btn secondary" href="https://developers.facebook.com/apps/" target="_blank" rel="noopener noreferrer">Mở Meta Developers ↗</a></div>
       <div id="connection-inline-message" class="connection-diagnostic" role="status"></div>`,
      `<h4>Bước 2 · Nhập App ID và App Secret</h4>
       <p>Trong Meta App Dashboard → Settings → Basic, tìm App ID và App Secret. Bạn điền hai mục này ở form ngay phía dưới.</p>
       <p class="connection-tip">Không nhập mật khẩu Facebook. Không gửi App Secret cho AI, Zalo, GitHub hay người hỗ trợ. Secret chỉ được lưu mã hóa trên máy.</p>
       <div class="connection-action-row"><button type="button" class="btn secondary" id="connection-focus-fields">Đi đến ô nhập App ID/Secret ↓</button></div>
       <div id="connection-inline-message" class="connection-diagnostic" role="status"></div>`,
      `<h4>Bước 3 · Kiểm tra cấu hình Meta</h4>
       <p>Trợ lý kiểm tra App ID có đúng dạng số và đã lưu App Secret hay chưa.</p>
       <div id="connection-inline-message" class="connection-diagnostic" role="status"></div>
       <div class="connection-action-row"><button type="button" class="btn primary" id="connection-save">Lưu ứng dụng Meta trên máy</button></div>
       <p class="connection-tip">Nếu Meta báo Redirect URI không hợp lệ: kiểm tra callback, chế độ Development/Live, HTTPS, người dùng thử nghiệm và App Review. Trợ lý không thể tự duyệt quyền thay Meta.</p>`,
      `<h4>Bước 4 · Đăng nhập Meta Ads chính thức</h4>
       <p>Mở màn hình tài khoản, chọn Meta và bấm đăng nhập Facebook. Chỉ đồng ý quyền bạn muốn cấp cho ứng dụng.</p>
       <div id="connection-inline-message" class="connection-diagnostic" role="status"></div>
       <div class="connection-action-row"><button type="button" class="btn primary" id="connection-open-oauth">Đến nút đăng nhập Meta Ads →</button></div>
       <p>Nếu App Live không cho phép localhost, cấu hình HTTPS và quyền app theo yêu cầu Meta; không dùng cách vòng qua xác minh hay App Review.</p>`
    ]
  };
  // Official MCP products are documented here as an ALTERNATIVE AI-client path.
  // LHM now exposes a local read-only stdio MCP server, but no remote HTTP MCP endpoint.
  const mcpGuides = {
    google: `<h4>Google Ads MCP chính thức · Dành cho AI client</h4>
      <p>Google cung cấp <strong>google-ads-mcp</strong> (chỉ đọc số liệu, không sửa giá thầu/chiến dịch). Bản LHM Ads AI Windows vẫn kết nối Google bằng OAuth/API riêng.</p>
      <ol><li>Vào Google Cloud, bật Google Ads API và cấp quyền <strong>Explorer hoặc cao hơn</strong> cho dự án để truy cập tài khoản thật; developer token đã ngừng yêu cầu từ 09/09/2026.</li>
      <li>Cấu hình OAuth hoặc Application Default Credentials (ADC) trên máy theo hướng dẫn Google. Không nhập token vào khung chat.</li>
      <li>Trong AI client hỗ trợ MCP, thêm máy chủ Google Ads chính thức bằng <code>pipx</code>, <code>GOOGLE_PROJECT_ID</code> và ADC; đăng nhập chính chủ.</li>
      <li>Thử lệnh “Liệt kê tài khoản Google Ads được phép truy cập” hoặc “Báo cáo chi phí 7 ngày qua”.</li></ol>
      <div class="connection-tip">Lưu ý: Đây là <strong>hướng dẫn cấu hình AI client bên ngoài</strong>, MCP local của LHM có thể tạo khóa ở Cài đặt; Google MCP chính thức vẫn là kết nối riêng bên ngoài.</div>
      <div class="connection-action-row"><a class="btn secondary" href="https://developers.google.com/google-ads/api/docs/developer-toolkit/mcp-server" target="_blank" rel="noopener noreferrer">Tài liệu Google Ads MCP chính thức ↗</a></div>`,
    meta: `<h4>Meta Ads MCP / AI Connectors chính thức</h4>
      <p>Meta có Ads MCP dành cho AI client hỗ trợ kết nối. Đây là luồng khác với Meta Marketing API đang dùng trực tiếp trong LHM Ads AI.</p>
      <ol><li>Đăng nhập Meta bằng tài khoản được cấp quyền truy cập Business Portfolio/ad account.</li>
      <li>Mở trang <strong>Meta Ads AI Connectors</strong> hoặc hướng dẫn Ads MCP của Meta và làm theo quy trình dành cho AI client bạn chọn.</li>
      <li>Chỉ cấp phạm vi cần thiết; đọc báo cáo trước. Những thao tác sửa quảng cáo phải có xác nhận rõ ràng.</li>
      <li>Thử hỏi AI phân tích hiệu suất, kiểm tra đúng tài khoản Meta và không gửi Access Token qua chat.</li></ol>
      <div class="connection-tip">LHM Ads AI hiện <strong>chưa tích hợp máy chủ MCP Meta</strong>. Để quản lý trực tiếp trong EXE, chuyển về mục API và làm theo hướng dẫn OAuth/Marketing API.</div>
      <div class="connection-action-row"><a class="btn secondary" href="https://developers.facebook.com/ads-mcp-server" target="_blank" rel="noopener noreferrer">Meta Ads MCP chính thức ↗</a><a class="btn secondary" href="https://www.facebook.com/meta-ads-ai-connectors" target="_blank" rel="noopener noreferrer">Meta Ads AI Connectors ↗</a></div>`
  };
  function redraw() {
    for (const button of root.querySelectorAll('[data-connect-provider]')) {
      const active = button.dataset.connectProvider === provider;
      button.classList.toggle('is-selected',active);
      button.setAttribute('aria-pressed',String(active));
    }
    for (const button of root.querySelectorAll('[data-connect-step]')) {
      if (Number(button.dataset.connectStep)===step) button.setAttribute('aria-current','step');
      else button.removeAttribute('aria-current');
    }
    for (const button of root.querySelectorAll('[data-connection-mode]')) {
      const active=button.dataset.connectionMode===mode;
      button.classList.toggle('is-selected',active);
      button.setAttribute('aria-pressed',String(active));
    }
    root.querySelector('.connection-step-nav').classList.toggle('hidden',mode==='mcp');
    root.querySelector('.connection-guide-footer').classList.toggle('hidden',mode==='mcp');
    body.innerHTML = mode==='mcp'?mcpGuides[provider]:templates[provider][step]; // Static checked-in HTML only.
    const callback = body.querySelector('[data-connection-callback]');
    if (callback) callback.textContent = callbacks[provider] || 'Địa chỉ sẽ có sau khi tải cấu hình.';
    const diagnosis = body.querySelector('#connection-inline-message');
    if (diagnosis) {
      diagnosis.textContent = diagnostic();
      diagnosis.classList.toggle('warning', !readiness[provider]);
    }
    byId('connection-back').disabled=step===0;
    byId('connection-next').textContent=step===3?'Hoàn tất hướng dẫn':'Tiếp tục →';
    status.textContent=mode==='mcp'?'MCP · Kết nối trong AI client':(readiness[provider]?'✓ Đã lưu ứng dụng':'Chưa lưu ứng dụng');
  }
  function goStep(value) {
    step=Math.max(0,Math.min(3,value));
    redraw();
  }
  async function importGoogleJson(file) {
    if(!file || file.size > 128*1024) {feedback('File JSON quá lớn hoặc không tồn tại.',true);return;}
    try {
      const contents=JSON.parse(await file.text());
      const item=contents?.installed;
      if(!item || contents.web || !GOOGLE_ID.test(String(item.client_id||'')) ||
         (item.client_secret!==undefined && (typeof item.client_secret!=='string'||item.client_secret.length>512))) {
        feedback('File không phải OAuth Desktop JSON hợp lệ (cần phần installed).',true);return;
      }
      byId('desktop-google-id').value=item.client_id;
      byId('desktop-google-secret').value=item.client_secret || '';
      readiness.google=false;
      feedback('Đã điền Client ID và Secret từ file, chưa lưu. Chuyển sang bước xác minh để lưu.');
    } catch { feedback('Không đọc được JSON Desktop OAuth. Hãy kiểm tra file bạn tải từ Google Cloud.',true); }
    finally {const input=byId('connection-json-file');if(input)input.value='';}
  }
  function toAccountScreen(){
    if(!readiness[provider]) {
      feedback('Bạn cần lưu cấu hình ứng dụng trước khi đăng nhập.',true);
      return;
    }
    if(typeof go==='function')go('accounts');
    window.lhmProviderUI?.setProvider?.(provider);
    const button=byId('oauth-'+provider);
    button?.scrollIntoView({block:'center',behavior:'instant'});
    button?.focus({preventScroll:true});
  }
  async function performSave() {
    if(!validId() || (provider==='meta' && !currentSecret() && !readiness.meta)){
      feedback(diagnostic(),true);return;
    }
    const form = byId('desktop-'+provider+'-form');
    const submit = form?.querySelector('button[type="submit"]');
    if(!submit) return;
    submit.click();
    feedback('Đang lưu cấu hình. Sau khi thông báo lưu thành công, tiếp tục bước đăng nhập.');
  }
  root.addEventListener('click', event=>{
    const button=event.target.closest('button');
    if(!button)return;
    if(button.dataset.connectionMode){
      mode=button.dataset.connectionMode==='mcp'?'mcp':'api';
      redraw();return;
    }
    if(button.dataset.connectProvider){provider=button.dataset.connectProvider;goStep(0);return;}
    if(button.dataset.connectStep!==undefined){goStep(Number(button.dataset.connectStep));return;}
    if(button.id==='connection-back'){goStep(step-1);return;}
    if(button.id==='connection-next'){if(step<3)goStep(step+1);else toAccountScreen();return;}
    if(button.id==='connection-import-json'){byId('connection-json-file')?.click();return;}
    if(button.id==='connection-copy-callback'){copy(callbacks[provider]);return;}
    if(button.id==='connection-focus-fields'){
      byId('desktop-'+provider+'-id')?.scrollIntoView({block:'center',behavior:'instant'});
      byId('desktop-'+provider+'-id')?.focus({preventScroll:true});return;
    }
    if(button.id==='connection-save'){performSave();return;}
    if(button.id==='connection-open-oauth'){toAccountScreen();}
  });
  root.addEventListener('change',event=>{
    if(event.target.id==='connection-json-file')importGoogleJson(event.target.files?.[0]);
  });
  window.addEventListener('lhm:desktop-providers-status',event=>{
    const data=event.detail||{};
    for(const p of providers) {
      readiness[p] = data[p]?.configured===true;
      callbacks[p] = typeof data[p]?.callback_url==='string'?data[p].callback_url:'';
    }
    redraw();
  });
  window.addEventListener('lhm:open-connect-guide',event=>{
    const next=event.detail?.provider;
    if(providers.includes(next)){provider=next;goStep(0);}
    root.scrollIntoView({block:'start',behavior:'instant'});
  });
  redraw();
})();
