"""
Tès espas kandida (routers/candidate.py) — pati C1.
Aplikasyon ak pwopozisyon yo kreye dirèk nan baz done a pou tès yo rete kout.
"""
import re
import uuid

from app.database import SessionLocal
from app.mailer import OUTBOX
from app.models import (
    Application, ApplicationStage, JobPosting, JobStatus, Offer, OfferStatus, Organization,
)

PASSWORD = "KandidaModpas2026"


def _mails_to(email):
    return [m for m in OUTBOX if m.to == email]


def _token(mail):
    match = re.search(r"#([A-Za-z0-9_-]{20,})", mail.text)
    assert match, mail.text
    return match.group(1)


def _candidate(client, verified=True):
    """Kont kandida (verifye pa defo). Retounen (imel, headers)."""
    email = f"kandida-{uuid.uuid4().hex[:8]}@konbit-test.ht"
    r = client.post("/api/candidate/signup", json={
        "full_name": "Kandida Tès", "email": email, "password": PASSWORD,
    })
    assert r.status_code == 200, r.text
    if verified:
        token = _token(_mails_to(email)[-1])
        assert client.post("/api/auth/verify-email", json={"token": token}).status_code == 200
    login = client.post("/api/auth/login", json={"email": email, "password": PASSWORD})
    assert login.status_code == 200, login.text
    return email, {"Authorization": f"Bearer {login.json()['access_token']}"}


def _application(org_slug, email, stage=ApplicationStage.RECEIVED, offer_status=None):
    """Yon òf travay + yon aplikasyon (ak nòt entèn sekrè) + opsyonèlman yon pwopozisyon."""
    unique = uuid.uuid4().hex[:8]
    with SessionLocal() as db:
        org = db.query(Organization).filter(Organization.slug == org_slug).first()
        job = JobPosting(organization_id=org.id, title=f"Pòs {unique}", slug=f"pos-{unique}",
                         status=JobStatus.PUBLISHED, openings=2)
        db.add(job)
        db.flush()
        app = Application(organization_id=org.id, job_posting_id=job.id, full_name="Kandida Tès",
                          email=email, stage=stage, rating=5, internal_notes="Nòt entèn SEKRÈ")
        db.add(app)
        db.flush()
        offer_id = None
        if offer_status is not None:
            offer = Offer(organization_id=org.id, application_id=app.id,
                          salary=4_500_000, status=offer_status)
            db.add(offer)
            db.flush()
            offer_id = offer.id
        db.commit()
        return app.id, offer_id


# ---------------------------------------------------------------------------
# ENSKRIPSYON
# ---------------------------------------------------------------------------

def test_signup_answer_is_the_same_for_existing_email(client):
    email = f"kandida-{uuid.uuid4().hex[:8]}@konbit-test.ht"
    body = {"full_name": "Kandida Tès", "email": email, "password": PASSWORD}

    first = client.post("/api/candidate/signup", json=body)
    second = client.post("/api/candidate/signup", json=body)
    assert first.status_code == second.status_code == 200
    assert first.json()["detail"] == second.json()["detail"]

    mails = _mails_to(email)
    assert len(mails) == 2
    assert "verify-email.html#" in mails[0].text          # 1: lyen verifikasyon
    assert "login.html#bliye" in mails[1].text            # 2: "ou deja gen yon kont"


def test_unverified_candidate_is_blocked(client):
    _, h = _candidate(client, verified=False)
    assert client.get("/api/candidate/applications", headers=h).status_code == 403


# ---------------------------------------------------------------------------
# APLIKASYON YO
# ---------------------------------------------------------------------------

def test_candidate_sees_own_applications_only_and_no_internal_fields(client, make_org):
    a, b = make_org(), make_org()
    email, h = _candidate(client)
    _application(a["org_slug"], email)
    _application(b["org_slug"], email.upper())             # menm imel, lòt biznis
    _application(a["org_slug"], "yon-lot-moun@konbit-test.ht")

    r = client.get("/api/candidate/applications", headers=h)
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["total"] == 2
    assert {i["status"] for i in data["items"]} == {"received"}
    assert "SEKRÈ" not in r.text
    assert "internal_notes" not in r.text and "rating" not in r.text


def test_candidate_has_no_access_to_business_endpoints(client, org_admin):
    _, h = _candidate(client)
    for path in ("/api/employees", "/api/payroll/periods", "/api/leaves/pending", "/api/jobs"):
        assert client.get(path, headers=h).status_code in (400, 403), path
    # E yon kont biznis pa ka sèvi ak espas kandida a
    assert client.get("/api/candidate/applications", headers=org_admin["headers"]).status_code == 403


def test_candidate_withdraws_application(client, org_admin):
    email, h = _candidate(client)
    app_id, _ = _application(org_admin["org_slug"], email)

    r = client.post(f"/api/candidate/applications/{app_id}/withdraw", headers=h)
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "withdrawn"
    assert client.post(f"/api/candidate/applications/{app_id}/withdraw", headers=h).status_code == 400


# ---------------------------------------------------------------------------
# PWOPOZISYON
# ---------------------------------------------------------------------------

def test_candidate_accepts_offer_and_hr_sees_it(client, org_admin):
    email, h = _candidate(client)
    _, offer_id = _application(org_admin["org_slug"], email, ApplicationStage.OFFER, OfferStatus.SENT)

    listed = client.get("/api/candidate/applications", headers=h).json()["items"][0]
    assert listed["offer"]["can_respond"] is True

    r = client.post(f"/api/candidate/offers/{offer_id}/respond", json={"accept": True}, headers=h)
    assert r.status_code == 200, r.text
    assert r.json()["offer"]["status"] == "accepted"

    hr = client.get(f"/api/offers/{offer_id}", headers=org_admin["headers"])
    assert hr.json()["offer"]["status"] == "accepted"


def test_declining_offer_withdraws_application(client, org_admin):
    email, h = _candidate(client)
    _, offer_id = _application(org_admin["org_slug"], email, ApplicationStage.OFFER, OfferStatus.SENT)

    r = client.post(f"/api/candidate/offers/{offer_id}/respond",
                    json={"accept": False, "note": "Mwen jwenn yon lòt travay."}, headers=h)
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "withdrawn"
    assert r.json()["offer"]["status"] == "declined"


def test_cannot_respond_to_someone_elses_offer(client, org_admin):
    _, h = _candidate(client)
    _, offer_id = _application(org_admin["org_slug"], "yon-lot@konbit-test.ht",
                               ApplicationStage.OFFER, OfferStatus.SENT)
    r = client.post(f"/api/candidate/offers/{offer_id}/respond", json={"accept": True}, headers=h)
    assert r.status_code == 404


def test_hr_sending_offer_emails_the_candidate(client, org_admin):
    email = f"kandida-{uuid.uuid4().hex[:8]}@konbit-test.ht"
    _, offer_id = _application(org_admin["org_slug"], email,
                               ApplicationStage.INTERVIEW, OfferStatus.DRAFT)

    r = client.post(f"/api/offers/{offer_id}/send", headers=org_admin["headers"])
    assert r.status_code == 200, r.text
    mails = _mails_to(email)
    assert mails and "candidate.html" in mails[-1].text