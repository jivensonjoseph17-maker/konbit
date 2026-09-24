"""
Konbit — Tès apwobasyon tan travay
Chemen: backend/tests/test_timesheets.py

Règ: manadjè a prepare (apwouve èdtan), HR peye. Opsyon B: peyòl la
mande konfimasyon pou moun ki poko apwouve, epi li pa peye èdtan
siplemantè yo.
"""

from datetime import date, datetime, time, timedelta, timezone

from app.database import SessionLocal
from app.models import AttendanceStatus, Employee, TimeEntry


# ---------------------------------------------------------------------------
# ZOUTI
# ---------------------------------------------------------------------------

def _make_period(client, headers, days_ago_end=31, length=14):
    end = date.today() - timedelta(days=days_ago_end)
    start = end - timedelta(days=length)
    resp = client.post("/api/payroll/periods", json={
        "name": f"Tès {start:%d/%m}–{end:%d/%m}",
        "start_date": start.isoformat(),
        "end_date": end.isoformat(),
        "pay_date": max(end, date.today() - timedelta(days=days_ago_end - 3)).isoformat(),
    }, headers=headers)
    assert resp.status_code == 201, resp.text
    return resp.json()


def _add_entry(employee_id, work_date, status=AttendanceStatus.CLOSED,
               worked=600, overtime=120):
    """Mete yon pwentaj dirèkteman: nou pa ka klòk in nan tan pase."""
    with SessionLocal() as db:
        emp = db.get(Employee, employee_id)
        start = datetime.combine(work_date, time(12, 0), tzinfo=timezone.utc)
        is_open = status == AttendanceStatus.OPEN
        entry = TimeEntry(
            organization_id=emp.organization_id,
            employee_id=employee_id,
            work_date=work_date,
            clock_in_at=start,
            clock_out_at=None if is_open else start + timedelta(minutes=worked),
            break_minutes=0,
            worked_minutes=0 if is_open else worked,
            overtime_minutes=0 if is_open else overtime,
            status=status,
        )
        db.add(entry)
        db.commit()
        return entry.id


def _team(make_employee_login, headers, **worker_extra):
    manager = make_employee_login(headers, login_role="manager")
    worker = make_employee_login(headers, manager_id=manager["employee"]["id"], **worker_extra)
    return manager, worker


def _row(client, headers, period_id, employee_id):
    resp = client.get(f"/api/timesheets/{period_id}", headers=headers)
    assert resp.status_code == 200, resp.text
    return next((r for r in resp.json()["items"] if r["employee_id"] == employee_id), None)


# ---------------------------------------------------------------------------
# MANADJÈ A
# ---------------------------------------------------------------------------

def test_manager_sees_and_approves_team_timesheet(client, org_admin, make_employee_login):
    h = org_admin["headers"]
    manager, worker = _team(make_employee_login, h)
    period = _make_period(client, h)
    _add_entry(worker["employee"]["id"], date.fromisoformat(period["start_date"]) + timedelta(days=1))

    row = _row(client, manager["headers"], period["id"], worker["employee"]["id"])
    assert row["status"] == "pending"
    assert row["overtime_minutes"] == 120
    assert row["can_decide"] is True

    resp = client.post(
        f"/api/timesheets/{period['id']}/employees/{worker['employee']['id']}/approve",
        json={"note": "Tout bon."}, headers=manager["headers"],
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "approved"


def test_manager_cannot_approve_self_or_outside_team(client, org_admin, make_employee_login):
    h = org_admin["headers"]
    manager, _ = _team(make_employee_login, h)
    stranger = make_employee_login(h)
    period = _make_period(client, h)

    for target in (manager, stranger):
        resp = client.post(
            f"/api/timesheets/{period['id']}/employees/{target['employee']['id']}/approve",
            json={}, headers=manager["headers"],
        )
        assert resp.status_code == 403

    assert _row(client, manager["headers"], period["id"], stranger["employee"]["id"]) is None


def test_cannot_approve_with_open_entry(client, org_admin, make_employee_login):
    h = org_admin["headers"]
    manager, worker = _team(make_employee_login, h)
    period = _make_period(client, h)
    _add_entry(worker["employee"]["id"], date.fromisoformat(period["start_date"]),
               status=AttendanceStatus.MISSING_OUT, worked=0, overtime=0)

    resp = client.post(
        f"/api/timesheets/{period['id']}/employees/{worker['employee']['id']}/approve",
        json={}, headers=manager["headers"],
    )
    assert resp.status_code == 400


def test_cannot_approve_before_period_ends(client, org_admin, make_employee_login):
    h = org_admin["headers"]
    manager, worker = _team(make_employee_login, h)
    today = date.today()
    period = client.post("/api/payroll/periods", json={
        "name": "Peryòd kouran",
        "start_date": (today - timedelta(days=3)).isoformat(),
        "end_date": (today + timedelta(days=3)).isoformat(),
        "pay_date": (today + timedelta(days=5)).isoformat(),
    }, headers=h).json()

    resp = client.post(
        f"/api/timesheets/{period['id']}/employees/{worker['employee']['id']}/approve",
        json={}, headers=manager["headers"],
    )
    assert resp.status_code == 400


def test_return_to_hr_needs_a_note(client, org_admin, make_employee_login):
    h = org_admin["headers"]
    manager, worker = _team(make_employee_login, h)
    period = _make_period(client, h)
    url = f"/api/timesheets/{period['id']}/employees/{worker['employee']['id']}/return"

    assert client.post(url, json={"note": ""}, headers=manager["headers"]).status_code == 422
    resp = client.post(url, json={"note": "Li te la jiska 5è, li bliye pwente."},
                       headers=manager["headers"])
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "returned"


# ---------------------------------------------------------------------------
# BLOKAJ AK HR
# ---------------------------------------------------------------------------

def test_approval_locks_hr_corrections_until_reset(client, org_admin, make_employee_login):
    h = org_admin["headers"]
    manager, worker = _team(make_employee_login, h)
    period = _make_period(client, h)
    entry_id = _add_entry(worker["employee"]["id"], date.fromisoformat(period["start_date"]))
    base = f"/api/timesheets/{period['id']}/employees/{worker['employee']['id']}"

    assert client.post(f"{base}/approve", json={}, headers=manager["headers"]).status_code == 200

    fix = {"break_minutes": 30, "reason": "Poz la pa t anrejistre."}
    assert client.patch(f"/api/attendance/{entry_id}", json=fix, headers=h).status_code == 409

    # Manadjè a pa ka retire apwobasyon an: se HR sèlman
    assert client.delete(base, headers=manager["headers"]).status_code == 403
    assert client.delete(base, headers=h).status_code == 200

    assert client.patch(f"/api/attendance/{entry_id}", json=fix, headers=h).status_code == 200
    assert _row(client, h, period["id"], worker["employee"]["id"])["status"] == "pending"


# ---------------------------------------------------------------------------
# PEYÒL — OPSYON B
# ---------------------------------------------------------------------------

def test_payroll_asks_confirmation_and_skips_unapproved_overtime(
    client, org_admin, make_employee_login,
):
    h = org_admin["headers"]
    manager = make_employee_login(h, login_role="manager")
    mgr_id = manager["employee"]["id"]
    approved = make_employee_login(h, manager_id=mgr_id, base_salary=3_000_000)
    pending = make_employee_login(h, manager_id=mgr_id, base_salary=3_000_000)
    period = _make_period(client, h)
    day = date.fromisoformat(period["start_date"]) + timedelta(days=1)
    for w in (approved, pending):
        _add_entry(w["employee"]["id"], day)

    ok = client.post(
        f"/api/timesheets/{period['id']}/employees/{approved['employee']['id']}/approve",
        json={}, headers=manager["headers"],
    )
    assert ok.status_code == 200, ok.text

    run_url = f"/api/payroll/periods/{period['id']}/run"
    body = {"pay_period_id": period["id"]}

    blocked = client.post(run_url, json=body, headers=h)
    assert blocked.status_code == 409
    assert pending["employee"]["employee_number"] in blocked.json()["detail"]
    assert approved["employee"]["employee_number"] not in blocked.json()["detail"]

    resp = client.post(f"{run_url}?confirm_unapproved=true", json=body, headers=h)
    assert resp.status_code == 200, resp.text
    assert len(resp.json()["unapproved"]) == 1

    slips = client.get(f"/api/payroll/periods/{period['id']}/payslips", headers=h).json()["items"]
    by_emp = {s["payslip"]["employee_id"]: s["payslip"] for s in slips}

    assert by_emp[approved["employee"]["id"]]["overtime_amount"] > 0
    assert by_emp[pending["employee"]["id"]]["overtime_amount"] == 0
    assert by_emp[pending["employee"]["id"]]["overtime_hours"] == 2
    # Salè de baz la peye kanmenm
    assert by_emp[pending["employee"]["id"]]["base_amount"] > 0


def test_payroll_without_time_entries_needs_no_confirmation(client, org_admin, make_employee):
    """Yon salarye ki pa janm pwente pa gen anyen pou apwouve: peyòl la pa bloke."""
    h = org_admin["headers"]
    make_employee(h, base_salary=3_000_000)
    period = _make_period(client, h)

    resp = client.post(f"/api/payroll/periods/{period['id']}/run",
                       json={"pay_period_id": period["id"]}, headers=h)
    assert resp.status_code == 200, resp.text
    assert resp.json()["unapproved"] == []