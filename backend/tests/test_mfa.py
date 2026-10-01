"""
Tès verifikasyon an 2 etap (routers/mfa.py, totp.py).
Kòd yo kalkile ak pyotp nan tès la, menm jan yon telefòn ta fè l.
"""
import time
import uuid

import pyotp

import app.deps
from app.config import settings


def _bearer(token):
    return {"Authorization": f"Bearer {token}"}


def _login(client, email, password):
    r = client.post("/api/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, r.text
    return r.json()


def _verify(client, mfa_token, code):
    return client.post("/api/auth/mfa/verify", json={"mfa_token": mfa_token, "code": code})


def _enable(client, headers, password):
    """Aktive 2FA. Retounen (sekrè, lè kòd la te kalkile, repons /enable)."""
    setup = client.post("/api/auth/mfa/setup", json={"password": password}, headers=headers)
    assert setup.status_code == 200, setup.text
    assert setup.json()["qr_png"].startswith("data:image/png;base64,")
    secret = setup.json()["secret"]
    now = time.time()
    r = client.post("/api/auth/mfa/enable", json={"code": pyotp.TOTP(secret).at(now)}, headers=headers)
    assert r.status_code == 200, r.text
    return secret, now, r.json()


def _employee(client, make_employee, admin_headers, role="employee"):
    email = f"mfa-{uuid.uuid4().hex[:8]}@konbit-test.ht"
    r = make_employee(admin_headers, personal_email=email, create_login=True, login_role=role)
    tokens = _login(client, r["login_email"], r["temporary_password"])
    return r["employee"], r["login_email"], r["temporary_password"], _bearer(tokens["access_token"])


def test_enable_then_login_needs_a_fresh_code(client, make_org):
    org = make_org()
    secret, t0, enabled = _enable(client, org["headers"], org["password"])
    assert len(enabled["codes"]) == 10
    # Aktivasyon an anile ansyen sesyon yo
    assert client.get("/api/auth/identity", headers=org["headers"]).status_code == 401

    first = _login(client, org["email"], org["password"])
    assert first["mfa_required"] is True and first["access_token"] is None

    totp = pyotp.TOTP(secret)
    assert _verify(client, first["mfa_token"], totp.at(t0)).status_code == 401    # deja sèvi
    ok = _verify(client, first["mfa_token"], totp.at(t0 + 30))
    assert ok.status_code == 200, ok.text
    me = client.get("/api/auth/identity", headers=_bearer(ok.json()["access_token"])).json()
    assert me["user"]["totp_enabled"] is True


def test_recovery_code_works_only_once(client, make_org):
    org = make_org()
    _, _, enabled = _enable(client, org["headers"], org["password"])
    code = enabled["codes"][0].lower()

    for expected in (200, 401):
        token = _login(client, org["email"], org["password"])["mfa_token"]
        assert _verify(client, token, code).status_code == expected


def test_wrong_codes_are_limited(client, make_org, monkeypatch):
    monkeypatch.setattr(settings, "max_failed_logins", 3)
    org = make_org()
    _enable(client, org["headers"], org["password"])
    token = _login(client, org["email"], org["password"])["mfa_token"]

    for _ in range(3):
        assert _verify(client, token, "000000").status_code == 401
    assert _verify(client, token, "000000").status_code == 429


def test_mfa_token_is_not_an_access_token(client, make_org):
    org = make_org()
    _enable(client, org["headers"], org["password"])
    token = _login(client, org["email"], org["password"])["mfa_token"]
    assert client.get("/api/auth/identity", headers=_bearer(token)).status_code == 401


def test_setup_needs_the_password(client, make_org):
    org = make_org()
    r = client.post("/api/auth/mfa/setup", json={"password": "MoveModpas2026"}, headers=org["headers"])
    assert r.status_code == 400


def test_admin_cannot_disable(client, make_org):
    org = make_org()
    secret, t0, enabled = _enable(client, org["headers"], org["password"])
    r = client.post("/api/auth/mfa/disable", json={
        "password": org["password"], "code": pyotp.TOTP(secret).at(t0 + 30),
    }, headers=_bearer(enabled["access_token"]))
    assert r.status_code == 403


def test_employee_can_disable(client, org_admin, make_employee):
    _, _, password, h = _employee(client, make_employee, org_admin["headers"])
    secret, t0, enabled = _enable(client, h, password)
    h2 = _bearer(enabled["access_token"])

    r = client.post("/api/auth/mfa/disable", json={
        "password": password, "code": pyotp.TOTP(secret).at(t0 + 30),
    }, headers=h2)
    assert r.status_code == 200, r.text
    assert client.get("/api/auth/mfa/status", headers=h2).json()["enabled"] is False


def test_admins_must_enable_mfa_when_enforced(client, make_org, monkeypatch):
    monkeypatch.setattr(app.deps, "ENFORCE_MFA", True)
    org = make_org()
    assert client.get("/api/employees", headers=org["headers"]).status_code == 403
    assert client.get("/api/auth/mfa/status", headers=org["headers"]).json()["required"] is True

    _, _, enabled = _enable(client, org["headers"], org["password"])
    assert client.get("/api/employees", headers=_bearer(enabled["access_token"])).status_code == 200


def test_admin_resets_employee_mfa(client, org_admin, make_employee, make_employee_login):
    emp, email, password, h = _employee(client, make_employee, org_admin["headers"])
    _, _, enabled = _enable(client, h, password)
    session = _bearer(enabled["access_token"])

    hr = make_employee_login(org_admin["headers"], login_role="hr")["headers"]
    assert client.post(f"/api/auth/mfa/reset/{emp['id']}", headers=hr).status_code == 403

    r = client.post(f"/api/auth/mfa/reset/{emp['id']}", headers=org_admin["headers"])
    assert r.status_code == 200, r.text
    assert client.get("/api/auth/identity", headers=session).status_code == 401
    login = _login(client, email, password)
    assert login["mfa_required"] is False and login["access_token"]


def test_totp_step_is_never_reused():
    from app.totp import matching_step
    secret = pyotp.random_base32()
    now = time.time()
    code = pyotp.TOTP(secret).at(now)
    step = matching_step(secret, code, None, now=now)
    assert step is not None
    assert matching_step(secret, code, step, now=now) is None