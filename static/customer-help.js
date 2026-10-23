/* Bundled customer connection help: immutable, offline, no network or credentials. */
'use strict';
(() => {
  const dialog=document.getElementById('customer-help-dialog');
  const content=document.getElementById('customer-help-content');
  if (!dialog || !content) return;
  let section='google';
  const sections={
    google: `
      <h3>Kết nối tài khoản Google Ads thật</h3>
      <p class="help-notice">Thời gian chuẩn bị phụ thuộc quyền Google Cloud và tài khoản Ads. Phần mềm chỉ đọc được số liệu khi bạn cấp quyền hợp lệ.</p>
      <ol>
        <li><strong>Chuẩn bị quyền.</strong> Dùng email Google có quyền truy cập tài khoản Google Ads cần kết nối hoặc MCC quản lý khách hàng.</li>
        <li><strong>Thiết lập Google Cloud.</strong> Mở <a href="https://console.cloud.google.com/" target="_blank" rel="noopener noreferrer">Google Cloud Console ↗</a>, tạo/chọn dự án, bật Google Ads API, kiểm tra mức quyền API. Để dùng tài khoản thật cần quyền tương ứng (thường từ Explorer), Test chỉ dành cho thử nghiệm.</li>
        <li><strong>Tạo ứng dụng OAuth.</strong> Trong Google Auth Platform, thiết lập màn hình đồng ý và scope <code>https://www.googleapis.com/auth/adwords</code>. Nếu còn ở chế độ Testing, thêm email của bạn vào Test users. Tạo OAuth Client loại <strong>Desktop app</strong> và tải JSON.</li>
        <li><strong>Nhập cấu hình vào LHM.</strong> Vào <strong>Tài khoản Ads → Google Ads → Cấu hình OAuth</strong>, tại bước 2 chọn file JSON vừa tải. Kiểm tra dữ liệu tự điền, sau đó bấm <strong>Lưu ứng dụng Google trên máy</strong>.</li>
        <li><strong>Đăng nhập và chọn Ads.</strong> Bấm <strong>Đăng nhập Google Ads</strong>, xác nhận tại trang Google chính thức. Chọn tài khoản Ads được phép dùng, với MCC chọn đúng khách hàng.</li>
        <li><strong>Kiểm tra dữ liệu thật.</strong> Bấm <strong>Kiểm tra API</strong> ở tài khoản vừa thêm; xem chi tiêu, số lần nhấp và khoảng ngày. Nhãn Demo không phải dữ liệu thực.</li>
      </ol>
      <p class="help-notice">Google Ads API hiện quản lý quyền qua dự án Cloud; từ 09/09/2026 không cần developer token theo chính sách mới. Nếu đọc API lỗi, kiểm tra quyền Cloud và quyền tài khoản Ads.</p>`,
    meta: `
      <h3>Kết nối Facebook / Meta Ads thật</h3>
      <ol>
        <li><strong>Quyền quảng cáo.</strong> Mở <a href="https://business.facebook.com/settings" target="_blank" rel="noopener noreferrer">Meta Business Settings ↗</a>, xác nhận Facebook của bạn có quyền trên tài khoản Ads cần đọc.</li>
        <li><strong>Tạo Meta App.</strong> Vào <a href="https://developers.facebook.com/apps/" target="_blank" rel="noopener noreferrer">Meta for Developers ↗</a>, tạo ứng dụng phù hợp với Marketing API/Facebook Login; chọn quyền <code>ads_read</code> cho báo cáo. Chỉ yêu cầu <code>ads_management</code> nếu thật sự cần sửa chiến dịch.</li>
        <li><strong>Cấu hình đăng nhập.</strong> Thiết lập Facebook Login/Business Login và <strong>Valid OAuth Redirect URI</strong> theo địa chỉ callback mà LHM hiển thị. App Live có thể cần HTTPS, App Review và xác minh Business.</li>
        <li><strong>Lưu App ID / App Secret.</strong> Vào <strong>Tài khoản Ads → Meta Ads → Cấu hình Meta App</strong>, nhập thông tin lấy từ App Settings → Basic. Secret được lưu mã hóa trên chính máy của bạn.</li>
        <li><strong>Đăng nhập Facebook.</strong> Bấm đăng nhập Meta Ads trên phần mềm, xác nhận trong trình duyệt hệ thống và chọn đúng tài khoản quảng cáo.</li>
        <li><strong>Kiểm tra API.</strong> Bấm <strong>Kiểm tra API</strong>; nếu Meta không hỗ trợ localhost cho app hiện tại, dùng cấu hình HTTPS/App Review hợp lệ. Chế độ Access Token nâng cao chỉ dành cho người đã hiểu rõ quyền và thời hạn token.</li>
      </ol>
      <p class="help-notice">LHM không yêu cầu mật khẩu Facebook. Không gửi App Secret, Access Token hoặc mã đăng nhập cho người hỗ trợ.</p>`,
    mcp: `
      <h3>MCP cho trợ lý AI — không phải API trong EXE</h3>
      <p><strong>Hiện tại LHM Ads AI chưa tích hợp MCP server trực tiếp.</strong> Google/Meta MCP chính thức có thể được cấu hình riêng trong AI client hỗ trợ MCP. Để đọc dữ liệu ngay trong LHM, hãy chọn API Google/Meta ở các tab bên cạnh.</p>
      <ol>
        <li><strong>Google Ads MCP.</strong> Xem <a href="https://developers.google.com/google-ads/api/docs/developer-toolkit/mcp-server" target="_blank" rel="noopener noreferrer">Google Ads MCP chính thức ↗</a>. Chuẩn bị Google Cloud, quyền Ads và xác thực theo tài liệu của Google rồi kết nối trong công cụ AI có hỗ trợ MCP. MCP Google chủ yếu để đọc, không phải đường tắt để đổi ngân sách.</li>
        <li><strong>Meta Ads MCP.</strong> Tham khảo <a href="https://developers.facebook.com/ads-mcp-server" target="_blank" rel="noopener noreferrer">Meta Ads MCP ↗</a> và <a href="https://www.facebook.com/meta-ads-ai-connectors" target="_blank" rel="noopener noreferrer">Meta AI Connectors ↗</a>. Đăng nhập trên trang Meta chính thức, kiểm tra app và các quyền trước khi chấp nhận.</li>
        <li><strong>Chỉ cấp quyền cần dùng.</strong> Nếu cần báo cáo, bắt đầu bằng chỉ đọc. Không đưa token vào prompt của mô hình hoặc lưu vào file cấu hình công khai.</li>
      </ol>
      <p class="help-notice">Nút “Bắt đầu kết nối” sẽ đưa bạn về luồng API bên trong LHM, không tự kích hoạt MCP.</p>`,
    errors: `
      <h3>Xử lý sự cố thường gặp</h3>
      <div class="help-troubleshooting">
        <details><summary>Google báo access_denied / 403</summary><p>Kiểm tra email có quyền Ads, email trong danh sách Test users nếu ứng dụng ở chế độ Testing, màn hình đồng ý và cấp quyền dự án Google Cloud. Đăng nhập lại đúng email.</p></details>
        <details><summary>Google không thấy tài khoản quảng cáo</summary><p>Kiểm tra quyền tài khoản Ads hoặc MCC, email đang đăng nhập và trạng thái khách hàng. OAuth thành công chưa đồng nghĩa email có quyền trên mọi tài khoản.</p></details>
        <details><summary>Google báo redirect_uri_mismatch</summary><p>Kiểm tra Client ID loại <strong>Desktop app</strong> (không dùng Web Application ID), tạo lại đúng loại nếu cần.</p></details>
        <details><summary>Meta báo Redirect URI không hợp lệ</summary><p>Sao chép lại địa chỉ callback ngay trong màn hình LHM. Kiểm tra chế độ Development/Live, yêu cầu HTTPS, App Review; không tìm cách bỏ qua bước xác minh.</p></details>
        <details><summary>Meta đã kết nối nhưng không đọc được báo cáo</summary><p>Kiểm tra ad account, quyền ads_read, phạm vi token, tình trạng App Review và thời hạn token. Sau đó chạy lại “Kiểm tra API”.</p></details>
        <details><summary>Tài khoản hiển thị nhưng số liệu trống</summary><p>Kiểm tra khoảng ngày, múi giờ và loại tiền. Chỉ số chuyển đổi có thể trống nếu chưa có theo dõi conversion; số liệu Demo không xác nhận kết nối thật.</p></details>
      </div>
      <p class="help-notice">Khi liên hệ hỗ trợ, chỉ gửi mã lỗi và ảnh đã che email, ID nhạy cảm, token. Không gửi file OAuth JSON hay Secret.</p>`
  };
  function render(){
    const tabs=dialog.querySelectorAll('[data-help-tab]');
    tabs.forEach(button=>{
      const active=button.dataset.helpTab===section;
      button.setAttribute('aria-selected',String(active));
      button.tabIndex=active?0:-1;
      button.classList.toggle('is-selected',active);
    });
    content.innerHTML=sections[section]; // Static bundled source, never interpolated user input.
    const cta=document.getElementById('customer-help-start');
    cta.textContent=section==='mcp'?'Mở kết nối API của LHM →':section==='errors'?'Quay lại cấu hình →':'Bắt đầu kết nối →';
  }
  function open(name){
    section=['google','meta','mcp','errors'].includes(name)?name:'google';
    render();
    if(!dialog.open)dialog.showModal();
    dialog.querySelector('[data-help-tab="'+section+'"]')?.focus();
  }
  function close(){if(dialog.open)dialog.close();}
  document.addEventListener('click',event=>{
    const trigger=event.target.closest('[data-customer-help]');
    if(trigger){open(trigger.dataset.customerHelp);return;}
    const tab=event.target.closest('[data-help-tab]');
    if(tab&&dialog.contains(tab)){section=tab.dataset.helpTab;render();tab.focus();return;}
    if(event.target.id==='customer-help-close'){close();return;}
    if(event.target.id==='customer-help-start'){
      const selected=section==='meta'?'meta':'google';
      close();
      if(typeof go==='function')go('settings');
      window.dispatchEvent(new CustomEvent('lhm:open-connect-guide',{detail:{provider:selected}}));
    }
  });
  dialog.querySelector('.customer-help-tabs').addEventListener('keydown',event=>{
    if(!['ArrowLeft','ArrowRight','Home','End'].includes(event.key))return;
    const order=['google','meta','mcp','errors'];
    let i=order.indexOf(section);
    if(event.key==='ArrowRight')i=(i+1)%order.length;
    else if(event.key==='ArrowLeft')i=(i+order.length-1)%order.length;
    else if(event.key==='Home')i=0;
    else i=order.length-1;
    event.preventDefault();section=order[i];render();
    dialog.querySelector('[data-help-tab="'+section+'"]')?.focus();
  });
  dialog.addEventListener('click',event=>{
    if(event.target===dialog)close();
  });
  render();
})();
