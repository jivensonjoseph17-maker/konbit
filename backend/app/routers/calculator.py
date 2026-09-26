"""
Konbit — Kalkilatè peyòl piblik
Chemen: backend/app/routers/calculator.py

Endpoint:
    POST /api/calculator     Kalkile retni yo pou yon salè (SAN KONEKSYON)

Paj piblik frontend/calculator.html sèvi avè l. Li itilize EGZAKTEMAN menm
fonksyon ak peyòl la (payroll.compute_deductions): yon chif sou kalkilatè a
toujou menm jan ak sa fich peye a ta montre pou menm salè a.

Pa gen done ki sere: nou kalkile epi nou retounen rezilta a, se tout.

TOUT MONTAN SE AN SANTIM. To yo se sa ki nan payroll.py — yon kontab dwe
verifye yo anvan konmbit.com lanse.
"""

from datetime import date, datetime
from typing import Literal, Optional
from zoneinfo import ZoneInfo

from fastapi import APIRouter
from pydantic import BaseModel, Field

from .payroll import (
    CFGDCT_MONTHLY_FLOOR,
    CFGDCT_RATE,
    FDU_CAS_RATE,
    OFATMA_RATE,
    ONA_RATE,
    SALARY_ABATEMENT,
    compute_deductions,
    supplemental_tax_rate,
)

router = APIRouter()

# Kalkilatè a pa lye ak okenn biznis: nou pran jodi a an lè Ayiti.
HAITI_TZ = ZoneInfo("America/Port-au-Prince")

PERIODS_PER_YEAR = {"monthly": 12, "semimonthly": 24, "weekly": 52}

# 100 milyon HTG pa peryòd — pi wo pase sa se sètènman yon erè tape.
MAX_CENTS = 100_000_000_00


class CalculatorRequest(BaseModel):
    gross_salary: int = Field(ge=0, le=MAX_CENTS, description="Salè brit pou peryòd la, an santim")
    bonus: int = Field(default=0, ge=0, le=MAX_CENTS,
                       description="Bonis, prim oswa èdtan siplemantè pou peryòd la, an santim")
    frequency: Literal["monthly", "semimonthly", "weekly"] = "monthly"
    pay_date: Optional[date] = Field(default=None, description="Pa defo: jodi a (lè Ayiti)")


class CalculatorResult(BaseModel):
    gross_salary: int
    bonus: int
    total_gross: int
    tax_amount: int                  # IRI sou salè a
    supplemental_tax_amount: int     # retni fiks sou bonis / èdtan siplemantè
    ona_amount: int
    ofatma_amount: int
    cfgdct_amount: int
    fdu_cas_amount: int
    total_deductions: int
    net_amount: int
    # Pou paj la ka esplike kalkil la ak VRÈ to yo, pa to ki ekri alamen.
    frequency: str
    periods_per_year: int
    pay_date: date
    supplemental_tax_rate: float
    ona_rate: float
    ofatma_rate: float
    cfgdct_rate: float
    cfgdct_applies: bool
    cfgdct_monthly_floor: int
    fdu_cas_rate: float
    salary_abatement: float


@router.post("", response_model=CalculatorResult)
def calculate(payload: CalculatorRequest):
    """Kalkile retni ak net pou yon salè. Pa bezwen konekte."""
    periods = PERIODS_PER_YEAR[payload.frequency]
    pay_date = payload.pay_date or datetime.now(HAITI_TZ).date()

    deductions = compute_deductions(
        salary_gross=payload.gross_salary,
        supplemental_gross=payload.bonus,
        periods_per_year=periods,
        pay_date=pay_date,
    )
    total_gross = payload.gross_salary + payload.bonus
    total_deductions = sum(deductions.values())

    return CalculatorResult(
        gross_salary=payload.gross_salary,
        bonus=payload.bonus,
        total_gross=total_gross,
        total_deductions=total_deductions,
        net_amount=max(0, total_gross - total_deductions),
        frequency=payload.frequency,
        periods_per_year=periods,
        pay_date=pay_date,
        supplemental_tax_rate=supplemental_tax_rate(pay_date),
        ona_rate=ONA_RATE,
        ofatma_rate=OFATMA_RATE,
        cfgdct_rate=CFGDCT_RATE,
        cfgdct_applies=deductions["cfgdct_amount"] > 0,
        cfgdct_monthly_floor=CFGDCT_MONTHLY_FLOOR,
        fdu_cas_rate=FDU_CAS_RATE,
        salary_abatement=SALARY_ABATEMENT,
        **deductions,
    )