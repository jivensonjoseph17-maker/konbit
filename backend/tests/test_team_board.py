"""
Konbit — Tès paj manadjè a: ekip mwen jodi a, konbyen bagay k ap tann
Chemen: backend/tests/test_team_board.py
"""

from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from app.database import SessionLocal
from app.models import (
    AttendanceStatus, Employee, LeaveRequest, LeaveType, RequestStatus, Shift, TimeEntry,
)

TZ = ZoneInfo("America/Port-au-Prince")     # fizo orè pa defo biznis tès yo


def _local_today() -> date:
    return datetime.now(TZ).date()


def _org_of(employee_id):
    with SessionLocal() as db:
        return db.get(Employee, employee_id).organization_id


def _open_entry(employee_id, minutes_ago=30):
    with SessionLocal() as db:
        db.add(TimeEntry(
            organization_id=_org_of(employee_id), employee_id=employee_id,
            work_date=_local_today(),
            clock_in_at=datetime.now(timezone.utc) - timedelta(minutes=minutes_ago),
            status=AttendanceStatus.OPEN,
        ))
        db.commit()


def _approved_leave_today(employee_id):
    with SessionLocal() as db:
        db.add(LeaveRequest(
            organization_id=_org_of(employee_id), employee_id=employee_id,
            leave_type=LeaveType.UNPAID, start_date=_local_today(), end_date=_local_today(),
            total_days=1, status=RequestStatus.APPROVED,
        ))
        db.commit()


def _shift_today(employee_id, start=time(0, 0), end=time(23, 59)):
    with SessionLocal() as db:
        db.add(Shift(
            organization_id=_org_of(employee_id), employee_id=employee_id,
            work_date=_local_today(), start_time=start, end_time=end,
            break_minutes=0, is_published=True,
        ))
        db.commit()


def _board(client, headers):
    resp = client.get("/api/team/today", headers=headers)
    assert resp.status_code == 200, resp.text
    return {i["employee_id"]: i for i in resp.json()["items"]}, resp.json()


def test_manager_sees_direct_reports_with_status(client, org_admin, make_employee, make_employee_login):
    h = org_admin["headers"]
    manager = make_employee_login(h, login_role="manager")
    mid = manager["employee"]["id"]
    working = make_employee(h, manager_id=mid)["employee"]
    on_leave = make_employee(h, manager_id=mid)["employee"]
    absent = make_employee(h, manager_id=mid)["employee"]
    stranger = make_employee(h)["employee"]

    _open_entry(working["id"])
    _approved_leave_today(on_leave["id"])
    _shift_today(absent["id"])                 # orè 00:00, pa gen pwentaj

    items, body = _board(client, manager["headers"])
    assert set(items) == {working["id"], on_leave["id"], absent["id"]}   # pa etranje a, pa manadjè a
    assert stranger["id"] not in items and mid not in items

    assert items[working["id"]]["status"] == "working"
    assert items[working["id"]]["worked_minutes"] >= 29
    assert items[on_leave["id"]]["status"] == "on_leave"
    assert items[on_leave["id"]]["leave_type"] == "unpaid"
    # Orè a kòmanse a minwi: apre 00:10 li absan, anvan sa li "poko".
    expected = "absent" if datetime.now(TZ).time() > time(0, 10) else "not_yet"
    assert items[absent["id"]]["status"] == expected
    assert items[absent["id"]]["shift_start"] == "00:00"
    assert body["counts"]["working"] == 1 and body["total"] == 3


def test_late_when_clocking_in_after_shift_start(client, org_admin, make_employee, make_employee_login):
    h = org_admin["headers"]
    manager = make_employee_login(h, login_role="manager")
    emp = make_employee(h, manager_id=manager["employee"]["id"])["employee"]
    now_local = datetime.now(TZ)
    if now_local.time() < time(0, 45):
        return                                  # twò bonè nan jounen an pou tès sa a
    _shift_today(emp["id"], start=time(0, 0))
    _open_entry(emp["id"], minutes_ago=15)      # antre 15 min de sa, orè a te kòmanse a minwi

    items, body = _board(client, manager["headers"])
    assert items[emp["id"]]["late"] is True
    assert body["late_count"] == 1


def test_hr_sees_everyone_but_employee_cannot(client, org_admin, make_employee, make_employee_login):
    h = org_admin["headers"]
    emp = make_employee(h)["employee"]
    items, _ = _board(client, h)
    assert emp["id"] in items

    worker = make_employee_login(h)
    assert client.get("/api/team/today", headers=worker["headers"]).status_code == 403
    count = client.get("/api/team/inbox-count", headers=worker["headers"])
    assert count.status_code == 200 and count.json()["total"] == 0


def test_inbox_count_includes_pending_leaves(client, org_admin, make_employee_login):
    h = org_admin["headers"]
    manager = make_employee_login(h, login_role="manager")
    worker = make_employee_login(h, manager_id=manager["employee"]["id"])

    start = _local_today() + timedelta(days=14)
    resp = client.post("/api/leaves", json={
        "leave_type": "unpaid",
        "start_date": start.isoformat(),
        "end_date": start.isoformat() if start.weekday() < 5
                    else (start + timedelta(days=7 - start.weekday())).isoformat(),
    }, headers=worker["headers"])
    assert resp.status_code == 201, resp.text

    count = client.get("/api/team/inbox-count", headers=manager["headers"]).json()
    assert count["leaves"] == 1
    assert count["total"] >= 1