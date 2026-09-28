"""
Konbit — Tès rapò pewòl ak fichye bank
Chemen: backend/tests/test_payroll_exports.py
"""

import csv
import io


def _paid_period(client, h, pay=True):
    pid = client.post("/api/payroll/periods", json={
        "name": "Out 2026", "start_date": "2026-08-01", "end_date": "2026-08-31", "pay_date": "2026-08-31",
    }, headers=h).json()["id"]
    assert client.post(f"/api/payroll/periods/{pid}/run", json={"pay_period_id": pid},
                       headers=h).status_code == 200
    assert client.post(f"/api/payroll/periods/{pid}/approve", headers=h).status_code == 200
    if pay:
        assert client.post(f"/api/payroll/periods/{pid}/pay",
                           json={"paid_at": "2026-08-31T15:00:00Z"}, headers=h).status_code == 200
    return pid


def _csv(resp):
    assert resp.status_code == 200, resp.text
    assert resp.headers["content-type"].startswith("text/csv")
    return list(csv.reader(io.StringIO(resp.content.decode("utf-8-sig"))))


def test_bank_file_has_full_account_and_net(client, org_admin, make_employee):
    h = org_admin["headers"]
    emp = make_employee(h, base_salary=4_500_000, hire_date="2025-01-01",
                        preferred_payment_method="direct_deposit", bank_name="Unibank",
                        bank_account_number="1234567890")["employee"]
    pid = _paid_period(client, h)
    slip = client.get(f"/api/payroll/periods/{pid}/payslips", headers=h).json()["items"][0]["payslip"]

    rows = _csv(client.get(f"/api/payroll/periods/{pid}/export/bank", headers=h))
    assert rows[0][0] == "Nimewo"
    line = next(r for r in rows if r[0] == emp["employee_number"])
    assert line[2] == "Depo dirèk" and line[4] == "1234567890"
    assert line[5] == f"{slip['net_amount'] / 100:.2f}"
    assert rows[-1][0] == "TOTAL" and rows[-1][5] == line[5]


def test_social_and_tax_reports_match_payslips(client, org_admin, make_employee):
    h = org_admin["headers"]
    make_employee(h, base_salary=4_500_000, hire_date="2025-01-01")
    pid = _paid_period(client, h, pay=False)          # apwouve sifi
    slip = client.get(f"/api/payroll/periods/{pid}/payslips", headers=h).json()["items"][0]["payslip"]

    ona = _csv(client.get(f"/api/payroll/periods/{pid}/export/ona", headers=h))
    assert ona[-1][4] == f"{slip['ona_amount'] / 100:.2f}"
    ofatma = _csv(client.get(f"/api/payroll/periods/{pid}/export/ofatma", headers=h))
    assert ofatma[-1][4] == f"{slip['ofatma_amount'] / 100:.2f}"
    dgi = _csv(client.get(f"/api/payroll/periods/{pid}/export/dgi", headers=h))
    assert dgi[-1][4] == f"{slip['tax_amount'] / 100:.2f}"


def test_exports_need_approved_payroll_and_hr(client, org_admin, make_employee, make_employee_login):
    h = org_admin["headers"]
    make_employee(h, base_salary=4_500_000, hire_date="2025-01-01")
    pid = client.post("/api/payroll/periods", json={
        "name": "Bouyon", "start_date": "2026-07-01", "end_date": "2026-07-31", "pay_date": "2026-07-31",
    }, headers=h).json()["id"]
    assert client.get(f"/api/payroll/periods/{pid}/export/bank", headers=h).status_code == 400
    assert client.get(f"/api/payroll/periods/{pid}/export/xyz", headers=h).status_code == 422

    worker = make_employee_login(h)
    assert client.get(f"/api/payroll/periods/{pid}/export/bank",
                      headers=worker["headers"]).status_code == 403