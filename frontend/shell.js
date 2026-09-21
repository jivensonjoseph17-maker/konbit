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
 * liy nan NAV anba a epi retire `soon: true`.
 */
(function () {
  'use strict';
  const { api, auth, fmt, h } = Konbit;

  const ADMIN = ['super_admin', 'org_admin', 'hr'];
  const MANAGERS = ['super_admin', 'org_admin', 'hr', 'manager'];

  // `needsEmployee`: paj la sèvi sèlman si kont lan gen yon dosye anplwaye.
  const NAV = [
    { group: null, items: [
      { id: 'dashboard', label: 'Akèy', href: 'dashboard.html' },
    ] },
    { group: 'Jesyon', roles: ADMIN, items: [
      { id: 'employees', label: 'Anplwaye', href: 'employees.html' },
      { id: 'payroll', label: 'Peyòl', href: 'payroll.html' },
      { id: 'leave-admin', label: 'Balans konje', soon: true },
      { id: 'hiring', label: 'Rekritman', soon: true },
      { id: 'training', label: 'Fòmasyon', soon: true },
    ] },
    { group: 'Ekip', roles: ['manager'], items: [
      { id: 'team', label: 'Ekip mwen', soon: true },
    ] },
  ];

  function initials(name) {
    return (name || '?').split(/\s+/).filter(Boolean).slice(0, 2)
      .map((p) => p[0].toUpperCase()).join('');
  }

  function renderSidebar(identity, active) {
    const role = identity.user.role;
    const aside = document.getElementById('sidebar');
    if (!aside) return;

    const groups = NAV
      .filter((g) => !g.roles || g.roles.includes(role))
      .map((g) => h('div', { class: 'nav-group' },
        g.group ? h('p', { class: 'nav-group-label' }, g.group) : null,
        h('ul', { class: 'nav-list' }, ...g.items.map((item) => {
          if (item.soon) {
            return h('li', {},
              h('span', { class: 'nav-item is-soon', 'aria-disabled': 'true' },
                item.label, h('span', { class: 'soon' }, 'byento')),
            );
          }
          const current = item.id === active;
          return h('li', {},
            h('a', {
              class: current ? 'nav-item is-active' : 'nav-item',
              href: item.href,
              'aria-current': current ? 'page' : null,
            }, item.label),
          );
        })),
      ));

    aside.replaceChildren(
      h('a', { class: 'brand sidebar-brand', href: 'dashboard.html', 'aria-label': 'KONMBIT — akèy' },
        h('span', { class: 'brand-mark', 'aria-hidden': 'true' }, 'K'),
        h('span', { class: 'brand-name' }, 'KONMBIT'),
      ),
      h('nav', { 'aria-label': 'Meni aplikasyon an' }, ...groups),
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
      'aria-expanded': 'false',
    }, 'Meni');

    menuBtn.addEventListener('click', () => {
      const open = document.body.classList.toggle('nav-open');
      menuBtn.setAttribute('aria-expanded', String(open));
    });

    const logout = h('button', { class: 'btn btn-quiet btn-sm', type: 'button' }, 'Dekonekte');
    logout.addEventListener('click', () => auth.logout());

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

    renderSidebar(identity, active);
    renderTopbar(identity);
    return identity;
  }

  Konbit.shell = { mount, initials, ADMIN, MANAGERS };
})();