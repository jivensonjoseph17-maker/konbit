from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.database import engine, Base
from app.config import settings
from app.routers import auth, companies, jobs, applications, offers, attendance, leaves

Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="Konbit API",
    description="API pou platfòm travay ak RH Ayiti",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_url],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(companies.router)
app.include_router(jobs.router)
app.include_router(applications.router)
app.include_router(offers.router)
app.include_router(attendance.router)
app.include_router(leaves.router)

@app.get("/")
def root():
    return {
        "message": "Byenveni sou Konbit API",
        "version": "1.0.0",
        "description": "Platfòm travay ak RH pou Ayiti"
    }

@app.get("/health")
def health():
    return {"status": "healthy", "service": "konbit-api"}