"""
Konbit — Tès enpòtasyon anplwaye pa CSV
Chemen: backend/tests/test_employee_import.py
"""

import uuid

GOOD = (
    "Prenon,Non,Dat anbochaj,Imel,Nimewo,Salè,Metòd peman,MonCash,Manadjè,Kolòn pèsonèl\n"
    "Woz,Pyè,2025-01-15,{a},EX-01,45000,MonCash,37123456,,x\n"
    "Jak,Lui,15/02/2025,{b},EX-02,\"30 000,50\",Chèk,,EX-01,y\n"
)


def _csv(text=GOOD):
    u = uuid.uuid4().hex[:6]
    return text.format(a=f"woz-{u}@example.com", b=f"jak-{u}@example.com")


def _preview(client, h, text, **kw):
    resp = client.post("/api/employee-import/preview", json={"csv_text": text, **kw}, headers=h)
    assert resp.status_code == 200, resp.text
    return resp.json()


def _commit(client, h, text, **kw):
    resp = client.post("/api/employee-import/commit", json={"csv_text": text, **kw}, headers=h)
    assert resp.status_code == 200, resp.text
    return resp.json()


def _by_number(client, h, number):
    items = client.get("/api/employees", params={"q": number}, headers=h).json()["items"]
    return next(e for e in items if e["employee_number"] == number)


def test_preview_reads_creole_headers_and_writes_nothing(client, org_admin):
    h = org_admin["headers"]
    before = client.get("/api/employees", headers=h).json()["total"]
    data = _preview(client, h, _csv())
    assert data["errors"] == []
    assert data["delimiter"] == ","
    assert [r["employee_number"] for r in data["rows"]] == ["EX-01", "EX-02"]
    assert data["rows"][1]["hire_date"] == "2025-02-15"
    assert data["rows"][0]["payment_method"] == "moncash"
    assert data["ignored_columns"] == ["Kolòn pèsonèl"]
    assert client.get("/api/employees", headers=h).json()["total"] == before


def test_commit_creates_everyone_with_manager_and_money(client, org_admin):
    h = org_admin["headers"]
    out = _commit(client, h, _csv())
    assert out["created"] == 2 and out["logins"] == [] and out["errors"] == []

    woz = _by_number(client, h, "EX-01")
    jak = _by_number(client, h, "EX-02")
    assert jak["manager_id"] == woz["id"]
    full = client.get(f"/api/employees/{jak['id']}", headers=h).json()
    assert full["base_salary"] == 3_000_050

    logged = client.get("/api/audit", params={"action": "import"}, headers=h).json()["items"]
    assert logged and logged[0]["changes"].startswith("2 anplwaye")


def test_one_bad_row_blocks_everything(client, org_admin):
    h = org_admin["headers"]
    before = client.get("/api/employees", headers=h).json()["total"]
    bad = _csv() + "Pòl,Jan,pa-yon-dat,,EX-03,abc,Bitcoin,,EX-99,\n"
    out = _commit(client, h, bad)
    assert out["created"] == 0
    codes = {(e["row"], e["field"], e["code"]) for e in out["errors"]}
    assert (4, "hire_date", "invalid_date") in codes
    assert (4, "base_salary", "invalid_number") in codes
    assert (4, "payment_method", "invalid_method") in codes
    assert (4, "manager_number", "unknown_manager") in codes
    assert client.get("/api/employees", headers=h).json()["total"] == before


def test_semicolon_excel_and_missing_columns(client, org_admin):
    h = org_admin["headers"]
    excel = "prenon;non;dat_anbochaj;sale\nMari;Jozèf;01/03/2025;25 000,00\n"
    data = _preview(client, h, "\ufeff" + excel)
    assert data["delimiter"] == ";" and data["errors"] == []

    template = _preview(client, h, "sep=;\nPrenon;Non;Dat anbochaj\nMari;Jozèf;2025-01-15\n")
    assert template["errors"] == [] and template["rows"][0]["first_name"] == "Mari"

    missing = _preview(client, h, "prenon,non\nMari,Jozèf\n")
    assert {"field": "hire_date", "code": "missing_column", "row": 1} in missing["errors"]


def test_duplicates_and_auto_numbers(client, org_admin):
    h = org_admin["headers"]
    _commit(client, h, _csv())
    again = _preview(client, h, _csv())
    assert {e["code"] for e in again["errors"]} == {"duplicate_number"}

    # San nimewo: sistèm nan bay yo, san li pa tonbe sou yon nimewo fichye a mande.
    text = "prenon,non,dat_anbochaj,nimewo\nA,Un,2025-01-01,\nB,De,2025-01-01,KB-0004\nC,Twa,2025-01-01,\n"
    out = _commit(client, h, text)
    assert out["created"] == 3
    numbers = [e["employee_number"] for e in client.get("/api/employees", params={"size": 100},
                                                         headers=h).json()["items"]]
    assert len(numbers) == len(set(numbers)) and "KB-0004" in numbers


def test_logins_are_created_once_and_work(client, org_admin):
    h = org_admin["headers"]
    no_email = _preview(client, h, "prenon,non,dat_anbochaj\nA,B,2025-01-01\n", create_logins=True)
    assert no_email["errors"][0]["code"] == "required_for_login"

    out = _commit(client, h, _csv(), create_logins=True)
    assert out["created"] == 2 and len(out["logins"]) == 2
    first = out["logins"][0]
    login = client.post("/api/auth/login", json={
        "email": first["login_email"], "password": first["temporary_password"]})
    assert login.status_code == 200, login.text


def test_only_hr_can_import(client, org_admin, make_employee_login):
    worker = make_employee_login(org_admin["headers"])
    for path in ("/api/employee-import/preview", "/api/employee-import/commit"):
        assert client.post(path, json={"csv_text": _csv()}, headers=worker["headers"]).status_code == 403