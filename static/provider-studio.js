/* Provider-specific connect experience. No credentials are handled in this module. */
'use strict';
(() => {
  const get = id => document.getElementById(id);
  const providers = ['google', 'meta'];
  let selected = 'google';
  let platformFilter = 'all';
  window.lhmAccountFilter = 'all';

  function setProvider(provider, options = {}) {
    if (!providers.includes(provider)) return;
    selected = provider;
    window.lhmSelectedProvider = provider;
    document.querySelectorAll('[data-pending-provider]').forEach(el=>el.classList.toggle('hidden',el.dataset.pendingProvider!==provider));
    for (const btn of document.querySelectorAll('[data-provider-choice]')) {
      const on = btn.dataset.providerChoice === selected;
      btn.classList.toggle('is-selected', on);
      btn.setAttribute('aria-pressed', String(on));
    }
    for (const panel of document.querySelectorAll('[data-provider-detail]')) {
      const active = panel.dataset.providerDetail === selected;
      panel.classList.toggle('hidden', !active);
    }
    if (options.filter !== false) setFilter(provider);
  }

  function setFilter(value) {
    if (!['all','google','meta','demo'].includes(value)) return;
    platformFilter = value;
    window.lhmAccountFilter = value;
    for (const btn of document.querySelectorAll('[data-account-filter]')) {
      const active = btn.dataset.accountFilter === value;
      btn.classList.toggle('is-active', active);
      btn.setAttribute('aria-pressed', String(active));
    }
    if (typeof applyAccountSearch === 'function') applyAccountSearch();
  }

  function renderCounts(accounts) {
    const valid = Array.isArray(accounts) ? accounts.filter(a => !String(a.label).startsWith('[REVOKED]')) : [];
    const counts = {all: valid.length, google: 0, meta: 0, demo: 0};
    for (const acc of valid) if (acc.platform in counts) counts[acc.platform] += 1;
    for (const platform of Object.keys(counts)) {
      const el = get('account-count-'+platform);
      if (el) el.textContent = String(counts[platform]);
    }

    // Each account is displayed separately; only a provider's own token
    // can be checked. The API sends back report statistics, never credentials.
    const rows = Array.from(document.querySelectorAll('#accounts-table tbody tr'));
    for (const [index, account] of (accounts || []).entries()) {
      const row = rows[index];
      if (!row || !['google','meta'].includes(account.platform) || !account.connected) continue;
      const cell = row.lastElementChild;
      const btn = document.createElement('button');
      btn.className = 'small-btn verify-btn';
      btn.type = 'button';
      btn.textContent = 'Kiểm tra API';
      btn.dataset.verifyAccount = String(account.id);
      cell.insertBefore(btn, cell.firstChild);
    }
  }

  function renderStatus(status) {
    for (const provider of providers) {
      const info = status?.[provider] || {};
      const badge = get('provider-badge-'+provider);
      if (!badge) continue;
      badge.textContent = info.configured ? '✓ Sẵn sàng đăng nhập' : '⚙ Cần cấu hình ứng dụng';
      badge.classList.toggle('is-ready', !!info.configured);
      badge.classList.toggle('is-unconfigured', !info.configured);
    }
  }

  function openManualForm(platform) {
    if (!['demo','google','meta'].includes(platform)) return;
    if (typeof accountDialog !== 'function') return;
    accountDialog(true);
    const hidden = get('acc-platform');
    hidden.value = platform;
    hidden.dispatchEvent(new Event('change'));
    const titles = {
      demo:'Thêm tài khoản Demo',
      google:'Google Ads · Nhập OAuth JSON nâng cao',
      meta:'Meta Ads · Nhập Access Token nâng cao'
    };
    const warnings = {
      demo:'Dữ liệu giả lập chỉ để trải nghiệm giao diện; không liên kết với tài khoản quảng cáo thật.',
      google:'Chỉ nhập OAuth JSON từ ứng dụng Google của chính bạn. Nên dùng nút đăng nhập Google Ads ở phía trên.',
      meta:'Chỉ nhập Access Token Meta hợp lệ của chính bạn. Không nhập mật khẩu Facebook; token được mã hóa trên máy.'
    };
    get('manual-provider-name').textContent = titles[platform];
    get('manual-provider-warning').textContent = warnings[platform];
    get('manual-submit').textContent = platform === 'demo' ? 'Tạo Demo' : 'Lưu kết nối '+(platform==='google'?'Google':'Meta');
    get('acc-token').closest('label').classList.toggle('hidden', platform === 'demo');
  }

  for (const btn of document.querySelectorAll('[data-provider-choice]')) {
    btn.addEventListener('click', () => setProvider(btn.dataset.providerChoice));
    btn.addEventListener('keydown', event => {
      if (!['ArrowLeft','ArrowRight'].includes(event.key)) return;
      event.preventDefault();
      const target = providers[(providers.indexOf(btn.dataset.providerChoice)+(event.key==='ArrowRight'?1:providers.length-1))%providers.length];
      setProvider(target);
      document.querySelector('[data-provider-choice="'+target+'"]')?.focus();
    });
  }
  for (const btn of document.querySelectorAll('[data-account-filter]')) {
    btn.addEventListener('click', () => setFilter(btn.dataset.accountFilter));
  }
  for (const btn of document.querySelectorAll('[data-provider-settings]')) {
    btn.addEventListener('click', () => {
      if (typeof go !== 'function') return;
      go('settings');
      // DOM updates and browser painting before scrolling.
      requestAnimationFrame(() => {
        const field = get('desktop-'+btn.dataset.providerSettings+'-id');
        if (field) {
          field.scrollIntoView({behavior:matchMedia('(prefers-reduced-motion: reduce)').matches?'instant':'smooth',block:'center'});
          field.focus({preventScroll:true});
        }
      });
    });
  }
  for (const btn of document.querySelectorAll('[data-manual-platform]')) {
    btn.addEventListener('click', () => openManualForm(btn.dataset.manualPlatform));
  }
  get('add-account')?.addEventListener('click', () => {
    queueMicrotask(() => {
      get('manual-provider-name').textContent = 'Thêm tài khoản Demo';
      get('manual-provider-warning').textContent = 'Dữ liệu giả lập, không kết nối với Google hoặc Meta.';
      get('manual-submit').textContent = 'Tạo Demo';
      get('acc-token').closest('label').classList.add('hidden');
    });
  });
  get('refresh-accounts')?.addEventListener('click', () => {
    if (typeof loadAccounts === 'function') loadAccounts();
  });

  // Empty-account filter retains the current view; the selected provider
  // determines the default filter, never merges Google/Meta identities.
  // The API already supports testing a single Google/Meta report after OAuth.
  // This is verification, not a campaign modification.
  document.addEventListener('click', async evt => {
    const button=evt.target.closest('[data-verify-account]');
    if(!button) return;
    const id=Number(button.dataset.verifyAccount);
    if(!Number.isSafeInteger(id)||id<=0) return;
    button.disabled=true;
    const oldLabel=button.textContent;
    button.textContent='Đang kiểm tra…';
    try{
      const report=await api('/api/report?account_id='+encodeURIComponent(String(id))+'&period=yesterday');
      if(report.source==='demo') throw Error('Đây chỉ là dữ liệu demo.');
      const label=button.closest('tr')?.querySelector('.status');
      if(label){label.textContent='API hoạt động';label.className='status success';}
      notify('Đã lấy báo cáo từ '+String(report.source||'API')+' thành công.');
    }catch(error){
      const label=button.closest('tr')?.querySelector('.status');
      if(label){label.textContent='API cần kiểm tra';label.className='status error';}
      notify('Kiểm tra API chưa thành công: '+error.message,true);
    }finally{
      button.disabled=false;
      button.textContent=oldLabel;
    }
  });

  window.lhmProviderUI = { setProvider, setFilter, renderCounts, renderStatus };
  setProvider('google', {filter:false});
  setFilter('all');
})();
