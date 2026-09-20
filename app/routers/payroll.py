"""
Konbit — Router Peyòl
Chemen: backend/app/routers/payroll.py

Endpoint yo:
    POST   /api/payroll/periods              Kreye yon peryòd peye (HR)
    GET    /api/payroll/periods              Lis peryòd yo
    GET    /api/payroll/periods/{id}         Detay yon peryòd
    POST   /api/payroll/periods/{id}/run     Jenere fich peye yo
    POST   /api/payroll/periods/{id}/approve Apwouve peyòl la
    POST   /api/payroll/periods/{id}/pay     Make l peye
    GET    /api/payroll/periods/{id}/payslips  Tout fich peye yon peryòd
    GET    /api/payroll/me/payslips          Pwòp fich peye mwen
    GET    /api/payroll/payslips/{id}        Yon fich peye
    PATCH  /api/payroll/payslips/{id}        Ajiste (bonis, dediksyon, chèk/depo)
    GET    /api/payroll/employee/{id}/payslips

TOUT MONTAN SE AN SANTIM. 150050 = 1 500,50 HTG.

DEDIKSYON AYITI (valè pa defo — chak biznis ka gen pwòp to pa l):
  - ONA    : 6% sou salè brit (pati anplwaye a)
  - OFATMA : 3% sou salè brit (pati anplwaye a)
  - Enpo sou salè: baremn pwogresif DGI

ATANSYON: to sa yo se yon pwen depa. Yon kontab ayisyen dwe verifye yo
anvan ou sèvi ak sistèm lan pou vrè peyòl.
"""

import logging
from datetime import date, datetime, timezone
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..deps import (
    CurrentEmployee,
    CurrentUser,
    DbSession,
    TenantId,
    ensure_can_view_employee,
    require_hr,
)
from ..models import (
    AttendanceStatus,
    AuditLog,
    Currency,
    Employee,
    EmploymentStatus,
    LeaveRequest,
    LeaveType,
    Notification,
    PaymentMethod,
    PayPeriod,
    PayrollStatus,
    Payslip,
    RequestStatus,
    TimeEntry,
    User,
)
from ..schemas import (
    Message,
    PayPeriodCreate,
    PayPeriodOut,
    PayrollRunRequest,
    PayslipAdjust,
    PayslipOut,
)

logger = logging.getLogger("konbit")

router = APIRouter()

# ---------------------------------------------------------------------------
# TO DEDIKSYON — AYITI
#
# Sous: DGI (dgi.gouv.ht), dekrè 29 septanm 2005 atik 149 (baremn),
# atik 92 (abatman), dekrè 29 septanm 1986 atik 96 (retni sou bonis),
# bidjè rektifikatif 2025-2026 (Moniteur 5 jen 2026) atik 3.
#
# YON KONTAB DWE VERIFYE TO SA YO ANVAN YON VRÈ BIZNIS SÈVI AK SISTÈM LAN.
# ---------------------------------------------------------------------------

ONA_RATE = 0.06          # Retrèt — Office National d'Assurance-vieillesse
OFATMA_RATE = 0.03       # Sante — accidents, maladie, maternité
CFGDCT_RATE = 0.01       # Kolektivite teritoryal yo
FDU_CAS_RATE = 0.01      # Fon dijans + Kès Asistans Sosyal

# CFGDCT aplike sèlman si salè brit mansyèl la ≥ 5 000 HTG
CFGDCT_MONTHLY_FLOOR = 500000        # an santim

# Abatman espesyal 10% (atik 92): baremn nan aplike sou 90% brit la.
SALARY_ABATEMENT = 0.10

OVERTIME_MULTIPLIER = 1.5

# Baremn IRI (anyèl, an santim HTG). Fòm: (limit siperyè, to). None = san limit.
TAX_BRACKETS = [
    (6000000, 0.00),      # jiska 60 000 HTG/an : egzan
    (24000000, 0.10),     # 60 001 – 240 000
    (48000000, 0.15),     # 240 001 – 480 000
    (100000000, 0.25),    # 480 001 – 1 000 000
    (None, 0.30),         # plis pase 1 000 000
]

# Retni alasous FIKS sou bonis, etrèn, prim ak èdtan siplemantè.
# Se yon prelèvman SEPARE de baremn nan — li pa pase nan tranch yo.
# Atik 96 dekrè 1986 la te mete l a 10%. Bidjè rektifikatif 2025-2026 la
# monte l a 15%, men MEF la (nòt 14 jiyè 2026) ranvwaye antre an vigè a
# pou 1ye oktòb 2026.
SUPPLEMENTAL_TAX_RATE_OLD = 0.10
SUPPLEMENTAL_TAX_RATE_NEW = 0.15
SUPPLEMENTAL_TAX_CHANGE_DATE = date(2026, 10, 1)


def supplemental_tax_rate(pay_date: date) -> float:
    """To retni sou bonis/prim/èdtan siplemantè, dapre dat peyman an."""
    if pay_date >= SUPPLEMENTAL_TAX_CHANGE_DATE:
        return SUPPLEMENTAL_TAX_RATE_NEW
    return SUPPLEMENTAL_TAX_RATE_OLD


# ---------------------------------------------------------------------------
# ZOUTI ENTÈN
# ---------------------------------------------------------------------------

def _audit(db: Session, request: Request, user: User, action: str,
           entity_type: str, entity_id: int, changes: Optional[str] = None) -> None:
    try:
        db.add(AuditLog(
            organization_id=user.organization_id,
            user_id=user.id,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            changes=changes,
            ip_address=request.client.host if request.client else None,
            user_agent=(request.headers.get("user-agent") or "")[:255],
        ))
        db.commit()
    except Exception:
        db.rollback()
        logger.warning("Jounal odit echwe", exc_info=True)


def _notify(db: Session, org_id: int, user_id: Optional[int],
            title: str, body: str, link: Optional[str] = None) -> None:
    if user_id is None:
        return
    try:
        db.add(Notification(
            organization_id=org_id, user_id=user_id,
            title=title, body=body, link_url=link, category="payroll",
        ))
        db.commit()
    except Exception:
        db.rollback()


def _annual_iri(annual_taxable_cents: int) -> int:
    """Kalkil IRI anyèl ak baremn pwogresif 5 tranch la. Tout an santim."""
    tax = 0
    lower = 0
    for upper, rate in TAX_BRACKETS:
        if upper is None:
            if annual_taxable_cents > lower:
                tax += int((annual_taxable_cents - lower) * rate)
            break
        if annual_taxable_cents > upper:
            tax += int((upper - lower) * rate)
            lower = upper
        else:
            if annual_taxable_cents > lower:
                tax += int((annual_taxable_cents - lower) * rate)
            break
    return tax


def compute_deductions(
    salary_gross: int,
    supplemental_gross: int,
    periods_per_year: int,
    pay_date: date,
) -> dict:
    """
    Kalkile tout dediksyon yo pou yon fich peye. Tout montan an santim.

    `salary_gross`       : salè regilye a (san bonis, san èdtan siplemantè)
    `supplemental_gross` : bonis + prim + peyman èdtan siplemantè

    DE BAZ SEPARE:
      1. Salè regilye a pase nan baremn pwogresif la, sou 90% brit
         (abatman 10%, atik 92), anyalize epi divize pa kantite peryòd.
      2. Bonis ak èdtan siplemantè pran yon retni FIKS sou montan brit yo,
         san abatman, san baremn (atik 96).

    ATANSYON: ONA ak OFATMA PA redwi baz enpozab la. Se yon erè komen.
    """
    total_gross = salary_gross + supplemental_gross

    # --- Kotizasyon sosyal ak kontribisyon (sou tout brit la) ---
    ona = int(total_gross * ONA_RATE)
    ofatma = int(total_gross * OFATMA_RATE)
    fdu_cas = int(total_gross * FDU_CAS_RATE)

    # CFGDCT: plafon an defini pa mwa. Nou konvèti peryòd la an ekivalan mansyèl
    # pou nou konpare ak plafon an san nou pa egzante moun ki peye chak kenzèn.
    monthly_equivalent = int(total_gross * periods_per_year / 12)
    cfgdct = int(total_gross * CFGDCT_RATE) if monthly_equivalent >= CFGDCT_MONTHLY_FLOOR else 0

    # --- IRI sou salè regilye a ---
    taxable_base = int(salary_gross * (1 - SALARY_ABATEMENT))
    annual_iri = _annual_iri(taxable_base * periods_per_year)
    iri = int(annual_iri / periods_per_year)

    # --- Retni fiks sou bonis / èdtan siplemantè ---
    rate = supplemental_tax_rate(pay_date)
    supplemental_tax = int(supplemental_gross * rate)

    return {
        "tax_amount": iri,
        "supplemental_tax_amount": supplemental_tax,
        "ona_amount": ona,
        "ofatma_amount": ofatma,
        "cfgdct_amount": cfgdct,
        "fdu_cas_amount": fdu_cas,
    }


def _periods_per_year(period: PayPeriod) -> int:
    """Konbyen fwa peryòd sa a repete nan yon ane (pou anyalize enpo a)."""
    days = (period.end_date - period.start_date).days + 1
    if days <= 8:
        return 52       # chak semèn
    if days <= 16:
        return 24       # chak kenzèn
    if days <= 32:
        return 12       # chak mwa
    return 12


def _get_period_or_404(db: Session, org_id: int, period_id: int) -> PayPeriod:
    period = db.query(PayPeriod).filter(
        PayPeriod.id == period_id,
        PayPeriod.organization_id == org_id,
    ).first()
    if period is None:
        raise HTTPException(status_code=404, detail="Peryòd la pa jwenn.")
    return period


def _get_payslip_or_404(db: Session, org_id: int, payslip_id: int) -> Payslip:
    slip = db.query(Payslip).filter(
        Payslip.id == payslip_id,
        Payslip.organization_id == org_id,
    ).first()
    if slip is None:
        raise HTTPException(status_code=404, detail="Fich peye a pa jwenn.")
    return slip


def _worked_minutes_in_period(db: Session, org_id: int, employee_id: int,
                              start: date, end: date) -> tuple[int, int]:
    """Retounen (minit nòmal, minit siplemantè) ki fèmen nan peryòd la."""
    rows = db.query(TimeEntry).filter(
        TimeEntry.organization_id == org_id,
        TimeEntry.employee_id == employee_id,
        TimeEntry.work_date >= start,
        TimeEntry.work_date <= end,
        TimeEntry.status.in_([AttendanceStatus.CLOSED, AttendanceStatus.ADJUSTED]),
    ).all()

    total = sum(r.worked_minutes or 0 for r in rows)
    overtime = sum(r.overtime_minutes or 0 for r in rows)
    return max(0, total - overtime), overtime


def _unpaid_leave_days(db: Session, org_id: int, employee_id: int,
                       start: date, end: date) -> float:
    """Jou konje san peye nan peryòd la — nou rache yo nan salè a."""
    rows = db.query(LeaveRequest).filter(
        LeaveRequest.organization_id == org_id,
        LeaveRequest.employee_id == employee_id,
        LeaveRequest.status == RequestStatus.APPROVED,
        LeaveRequest.leave_type == LeaveType.UNPAID,
        LeaveRequest.start_date <= end,
        LeaveRequest.end_date >= start,
    ).all()
    return float(sum(float(r.total_days) for r in rows))


def _compute_payslip(db: Session, org_id: int, emp: Employee,
                     period: PayPeriod, include_overtime: bool) -> dict:
    """
    Kalkile yon fich peye. Retounen yon diksyonè ak tout montan an santim.

    Salarye (base_salary): montan fiks pa peryòd, mwens jou san peye.
    Moun pa lè (hourly_rate): kalkil sou minit yo travay reyèlman.
    """
    periods = _periods_per_year(period)
    normal_min, overtime_min = _worked_minutes_in_period(
        db, org_id, emp.id, period.start_date, period.end_date
    )

    if emp.hourly_rate:
        base = int(emp.hourly_rate * (normal_min / 60))
        overtime_amount = (
            int(emp.hourly_rate * (overtime_min / 60) * OVERTIME_MULTIPLIER)
            if include_overtime else 0
        )
    else:
        base = int(emp.base_salary or 0)
        # Rache jou konje san peye
        unpaid = _unpaid_leave_days(db, org_id, emp.id, period.start_date, period.end_date)
        if unpaid > 0:
            working_days_in_period = 22 if periods == 12 else 11
            daily = base / working_days_in_period if working_days_in_period else 0
            base = max(0, int(base - daily * unpaid))

        hourly_equiv = (emp.base_salary or 0) / (173.33 if periods == 12 else 86.67)
        overtime_amount = (
            int(hourly_equiv * (overtime_min / 60) * OVERTIME_MULTIPLIER)
            if include_overtime else 0
        )

    # Èdtan siplemantè tonbe nan menm retni fiks la ak bonis yo.
    deductions = compute_deductions(
        salary_gross=base,
        supplemental_gross=overtime_amount,
        periods_per_year=periods,
        pay_date=period.pay_date,
    )

    gross = base + overtime_amount
    net = max(0, gross - sum(deductions.values()))

    account = (emp.bank_account_number or "").strip()
    return {
        "base_amount": base,
        "overtime_amount": overtime_amount,
        "bonus_amount": 0,
        "gross_amount": gross,
        "other_deductions": 0,
        "net_amount": net,
        "currency": emp.currency or Currency.HTG,
        "hours_worked": round(normal_min / 60, 2),
        "overtime_hours": round(overtime_min / 60, 2),
        "payment_method": emp.preferred_payment_method or PaymentMethod.CHECK,
        "bank_name": emp.bank_name,
        "account_last4": account[-4:] if len(account) >= 4 else None,
        **deductions,
    }


def _recompute(slip: Payslip, period: PayPeriod) -> None:
    """
    Rekalkile TOUT dediksyon yo apre yon ajisteman.

    Sa a se koreksyon yon bug: premye vèsyon an te rekalkile net la san li
    pa t retouche enpo a. Yon bonis t ap pase san enpo, epi DGI mande
    yon retni fiks sou bonis — sa se yon manke nan obligasyon anplwayè a.
    """
    base = slip.base_amount or 0
    overtime = slip.overtime_amount or 0
    bonus = slip.bonus_amount or 0

    periods = _periods_per_year(period)
    deductions = compute_deductions(
        salary_gross=base,
        supplemental_gross=overtime + bonus,
        periods_per_year=periods,
        pay_date=period.pay_date,
    )

    for field, value in deductions.items():
        setattr(slip, field, value)

    slip.gross_amount = base + overtime + bonus
    slip.net_amount = max(0, (
        slip.gross_amount
        - sum(deductions.values())
        - (slip.other_deductions or 0)
    ))


# ---------------------------------------------------------------------------
# PERYÒD
# ---------------------------------------------------------------------------

@router.post(
    "/periods",
    response_model=PayPeriodOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_hr)],
)
def create_period(payload: PayPeriodCreate, org_id: TenantId, db: DbSession):
    overlap = db.query(PayPeriod).filter(
        PayPeriod.organization_id == org_id,
        PayPeriod.start_date <= payload.end_date,
        PayPeriod.end_date >= payload.start_date,
    ).first()
    if overlap:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Peryòd la kouvri menm dat ak '{overlap.name}'.",
        )

    period = PayPeriod(organization_id=org_id, **payload.model_dump())
    db.add(period)
    db.commit()
    db.refresh(period)
    return PayPeriodOut.model_validate(period)


class PeriodListResponse(BaseModel):
    total: int
    items: list[PayPeriodOut]


def _period_out(db: Session, period: PayPeriod) -> PayPeriodOut:
    count, total_net = db.query(
        func.count(Payslip.id), func.coalesce(func.sum(Payslip.net_amount), 0)
    ).filter(Payslip.pay_period_id == period.id).first()

    out = PayPeriodOut.model_validate(period)
    out.payslip_count = count or 0
    out.total_net = int(total_net or 0)
    return out


@router.get("/periods", response_model=PeriodListResponse, dependencies=[Depends(require_hr)])
def list_periods(
    org_id: TenantId,
    db: DbSession,
    status_filter: Annotated[Optional[PayrollStatus], Query(alias="status")] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 24,
):
    q = db.query(PayPeriod).filter(PayPeriod.organization_id == org_id)
    if status_filter:
        q = q.filter(PayPeriod.status == status_filter)

    items = q.order_by(PayPeriod.start_date.desc()).limit(limit).all()
    return PeriodListResponse(
        total=len(items), items=[_period_out(db, p) for p in items]
    )


@router.get("/periods/{period_id}", response_model=PayPeriodOut, dependencies=[Depends(require_hr)])
def read_period(period_id: int, org_id: TenantId, db: DbSession):
    return _period_out(db, _get_period_or_404(db, org_id, period_id))


# ---------------------------------------------------------------------------
# JENERE FICH PEYE YO
# ---------------------------------------------------------------------------

class PayrollRunResult(BaseModel):
    period_id: int
    created: int
    skipped: int
    total_gross: int
    total_net: int
    total_deductions: int
    warnings: list[str] = []


@router.post(
    "/periods/{period_id}/run",
    response_model=PayrollRunResult,
    dependencies=[Depends(require_hr)],
)
def run_payroll(
    period_id: int,
    payload: PayrollRunRequest,
    user: CurrentUser,
    org_id: TenantId,
    request: Request,
    db: DbSession,
):
    """
    Jenere fich peye pou tout anplwaye aktif (oswa yon lis presi).
    Ou ka rele sa a plizyè fwa: anplwaye ki gen yon fich deja ap sote.
    Peyòl ki deja PAID pa ka rejenere.
    """
    period = _get_period_or_404(db, org_id, period_id)

    if period.status == PayrollStatus.PAID:
        raise HTTPException(
            status_code=400,
            detail="Peyòl sa a deja peye. Ou pa ka rejenere l.",
        )

    q = db.query(Employee).filter(
        Employee.organization_id == org_id,
        Employee.is_active.is_(True),
        Employee.status.in_([EmploymentStatus.ACTIVE, EmploymentStatus.ON_LEAVE]),
    )
    if payload.employee_ids:
        q = q.filter(Employee.id.in_(payload.employee_ids))

    employees = q.all()

    created = skipped = 0
    total_gross = total_net = total_deductions = 0
    warnings: list[str] = []

    for emp in employees:
        exists = db.query(Payslip).filter(
            Payslip.pay_period_id == period.id,
            Payslip.employee_id == emp.id,
        ).first()
        if exists:
            skipped += 1
            continue

        if not emp.base_salary and not emp.hourly_rate:
            warnings.append(
                f"{emp.first_name} {emp.last_name} ({emp.employee_number}): "
                "pa gen salè ni to orè. Sote."
            )
            skipped += 1
            continue

        data = _compute_payslip(db, org_id, emp, period, payload.include_overtime)

        method = data["payment_method"]
        if method == PaymentMethod.DIRECT_DEPOSIT and not emp.bank_account_number:
            warnings.append(
                f"{emp.first_name} {emp.last_name}: depo dirèk chwazi men "
                "pa gen nimewo kont. Chanje pou chèk."
            )
            data["payment_method"] = PaymentMethod.CHECK
        elif method in (PaymentMethod.MONCASH, PaymentMethod.NATCASH) \
                and not emp.mobile_money_number:
            warnings.append(
                f"{emp.first_name} {emp.last_name}: {method.value} chwazi men "
                "pa gen nimewo telefòn. Chanje pou chèk."
            )
            data["payment_method"] = PaymentMethod.CHECK

        slip = Payslip(
            organization_id=org_id,
            pay_period_id=period.id,
            employee_id=emp.id,
            status=PayrollStatus.DRAFT,
            **data,
        )
        db.add(slip)

        created += 1
        total_gross += data["gross_amount"]
        total_net += data["net_amount"]
        total_deductions += (
            data["tax_amount"] + data["ona_amount"] + data["ofatma_amount"]
        )

    db.commit()
    _audit(db, request, user, "run_payroll", "pay_period", period.id,
           changes=f"{created} fich kreye, {skipped} sote.")

    return PayrollRunResult(
        period_id=period.id,
        created=created,
        skipped=skipped,
        total_gross=total_gross,
        total_net=total_net,
        total_deductions=total_deductions,
        warnings=warnings,
    )


# ---------------------------------------------------------------------------
# APWOBASYON AK PEYMAN
# ---------------------------------------------------------------------------

@router.post(
    "/periods/{period_id}/approve",
    response_model=PayPeriodOut,
    dependencies=[Depends(require_hr)],
)
def approve_payroll(
    period_id: int,
    user: CurrentUser,
    org_id: TenantId,
    request: Request,
    db: DbSession,
):
    """Apwouve peyòl la. Apre sa, fich yo pa ka ajiste ankò."""
    period = _get_period_or_404(db, org_id, period_id)

    if period.status != PayrollStatus.DRAFT:
        raise HTTPException(
            status_code=400,
            detail=f"Peryòd la nan estati '{period.status.value}'.",
        )

    count = db.query(func.count(Payslip.id)).filter(
        Payslip.pay_period_id == period.id
    ).scalar() or 0
    if count == 0:
        raise HTTPException(
            status_code=400,
            detail="Pa gen fich peye. Rele /run anvan.",
        )

    period.status = PayrollStatus.APPROVED
    period.approved_by_id = user.id
    period.approved_at = datetime.now(timezone.utc)

    db.query(Payslip).filter(Payslip.pay_period_id == period.id).update(
        {Payslip.status: PayrollStatus.APPROVED}, synchronize_session=False
    )
    db.commit()
    db.refresh(period)

    _audit(db, request, user, "approve", "pay_period", period.id,
           changes=f"{count} fich peye apwouve.")
    return _period_out(db, period)


class MarkPaidRequest(BaseModel):
    paid_at: Optional[datetime] = None
    check_start_number: Optional[int] = Field(
        default=None, description="Premye nimewo chèk; li monte pou chak moun."
    )


class MarkPaidResult(BaseModel):
    period_id: int
    paid_count: int
    total_net: int
    by_method: dict[str, int]


@router.post(
    "/periods/{period_id}/pay",
    response_model=MarkPaidResult,
    dependencies=[Depends(require_hr)],
)
def mark_paid(
    period_id: int,
    payload: MarkPaidRequest,
    user: CurrentUser,
    org_id: TenantId,
    request: Request,
    db: DbSession,
):
    """
    Make peyòl la peye epi avèti chak anplwaye.
    Si ou bay `check_start_number`, nou asiyen nimewo chèk yo otomatikman.
    """
    period = _get_period_or_404(db, org_id, period_id)

    if period.status != PayrollStatus.APPROVED:
        raise HTTPException(
            status_code=400,
            detail="Ou dwe apwouve peyòl la anvan ou make l peye.",
        )

    slips = db.query(Payslip).filter(Payslip.pay_period_id == period.id).all()
    paid_at = payload.paid_at or datetime.now(timezone.utc)
    check_no = payload.check_start_number

    by_method: dict[str, int] = {}
    total_net = 0

    for slip in slips:
        slip.status = PayrollStatus.PAID
        slip.paid_at = paid_at

        if slip.payment_method == PaymentMethod.CHECK and check_no is not None:
            if not slip.check_number:
                slip.check_number = str(check_no)
                check_no += 1

        key = slip.payment_method.value
        by_method[key] = by_method.get(key, 0) + 1
        total_net += slip.net_amount or 0

    period.status = PayrollStatus.PAID
    db.commit()

    for slip in slips:
        emp = db.query(Employee).filter(Employee.id == slip.employee_id).first()
        if emp and emp.user_id:
            method_label = {
                PaymentMethod.CHECK: "chèk",
                PaymentMethod.DIRECT_DEPOSIT: "depo dirèk",
                PaymentMethod.CASH: "lajan kach",
                PaymentMethod.MONCASH: "MonCash",
                PaymentMethod.NATCASH: "NatCash",
            }.get(slip.payment_method, slip.payment_method.value)

            _notify(
                db, org_id, emp.user_id,
                title="Fich peye w disponib",
                body=(
                    f"Peyman pou '{period.name}' fèt pa {method_label}. "
                    f"Net: {slip.net_amount / 100:,.2f} {slip.currency.value}."
                ),
                link=f"/payslips/{slip.id}",
            )

    _audit(db, request, user, "mark_paid", "pay_period", period.id,
           changes=f"{len(slips)} fich peye. Total net: {total_net}.")

    return MarkPaidResult(
        period_id=period.id,
        paid_count=len(slips),
        total_net=total_net,
        by_method=by_method,
    )


# ---------------------------------------------------------------------------
# FICH PEYE
# ---------------------------------------------------------------------------

class PayslipRow(BaseModel):
    payslip: PayslipOut
    employee_name: str
    employee_number: str


class PayslipListResponse(BaseModel):
    total: int
    total_net: int
    items: list[PayslipRow]


@router.get(
    "/periods/{period_id}/payslips",
    response_model=PayslipListResponse,
    dependencies=[Depends(require_hr)],
)
def period_payslips(period_id: int, org_id: TenantId, db: DbSession):
    _get_period_or_404(db, org_id, period_id)

    rows = (
        db.query(Payslip, Employee)
        .join(Employee, Payslip.employee_id == Employee.id)
        .filter(Payslip.pay_period_id == period_id)
        .order_by(Employee.last_name, Employee.first_name)
        .all()
    )

    items = [
        PayslipRow(
            payslip=PayslipOut.model_validate(slip),
            employee_name=f"{emp.first_name} {emp.last_name}",
            employee_number=emp.employee_number,
        )
        for slip, emp in rows
    ]
    return PayslipListResponse(
        total=len(items),
        total_net=sum(i.payslip.net_amount for i in items),
        items=items,
    )


class MyPayslipsResponse(BaseModel):
    total: int
    items: list[PayslipOut]


@router.get("/me/payslips", response_model=MyPayslipsResponse)
def my_payslips(
    emp: CurrentEmployee,
    org_id: TenantId,
    db: DbSession,
    limit: Annotated[int, Query(ge=1, le=100)] = 24,
):
    """
    Pwòp fich peye mwen. Anplwaye a wè sèlman sa ki APWOUVE oswa PEYE —
    yon bouyon ka gen erè ladan l.
    """
    slips = db.query(Payslip).filter(
        Payslip.organization_id == org_id,
        Payslip.employee_id == emp.id,
        Payslip.status.in_([PayrollStatus.APPROVED, PayrollStatus.PAID]),
    ).order_by(Payslip.created_at.desc()).limit(limit).all()

    return MyPayslipsResponse(
        total=len(slips), items=[PayslipOut.model_validate(s) for s in slips]
    )


@router.get("/payslips/{payslip_id}", response_model=PayslipOut)
def read_payslip(payslip_id: int, user: CurrentUser, org_id: TenantId, db: DbSession):
    slip = _get_payslip_or_404(db, org_id, payslip_id)
    emp = db.query(Employee).filter(Employee.id == slip.employee_id).first()
    if emp is None:
        raise HTTPException(status_code=404, detail="Anplwaye a pa jwenn.")

    ensure_can_view_employee(user, emp, db)

    # Yon anplwaye pa wè pwòp bouyon l
    if slip.status == PayrollStatus.DRAFT and emp.user_id == user.id:
        raise HTTPException(
            status_code=403,
            detail="Fich peye sa a poko apwouve.",
        )
    return slip


@router.patch(
    "/payslips/{payslip_id}",
    response_model=PayslipOut,
    dependencies=[Depends(require_hr)],
)
def adjust_payslip(
    payslip_id: int,
    payload: PayslipAdjust,
    user: CurrentUser,
    org_id: TenantId,
    request: Request,
    db: DbSession,
):
    """
    Ajiste yon fich peye: bonis, lòt dediksyon, oswa chanje chèk ↔ depo.
    Sèlman pandan li nan estati DRAFT.
    """
    slip = _get_payslip_or_404(db, org_id, payslip_id)

    if slip.status != PayrollStatus.DRAFT:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Fich la nan estati '{slip.status.value}'. "
                "Sèlman yon bouyon ka ajiste."
            ),
        )

    period = _get_period_or_404(db, org_id, slip.pay_period_id)
    before = (
        f"bonis={slip.bonus_amount}, enpo={slip.tax_amount}, "
        f"retni-sip={slip.supplemental_tax_amount}, net={slip.net_amount}"
    )
    data = payload.model_dump(exclude_unset=True)

    if "payment_method" in data and data["payment_method"] is not None:
        emp = db.query(Employee).filter(Employee.id == slip.employee_id).first()
        method = data["payment_method"]
        if method == PaymentMethod.DIRECT_DEPOSIT and not (emp and emp.bank_account_number):
            raise HTTPException(
                status_code=400,
                detail="Anplwaye a pa gen nimewo kont labank pou depo dirèk.",
            )
        if method in (PaymentMethod.MONCASH, PaymentMethod.NATCASH) \
                and not (emp and emp.mobile_money_number):
            raise HTTPException(
                status_code=400,
                detail=f"Anplwaye a pa gen nimewo telefòn pou {method.value}.",
            )

    for field, value in data.items():
        setattr(slip, field, value)

    _recompute(slip, period)
    db.commit()
    db.refresh(slip)

    _audit(db, request, user, "adjust", "payslip", slip.id,
           changes=f"{before} -> bonis={slip.bonus_amount}, "
                   f"enpo={slip.tax_amount}, retni-sip={slip.supplemental_tax_amount}, "
                   f"net={slip.net_amount}. Nòt: {payload.notes or '—'}")
    return slip


@router.get("/employee/{employee_id}/payslips", response_model=MyPayslipsResponse)
def employee_payslips(
    employee_id: int,
    user: CurrentUser,
    org_id: TenantId,
    db: DbSession,
    limit: Annotated[int, Query(ge=1, le=100)] = 24,
):
    emp = db.query(Employee).filter(
        Employee.id == employee_id,
        Employee.organization_id == org_id,
    ).first()
    if emp is None:
        raise HTTPException(status_code=404, detail="Anplwaye a pa jwenn.")

    ensure_can_view_employee(user, emp, db)

    slips = db.query(Payslip).filter(
        Payslip.organization_id == org_id,
        Payslip.employee_id == employee_id,
    ).order_by(Payslip.created_at.desc()).limit(limit).all()

    return MyPayslipsResponse(
        total=len(slips), items=[PayslipOut.model_validate(s) for s in slips]
    )


# ---------------------------------------------------------------------------
# TO DEDIKSYON YO
# ---------------------------------------------------------------------------

class TaxRatesInfo(BaseModel):
    ona_rate: float
    ofatma_rate: float
    cfgdct_rate: float
    cfgdct_monthly_floor: int
    fdu_cas_rate: float
    salary_abatement: float
    supplemental_tax_rate_today: float
    supplemental_tax_change_date: date
    tax_brackets: list[dict]
    overtime_multiplier: float
    note: str


@router.get("/tax-rates", response_model=TaxRatesInfo, dependencies=[Depends(require_hr)])
def tax_rates():
    """
    To yo sistèm lan sèvi pou kalkile peyòl la.
    Frontend lan ka montre sa nan yon paj 'Kijan nou kalkile fich peye w'.
    """
    return TaxRatesInfo(
        ona_rate=ONA_RATE,
        ofatma_rate=OFATMA_RATE,
        cfgdct_rate=CFGDCT_RATE,
        cfgdct_monthly_floor=CFGDCT_MONTHLY_FLOOR,
        fdu_cas_rate=FDU_CAS_RATE,
        salary_abatement=SALARY_ABATEMENT,
        supplemental_tax_rate_today=supplemental_tax_rate(date.today()),
        supplemental_tax_change_date=SUPPLEMENTAL_TAX_CHANGE_DATE,
        tax_brackets=[
            {"up_to": upper, "rate": rate} for upper, rate in TAX_BRACKETS
        ],
        overtime_multiplier=OVERTIME_MULTIPLIER,
        note=(
            "To sa yo baze sou piblikasyon DGI yo. Yon kontab dwe verifye yo "
            "anvan yon vrè biznis sèvi ak sistèm lan. Retni sou bonis ak èdtan "
            "siplemantè pase de 10% a 15% nan 1ye oktòb 2026."
        ),
    )