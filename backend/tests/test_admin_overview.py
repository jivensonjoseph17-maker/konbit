"""
Konbit — Tès Tablo jesyon an (administratè / HR)
Chemen: backend/tests/test_admin_overview.py
"""

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

TZ = ZoneInfo("America/Port-au-Prince")


def _today() -> date:
    return datetime.now(TZ).date()


def _overview(client, h):
    resp = client.get("/api/admin/overview", headers=h)
    assert resp.status_code == 200, resp.text
    return resp.json()


def _steps(data):
    return {s["key"]: s for s in data["onboarding"]["steps"]}


def test_onboarding_checklist_progresses(client, org_admin, make_employee):
    h = org_admin["headers"]
    fresh = _overview(client, h)
    assert fresh["onboarding"]["complete"] is False
    assert _steps(fresh)["employees"]["done"] is False

    a = make_employee(h, base_salary=3_000_000)["employee"]
    b = make_employee(h, base_salary=2_000_000)["employee"]
    data = _overview(client, h)
    steps = _steps(data)
    assert steps["employees"]["done"] is True
    assert steps["leave_balances"] == {**steps["leave_balances"], "done": False, "progress": 0, "total": 2}
    assert data["headcount"]["active"] == 2

    for emp in (a, b):
        resp = client.put("/api/leaves/balances", json={
            "employee_id": emp["id"], "leave_type": "vacation", "year": _today().year,
            "entitled_days": 15, "carried_over_days": 0,
        }, headers=h)
        assert resp.status_code == 200, resp.text
    assert client.put("/api/kiosk/settings", json={"clock_mode": "both"}, headers=h).status_code == 200

    steps = _steps(_overview(client, h))
    assert steps["leave_balances"]["done"] is True
    assert steps["clock_mode"]["done"] is True
    assert steps["pay_period"]["done"] is False


def test_next_payroll_is_estimated_until_run(client, org_admin, make_employee):
    h = org_admin["headers"]
    make_employee(h, base_salary=3_000_000)
    make_employee(h, base_salary=2_000_000)

    start = _today() + timedelta(days=30)
    end = start + timedelta(days=13)
    resp = client.post("/api/payroll/periods", json={
        "name": "Peryòd tès", "start_date": start.isoformat(),
        "end_date": end.isoformat(), "pay_date": end.isoformat(),
    }, headers=h)
    assert resp.status_code == 201, resp.text

    data = _overview(client, h)
    nxt = data["next_payroll"]
    assert nxt["name"] == "Peryòd tès"
    assert nxt["estimated"] is True
    assert nxt["total_gross"] == 5_000_000
    assert nxt["days_until_pay"] == (end - _today()).days
    assert _steps(data)["pay_period"]["done"] is True


def test_declarations_sum_paid_withholdings(client, org_admin, make_employee):
    h = org_admin["headers"]
    make_employee(h, base_salary=4_500_000, hire_date="2025-01-01")

    decl = {d["code"]: d for d in _overview(client, h)["declarations"]}
    assert set(decl) == {"DGI", "ONA", "OFATMA"}
    assert all(d["days_left"] >= 0 for d in decl.values())
    assert decl["ONA"]["amount"] == 0

    # Yon pewòl peye nan mwa deklarasyon an: premye jou travay mwa a.
    year, month = map(int, decl["ONA"]["for_month"].split("-"))
    day = date(year, month, 1)
    while day.weekday() >= 5:
        day += timedelta(days=1)
    pid = client.post("/api/payroll/periods", json={
        "name": "Mwa deklarasyon", "start_date": day.isoformat(),
        "end_date": day.isoformat(), "pay_date": day.isoformat(),
    }, headers=h).json()["id"]
    assert client.post(f"/api/payroll/periods/{pid}/run", json={"pay_period_id": pid},
                       headers=h).status_code == 200
    assert client.post(f"/api/payroll/periods/{pid}/approve", headers=h).status_code == 200
    paid = client.post(f"/api/payroll/periods/{pid}/pay",
                       json={"paid_at": f"{day.isoformat()}T15:00:00Z"}, headers=h)
    assert paid.status_code == 200, paid.text

    slip = client.get(f"/api/payroll/periods/{pid}/payslips", headers=h).json()["items"][0]["payslip"]
    decl = {d["code"]: d for d in _overview(client, h)["declarations"]}
    assert decl["ONA"]["amount"] == slip["ona_amount"] > 0
    assert decl["OFATMA"]["amount"] == slip["ofatma_amount"]
    assert decl["DGI"]["amount"] == slip["tax_amount"] + slip["supplemental_tax_amount"]


def test_employees_cannot_see_admin_overview(client, org_admin, make_employee_login):
    worker = make_employee_login(org_admin["headers"])
    assert client.get("/api/admin/overview", headers=worker["headers"]).status_code == 403