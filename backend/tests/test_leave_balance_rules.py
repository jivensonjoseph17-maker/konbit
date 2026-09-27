"""
Konbit — Tès règ balans konje yo
Chemen: backend/tests/test_leave_balance_rules.py

  - Pa gen balans (HR poko mete l) → pa ka mande vakans.
  - Demann ki toujou ap tann yo konte nan jou ki disponib yo.
  - Apwobasyon an verifye balans lan ankò; balans lan pa janm negatif.
"""

from datetime import date, timedelta


def _next_monday() -> date:
    today = date.today()
    return today + timedelta(days=(7 - today.weekday()) % 7 or 7)


def _set_balance(client, h, emp_id, days, year):
    resp = client.put("/api/leaves/balances", json={
        "employee_id": emp_id, "leave_type": "vacation", "year": year,
        "entitled_days": days, "carried_over_days": 0,
    }, headers=h)
    assert resp.status_code == 200, resp.text


def _ask(client, headers, start, days):
    """`days` jou travay apati yon lendi (maks 5)."""
    return client.post("/api/leaves", json={
        "leave_type": "vacation",
        "start_date": start.isoformat(),
        "end_date": (start + timedelta(days=days - 1)).isoformat(),
    }, headers=headers)


def test_vacation_needs_a_balance_first(client, org_admin, make_employee_login):
    me = make_employee_login(org_admin["headers"])
    resp = _ask(client, me["headers"], _next_monday(), 2)
    assert resp.status_code == 400
    assert "HR" in resp.json()["detail"]

    # Konje san peye pa bezwen balans
    unpaid = client.post("/api/leaves", json={
        "leave_type": "unpaid",
        "start_date": _next_monday().isoformat(),
        "end_date": _next_monday().isoformat(),
    }, headers=me["headers"])
    assert unpaid.status_code == 201, unpaid.text


def test_pending_requests_count_against_balance(client, org_admin, make_employee_login):
    h = org_admin["headers"]
    me = make_employee_login(h)
    start = _next_monday()
    _set_balance(client, h, me["employee"]["id"], 3, start.year)

    assert _ask(client, me["headers"], start, 2).status_code == 201       # rete 1
    second = _ask(client, me["headers"], start + timedelta(weeks=1), 2)    # mande 2
    assert second.status_code == 400
    assert "1" in second.json()["detail"]


def test_approval_rechecks_balance_and_never_goes_negative(client, org_admin, make_employee_login):
    h = org_admin["headers"]
    me = make_employee_login(h)
    emp_id = me["employee"]["id"]
    start = _next_monday()
    _set_balance(client, h, emp_id, 5, start.year)

    req = _ask(client, me["headers"], start, 3)
    assert req.status_code == 201, req.text
    req_id = req.json()["id"]

    _set_balance(client, h, emp_id, 1, start.year)        # HR bese balans lan
    blocked = client.post(f"/api/leaves/{req_id}/decide", json={"approve": True}, headers=h)
    assert blocked.status_code == 409

    balances = client.get(f"/api/leaves/employee/{emp_id}/balances",
                          params={"year": start.year}, headers=h).json()["balances"]
    row = next(b for b in balances if b["leave_type"] == "vacation")
    assert row["used_days"] == 0 and row["remaining_days"] == 1

    # Refize toujou posib
    refused = client.post(f"/api/leaves/{req_id}/decide", json={"approve": False}, headers=h)
    assert refused.status_code == 200
    assert refused.json()["status"] == "rejected"