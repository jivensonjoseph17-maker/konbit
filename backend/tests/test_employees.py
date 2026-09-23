"""
Konbit — Tès anplwaye ak izolasyon milti-tenant
Chemen: backend/tests/test_employees.py

Tès `test_org_b_cannot_see_org_a_employee` la enpòtan anpil: se li ki
verifye REGLA MILTI-TENANT prensipal aplikasyon an — yon biznis pa ka janm
wè done yon lòt biznis, menm si li konnen (oswa devine) yon ID.
"""


def test_create_employee(client, org_admin, make_employee):
    result = make_employee(org_admin["headers"], first_name="Pòl", last_name="Jean")
    emp = result["employee"]
    assert emp["first_name"] == "Pòl"
    assert emp["employee_number"].startswith("KB-")
    assert emp["status"] == "active"


def test_list_employees_returns_created_one(client, org_admin, make_employee):
    make_employee(org_admin["headers"], first_name="Woz", last_name="Pyè")
    resp = client.get("/api/employees", headers=org_admin["headers"])
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] >= 1
    names = [f"{e['first_name']} {e['last_name']}" for e in data["items"]]
    assert "Woz Pyè" in names


def test_duplicate_employee_number_rejected(client, org_admin, make_employee):
    make_employee(org_admin["headers"], employee_number="KB-9999")
    resp = client.post("/api/employees", json={
        "first_name": "Lòt",
        "last_name": "Moun",
        "hire_date": "2026-01-15",
        "employee_number": "KB-9999",
        "create_login": False,
    }, headers=org_admin["headers"])
    assert resp.status_code == 409


def test_org_b_cannot_see_org_a_employee(client, make_org, make_employee):
    org_a = make_org()
    org_b = make_org()

    created = make_employee(org_a["headers"], first_name="Sekrè", last_name="OrgA")
    emp_id = created["employee"]["id"]

    # Org A wè pwòp anplwaye l san pwoblèm.
    ok = client.get(f"/api/employees/{emp_id}", headers=org_a["headers"])
    assert ok.status_code == 200

    # Org B, menm ak yon ID valab, pa dwe janm jwenn li — 404, pa 403,
    # pou pa menm konfime existans dosye a.
    blocked = client.get(f"/api/employees/{emp_id}", headers=org_b["headers"])
    assert blocked.status_code == 404

    # Lis Org B la pa dwe gen anplwaye Org A ladan l.
    listing = client.get("/api/employees", headers=org_b["headers"])
    ids = [e["id"] for e in listing.json()["items"]]
    assert emp_id not in ids


def test_employee_endpoints_require_auth(client):
    resp = client.get("/api/employees")
    assert resp.status_code == 401