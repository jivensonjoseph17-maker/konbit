/*
 * KONMBIT — kad aplikasyon an (meni sou kote + ba anlè)
 * Chemen: frontend/shell.js
 *
 * Chak paj aplikasyon an chaje api.js, apre sa shell.js, epi li rele:
 *
 *     Konbit.i18n.add([...]);          // tradiksyon paj la (si l genyen)
 *     const identity = await Konbit.shell.mount('employees');
 *
 * Paj la dwe gen: <aside id="sidebar"></aside> ak <header id="topbar"></header>.
 * Meni an chanje dapre wòl moun nan. Pou ajoute yon nouvo paj, ajoute yon
 * liy nan NAV anba a (ak tradiksyon l nan NAV_TRANSLATIONS) epi retire `soon: true`.
 *
 * mount() mete lang kont lan an plas (Konbit.i18n.sync) epi tradui tèks fiks
 * HTML la (data-i18n) ANVAN li retounen — kidonk tout sa paj la rann apre
 * `await mount()` deja nan bon lang lan.
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

  i18n.add([
    // --- Meni ---
    ['Akèy', 'Accueil', 'Home'],
    ['Jesyon', 'Gestion', 'Management'],
    ['Anplwaye|meni', 'Employés', 'Employees'],
    ['Peyòl', 'Paie', 'Payroll'],
    ['Balans konje', 'Soldes de congés', 'Leave balances'],
    ['Rekritman', 'Recrutement', 'Recruiting'],
    ['Fòmasyon', 'Formation', 'Training'],
    ['Ekip', 'Équipe', 'Team'],
    ['Ekip mwen', 'Mon équipe', 'My team'],
    ['Tan travay', 'Temps de travail', 'Timesheets'],
    ['byento', 'bientôt', 'soon'],

    // --- Kad la ---
    ['KONMBIT — akèy', 'KONMBIT — accueil', 'KONMBIT — home'],
    ['Meni aplikasyon an', "Menu de l'application", 'App menu'],
    ['Meni', 'Menu', 'Menu'],
    ['Dekonekte', 'Se déconnecter', 'Log out'],
  ]);

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
    const langSelect = i18n.switcher();
    langSelect.style.width = 'auto';
    langSelect.style.minWidth = '0';

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
        langSelect,
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

    // Lang kont lan, epi tèks fiks HTML la (ak tradiksyon paj la te ajoute).
    await i18n.sync(identity.user.preferred_language);
    i18n.apply(document);

    applySidebarState();
    renderSidebar(identity, active);
    renderTopbar(identity);
    return identity;
  }

  Konbit.shell = { mount, initials, ADMIN, MANAGERS };
})();