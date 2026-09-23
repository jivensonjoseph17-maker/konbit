"""
Konbit — Tès otantifikasyon
Chemen: backend/tests/test_auth.py
"""


def test_signup_creates_org_and_admin(client, make_org):
    org = make_org()
    resp = client.get("/api/auth/identity", headers=org["headers"])
    assert resp.status_code == 200
    data = resp.json()
    assert data["user"]["role"] == "org_admin"
    assert data["organization_name"]


def test_signup_rejects_duplicate_slug(client):
    payload = {
        "organization": {
            "name": "Menm Non An",
            "slug": "menm-slug-la",
            "country": "HT",
            "default_currency": "HTG",
        },
        "admin_full_name": "Premye Admin",
        "admin_email": "premye@konbit-test.ht",
        "admin_password": "TestPassw0rd2026",
    }
    first = client.post("/api/auth/signup", json=payload)
    assert first.status_code == 201

    payload["admin_email"] = "dezyem@konbit-test.ht"
    second = client.post("/api/auth/signup", json=payload)
    assert second.status_code == 409


def test_login_with_correct_credentials(client, org_admin):
    resp = client.post("/api/auth/login", json={
        "email": org_admin["email"],
        "password": org_admin["password"],
    })
    assert resp.status_code == 200
    assert "access_token" in resp.json()


def test_login_with_wrong_password_fails(client, org_admin):
    resp = client.post("/api/auth/login", json={
        "email": org_admin["email"],
        "password": "modpasfalspaseditou",
    })
    assert resp.status_code == 401


def test_protected_endpoint_requires_token(client):
    resp = client.get("/api/auth/me")
    assert resp.status_code == 401