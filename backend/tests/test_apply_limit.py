"""
Tès limit paj karyè a (login_guard.apply_blocked, routers/applications.py).
"""
import uuid

from app.config import settings
from app.database import SessionLocal
from app.models import AuthAttempt


def _clean():
    with SessionLocal() as db:
        db.query(AuthAttempt).filter(AuthAttempt.kind == "apply").delete()
        db.commit()


def _published_job(client, org):
    h = org["headers"]
    job = client.post("/api/jobs", json={"title": f"Kesye {uuid.uuid4().hex[:6]}",
                                         "description": "Travay tès."}, headers=h)
    assert job.status_code == 201, job.text
    pub = client.post(f"/api/jobs/{job.json()['id']}/publish", json={}, headers=h)
    assert pub.status_code == 200, pub.text
    return pub.json()["slug"]


def _apply(client, org, slug, application_answers, email):
    answers = application_answers(org["org_slug"], slug)
    return client.post(f"/api/applications/public/{org['org_slug']}/{slug}", json={
        "full_name": "Kandida Limit", "email": email, "answers": answers,
    })


def test_same_email_is_limited(client, org_admin, application_answers, monkeypatch):
    _clean()
    monkeypatch.setattr(settings, "apply_max_per_email_hour", 2)
    slug = _published_job(client, org_admin)
    email = f"limit-{uuid.uuid4().hex[:6]}@konbit-test.ht"
    for _ in range(2):
        r = _apply(client, org_admin, slug, application_answers, email)
        assert r.status_code == 201, r.text
    assert _apply(client, org_admin, slug, application_answers, email).status_code == 429


def test_same_connection_is_limited(client, org_admin, application_answers, monkeypatch):
    _clean()
    monkeypatch.setattr(settings, "apply_max_per_ip_hour", 3)
    slug = _published_job(client, org_admin)
    codes = [
        _apply(client, org_admin, slug, application_answers,
               f"robo-{uuid.uuid4().hex[:6]}@konbit-test.ht").status_code
        for _ in range(4)
    ]
    assert codes == [201, 201, 201, 429]
