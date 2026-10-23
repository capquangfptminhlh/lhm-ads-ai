/* The OAuth return tab was opened by the Windows SYSTEM browser.
 * Chrome/Edge often disallow closing ordinary tabs from JavaScript.
 * Try only after explicit user click, then show accurate keyboard fallback.
 */
'use strict';
(() => {
  const button = document.getElementById('oauth-finished-close');
  const hint = document.getElementById('oauth-close-hint');
  if (!button || !hint) return;
  button.addEventListener('click', () => {
    // The user gesture allows closing script-opened tabs on supported browsers.
    // Ordinary tabs may stay open; never claim success in that case.
    try { window.close(); } catch (_) { /* use keyboard fallback */ }
    window.setTimeout(() => {
      if (!window.closed) {
        hint.textContent = '';
        hint.append('Trình duyệt đang chặn đóng tab tự động. Hãy nhấn ');
        const control = document.createElement('kbd');
        control.textContent = 'Ctrl';
        const key = document.createElement('kbd');
        key.textContent = 'W';
        hint.append(control, ' + ', key, ', rồi quay về cửa sổ LHM Ads AI để chọn tài khoản.');
        button.textContent = 'Thử đóng tab';
      }
    }, 350);
  });
})();
