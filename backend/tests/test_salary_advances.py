"""
Tès avans sou salè — API (routers/salary_advances.py) ak pewòl la (/run).
Kalkil pi yo (vèsman, limit net la) nan test_salary_advance_plan.py.

Peryòd pewòl yo an 2030: yon avans apwouve JODI A toujou anvan dat peman
yo, kèlkeswa jou tès yo kouri.
"""
from calendar import monthrange
from datetime import date, timedelta

SALARY = 4_500_000          # 45 000 HTG pa mwa
TAX_FIELDS = (
    "tax_amount", "supplemental_tax_amount", "ona_amount",
    "ofatma_amount", "cfgdct_amount", "fdu_cas_amount",
)


def _team(make_employee_login, admin_headers):
    """Yon manadjè ak yon anplwaye anba l, tou de ak kont koneksyon."""
    manager = make_employee_login(admin_headers, login_role="manager", base_salary=SALARY)
    worker = make_employee_login(
        admin_headers, manager_id=manager["employee"]["id"], base_salary=SALARY,
    )
    return manager, worker


def _request(client, headers, amount, installments=1):
    return client.post("/api/salary-advances/me", json={
        "amount": amount, "installments": installments,
    }, headers=headers)


def _grant(client, headers, employee_id, amount, installments=1):
    r = client.post("/api/salary-advances", json={
        "employee_id": employee_id, "amount": amount, "installments": installments,
    }, headers=headers)
    assert r.status_code == 201, r.text
    return r.json()


def _period(client, headers, month):
    start = date(2030, month, 1)
    end = date(2030, month, monthrange(2030, month)[1])
    r = client.post("/api/payroll/periods", json={
        "name": f"Tès {month:02d}/2030",
        "start_date": start.isoformat(),
        "end_date": end.isoformat(),
        "pay_date": (end + timedelta(days=5)).isoformat(),
    }, headers=headers)
    assert r.status_code == 201, r.text
    return r.json()["id"]


def _run(client, headers, period_id):
    r = client.post(f"/api/payroll/periods/{period_id}/run", json={
        "pay_period_id": period_id, "include_overtime": True,
    }, headers=headers)
    assert r.status_code == 200, r.text
    return r.json()


def _slip(client, headers, period_id, employee_id):
    r = client.get(f"/api/payroll/periods/{period_id}/payslips", headers=headers)
    assert r.status_code == 200, r.text
    return next(i["payslip"] for i in r.json()["items"] if i["payslip"]["employee_id"] == employee_id)


def _advance(client, headers, advance_id):
    r = client.get("/api/salary-advances", headers=headers)
    assert r.status_code == 200, r.text
    return next(a for a in r.json()["items"] if a["id"] == advance_id)


# ---------------------------------------------------------------------------
# DEMANN AK APWOBASYON
# ---------------------------------------------------------------------------

def test_request_then_manager_approves(client, org_admin, make_employee_login):
    manager, worker = _team(make_employee_login, org_admin["headers"])

    r = client.post("/api/salary-advances/me", json={
        "amount": 900_000, "installments": 3, "reason": "Lekòl timoun yo",
    }, headers=worker["headers"])
    assert r.status_code == 201, r.text
    adv = r.json()
    assert adv["status"] == "pending"
    assert adv["installment_amount"] == 300_000
    assert adv["remaining_amount"] == 900_000

    r = client.get("/api/salary-advances?status=pending", headers=manager["headers"])
    assert r.status_code == 200, r.text
    assert [a["id"] for a in r.json()["items"]] == [adv["id"]]

    r = client.post(f"/api/salary-advances/{adv['id']}/decide",
                    json={"approve": True}, headers=manager["headers"])
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "approved"

    r = client.get("/api/salary-advances/me", headers=worker["headers"])
    assert r.json()["items"][0]["status"] == "approved"


def test_amount_limit_and_one_active_advance(client, org_admin, make_employee_login):
    _, worker = _team(make_employee_login, org_admin["headers"])

    assert _request(client, worker["headers"], SALARY + 1).status_code == 400
    assert _request(client, worker["headers"], 100_000).status_code == 201
    assert _request(client, worker["headers"], 100_000).status_code == 409


def test_employee_cancels_pending_request(client, org_admin, make_employee_login):
    _, worker = _team(make_employee_login, org_admin["headers"])
    adv = _request(client, worker["headers"], 200_000).json()

    r = client.post(f"/api/salary-advances/me/{adv['id']}/cancel", json={}, headers=worker["headers"])
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "cancelled"
    # Yon demann anile pa bloke yon nouvo demann.
    assert _request(client, worker["headers"], 200_000).status_code == 201


def test_only_direct_manager_or_hr_decides(client, org_admin, make_employee_login):
    _, worker = _team(make_employee_login, org_admin["headers"])
    other_manager = make_employee_login(org_admin["headers"], login_role="manager", base_salary=SALARY)
    adv = _request(client, worker["headers"], 200_000).json()

    r = client.post(f"/api/salary-advances/{adv['id']}/decide",
                    json={"approve": True}, headers=other_manager["headers"])
    assert r.status_code == 404
    r = client.post(f"/api/salary-advances/{adv['id']}/decide",
                    json={"approve": True}, headers=worker["headers"])
    assert r.status_code == 403


def test_nobody_approves_own_advance(client, org_admin, make_employee_login):
    hr = make_employee_login(org_admin["headers"], login_role="hr", base_salary=SALARY)
    adv = _request(client, hr["headers"], 200_000).json()

    r = client.post(f"/api/salary-advances/{adv['id']}/decide",
                    json={"approve": True}, headers=hr["headers"])
    assert r.status_code == 403
    r = client.post("/api/salary-advances", json={
        "employee_id": hr["employee"]["id"], "amount": 100_000, "installments": 1,
    }, headers=hr["headers"])
    assert r.status_code == 403


def test_other_business_cannot_see_or_decide(client, make_org, make_employee_login):
    a, b = make_org(), make_org()
    _, worker = _team(make_employee_login, a["headers"])
    adv = _request(client, worker["headers"], 200_000).json()

    r = client.get("/api/salary-advances", headers=b["headers"])
    assert r.status_code == 200, r.text
    assert r.json()["total"] == 0
    r = client.post(f"/api/salary-advances/{adv['id']}/decide",
                    json={"approve": True}, headers=b["headers"])
    assert r.status_code == 404


# ---------------------------------------------------------------------------
# PEWÒL
# ---------------------------------------------------------------------------

def test_payroll_takes_one_installment_after_tax(client, org_admin, make_employee_login):
    h = org_admin["headers"]
    _, worker = _team(make_employee_login, h)
    emp_id = worker["employee"]["id"]
    adv = _grant(client, h, emp_id, 900_000, 3)

    pid = _period(client, h, 1)
    _run(client, h, pid)
    slip = _slip(client, h, pid, emp_id)

    assert slip["advance_amount"] == 300_000
    assert slip["gross_amount"] == SALARY              # brit la pa chanje
    taxes = sum(slip[f] for f in TAX_FIELDS)
    assert slip["net_amount"] == slip["gross_amount"] - taxes - 300_000

    item = _advance(client, h, adv["id"])
    assert item["repaid_amount"] == 300_000
    assert item["remaining_amount"] == 600_000
    assert item["repayments"][0]["pay_period_id"] == pid


def test_advance_is_repaid_after_last_installment(client, org_admin, make_employee_login):
    h = org_admin["headers"]
    _, worker = _team(make_employee_login, h)
    emp_id = worker["employee"]["id"]
    adv = _grant(client, h, emp_id, 500_000, 2)

    taken = []
    for month in (1, 2, 3):
        pid = _period(client, h, month)
        _run(client, h, pid)
        taken.append(_slip(client, h, pid, emp_id)["advance_amount"])

    assert taken == [250_000, 250_000, 0]
    item = _advance(client, h, adv["id"])
    assert item["status"] == "repaid"
    assert item["remaining_amount"] == 0


def test_installment_never_exceeds_net(client, org_admin, make_employee):
    """1 000 HTG brit: ONA 60 + OFATMA 30 + FDU/CAS 10 → net 900 HTG."""
    h = org_admin["headers"]
    emp_id = make_employee(h, base_salary=100_000)["employee"]["id"]
    adv = _grant(client, h, emp_id, 100_000, 1)

    pid = _period(client, h, 1)
    result = _run(client, h, pid)
    slip = _slip(client, h, pid, emp_id)

    assert slip["advance_amount"] == 90_000
    assert slip["net_amount"] == 0
    assert any("net la pa ase" in w for w in result["warnings"])
    assert _advance(client, h, adv["id"])["remaining_amount"] == 10_000


def test_hr_closes_balance(client, org_admin, make_employee_login):
    h = org_admin["headers"]
    _, worker = _team(make_employee_login, h)
    emp_id = worker["employee"]["id"]
    adv = _grant(client, h, emp_id, 600_000, 2)

    pid = _period(client, h, 1)
    _run(client, h, pid)
    assert _slip(client, h, pid, emp_id)["advance_amount"] == 300_000

    r = client.post(f"/api/salary-advances/{adv['id']}/close",
                    json={"note": "Patwon an padone rès la."}, headers=h)
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "closed"
    assert r.json()["remaining_amount"] == 0

    pid2 = _period(client, h, 2)
    _run(client, h, pid2)
    assert _slip(client, h, pid2, emp_id)["advance_amount"] == 0