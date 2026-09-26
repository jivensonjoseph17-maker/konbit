# 🇭🇹 KONMBIT

**KONMBIT** se yon platfòm jesyon resous imen (HRIS) ki fèt espesyalman pou biznis ayisyen — tankou Workday, an Kreyòl.

## Deskripsyon

KONMBIT pèmèt yon biznis jere:
- **Anplwaye** — dosye, wòl, chèn manadjè
- **Prezans** — pwentaj antre/soti, ak fizo orè biznis la (America/Port-au-Prince)
- **Konje** — demann, apwobasyon, balans pa kalite konje
- **Pewòl** — kalkil an santim (IRI, ONA, OFATMA, CFGDCT, FDU/CAS)
- **Rekritman** — òf travay, pipeline kandida
- **Fòmasyon** — kou ak leson videyo, swiv pwogrè

Chak biznis ki enskri (milti-tenant) gen done l izole nèt de lòt biznis yo.

## Teknoloji

- **Backend:** FastAPI + SQLAlchemy + Alembic — SQLite an devlopman, PostgreSQL an pwodiksyon
- **Sekirite:** JWT (access + refresh token) + bcrypt
- **Frontend:** HTML/JS senp (san framework), Live Server pou devlopman
- **Lang:** Python 3.14

## Enstalasyon (devlopman lokal)

### 1. Klon repo a
```bash
git clone https://github.com/jivensonjoseph17-maker/konbit.git
cd konbit/backend
```

### 2. Kreye environman virtual
```bash
python -m venv venv
venv\Scripts\activate      # Windows
# source venv/bin/activate # Linux/Mac
```

### 3. Enstale dependans yo
```bash
pip install -r requirements.txt
```

### 4. Kreye fichye `.env` (nan `backend/`, jamè komite l nan Git)
```env
DATABASE_URL=sqlite:///./konbit.db
SECRET_KEY=chanje-kle-sa-a-pou-yon-bagay-aleatwa-epi-long
```

### 5. Kreye tab yo
```bash
alembic upgrade head
```

### 6. Demare sèvè a
```bash
uvicorn app.main:app --reload
```

### 7. Frontend la
Ouvri dosye `frontend/` ak Live Server (pò 5500). Li pale ak backend la sou
`http://localhost:8000` pa defo (`api.js`, varyab `window.KONBIT_API_URL`).

## Dokimantasyon API

Yon fwa sèvè a ap mache:
- **Swagger UI:** http://localhost:8000/docs
- **ReDoc:** http://localhost:8000/redoc

## Wout prensipal yo (tout anba `/api`)

| Wout | Deskripsyon |
|---|---|
| `POST /api/auth/signup` | Enskri yon nouvo biznis + premye admin |
| `POST /api/auth/login` | Konekte |
| `GET /api/auth/identity` | Idantite + wòl moun konekte a |
| `GET /POST /api/employees` | Jesyon anplwaye |
| `GET /POST /api/attendance` | Pwentaj (klòk antre/soti) |
| `GET /POST /api/leaves` | Demann konje ak balans |
| `GET /POST /api/payroll` | Peryòd pewòl |
| `GET /POST /api/jobs` | Òf travay (Rekritman) |
| `GET /POST /api/applications` | Pipeline kandida |
| `GET /POST /api/training` | Kou ak fòmasyon |

Lis konplè ak schema chak wout: gade Swagger UI (`/docs`) yon fwa sèvè a ap mache.

## Estrikti repo a

```
konbit/
├── backend/
│   ├── app/
│   │   ├── main.py            # Point antre FastAPI
│   │   ├── config.py          # Konfigirasyon (li .env)
│   │   ├── database.py        # Koneksyon SQLAlchemy
│   │   ├── models.py          # Modèl yo
│   │   ├── schemas.py         # Validasyon Pydantic
│   │   ├── deps.py            # Depandans pataje (tenant, wòl)
│   │   ├── security.py        # JWT, hachaj modpas
│   │   ├── timezone_utils.py  # Fizo orè biznis la (pataje ant router yo)
│   │   └── routers/           # Yon fichye pa modil (auth, employees, leaves...)
│   ├── alembic/                # Migrasyon baz done
│   ├── tests/                  # pytest (conftest.py + test_*.py)
│   ├── requirements.txt
│   └── .env                    # Pa janm komite sa!
├── frontend/
│   ├── index.html, login.html, dashboard.html, employees.html...
│   ├── api.js                  # Kliyan API, refresh token, fòma
│   ├── shell.js                # Meni sou kote + ba anlè, pataje ant tout paj
│   └── app.css
├── DEPLOYMENT.md                # Gid deplwaman pwodiksyon (PostgreSQL, sekrè, CORS...)
└── .gitignore
```

## Tès

```bash
cd backend
pytest -v
```

## Kontribye

1. Fè yon **fork** nan repo a
2. Kreye yon branch: `git checkout -b fonksyonalite-mwen`
3. Fè chanjman ou yo, ajoute tès si sa aplikab (`backend/tests/`)
4. Pouse: `git push origin fonksyonalite-mwen`
5. Ouvri yon **Pull Request**

## Deplwaman

Gade [`DEPLOYMENT.md`](../DEPLOYMENT.md) nan rasin repo a pou gid pwodiksyon
konplè (PostgreSQL, sekrè, CORS, backup, elt.).

## Lisans

MIT License — Lib pou itilize ak modifye.

---
**Fèt ak ❤️ pou Ayiti**
