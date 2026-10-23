/* Signed online update controller for native Windows WebView2 only.
   No direct network calls, update URLs or Ads credentials in the frontend. */
'use strict';
(() => {
  const byId = id => document.getElementById(id);
  let checked = false;
  let busy = false;
  let available = false;
  const api = () => window.pywebview?.api;
  function status(message, detail) {
    byId('ui-update-status').textContent = message;
    if (detail !== undefined) byId('ui-update-detail').textContent = detail;
  }
  function visibility(download, install) {
    byId('ui-update-download').classList.toggle('hidden', !download);
    byId('ui-update-install').classList.toggle('hidden', !install);
  }
  async function call(method) {
    const bridge = api();
    if (!bridge?.[method]) throw Error('Chỉ hỗ trợ trong ứng dụng Windows EXE.');
    return bridge[method]();
  }
  async function check() {
    if (busy) return;
    busy = true;
    const button = byId('ui-update-check');
    button.disabled = true;
    button.setAttribute('aria-busy','true');
    visibility(false,false);
    status('Đang kiểm tra…','Đọc thông báo phát hành có chữ ký số của LHM.');
    try {
      const result = await call('check_update');
      checked = true;
      available = result.status === 'update_available';
      if (available) {
        status('Có bản mới ' + result.version,
          (result.message || '') + ' ' + (result.notes || '') +
          ' Bấm Tải và xác minh để chuẩn bị cập nhật.');
      } else {
        status(result.status === 'up_to_date' ? 'Đã là phiên bản mới nhất' :
          'Chưa thể cập nhật',result.message || '');
      }
      visibility(available,false);
    } catch {
      status('Không kiểm tra được cập nhật','Không thay đổi phần mềm hoặc dữ liệu.');
    } finally {
      busy = false;
      button.disabled = false;
      button.setAttribute('aria-busy','false');
    }
  }
  async function download() {
    if (busy || !available) return;
    busy = true;
    const button=byId('ui-update-download');
    button.disabled=true;button.setAttribute('aria-busy','true');
    status('Đang tải bản có chữ ký…','Đang kiểm tra SHA-256 trước khi cho phép cài đặt.');
    try {
      const result=await call('download_update');
      if (result.status==='downloaded'){
        status('Đã tải và xác minh bản ' + result.version, result.message);
        visibility(false,true);
      } else {
        status('Không thể tải bản cập nhật',result.message || '');
        visibility(available,false);
      }
    } catch {
      status('Lỗi trong quá trình tải','Bản EXE hiện tại không bị thay đổi.');
      visibility(available,false);
    } finally {
      busy=false;button.disabled=false;button.setAttribute('aria-busy','false');
    }
  }
  async function install() {
    if (busy || !confirm('Cài đặt phiên bản đã xác minh? Ứng dụng sẽ đóng rồi khởi động lại.')) return;
    busy=true;
    const button=byId('ui-update-install');button.disabled=true;
    status('Đang chuẩn bị khởi động lại','Giữ nguyên dữ liệu và cấu hình trên máy.');
    try{
      const result=await call('install_update');
      if (result.status!=='restarting') {
        status('Không thể bắt đầu cài đặt',result.message || '');
        busy=false;button.disabled=false;
      }
    }catch{
      status('Không thể bắt đầu cài đặt','Ứng dụng hiện tại vẫn được giữ nguyên.');
      busy=false;button.disabled=false;
    }
  }
  function init(){
    if (!byId('ui-update-check')) return;
    byId('ui-update-check').addEventListener('click',check);
    byId('ui-update-download').addEventListener('click',download);
    byId('ui-update-install').addEventListener('click',install);
    const shell=byId('shell');
    const maybeCheck=()=>{
      if (!checked && !shell.classList.contains('hidden') && api()?.check_update){
        checked=true;check();
      }
    };
    new MutationObserver(maybeCheck).observe(shell,{attributes:true,attributeFilter:['class']});
    document.addEventListener('pywebviewready',maybeCheck,{once:true});
    maybeCheck();
  }
  if (document.readyState==='loading') document.addEventListener('DOMContentLoaded',init,{once:true});
  else init();
})();
