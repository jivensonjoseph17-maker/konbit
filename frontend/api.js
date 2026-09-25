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
  //     t('Bonjou {name}', {name})      → valè yo ranplase {name}
  //     t('Anile|aksyon')               → pati apre | a se KONTÈKS: li separe
  //                                       "Anile" (estati: Annulé) ak
  //                                       "Anile" (bouton: Annuler). An kreyòl
  //                                       sèlman pati anvan | a parèt.
  //
  // Yon tèks ki pa gen tradiksyon rete an kreyòl — paj la pa janm kase.
  // Sou 127.0.0.1/localhost, konsòl la montre sa ki manke (Konbit.i18n.missing()).
  //
  // Tradiksyon yon paj: Konbit.i18n.add([['Kreyòl', 'Français', 'English'], ...])
  //
  // Tèks fiks nan HTML la:
  //     <h1 data-i18n>Balans konje</h1>
  //     <input data-i18n-attr="placeholder aria-label" placeholder="Chèche…">
  //     <title data-i18n>Peyòl — KONMBIT</title>
  // `data-i18n` sèlman sou yon eleman ki gen TÈKS SÈLMAN (pa lòt eleman
  // anndan l) — sinon mete tèks la nan yon <span data-i18n>.
  // =========================================================================

  const LANGS = [
    { code: 'ht', label: 'Kreyòl' },
    { code: 'fr', label: 'Français' },
    { code: 'en', label: 'English' },
  ];
  const DEFAULT_LANG = 'ht';
  const isSupported = (code) => LANGS.some((l) => l.code === code);

  const DICT = { fr: Object.create(null), en: Object.create(null) };
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
  document.documentElement.lang = lang;

  function t(key, vars) {
    const display = key.split('|')[0];
    let text = display;
    if (lang !== DEFAULT_LANG) {
      const found = DICT[lang][key];
      if (found !== undefined) {
        text = found;
      } else if (isDev && !missingKeys.has(`${lang}:${key}`)) {
        missingKeys.add(`${lang}:${key}`);
        console.debug(`[i18n] ${lang} manke: "${key}"`);
      }
    }
    if (vars) {
      text = text.replace(/\{(\w+)\}/g, (m, name) => (name in vars ? String(vars[name]) : m));
    }
    return text;
  }

  /** rows: [['Kreyòl', 'Français', 'English'], ...] */
  function addTranslations(rows) {
    for (const [ht, fr, en] of rows) {
      if (fr) DICT.fr[ht] = fr;
      if (en) DICT.en[ht] = en;
    }
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
    document.documentElement.lang = code;
    return true;
  }

  const i18n = {
    LANGS,
    get lang() { return lang; },
    t,
    add: addTranslations,
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
      const pending = storageGet(KEYS.langPending) === '1';
      if (pending) {
        if (accountLang !== lang) {
          try { await api.patch('/api/auth/me', { preferred_language: lang }); } catch { return false; }
        }
        storageRemove(KEYS.langPending);
        return false;
      }
      if (accountLang && accountLang !== lang && setLang(accountLang)) {
        applyTranslations(document);
        return true;
      }
      return false;
    },

    /** <select> pou chwazi lang. Non lang yo rete nan pwòp lang yo. */
    switcher() {
      const select = document.createElement('select');
      select.className = 'select lang-select';
      select.setAttribute('aria-label', t('Lang'));
      for (const l of LANGS) {
        const opt = document.createElement('option');
        opt.value = l.code;
        opt.textContent = l.label;
        opt.lang = l.code;
        select.append(opt);
      }
      select.value = lang;
      select.addEventListener('change', () => {
        select.disabled = true;
        i18n.change(select.value);
      });
      return select;
    },
  };

  // Tradiksyon pataje: erè, meni, fòma, estati. Chak paj ajoute pa l yo.
  addTranslations([
    // --- Erè rezo / HTTP ---
    ['Nou pa ka rive jwenn sèvè a. Verifye koneksyon entènèt ou.',
      'Impossible de joindre le serveur. Vérifiez votre connexion Internet.',
      'We cannot reach the server. Check your internet connection.'],
    ['Sesyon w lan fini. Konekte ankò.',
      'Votre session a expiré. Reconnectez-vous.',
      'Your session has ended. Please sign in again.'],
    ['Ou pa gen dwa pou aksyon sa a.',
      "Vous n'avez pas le droit d'effectuer cette action.",
      'You are not allowed to perform this action.'],
    ['Sa ou chèche a pa egziste.',
      "Ce que vous cherchez n'existe pas.",
      'What you are looking for does not exist.'],
    ['Gen yon konfli ak done ki deja la.',
      'Conflit avec des données existantes.',
      'There is a conflict with existing data.'],
    ['Kèk enfòmasyon pa valab.',
      'Certaines informations ne sont pas valides.',
      'Some information is not valid.'],
    ['Sèvè a gen yon pwoblèm. Eseye ankò nan kèk minit.',
      'Le serveur rencontre un problème. Réessayez dans quelques minutes.',
      'The server has a problem. Try again in a few minutes.'],
    ['Yon bagay pa mache.', "Quelque chose n'a pas fonctionné.", 'Something went wrong.'],

    // --- Mo ki repete sou tout paj yo ---
    ['Ap chaje…', 'Chargement…', 'Loading…'],
    ['Sove', 'Enregistrer', 'Save'],
    ['Anile|aksyon', 'Annuler', 'Cancel'],
    ['Efase', 'Supprimer', 'Delete'],
    ['Modifye', 'Modifier', 'Edit'],
    ['Fèmen', 'Fermer', 'Close'],
    ['Anvan', 'Précédent', 'Previous'],
    ['Apre', 'Suivant', 'Next'],
    ['Wi', 'Oui', 'Yes'],
    ['Non|repons', 'Non', 'No'],
    ['Aksyon', 'Actions', 'Actions'],
    ['Estati', 'Statut', 'Status'],
    ['Lang', 'Langue', 'Language'],

    // --- Estati anplwaye ---
    ['Aktif', 'Actif', 'Active'],
    ['An konje', 'En congé', 'On leave'],
    ['Sispann', 'Suspendu', 'Suspended'],
    ['Pa nan biznis la ankò', "N'est plus dans l'entreprise", 'No longer with the company'],

    // --- Mwayen peman ---
    ['Chèk nimewo {n}', 'Chèque numéro {n}', 'Check number {n}'],
    ['Chèk', 'Chèque', 'Check'],
    ['Depo dirèk', 'Virement direct', 'Direct deposit'],
    ['kont ••{last4}', 'compte ••{last4}', 'account ••{last4}'],
    ['Lajan kach', 'Espèces', 'Cash'],

    // --- Kalite konje ---
    ['Vakans', 'Congé annuel', 'Vacation'],
    ['Maladi', 'Maladie', 'Sick leave'],
    ['Matènite', 'Maternité', 'Maternity'],
    ['Patènite', 'Paternité', 'Paternity'],
    ['Lanmò nan fanmi', 'Deuil', 'Bereavement'],
    ['San peye', 'Sans solde', 'Unpaid'],
    ['Lòt', 'Autre', 'Other'],

    // --- Estati demann (adjektif; bouton yo sèvi ak |aksyon) ---
    ['Ap tann', 'En attente', 'Pending'],
    ['Apwouve', 'Approuvé', 'Approved'],
    ['Refize', 'Refusé', 'Rejected'],
    ['Anile', 'Annulé', 'Cancelled'],

    // --- Wòl ---
    ['Administratè Konbit', 'Administrateur Konbit', 'Konbit administrator'],
    ['Administratè', 'Administrateur', 'Administrator'],
    ['Resous imèn', 'Ressources humaines', 'Human resources'],
    ['Manadjè', 'Manager', 'Manager'],
    ['Anplwaye', 'Employé', 'Employee'],
    ['Kandida', 'Candidat', 'Candidate'],
  ]);

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
          headers: { 'Content-Type': 'application/json', 'Accept-Language': lang },
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
    // Accept-Language: backend la tradui mesaj erè yo nan lang sa a.
    const headers = { Accept: 'application/json', 'Accept-Language': lang };
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
  // Dat yo nan lang moun nan chwazi a. Pou kreyòl nou pa ka sèvi ak
  // toLocaleDateString (li pa konnen kreyòl), kidonk non mwa ak jou yo
  // ekri isit pou chak lang, epi fòma a rete menm jan sou tout paj yo.
  // -------------------------------------------------------------------------

  const CALENDAR = {
    ht: {
      months: ['janvye', 'fevriye', 'mas', 'avril', 'me', 'jen',
               'jiyè', 'out', 'septanm', 'oktòb', 'novanm', 'desanm'],
      monthsShort: ['jan.', 'fev.', 'mas', 'avr.', 'me', 'jen',
                    'jiy.', 'out', 'sept.', 'okt.', 'nov.', 'des.'],
      days: ['dimanch', 'lendi', 'madi', 'mèkredi', 'jedi', 'vandredi', 'samdi'],
      daysShort: ['dim.', 'len.', 'mad.', 'mèk.', 'jed.', 'van.', 'sam.'],
    },
    fr: {
      months: ['janvier', 'février', 'mars', 'avril', 'mai', 'juin',
               'juillet', 'août', 'septembre', 'octobre', 'novembre', 'décembre'],
      monthsShort: ['janv.', 'févr.', 'mars', 'avr.', 'mai', 'juin',
                    'juil.', 'août', 'sept.', 'oct.', 'nov.', 'déc.'],
      days: ['dimanche', 'lundi', 'mardi', 'mercredi', 'jeudi', 'vendredi', 'samedi'],
      daysShort: ['dim.', 'lun.', 'mar.', 'mer.', 'jeu.', 'ven.', 'sam.'],
    },
    en: {
      months: ['January', 'February', 'March', 'April', 'May', 'June',
               'July', 'August', 'September', 'October', 'November', 'December'],
      monthsShort: ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
                    'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'],
      days: ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday'],
      daysShort: ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'],
    },
  };
  const cal = () => CALENDAR[lang] || CALENDAR[DEFAULT_LANG];

  // Kreyòl ak franse: "45 000,00". Angle: "45,000.00".
  const numberFormats = {};
  function numberFmt() {
    const locale = lang === 'en' ? 'en-US' : 'fr-FR';
    if (!numberFormats[locale]) {
      numberFormats[locale] = new Intl.NumberFormat(locale, {
        minimumFractionDigits: 2,
        maximumFractionDigits: 2,
      });
    }
    return numberFormats[locale];
  }

  const pad2 = (n) => String(n).padStart(2, '0');

  const fmt = {
    /** Non mwa yo nan lang aktyèl la (miniskil an kreyòl ak franse). */
    get MONTHS() { return cal().months; },
    get DAYS() { return cal().days; },

    /** 4500000 → "45 000,00 HTG" (oswa "45,000.00 HTG" an angle). Montan API yo an santim. */
    money(cents, currency = 'HTG') {
      if (cents === null || cents === undefined) return '—';
      // fr-FR separe milye yo ak yon espas TRÈ etwat (U+202F) ki parèt
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

    /** "21 oktòb 2026" · "21 octobre 2026" · "October 21, 2026" */
    date(value) {
      const d = fmt.parseDate(value);
      if (!d || isNaN(d)) return '—';
      const c = cal();
      if (lang === 'en') return `${c.months[d.getMonth()]} ${d.getDate()}, ${d.getFullYear()}`;
      return `${d.getDate()} ${c.months[d.getMonth()]} ${d.getFullYear()}`;
    },

    /** "23 sept." · "Sep 23" */
    shortDate(value) {
      const d = fmt.parseDate(value);
      if (!d || isNaN(d)) return '—';
      const c = cal();
      if (lang === 'en') return `${c.monthsShort[d.getMonth()]} ${d.getDate()}`;
      return `${d.getDate()} ${c.monthsShort[d.getMonth()]}`;
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
      const c = cal();
      const clock = `${pad2(d.getHours())}:${pad2(d.getMinutes())}`;
      if (lang === 'en') {
        return `${c.daysShort[d.getDay()]}, ${c.monthsShort[d.getMonth()]} ${d.getDate()}, `
          + `${d.getFullYear()} · ${clock}`;
      }
      return `${c.daysShort[d.getDay()]} ${d.getDate()} ${c.monthsShort[d.getMonth()]} `
        + `${d.getFullYear()} · ${clock}`;
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
      const u = {
        ht: { h: (x) => `${x}è`, m: (x) => `${x}min` },
        fr: { h: (x) => `${x} h`, m: (x) => `${x} min` },
        en: { h: (x) => `${x}h`, m: (x) => `${x}m` },
      }[lang] || { h: (x) => `${x}è`, m: (x) => `${x}min` };
      if (h === 0) return u.m(m);
      return m === 0 ? u.h(h) : `${u.h(h)} ${u.m(m)}`;
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

  // Tradui tèks fiks HTML la depi paj la pare. Paj ki ajoute pwòp
  // tradiksyon yo (i18n.add) apre sa dwe rele Konbit.i18n.apply() ankò.
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => applyTranslations(document));
  } else {
    applyTranslations(document);
  }
})();