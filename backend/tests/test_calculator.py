"""
Konbit — Tès kalkilatè pewòl piblik la
Chemen: backend/tests/test_calculator.py
"""

from datetime import date

from app.routers.payroll import compute_deductions


def _calc(client, **body):
    resp = client.post("/api/calculator", json=body)
    assert resp.status_code == 200, resp.text
    return resp.json()


def test_no_login_needed_and_same_numbers_as_payroll(client):
    r = _calc(client, gross_salary=5_000_000, frequency="monthly", pay_date="2026-09-30")
    expected = compute_deductions(5_000_000, 0, 12, date(2026, 9, 30))
    for key, value in expected.items():
        assert r[key] == value, key
    assert r["total_deductions"] == sum(expected.values())
    assert r["net_amount"] == 5_000_000 - sum(expected.values())
    # 50 000 HTG/mwa: 90% × 12 = 540 000/an → IRI anyèl 69 000 → 5 750 HTG/mwa
    assert r["tax_amount"] == 575_000


def test_bonus_rate_changes_on_october_first_2026(client):
    before = _calc(client, gross_salary=0, bonus=1_000_000, pay_date="2026-09-30")
    after = _calc(client, gross_salary=0, bonus=1_000_000, pay_date="2026-10-01")
    assert before["supplemental_tax_amount"] == 100_000     # 10%
    assert after["supplemental_tax_amount"] == 150_000      # 15%
    assert after["supplemental_tax_rate"] == 0.15


def test_frequency_changes_the_annualization(client):
    weekly = _calc(client, gross_salary=1_200_000, frequency="weekly", pay_date="2026-09-30")
    assert weekly["periods_per_year"] == 52
    expected = compute_deductions(1_200_000, 0, 52, date(2026, 9, 30))
    assert weekly["tax_amount"] == expected["tax_amount"]


def test_cfgdct_only_above_monthly_floor(client):
    low = _calc(client, gross_salary=400_000, pay_date="2026-09-30")      # 4 000 HTG/mwa
    high = _calc(client, gross_salary=600_000, pay_date="2026-09-30")     # 6 000 HTG/mwa
    assert low["cfgdct_amount"] == 0 and low["cfgdct_applies"] is False
    assert high["cfgdct_amount"] == 6_000 and high["cfgdct_applies"] is True


def test_invalid_input_is_rejected(client):
    assert client.post("/api/calculator", json={"gross_salary": -5}).status_code == 422
    assert client.post("/api/calculator", json={"gross_salary": 100, "frequency": "daily"}).status_code == 422