"""
Konbit — Pwen antre aplikasyon an
Chemen: backend/app/main.py
"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text

from .config import settings
from .database import Base, engine

# --- Router ki aktif ---
from .routers import (
    auth, employees, hierarchy, attendance, leaves,
    payroll, training, feedback,
    jobs, applications, offers,
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
    # Nan devlopman sèlman: kreye tab yo otomatikman.
    # Nan pwodiksyon se Alembic ki fè travay sa a.
    if not settings.is_production:
        Base.metadata.create_all(bind=engine)
        logger.info("Tab yo kreye (mòd devlopman).")
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
    allow_headers=["Authorization", "Content-Type", "Accept-Language"],
)


# ---------------------------------------------------------------------------
# JESYON ERÈ
# ---------------------------------------------------------------------------

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """Mete erè validasyon yo nan yon fòm frontend lan ka sèvi avè l fasil."""
    errors = []
    for err in exc.errors():
        location = ".".join(str(p) for p in err.get("loc", []) if p != "body")
        errors.append({"field": location or "body", "message": err.get("msg", "")})
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={"detail": "Done ou voye yo pa valab.", "errors": errors},
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    """
    Nan pwodiksyon nou pa janm voye detay yon erè entèn bay kliyan an —
    trace la ka gen non tab, chemen fichye, menm valè done.
    """
    logger.exception("Erè pa jere sou %s %s", request.method, request.url.path)
    detail = (
        "Yon erè entèn rive."
        if settings.is_production
        else f"{type(exc).__name__}: {exc}"
    )
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": detail},
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
app.include_router(payroll.router,    prefix="/api/payroll",    tags=["Peyòl"])
app.include_router(training.router,   prefix="/api/training",   tags=["Fòmasyon"])
app.include_router(feedback.router,   prefix="/api/feedback",   tags=["Fidbak"])
app.include_router(jobs.router,         prefix="/api/jobs",         tags=["Òf travay"])
app.include_router(applications.router, prefix="/api/applications", tags=["Aplikasyon"])
app.include_router(offers.router,       prefix="/api/offers",       tags=["Pwopozisyon"])

# --- Poko pare ---
# app.include_router(companies.router,    prefix="/api/companies",    tags=["Biznis"])