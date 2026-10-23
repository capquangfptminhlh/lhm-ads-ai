/* External Google/Meta OAuth runs in the SYSTEM browser. Chrome/Edge cannot
 * close tabs they did not allow a web page to open. Instead, request that the
 * local native WebView2 window be brought to the front, with Alt+Tab fallback.
 * This endpoint accepts only a short-lived one-time nonce from this page.
 */
'use strict';
(() => {
  const button = document.getElementById('oauth-finished-close');
  const hint = document.getElementById('oauth-close-hint');
  if (!button || !hint) return;
  button.addEventListener('click', async () => {
    if (button.disabled) return;
    button.disabled = true;
    button.textContent = 'Đang chuyển về LHM Ads AI…';
    try {
      const token = button.dataset.returnToken;
      const response = await fetch('/api/oauth/finished/activate', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-LHM-Return-Token': token
        },
        body: '{}',
        credentials: 'omit',
        cache: 'no-store',
        redirect: 'error'
      });
      if (!response.ok) throw Error('activation unavailable');
      const result = await response.json();
      if (!result.activated) throw Error('native app not found');
      button.textContent = 'Đã yêu cầu mở LHM Ads AI';
      hint.textContent = 'Ứng dụng đã được yêu cầu hiện lên phía trước. Nếu Windows chưa chuyển cửa sổ, nhấn Alt + Tab rồi chọn LHM Ads AI. Tab này không cần đóng để tiếp tục.';
    } catch (_) {
      button.textContent = 'Thử quay về phần mềm';
      hint.textContent = 'Không thể chuyển cửa sổ tự động. Nhấn Alt + Tab, chọn LHM Ads AI và lưu tài khoản. Muốn đóng tab trình duyệt, nhấn Ctrl + W.';
    } finally {
      button.disabled = false;
    }
  });
})();
