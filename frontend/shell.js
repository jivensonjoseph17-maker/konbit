/*
 * KONMBIT — kad aplikasyon an (meni sou kote + ba anlè)
 * Chemen: frontend/shell.js
 *
 * Chak paj aplikasyon an chaje api.js, apre sa shell.js, epi li rele:
 *
 *     const identity = await Konbit.shell.mount('employees');
 *
 * Paj la dwe gen: <aside id="sidebar"></aside> ak <header id="topbar"></header>.
 * Meni an chanje dapre wòl moun nan. Pou ajoute yon nouvo paj, ajoute yon
 * liy nan NAV anba a (ak tradiksyon l nan frontend/i18n/*.json) epi retire `soon: true`.
 *
 * mount() tann tradiksyon yo, mete lang kont lan an plas (Konbit.i18n.sync)
 * epi tradui tèks fiks HTML la (data-i18n) ANVAN li retounen — kidonk tout
 * sa paj la rann apre `await mount()` deja nan bon lang lan.
 */
(function () {
  'use strict';
  const { api, auth, fmt, h, i18n, t } = Konbit;

  const ADMIN = ['super_admin', 'org_admin', 'hr'];
  const MANAGERS = ['super_admin', 'org_admin', 'hr', 'manager'];

  // `needsEmployee`: paj la sèvi sèlman si kont lan gen yon dosye anplwaye.
  // Label yo se kle tradiksyon (tèks kreyòl la). '|meni' separe "Anplwaye"
  // nan meni an (Employés) ak wòl "Anplwaye" (Employé).
  const NAV = [
    { group: null, items: [
      { id: 'dashboard', label: 'Akèy', href: 'dashboard.html' },
    ] },
    { group: 'Jesyon', roles: ADMIN, items: [
      { id: 'employees', label: 'Anplwaye|meni', href: 'employees.html' },
      { id: 'payroll', label: 'Peyòl', href: 'payroll.html' },
      { id: 'leave-admin', label: 'Balans konje', href: 'leave-balances.html' },
      { id: 'hiring', label: 'Rekritman', href: 'jobs.html' },
      { id: 'training', label: 'Fòmasyon', href: 'training.html' },
    ] },
    { group: 'Ekip', roles: MANAGERS, items: [
      { id: 'team', label: 'Ekip mwen', href: 'team.html' },
      { id: 'timesheets', label: 'Tan travay', href: 'timesheets.html' },
    ] },
  ];


  function initials(name) {
    return (name || '?').split(/\s+/).filter(Boolean).slice(0, 2)
      .map((p) => p[0].toUpperCase()).join('');
  }

  // -------------------------------------------------------------------------
  // SIDEBAR — sou telefòn ☰ louvri yon tiwa (pa sove, li toujou fèmen lè paj
  // la chaje). Sou òdinatè ☰ kache/montre sidebar la nèt, epi CHWA a SOVE
  // (localStorage) pou l rete konsa lè moun nan chanje paj.
  // -------------------------------------------------------------------------

  const SIDEBAR_KEY = 'konbit.sidebar_collapsed';
  const isMobileView = () => window.matchMedia('(max-width: 880px)').matches;

  function isSidebarCollapsed() {
    try { return localStorage.getItem(SIDEBAR_KEY) === '1'; } catch { return false; }
  }

  /** Aplike chwa sove a sou <body> anvan nou rann anyen — evite yon ti fla. */
  function applySidebarState() {
    document.body.classList.toggle('sidebar-collapsed', isSidebarCollapsed());
  }

  function renderSidebar(identity, active) {
    const role = identity.user.role;
    const aside = document.getElementById('sidebar');
    if (!aside) return;

    const groups = NAV
      .filter((g) => !g.roles || g.roles.includes(role))
      .map((g) => h('div', { class: 'nav-group' },
        g.group ? h('p', { class: 'nav-group-label' }, t(g.group)) : null,
        h('ul', { class: 'nav-list' }, ...g.items.map((item) => {
          if (item.soon) {
            return h('li', {},
              h('span', { class: 'nav-item is-soon', 'aria-disabled': 'true' },
                t(item.label), h('span', { class: 'soon' }, t('byento'))),
            );
          }
          const current = item.id === active;
          return h('li', {},
            h('a', {
              class: current ? 'nav-item is-active' : 'nav-item',
              href: item.href,
              'aria-current': current ? 'page' : null,
            }, t(item.label)),
          );
        })),
      ));

    aside.replaceChildren(
      h('a', { class: 'brand sidebar-brand', href: 'dashboard.html', 'aria-label': t('KONMBIT — akèy') },
        h('span', { class: 'brand-mark', 'aria-hidden': 'true' }, 'K'),
        h('span', { class: 'brand-name' }, 'KONMBIT'),
      ),
      h('nav', { 'aria-label': t('Meni aplikasyon an') }, ...groups),
    );
  }

  function renderTopbar(identity) {
    const bar = document.getElementById('topbar');
    if (!bar) return;
    const user = identity.user;

    const menuBtn = h('button', {
      class: 'btn btn-ghost btn-sm menu-btn',
      type: 'button',
      'aria-controls': 'sidebar',
      'aria-expanded': String(isMobileView() ? false : !isSidebarCollapsed()),
    }, t('Meni'));

    menuBtn.addEventListener('click', () => {
      if (isMobileView()) {
        // Telefòn: tiwa ki louvri sou kontni a, pa gen anyen pou sove.
        const open = document.body.classList.toggle('nav-open');
        menuBtn.setAttribute('aria-expanded', String(open));
        return;
      }
      // Òdinatè: kache/montre sidebar la nèt, epi sove chwa a.
      const collapsed = document.body.classList.toggle('sidebar-collapsed');
      try { localStorage.setItem(SIDEBAR_KEY, collapsed ? '1' : '0'); } catch { /* ok san sove */ }
      menuBtn.setAttribute('aria-expanded', String(!collapsed));
    });

    const logout = h('button', { class: 'btn btn-quiet btn-sm', type: 'button' }, t('Dekonekte'));
    logout.addEventListener('click', () => auth.logout());

    // Chwa lang: sove nan kont lan (PATCH /api/auth/me) epi paj la rechaje.
    const langPicker = i18n.switcher();

    bar.replaceChildren(
      h('div', { class: 'topbar-left' },
        menuBtn,
        h('span', { class: 'topbar-org' }, identity.organization_name || ''),
      ),
      h('div', { class: 'topbar-user' },
        h('div', { class: 'user-chip' },
          h('div', { class: 'name' }, user.full_name),
          h('div', { class: 'role' }, fmt.role(user.role)),
        ),
        h('span', { class: 'avatar', 'aria-hidden': 'true' }, initials(user.full_name)),
        langPicker,
        logout,
      ),
    );

    // Fèmen meni mobil lan lè moun nan klike deyò l
    document.addEventListener('click', (e) => {
      if (!document.body.classList.contains('nav-open')) return;
      if (e.target.closest('#sidebar') || e.target.closest('.menu-btn')) return;
      document.body.classList.remove('nav-open');
      menuBtn.setAttribute('aria-expanded', 'false');
    });
  }

  /**
   * Monte kad la epi retounen idantite moun nan.
   * `allowedRoles`: si li bay, moun ki pa gen wòl sa yo voye tounen nan akèy.
   */
  async function mount(active, allowedRoles) {
    if (!auth.requireLogin()) return null;
    await i18n.ready;

    let identity;
    try {
      identity = await api.get('/api/auth/identity');
    } catch (err) {
      const main = document.querySelector('main');
      if (main) main.replaceChildren(h('div', { class: 'alert alert-error' }, err.message));
      return null;
    }

    if (allowedRoles && !allowedRoles.includes(identity.user.role)) {
      location.replace('dashboard.html');
      return null;
    }

    // Lang kont lan, epi tèks fiks HTML la.
    await i18n.sync(identity.user.preferred_language);
    i18n.apply(document);

    applySidebarState();
    renderSidebar(identity, active);
    renderTopbar(identity);
    return identity;
  }

  // =========================================================================
  // CHWAZI YON ANPLWAYE — chan rechèch olye yon lis dewoulan
  //
  // Yon <select> ak tout anplwaye yo pa mache pou yon gwo biznis: API a bay
  // 100 moun maksimòm. Isit la moun nan tape 2-3 lèt, nou chèche sou sèvè a
  // (non oswa nimewo), epi li chwazi nan 20 rezilta. Mache ak 10 kou 10 000.
  //
  //     const picker = Konbit.shell.employeePicker({ id: 'f-manager', excludeIds: [emp.id] });
  //     parent.append(picker.el);
  //     picker.value            → id anplwaye a oswa null
  //     picker.set(id, name)    → mete yon valè (egz: manadjè aktyèl la)
  //     picker.clear()
  // =========================================================================

  const nameCache = new Map();     // id → "Prenon Non"

  /** Non anplwaye yo, ak yon sèl rekèt pa moun ki poko nan kach la. */
  async function employeeNames(ids) {
    const missing = [...new Set(ids.filter((x) => x && !nameCache.has(x)))];
    await Promise.all(missing.map(async (empId) => {
      try {
        const e = await api.get(`/api/employees/${empId}`);
        nameCache.set(empId, `${e.first_name} ${e.last_name}`);
      } catch {
        nameCache.set(empId, null);   // pa gen dwa wè l, oswa li pa egziste
      }
    }));
    return nameCache;
  }

  /** Non yon anplwaye si li deja nan kach la (apre employeeNames). */
  function cachedName(empId) {
    return nameCache.get(empId) || null;
  }

  function ensurePickerStyles() {
    if (document.getElementById('konbit-emp-picker-css')) return;
    const style = document.createElement('style');
    style.id = 'konbit-emp-picker-css';
    style.textContent = `
      .emp-picker { position: relative; }
      .emp-picker .input { padding-inline-end: 40px; }
      .emp-picker-clear {
        position: absolute; inset-inline-end: 6px; top: 50%; transform: translateY(-50%);
        width: 30px; height: 30px; border: 0; border-radius: 50%; background: transparent;
        color: var(--muted); font-size: 18px; line-height: 1; cursor: pointer;
      }
      .emp-picker-clear:hover { background: var(--surface-2); color: var(--text); }
      .emp-picker-list {
        position: absolute; inset-inline: 0; top: calc(100% + 4px); z-index: 60;
        max-height: 280px; overflow-y: auto; padding: 6px; display: grid; gap: 2px;
        border: 1px solid var(--line-strong); border-radius: var(--radius-sm);
        background: var(--bg); box-shadow: 0 16px 32px rgba(0, 0, 0, 0.45);
      }
      .emp-picker-list[hidden] { display: none; }
      .emp-picker-option {
        display: flex; justify-content: space-between; gap: 12px; padding: 8px 10px;
        border: 0; border-radius: 6px; background: none; color: var(--text);
        font: inherit; font-size: 14px; text-align: start; cursor: pointer;
      }
      .emp-picker-option .num { color: var(--faint); font-size: 12.5px; }
      .emp-picker-option:hover, .emp-picker-option.is-active { background: var(--surface-2); }
      .emp-picker-note { padding: 8px 10px; color: var(--muted); font-size: 13.5px; }
    `;
    document.head.append(style);
  }

  function employeePicker({ id, excludeIds = [], placeholder } = {}) {
    ensurePickerStyles();
    const listId = `${id}-list`;
    let value = null;
    let options = [];
    let active = -1;
    let timer = null;
    let requestNo = 0;

    const input = h('input', {
      class: 'input', id, type: 'search', autocomplete: 'off',
      role: 'combobox', 'aria-autocomplete': 'list', 'aria-expanded': 'false', 'aria-controls': listId,
      placeholder: placeholder || t('Tape yon non oswa yon nimewo…'),
    });
    const clearBtn = h('button', {
      class: 'emp-picker-clear', type: 'button', hidden: true,
      'aria-label': t('Retire chwa a'), title: t('Retire chwa a'),
    }, '×');
    const list = h('div', { class: 'emp-picker-list', id: listId, role: 'listbox', hidden: true });
    const el = h('div', { class: 'emp-picker' }, input, clearBtn, list);

    function close() {
      list.hidden = true;
      input.setAttribute('aria-expanded', 'false');
      active = -1;
    }

    function setValue(empId, name) {
      value = empId || null;
      input.value = value ? (name || '') : '';
      clearBtn.hidden = !value;
      if (value && name) nameCache.set(value, name);
      close();
    }

    function highlight(i) {
      const buttons = list.querySelectorAll('.emp-picker-option');
      buttons.forEach((b, j) => b.classList.toggle('is-active', j === i));
      active = i;
      if (buttons[i]) buttons[i].scrollIntoView({ block: 'nearest' });
    }

    function showNote(text) {
      list.replaceChildren(h('div', { class: 'emp-picker-note' }, text));
      list.hidden = false;
      input.setAttribute('aria-expanded', 'true');
    }

    async function search() {
      const q = input.value.trim();
      const mine = ++requestNo;
      showNote(t('Ap chèche…'));
      try {
        const params = new URLSearchParams({ size: '20' });
        if (q) params.set('q', q);
        const data = await api.get(`/api/employees?${params}`);
        if (mine !== requestNo) return;          // yon lòt rechèch pi resan deja pati
        options = data.items.filter((e) => !excludeIds.includes(e.id));
        if (!options.length) { showNote(t('Pesonn pa koresponn ak rechèch sa a.')); return; }
        list.replaceChildren(...options.map((e, i) => {
          const name = `${e.first_name} ${e.last_name}`;
          const opt = h('button', {
            class: 'emp-picker-option', type: 'button', role: 'option', tabindex: '-1',
          }, h('span', {}, name), h('span', { class: 'num' }, e.employee_number));
          // mousedown: pase anvan "blur" chan an fèmen lis la.
          opt.addEventListener('mousedown', (ev) => { ev.preventDefault(); setValue(e.id, name); });
          opt.addEventListener('mouseenter', () => highlight(i));
          return opt;
        }));
        list.hidden = false;
        input.setAttribute('aria-expanded', 'true');
        active = -1;
      } catch (err) {
        if (mine === requestNo) showNote(err.message);
      }
    }

    input.addEventListener('input', () => {
      // Moun nan chanje tèks la: chwa anvan an pa valab ankò.
      value = null;
      clearBtn.hidden = true;
      clearTimeout(timer);
      timer = setTimeout(search, 250);
    });
    input.addEventListener('focus', () => { if (!value) search(); });
    input.addEventListener('blur', () => setTimeout(close, 120));
    input.addEventListener('keydown', (ev) => {
      if (list.hidden) return;
      if (ev.key === 'ArrowDown') { ev.preventDefault(); highlight(Math.min(active + 1, options.length - 1)); }
      else if (ev.key === 'ArrowUp') { ev.preventDefault(); highlight(Math.max(active - 1, 0)); }
      else if (ev.key === 'Enter' && active >= 0 && options[active]) {
        ev.preventDefault();
        const e = options[active];
        setValue(e.id, `${e.first_name} ${e.last_name}`);
      } else if (ev.key === 'Escape') { close(); }
    });
    clearBtn.addEventListener('click', () => { setValue(null); input.focus(); });

    return {
      el,
      get value() { return value; },
      set: setValue,
      clear: () => setValue(null),
    };
  }

  Konbit.shell = {
    mount, initials, ADMIN, MANAGERS, employeePicker, employeeNames, cachedName,
  };
})();