"""
Konbit — Tès pozisyon, Direksyon ak "Pa sou pewòl"
Chemen: backend/tests/test_positions.py
"""


def _employee(client, h, first, **extra):
    payload = {
        "first_name": first,
        "last_name": "Tès",
        "hire_date": "2025-01-01",
        "base_salary": 3_000_000,
        "create_login": False,
        **extra,
    }
    resp = client.post("/api/employees", json=payload, headers=h)
    assert resp.status_code == 201, resp.text
    return resp.json()["employee"]


def _positions(client, h, **params):
    resp = client.get("/api/positions", params=params, headers=h)
    assert resp.status_code == 200, resp.text
    return {p["title"]: p for p in resp.json()["items"]}


def test_defaults_are_added_once(client, org_admin):
    h = org_admin["headers"]
    first = client.post("/api/positions/defaults", headers=h)
    assert first.status_code == 200, first.text
    again = client.post("/api/positions/defaults", headers=h)
    assert again.json()["created"] == 0

    pos = _positions(client, h)
    assert pos["Fondatè"]["is_leadership"] is True
    assert pos["Pwopriyetè"]["is_leadership"] is True
    assert pos["Kesye"]["is_leadership"] is False


def test_signup_gets_default_positions(client):
    resp = client.post("/api/auth/signup", json={
        "organization": {"name": "Boulanjri Tès", "slug": "boulanjri-tes-pozisyon"},
        "admin_full_name": "Mari Tès",
        "admin_email": "mari.pozisyon@example.com",
        "admin_password": "Konmbit2026Solid",
    })
    assert resp.status_code == 201, resp.text
    h = {"Authorization": f"Bearer {resp.json()['access_token']}"}
    pos = _positions(client, h)
    assert {"Pwopriyetè", "Fondatè", "Kofondatè", "Kesye"} <= set(pos)


def test_duplicate_title_is_refused(client, org_admin):
    h = org_admin["headers"]
    assert client.post("/api/positions", json={"title": "Chofè"}, headers=h).status_code == 201
    dup = client.post("/api/positions", json={"title": "  chofè "}, headers=h)
    assert dup.status_code == 409, dup.text


def test_used_position_is_deactivated_not_deleted(client, org_admin):
    h = org_admin["headers"]
    pid = client.post("/api/positions", json={"title": "Gad"}, headers=h).json()["id"]
    _employee(client, h, "Jak", position_id=pid)

    assert client.delete(f"/api/positions/{pid}", headers=h).status_code == 409
    off = client.patch(f"/api/positions/{pid}", json={"is_active": False}, headers=h)
    assert off.status_code == 200 and off.json()["is_active"] is False
    assert "Gad" not in _positions(client, h)
    assert "Gad" in _positions(client, h, include_inactive="true")

    unused = client.post("/api/positions", json={"title": "Tanporè"}, headers=h).json()["id"]
    assert client.delete(f"/api/positions/{unused}", headers=h).status_code == 200


def test_leadership_on_top_of_org_chart(client, org_admin):
    h = org_admin["headers"]
    client.post("/api/positions/defaults", headers=h)
    founder_pos = _positions(client, h)["Fondatè"]["id"]
    _employee(client, h, "Jivenson", position_id=founder_pos)
    _employee(client, h, "Lwi")

    tree = client.get("/api/hierarchy/tree", headers=h).json()
    leaders = [n["full_name"] for n in tree["leadership"]]
    assert leaders == ["Jivenson Tès"]
    assert tree["leadership"][0]["is_leadership"] is True


def test_off_payroll_person_gets_no_payslip(client, org_admin):
    h = org_admin["headers"]
    owner = _employee(client, h, "Pwopriyetè", on_payroll=False)
    staff = _employee(client, h, "Kesye")
    assert owner["on_payroll"] is False and staff["on_payroll"] is True

    period = client.post("/api/payroll/periods", json={
        "name": "Jiyè 2026", "start_date": "2026-07-01",
        "end_date": "2026-07-31", "pay_date": "2026-07-31",
    }, headers=h)
    assert period.status_code == 201, period.text
    pid = period.json()["id"]

    run = client.post(f"/api/payroll/periods/{pid}/run", json={"pay_period_id": pid}, headers=h)
    assert run.status_code == 200, run.text
    body = run.json()
    assert body["created"] == 1
    assert any("pa sou pewòl" in w for w in body["warnings"])

    slips = client.get(f"/api/payroll/periods/{pid}/payslips", headers=h).json()["items"]
    assert [s["payslip"]["employee_id"] for s in slips] == [staff["id"]]


def test_on_payroll_can_be_changed_but_not_nulled(client, org_admin):
    h = org_admin["headers"]
    emp = _employee(client, h, "Asosye")
    off = client.patch(f"/api/employees/{emp['id']}", json={"on_payroll": False}, headers=h)
    assert off.status_code == 200 and off.json()["on_payroll"] is False

    null = client.patch(f"/api/employees/{emp['id']}", json={"on_payroll": None}, headers=h)
    assert null.status_code == 200 and null.json()["on_payroll"] is False
    assert null.json()["has_bank_account"] is False