"""
Tès pwoteksyon koneksyon (pati A): blokaj tanporè, limit pa IP ak pa imel,
revokasyon token (token_version), wòl HR pa ka bay, biznis dezaktive.

Chak tès efase tab auth_attempts anvan: tout tès yo soti nan menm IP
(testclient), e conftest.py leve limit yo pou lòt tès yo.
"""
import uuid
from datetime import datetime, timedelta, timezone

from app.config import settings
from app.database import SessionLocal
from app.models import AuthAttempt, Organization

WRONG = "MoveModpas2026x"
NEW_PASSWORD = "BonModpas2026x"
TOO_MANY = "Twòp esè. Tann kèk minit."


def _clean_attempts():
    with SessionLocal() as db:
        db.query(AuthAttempt).delete()
        db.commit()


def _login(client, email, password):
    return client.post("/api/auth/login", json={"email": email, "password": password})


def _bearer(token):
    return {"Authorization": f"Bearer {token}"}


def _new_login(make_employee, headers, role="employee"):
    """Anplwaye ak kont koneksyon. Retounen (employee, imel, modpas tanporè)."""
    email = f"sek-{uuid.uuid4().hex[:8]}@konbit-test.ht"
    r = make_employee(headers, personal_email=email, create_login=True, login_role=role)
    return r["employee"], r["login_email"], r["temporary_password"]


# ---------------------------------------------------------------------------
# BLOKAJ AK LIMIT
# ---------------------------------------------------------------------------

def test_same_answer_for_unknown_email_and_wrong_password(client, org_admin, make_employee):
    _clean_attempts()
    _, email, _ = _new_login(make_employee, org_admin["headers"])
    a = _login(client, email, WRONG)
    b = _login(client, "pa-egziste@konbit-test.ht", WRONG)
    assert a.status_code == b.status_code == 401
    assert a.json()["detail"] == b.json()["detail"]


def test_email_lock_is_temporary_and_same_for_unknown_emails(client, org_admin, make_employee, monkeypatch):
    _clean_attempts()
    monkeypatch.setattr(settings, "max_failed_logins", 3)
    _, email, temp = _new_login(make_employee, org_admin["headers"])

    for _ in range(3):
        assert _login(client, email, WRONG).status_code == 401
    locked = _login(client, email, temp)            # bon modpas, men imel la bloke
    assert locked.status_code == 429
    assert locked.json()["detail"] == TOO_MANY

    # Yon imel ki pa egziste bloke menm jan: pa gen fason pou devine ki kont ki reyèl.
    ghost = f"fantom-{uuid.uuid4().hex[:6]}@konbit-test.ht"
    for _ in range(3):
        _login(client, ghost, WRONG)
    assert _login(client, ghost, WRONG).json()["detail"] == TOO_MANY

    # 16 minit pita: blokaj la fini pou kont li.
    with SessionLocal() as db:
        db.query(AuthAttempt).filter(AuthAttempt.email == email).update(
            {AuthAttempt.created_at: datetime.now(timezone.utc) - timedelta(minutes=16)},
            synchronize_session=False,
        )
        db.commit()
    assert _login(client, email, temp).status_code == 200


def test_hr_reset_unlocks_the_account(client, org_admin, make_employee, monkeypatch):
    _clean_attempts()
    monkeypatch.setattr(settings, "max_failed_logins", 2)
    emp, email, _ = _new_login(make_employee, org_admin["headers"])
    for _ in range(2):
        _login(client, email, WRONG)

    reset = client.post(f"/api/employees/{emp['id']}/reset-password", headers=org_admin["headers"])
    assert reset.status_code == 200, reset.text
    assert _login(client, email, reset.json()["temporary_password"]).status_code == 200


def test_ip_limit_across_emails(client, monkeypatch):
    _clean_attempts()
    monkeypatch.setattr(settings, "login_max_failures_per_ip", 4)
    for i in range(4):
        assert _login(client, f"moun{i}-{uuid.uuid4().hex[:4]}@konbit-test.ht", WRONG).status_code == 401
    assert _login(client, "lot@konbit-test.ht", WRONG).status_code == 429


def test_signup_limit_per_ip(client, monkeypatch):
    _clean_attempts()
    monkeypatch.setattr(settings, "signup_max_per_ip_hour", 1)

    def signup():
        unique = uuid.uuid4().hex[:8]
        return client.post("/api/auth/signup", json={
            "organization": {"name": f"Limit {unique}", "slug": f"limit-{unique}",
                             "country": "HT", "default_currency": "HTG"},
            "admin_full_name": "Admin Limit",
            "admin_email": f"limit-{unique}@konbit-test.ht",
            "admin_password": "TestPassw0rd2026",
        })

    assert signup().status_code == 201
    assert signup().status_code == 429


# ---------------------------------------------------------------------------
# REVOKASYON TOKEN
# ---------------------------------------------------------------------------

def test_logout_revokes_access_and_refresh_tokens(client, org_admin, make_employee):
    _clean_attempts()
    _, email, temp = _new_login(make_employee, org_admin["headers"])
    tokens = _login(client, email, temp).json()
    h = _bearer(tokens["access_token"])

    assert client.post("/api/auth/logout", headers=h).status_code == 200
    assert client.get("/api/auth/identity", headers=h).status_code == 401
    assert client.post("/api/auth/refresh",
                       json={"refresh_token": tokens["refresh_token"]}).status_code == 401


def test_change_password_returns_new_tokens_and_kills_old_ones(client, org_admin, make_employee):
    _clean_attempts()
    _, email, temp = _new_login(make_employee, org_admin["headers"])
    old = _login(client, email, temp).json()

    r = client.post("/api/auth/change-password", json={
        "current_password": temp, "new_password": NEW_PASSWORD,
    }, headers=_bearer(old["access_token"]))
    assert r.status_code == 200, r.text
    new = r.json()

    assert client.get("/api/auth/identity", headers=_bearer(old["access_token"])).status_code == 401
    assert client.post("/api/auth/refresh", json={"refresh_token": old["refresh_token"]}).status_code == 401
    assert client.get("/api/auth/identity", headers=_bearer(new["access_token"])).status_code == 200


# ---------------------------------------------------------------------------
# WÒL: HR PA KA PRAN PLAS ADMINISTRATÈ A
# ---------------------------------------------------------------------------

def test_hr_cannot_create_admin_accounts(client, org_admin, make_employee_login):
    hr = make_employee_login(org_admin["headers"], login_role="hr")["headers"]

    def create(role, headers):
        return client.post("/api/employees", json={
            "first_name": "Pòl", "last_name": "Tès", "hire_date": "2026-01-15",
            "personal_email": f"r-{uuid.uuid4().hex[:8]}@konbit-test.ht",
            "create_login": True, "login_role": role,
        }, headers=headers)

    assert create("org_admin", hr).status_code == 403
    assert create("super_admin", hr).status_code == 422
    assert create("super_admin", org_admin["headers"]).status_code == 422
    assert create("manager", hr).status_code == 201
    assert create("org_admin", org_admin["headers"]).status_code == 201


def test_hr_cannot_take_over_an_admin_account(client, org_admin, make_employee, make_employee_login):
    admin_emp, _, _ = _new_login(make_employee, org_admin["headers"], role="org_admin")
    hr = make_employee_login(org_admin["headers"], login_role="hr")["headers"]

    r = client.post(f"/api/employees/{admin_emp['id']}/reset-password", headers=hr)
    assert r.status_code == 403
    r = client.post(f"/api/employees/{admin_emp['id']}/terminate", json={
        "termination_date": "2026-09-30", "reason": "Tès sekirite", "deactivate_login": True,
    }, headers=hr)
    assert r.status_code == 403


def test_deactivated_business_is_blocked(client, make_org):
    org = make_org()
    assert client.get("/api/auth/identity", headers=org["headers"]).status_code == 200

    with SessionLocal() as db:
        o = db.query(Organization).filter(Organization.slug == org["org_slug"]).first()
        o.is_active = False
        db.commit()
    assert client.get("/api/auth/identity", headers=org["headers"]).status_code == 403