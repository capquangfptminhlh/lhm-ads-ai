/* LHM Ads AI interface controls; no network calls or customer data storage. */
'use strict';
(() => {
  function start() {
    const dock = document.querySelector('.ui-mobile-dock');
    const sidebar = document.getElementById('sidebar');
    const menu = document.getElementById('menu');
    const more = document.getElementById('ui-dock-more');
    const shell = document.getElementById('shell');
    if (!dock || !sidebar || !menu || !more || !shell) return;

    const tabs = [...dock.querySelectorAll('[data-ui-tab]')];
    const sidebarTabs = [...document.querySelectorAll('#navigation .nav-link[data-page]')];
    const sync = () => {
      const selected = sidebarTabs.find(el => el.classList.contains('active'))?.dataset.page;
      for (const tab of tabs) {
        const active = tab.dataset.uiTab === selected;
        tab.classList.toggle('is-current', active);
        if (active) tab.setAttribute('aria-current', 'page');
        else tab.removeAttribute('aria-current');
      }
      const isOpen = sidebar.classList.contains('open') &&
        !shell.classList.contains('hidden') &&
        window.matchMedia('(max-width: 900px)').matches;
      more.setAttribute('aria-expanded', String(isOpen));
      // Non-dock pages remain visible as the active destination on mobile.
      const onAdditionalPage = Boolean(selected) && !tabs.some(tab => tab.dataset.uiTab === selected);
      more.classList.toggle('is-current', isOpen || onAdditionalPage);
      if (onAdditionalPage && !isOpen) more.setAttribute('aria-current', 'page');
      else more.removeAttribute('aria-current');
    };

    // Reuse the existing, already tested mobile sidebar/backdrop/Escape logic.
    more.addEventListener('click', () => {
      menu.click();
      sync();
    });
    for (const tab of tabs) {
      tab.addEventListener('click', () => {
        // Switching sections should start at the heading, not the last scroll
        // offset of the previous page (a common mobile navigation defect).
        window.scrollTo(0, 0);
      });
    }

    const observer = new MutationObserver(sync);
    for (const item of sidebarTabs)
      observer.observe(item, {attributes: true, attributeFilter: ['class']});
    observer.observe(sidebar, {attributes: true, attributeFilter: ['class']});
    observer.observe(shell, {attributes: true, attributeFilter: ['class']});
    window.addEventListener('resize', sync, {passive: true});
    sync();
  }
  if (document.readyState === 'loading')
    document.addEventListener('DOMContentLoaded', start, {once: true});
  else start();
})();
