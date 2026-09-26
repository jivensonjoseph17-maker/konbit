"""
Konbit — Tès kalkil pewòl
Chemen: backend/tests/test_payroll.py

Tès sa yo verifye ke kòd la aplike règ ki ekri nan payroll.py yo.
Yo PA verifye si règ yo menm kòrèk dapre lalwa — se yon kontab ki dwe
fè sa. Tout montan an santim: 3_000_000 = 30 000,00 HTG.
"""

from datetime import date
from types import SimpleNamespace

import pytest

from app.routers.payroll import (
    _annual_iri,
    _periods_per_year,
    compute_deductions,
    supplemental_tax_rate,
)

AVAN_OKTOB = date(2026, 9, 30)
APRE_OKTOB = date(2026, 10, 1)


# ---------------------------------------------------------------------------
# Retni sou bonis: 10% → 15% nan dat 1ye oktòb 2026
# ---------------------------------------------------------------------------

def test_supplemental_rate_changes_on_october_first():
    assert supplemental_tax_rate(date(2026, 9, 30)) == 0.10
    assert supplemental_tax_rate(date(2026, 10, 1)) == 0.15
    assert supplemental_tax_rate(date(2027, 1, 15)) == 0.15


# ---------------------------------------------------------------------------
# Baremn IRI anyèl
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("annual, expected", [
    (0, 0),
    (6_000_000, 0),              # 60 000 HTG: egzan
    (24_000_000, 1_800_000),     # 180 000 × 10%
    (30_000_000, 2_700_000),     # + 60 000 × 15%
    (150_000_000, 33_400_000),   # 18 000 + 36 000 + 130 000 + 150 000 HTG
])
def test_annual_iri_brackets(annual, expected):
    assert _annual_iri(annual) == expected


# ---------------------------------------------------------------------------
# Yon salè mansyèl 30 000 HTG, san bonis
# ---------------------------------------------------------------------------

def test_monthly_salary_30000_htg():
    d = compute_deductions(
        salary_gross=3_000_000, supplemental_gross=0,
        periods_per_year=12, pay_date=AVAN_OKTOB,
    )
    # IRI: 90% × 30 000 × 12 = 324 000/an → 18 000 + 12 600 = 30 600/an → 2 550/mwa
    assert d["tax_amount"] == 255_000
    assert d["supplemental_tax_amount"] == 0
    assert d["ona_amount"] == 180_000       # 6%
    assert d["ofatma_amount"] == 90_000     # 3%
    assert d["cfgdct_amount"] == 30_000     # 1%, paske ≥ 5 000 HTG/mwa
    assert d["fdu_cas_amount"] == 30_000    # 1%


def test_low_salary_is_iri_exempt():
    # 5 000 HTG/mwa → 90% × 12 = 54 000/an, anba 60 000
    d = compute_deductions(500_000, 0, 12, AVAN_OKTOB)
    assert d["tax_amount"] == 0
    assert d["cfgdct_amount"] == 5_000      # egzakteman nan plafon an: li aplike


# ---------------------------------------------------------------------------
# Bonis: retni fiks, pa nan baremn nan, men nan kotizasyon sosyal yo
# ---------------------------------------------------------------------------

def test_bonus_does_not_change_iri_but_counts_for_ona():
    san_bonis = compute_deductions(3_000_000, 0, 12, APRE_OKTOB)
    ak_bonis = compute_deductions(3_000_000, 500_000, 12, APRE_OKTOB)

    assert ak_bonis["tax_amount"] == san_bonis["tax_amount"]
    assert ak_bonis["ona_amount"] == 210_000       # 6% × 35 000
    assert ak_bonis["ofatma_amount"] == 105_000    # 3% × 35 000


def test_bonus_withholding_before_and_after_october():
    avan = compute_deductions(3_000_000, 500_000, 12, AVAN_OKTOB)
    apre = compute_deductions(3_000_000, 500_000, 12, APRE_OKTOB)
    assert avan["supplemental_tax_amount"] == 50_000   # 10% × 5 000 HTG
    assert apre["supplemental_tax_amount"] == 75_000   # 15% × 5 000 HTG


# ---------------------------------------------------------------------------
# CFGDCT: plafon mansyèl la konvèti pou moun ki peye chak kenzèn
# ---------------------------------------------------------------------------

def test_cfgdct_biweekly_uses_monthly_equivalent():
    # 2 400 HTG/kenzèn → 4 800/mwa: anba plafon an
    anba = compute_deductions(240_000, 0, 24, AVAN_OKTOB)
    assert anba["cfgdct_amount"] == 0

    # 2 600 HTG/kenzèn → 5 200/mwa: li aplike
    anwo = compute_deductions(260_000, 0, 24, AVAN_OKTOB)
    assert anwo["cfgdct_amount"] == 2_600


# ---------------------------------------------------------------------------
# Kantite peryòd pa ane
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("start, end, expected", [
    (date(2026, 9, 1), date(2026, 9, 7), 52),     # semèn
    (date(2026, 9, 1), date(2026, 9, 15), 24),    # kenzèn
    (date(2026, 9, 1), date(2026, 9, 30), 12),    # mwa
    (date(2026, 2, 1), date(2026, 2, 28), 12),    # fevriye
])
def test_periods_per_year(start, end, expected):
    period = SimpleNamespace(start_date=start, end_date=end)
    assert _periods_per_year(period) == expected