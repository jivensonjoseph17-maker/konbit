"""
Konbit — Tès Jounal odit
Chemen: backend/tests/test_audit.py
"""

import re
import uuid
from datetime import datetime, timedelta, timezone

from app.routers.audit import is_sensitive, safe_cell


# ---------------------------------------------------------------------------
# ZOUTI
# ---------------------------------------------------------------------------

def _entries(client, h, **params):
    resp = client.get("/api/audit", params=params, headers=h)
    assert resp.status_code == 200, resp.text
    return resp.json()


def _login(client, org):
    resp = client.post("/api/auth/login", json={"email": org["email"], "password": org["password"]})
    assert resp.status_code == 200, resp.text


def _employee_with_login(client, h, first="Woz"):
    email = f"{first.lower()}-{uuid.uuid4().hex[:6]}@example.com"
    resp = client.post("/api/employees", json={
        "first_name": first, "last_name": "Odit", "hire_date": "2025-01-01",
        "personal_email": email, "create_login": True,
        "login_email": email, "login_role": "employee",
    }, headers=h)
    assert resp.status_code == 201, resp.text
    return resp.json()["employee"]


# ---------------------------------------------------------------------------
# LIS LA
# ---------------------------------------------------------------------------

def test_admin_sees_own_business_log(client, org_admin):
    data = _entries(client, org_admin["headers"])
    assert data["total"] >= 1
    signup = [e for e in data["items"]
              if e["action"] == "create" and e["entity_type"] == "organization"]
    assert signup, data["items"]
    row = signup[0]
    assert row["user_name"] == "Admin Tès"
    assert row["user_email"] == org_admin["email"]
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}", row["local_date"])
    assert re.fullmatch(r"\d{2}:\d{2}", row["local_time"])
    assert row["sensitive"] is False


def test_other_business_sees_nothing(client, make_org):
    a, b = make_org(), make_org()
    _login(client, a)

    a_items = _entries(client, a["headers"])["items"]
    a_ids = {e["id"] for e in a_items}
    a_user = a_items[0]["user_id"]

    b_items = _entries(client, b["headers"], size=100)["items"]
    assert not a_ids & {e["id"] for e in b_items}
    # Menm si B mande dirèkteman moun oswa imel A: anyen.
    assert _entries(client, b["headers"], user_id=a_user)["total"] == 0
    assert _entries(client, b["headers"], q=a["email"])["total"] == 0

    filters = client.get("/api/audit/filters", headers=b["headers"]).json()
    assert a_user not in {u["id"] for u in filters["users"]}

    csv_b = client.get("/api/audit/export", headers=b["headers"])
    assert csv_b.status_code == 200
    assert a["email"] not in csv_b.content.decode("utf-8-sig")


def test_only_business_admin(client, org_admin, make_employee_login):
    h = org_admin["headers"]
    hr = make_employee_login(h, login_role="hr")
    worker = make_employee_login(h)
    for path in ("/api/audit", "/api/audit/filters", "/api/audit/export"):
        assert client.get(path, headers=hr["headers"]).status_code == 403, path
        assert client.get(path, headers=worker["headers"]).status_code == 403, path
        assert client.get(path).status_code == 401, path


# ---------------------------------------------------------------------------
# FILTÈ YO
# ---------------------------------------------------------------------------

def test_sensitive_actions_are_flagged_and_filtered(client, org_admin):
    h = org_admin["headers"]
    emp = _employee_with_login(client, h)
    resp = client.post(f"/api/employees/{emp['id']}/role", json={"role": "manager"}, headers=h)
    assert resp.status_code == 200, resp.text

    only = _entries(client, h, sensitive_only="true")["items"]
    assert only and all(e["sensitive"] for e in only)
    role = [e for e in only if e["action"] == "change_role"]
    assert role and role[0]["entity_id"] == emp["id"]
    assert "manager" in role[0]["changes"]
    assert not any(e["action"] == "create" and e["entity_type"] == "organization" for e in only)


def test_action_entity_and_search_filters(client, org_admin):
    h = org_admin["headers"]
    emp = _employee_with_login(client, h)
    client.post(f"/api/employees/{emp['id']}/role", json={"role": "manager"}, headers=h)
    _login(client, org_admin)

    by_action = _entries(client, h, action="change_role")["items"]
    assert by_action and {e["action"] for e in by_action} == {"change_role"}

    by_entity = _entries(client, h, entity_type="organization")["items"]
    assert by_entity and {e["entity_type"] for e in by_entity} == {"organization"}

    found = _entries(client, h, q="MANAGER")["items"]          # pa gen diferans majiskil
    assert any(e["action"] == "change_role" for e in found)

    # % ak _ se lèt nòmal nan rechèch la, pa jokè SQL.
    assert _entries(client, h, q="%")["total"] == 0

    filters = client.get("/api/audit/filters", headers=h).json()
    assert {"create", "change_role", "login"} <= set(filters["actions"])
    assert "Admin Tès" in {u["name"] for u in filters["users"]}


def test_date_filter(client, org_admin):
    h = org_admin["headers"]
    today = datetime.now(timezone.utc).date()
    around = _entries(client, h, date_from=(today - timedelta(days=2)).isoformat(),
                      date_to=(today + timedelta(days=2)).isoformat())
    assert around["total"] >= 1

    # Dat yo ranvèse: menm rezilta.
    swapped = _entries(client, h, date_from=(today + timedelta(days=2)).isoformat(),
                       date_to=(today - timedelta(days=2)).isoformat())
    assert swapped["total"] == around["total"]

    assert _entries(client, h, date_from="2099-01-01")["total"] == 0
    assert _entries(client, h, date_to="2000-01-01")["total"] == 0


def test_pagination_newest_first(client, org_admin):
    h = org_admin["headers"]
    for _ in range(3):
        _login(client, org_admin)

    first = _entries(client, h, size=2, page=1)
    second = _entries(client, h, size=2, page=2)
    assert first["total"] >= 4 and first["total"] == second["total"]
    assert len(first["items"]) == 2 and len(second["items"]) == 2
    assert not {e["id"] for e in first["items"]} & {e["id"] for e in second["items"]}
    assert first["items"][0]["id"] > second["items"][0]["id"]

    assert client.get("/api/audit", params={"size": 101}, headers=h).status_code == 422


# ---------------------------------------------------------------------------
# CSV
# ---------------------------------------------------------------------------

def test_csv_export_is_logged(client, org_admin):
    h = org_admin["headers"]
    resp = client.get("/api/audit/export", headers=h)
    assert resp.status_code == 200, resp.text
    assert resp.headers["content-type"].startswith("text/csv")
    assert "jounal-odit-" in resp.headers["content-disposition"]
    text = resp.content.decode("utf-8-sig")
    assert text.splitlines()[0].startswith("Dat,Lè,Moun,Imel,Aksyon")
    assert org_admin["email"] in text

    logged = _entries(client, h, action="export")["items"]
    assert logged[0]["entity_type"] == "audit_log"
    assert logged[0]["sensitive"] is True


def test_csv_cells_and_sensitive_rules():
    assert safe_cell("=HYPERLINK(\"x\")") == "'=HYPERLINK(\"x\")"
    assert safe_cell("+509") == "'+509"
    assert safe_cell("-1") == "'-1"
    assert safe_cell("@SUM") == "'@SUM"
    assert safe_cell("Bonjou") == "Bonjou"
    assert safe_cell(None) == ""
    assert safe_cell(7) == "7"

    assert is_sensitive("export", "pay_period", "Rapò bank: 3 fich.") is True
    assert is_sensitive("export", "pay_period", "Rapò ona: 3 fich.") is False
    assert is_sensitive("export", "audit_log", "Jounal odit CSV: 4 liy.") is True
    assert is_sensitive("kiosk_pin_set", "employee", None) is True
    assert is_sensitive("login", "user", None) is False