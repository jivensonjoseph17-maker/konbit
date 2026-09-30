"""
Tès konje ki travèse 2 ane (routers/leaves.py, _days_by_year).

29 des 2031 (lendi) → 5 jan 2032 (lendi) = 6 jou travay:
  2031: lendi 29, madi 30, mèkredi 31           → 3 jou
  2032: jedi 1, vandredi 2, lendi 5             → 3 jou
Dat nan lavni: tès yo rete valab kèlkeswa jou yo kouri.
"""
from datetime import date

from app.routers.leaves import _days_by_year

START, END = "2031-12-29", "2032-01-05"


def _set_balance(client, headers, emp_id, year, days):
    r = client.put("/api/leaves/balances", json={
        "employee_id": emp_id, "leave_type": "vacation", "year": year, "entitled_days": days,
    }, headers=headers)
    assert r.status_code == 200, r.text


def _request(client, headers, start=START, end=END):
    return client.post("/api/leaves", json={
        "leave_type": "vacation", "start_date": start, "end_date": end,
    }, headers=headers)


def _used(client, headers, emp_id, year):
    r = client.get(f"/api/leaves/employee/{emp_id}/balances?year={year}", headers=headers)
    assert r.status_code == 200, r.text
    vac = [b for b in r.json()["balances"] if b["leave_type"] == "vacation"]
    return vac[0]["used_days"] if vac else 0


def test_days_by_year_splits_business_days():
    assert _days_by_year(date(2031, 12, 29), date(2032, 1, 5)) == {2031: 3, 2032: 3}
    # Yon sèl ane: menm total ak anvan.
    assert _days_by_year(date(2031, 3, 3), date(2031, 3, 7)) == {2031: 5}
    # Premye jou ane a se yon samdi: ane sa a pa parèt ditou.
    assert _days_by_year(date(2032, 12, 31), date(2033, 1, 2)) == {2032: 1}


def test_cross_year_needs_balance_for_each_year(client, org_admin, make_employee_login):
    h = org_admin["headers"]
    emp = make_employee_login(h)
    _set_balance(client, h, emp["employee"]["id"], 2031, 15)      # pa gen balans 2032

    r = _request(client, emp["headers"])
    assert r.status_code == 400
    assert "HR poko mete balans" in r.json()["detail"]


def test_each_year_is_checked_separately(client, org_admin, make_employee_login):
    h = org_admin["headers"]
    emp = make_employee_login(h)
    _set_balance(client, h, emp["employee"]["id"], 2031, 15)
    _set_balance(client, h, emp["employee"]["id"], 2032, 2)       # 3 jou nan 2032 > 2

    r = _request(client, emp["headers"])
    assert r.status_code == 400
    assert r.json()["detail"] == "Ou mande 3 jou men ou gen sèlman 2 jou ki rete."


def test_approval_and_cancel_split_between_years(client, org_admin, make_employee_login):
    h = org_admin["headers"]
    emp = make_employee_login(h)
    emp_id = emp["employee"]["id"]
    _set_balance(client, h, emp_id, 2031, 15)
    _set_balance(client, h, emp_id, 2032, 15)

    r = _request(client, emp["headers"])
    assert r.status_code == 201, r.text
    req = r.json()
    assert req["total_days"] == 6

    r = client.post(f"/api/leaves/{req['id']}/decide", json={"approve": True}, headers=h)
    assert r.status_code == 200, r.text
    assert _used(client, h, emp_id, 2031) == 3
    assert _used(client, h, emp_id, 2032) == 3

    r = client.delete(f"/api/leaves/{req['id']}", headers=emp["headers"])
    assert r.status_code == 200, r.text
    assert _used(client, h, emp_id, 2031) == 0
    assert _used(client, h, emp_id, 2032) == 0


def test_pending_counts_only_days_in_that_year(client, org_admin, make_employee_login):
    h = org_admin["headers"]
    emp = make_employee_login(h)
    emp_id = emp["employee"]["id"]
    _set_balance(client, h, emp_id, 2031, 15)
    _set_balance(client, h, emp_id, 2032, 4)

    # Demann 1 (ap tann): 3 jou nan 2032 → rete 1 jou pou 2032.
    assert _request(client, emp["headers"]).status_code == 201

    # Demann 2: mèkredi 7 ak jedi 8 janvye 2032 = 2 jou > 1.
    r = _request(client, emp["headers"], "2032-01-07", "2032-01-08")
    assert r.status_code == 400
    assert r.json()["detail"] == "Ou mande 2 jou men ou gen sèlman 1 jou ki rete."