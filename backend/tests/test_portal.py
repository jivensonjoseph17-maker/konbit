"""
Konbit — Tès pòtay anplwaye (èdtan mwen, total ane a)
Chemen: backend/tests/test_portal.py
"""

from datetime import date, datetime, time, timedelta, timezone

from app.database import SessionLocal
from app.models import AttendanceStatus, Employee, TimeEntry


# ---------------------------------------------------------------------------
# ZOUTI
# ---------------------------------------------------------------------------

def _entry(employee_id, work_date, *, worked=0, overtime=0,
           status=AttendanceStatus.CLOSED, clock_in=None):
    """Mete yon pwentaj dirèkteman: nou pa ka klòk in nan tan pase."""
    with SessionLocal() as db:
        emp = db.get(Employee, employee_id)
        start = clock_in or datetime.combine(work_date, time(12, 0), tzinfo=timezone.utc)
        is_open = status == AttendanceStatus.OPEN
        db.add(TimeEntry(
            organization_id=emp.organization_id,
            employee_id=employee_id,
            work_date=work_date,
            clock_in_at=start,
            clock_out_at=None if is_open else start + timedelta(minutes=worked),
            break_minutes=0,
            worked_minutes=None if is_open else worked,
            overtime_minutes=0 if is_open else overtime,
            status=status,
        ))
        db.commit()


def _hours(client, headers):
    resp = client.get("/api/portal/hours", headers=headers)
    assert resp.status_code == 200, resp.text
    return resp.json()


def _ytd(client, headers, year):
    resp = client.get(f"/api/portal/ytd?year={year}", headers=headers)
    assert resp.status_code == 200, resp.text
    return resp.json()


def _period(client, h, name, start, end, pay, *, pay_it):
    resp = client.post("/api/payroll/periods", json={
        "name": name, "start_date": start, "end_date": end, "pay_date": pay,
    }, headers=h)
    assert resp.status_code == 201, resp.text
    pid = resp.json()["id"]
    run = client.post(f"/api/payroll/periods/{pid}/run", json={"pay_period_id": pid}, headers=h)
    assert run.status_code == 200, run.text
    assert client.post(f"/api/payroll/periods/{pid}/approve", headers=h).status_code == 200
    if pay_it:
        paid = client.post(f"/api/payroll/periods/{pid}/pay",
                           json={"paid_at": f"{pay}T15:00:00Z"}, headers=h)
        assert paid.status_code == 200, paid.text
    return pid


# ---------------------------------------------------------------------------
# ÈDTAN MWEN
# ---------------------------------------------------------------------------

def test_portal_needs_login(client):
    assert client.get("/api/portal/hours").status_code == 401
    assert client.get("/api/portal/ytd").status_code == 401


def test_hours_today_week_and_pay_period(client, org_admin, make_employee_login):
    h = org_admin["headers"]
    me = make_employee_login(h)
    emp_id = me["employee"]["id"]
    today = date.fromisoformat(_hours(client, me["headers"])["today"])

    created = client.post("/api/payroll/periods", json={
        "name": "Peryòd tès",
        "start_date": (today - timedelta(days=10)).isoformat(),
        "end_date": (today + timedelta(days=4)).isoformat(),
        "pay_date": (today + timedelta(days=4)).isoformat(),
    }, headers=h)
    assert created.status_code == 201, created.text

    _entry(emp_id, today, worked=300)
    _entry(emp_id, today - timedelta(days=10), worked=540, overtime=60)   # peryòd, pa semèn
    _entry(emp_id, today - timedelta(days=9), status=AttendanceStatus.MISSING_OUT)
    _entry(emp_id, today - timedelta(days=40), worked=480)               # andeyò tout bagay

    data = _hours(client, me["headers"])
    assert data["clocked_in"] is False
    assert data["day"]["worked_minutes"] == 300
    assert data["week"]["worked_minutes"] == 300
    assert data["period"]["worked_minutes"] == 840
    assert data["period"]["overtime_minutes"] == 60
    assert data["period"]["days_worked"] == 2
    assert data["period_info"]["pay_period_id"] == created.json()["id"]
    assert data["needs_correction"] == 1


def test_open_shift_counts_live_and_month_is_fallback(client, org_admin, make_employee_login):
    me = make_employee_login(org_admin["headers"])
    today = date.fromisoformat(_hours(client, me["headers"])["today"])

    _entry(me["employee"]["id"], today, status=AttendanceStatus.OPEN,
           clock_in=datetime.now(timezone.utc) - timedelta(minutes=90))

    data = _hours(client, me["headers"])
    assert data["clocked_in"] is True
    assert 89 <= data["day"]["worked_minutes"] <= 91
    # Pa gen peryòd pewòl: nou pran mwa a
    assert data["period_info"]["pay_period_id"] is None
    assert data["period"]["start_date"] == today.replace(day=1).isoformat()


def test_colleague_hours_stay_private(client, org_admin, make_employee_login):
    h = org_admin["headers"]
    me = make_employee_login(h)
    other = make_employee_login(h)
    today = date.fromisoformat(_hours(client, me["headers"])["today"])
    _entry(other["employee"]["id"], today, worked=480)

    assert _hours(client, me["headers"])["day"]["worked_minutes"] == 0


# ---------------------------------------------------------------------------
# TOTAL ANE A
# ---------------------------------------------------------------------------

def test_ytd_counts_only_paid_slips(client, org_admin, make_employee_login):
    h = org_admin["headers"]
    me = make_employee_login(h, base_salary=4_500_000, hire_date="2025-01-01")

    empty = _ytd(client, me["headers"], 2026)
    assert empty["totals"] == [] and empty["years"] == []

    aug = _period(client, h, "Out 2026", "2026-08-01", "2026-08-31", "2026-08-31", pay_it=True)
    _period(client, h, "Septanm 2026", "2026-09-01", "2026-09-30", "2026-09-30", pay_it=False)

    slip = client.get(f"/api/payroll/periods/{aug}/payslips", headers=h).json()["items"][0]["payslip"]

    data = _ytd(client, me["headers"], 2026)
    assert data["years"] == [2026]
    [totals] = data["totals"]
    assert totals["payslip_count"] == 1                  # septanm poko peye
    assert totals["gross_amount"] == slip["gross_amount"]
    assert totals["net_amount"] == slip["net_amount"]
    assert totals["ona_amount"] == slip["ona_amount"]
    assert totals["gross_amount"] - totals["total_deductions"] == totals["net_amount"]

    assert _ytd(client, me["headers"], 2025)["totals"] == []