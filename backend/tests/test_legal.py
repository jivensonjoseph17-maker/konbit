"""
Tès legal (app/legal.py, routers/legal.py): akseptasyon kondisyon yo nan
enskripsyon, avètisman pewòl avan premye apwobasyon an.
"""
import uuid

import pytest

import app.legal
from app.database import SessionLocal
from app.models import User


@pytest.fixture()
def enforce(monkeypatch):
    monkeypatch.setattr(app.legal, "ENFORCE_TERMS", True)
    monkeypatch.setattr(app.legal, "ENFORCE_PAYROLL_ACK", True)


def _signup_body(accept):
    unique = uuid.uuid4().hex[:8]
    return {
        "organization": {"name": f"Legal {unique}", "slug": f"legal-{unique}",
                         "country": "HT", "default_currency": "HTG"},
        "admin_full_name": "Admin Legal",
        "admin_email": f"legal-{unique}@konbit-test.ht",
        "admin_password": "TestPassw0rd2026",
        "accept_terms": accept,
    }


def test_business_signup_requires_terms(client, enforce):
    assert client.post("/api/auth/signup", json=_signup_body(False)).status_code == 400

    body = _signup_body(True)
    assert client.post("/api/auth/signup", json=body).status_code == 201
    with SessionLocal() as db:
        user = db.query(User).filter(User.email == body["admin_email"]).first()
        assert user.terms_version == app.legal.TERMS_VERSION
        assert user.terms_accepted_at is not None


def test_candidate_signup_requires_terms(client, enforce):
    email = f"kandida-legal-{uuid.uuid4().hex[:8]}@konbit-test.ht"
    body = {"full_name": "Kandida Legal", "email": email, "password": "KandidaModpas2026"}
    assert client.post("/api/candidate/signup", json={**body, "accept_terms": False}).status_code == 400
    assert client.post("/api/candidate/signup", json={**body, "accept_terms": True}).status_code == 200


def test_terms_version_is_public(client):
    r = client.get("/api/legal/terms")
    assert r.status_code == 200 and r.json()["version"] == app.legal.TERMS_VERSION


def _period_with_payslip(client, h, make_employee):
    make_employee(h, base_salary=4_500_000)
    p = client.post("/api/payroll/periods", json={
        "name": "Legal 01/2031", "start_date": "2031-01-01",
        "end_date": "2031-01-31", "pay_date": "2031-02-05",
    }, headers=h)
    assert p.status_code == 201, p.text
    pid = p.json()["id"]
    run = client.post(f"/api/payroll/periods/{pid}/run",
                      json={"pay_period_id": pid, "include_overtime": True}, headers=h)
    assert run.status_code == 200, run.text
    return pid


def test_payroll_approval_needs_the_warning_once(client, org_admin, make_employee, enforce):
    h = org_admin["headers"]
    pid = _period_with_payslip(client, h, make_employee)

    assert client.post(f"/api/payroll/periods/{pid}/approve", headers=h).status_code == 409

    first = client.post("/api/legal/payroll-ack", headers=h).json()
    assert first["accepted"] is True and first["accepted_by"] == "Admin Tès"
    again = client.post("/api/legal/payroll-ack", headers=h).json()
    assert again["accepted_at"] == first["accepted_at"]          # premye a rete

    assert client.post(f"/api/payroll/periods/{pid}/approve", headers=h).status_code == 200


def test_only_hr_confirms_the_payroll_warning(client, org_admin, make_employee_login):
    worker = make_employee_login(org_admin["headers"])["headers"]
    assert client.post("/api/legal/payroll-ack", headers=worker).status_code == 403
    assert client.get("/api/legal/payroll-ack", headers=org_admin["headers"]).json()["accepted"] is False