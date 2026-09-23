"""
Konbit — Tès Rekritman: antrevi ak pwopozisyon
Chemen: backend/tests/test_recruitment.py

Sik konplè a: òf pibliye → kandida aplike → antrevi → pwopozisyon →
repons → anbochaj (Employee + User kreye ansanm).
"""

import uuid
from datetime import datetime, timedelta, timezone

import pytest

from app.database import SessionLocal
from app.models import Notification


# ---------------------------------------------------------------------------
# ZOUTI
# ---------------------------------------------------------------------------

@pytest.fixture()
def make_application(client):
    """Pibliye yon òf epi fè yon kandida aplike sou paj piblik la."""
    def _make(org, openings=1):
        h = org["headers"]
        job = client.post("/api/jobs", json={
            "title": f"Kesye {uuid.uuid4().hex[:6]}",
            "description": "Travay nan kès la.",
            "openings": openings,
        }, headers=h).json()
        pub = client.post(f"/api/jobs/{job['id']}/publish", json={}, headers=h)
        assert pub.status_code == 200, pub.text

        email = f"kandida-{uuid.uuid4().hex[:8]}@konbit-test.ht"
        resp = client.post(
            f"/api/applications/public/{org['org_slug']}/{job['slug']}",
            json={"full_name": "Jak Pòl", "email": email},
        )
        assert resp.status_code == 201, resp.text
        return {"id": resp.json()["application_id"], "job_id": job["id"], "email": email}
    return _make


def _application(client, org, app_id):
    resp = client.get(f"/api/applications/{app_id}", headers=org["headers"])
    assert resp.status_code == 200, resp.text
    return resp.json()


def _accepted_offer(client, org, app_id, **extra):
    h = org["headers"]
    body = {"application_id": app_id, "salary": 4_500_000, **extra}
    offer = client.post("/api/offers", json=body, headers=h)
    assert offer.status_code == 201, offer.text
    oid = offer.json()["id"]
    assert client.post(f"/api/offers/{oid}/send", headers=h).status_code == 200
    resp = client.post(f"/api/offers/{oid}/respond", json={"accept": True}, headers=h)
    assert resp.status_code == 200, resp.text
    return oid


# ---------------------------------------------------------------------------
# ANTREVI
# ---------------------------------------------------------------------------

def test_interview_without_timezone_is_rejected(client, org_admin, make_application):
    app = make_application(org_admin)
    resp = client.post(f"/api/applications/{app['id']}/interviews", json={
        "application_id": app["id"],
        "scheduled_at": "2027-01-15T10:00",          # sa datetime-local voye
    }, headers=org_admin["headers"])
    assert resp.status_code == 422


def test_interview_stored_in_utc_and_notification_in_haiti_time(
    client, org_admin, make_application, make_employee_login,
):
    interviewer = make_employee_login(org_admin["headers"])["employee"]
    app = make_application(org_admin)

    # 10è maten lè Ayiti an janvye (UTC-5) = 15è UTC
    resp = client.post(f"/api/applications/{app['id']}/interviews", json={
        "application_id": app["id"],
        "interviewer_id": interviewer["id"],
        "scheduled_at": "2027-01-15T10:00:00-05:00",
    }, headers=org_admin["headers"])
    assert resp.status_code == 201, resp.text

    detail = _application(client, org_admin, app["id"])
    assert detail["application"]["stage"] == "interview"
    assert detail["interviews"][0]["scheduled_at"].startswith("2027-01-15T15:00")

    with SessionLocal() as db:
        note = db.query(Notification).filter(
            Notification.user_id == interviewer["user_id"],
            Notification.title == "Antrevi planifye",
        ).first()
    assert note is not None
    assert "15/01/2027 10:00" in note.body


def test_reschedule_without_timezone_is_rejected(client, org_admin, make_application):
    app = make_application(org_admin)
    iv = client.post(f"/api/applications/{app['id']}/interviews", json={
        "application_id": app["id"],
        "scheduled_at": "2027-01-15T15:00:00Z",
    }, headers=org_admin["headers"]).json()

    resp = client.patch(f"/api/applications/interviews/{iv['id']}", json={
        "scheduled_at": "2027-01-16T10:00",
    }, headers=org_admin["headers"])
    assert resp.status_code == 422


def test_upcoming_interviews_lists_future_interview(client, org_admin, make_application):
    app = make_application(org_admin)
    soon = (datetime.now(timezone.utc) + timedelta(days=2)).isoformat()
    iv = client.post(f"/api/applications/{app['id']}/interviews", json={
        "application_id": app["id"], "scheduled_at": soon,
    }, headers=org_admin["headers"]).json()

    resp = client.get("/api/applications/interviews/upcoming", headers=org_admin["headers"])
    assert resp.status_code == 200, resp.text
    ids = [item["interview"]["id"] for item in resp.json()["items"]]
    assert iv["id"] in ids


# ---------------------------------------------------------------------------
# PWOPOZISYON
# ---------------------------------------------------------------------------

def test_offer_expiry_without_timezone_is_rejected(client, org_admin, make_application):
    app = make_application(org_admin)
    resp = client.post("/api/offers", json={
        "application_id": app["id"], "salary": 4_500_000,
        "expires_at": "2027-01-31T17:00",
    }, headers=org_admin["headers"])
    assert resp.status_code == 422


def test_only_one_active_offer_per_candidate(client, org_admin, make_application):
    app = make_application(org_admin)
    body = {"application_id": app["id"], "salary": 4_500_000}
    first = client.post("/api/offers", json=body, headers=org_admin["headers"])
    assert first.status_code == 201
    second = client.post("/api/offers", json=body, headers=org_admin["headers"])
    assert second.status_code == 409


def test_declined_offer_withdraws_candidate_and_blocks_hire(client, org_admin, make_application):
    h = org_admin["headers"]
    app = make_application(org_admin)
    oid = client.post("/api/offers", json={
        "application_id": app["id"], "salary": 4_500_000,
    }, headers=h).json()["id"]
    client.post(f"/api/offers/{oid}/send", headers=h)

    resp = client.post(f"/api/offers/{oid}/respond", json={"accept": False}, headers=h)
    assert resp.status_code == 200
    assert _application(client, org_admin, app["id"])["application"]["stage"] == "withdrawn"

    hire = client.post(f"/api/offers/{oid}/hire",
                       json={"first_name": "Jak", "last_name": "Pòl"}, headers=h)
    assert hire.status_code == 400


def test_full_hire_creates_employee_and_login(client, org_admin, make_application):
    h = org_admin["headers"]
    app = make_application(org_admin, openings=1)
    oid = _accepted_offer(client, org_admin, app["id"], start_date="2026-11-02")

    resp = client.post(f"/api/offers/{oid}/hire",
                       json={"first_name": "Jak", "last_name": "Pòl"}, headers=h)
    assert resp.status_code == 201, resp.text
    result = resp.json()

    emp = result["employee"]
    assert emp["base_salary"] == 4_500_000
    assert emp["hire_date"] == "2026-11-02"
    assert emp["status"] == "active"
    assert result["job_closed"] is True          # sèl pòs la ranpli
    assert result["remaining_openings"] == 0
    assert result["temporary_password"]

    assert _application(client, org_admin, app["id"])["application"]["stage"] == "hired"

    login = client.post("/api/auth/login", json={
        "email": result["login_email"], "password": result["temporary_password"],
    })
    assert login.status_code == 200, login.text


def test_cannot_hire_same_candidate_twice(client, org_admin, make_application):
    h = org_admin["headers"]
    app = make_application(org_admin, openings=2)
    oid = _accepted_offer(client, org_admin, app["id"])
    body = {"first_name": "Jak", "last_name": "Pòl", "create_login": False}

    assert client.post(f"/api/offers/{oid}/hire", json=body, headers=h).status_code == 201
    assert client.post(f"/api/offers/{oid}/hire", json=body, headers=h).status_code == 400


def test_other_org_cannot_see_offer(client, make_org, make_application):
    org_a, org_b = make_org(), make_org()
    app = make_application(org_a)
    oid = client.post("/api/offers", json={
        "application_id": app["id"], "salary": 4_500_000,
    }, headers=org_a["headers"]).json()["id"]

    assert client.get(f"/api/offers/{oid}", headers=org_b["headers"]).status_code == 404