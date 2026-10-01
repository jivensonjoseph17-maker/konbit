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
 * Yon liy ka gen pwòp `roles` li (pi sere pase gwoup la).
 *
 * mount() tann tradiksyon yo, mete lang kont lan an plas (Konbit.i18n.sync)
 * epi tradui tèks fiks HTML la (data-i18n) ANVAN li retounen — kidonk tout
 * sa paj la rann apre `await mount()` deja nan bon lang lan.
 */
(function () {
  'use strict';
  const { api, auth, fmt, h, i18n, t, theme } = Konbit;

  const ADMIN = ['super_admin', 'org_admin', 'hr'];
  const OWNERS = ['super_admin', 'org_admin'];
  const MANAGERS = ['super_admin', 'org_admin', 'hr', 'manager'];
  // Menm lis ak backend la (deps.MFA_REQUIRED_ROLES).
  const MFA_REQUIRED = ['super_admin', 'org_admin', 'hr'];

  // `needsEmployee`: paj la sèvi sèlman si kont lan gen yon dosye anplwaye.
  // Label yo se kle tradiksyon (tèks kreyòl la). '|meni' separe "Anplwaye"
  // nan meni an (Employés) ak wòl "Anplwaye" (Employé).
  const NAV = [
    { group: null, items: [
      { id: 'dashboard', label: 'Akèy', href: 'dashboard.html' },
      { id: 'organigram', label: 'Òganigram', href: 'organigram.html' },
    ] },
    { group: 'Jesyon', roles: ADMIN, items: [
      { id: 'admin', label: 'Tablo jesyon', href: 'admin.html' },
      { id: 'employees', label: 'Anplwaye|meni', href: 'employees.html' },
      { id: 'employee-import', label: 'Enpòte anplwaye', href: 'employees-import.html' },
      { id: 'positions', label: 'Pozisyon', href: 'positions.html' },
      { id: 'payroll', label: 'Pewòl', href: 'payroll.html' },
      { id: 'leave-admin', label: 'Balans konje', href: 'leave-balances.html' },
      { id: 'payment-changes', label: 'Chanjman peman', href: 'payment-changes.html' },
      { id: 'hiring', label: 'Rekritman', href: 'jobs.html' },
      { id: 'training', label: 'Fòmasyon', href: 'training.html' },
      // Sèlman administratè biznis la (backend: require_admin).
      { id: 'kiosk', label: 'Pwentaj ak tablèt', href: 'kiosk-settings.html', roles: OWNERS },
      { id: 'settings', label: 'Paramèt biznis', href: 'settings.html', roles: OWNERS },
      { id: 'audit', label: 'Jounal odit', href: 'audit.html', roles: OWNERS },
    ] },
    { group: 'Ekip', roles: MANAGERS, items: [
      { id: 'team', label: 'Ekip mwen', href: 'team.html' },
      { id: 'timesheets', label: 'Tan travay', href: 'timesheets.html' },
      { id: 'salary-advances', label: 'Avans sou salè', href: 'salary-advances.html' },
      { id: 'schedule', label: 'Orè', href: 'schedule.html' },
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
        h('ul', { class: 'nav-list' }, ...g.items
          .filter((item) => !item.roles || item.roles.includes(role))
          .map((item) => {
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

  // -------------------------------------------------------------------------
  // LOGO BIZNIS LA (lyen ki nan Paramèt biznis). Imaj la parèt sèlman lè l
  // fin chaje; si lyen an kase, non biznis la rete pou kont li. Pa gen
  // "Referer": sit logo a pa konnen ki paj moun nan te sou li.
  // -------------------------------------------------------------------------

  function ensureLogoStyles() {
    if (document.getElementById('konbit-org-logo-css')) return;
    const style = document.createElement('style');
    style.id = 'konbit-org-logo-css';
    style.textContent = `
      .topbar-org { display: inline-flex; align-items: center; gap: 10px; min-width: 0; }
      .topbar-logo {
        height: 30px; width: auto; max-width: 110px; object-fit: contain; flex: none;
        padding: 3px; border-radius: 7px; background: #fff;
      }
    `;
    document.head.append(style);
  }

  /** <img> logo a, oswa null si lyen an pa http(s). */
  function orgLogo(url, cls) {
    if (!url) return null;
    let src = null;
    try {
      // "/api/logos/…" (fichye a) → adrès API a devan; yon lyen https rete jan l ye.
      const u = new URL(url, Konbit.API_URL);
      if (u.protocol === 'https:' || u.protocol === 'http:') src = u.href;
    } catch {
      return null;
    }
    if (!src) return null;
    ensureLogoStyles();
    const img = h('img', { class: cls || '', src, decoding: 'async' });
    img.alt = '';
    img.referrerPolicy = 'no-referrer';
    img.hidden = true;
    img.addEventListener('load', () => { img.hidden = false; });
    img.addEventListener('error', () => img.remove());
    return img;
  }

  // -------------------------------------------------------------------------
  // KLÒCH NOTIFIKASYON — ti chif wouj + 20 dènye yo (routers/notifications.py)
  // -------------------------------------------------------------------------

  function ensureBellStyles() {
    if (document.getElementById('konbit-bell-css')) return;
    const style = document.createElement('style');
    style.id = 'konbit-bell-css';
    style.textContent = `
      .bell { position: relative; }
      .bell-btn { position: relative; display: inline-flex; align-items: center; justify-content: center; }
      .bell-btn svg { width: 18px; height: 18px; }
      .bell-count {
        position: absolute; top: -4px; inset-inline-end: -4px; min-width: 18px; height: 18px; padding: 0 5px;
        border-radius: 999px; background: #e5484d; color: #fff; font-size: 11px; font-weight: 700;
        display: inline-flex; align-items: center; justify-content: center; line-height: 1;
      }
      .bell-count[hidden] { display: none; }
      .bell-panel {
        position: absolute; top: calc(100% + 8px); inset-inline-end: 0; z-index: 80;
        width: min(380px, 92vw); max-height: 440px; overflow-y: auto;
        background: var(--surface); color: var(--text); border: 1px solid var(--line-strong, var(--line));
        border-radius: 14px; box-shadow: var(--shadow, 0 12px 32px rgba(15, 23, 42, 0.18));
      }
      .bell-panel[hidden] { display: none; }
      .bell-head {
        position: sticky; top: 0; display: flex; justify-content: space-between; align-items: center; gap: 8px;
        padding: 12px 14px; border-bottom: 1px solid var(--line); background: var(--surface);
      }
      .bell-item {
        display: block; padding: 12px 14px; border-bottom: 1px solid var(--line);
        color: inherit; text-decoration: none; cursor: default;
      }
      a.bell-item { cursor: pointer; }
      a.bell-item:hover, a.bell-item:focus-visible { background: var(--surface-2, rgba(148, 163, 184, 0.12)); }
      .bell-item.is-unread { box-shadow: inset 3px 0 0 var(--accent, #2563eb); }
      .bell-item.is-unread .bell-title { font-weight: 700; }
      .bell-title { font-size: 14px; }
      .bell-body { font-size: 13px; color: var(--muted); margin-top: 3px; }
      .bell-time { font-size: 12px; color: var(--faint, var(--muted)); margin-top: 4px; }
      .bell-empty { padding: 18px 14px; color: var(--muted); font-size: 14px; margin: 0; }
    `;
    document.head.append(style);
  }

  function bellIcon() {
    const NS = 'http://www.w3.org/2000/svg';
    const svg = document.createElementNS(NS, 'svg');
    for (const [k, v] of Object.entries({
      viewBox: '0 0 24 24', fill: 'none', stroke: 'currentColor', 'stroke-width': '1.8',
      'stroke-linecap': 'round', 'stroke-linejoin': 'round', 'aria-hidden': 'true',
    })) svg.setAttribute(k, v);
    for (const d of ['M6 8a6 6 0 1 1 12 0c0 7 3 9 3 9H3s3-2 3-9', 'M10.3 21a1.94 1.94 0 0 0 3.4 0']) {
      const path = document.createElementNS(NS, 'path');
      path.setAttribute('d', d);
      svg.append(path);
    }
    return svg;
  }

  /** Lyen yon notifikasyon: sèlman yon paj .html KONMBIT; sinon pa gen lyen. */
  function safeNotifLink(link) {
    const s = String(link || '').replace(/^\/+/, '');
    if (/^[a-z0-9-]+\.html(#[a-z0-9-]+)?$/i.test(s)) return s;
    if (/^payslips\/\d+$/.test(s)) return 'dashboard.html#fich-peye';
    const course = s.match(/^training\/(\d+)$/);
    if (course) return `my-course.html?id=${course[1]}`;
    if (/^leaves\/\d+$/.test(s)) return 'dashboard.html#konje';
    return null;
  }

  function notifBell() {
    ensureBellStyles();
    const count = h('span', { class: 'bell-count', hidden: true });
    const btn = h('button', {
      class: 'btn btn-ghost btn-sm bell-btn', type: 'button',
      'aria-haspopup': 'true', 'aria-expanded': 'false', title: t('Notifikasyon'),
    }, bellIcon(), count);
    const list = h('div', {});
    const readAll = h('button', { class: 'btn btn-quiet btn-sm', type: 'button' }, t('Make tout kòm li'));
    const panel = h('div', { class: 'bell-panel', hidden: true, role: 'dialog', 'aria-label': t('Notifikasyon') },
      h('div', { class: 'bell-head' }, h('strong', {}, t('Notifikasyon')), readAll), list);
    const wrap = h('div', { class: 'bell' }, btn, panel);

    function setCount(n) {
      count.hidden = !n;
      count.textContent = n > 99 ? '99+' : String(n);
      btn.setAttribute('aria-label', n ? t('{n} notifikasyon ou poko li', { n }) : t('Notifikasyon'));
      readAll.hidden = !n;
    }

    async function refreshCount() {
      try {
        setCount((await api.get('/api/notifications/count')).unread);
      } catch {
        // Pa grav: klòch la ap eseye ankò pita.
      }
    }

    function item(n) {
      const href = safeNotifLink(n.link_url);
      // Tit ak tèks yo ekri an kreyòl pa sistèm nan: nou montre yo jan yo ye.
      const el = h(href ? 'a' : 'div', { class: n.is_read ? 'bell-item' : 'bell-item is-unread', href },
        h('div', { class: 'bell-title' }, n.title),
        n.body ? h('div', { class: 'bell-body' }, n.body) : null,
        h('div', { class: 'bell-time' }, fmt.dateTime(n.created_at)));
      el.addEventListener('click', async (e) => {
        if (n.is_read) return;
        if (href) e.preventDefault();
        try { await api.post(`/api/notifications/${n.id}/read`, {}); } catch { /* ale kanmenm */ }
        if (href) location.href = href;
        else { n.is_read = true; el.classList.remove('is-unread'); refreshCount(); }
      });
      return el;
    }

    async function loadList() {
      list.replaceChildren(h('p', { class: 'bell-empty' }, t('Ap chaje…')));
      try {
        const data = await api.get('/api/notifications?limit=20');
        setCount(data.unread);
        list.replaceChildren(...(data.items.length
          ? data.items.map(item)
          : [h('p', { class: 'bell-empty' }, t('Ou pa gen notifikasyon.'))]));
      } catch (err) {
        list.replaceChildren(h('p', { class: 'bell-empty' }, err.message));
      }
    }

    function open(show) {
      panel.hidden = !show;
      btn.setAttribute('aria-expanded', String(show));
      if (show) loadList();
    }

    btn.addEventListener('click', (e) => { e.stopPropagation(); open(panel.hidden); });
    readAll.addEventListener('click', async () => {
      readAll.disabled = true;
      try { await api.post('/api/notifications/read-all', {}); } catch { /* lis la ap montre verite a */ }
      readAll.disabled = false;
      loadList();
    });
    document.addEventListener('click', (e) => { if (!panel.hidden && !wrap.contains(e.target)) open(false); });
    document.addEventListener('keydown', (e) => { if (e.key === 'Escape' && !panel.hidden) { open(false); btn.focus(); } });
    // Chak 2 minit, sèlman lè paj la vizib (pa gaspiye batri telefòn nan).
    setInterval(() => { if (!document.hidden) refreshCount(); }, 120000);
    document.addEventListener('visibilitychange', () => { if (!document.hidden) refreshCount(); });

    refreshCount();
    return wrap;
  }

  // -------------------------------------------------------------------------
  // FOTO PWOFIL (routers/employee_photos.py)
  // -------------------------------------------------------------------------

  /** Avatar: foto a si genyen youn (lyen relatif ak API a), sinon inisyal yo. */
  function avatar(url, name, extraClass) {
    const el = h('span', { class: extraClass ? `avatar ${extraClass}` : 'avatar', 'aria-hidden': 'true' },
      initials(name));
    if (url) {
      let src = null;
      try {
        const u = new URL(url, Konbit.API_URL);
        if (u.protocol === 'https:' || u.protocol === 'http:') src = u.href;
      } catch {
        src = null;
      }
      if (src) {
        const img = h('img', { src, decoding: 'async' });
        img.alt = '';
        img.referrerPolicy = 'no-referrer';
        img.addEventListener('load', () => el.replaceChildren(img));
      }
    }
    return el;
  }

  let photoMapPromise = null;

  /** {employee_id: lyen foto} pou tout biznis la; yon sèl rekèt pa paj. */
  function photoMap(force) {
    if (!photoMapPromise || force) {
      photoMapPromise = api.get('/api/photos/map').then((d) => d.photos).catch(() => ({}));
    }
    return photoMapPromise;
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
        h('span', { class: 'topbar-org' },
          orgLogo(identity.organization_logo_url, 'topbar-logo'),
          identity.organization_name || ''),
      ),
      h('div', { class: 'topbar-user' },
        h('div', { class: 'user-chip' },
          h('div', { class: 'name' }, user.full_name),
          h('div', { class: 'role' }, fmt.role(user.role)),
          h('a', { class: 'role plain-link', href: 'password.html' }, t('Chanje modpas')),
          h('a', { class: 'role plain-link', href: 'security.html' }, t('Verifikasyon 2 etap')),
        ),
        avatar(identity.photo_url, user.full_name),
        notifBell(),
        theme.button(),
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

  // -------------------------------------------------------------------------
  // TI CHIF WOUJ BÒ KOTE "EKIP MWEN" — konje + èdtan k ap tann manadjè a
  // -------------------------------------------------------------------------

  function ensureBadgeStyles() {
    if (document.getElementById('konbit-nav-badge-css')) return;
    const style = document.createElement('style');
    style.id = 'konbit-nav-badge-css';
    style.textContent = `
      .nav-item:has(.nav-badge) { display: flex; align-items: center; gap: 8px; }
      .nav-badge {
        margin-inline-start: auto; min-width: 20px; height: 20px; padding: 0 6px; border-radius: 999px;
        display: inline-flex; align-items: center; justify-content: center;
        background: #e5484d; color: #fff; font-size: 12px; font-weight: 700; line-height: 1;
      }
    `;
    document.head.append(style);
  }

  let currentRole = null;

  /** Mete ajou ti chif la. Paj Ekip mwen rele sa apre yon apwobasyon. */
  async function refreshInboxBadge() {
    if (!MANAGERS.includes(currentRole)) return;
    const link = document.querySelector('#sidebar a[href="team.html"]');
    if (!link) return;
    try {
      const c = await api.get('/api/team/inbox-count');
      ensureBadgeStyles();
      let badge = link.querySelector('.nav-badge');
      if (!c.total) {
        if (badge) badge.remove();
        return;
      }
      if (!badge) {
        badge = h('span', { class: 'nav-badge' });
        link.append(badge);
      }
      badge.textContent = c.total > 99 ? '99+' : String(c.total);
      badge.setAttribute('aria-label', t('{n} bagay k ap tann ou', { n: c.total }));
    } catch {
      // Pa grav: meni an mache san chif la.
    }
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

    // Kont kandida (paj karyè): li pa fè pati okenn biznis — espas pa l se candidate.html.
    if (identity.user.role === 'applicant') {
      location.replace('candidate.html');
      return null;
    }

    // Admin ak HR: verifikasyon an 2 etap obligatwa (backend: deps.ENFORCE_MFA).
    if (MFA_REQUIRED.includes(identity.user.role) && !identity.user.totp_enabled && active !== 'security') {
      location.replace('security.html');
      return null;
    }

    if (allowedRoles && !allowedRoles.includes(identity.user.role)) {
      location.replace('dashboard.html');
      return null;
    }

    // Modpas tanporè: moun nan dwe chwazi pa l anvan li fè anyen.
    if (identity.user.must_change_password) {
      location.replace('password.html');
      return null;
    }

    // Lang kont lan, epi tèks fiks HTML la.
    await i18n.sync(identity.user.preferred_language);
    i18n.apply(document);

    applySidebarState();
    renderSidebar(identity, active);
    renderTopbar(identity);
    currentRole = identity.user.role;
    refreshInboxBadge();
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
        background: var(--input-bg, var(--bg)); box-shadow: var(--shadow);
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
    mount, initials, ADMIN, OWNERS, MANAGERS, employeePicker, employeeNames, cachedName,
    refreshInboxBadge, orgLogo, avatar, photoMap,
  };
})();