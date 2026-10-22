/* FinPoint Motion Controller. Data-driven animation only; no external network/API.
   Does not attach handlers to approval or mutation buttons. */
'use strict';
(() => {
  const $ = id => document.getElementById(id);
  const reduceMotion = () => window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  const number = value => Number(value).toLocaleString('vi-VN', {maximumFractionDigits: 2});
  const currentFrames = new Map();
  const duration = 820;

  function countUp(id, value, suffix, reset = false) {
    const node = $(id);
    if (!node || !Number.isFinite(value) || value < 0) return;
    const old = currentFrames.get(id);
    if (old) window.cancelAnimationFrame(old);
    const finalText = number(value) + (suffix || '');
    currentFrames.delete(id);
    if (reduceMotion() || document.hidden || !node.closest('.view:not(.hidden)')) {
      node.textContent = finalText;
      return;
    }
    // Animation always starts from 0, never from an invented historical KPI.
    const start = performance.now();
    const animate = now => {
      if (!node.isConnected || !node.closest('.view:not(.hidden)')) {
        node.textContent = finalText;
        currentFrames.delete(id);
        return;
      }
      const p = Math.min(1, (now - start) / duration);
      const ease = 1 - Math.pow(1 - p, 3);
      node.textContent = p === 1 ? finalText : number(value * ease) + (suffix || '');
      if (p < 1) currentFrames.set(id, requestAnimationFrame(animate));
      else {
        currentFrames.delete(id);
        const card = node.closest('.kpi-card');
        if (card && !reset) {
          card.dataset.motionUpdated = 'true';
          window.setTimeout(() => { if (card.isConnected) delete card.dataset.motionUpdated; }, 590);
        }
      }
    };
    currentFrames.set(id, requestAnimationFrame(animate));
  }

  function dashboardData(evt) {
    const t = evt.detail?.totals;
    if (!t || typeof t !== 'object' || !t.included_accounts) return;
    if (t.spend !== null && t.spend !== undefined && t.currency)
      countUp('k-spend', Number(t.spend), ' ' + t.currency);
    // In multi-currency mode, preserve the explicit 'Đa tiền tệ' label.
    countUp('k-impressions', Number(t.impressions), '');
    countUp('k-clicks', Number(t.clicks), '');
    countUp('k-ctr', Number(t.ctr), '%');
  }

  document.addEventListener('lhm:dashboard-reset', () => {
    for (const frame of currentFrames.values()) window.cancelAnimationFrame(frame);
    currentFrames.clear();
  });
  function syncNavigation() {
    const shell = $('shell');
    if (!shell || shell.classList.contains('hidden')) return;
    for (const link of document.querySelectorAll('#navigation .nav-link')) {
      if (link.classList.contains('active')) link.setAttribute('aria-current','page');
      else link.removeAttribute('aria-current');
    }
  }

  function initNavigation() {
    const shell = $('shell'), sidebar = $('sidebar');
    if (!shell || !sidebar) return;
    const backdrop = document.createElement('div');
    backdrop.className = 'sidebar-backdrop';
    backdrop.setAttribute('aria-hidden', 'true');
    backdrop.id = 'sidebar-backdrop';
    sidebar.after(backdrop);
    const menu = $('menu');
    const close = () => {
      sidebar.classList.remove('open');
      syncBackdrop();
    };
    const syncBackdrop = () => {
      const mobile = window.matchMedia('(max-width: 900px)').matches;
      const open = mobile && sidebar.classList.contains('open') && !shell.classList.contains('hidden');
      backdrop.classList.toggle('open', open);
      if (menu) menu.setAttribute('aria-expanded', String(open));
      sidebar.setAttribute('aria-label', 'Điều hướng LHM Ads AI');
      if (open) {
        backdrop.removeAttribute('inert');
        backdrop.setAttribute('aria-hidden', 'false');
      } else {
        backdrop.setAttribute('inert', '');
        backdrop.setAttribute('aria-hidden', 'true');
      }
    };
    backdrop.addEventListener('click', () => {
      close();
      menu?.focus();
    });
    const obs = new MutationObserver(() => {
      syncBackdrop();syncNavigation();
    });
    obs.observe(sidebar, {attributes: true,attributeFilter: ['class']});
    obs.observe(shell, {attributes: true,attributeFilter: ['class']});
    for (const link of document.querySelectorAll('#navigation .nav-link'))
      obs.observe(link, {attributes: true,attributeFilter: ['class']});
    window.addEventListener('resize', syncBackdrop, {passive: true});
    document.addEventListener('keydown', evt => {
      if (evt.key === 'Escape') {
        if (sidebar.classList.contains('open')) {
          close();menu?.focus();evt.preventDefault();return;
        }
        const modal = $('account-dialog');
        if (modal && !modal.classList.contains('hidden')) $('close-dialog')?.click();
      }
      if ((evt.ctrlKey || evt.metaKey) && evt.key.toLowerCase() === 'k') {
        if (shell.classList.contains('hidden')) return;
        evt.preventDefault();
        const accounts = document.querySelector('.nav-link[data-page="accounts"]');
        if (accounts) accounts.click();
        window.setTimeout(() => {
          const mobile = window.matchMedia('(max-width: 650px)').matches;
          const search = mobile ? $('account-list-search') : $('global-account-search');
          search?.focus();search?.select();
        }, 60);
      }
    });
    document.addEventListener('click', evt => {
      if (evt.target.closest('#navigation .nav-link')) {
        window.setTimeout(() => {syncNavigation();syncBackdrop();}, 0);
      }
    });
    syncBackdrop();syncNavigation();
  }

  function start() {
    initNavigation();
    document.addEventListener('lhm:dashboard-updated', dashboardData);
  }
  if (document.readyState === 'loading')
    document.addEventListener('DOMContentLoaded', start, {once: true});
  else start();
})();
