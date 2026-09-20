"""
Konbit — Pwen antre aplikasyon an
Chemen: backend/app/main.py
"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text

from .config import settings
from .database import Base, engine

# Router yo. Dekomante chak liy lè fichye a genyen yon `router = APIRouter()`.
from .routers import auth
# from .routers import companies, employees, hierarchy
# from .routers import jobs, applications, offers
# from .routers import attendance, leaves
# from .routers import payroll, training, feedback

logger = logging.getLogger("konbit")
logging.basicConfig(level=logging.INFO if not settings.debug else logging.DEBUG)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Nan devlopman sèlman: kreye tab yo otomatikman.
    # Nan pwodiksyon se Alembic ki fè travay sa a.
    if not settings.is_production:
        Base.metadata.create_all(bind=engine)
        logger.info("Tab yo kreye (mòd devlopman).")
    yield
    engine.dispose()


app = FastAPI(
    title="Konbit API",
    description="Platfòm jesyon antrepriz ak resous imèn pou Ayiti.",
    version="0.1.0",
    lifespan=lifespan,
    docs_url=None if settings.is_production else "/docs",
    redoc_url=None if settings.is_production else "/redoc",
)

# --- CORS ---
origins = list({settings.frontend_url, *settings.allowed_origins})
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "Accept-Language"],
)


# --- Jesyon erè ---
@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    """
    Pa janm voye detay yon erè entèn bay kliyan an nan pwodiksyon —
    trace la ka gen non tab, chemen fichye, menm valè done.
    """
    logger.exception("Erè pa jere sou %s %s", request.method, request.url.path)
    detail = str(exc) if not settings.is_production else "Yon erè entèn rive."
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": detail},
    )


# --- Sante sistèm lan ---
@app.get("/api/health", tags=["Sistèm"])
def health():
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        db_ok = True
    except Exception:
        db_ok = False
    return {
        "status": "ok" if db_ok else "degraded",
        "database": db_ok,
        "environment": settings.environment,
        "version": app.version,
    }


# --- Router yo ---
app.include_router(auth.router, prefix="/api/auth", tags=["Otantifikasyon"])
# app.include_router(companies.router,    prefix="/api/companies",    tags=["Biznis"])
# app.include_router(employees.router,    prefix="/api/employees",    tags=["Anplwaye"])
# app.include_router(hierarchy.router,    prefix="/api/hierarchy",    tags=["Òganigram"])
# app.include_router(jobs.router,         prefix="/api/jobs",         tags=["Òf travay"])
# app.include_router(applications.router, prefix="/api/applications", tags=["Aplikasyon"])
# app.include_router(offers.router,       prefix="/api/offers",       tags=["Pwopozisyon"])
# app.include_router(attendance.router,   prefix="/api/attendance",   tags=["Prezans"])
# app.include_router(leaves.router,       prefix="/api/leaves",       tags=["Konje"])
# app.include_router(payroll.router,      prefix="/api/payroll",      tags=["Peyòl"])
# app.include_router(training.router,     prefix="/api/training",     tags=["Fòmasyon"])
# app.include_router(feedback.router,     prefix="/api/feedback",     tags=["Fidbak"])