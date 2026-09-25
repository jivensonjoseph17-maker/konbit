/*
 * Konbit — kliyan API
 * Chemen: frontend/api.js
 *
 * Tout paj aplikasyon an pase nan fichye sa a pou pale ak backend la.
 * Li jere: lang (kreyòl / franse / angle), token nan chak rekèt, refresh
 * otomatik lè li ekspire, erè, ak fòma lajan / dat / èdtan.
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
    lang: 'konbit.lang',
    langPending: 'konbit.lang_pending',
  };

  // =========================================================================
  // LANG (i18n)
  //
  // Tèks yo ekri an KREYÒL nan kòd la, epi tèks kreyòl la sèvi kòm KLE:
  //
  //     t('Ap chaje…')                  → "Chargement…" an franse
  //     t('Bonjou, {name}', {name})     → valè yo ranplase {name}
  //     t('Anile|aksyon')               → pati apre | a se KONTÈKS: li separe
  //                                       "Anile" (estati: Annulé) ak
  //                                       "Anile" (bouton: Annuler). An kreyòl
  //                                       sèlman pati anvan | a parèt.
  //
  // Tradiksyon yo nan frontend/i18n/<kòd>.json: { "tèks kreyòl": "tradiksyon" }.
  // Paj la chaje SÈLMAN lang moun nan chwazi a (+ angle kòm rezèv).
  // Si yon fraz manke: angle, epi si l manke an angle tou: kreyòl.
  // Pou verifye sa ki manke:  python frontend/i18n/check_i18n.py
  //
  // Paj ki pa sèvi ak shell.js (login, karyè, akèy) dwe tann:
  //     await Konbit.i18n.ready;
  // shell.mount() fè sa pou lòt paj yo.
  //
  // Tèks fiks nan HTML la:
  //     <h1 data-i18n>Balans konje</h1>
  //     <input data-i18n-attr="placeholder aria-label" placeholder="Chèche…">
  // `data-i18n` sèlman sou yon eleman ki gen TÈKS SÈLMAN (pa lòt eleman
  // anndan l) — sinon mete tèks la nan yon <span data-i18n>.
  //
  // POU AJOUTE YON LANG: mete fichye i18n/<kòd>.json la, epi yon liy nan LANGS.
  // =========================================================================

  // `locale`: pou dat ak chif (Intl). `-u-nu-latn` = chif 0-9 nòmal, menm an
  // arab oswa bengali — sa enpòtan pou montan peyòl yo.
  const LANGS = [
    { code: 'ht', label: 'Kreyòl ayisyen', locale: 'fr-FR' },
    { code: 'fr', label: 'Français', locale: 'fr-FR' },
    { code: 'en', label: 'English', locale: 'en-US' },
    { code: 'es', label: 'Español', locale: 'es-ES' },
    // Pwochen lang yo (fichye yo ap vini youn apre lòt):
    // pt Português · zh 中文 · ar العربية · hi हिन्दी · bn বাংলা · ru Русский
    // ja 日本語 · de Deutsch · it Italiano · ko 한국어 · tr Türkçe · vi Tiếng Việt
    // id Bahasa Indonesia · sw Kiswahili · nl Nederlands · pl Polski
  ];
  const RTL = new Set(['ar', 'ur', 'fa', 'he']);
  const DEFAULT_LANG = 'ht';
  const FALLBACK_LANG = 'en';
  const langInfo = (code) => LANGS.find((l) => l.code === code);
  const isSupported = (code) => Boolean(langInfo(code));

  // Kote fichye tradiksyon yo ye: bò kote api.js, nan dosye i18n/.
  const I18N_BASE = (() => {
    try {
      return new URL('i18n/', document.currentScript.src).href;
    } catch {
      return 'i18n/';
    }
  })();

  const DICT = Object.create(null);          // { fr: {...}, en: {...} }
  const missingKeys = new Set();
  const isDev = ['127.0.0.1', 'localhost'].includes(location.hostname);

  function storageGet(key) {
    try { return localStorage.getItem(key); } catch { return null; }
  }
  function storageSet(key, value) {
    try { localStorage.setItem(key, value); return true; } catch { return false; }
  }
  function storageRemove(key) {
    try { localStorage.removeItem(key); } catch { /* anyen pou fè */ }
  }

  /** ?lang=fr nan URL la (pou lyen paj karyè a), sinon chwa sove a, sinon kreyòl. */
  function initialLang() {
    const fromUrl = new URLSearchParams(location.search).get('lang');
    if (fromUrl && isSupported(fromUrl)) {
      storageSet(KEYS.lang, fromUrl);
      return fromUrl;
    }
    const saved = storageGet(KEYS.lang);
    return saved && isSupported(saved) ? saved : DEFAULT_LANG;
  }

  let lang = initialLang();

  function applyDocumentLang() {
    document.documentElement.lang = lang;
    document.documentElement.dir = RTL.has(lang) ? 'rtl' : 'ltr';
  }
  applyDocumentLang();

  /** Chaje yon fichye lang yon sèl fwa. Si l echwe, paj la kontinye san li. */
  const loading = Object.create(null);
  function loadDict(code) {
    if (code === DEFAULT_LANG || DICT[code]) return Promise.resolve();
    if (!loading[code]) {
      loading[code] = fetch(`${I18N_BASE}${code}.json`, { cache: 'no-cache' })
        .then((res) => (res.ok ? res.json() : Promise.reject(new Error(`HTTP ${res.status}`))))
        .then((data) => { DICT[code] = data; })
        .catch((err) => {
          console.warn(`[i18n] nou pa t ka chaje ${code}.json:`, err.message);
          DICT[code] = Object.create(null);
        });
    }
    return loading[code];
  }

  function loadLang(code) {
    if (code === DEFAULT_LANG) return Promise.resolve();
    return Promise.all([loadDict(code), loadDict(FALLBACK_LANG)]);
  }

  function t(key, vars) {
    let text = key.split('|')[0];
    if (lang !== DEFAULT_LANG) {
      const own = DICT[lang] && DICT[lang][key];
      const fallback = DICT[FALLBACK_LANG] && DICT[FALLBACK_LANG][key];
      if (own) {
        text = own;
      } else {
        if (fallback) text = fallback;
        if (isDev && !missingKeys.has(`${lang}:${key}`)) {
          missingKeys.add(`${lang}:${key}`);
          console.debug(`[i18n] ${lang} manke: "${key}"`);
        }
      }
    }
    if (vars) {
      text = text.replace(/\{(\w+)\}/g, (m, name) => (name in vars ? String(vars[name]) : m));
    }
    return text;
  }

  const camel = (attr) => attr.replace(/-(\w)/g, (m, c) => c.toUpperCase());

  /** Tradui tèks fiks HTML la (data-i18n, data-i18n-attr). Ka rele plizyè fwa. */
  function applyTranslations(root = document) {
    root.querySelectorAll('[data-i18n]').forEach((el) => {
      if (el.children.length) {
        if (isDev) console.warn('[i18n] data-i18n sou yon eleman ki gen lòt eleman ladan:', el);
        return;
      }
      if (el.dataset.i18nKey === undefined) {
        el.dataset.i18nKey = el.getAttribute('data-i18n') || el.textContent.trim();
      }
      el.textContent = t(el.dataset.i18nKey);
    });

    root.querySelectorAll('[data-i18n-attr]').forEach((el) => {
      for (const attr of el.getAttribute('data-i18n-attr').split(/\s+/).filter(Boolean)) {
        const store = `i18nOrig${camel(`-${attr}`)}`;
        if (el.dataset[store] === undefined) {
          const original = el.getAttribute(attr);
          if (original === null) continue;
          el.dataset[store] = original;
        }
        el.setAttribute(attr, t(el.dataset[store]));
      }
    });
  }

  function setLang(code) {
    if (!isSupported(code)) return false;
    lang = code;
    storageSet(KEYS.lang, code);
    applyDocumentLang();
    return true;
  }

  /** Header Accept-Language: lang moun nan, ak angle kòm rezèv pou backend la. */
  const acceptLanguage = () => (lang === FALLBACK_LANG ? lang : `${lang}, ${FALLBACK_LANG};q=0.5`);

  /** Ikòn glòb an SVG — kreye ak DOM, pa ak innerHTML. */
  function globeIcon() {
    const NS = 'http://www.w3.org/2000/svg';
    const svg = document.createElementNS(NS, 'svg');
    for (const [k, v] of Object.entries({
      viewBox: '0 0 24 24', width: '18', height: '18', fill: 'none',
      stroke: 'currentColor', 'stroke-width': '1.8', 'aria-hidden': 'true',
    })) svg.setAttribute(k, v);
    const shapes = [
      ['circle', { cx: '12', cy: '12', r: '9.5' }],
      ['ellipse', { cx: '12', cy: '12', rx: '4', ry: '9.5' }],
      ['path', { d: 'M2.5 12h19M4.2 7h15.6M4.2 17h15.6' }],
    ];
    for (const [tag, attrs] of shapes) {
      const el = document.createElementNS(NS, tag);
      for (const [k, v] of Object.entries(attrs)) el.setAttribute(k, v);
      svg.append(el);
    }
    return svg;
  }

  /** Stil bouton lang lan, mete yon sèl fwa. Sèvi ak koulè app.css yo si yo la. */
  function ensurePickerStyles() {
    if (document.getElementById('konbit-lang-picker-css')) return;
    const style = document.createElement('style');
    style.id = 'konbit-lang-picker-css';
    style.textContent = `
      .lang-picker { position: relative; display: inline-block; }
      .lang-picker-btn {
        display: inline-flex; align-items: center; gap: 6px; height: 36px; padding: 0 12px;
        border-radius: 999px; border: 1px solid var(--line, #1f2937); background: transparent;
        color: var(--text, #f3f4f6); font: inherit; font-size: 13px; font-weight: 700;
        letter-spacing: 0.04em; cursor: pointer;
      }
      .lang-picker-btn:hover { background: var(--surface, rgba(255, 255, 255, 0.06)); }
      .lang-picker-menu {
        position: absolute; inset-inline-end: 0; top: calc(100% + 6px); min-width: 200px;
        max-height: min(70vh, 460px); overflow-y: auto; padding: 6px;
        display: grid; gap: 2px; z-index: 3000; border-radius: 12px;
        border: 1px solid var(--line, #1f2937); background: var(--bg, #0b0f19);
        box-shadow: 0 20px 40px rgba(0, 0, 0, 0.5);
      }
      .lang-picker-menu[hidden] { display: none; }
      .lang-picker-option {
        display: flex; justify-content: space-between; gap: 12px; padding: 9px 10px;
        border: 0; border-radius: 8px; background: none; color: var(--text, #f3f4f6);
        font: inherit; font-size: 14px; text-align: start; cursor: pointer;
      }
      .lang-picker-option:hover, .lang-picker-option:focus-visible {
        background: var(--surface, rgba(255, 255, 255, 0.06));
      }
      .lang-picker-option[aria-checked="true"] { font-weight: 700; }
    `;
    document.head.append(style);
  }

  // Tradiksyon lang moun nan chwazi a. Tout paj dwe tann sa anvan yo rann tèks.
  const ready = loadLang(lang).then(() => applyTranslations(document));

  const i18n = {
    LANGS,
    get lang() { return lang; },
    get locale() { return (langInfo(lang) || LANGS[0]).locale; },
    ready,
    t,
    apply: applyTranslations,
    missing: () => [...missingKeys],

    /**
     * Moun nan chwazi yon lang: sove l, mete l nan kont lan si l konekte,
     * epi rechaje paj la pou tout tèks yo (menm sa ki soti nan API) chanje.
     */
    async change(code) {
      if (!setLang(code)) return;
      if (tokens.access) {
        try {
          await api.patch('/api/auth/me', { preferred_language: code });
          storageRemove(KEYS.langPending);
        } catch {
          storageSet(KEYS.langPending, '1');   // n ap eseye ankò nan pwochen paj la
        }
      } else {
        // Pa konekte (paj koneksyon, paj karyè): kont lan ap pran chwa sa a apre koneksyon.
        storageSet(KEYS.langPending, '1');
      }
      location.reload();
    },

    /**
     * shell.js rele sa apre /api/auth/identity. Lang kont lan genyen —
     * sof si moun nan fèk chwazi yon lòt anvan l konekte.
     * Retounen true si lang lan chanje.
     */
    async sync(accountLang) {
      await ready;
      const pending = storageGet(KEYS.langPending) === '1';
      if (pending) {
        if (accountLang !== lang) {
          try { await api.patch('/api/auth/me', { preferred_language: lang }); } catch { return false; }
        }
        storageRemove(KEYS.langPending);
        return false;
      }
      if (accountLang && accountLang !== lang && setLang(accountLang)) {
        await loadLang(accountLang);
        applyTranslations(document);
        return true;
      }
      return false;
    },

    /**
     * Bouton glòb 🌐 ak kòd lang lan (HT / FR / EN…) ki louvri yon meni.
     * Non lang yo rete nan pwòp lang yo, pou moun nan rekonèt pa l.
     * Sèvi ak li nenpòt kote: parent.append(Konbit.i18n.switcher())
     */
    switcher() {
      ensurePickerStyles();

      const wrap = document.createElement('div');
      wrap.className = 'lang-picker';

      const btn = document.createElement('button');
      btn.type = 'button';
      btn.className = 'lang-picker-btn';
      btn.setAttribute('aria-haspopup', 'true');
      btn.setAttribute('aria-expanded', 'false');
      btn.setAttribute('aria-label', t('Chwazi lang'));
      btn.title = t('Chwazi lang');
      const code = document.createElement('span');
      code.textContent = lang.toUpperCase();
      btn.append(globeIcon(), code);

      const menu = document.createElement('div');
      menu.className = 'lang-picker-menu';
      menu.hidden = true;

      const close = () => {
        menu.hidden = true;
        btn.setAttribute('aria-expanded', 'false');
      };
      const open = () => {
        menu.hidden = false;
        btn.setAttribute('aria-expanded', 'true');
        const current = menu.querySelector('[aria-checked="true"]');
        if (current) current.focus();
      };

      for (const l of LANGS) {
        const isCurrent = l.code === lang;
        const opt = document.createElement('button');
        opt.type = 'button';
        opt.className = 'lang-picker-option';
        opt.lang = l.code;
        opt.dir = RTL.has(l.code) ? 'rtl' : 'ltr';
        opt.setAttribute('role', 'menuitemradio');
        opt.setAttribute('aria-checked', String(isCurrent));
        const name = document.createElement('span');
        name.textContent = l.label;
        opt.append(name);
        if (isCurrent) {
          const mark = document.createElement('span');
          mark.setAttribute('aria-hidden', 'true');
          mark.textContent = '✓';
          opt.append(mark);
        }
        opt.addEventListener('click', () => {
          if (isCurrent) { close(); return; }
          menu.querySelectorAll('button').forEach((b) => { b.disabled = true; });
          i18n.change(l.code);
        });
        menu.append(opt);
      }

      btn.addEventListener('click', (e) => {
        e.stopPropagation();
        if (menu.hidden) open(); else close();
      });
      document.addEventListener('click', (e) => {
        if (!wrap.contains(e.target)) close();
      });
      wrap.addEventListener('keydown', (e) => {
        if (e.key === 'Escape' && !menu.hidden) { close(); btn.focus(); }
      });

      wrap.append(btn, menu);
      return wrap;
    },
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
    if (status === 0) return t('Nou pa ka rive jwenn sèvè a. Verifye koneksyon entènèt ou.');
    if (status === 401) return t('Sesyon w lan fini. Konekte ankò.');
    if (status === 403) return t('Ou pa gen dwa pou aksyon sa a.');
    if (status === 404) return t('Sa ou chèche a pa egziste.');
    if (status === 409) return t('Gen yon konfli ak done ki deja la.');
    if (status === 422) return t('Kèk enfòmasyon pa valab.');
    if (status >= 500) return t('Sèvè a gen yon pwoblèm. Eseye ankò nan kèk minit.');
    return t('Yon bagay pa mache.');
  }

  function toApiError(status, body) {
    if (!body) return new ApiError(status, defaultMessage(status));

    // Backend la deja tradui `detail` dapre header Accept-Language la.
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
      return storageGet(KEYS.access);
    },
    get refresh() {
      return storageGet(KEYS.refresh);
    },
    save(access, refresh) {
      // Navigasyon prive: si sa echwe, sesyon an ap dire jouk paj la fèmen.
      storageSet(KEYS.access, access);
      if (refresh) storageSet(KEYS.refresh, refresh);
    },
    clear() {
      storageRemove(KEYS.access);
      storageRemove(KEYS.refresh);
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
          headers: { 'Content-Type': 'application/json', 'Accept-Language': acceptLanguage() },
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
    // Accept-Language: backend la tradui mesaj erè yo nan lang sa a (oswa angle).
    const headers = { Accept: 'application/json', 'Accept-Language': acceptLanguage() };
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
      // Backend la deja mete lang Accept-Language la sou nouvo kont lan.
      storageRemove(KEYS.langPending);
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
  //
  // Kreyòl: navigatè yo pa konnen kreyòl, kidonk non mwa ak jou yo ekri
  // isit. Tout lòt lang yo: Intl (li konnen franse, angle, panyòl, chinwa,
  // arab…). Chif yo toujou 0-9 (gade `locale` nan LANGS).
  // -------------------------------------------------------------------------

  const HT_CAL = {
    months: ['janvye', 'fevriye', 'mas', 'avril', 'me', 'jen',
             'jiyè', 'out', 'septanm', 'oktòb', 'novanm', 'desanm'],
    monthsShort: ['jan.', 'fev.', 'mas', 'avr.', 'me', 'jen',
                  'jiy.', 'out', 'sept.', 'okt.', 'nov.', 'des.'],
    days: ['dimanch', 'lendi', 'madi', 'mèkredi', 'jedi', 'vandredi', 'samdi'],
    daysShort: ['dim.', 'len.', 'mad.', 'mèk.', 'jed.', 'van.', 'sam.'],
  };

  const isHt = () => lang === DEFAULT_LANG;
  const locale = () => (langInfo(lang) || LANGS[0]).locale;
  const withLatnDigits = (loc) => (loc.includes('-u-') ? loc : `${loc}-u-nu-latn`);

  const formatters = Object.create(null);
  function dtf(options) {
    const key = `${lang}|${JSON.stringify(options)}`;
    if (!formatters[key]) {
      formatters[key] = new Intl.DateTimeFormat(withLatnDigits(locale()), options);
    }
    return formatters[key];
  }

  const numberFormats = Object.create(null);
  function numberFmt() {
    const loc = withLatnDigits(locale());
    if (!numberFormats[loc]) {
      numberFormats[loc] = new Intl.NumberFormat(loc, {
        minimumFractionDigits: 2,
        maximumFractionDigits: 2,
      });
    }
    return numberFormats[loc];
  }

  /** Non 12 mwa oswa 7 jou nan lang aktyèl la. */
  function calendarNames(kind) {
    if (isHt()) return HT_CAL[kind];
    if (kind === 'months') {
      return Array.from({ length: 12 }, (_, m) => dtf({ month: 'long' }).format(new Date(2026, m, 1)));
    }
    // 4 janvye 2026 se yon dimanch.
    return Array.from({ length: 7 }, (_, d) => dtf({ weekday: 'long' }).format(new Date(2026, 0, 4 + d)));
  }

  const pad2 = (n) => String(n).padStart(2, '0');

  const DURATION_UNITS = {
    ht: [(x) => `${x}è`, (x) => `${x}min`],
    fr: [(x) => `${x} h`, (x) => `${x} min`],
    en: [(x) => `${x}h`, (x) => `${x}m`],
  };

  const fmt = {
    /** Non mwa / jou yo nan lang aktyèl la. */
    get MONTHS() { return calendarNames('months'); },
    get DAYS() { return calendarNames('days'); },

    /** 4500000 → "45 000,00 HTG" (oswa "45,000.00 HTG" an angle). Montan API yo an santim. */
    money(cents, currency = 'HTG') {
      if (cents === null || cents === undefined) return '—';
      // Kèk lang separe milye yo ak yon espas TRÈ etwat (U+202F) ki parèt
      // envizib nan kèk polis ("41000,00"). Nou mete yon espas nòmal
      // ki pa kase liy (U+00A0) olye.
      const text = numberFmt().format(cents / 100).replace(/[\u202F\u2009]/g, '\u00A0');
      return `${text} ${currency}`;
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

    /** Dat jodi a (lè lokal) an "AAAA-MM-JJ" — pou <input type="date">. */
    todayIso() {
      const d = new Date();
      return `${d.getFullYear()}-${pad2(d.getMonth() + 1)}-${pad2(d.getDate())}`;
    },

    /** "21 oktòb 2026" · "21 octobre 2026" · "October 21, 2026" · "2026年10月21日" */
    date(value) {
      const d = fmt.parseDate(value);
      if (!d || isNaN(d)) return '—';
      if (isHt()) return `${d.getDate()} ${HT_CAL.months[d.getMonth()]} ${d.getFullYear()}`;
      return dtf({ day: 'numeric', month: 'long', year: 'numeric' }).format(d);
    },

    /** "jedi 24 septanm 2026" · "Thursday, September 24, 2026" */
    longDate(value) {
      const d = fmt.parseDate(value);
      if (!d || isNaN(d)) return '—';
      if (isHt()) {
        return `${HT_CAL.days[d.getDay()]} ${d.getDate()} ${HT_CAL.months[d.getMonth()]} ${d.getFullYear()}`;
      }
      return dtf({ weekday: 'long', day: 'numeric', month: 'long', year: 'numeric' }).format(d);
    },

    /** "23 sept." · "Sep 23" */
    shortDate(value) {
      const d = fmt.parseDate(value);
      if (!d || isNaN(d)) return '—';
      if (isHt()) return `${d.getDate()} ${HT_CAL.monthsShort[d.getMonth()]}`;
      return dtf({ day: 'numeric', month: 'short' }).format(d);
    },

    /** "22:45" */
    time(value) {
      const d = fmt.parseDate(value);
      if (!d || isNaN(d)) return '—';
      return `${pad2(d.getHours())}:${pad2(d.getMinutes())}`;
    },

    /** "sam. 10 okt. 2026 · 22:45" · "Sat, Oct 10, 2026 · 22:45" */
    dateTime(value) {
      const d = fmt.parseDate(value);
      if (!d || isNaN(d)) return '—';
      const clock = `${pad2(d.getHours())}:${pad2(d.getMinutes())}`;
      if (isHt()) {
        return `${HT_CAL.daysShort[d.getDay()]} ${d.getDate()} ${HT_CAL.monthsShort[d.getMonth()]} `
          + `${d.getFullYear()} · ${clock}`;
      }
      const day = dtf({ weekday: 'short', day: 'numeric', month: 'short', year: 'numeric' }).format(d);
      return `${day} · ${clock}`;
    },

    /**
     * Sa moun nan tape → santim. "45 000" → 4500000, "1500,50" → 150050,
     * "45,000.00" → 4500000. Aksepte vigil oswa pwen pou desimal, ak espas
     * pou milye. Retounen null si sa pa yon chif.
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
      const key = {
        active: 'Aktif',
        on_leave: 'An konje',
        suspended: 'Sispann',
        terminated: 'Pa nan biznis la ankò',
      }[s];
      return key ? t(key) : s;
    },

    /** 450 → "7è 30min" · "7 h 30 min" · "7h 30m" */
    duration(minutes) {
      if (minutes === null || minutes === undefined) return '—';
      const h = Math.floor(minutes / 60);
      const m = Math.round(minutes % 60);
      const [uh, um] = DURATION_UNITS[lang] || DURATION_UNITS.fr;
      if (h === 0) return um(m);
      return m === 0 ? uh(h) : `${uh(h)} ${um(m)}`;
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
        return slip.check_number ? t('Chèk nimewo {n}', { n: slip.check_number }) : t('Chèk');
      }
      if (m === 'direct_deposit') {
        let label = t('Depo dirèk');
        if (slip.bank_name) label += ` — ${slip.bank_name}`;
        if (slip.account_last4) label += ` (${t('kont ••{last4}', { last4: slip.account_last4 })})`;
        return label;
      }
      if (m === 'moncash') return 'MonCash';
      if (m === 'natcash') return 'NatCash';
      if (m === 'cash') return t('Lajan kach');
      return m || '—';
    },

    leaveType(type) {
      const key = {
        vacation: 'Vakans',
        sick: 'Maladi',
        maternity: 'Matènite',
        paternity: 'Patènite',
        bereavement: 'Lanmò nan fanmi',
        unpaid: 'San peye',
        other: 'Lòt',
      }[type];
      return key ? t(key) : type;
    },

    requestStatus(s) {
      const key = {
        pending: 'Ap tann',
        approved: 'Apwouve',
        rejected: 'Refize',
        cancelled: 'Anile',
      }[s];
      return key ? t(key) : s;
    },

    role(r) {
      const key = {
        super_admin: 'Administratè Konbit',
        org_admin: 'Administratè',
        hr: 'Resous imèn',
        manager: 'Manadjè',
        employee: 'Anplwaye',
        applicant: 'Kandida',
      }[r];
      return key ? t(key) : r;
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

  window.Konbit = { API_URL, api, auth, fmt, h, ApiError, i18n, t };
})();