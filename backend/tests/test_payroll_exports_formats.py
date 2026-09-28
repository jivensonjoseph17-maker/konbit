"""
Konbit — Tès fichye bank (transfè sèlman), lis chèk/kach, fòma Excel
Chemen: backend/tests/test_payroll_exports_formats.py
"""

import csv
import io


def _paid_period(client, h, check_start=None):
    pid = client.post("/api/payroll/periods", json={
        "name": "Out 2026", "start_date": "2026-08-01", "end_date": "2026-08-31", "pay_date": "2026-08-31",
    }, headers=h).json()["id"]
    assert client.post(f"/api/payroll/periods/{pid}/run", json={"pay_period_id": pid},
                       headers=h).status_code == 200
    assert client.post(f"/api/payroll/periods/{pid}/approve", headers=h).status_code == 200
    body = {"paid_at": "2026-08-31T15:00:00Z"}
    if check_start is not None:
        body["check_start_number"] = check_start
    assert client.post(f"/api/payroll/periods/{pid}/pay", json=body, headers=h).status_code == 200
    return pid


def _csv(resp, delimiter=","):
    assert resp.status_code == 200, resp.text
    return list(csv.reader(io.StringIO(resp.content.decode("utf-8-sig")), delimiter=delimiter))


def _two_employees(h, make_employee):
    bank = make_employee(h, base_salary=4_500_000, hire_date="2025-01-01",
                         preferred_payment_method="direct_deposit", bank_name="Unibank",
                         bank_account_number="1234567890")["employee"]
    check = make_employee(h, base_salary=3_000_000, hire_date="2025-01-01",
                          preferred_payment_method="check")["employee"]
    return bank, check


def test_bank_file_has_only_transfers_with_creole_labels(client, org_admin, make_employee):
    h = org_admin["headers"]
    bank, check = _two_employees(h, make_employee)
    pid = _paid_period(client, h, check_start=1001)

    rows = _csv(client.get(f"/api/payroll/periods/{pid}/export/bank", headers=h))
    numbers = [r[0] for r in rows[1:-1]]
    assert numbers == [bank["employee_number"]]           # moun chèk la PA ladan
    assert rows[1][2] == "Depo dirèk" and rows[1][4] == "1234567890"
    assert "Chèk" not in rows[0]                           # pa gen kolòn chèk ankò
    assert rows[-1][0] == "TOTAL" and rows[-1][5] == rows[1][5]


def test_checks_file_lists_checks_with_numbers(client, org_admin, make_employee):
    h = org_admin["headers"]
    bank, check = _two_employees(h, make_employee)
    pid = _paid_period(client, h, check_start=1001)

    rows = _csv(client.get(f"/api/payroll/periods/{pid}/export/checks", headers=h))
    assert rows[0] == ["Nimewo", "Non", "Metòd", "Nimewo chèk", "Net", "Lajan", "Siyati"]
    assert [r[0] for r in rows[1:-1]] == [check["employee_number"]]
    assert rows[1][2] == "Chèk" and rows[1][3] == "1001" and rows[1][6] == ""
    assert rows[-1][0] == "TOTAL" and rows[-1][4] == rows[1][4]

    logged = client.get("/api/audit", params={"action": "export"}, headers=h).json()["items"]
    assert logged[0]["changes"] == "Rapò checks: 1 fich."
    assert logged[0]["sensitive"] is False


def test_excel_format_uses_semicolon_and_decimal_comma(client, org_admin, make_employee):
    h = org_admin["headers"]
    _two_employees(h, make_employee)
    pid = _paid_period(client, h)

    plain = _csv(client.get(f"/api/payroll/periods/{pid}/export/dgi", headers=h))
    resp = client.get(f"/api/payroll/periods/{pid}/export/dgi?excel=true", headers=h)
    assert "-excel.csv" in resp.headers["content-disposition"]
    excel = _csv(resp, delimiter=";")

    assert len(excel) == len(plain) and len(excel[1]) == len(plain[1])
    assert excel[-1][3] == plain[-1][3].replace(".", ",")
    assert "," in excel[-1][3] and "." not in excel[-1][3]

    logged = client.get("/api/audit", params={"action": "export"}, headers=h).json()["items"]
    assert logged[0]["changes"].endswith("(Excel).")


def test_bank_export_is_still_sensitive(client, org_admin, make_employee):
    h = org_admin["headers"]
    _two_employees(h, make_employee)
    pid = _paid_period(client, h)
    client.get(f"/api/payroll/periods/{pid}/export/bank?excel=true", headers=h)
    logged = client.get("/api/audit", params={"action": "export"}, headers=h).json()["items"]
    assert logged[0]["changes"].startswith("Rapò bank") and logged[0]["sensitive"] is True