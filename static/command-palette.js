/* LHM Ads AI • safe, local command palette for NAVIGATION ONLY.
   Never calls Ads APIs, never searches tokens or triggers write approvals. */
'use strict';
(() => {
  const aliases = {
    dashboard: 'dashboard tong quan trang chu overview kpi',
    accounts: 'accounts tai khoan google meta oauth ket noi',
    campaigns: 'campaign chien dich quang cao',
    assistant: 'ai tro ly center phan tich',
    autopilot: 'tu dong automation giam sat',
    alerts: 'canh bao thong bao',
    reports: 'report bao cao xuat csv',
    approvals: 'phe duyet xac nhan',
    team: 'nhan su nhom quyen',
    audit: 'nhat ky lich su',
    settings: 'cai dat cau hinh mfa',
    license: 'ban quyen license gia han'
  };
  // Strip Vietnamese diacritics for predictable keyboard search.
  const normalize = text => String(text || '').normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '').replace(/đ/g,'d').replace(/Đ/g,'D')
    .toLocaleLowerCase('vi').trim();
  const $ = id => document.getElementById(id);

  function start() {
    const shell = $('shell'), overlay = $('ui-command-overlay');
    const launcher = $('ui-command-open'), closeButton = $('ui-command-close');
    const search = $('ui-command-input'), results = $('ui-command-results');
    if (!shell || !overlay || !launcher || !closeButton || !search || !results) return;
    let entries = [], selected = 0, restoreFocus = null;

    const visibleItems = () => [...document.querySelectorAll('#navigation .nav-link[data-page]')]
      .filter(link => !link.classList.contains('hidden') &&
        !link.closest('.hidden') && aliases[link.dataset.page])
      .map(link => ({
        page: link.dataset.page,
        // Use the existing navigation text, not a second source of permission.
        label: link.childNodes[1]?.textContent?.trim() ||
          link.textContent.replace(/\bNEW\b/g, '').trim(),
        icon: link.querySelector('span')?.textContent || '•',
        link
      }));
    // Base labels in nav buttons are text nodes after the decorative icon span.
    const displayLabel = item => {
      const text = [...item.link.childNodes]
        .filter(node => node.nodeType === Node.TEXT_NODE)
        .map(node => node.textContent).join('').trim();
      return text || item.label;
    };
    const matches = () => {
      const query = normalize(search.value);
      return visibleItems().filter(item => !query ||
        normalize(displayLabel(item)+' '+aliases[item.page]).includes(query));
    };
    const updateSelected = () => {
      const options = [...results.querySelectorAll('[role="option"]')];
      options.forEach((el, index) => {
        const current = index === selected;
        el.setAttribute('aria-selected', String(current));
        el.classList.toggle('is-highlighted', current);
      });
      const active = options[selected];
      if (active) {
        search.setAttribute('aria-activedescendant', active.id);
        active.scrollIntoView({block:'nearest'});
      } else {
        search.removeAttribute('aria-activedescendant');
      }
    };
    const activate = (index) => {
      const item = entries[index];
      if (!item || !item.link.isConnected || item.link.classList.contains('hidden')) return;
      hide(false);
      item.link.click(); // Reuses the existing read/navigation access control.
    };
    const render = () => {
      entries = matches();
      selected = 0;
      results.replaceChildren();
      if (!entries.length) {
        const empty = document.createElement('p');
        empty.className = 'ui-command-empty';
        empty.textContent = 'Không tìm thấy mục phù hợp. Thử tên trang khác.';
        results.append(empty);
      }
      for (const [index, item] of entries.entries()) {
        const option = document.createElement('button');
        option.type = 'button';
        option.setAttribute('role','option');
        option.id = 'ui-command-item-'+index;
        option.dataset.page = item.page;
        option.className = 'ui-command-option';
        const glyph = document.createElement('span');
        glyph.className = 'ui-command-option-icon';
        glyph.setAttribute('aria-hidden','true');
        glyph.textContent = item.icon;
        const words = document.createElement('span');
        words.className = 'ui-command-option-label';
        words.textContent = displayLabel(item);
        const hint = document.createElement('span');
        hint.className = 'ui-command-option-hint';
        hint.textContent = 'Mở trang ↗';
        option.append(glyph, words, hint);
        option.addEventListener('mouseenter', () => {selected=index;updateSelected();});
        option.addEventListener('click', () => activate(index));
        results.append(option);
      }
      updateSelected();
    };
    function show() {
      if (shell.classList.contains('hidden')) return;
      if (!overlay.classList.contains('hidden')) return;
      restoreFocus = document.activeElement;
      overlay.classList.remove('hidden');
      overlay.setAttribute('aria-hidden', 'false');
      launcher.setAttribute('aria-expanded','true');
      search.value = '';
      render();
      search.focus();
    }
    function hide(focusBack=true) {
      if (overlay.classList.contains('hidden')) return;
      overlay.classList.add('hidden');
      overlay.setAttribute('aria-hidden','true');
      launcher.setAttribute('aria-expanded','false');
      search.removeAttribute('aria-activedescendant');
      if (focusBack && restoreFocus?.isConnected) restoreFocus.focus();
    }
    const isVisible = () => !overlay.classList.contains('hidden');
    launcher.addEventListener('click', () => isVisible() ? hide() : show());
    closeButton.addEventListener('click', () => hide());
    overlay.addEventListener('pointerdown', evt => {
      if (evt.target === overlay) hide();
    });
    search.addEventListener('input', render);
    search.addEventListener('keydown', evt => {
      if (evt.key === 'ArrowDown' || evt.key === 'ArrowUp') {
        evt.preventDefault();
        if (entries.length) selected = (selected + (evt.key === 'ArrowDown' ? 1 : -1)
          + entries.length) % entries.length;
        updateSelected();
      } else if (evt.key === 'Enter') {
        evt.preventDefault();
        activate(selected);
      }
    });
    document.addEventListener('keydown', evt => {
      if (evt.key === 'Escape' && isVisible()) {
        evt.preventDefault();evt.stopPropagation();hide();return;
      }
      if (shell.classList.contains('hidden') || evt.altKey) return;
      const cmd = (evt.ctrlKey || evt.metaKey) && evt.shiftKey &&
        evt.key.toLocaleLowerCase('en') === 'p';
      const target = evt.target;
      const typing = target?.isContentEditable ||
        /^(INPUT|TEXTAREA|SELECT)$/.test(target?.tagName || '');
      const slash = evt.key === '/' && !evt.ctrlKey && !evt.metaKey && !typing;
      if (cmd || slash) {
        evt.preventDefault();
        if (isVisible()) hide();
        else show();
        return;
      }
      // Trap Tab focus inside the modal (including mouse-opened dialogs).
      if (evt.key === 'Tab' && isVisible()) {
        const controls = [search, ...results.querySelectorAll('button'), closeButton];
        const first = controls[0], last = controls[controls.length-1];
        if (evt.shiftKey && document.activeElement === first) {
          evt.preventDefault(); last.focus();
        } else if (!evt.shiftKey && document.activeElement === last) {
          evt.preventDefault(); first.focus();
        }
      }
    }, true);
    const observer = new MutationObserver(() => {
      if (shell.classList.contains('hidden')) hide(false);
    });
    observer.observe(shell, {attributes:true,attributeFilter:['class']});
  }
  if (document.readyState === 'loading')
    document.addEventListener('DOMContentLoaded', start, {once:true});
  else start();
})();
