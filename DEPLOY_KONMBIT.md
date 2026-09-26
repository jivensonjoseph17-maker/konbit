# Mete KONMBIT sou konmbit.com — etap pa etap

Gid sa a konplete `DEPLOYMENT.md` (ki esplike *poukisa* chak etap). Isit la se
*kisa pou fè*, nan lòd, pou konmbit.com sou Render.

| Adrès | Sa l ye | Sèvis Render |
|---|---|---|
| https://konmbit.com, https://www.konmbit.com | Paj yo (frontend) | `konmbit-web` |
| https://api.konmbit.com | Backend FastAPI | `konmbit-api` |
| (pa piblik) | PostgreSQL 16 | `konmbit-db` |

Tout sa defini nan `render.yaml` nan rasin repo a.

---

## 1. Anvan tout bagay (sou machin ou)

1. **Sekrè yo** — `DEPLOYMENT.md`, Etap 0. Si sa poko fèt, fè l an premye.
2. **Jenere SECRET_KEY pwodiksyon an** epi sere l nan yon kote an sekirite
   (jeretè modpas):
   ```
   python -c "import secrets; print(secrets.token_urlsafe(64))"
   ```
   Si kle a gen mo "dev", "test" oswa "secret" ladan l (sa ra), jenere yon lòt:
   `config.py` ap refize l.
3. **Pouse fichye yo sou GitHub**, epi ouvri tab **Actions** sou GitHub.
   Workflow **CI** a dwe vèt: tès yo, tradiksyon yo, ak migrasyon yo sou yon
   vrè PostgreSQL 16. **Si "migrations-postgres" wouj, pa deplwaye**: voye
   mesaj erè a pou n korije migrasyon an anvan.

## 2. Render

1. Kreye yon kont sou https://render.com (ak kont GitHub ou).
2. **New → Blueprint** → chwazi repo `konbit`. Render li `render.yaml`.
3. Li mande **SECRET_KEY**: kole kle ou te jenere a.
4. Klike **Apply**. Render kreye baz done a, konstwi backend la, kouri
   `alembic upgrade head`, epi mete paj yo an liy.

Pri: web `starter` + baz done `basic-256mb` se plan peye ki pa chè. Plan gratis
la dòmi apre 15 minit, e premye moun ki konekte chak maten ta tann prèske yon
minit. Gade pri aktyèl yo sou render.com/pricing.

**Si build la echwe sou vèsyon Python la** (Render ka poko gen 3.14.4): chanje
`PYTHON_VERSION` nan `render.yaml` pou dènye 3.14.x Render sipòte.

## 3. Non domèn nan (DNS)

Nan Render, ouvri chak sèvis → **Settings → Custom Domains**. Render montre
egzakteman ki anrejistreman pou mete. Mete yo kote w te achte konmbit.com:

| Non | Kalite | Valè |
|---|---|---|
| `api` | CNAME | sa Render montre pou `konmbit-api` (…onrender.com) |
| `www` | CNAME | sa Render montre pou `konmbit-web` (…onrender.com) |
| `@` (konmbit.com) | ALIAS/ANAME, oswa A | sa Render montre pou `konmbit-web` |

Toujou pran valè Render montre w yo: yo ka chanje. Apre DNS la pwopaje
(kèk minit, pafwa kèk èdtan), Render mete HTTPS otomatikman.

## 4. Verifye

1. https://api.konmbit.com/api/health → `"status": "ok"`, `"database": true`.
2. https://konmbit.com → paj akèy la.
3. https://konmbit.com/login.html → **Enskri biznis ou**: premye biznis ak
   premye admin (`DEPLOYMENT.md`, Etap 5).

`api.js` konnen poukont li: sou konmbit.com li pale ak api.konmbit.com; sou
Live Server li toujou pale ak `localhost:8000`.

## 5. Backup chak jou

1. Render → `konmbit-db` → kopye **External Database URL**.
2. GitHub → repo → **Settings → Secrets and variables → Actions** →
   **New repository secret**:
   - `DATABASE_URL_BACKUP` = adrès ou fèk kopye a
   - `BACKUP_PASSPHRASE` = yon fraz long ou envante
3. **Sere fraz la yon lòt kote** (papye, jeretè modpas). San li, backup yo
   pa ka louvri — menm pa ou.
4. Actions → **Backup** → **Run workflow** pou fè premye backup la kounye a.

**Teste yon retablisman omwen yon fwa** sou yon baz jetab. Yon backup ou poko
janm retabli se yon backup ou pa sèten li mache.

## Chèklis

- [ ] Sekrè yo chanje (DEPLOYMENT.md, Etap 0)
- [ ] CI vèt, sitou "migrations-postgres"
- [ ] Blueprint aplike, SECRET_KEY antre
- [ ] DNS: api, www, konmbit.com
- [ ] /api/health reponn `ok`
- [ ] Premye biznis enskri
- [ ] Sekrè backup yo mete, premye backup fèt, retablisman teste
- [ ] **Pewòl la verifye pa yon kontab anvan premye vrè pewòl**
