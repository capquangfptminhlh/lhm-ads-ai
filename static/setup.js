'use strict';
const $ = id => document.getElementById(id);
const form = $('setup-form');
const error = $('form-error');
const submit = $('submit');
const suppliedToken = new URLSearchParams(location.hash.slice(1)).get('token');
history.replaceState(null, '', '/setup');
let secret = suppliedToken;
if (!secret || secret.length < 32) {
  error.textContent = 'Phiên thiết lập đã hết hạn. Hãy đóng LHM Ads AI rồi mở lại để nhận phiên mới.';
  submit.disabled = true;
}
for (const btn of document.querySelectorAll('[data-eye]')) {
  btn.addEventListener('click', () => {
    const input = $(btn.dataset.eye);
    input.type = input.type === 'password' ? 'text' : 'password';
    btn.textContent = input.type === 'password' ? 'Hiện' : 'Ẩn';
  });
}
$('password').addEventListener('input', () => {
  const s = $('password').value;
  const score = [s.length >= 12, /[A-Z]/.test(s), /[a-z]/.test(s), /\d/.test(s), /[^a-zA-Z0-9]/.test(s)].filter(Boolean).length;
  const fill = $('strength-fill');
  fill.style.width = (score * 20) + '%';
  fill.style.background = score >= 4 ? '#57a681' : score >= 3 ? '#e7a250' : '#d66a55';
  $('strength-label').textContent = s.length ? (score >= 4 ? 'Mật khẩu mạnh' : 'Thêm chữ hoa, chữ thường, số hoặc ký tự đặc biệt') : 'Nên có chữ hoa, chữ thường, số và ký tự đặc biệt';
});
form.addEventListener('submit', async evt => {
  evt.preventDefault();
  error.textContent = '';
  const email = $('email').value.trim();
  const password = $('password').value;
  const confirm = $('confirm').value;
  if (!secret) return;
  if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) return error.textContent = 'Hãy nhập email hợp lệ.';
  if (password.length < 12) return error.textContent = 'Mật khẩu phải có tối thiểu 12 ký tự.';
  if (password !== confirm) return error.textContent = 'Hai lần nhập mật khẩu chưa trùng nhau.';
  submit.disabled = true;
  submit.textContent = 'Đang thiết lập tài khoản...';
  try {
    const res = await fetch('/api/desktop/first-run', {
      method: 'POST', credentials: 'same-origin', cache: 'no-store',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({email, password, token: secret}),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(typeof data.detail === 'string' ? data.detail : 'Không thể tạo tài khoản.');
    secret = null;
    form.reset();
    location.replace('/studio');
  } catch (e) {
    error.textContent = e.message || 'Không thể kết nối phần mềm. Hãy thử lại.';
    submit.disabled = false;
    submit.innerHTML = 'Tạo tài khoản &amp; mở Dashboard <span>↗</span>';
  }
});
