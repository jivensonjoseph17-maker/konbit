/*
 * Konbit — kliyan API
 * Chemen: frontend/api.js
 *
 * Tout paj aplikasyon an pase pa fichye sa a pou pale ak backend la.
 * Li jere: token nan chak rekèt, refresh otomatik lè li ekspire,
 * erè an kreyòl, ak fòma lajan / dat / èdtan.
 *
 * Sèvi avè l konsa nan yon paj:
 *     <script src="api.js"></script>
 *     const me = await Konbit.api.get('/api/auth/identity');
 */
(function () {
  'use strict';

  // Chanje sa pou pwodiksyon, oswa defini window.KONBIT_API_URL anvan fichye sa a.
  const API_URL = window.KONBIT_API_URL || 'http://localhost:8000';

  const KEYS = {
    access: 'konbit.access_token',
    refresh: 'konbit.refresh_token',
  };

  // -------------------------------------------------------------------------
  // ERÈ
  // -------------------------------------------------------------------------

  class ApiError extends Error {
    constructor(status, message, fields) {
      super(message);
      this.name = 'ApiError';
      this.status = status;
      this.fields = fields || [];   // [{field, message}] pou erè validasyon
    }
  }

  function defaultMessage(status) {
    if (status === 0) return 'Nou pa ka rive jwenn sèvè a. Verifye koneksyon entènèt ou.';
    if (status === 401) return 'Sesyon w lan fini. Konekte ankò.';
    if (status === 403) return 'Ou pa gen dwa pou aksyon sa a.';
    if (status === 404) return 'Sa ou chèche a pa egziste.';
    if (status === 409) return 'Gen yon konfli ak done ki deja la.';
    if (status === 422) return 'Kèk enfòmasyon pa valab.';
    if (status >= 500) return 'Sèvè a gen yon pwoblèm. Eseye ankò nan kèk minit.';
    return 'Yon bagay pa mache.';
  }

  function toApiError(status, body) {
    if (!body) return new ApiError(status, defaultMessage(status));

    let message = body.detail;
    // Backend la ka voye yon lis mesaj (egz: règ modpas yo)
    if (Array.isArray(message)) message = message.join(' ');
    if (typeof message !== 'string' || !message) message = defaultMessage(status);

    return new ApiError(status, message, body.errors);
  }

  // -------------------------------------------------------------------------
  // TOKEN
  //
  // Nou estoke token yo nan localStorage. Sa pratik men li gen yon limit:
  // si yon atakè rive egzekite JavaScript sou paj la (XSS), li ka li yo.
  // Se poutèt sa kòd sa a pa janm sèvi ak innerHTML ak done ki soti nan API.
  // Pi devan, cookie httpOnly t ap pi solid.
  // -------------------------------------------------------------------------

  const tokens = {
    get access() {
      try { return localStorage.getItem(KEYS.access); } catch { return null; }
    },
    get refresh() {
      try { return localStorage.getItem(KEYS.refresh); } catch { return null; }
    },
    save(access, refresh) {
      try {
        localStorage.setItem(KEYS.access, access);
        if (refresh) localStorage.setItem(KEYS.refresh, refresh);
      } catch { /* navigasyon prive — sesyon an ap dire jouk paj la fèmen */ }
    },
    clear() {
      try {
        localStorage.removeItem(KEYS.access);
        localStorage.removeItem(KEYS.refresh);
      } catch { /* anyen pou fè */ }
    },
  };

  // Si plizyè rekèt resevwa 401 an menm tan, nou fè YON SÈL refresh.
  let refreshInFlight = null;

  function refreshTokens() {
    if (refreshInFlight) return refreshInFlight;
    const refreshToken = tokens.refresh;
    if (!refreshToken) return Promise.resolve(false);

    refreshInFlight = (async () => {
      try {
        const res = await fetch(`${API_URL}/api/auth/refresh`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ refresh_token: refreshToken }),
        });
        if (!res.ok) return false;
        const data = await res.json();
        tokens.save(data.access_token, data.refresh_token);
        return true;
      } catch {
        return false;
      } finally {
        refreshInFlight = null;
      }
    })();

    return refreshInFlight;
  }

  function goToLogin() {
    if (location.pathname.endsWith('login.html')) return;
    const next = encodeURIComponent(location.pathname.split('/').pop() || 'dashboard.html');
    location.href = `login.html?next=${next}`;
  }

  // -------------------------------------------------------------------------
  // REKÈT
  // -------------------------------------------------------------------------

  async function request(method, path, { body, auth = true, retried = false } = {}) {
    const headers = { Accept: 'application/json' };
    if (body !== undefined) headers['Content-Type'] = 'application/json';
    if (auth && tokens.access) headers.Authorization = `Bearer ${tokens.access}`;

    let res;
    try {
      res = await fetch(API_URL + path, {
        method,
        headers,
        body: body !== undefined ? JSON.stringify(body) : undefined,
      });
    } catch {
      // fetch voye yon erè sèlman lè rezo a pa reponn ditou — oswa CORS bloke l.
      throw new ApiError(0, defaultMessage(0));
    }

    if (res.status === 401 && auth && !retried) {
      if (await refreshTokens()) {
        return request(method, path, { body, auth, retried: true });
      }
      tokens.clear();
      goToLogin();
      throw new ApiError(401, defaultMessage(401));
    }

    const text = await res.text();
    let data = null;
    if (text) {
      try { data = JSON.parse(text); } catch { data = null; }
    }

    if (!res.ok) throw toApiError(res.status, data);
    return data;
  }

  const api = {
    get: (path, opts) => request('GET', path, opts),
    post: (path, body, opts) => request('POST', path, { ...opts, body: body ?? {} }),
    patch: (path, body, opts) => request('PATCH', path, { ...opts, body: body ?? {} }),
    put: (path, body, opts) => request('PUT', path, { ...opts, body: body ?? {} }),
    del: (path, opts) => request('DELETE', path, opts),
  };

  // -------------------------------------------------------------------------
  // OTANTIFIKASYON
  // -------------------------------------------------------------------------

  const auth = {
    isLoggedIn() {
      return Boolean(tokens.access);
    },

    async login(email, password) {
      const data = await api.post('/api/auth/login', { email, password }, { auth: false });
      tokens.save(data.access_token, data.refresh_token);
      return data;
    },

    async signup(payload) {
      const data = await api.post('/api/auth/signup', payload, { auth: false });
      tokens.save(data.access_token, data.refresh_token);
      return data;
    },

    async logout() {
      try { await api.post('/api/auth/logout'); } catch { /* token deja ekspire: pa grav */ }
      tokens.clear();
      location.href = 'login.html';
    },

    /** Rele sa anlè chak paj ki mande koneksyon. */
    requireLogin() {
      if (!tokens.access) {
        goToLogin();
        return false;
      }
      return true;
    },
  };

  // -------------------------------------------------------------------------
  // FÒMA
  // -------------------------------------------------------------------------

  const numberFmt = new Intl.NumberFormat('fr-FR', {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });

  const fmt = {
    /** 4500000 → "45 000,00 HTG". Tout montan nan API a an santim. */
    money(cents, currency = 'HTG') {
      if (cents === null || cents === undefined) return '—';
      return `${numberFmt.format(cents / 100)} ${currency}`;
    },

    /**
     * SQLite retounen dat san fizo orè ("2026-09-20T19:53:59").
     * JavaScript ta li sa kòm lè LOKAL — sa ta mete tout minitè yo 4è an reta
     * an Ayiti. Backend la toujou ekri an UTC, donk nou ajoute 'Z' si l manke.
     */
    parseDate(value) {
      if (!value) return null;
      if (value instanceof Date) return value;
      const hasZone = /[zZ]$|[+-]\d{2}:?\d{2}$/.test(value);
      const isDateOnly = /^\d{4}-\d{2}-\d{2}$/.test(value);
      if (isDateOnly) return new Date(`${value}T00:00:00`);
      return new Date(hasZone ? value : `${value}Z`);
    },

    date(value) {
      const d = fmt.parseDate(value);
      if (!d || isNaN(d)) return '—';
      return d.toLocaleDateString('fr-FR', { day: 'numeric', month: 'long', year: 'numeric' });
    },

    shortDate(value) {
      const d = fmt.parseDate(value);
      if (!d || isNaN(d)) return '—';
      return d.toLocaleDateString('fr-FR', { day: 'numeric', month: 'short' });
    },

    time(value) {
      const d = fmt.parseDate(value);
      if (!d || isNaN(d)) return '—';
      return d.toLocaleTimeString('fr-FR', { hour: '2-digit', minute: '2-digit' });
    },

    /**
     * Sa moun nan tape → santim. "45 000" → 4500000, "1500,50" → 150050.
     * Aksepte vigil oswa pwen pou desimal, ak espas pou milye.
     * Retounen null si sa pa yon chif.
     */
    parseMoney(input) {
      const clean = String(input ?? '').replace(/\s/g, '').replace(/[^\d.,]/g, '');
      if (!clean) return null;
      const lastSep = Math.max(clean.lastIndexOf(','), clean.lastIndexOf('.'));
      let normalized = clean;
      if (lastSep !== -1) {
        const decimals = clean.slice(lastSep + 1);
        // 1-2 chif apre dènye separatè a = desimal; 3 chif = milye ("45.000")
        normalized = decimals.length <= 2
          ? clean.slice(0, lastSep).replace(/[.,]/g, '') + '.' + decimals
          : clean.replace(/[.,]/g, '');
      }
      const n = Number(normalized);
      return Number.isFinite(n) && n >= 0 ? Math.round(n * 100) : null;
    },

    employmentStatus(s) {
      return {
        active: 'Aktif',
        on_leave: 'An konje',
        suspended: 'Sispann',
        terminated: 'Pa nan biznis la ankò',
      }[s] || s;
    },

    /** 450 → "7è 30min" */
    duration(minutes) {
      if (minutes === null || minutes === undefined) return '—';
      const h = Math.floor(minutes / 60);
      const m = Math.round(minutes % 60);
      if (h === 0) return `${m}min`;
      return m === 0 ? `${h}è` : `${h}è ${m}min`;
    },

    /** Segonn → "02:14:07" pou minitè a */
    clock(totalSeconds) {
      const s = Math.max(0, Math.floor(totalSeconds));
      const h = String(Math.floor(s / 3600)).padStart(2, '0');
      const m = String(Math.floor((s % 3600) / 60)).padStart(2, '0');
      const sec = String(s % 60).padStart(2, '0');
      return `${h}:${m}:${sec}`;
    },

    /** Kijan anplwaye a resevwa lajan l — sa te youn nan premye egzijans yo. */
    paymentMethod(slip) {
      const m = slip.payment_method;
      if (m === 'check') {
        return slip.check_number ? `Chèk nimewo ${slip.check_number}` : 'Chèk';
      }
      if (m === 'direct_deposit') {
        let label = 'Depo dirèk';
        if (slip.bank_name) label += ` — ${slip.bank_name}`;
        if (slip.account_last4) label += ` (kont ••${slip.account_last4})`;
        return label;
      }
      if (m === 'moncash') return 'MonCash';
      if (m === 'natcash') return 'NatCash';
      if (m === 'cash') return 'Lajan kach';
      return m || '—';
    },

    leaveType(t) {
      return {
        vacation: 'Vakans',
        sick: 'Maladi',
        maternity: 'Matènite',
        paternity: 'Patènite',
        bereavement: 'Lanmò nan fanmi',
        unpaid: 'San peye',
        other: 'Lòt',
      }[t] || t;
    },

    requestStatus(s) {
      return {
        pending: 'Ap tann',
        approved: 'Apwouve',
        rejected: 'Refize',
        cancelled: 'Anile',
      }[s] || s;
    },

    role(r) {
      return {
        super_admin: 'Administratè Konbit',
        org_admin: 'Administratè',
        hr: 'Resous imèn',
        manager: 'Manadjè',
        employee: 'Anplwaye',
        applicant: 'Kandida',
      }[r] || r;
    },
  };

  // -------------------------------------------------------------------------
  // DOM — kreye eleman san innerHTML
  // -------------------------------------------------------------------------

  /**
   * h('div', {class: 'card'}, 'tèks', h('span', {}, 'lòt'))
   * Tèks yo toujou antre kòm textContent — pa gen risk XSS.
   */
  function h(tag, attrs, ...children) {
    const el = document.createElement(tag);
    for (const [key, value] of Object.entries(attrs || {})) {
      if (value === null || value === undefined || value === false) continue;
      if (key === 'class') el.className = value;
      else if (key.startsWith('on') && typeof value === 'function') {
        el.addEventListener(key.slice(2).toLowerCase(), value);
      } else if (key === 'dataset') {
        Object.assign(el.dataset, value);
      } else if (value === true) {
        el.setAttribute(key, '');
      } else {
        el.setAttribute(key, value);
      }
    }
    for (const child of children.flat()) {
      if (child === null || child === undefined || child === false) continue;
      el.append(child instanceof Node ? child : document.createTextNode(String(child)));
    }
    return el;
  }

  window.Konbit = { API_URL, api, auth, fmt, h, ApiError };
})();