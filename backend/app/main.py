"""
Konbit — Pwen antre aplikasyon an
Chemen: backend/app/main.py
"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, status
from fastapi.exception_handlers import http_exception_handler
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text
from starlette.exceptions import HTTPException as StarletteHTTPException

from .config import settings
from .database import engine
from .i18n import resolve_language, translate, translate_detail, validation_message

# --- Router ki aktif ---
from .routers import (
    auth, employees, hierarchy, attendance, leaves,
    payroll, training, feedback,
    jobs, applications, offers, application_questions, timesheets,
    calculator, schedules, positions, portal, kiosk, team, admin, organization,
    payroll_exports, audit, org_logo, geofence, payment_changes, my_profile,
    notifications, employee_import, employee_photos, salary_advances,
    candidate, mfa, legal, org_data,
)

# --- Router ki poko pare ---
# Ansyen fichye sa yo t ap refere ak ansyen modèl yo. Dekomante chak liy
# sèlman lè fichye a reekri pou nouvo schema a.
# from .routers import companies

logging.basicConfig(
    level=logging.DEBUG if settings.debug else logging.INFO,
    format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
)
logger = logging.getLogger("konbit")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Pa gen create_all isit: se Alembic sèlman ki kreye ak modifye tab yo.
    # Si ou chanje yon modèl: alembic revision --autogenerate -m "..."
    # epi alembic upgrade head.
    logger.info("Konbit API demare — anviwonman: %s", settings.environment)
    yield
    engine.dispose()
    logger.info("Konbit API fèmen.")


app = FastAPI(
    title="Konbit API",
    description=(
        "Platfòm jesyon antrepriz ak resous imèn pou Ayiti.\n\n"
        "**Sonje:** tout montan lajan se an SANTIM. "
        "`4500000` vle di 45 000,00 HTG."
    ),
    version="0.1.0",
    lifespan=lifespan,
    docs_url=None if settings.is_production else "/docs",
    redoc_url=None if settings.is_production else "/redoc",
    openapi_url=None if settings.is_production else "/openapi.json",
)


# ---------------------------------------------------------------------------
# CORS
# ---------------------------------------------------------------------------

origins = list({settings.frontend_url, *settings.allowed_origins})
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "PUT", "DELETE", "OPTIONS"],
    # X-Kiosk-Token: tablèt pwentaj la (routers/kiosk.py), pa yon kont itilizatè.
    allow_headers=["Authorization", "Content-Type", "Accept-Language", "X-Kiosk-Token"],
    # Kite frontend lan li non fichye PDF yo (fich-peye-KB-0007-2026-09.pdf).
    expose_headers=["Content-Disposition"],
)


# ---------------------------------------------------------------------------
# HEADER SEKIRITE SOU REPONS API YO
#
# Repons yo gen salè, fich peye, nimewo kont: yon òdinatè pataje (sibè,
# biwo) pa dwe kenbe yo nan kach. setdefault: yon repons ki mete pwòp
# Cache-Control li (logo, foto) kenbe l.
# ---------------------------------------------------------------------------

@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers.setdefault("Cache-Control", "no-store")
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "no-referrer")
    return response


def cors_headers_for(request: Request) -> dict[str, str]:
    """
    Header CORS pou yon repons ki PA pase nan CORSMiddleware la (erè 500 yo).
    Sèlman pou yon orijin ki nan lis la — pa janm "*".
    """
    origin = request.headers.get("origin")
    if not origin or origin not in origins:
        return {}
    return {
        "Access-Control-Allow-Origin": origin,
        "Access-Control-Allow-Credentials": "true",
        "Access-Control-Expose-Headers": "Content-Disposition",
        "Vary": "Origin",
    }


# ---------------------------------------------------------------------------
# JESYON ERÈ
#
# Router yo ekri mesaj yo an kreyòl. Isit la nou tradui yo dapre header
# Accept-Language api.js voye a (ht / fr / en). Gade app/i18n.py.
# ---------------------------------------------------------------------------

def _request_language(request: Request) -> str:
    return resolve_language(request.headers.get("accept-language"))


@app.exception_handler(StarletteHTTPException)
async def translated_http_exception_handler(request: Request, exc: StarletteHTTPException):
    """Tout HTTPException (pa nou yo ak pa FastAPI yo) pase isit anvan yo pati."""
    lang = _request_language(request)
    translated = StarletteHTTPException(
        status_code=exc.status_code,
        detail=translate_detail(exc.detail, lang),
        headers=getattr(exc, "headers", None),
    )
    return await http_exception_handler(request, translated)


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """Mete erè validasyon yo nan yon fòm frontend lan ka sèvi avè l fasil."""
    lang = _request_language(request)
    errors = []
    for err in exc.errors():
        location = ".".join(str(p) for p in err.get("loc", []) if p != "body")
        errors.append({
            "field": location or "body",
            "message": validation_message(err, lang),
        })
    return JSONResponse(
        status_code=422,
        content={
            "detail": translate("Done ou voye yo pa valab.", lang),
            "errors": errors,
        },
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    """
    Nan pwodiksyon nou pa janm voye detay yon erè entèn bay kliyan an —
    trace la ka gen non tab, chemen fichye, menm valè done.

    Starlette voye erè sa yo depi ServerErrorMiddleware, ki DEYÒ
    CORSMiddleware. San cors_headers_for(), navigatè a bloke repons lan
    epi frontend lan di "Nou pa ka rive jwenn sèvè a" olye vrè mesaj la.
    """
    logger.exception("Erè pa jere sou %s %s", request.method, request.url.path)
    detail = (
        translate("Yon erè entèn rive.", _request_language(request))
        if settings.is_production
        else f"{type(exc).__name__}: {exc}"
    )
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": detail},
        headers=cors_headers_for(request),
    )


# ---------------------------------------------------------------------------
# SANTE SISTÈM LAN
# ---------------------------------------------------------------------------

@app.get("/api/health", tags=["Sistèm"])
def health():
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        db_ok = True
    except Exception:
        logger.exception("Verifikasyon baz done echwe")
        db_ok = False

    return {
        "status": "ok" if db_ok else "degraded",
        "database": db_ok,
        "environment": settings.environment,
        "version": app.version,
    }


@app.get("/", include_in_schema=False)
def root():
    return {
        "name": "Konbit API",
        "version": app.version,
        "docs": None if settings.is_production else "/docs",
    }


# ---------------------------------------------------------------------------
# ROUTER YO
# ---------------------------------------------------------------------------

app.include_router(auth.router,      prefix="/api/auth",      tags=["Otantifikasyon"])
app.include_router(employees.router, prefix="/api/employees", tags=["Anplwaye"])
app.include_router(hierarchy.router, prefix="/api/hierarchy", tags=["Òganigram"])
app.include_router(attendance.router, prefix="/api/attendance", tags=["Prezans"])
app.include_router(leaves.router,     prefix="/api/leaves",     tags=["Konje"])
app.include_router(payroll.router,    prefix="/api/payroll",    tags=["Pewòl"])
# Rapò ONA / OFATMA / DGI, fichye bank ak lis chèk/kach (CSV)
app.include_router(payroll_exports.router, prefix="/api/payroll", tags=["Pewòl"])
app.include_router(training.router,   prefix="/api/training",   tags=["Fòmasyon"])
app.include_router(feedback.router,   prefix="/api/feedback",   tags=["Fidbak"])
app.include_router(jobs.router,         prefix="/api/jobs",         tags=["Òf travay"])
app.include_router(applications.router, prefix="/api/applications", tags=["Aplikasyon"])
app.include_router(offers.router,       prefix="/api/offers",       tags=["Pwopozisyon"])
app.include_router(timesheets.router,   prefix="/api/timesheets",   tags=["Tan travay"])
app.include_router(schedules.router,    prefix="/api/schedules",    tags=["Orè travay"])
app.include_router(positions.router,    prefix="/api/positions",    tags=["Pozisyon"])
# Pòtay anplwaye: pwòp èdtan mwen, total ane a (sèlman done moun ki konekte a)
app.include_router(portal.router,       prefix="/api/portal",       tags=["Pòtay anplwaye"])
# Kiyòsk: tablèt biznis la + kòd pèsonèl (header X-Kiosk-Token)
app.include_router(kiosk.router,        prefix="/api/kiosk",        tags=["Kiyòsk"])
# Paj manadjè a: ekip mwen jodi a, konbyen bagay k ap tann
app.include_router(team.router,         prefix="/api/team",         tags=["Ekip"])
# Tablo jesyon: kòmanse ak KONMBIT, chif yo, pwochen pewòl, deklarasyon
app.include_router(admin.router,        prefix="/api/admin",        tags=["Tablo jesyon"])
# Paramèt biznis: non, logo, fizo orè, lajan, frekans pewòl
app.include_router(organization.router, prefix="/api/organization", tags=["Paramèt biznis"])
# Jounal odit: kiyès ki fè kisa (administratè biznis la sèlman)
app.include_router(audit.router,        prefix="/api/audit",        tags=["Jounal odit"])
# Logo biznis la: telechaje (admin), sèvi l piblikman (paj karyè, ba anlè), PDF
app.include_router(org_logo.router, tags=["Logo biznis"])
# Zòn otorize pou pwentaj sou telefòn (GPS)
app.include_router(geofence.router, tags=["Pwentaj"])
# Pòtay anplwaye: Dosye mwen, kòlèg mwen; demann chanjman peman (HR apwouve)
app.include_router(my_profile.router,      prefix="/api/profile",         tags=["Pòtay anplwaye"])
app.include_router(payment_changes.router, prefix="/api/payment-changes", tags=["Pewòl"])
# Avans sou salè: anplwaye a mande, manadjè/HR apwouve, pewòl la retire vèsman yo
app.include_router(salary_advances.router, prefix="/api/salary-advances", tags=["Pewòl"])
# Espas kandida: kont kandida (san biznis), aplikasyon, pwopozisyon (routers/candidate.py)
app.include_router(candidate.router, prefix="/api/candidate", tags=["Espas kandida"])
# Verifikasyon an 2 etap (TOTP): konfigirasyon, etap 2 koneksyon an, kòd sekou
app.include_router(mfa.router, prefix="/api/auth/mfa", tags=["Otantifikasyon"])
# Kondisyon itilizasyon, konfidansyalite, avètisman pewòl (app/legal.py)
app.include_router(legal.router, prefix="/api/legal", tags=["Legal"])
# Ekspòtasyon konplè ak fèmti biznis la (app/org_data.py)
app.include_router(org_data.router, prefix="/api/org-data", tags=["Legal"])
# Klòch notifikasyon (chak moun wè pa l sèlman) ak enpòtasyon anplwaye CSV (HR)
app.include_router(notifications.router,   prefix="/api/notifications",   tags=["Notifikasyon"])
app.include_router(employee_import.router, prefix="/api/employee-import", tags=["Anplwaye"])
# Foto pwofil: anplwaye a mete pa l, HR ka retire l; lyen ak kle aleyatwa
app.include_router(employee_photos.router, tags=["Foto pwofil"])
app.include_router(
    application_questions.router,
    prefix="/api/application-questions",
    tags=["Kesyon aplikasyon"],
)
# Piblik (san koneksyon): paj frontend/calculator.html
app.include_router(calculator.router, prefix="/api/calculator", tags=["Kalkilatè pewòl"])

# --- Poko pare ---
# app.include_router(companies.router,    prefix="/api/companies",    tags=["Biznis"])