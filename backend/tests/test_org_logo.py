"""
Konbit — Tès logo biznis la (ba anlè aplikasyon an + paj karyè)
Chemen: backend/tests/test_org_logo.py
"""

LOGO = "https://example.com/logo.png"


def _identity(client, h):
    resp = client.get("/api/auth/identity", headers=h)
    assert resp.status_code == 200, resp.text
    return resp.json()


def _set_logo(client, h, url):
    resp = client.patch("/api/organization", json={"logo_url": url}, headers=h)
    assert resp.status_code == 200, resp.text


def _published_job(client, h, title="Kesye Logo"):
    job = client.post("/api/jobs", json={"title": title, "description": "OK"}, headers=h).json()
    client.post(f"/api/jobs/{job['id']}/publish", json={}, headers=h)
    return job


def test_logo_in_identity_and_careers(client, org_admin):
    h = org_admin["headers"]
    slug = org_admin["org_slug"]
    assert _identity(client, h)["organization_logo_url"] is None

    _set_logo(client, h, LOGO)
    assert _identity(client, h)["organization_logo_url"] == LOGO

    job = _published_job(client, h)
    listing = client.get(f"/api/jobs/public/{slug}").json()
    assert listing["company_logo"] == LOGO
    assert listing["items"][0]["company_logo"] == LOGO

    detail = client.get(f"/api/jobs/public/{slug}/{job['slug']}")
    assert detail.status_code == 200, detail.text
    assert detail.json()["company_logo"] == LOGO

    # Retire logo a: tout kote yo retounen san logo.
    _set_logo(client, h, None)
    assert _identity(client, h)["organization_logo_url"] is None
    assert client.get(f"/api/jobs/public/{slug}/{job['slug']}").json()["company_logo"] is None


def test_logo_stays_in_its_business(client, make_org):
    a, b = make_org(), make_org()
    _set_logo(client, a["headers"], LOGO)

    assert _identity(client, b["headers"])["organization_logo_url"] is None
    assert client.get(f"/api/jobs/public/{b['org_slug']}").json()["company_logo"] is None


def test_employee_sees_business_logo(client, org_admin, make_employee_login):
    _set_logo(client, org_admin["headers"], LOGO)
    worker = make_employee_login(org_admin["headers"])
    assert _identity(client, worker["headers"])["organization_logo_url"] == LOGO