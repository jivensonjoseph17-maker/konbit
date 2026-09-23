"""
Konbit — Tès konje ak balans
Chemen: backend/tests/test_leaves.py
"""

from datetime import date, timedelta


def _next_monday() -> date:
    """Pwochen lendi, pou tès yo pa depann de ki jou nou ye lè yo kouri."""
    today = date.today()
    days_ahead = (7 - today.weekday()) % 7 or 7
    return today + timedelta(days=days_ahead)


def test_hr_sets_balance_and_computes_remaining(client, org_admin, make_employee):
    emp = make_employee(org_admin["headers"])["employee"]
    year = date.today().year

    resp = client.put("/api/leaves/balances", json={
        "employee_id": emp["id"],
        "leave_type": "vacation",
        "year": year,
        "entitled_days": 15,
        "carried_over_days": 2,
    }, headers=org_admin["headers"])
    assert resp.status_code == 200
    body = resp.json()
    assert body["entitled_days"] == 15
    assert body["remaining_days"] == 17   # 15 + 2 pote - 0 itilize


def test_org_balances_list_includes_employee_with_zero_default(client, org_admin, make_employee):
    emp = make_employee(org_admin["headers"])["employee"]

    resp = client.get(
        "/api/leaves/balances",
        params={"leave_type": "vacation"},
        headers=org_admin["headers"],
    )
    assert resp.status_code == 200
    body = resp.json()
    row = next(r for r in body["items"] if r["employee_id"] == emp["id"])
    assert row["entitled_days"] == 0   # pa gen balans mete ankò pou li


def test_leave_request_counts_only_business_days(client, org_admin, make_employee_login):
    login = make_employee_login(org_admin["headers"])

    start = _next_monday()
    end = start + timedelta(days=4)   # Lendi -> Vandredi = 5 jou travay

    resp = client.post("/api/leaves", json={
        "leave_type": "unpaid",   # san peye: pa mande balans deja mete
        "start_date": start.isoformat(),
        "end_date": end.isoformat(),
        "reason": "Tès",
    }, headers=login["headers"])
    assert resp.status_code == 201, resp.text
    assert resp.json()["total_days"] == 5


def test_leave_request_blocked_without_enough_balance(client, org_admin, make_employee_login):
    login = make_employee_login(org_admin["headers"])
    emp_id = login["employee"]["id"]
    start = _next_monday()   # kalkile anvan — balans lan dwe sou MENM ane ak li

    client.put("/api/leaves/balances", json={
        "employee_id": emp_id,
        "leave_type": "vacation",
        "year": start.year,
        "entitled_days": 1,   # jis 1 jou disponib
        "carried_over_days": 0,
    }, headers=org_admin["headers"])

    end = start + timedelta(days=4)   # ta mande 5 jou

    resp = client.post("/api/leaves", json={
        "leave_type": "vacation",
        "start_date": start.isoformat(),
        "end_date": end.isoformat(),
    }, headers=login["headers"])
    assert resp.status_code == 400


def test_approval_deducts_balance(client, org_admin, make_employee_login):
    login = make_employee_login(org_admin["headers"])
    emp_id = login["employee"]["id"]
    start = _next_monday()   # kalkile anvan — balans lan dwe sou MENM ane ak li

    client.put("/api/leaves/balances", json={
        "employee_id": emp_id,
        "leave_type": "vacation",
        "year": start.year,
        "entitled_days": 15,
        "carried_over_days": 0,
    }, headers=org_admin["headers"])

    end = start + timedelta(days=1)   # Lendi + Madi = 2 jou

    created = client.post("/api/leaves", json={
        "leave_type": "vacation",
        "start_date": start.isoformat(),
        "end_date": end.isoformat(),
    }, headers=login["headers"])
    assert created.status_code == 201
    request_id = created.json()["id"]

    decided = client.post(f"/api/leaves/{request_id}/decide", json={
        "approve": True,
    }, headers=org_admin["headers"])
    assert decided.status_code == 200
    assert decided.json()["status"] == "approved"

    balances = client.get(
        f"/api/leaves/employee/{emp_id}/balances",
        params={"year": start.year},
        headers=org_admin["headers"],
    )
    row = next(b for b in balances.json()["balances"] if b["leave_type"] == "vacation")
    assert row["used_days"] == 2
    assert row["remaining_days"] == 13