# 🇭🇹 Konbit

**Konbit** se yon platfòm travay ak jesyon resous imen (RH) ki fèt espesyalman pou Ayiti.

## Deskripsyon

Konbit pèmèt:
- **Chèchè travay** kreye pwofil, aplike pou travay, ak jere karyè yo
- **Biznis** pibliye travay, anboche employe, ak jere prezans yo
- **Manadjè** swiv konje, voye of, ak jene rapò RH

## Teknoloji

- **Backend:** FastAPI + SQLAlchemy + SQLite
- **Sekirite:** JWT + bcrypt
- **Peman:** MonCash + NatCash
- **Lang:** Python 3.11+

## Enstalasyon

### 1. Klon repo a
```bash
git clone https://github.com/jivensonjoseph17-maker/konbit.git
cd konbit
```

### 2. Kreye environman virtual
```bash
python -m venv venv
venv\Scripts\activate  # Windows
# source venv/bin/activate  # Linux/Mac
```

### 3. Enstale dependans yo
```bash
pip install -r requirements.txt
```

### 4. Kreye fichye `.env`
```env
DATABASE_URL=sqlite:///./konbit.db
SECRET_KEY=chanje-kle-sa-a-pou-yon-bagay-aleatoire-epi-long
```

### 5. Demare sèvè a
```bash
python run.py
```

## Dokimantasyon API

Yon fwa sèvè a ap mache, ou ka wè dokimantasyon an nan:
- **Swagger UI:** http://localhost:8000/docs
- **ReDoc:** http://localhost:8000/redoc

## Endpoint prensipal yo

| Endpoint | Deskripsyon |
|----------|-------------|
| `POST /auth/register` | Kreye kont nouvo |
| `POST /auth/login` | Konekte |
| `GET /auth/me` | Wè pwofil ou |
| `POST /companies` | Kreye konpayi |
| `POST /jobs` | Pibliye travay |
| `GET /jobs` | Lisyen travay yo |
| `POST /applications/{job_id}` | Aplike pou travay |
| `POST /employees/hire/{user_id}` | Anboche yon moun |
| `POST /attendance/clock-in` | Pointe antre |
| `POST /attendance/clock-out` | Pointe soti |
| `POST /leaves` | Demann konje |

## Strukti Pwojè a

```
konbit/
├── app/
│   ├── __init__.py
│   ├── main.py           # Point antre FastAPI
│   ├── config.py         # Konfigirasyon
│   ├── database.py       # Koneksyon SQLite
│   ├── models.py         # Modèl SQLAlchemy
│   ├── schemas.py        # Validasyon Pydantic
│   ├── auth.py           # JWT & Sekirite
│   ├── routers/          # Endpoint yo
│   │   ├── auth.py
│   │   ├── companies.py
│   │   ├── jobs.py
│   │   ├── applications.py
│   │   ├── offers.py
│   │   ├── attendance.py
│   │   ├── leaves.py
│   │   └── employees.py
│   └── services/         # Sèvis ekstèn
│       ├── moncash_service.py
│       └── natcash_service.py
├── tests/                # Tès yo
├── requirements.txt
├── .env                  # Pa pataje sa!
├── .gitignore
└── run.py                # Demare app la
```

## Kontribye

1. Fè yon **fork** nan repo a
2. Kreye yon branch: `git checkout -b fonksyonalite-mwen`
3. Fè chanjman ou yo
4. Pouse: `git push origin fonksyonalite-mwen`
5. Ouvri yon **Pull Request**

## Lisans

MIT License - Lib pou itilize ak modifye.

---
**Fèt ak ❤️ pou Ayiti**
