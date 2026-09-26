"""
Konbit — Tès total retni yo nan /run ak /tax-rates
Chemen: backend/tests/test_payroll_totals.py
"""

import uuid

from app.routers.payroll import DEDUCTION_FIELDS


def test_run_total_deductions_counts_every_deduction(client, make_org):
    h = make_org()["headers"]
    r = client.post("/api/employees", headers=h, json={
        "first_name": "Total", "last_name": uuid.uuid4().hex[:6],
        "hire_date": "2026-01-05", "base_salary": 5_000_000,   # 50 000 HTG: CFGDCT aplike
        "preferred_payment_method": "check", "create_login": False,
    })
    assert r.status_code in (200, 201), r.text

    period = client.post("/api/payroll/periods", headers=h, json={
        "name": "Oktòb 2026", "start_date": "2026-10-01",
        "end_date": "2026-10-31", "pay_date": "2026-11-05",
    }).json()

    run = client.post(f"/api/payroll/periods/{period['id']}/run", headers=h,
                      json={"pay_period_id": period["id"], "include_overtime": True})
    assert run.status_code == 200, run.text
    result = run.json()

    slips = client.get(f"/api/payroll/periods/{period['id']}/payslips", headers=h).json()["items"]
    expected = sum(row["payslip"][f] or 0 for row in slips for f in DEDUCTION_FIELDS)
    assert result["total_deductions"] == expected
    # Ansyen kalkil la te konte sèlman IRI + ONA + OFATMA.
    old = sum((row["payslip"][f] or 0) for row in slips
              for f in ("tax_amount", "ona_amount", "ofatma_amount"))
    assert result["total_deductions"] > old
    assert result["total_gross"] - result["total_deductions"] == result["total_net"]


def test_tax_rates_uses_business_today(client, make_org):
    h = make_org()["headers"]
    r = client.get("/api/payroll/tax-rates", headers=h)
    assert r.status_code == 200, r.text
    assert r.json()["supplemental_tax_rate_today"] in (0.10, 0.15)