"""
Konbit — Tès fichye logo biznis la (telechaje, piblik, PDF fich peye)
Chemen: backend/tests/test_org_logo_file.py
"""

import base64
import io

from PIL import Image

LINK = "https://example.com/logo.png"
AUGUST = {"name": "Out 2026", "start_date": "2026-08-01",
          "end_date": "2026-08-31", "pay_date": "2026-08-31"}
JULY = {"name": "Jiyè 2026", "start_date": "2026-07-01",
        "end_date": "2026-07-31", "pay_date": "2026-07-31"}


def _image(size=(800, 400), fmt="PNG", mode="RGBA") -> bytes:
    buf = io.BytesIO()
    color = (29, 78, 216, 255) if mode == "RGBA" else (29, 78, 216)
    Image.new(mode, size, color).save(buf, fmt)
    return buf.getvalue()


def _upload(client, h, raw: bytes):
    return client.put("/api/organization/logo",
                      json={"data_base64": base64.b64encode(raw).decode()}, headers=h)


def _identity_logo(client, h):
    return client.get("/api/auth/identity", headers=h).json()["organization_logo_url"]


# ---------------------------------------------------------------------------
# TELECHAJE AK SÈVI
# ---------------------------------------------------------------------------

def test_upload_is_cleaned_and_served_publicly(client, org_admin):
    h, slug = org_admin["headers"], org_admin["org_slug"]
    client.patch("/api/organization", json={"logo_url": LINK}, headers=h)

    resp = _upload(client, h, _image((1600, 800)))
    assert resp.status_code == 200, resp.text
    info = resp.json()
    assert info["has_file"] is True
    assert (info["width"], info["height"]) == (512, 256)       # redui a 512 px
    assert info["url"].startswith(f"/api/logos/{slug}?v=")

    # Fichye a pase devan lyen an, toupatou.
    assert _identity_logo(client, h) == info["url"]
    assert client.get(f"/api/jobs/public/{slug}").json()["company_logo"] == info["url"]

    # Piblik: san token.
    img = client.get(info["url"])
    assert img.status_code == 200
    assert img.headers["content-type"] == "image/png"
    assert img.headers["x-content-type-options"] == "nosniff"
    assert "immutable" in img.headers["cache-control"]
    assert Image.open(io.BytesIO(img.content)).size == (512, 256)

    again = client.get(info["url"], headers={"If-None-Match": img.headers["etag"]})
    assert again.status_code == 304


def test_jpeg_and_data_url_prefix_are_accepted(client, org_admin):
    raw = _image((300, 300), fmt="JPEG", mode="RGB")
    data_url = "data:image/jpeg;base64," + base64.b64encode(raw).decode()
    resp = client.put("/api/organization/logo", json={"data_base64": data_url},
                      headers=org_admin["headers"])
    assert resp.status_code == 200, resp.text
    assert (resp.json()["width"], resp.json()["height"]) == (300, 300)


def test_bad_files_are_refused(client, org_admin):
    h = org_admin["headers"]
    gif = _image((50, 50), fmt="GIF", mode="RGB")
    for raw in (b"<svg onload=alert(1)>" * 5, gif, _image((8, 8)),
                b"\x89PNG\r\n\x1a\n" + b"x" * 200,
                b"\x89PNG\r\n\x1a\n" + b"0" * (2 * 1024 * 1024)):
        assert _upload(client, h, raw).status_code == 422
    bad = client.put("/api/organization/logo", json={"data_base64": "pa-base64!!!"}, headers=h)
    assert bad.status_code == 422
    assert client.get("/api/organization/logo", headers=h).json()["has_file"] is False


def test_delete_falls_back_to_link(client, org_admin):
    h, slug = org_admin["headers"], org_admin["org_slug"]
    client.patch("/api/organization", json={"logo_url": LINK}, headers=h)
    url = _upload(client, h, _image()).json()["url"]

    resp = client.delete("/api/organization/logo", headers=h)
    assert resp.status_code == 200 and resp.json()["has_file"] is False
    assert _identity_logo(client, h) == LINK
    assert client.get(url).status_code == 404
    assert client.get(f"/api/logos/{slug}").status_code == 404

    actions = {(e["action"], e["entity_type"]) for e in
               client.get("/api/audit", params={"entity_type": "organization_logo"},
                          headers=h).json()["items"]}
    assert actions == {("update", "organization_logo"), ("delete", "organization_logo")}


# ---------------------------------------------------------------------------
# DWA AK IZOLASYON
# ---------------------------------------------------------------------------

def test_only_admin_changes_logo(client, org_admin, make_employee_login):
    h = org_admin["headers"]
    hr = make_employee_login(h, login_role="hr")
    worker = make_employee_login(h)

    assert _upload(client, hr["headers"], _image()).status_code == 403
    assert client.delete("/api/organization/logo", headers=hr["headers"]).status_code == 403
    assert client.get("/api/organization/logo", headers=hr["headers"]).status_code == 200
    assert client.get("/api/organization/logo", headers=worker["headers"]).status_code == 403
    assert _upload(client, worker["headers"], _image()).status_code == 403


def test_logo_stays_in_its_business(client, make_org):
    a, b = make_org(), make_org()
    url_a = _upload(client, a["headers"], _image()).json()["url"]

    assert _identity_logo(client, b["headers"]) is None
    assert client.get("/api/organization/logo", headers=b["headers"]).json()["has_file"] is False
    # Menm "v" a sou slug B a: anyen.
    assert client.get(url_a.replace(a["org_slug"], b["org_slug"])).status_code == 404


# ---------------------------------------------------------------------------
# PDF FICH PEYE
# ---------------------------------------------------------------------------

def _payslip_pdf(client, h, make_employee, period) -> bytes:
    make_employee(h, base_salary=4_500_000, hire_date="2025-01-01")
    pid = client.post("/api/payroll/periods", json=period, headers=h).json()["id"]
    run = client.post(f"/api/payroll/periods/{pid}/run", json={"pay_period_id": pid}, headers=h)
    assert run.status_code == 200, run.text
    sid = client.get(f"/api/payroll/periods/{pid}/payslips", headers=h).json()["items"][0]["payslip"]["id"]
    resp = client.get(f"/api/payroll/payslips/{sid}/pdf?lang=fr", headers=h)
    assert resp.status_code == 200, resp.text
    return resp.content


def test_payslip_pdf_shows_logo(client, org_admin, make_employee):
    h = org_admin["headers"]
    assert b"/Subtype /Image" not in _payslip_pdf(client, h, make_employee, JULY)

    _upload(client, h, _image())
    pdf = _payslip_pdf(client, h, make_employee, AUGUST)
    assert pdf.startswith(b"%PDF")
    assert b"/Subtype /Image" in pdf