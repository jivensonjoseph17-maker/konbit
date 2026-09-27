"""
Konbit — Tès Paramèt biznis
Chemen: backend/tests/test_org_settings.py
"""


def test_admin_reads_and_updates_settings(client, org_admin):
    h = org_admin["headers"]
    before = client.get("/api/organization", headers=h)
    assert before.status_code == 200, before.text
    assert before.json()["pay_frequency"] == "monthly"
    assert before.json()["clock_mode"] == "phone"

    resp = client.patch("/api/organization", json={
        "name": "Boulanjri Lakay",
        "tax_id": "000-123-456-7",
        "city": "Okap",
        "timezone": "America/New_York",
        "default_currency": "USD",
        "pay_frequency": "biweekly",
        "logo_url": "https://example.com/logo.png",
    }, headers=h)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["name"] == "Boulanjri Lakay"
    assert body["tax_id"] == "000-123-456-7"
    assert body["timezone"] == "America/New_York"
    assert body["default_currency"] == "USD"
    assert body["pay_frequency"] == "biweekly"

    # Non an chanje tou nan idantite a (ba anlè a)
    assert client.get("/api/auth/identity", headers=h).json()["organization_name"] == "Boulanjri Lakay"

    # Yon chan vid efase l; yon null sou yon chan obligatwa pa chanje anyen
    cleared = client.patch("/api/organization", json={"city": "", "name": None}, headers=h).json()
    assert cleared["city"] is None and cleared["name"] == "Boulanjri Lakay"


def test_invalid_values_are_refused(client, org_admin):
    h = org_admin["headers"]
    bad_tz = client.patch("/api/organization", json={"timezone": "Mars/Olympus"}, headers=h)
    assert bad_tz.status_code == 422
    assert client.patch("/api/organization", json={"logo_url": "javascript:alert(1)"},
                        headers=h).status_code == 422
    assert client.patch("/api/organization", json={"pay_frequency": "daily"},
                        headers=h).status_code == 422
    assert client.patch("/api/organization", json={"name": "A"}, headers=h).status_code == 422


def test_only_admin_can_change_settings(client, org_admin, make_employee_login):
    h = org_admin["headers"]
    hr = make_employee_login(h, login_role="hr")
    worker = make_employee_login(h)

    assert client.get("/api/organization", headers=hr["headers"]).status_code == 200
    assert client.patch("/api/organization", json={"city": "Jakmèl"},
                        headers=hr["headers"]).status_code == 403
    assert client.get("/api/organization", headers=worker["headers"]).status_code == 403