import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.database import SessionLocal, engine, Base

client = TestClient(app)

# Kreye tab yo chak fwa
Base.metadata.create_all(bind=engine)

def test_root():
    response = client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert data["message"] == "Byenveni sou Konbit API"

def test_health():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "healthy"

def test_register_and_login():
    # Kreye yon itilizatè
    resp = client.post("/auth/register", json={
        "email": "test@konbit.ht",
        "password": "testpass123",
        "full_name": "Test User",
        "phone": "50912345678",
        "role": "job_seeker"
    })
    assert resp.status_code == 200

    # Konekte
    resp = client.post("/auth/login", json={
        "email": "test@konbit.ht",
        "password": "testpass123"
    })
    assert resp.status_code == 200
    assert "access_token" in resp.json()
