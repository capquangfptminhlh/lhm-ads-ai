/* Progressive enhancement: install UI cannot promise background monitoring. */
'use strict';
(() => {
  let pendingPrompt = null;
  const button = document.getElementById('pwa-install-button');
  const dialog = document.getElementById('pwa-install-guide');
  const close = document.getElementById('pwa-install-guide-close');
  const message = document.getElementById('pwa-install-guide-message');
  if (!button || !dialog || !close || !message) return;
  const standalone = () => window.matchMedia('(display-mode: standalone)').matches || navigator.standalone === true;
  const isIOS = /iPad|iPhone|iPod/.test(navigator.userAgent);
  const refresh = () => { button.hidden = standalone(); };
  window.addEventListener('beforeinstallprompt', event => {
    event.preventDefault();
    pendingPrompt = event;
    refresh();
  });
  window.addEventListener('appinstalled', () => { pendingPrompt = null; refresh(); });
  button.addEventListener('click', async () => {
    if (pendingPrompt) {
      const prompt = pendingPrompt;
      pendingPrompt = null;
      try { await prompt.prompt(); await prompt.userChoice; } catch (_) { /* fallback to manual instructions */ }
      refresh();
      return;
    }
    message.textContent = isIOS
      ? 'Trên iPhone hoặc iPad: mở bằng Safari, nhấn Chia sẻ và chọn Thêm vào Màn hình chính. Sau đó mở biểu tượng LHM Ads AI.'
      : 'Mở website LHM Ads AI bằng Chrome, nhấn menu ⋮ rồi chọn Cài đặt ứng dụng hoặc Thêm vào Màn hình chính. Cần HTTPS và trình duyệt hỗ trợ.';
    if (typeof dialog.showModal === 'function') dialog.showModal();
  });
  close.addEventListener('click', () => dialog.close());
  refresh();
  if ('serviceWorker' in navigator && window.isSecureContext) {
    window.addEventListener('load', () => {
      navigator.serviceWorker.register('/sw.js', {scope: '/'}).catch(() => {
        // Failure to install offline shell must not disrupt authenticated Ads operations.
      });
    });
  }
})();
