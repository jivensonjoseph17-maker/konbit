"""
Konbit — Router Pòtay anplwaye
Chemen: backend/app/routers/portal.py

    GET /api/portal/hours     Èdtan mwen: jodi a, semèn sa a, peryòd pewòl la
    GET /api/portal/ytd       Total ane a sou fich PEYE mwen yo (brit, retni, net)

RÈG: se done moun ki konekte a SÈLMAN. Pa gen okenn paramèt employee_id —
yon anplwaye pa ka mande done yon lòt moun, menm si li devine yon ID.

"Jodi a" = jodi a nan lè biznis la (get_local_today), JAMAN date.today().
"""

from datetime import date, datetime, timedelta, timezone
from typing import Annotated, Optional

from fastapi import APIRouter, Query
from pydantic import BaseModel

from ..deps import CurrentEmployee, DbSession, TenantId
from ..models import AttendanceStatus, PayPeriod, Payslip, PayrollStatus, TimeEntry
from ..timezone_utils import get_local_today, get_org_timezone
from .attendance import MAX_SHIFT_MINUTES

router = APIRouter()


def _as_aware(dt: Optional[datetime]) -> Optional[datetime]:
    """SQLite retounen datetime san fizo orè: nou konsidere yo UTC."""
    if dt is None:
        return None
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=timezone.utc)


def _month_bounds(day: date) -> tuple[date, date]:
    start = day.replace(day=1)
    next_month = (start + timedelta(days=32)).replace(day=1)
    return start, next_month - timedelta(days=1)


# ---------------------------------------------------------------------------
# ÈDTAN MWEN
# ---------------------------------------------------------------------------

class HoursBucket(BaseModel):
    start_date: date
    end_date: date
    worked_minutes: int = 0
    overtime_minutes: int = 0
    days_worked: int = 0


class PeriodInfo(BaseModel):
    """pay_period_id None = biznis la pa gen peryòd pewòl pou jodi a: nou pran mwa a."""
    pay_period_id: Optional[int] = None
    name: Optional[str] = None
    pay_date: Optional[date] = None


class MyHours(BaseModel):
    today: date
    clocked_in: bool
    open_since: Optional[datetime] = None
    day: HoursBucket
    week: HoursBucket
    period: HoursBucket
    period_info: PeriodInfo
    needs_correction: int           # jounen san klòk out nan peryòd la (HR dwe korije)


@router.get("/hours", response_model=MyHours)
def my_hours(emp: CurrentEmployee, org_id: TenantId, db: DbSession):
    """
    Frontend lan rele sa a lè paj la louvri ak touswit apre klòk out.

    Yon jounen ki toujou louvri konte an dirèk (kounye a − lè antre), san
    poz la: poz la konnen sèlman lè moun nan fè klòk out. Si jounen louvri
    a depase MAX_SHIFT_MINUTES (moun nan bliye klòk out), nou pa konte l —
    pou pa montre yon total fo.
    """
    today = get_local_today(db, org_id)
    now = datetime.now(timezone.utc)

    week_start = today - timedelta(days=today.weekday())      # lendi
    week_end = week_start + timedelta(days=6)

    pay_period = db.query(PayPeriod).filter(
        PayPeriod.organization_id == org_id,
        PayPeriod.start_date <= today,
        PayPeriod.end_date >= today,
    ).order_by(PayPeriod.start_date.desc()).first()

    if pay_period is not None:
        p_start, p_end = pay_period.start_date, pay_period.end_date
        info = PeriodInfo(pay_period_id=pay_period.id, name=pay_period.name,
                          pay_date=pay_period.pay_date)
    else:
        p_start, p_end = _month_bounds(today)
        info = PeriodInfo()

    entries = db.query(TimeEntry).filter(
        TimeEntry.organization_id == org_id,
        TimeEntry.employee_id == emp.id,
        TimeEntry.work_date >= min(week_start, p_start),
        TimeEntry.work_date <= max(week_end, p_end),
    ).all()

    buckets = [
        HoursBucket(start_date=today, end_date=today),
        HoursBucket(start_date=week_start, end_date=week_end),
        HoursBucket(start_date=p_start, end_date=p_end),
    ]
    days_seen: list[set[date]] = [set(), set(), set()]

    open_since: Optional[datetime] = None
    needs_correction = 0

    for e in entries:
        if e.status == AttendanceStatus.MISSING_OUT:
            if p_start <= e.work_date <= p_end:
                needs_correction += 1
            continue

        if e.status == AttendanceStatus.OPEN:
            since = _as_aware(e.clock_in_at)
            open_since = since
            worked = max(0, int((now - since).total_seconds() // 60))
            if worked > MAX_SHIFT_MINUTES:
                worked = 0
                if p_start <= e.work_date <= p_end:
                    needs_correction += 1
            overtime = 0                    # kalkile lè klòk out fèt
        else:
            worked = e.worked_minutes or 0
            overtime = e.overtime_minutes or 0

        for bucket, seen in zip(buckets, days_seen):
            if bucket.start_date <= e.work_date <= bucket.end_date:
                bucket.worked_minutes += worked
                bucket.overtime_minutes += overtime
                seen.add(e.work_date)

    for bucket, seen in zip(buckets, days_seen):
        bucket.days_worked = len(seen)

    day, week, period = buckets
    return MyHours(
        today=today,
        clocked_in=open_since is not None,
        open_since=open_since,
        day=day,
        week=week,
        period=period,
        period_info=info,
        needs_correction=needs_correction,
    )


# ---------------------------------------------------------------------------
# TOTAL ANE A (YTD)
# ---------------------------------------------------------------------------

_DEDUCTION_FIELDS = (
    "tax_amount",
    "supplemental_tax_amount",
    "ona_amount",
    "ofatma_amount",
    "cfgdct_amount",
    "fdu_cas_amount",
    "other_deductions",
)
_SUM_FIELDS = ("gross_amount", *_DEDUCTION_FIELDS, "net_amount")


class YtdTotals(BaseModel):
    """Montan yo an santim."""
    currency: str
    payslip_count: int = 0
    gross_amount: int = 0
    tax_amount: int = 0
    supplemental_tax_amount: int = 0
    ona_amount: int = 0
    ofatma_amount: int = 0
    cfgdct_amount: int = 0
    fdu_cas_amount: int = 0
    other_deductions: int = 0
    total_deductions: int = 0
    net_amount: int = 0


class MyYtd(BaseModel):
    year: int
    totals: list[YtdTotals]         # youn pa lajan (HTG/USD); nòmalman youn sèlman
    years: list[int]                # ane ki gen fich peye, pou chwazi nan meni an


@router.get("/ytd", response_model=MyYtd)
def my_ytd(
    emp: CurrentEmployee,
    org_id: TenantId,
    db: DbSession,
    year: Annotated[Optional[int], Query(ge=2000, le=2100)] = None,
):
    """
    Sèlman fich PEYE yo konte (pa bouyon, pa apwouve-poko-peye).
    Ane a se ane jou peman an REYÈLMAN fèt, an lè lokal biznis la —
    se sa ki konte pou DGI. Si paid_at manke, nou pran dat peman peryòd la.
    """
    tz = get_org_timezone(db, org_id)
    year = year or get_local_today(db, org_id).year

    rows = (
        db.query(Payslip, PayPeriod)
        .join(PayPeriod, Payslip.pay_period_id == PayPeriod.id)
        .filter(
            Payslip.organization_id == org_id,
            Payslip.employee_id == emp.id,
            Payslip.status == PayrollStatus.PAID,
        )
        .all()
    )

    by_currency: dict[str, YtdTotals] = {}
    years: set[int] = set()

    for slip, period in rows:
        paid = _as_aware(slip.paid_at)
        slip_year = paid.astimezone(tz).year if paid else period.pay_date.year
        years.add(slip_year)
        if slip_year != year:
            continue

        currency = getattr(slip.currency, "value", slip.currency)
        totals = by_currency.setdefault(currency, YtdTotals(currency=currency))
        totals.payslip_count += 1
        for field in _SUM_FIELDS:
            setattr(totals, field, getattr(totals, field) + (getattr(slip, field) or 0))

    for totals in by_currency.values():
        totals.total_deductions = sum(getattr(totals, f) for f in _DEDUCTION_FIELDS)

    return MyYtd(
        year=year,
        totals=sorted(by_currency.values(), key=lambda t: t.currency),
        years=sorted(years, reverse=True),
    )