"""
Konbit — Konfigirasyon pataje pou tès yo
Chemen: backend/tests/conftest.py

REMAK ENPÒTAN — poukisa `create_all()` isit la, alòske `database.py` di
"se Alembic sèlman ki kreye tab yo": pou tès, nou vle yon baz done FRÈ,
RAPID, ak izole chak fwa nou kouri sit la — kouri Alembic pa etap pa etap
pou sa ta pi lan san anpil benefis. Konpwomi sa a vle di: si yon jou yon
migrasyon Alembic vin diferan de `models.py` (egzanp: yon moun chanje yon
kolòn nan modèl la san l pa jenere yon migrasyon), tès yo p ap detekte sa.
Se yon chwa rezonab pou yon ti baz done SQLite; pa fè menm bagay la pou
yon vrè migrasyon nan pwodiksyon.

ITILIZASYON: kouri `pytest` soti nan `backend/` (menm dosye ak `.env`),
menm jan ak `uvicorn` ak `alembic`.
"""

import os
import uuid
from pathlib import Path

# Dwe fèt AVAN nenpòt enpòtasyon `app.*` — pydantic-settings pran yon
# varyab anviwonman anvan valè `.env` la, kidonk sa a fòse yon baz done
# SEPARE pou tès yo, pa touche `konbit.db` devlopman an.
os.environ["DATABASE_URL"] = "sqlite:///./test_konbit.db"

import pytest
from fastapi.testclient import TestClient

from app.database import Base, engine
from app.main import app

TEST_DB_FILE = Path("test_konbit.db")


@pytest.fixture(scope="session", autouse=True)
def _test_database():
    """Bati tab yo yon sèl fwa pou tout sesyon an, netwaye apre."""
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)
    engine.dispose()
    if TEST_DB_FILE.exists():
        TEST_DB_FILE.unlink()


@pytest.fixture()
def client():
    return TestClient(app)


@pytest.fixture()
def make_org(client):
    """
    Retounen yon fonksyon ki enskri yon NOUVO biznis + admin chak fwa yo
    rele l — sa pèmèt tès ki bezwen DE biznis (egzanp: izolasyon
    milti-tenant) rele l de fwa san konfli.
    """
    def _make():
        unique = uuid.uuid4().hex[:8]
        payload = {
            "organization": {
                "name": f"Biznis Tès {unique}",
                "slug": f"tes-{unique}",
                "country": "HT",
                "default_currency": "HTG",
            },
            "admin_full_name": "Admin Tès",
            "admin_email": f"admin-{unique}@konbit-test.ht",
            "admin_password": "TestPassw0rd2026",
        }
        resp = client.post("/api/auth/signup", json=payload)
        assert resp.status_code == 201, resp.text
        tokens = resp.json()
        return {
            "headers": {"Authorization": f"Bearer {tokens['access_token']}"},
            "email": payload["admin_email"],
            "password": payload["admin_password"],
            "org_slug": payload["organization"]["slug"],
        }
    return _make


@pytest.fixture()
def org_admin(make_org):
    """Yon sèl biznis + admin — sa a sèvi pou pifò tès ki pa bezwen 2 biznis."""
    return make_org()


@pytest.fixture()
def make_employee(client):
    """
    Fonksyon pou kreye yon anplwaye nan yon biznis. Pa defo, san kont
    koneksyon (`create_login=False`) — pi rapid pou tès ki jis bezwen yon
    `employee_id`. Pase `create_login=True` ak yon `personal_email` si yon
    tès bezwen konekte kòm anplwaye a limenm.
    """
    def _make(headers, **overrides):
        unique = uuid.uuid4().hex[:6]
        payload = {
            "first_name": "Mari",
            "last_name": f"Dorvil{unique}",
            "hire_date": "2026-01-15",
            "create_login": False,
        }
        payload.update(overrides)
        resp = client.post("/api/employees", json=payload, headers=headers)
        assert resp.status_code == 201, resp.text
        return resp.json()
    return _make


@pytest.fixture()
def make_employee_login(client, make_employee):
    """
    Kreye yon anplwaye AK yon kont koneksyon, epi konekte kòm li.
    Itil pou tès "sèvis pwòp tèt li" (fè yon demann konje, gade fòmasyon
    pa li...) kote nou bezwen yon token ki lye ak yon Employee, pa yon
    User HR san dosye anplwaye.
    """
    def _make(hr_headers, **overrides):
        unique = uuid.uuid4().hex[:6]
        email = f"anplwaye-{unique}@konbit-test.ht"
        overrides.setdefault("personal_email", email)
        overrides.setdefault("create_login", True)
        result = make_employee(hr_headers, **overrides)

        login = client.post("/api/auth/login", json={
            "email": result["login_email"],
            "password": result["temporary_password"],
        })
        assert login.status_code == 200, login.text
        token = login.json()["access_token"]
        return {
            "employee": result["employee"],
            "headers": {"Authorization": f"Bearer {token}"},
        }
    return _make