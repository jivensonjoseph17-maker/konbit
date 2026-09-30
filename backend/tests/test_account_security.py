"""
Konbit — Tès modpas tanporè ak chanjman wòl
Chemen: backend/tests/test_account_security.py
"""

import app.deps

NEW_PASSWORD = "NouvoModpas2026"


def _employee_with_login(client, h, first, role="employee"):
    email = f"{first.lower()}@example.com"
    resp = client.post("/api/employees", json={
        "first_name": first,
        "last_name": "Tès",
        "hire_date": "2025-01-01",
        "personal_email": email,
        "create_login": True,
        "login_email": email,
        "login_role": role,
    }, headers=h)
    assert resp.status_code == 201, resp.text
    body = resp.json()
    return body["employee"], email, body["temporary_password"]


def _login(client, email, password):
    resp = client.post("/api/auth/login", json={"email": email, "password": password})
    assert resp.status_code == 200, resp.text
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


def test_temporary_password_must_be_changed(client, org_admin, monkeypatch):
    monkeypatch.setattr(app.deps, "ENFORCE_PASSWORD_CHANGE", True)
    _, email, temp = _employee_with_login(client, org_admin["headers"], "Rose")
    h = _login(client, email, temp)

    me = client.get("/api/auth/identity", headers=h)
    assert me.status_code == 200 and me.json()["user"]["must_change_password"] is True

    blocked = client.get("/api/employees/me", headers=h)
    assert blocked.status_code == 403, blocked.text

    changed = client.post("/api/auth/change-password", json={
        "current_password": temp, "new_password": NEW_PASSWORD,
    }, headers=h)
    assert changed.status_code == 200, changed.text

    # Chanje modpas anile ansyen token yo (token_version): nou sèvi ak nouvo yo.
    assert client.get("/api/employees/me", headers=h).status_code == 401
    h = {"Authorization": f"Bearer {changed.json()['access_token']}"}

    assert client.get("/api/employees/me", headers=h).status_code == 200
    assert client.get("/api/auth/identity", headers=h).json()["user"]["must_change_password"] is False


def test_reset_password_sets_the_flag_again(client, org_admin):
    emp, email, temp = _employee_with_login(client, org_admin["headers"], "Jan")
    h = _login(client, email, temp)
    client.post("/api/auth/change-password", json={
        "current_password": temp, "new_password": NEW_PASSWORD,
    }, headers=h)

    reset = client.post(f"/api/employees/{emp['id']}/reset-password", headers=org_admin["headers"])
    assert reset.status_code == 200
    h2 = _login(client, email, reset.json()["temporary_password"])
    assert client.get("/api/auth/identity", headers=h2).json()["user"]["must_change_password"] is True


def test_employee_can_become_manager(client, org_admin):
    admin = org_admin["headers"]
    emp, email, temp = _employee_with_login(client, admin, "Pyè")
    assert emp["login_role"] == "employee"

    resp = client.post(f"/api/employees/{emp['id']}/role", json={"role": "manager"}, headers=admin)
    assert resp.status_code == 200, resp.text
    assert resp.json()["role"] == "manager"

    # Aplike touswit: menm token an wè nouvo wòl la.
    h = _login(client, email, temp)
    assert client.get("/api/auth/identity", headers=h).json()["user"]["role"] == "manager"
    assert client.get(f"/api/employees/{emp['id']}", headers=admin).json()["login_role"] == "manager"


def test_hr_limits(client, org_admin):
    admin = org_admin["headers"]
    hr_emp, hr_email, hr_temp = _employee_with_login(client, admin, "Nadia", role="hr")
    other, _, _ = _employee_with_login(client, admin, "Wilnè")
    hr = _login(client, hr_email, hr_temp)

    # HR pa ka bay wòl administratè
    grant = client.post(f"/api/employees/{other['id']}/role", json={"role": "org_admin"}, headers=hr)
    assert grant.status_code == 403
    # HR pa ka chanje pwòp wòl li
    own = client.post(f"/api/employees/{hr_emp['id']}/role", json={"role": "manager"}, headers=hr)
    assert own.status_code == 403
    # Men HR ka fè yon anplwaye vin manadjè
    ok = client.post(f"/api/employees/{other['id']}/role", json={"role": "manager"}, headers=hr)
    assert ok.status_code == 200
    # Wòl ki pa egziste
    bad = client.post(f"/api/employees/{other['id']}/role", json={"role": "super_admin"}, headers=hr)
    assert bad.status_code == 422