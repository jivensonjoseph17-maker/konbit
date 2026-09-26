"""
Konbit — Tès dat peman reyèl la vs chanjman to bonis 1ye oktòb 2026
Chemen: backend/tests/test_payroll_pay_date.py

Retni sou bonis la depann de DAT PEMAN an (10% → 15% nan dat 1ye okt 2026).
Fich yo kalkile ak dat PREVWA a; tès sa yo verifye ke nou pa ka make yon
pewòl peye nan yon dat ki gen yon lòt to san nou pa rekalkile l.
"""

SEPT = {
    "name": "Septanm 2026",
    "start_date": "2026-09-01",
    "end_date": "2026-09-30",
    "pay_date": "2026-09-30",
}
BONUS = 500_000   # 5 000 HTG → 10% = 50 000 santim, 15% = 75 000 santim


def _slips(client, h, pid):
    r = client.get(f"/api/payroll/periods/{pid}/payslips", headers=h)
    assert r.status_code == 200, r.text
    return [row["payslip"] for row in r.json()["items"]]


def _approved_period(client, h, make_employee, bonus=BONUS):
    make_employee(h, base_salary=3_000_000, hire_date="2025-01-01")
    resp = client.post("/api/payroll/periods", json=SEPT, headers=h)
    assert resp.status_code == 201, resp.text
    pid = resp.json()["id"]

    run = client.post(f"/api/payroll/periods/{pid}/run", json={"pay_period_id": pid}, headers=h)
    assert run.status_code == 200, run.text

    if bonus:
        slip = _slips(client, h, pid)[0]
        adj = client.patch(f"/api/payroll/payslips/{slip['id']}",
                           json={"bonus_amount": bonus}, headers=h)
        assert adj.status_code == 200, adj.text
        assert adj.json()["supplemental_tax_amount"] == 50_000   # 10%

    ok = client.post(f"/api/payroll/periods/{pid}/approve", headers=h)
    assert ok.status_code == 200, ok.text
    return pid


def _pay(client, h, pid, paid_at):
    return client.post(f"/api/payroll/periods/{pid}/pay", json={"paid_at": paid_at}, headers=h)


def test_paying_in_october_with_bonus_is_blocked(client, org_admin, make_employee):
    h = org_admin["headers"]
    pid = _approved_period(client, h, make_employee)

    resp = _pay(client, h, pid, "2026-10-01T15:00:00Z")    # 11è AM an Ayiti
    assert resp.status_code == 409, resp.text
    assert "15%" in resp.json()["detail"]

    # Anyen pa chanje
    period = client.get(f"/api/payroll/periods/{pid}", headers=h).json()
    assert period["status"] == "approved"
    assert all(s["status"] == "approved" and s["paid_at"] is None for s in _slips(client, h, pid))


def test_evening_of_sept_30_in_haiti_is_still_september(client, org_admin, make_employee):
    """02:30 UTC 1ye okt = 22:30 lè Ayiti 30 sept: to 10% la rete bon."""
    h = org_admin["headers"]
    pid = _approved_period(client, h, make_employee)

    resp = _pay(client, h, pid, "2026-10-01T02:30:00Z")
    assert resp.status_code == 200, resp.text
    assert _slips(client, h, pid)[0]["supplemental_tax_amount"] == 50_000


def test_no_bonus_means_no_block(client, org_admin, make_employee):
    h = org_admin["headers"]
    pid = _approved_period(client, h, make_employee, bonus=0)

    resp = _pay(client, h, pid, "2026-10-02T15:00:00Z")
    assert resp.status_code == 200, resp.text


def test_changing_pay_date_recomputes_and_reopens(client, org_admin, make_employee):
    h = org_admin["headers"]
    pid = _approved_period(client, h, make_employee)

    resp = client.post(f"/api/payroll/periods/{pid}/pay-date",
                       json={"pay_date": "2026-10-01"}, headers=h)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["reopened"] is True
    assert body["changed_slips"] == 1
    assert body["period"]["status"] == "draft"
    assert body["period"]["pay_date"] == "2026-10-01"

    slip = _slips(client, h, pid)[0]
    assert slip["supplemental_tax_amount"] == 75_000       # 15%
    assert slip["status"] == "draft"

    # Apwouve ankò → peman 1ye okt pase kounye a
    assert client.post(f"/api/payroll/periods/{pid}/approve", headers=h).status_code == 200
    assert _pay(client, h, pid, "2026-10-01T15:00:00Z").status_code == 200


def test_same_rate_change_keeps_approval(client, org_admin, make_employee):
    """San bonis, chanje dat la pa chanje okenn chif: pewòl la rete apwouve."""
    h = org_admin["headers"]
    pid = _approved_period(client, h, make_employee, bonus=0)

    resp = client.post(f"/api/payroll/periods/{pid}/pay-date",
                       json={"pay_date": "2026-10-02"}, headers=h)
    assert resp.status_code == 200, resp.text
    assert resp.json()["reopened"] is False
    assert resp.json()["period"]["status"] == "approved"


def test_pay_date_rules(client, org_admin, make_employee):
    h = org_admin["headers"]
    pid = _approved_period(client, h, make_employee)

    before_end = client.post(f"/api/payroll/periods/{pid}/pay-date",
                             json={"pay_date": "2026-09-29"}, headers=h)
    assert before_end.status_code == 400

    assert _pay(client, h, pid, "2026-10-01T02:30:00Z").status_code == 200
    after_paid = client.post(f"/api/payroll/periods/{pid}/pay-date",
                             json={"pay_date": "2026-10-05"}, headers=h)
    assert after_paid.status_code == 400