# Deplwaman KONMBIT — Gid pou Pwodiksyon

Gid sa a sipoze ou ap deplwaye pou vre (pa jis teste). Swiv etap yo nan lòd —
Etap 0 la pi ijan pase tout rès yo.

---

## Etap 0 — Sekrè ki te ekspoze yo (FÈ SA ANVAN NENPÒT LÒT BAGAY)

Nan yon vèsyon anvan repo a, `.env` ak `konbit.db` te yon fwa komite piblikman
sou GitHub anvan yo te antre nan `.gitignore`. Lòd aksyon an enpòtan:

1. **Konsidere tout sa ki te nan ansyen `.env` la kòm konpwomèt**, menm si
   repo a prive kounye a: `SECRET_KEY`, nenpòt modpas oswa kle API. Chanje
   yo TOUT. `git filter-repo` netwaye istorik Git la, men li pa efase kopi
   moun te ka deja klone, oswa kach ekstèn — kidonk netwaye istorik la se
   ijyèn anplis, pa yon sistèm sekirite. SÈL bagay ki reyèlman pwoteje w se
   chanje valè sekrè yo.
2. **Apre** ou fin chanje sekrè yo, netwaye istorik la (`git filter-repo`)
   epi `git push --force`.
3. Si `konbit.db` te gen modpas VRÈ moun ladan (menm ashe/hachage), mande
   moun sa yo chanje modpas yo tou — pa depann sèlman sou fenès la.
4. Verifye `.gitignore` gen `.env`, `*.db`, **ak `*.db-journal`** (fichye
   jounal SQLite ki ka gen menм kalite done sansib).

Jenere nouvo `SECRET_KEY` pwodiksyon an konsa:
```bash
python -c "import secrets; print(secrets.token_urlsafe(64))"
```

---

## Etap 1 — Chwazi yon sèvis PostgreSQL

Pou yon ti biznis, pi senp lan se yon sèvis ki jere Postgres pou ou. Men gen
limit plan gratis ki ka mòde w:

| Sèvis | Limit gratis ki enpòtan |
|---|---|
| **Supabase** | Pwojè gratis mete an poz apre ~1 semèn san aktivite |
| **Neon** | Baz done "dòmi" san trafik → yon ti reta sou premye rekèt apre yon poz |
| **Railway** | Pa gen menm pwoblèm poz la, men gratis limite an tan/lajan |

**Si w chwazi Supabase**: pran chèn koneksyon **"Session pooler"** oswa
koneksyon **dirèk** la, PA "Transaction pooler" la (pò 6543). Transaction
pooler a kase prepared statements Psycopg 3 sèvi ak yo pa defo. Si w oblije
itilize Transaction pooler pou yon rezon, ajoute nan `create_engine` (nan
`backend/app/database.py`, branch PostgreSQL la):
```python
connect_args={"prepare_threshold": None}
```

**Si w chwazi Neon**: ajoute `?sslmode=require` nan fen `DATABASE_URL` la.

---

## Etap 2 — Vèsyon Python

Ou devlope sou Python 3.14; sèvis yo ka itilize yon lòt vèsyon pa defo.

- **Render**: mete varyab anviwonman `PYTHON_VERSION=3.14`.
- **Railway**: kreye yon fichye `.python-version` nan `backend/` ki gen `3.14`.

Nan tou de ka yo, mete dosye rasin sèvis la sou `backend/` (se la
`requirements.txt` la ye).

`pool_pre_ping=True` **deja nan `database.py`** pou branch PostgreSQL la —
pa gen anyen pou ajoute la. Se sa ki anpeche erè o aza lè yon sèvis Postgres
jere fèmen koneksyon ki rete san travay twò lontan.

---

## Etap 3 — CORS

Nan `ALLOWED_ORIGINS` (fichye `.env` pwodiksyon an), orijin nan dwe egzak:
`https://konbit.netlify.app` — san `/` nan fen, ak bon eskèm (`https`, pa
`http`). Yon ti diferans sifi pou navigatè a bloke tout rekèt yo san mesaj
klè.

---

## Etap 4 — Migrasyon Alembic: teste anvan pwodiksyon

**Pa janm kouri `alembic upgrade head` sou baz done pwodiksyon an pou premye
fwa san w pa teste l anvan.** De bagay konkrè pou verifye nan migrasyon
inisyal la (`6a7914a087bf_schema_inisyal.py`):

- **Kolòn Enum** (`role = Column(SQLEnum(UserRole), ...)` nan `models.py`,
  ak lòt tankou `LeaveType`, `ApplicationStage`, `JobStatus`): sou
  PostgreSQL, yo kreye yon VRÈ tip DB (`CREATE TYPE`). Migrasyon
  `downgrade()` a ka pa efase tip sa yo — si yon jou ou fè
  `downgrade` apre yon `upgrade`, ou ka jwenn "type already exists" lè w
  eseye `upgrade` ankò. Verifye `downgrade()` gen yon `DROP TYPE` pou chak
  Enum, oswa jis evite `downgrade` sou pwodiksyon.
- **`server_default=sa.text('(CURRENT_TIMESTAMP)')`** pou `created_at`/
  `updated_at`: sentaks sa a soti nan SQLite. PostgreSQL aksepte fòm sa a
  tou nan pifò ka, men se egzakteman kalite ti detay ki ta dwe verifye ak
  yon vrè baz done, pa sipoze.
- `batch_alter_table(...)` yo *pa* yon pwoblèm an jeneral — se yon
  konpòtman entansyonèl Alembic (menm kòmantè a nan `env.py` w la konfime
  sa: "Sa pa fè mal sou PostgreSQL"). Men li rete yon bon rezon anplis pou
  teste kanmenm.

**Fason pou teste**: kreye yon baz Postgres jetab (yon branch Neon separe,
oswa Docker lokal: `docker run -e POSTGRES_PASSWORD=test -p 5432:5432
postgres:16`), pwente `DATABASE_URL` sou li, kouri `alembic upgrade head`,
epi kouri `pytest` kont li. Si tou de pase, w ap gen konfyans reyèl anvan
pwodiksyon.

---

## Etap 5 — Premye biznis ak premye admin nan

**Pa gen script `seed_admin.py` ki nesesè.** `POST /api/auth/signup` (menm
wout `login.html` itilize pou "Enskri biznis ou") kreye YON biznis (Organization)
**AK** premye kont admin nan menm apèl la. Baz done pwodiksyon an ap vid lè
w fin kouri migrasyon yo — se nòmal. Pou kòmanse:

1. Louvri frontend pwodiksyon an (`https://konbit.netlify.app/login.html`
   pa egzanp).
2. Klike sou tab "Enskri biznis ou" (oswa ekivalan an).
3. Ranpli non biznis la, imèl ak modpas admin nan.

Sa a kreye premye Organization + premye User (`org_admin`) reyèl la,
egzakteman menm jan chak nouvo kliyan KONMBIT ta fè l. Si yon jou ou vle
**anpeche** nenpòt moun enskri yon nouvo biznis nan pwodiksyon (egzanp: si
KONMBIT rete yon sistèm entèn pou yon sèl biznis, pa yon SaaS piblik), sa se
yon lòt fonksyonalite separe (yon "drapo" ki bloke `/signup` apre premye
biznis la) — di m si w vle sa, se pa menm bagay ak kesyon "kijan premye
admin antre a".

---

## Etap 6 — Backend la

**Kòmand demaraj:**
```bash
uvicorn app.main:app --host 0.0.0.0 --port $PORT --proxy-headers --forwarded-allow-ips="*"
```
`--proxy-headers` **enpòtan**: san li, Uvicorn pa konprann `X-Forwarded-For`
sèvis la voye, e fonksyon jounal odit yo (`_audit()` nan plizyè router) ki
anrejistre `request.client.host` ap anrejistre IP pwoksi a olye vrè IP
kliyan an.

**Migrasyon otomatik**: si sèvis ou a sipòte yon "Pre-Deploy Command" (Render
genyen sa), mete `alembic upgrade head` la, separe de kòmand demaraj la.
Sinon, anchène yo: `alembic upgrade head && uvicorn ...`.

**Sèvè a ap kouri an UTC.** Se egzakteman poutèt sa patch `attendance.py`
la (fizo orè biznis la, `backend/app/timezone_utils.py`) enpòtan — san li,
pwentaj ki fèt apre 8è diswa lè Ayiti anrejistre sou move jou a. **Verifye
patch sa a byen aplike anvan deplwaman**, li pa opsyonèl pou pwodiksyon.

**Plan gratis Render**: sèvis web gratis yo dòmi apre ~15 minit san trafik.
Premye moun ki konekte yon maten ap tann prèske yon minit. Pou yon HRIS moun
ap sèvi avè l chak maten, sa se yon reyèl pwoblèm — yon plan peye ki pa chè
(oswa Railway) vo lapèn pou evite l.

---

## Etap 7 — Frontend la

**`config.js` separe olye yon `<script>` nan chak paj**: kreye yon sèl
fichye `frontend/config.js`:
```js
window.KONBIT_API_URL = 'https://api-ou.com';
```
Chaje l anvan `api.js` nan CHAK paj HTML:
```html
<script src="config.js"></script>
<script src="api.js"></script>
```
Yon sèl fichye pou chanje demen, san risk bliye yon paj.

**Refresh token**: si li estoke nan yon cookie (verifye nan `api.js`
oswa backend la), e frontend/backend sou de domèn diferan, cookie a bezwen
`SameSite=None; Secure` pou navigatè a aksepte voye l atravè domèn. Si li
nan `localStorage` pito, pa gen chanjman pou fè.

---

## Etap 8 — Backup (anplis de sa sèvis la bay)

Pa depann sèlman sou backup otomatik founisè Postgres la bay pou yon done
tankou pewòl ak dosye anplwaye. Mete yon `pg_dump` regilye (chak jou,
egzanp via yon cron oswa yon GitHub Action) ki sove yon kopi apa, menm si
plan gratis la gen "backup" enkli.

---

## Chèklis final anvan lansman

- [ ] Sekrè yo chanje (Etap 0) — **ijan, fè sa an premye**
- [ ] Baz Postgres kreye, chèn koneksyon kòrèk (Session pooler / dirèk)
- [ ] `PYTHON_VERSION` / `.python-version` fikse sou 3.14
- [ ] `ALLOWED_ORIGINS` gen domèn egzak frontend pwodiksyon an
- [ ] Migrasyon teste sou yon vrè Postgres jetab + `pytest` pase sou li
- [ ] Patch `attendance.py` (fizo orè) konfime aplike
- [ ] `config.js` frontend pwente sou backend pwodiksyon an
- [ ] Premye enskripsyon biznis fèt via `/login.html`
- [ ] Backup `pg_dump` konfigire apa de sèvis la
