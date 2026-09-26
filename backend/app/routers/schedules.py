"""
Konbit — Router Orè travay pa semèn
Chemen: backend/app/routers/schedules.py

Endpoint yo:
    GET    /api/schedules/templates          Modèl orè yo ("Maten", "Lannwit"…)
    POST   /api/schedules/templates          Kreye yon modèl (HR)
    PATCH  /api/schedules/templates/{id}     Modifye / dezaktive yon modèl (HR)
    GET    /api/schedules/week               Grid semèn nan (HR: tout moun; manadjè: ekip li)
    PUT    /api/schedules/shifts             Mete orè yon moun pou yon jou (kreye oswa ranplase)
    DELETE /api/schedules/shifts/{id}        Retire yon orè
    POST   /api/schedules/week/copy          Kopye semèn anvan an (rotasyon)
    POST   /api/schedules/week/publish       Pibliye semèn nan: anplwaye yo ka wè l
    GET    /api/schedules/me                 Pwòp orè mwen (sèlman sa ki pibliye)

REG YO:
  - HR ak admin planifye tout moun. Yon manadjè planifye sèlman moun ki anba l
    (pa tèt li — menm prensip ak apwobasyon konje ak èdtan).
  - Lè yo LOKAL biznis la. Si lè fen <= lè kòmansman, orè a fini nan demen.
  - Yon orè: 16 èdtan maksimòm. Semèn: nou MAKE moun ki depase 48 èdtan, men
    nou pa bloke — règ legal egzak la ap tann konfimasyon avoka a.
  - Yon semèn kòmanse lendi.
"""

from datetime import date, time, timedelta
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import or_
from sqlalchemy.orm import Session

from ..deps import CurrentEmployee, CurrentUser, DbSession, TenantId, require_hr
from ..models import Employee, Shift, ShiftTemplate, User, UserRole
from ..timezone_utils import get_local_today
from .employees import _collect_subordinate_ids

router = APIRouter()

HR_ROLES = {UserRole.SUPER_ADMIN, UserRole.ORG_ADMIN, UserRole.HR}
SCHEDULER_ROLES = HR_ROLES | {UserRole.MANAGER}

MAX_SHIFT_MINUTES = 16 * 60
WEEKLY_WARNING_MINUTES = 48 * 60


# ---------------------------------------------------------------------------
# KALKIL
# ---------------------------------------------------------------------------

def _span_minutes(start: time, end: time) -> int:
    """Minit ant de lè. Si fen <= kòmansman, orè a travèse minwi."""
    s = start.hour * 60 + start.minute
    e = end.hour * 60 + end.minute
    if e <= s:
        e += 24 * 60
    return e - s


def shift_minutes(start: time, end: time, break_minutes: int) -> int:
    """Minit travay nan yon orè, san poz la."""
    return max(0, _span_minutes(start, end) - (break_minutes or 0))


def _check_times(start: time, end: time, break_minutes: int) -> None:
    span = _span_minutes(start, end)
    if span > MAX_SHIFT_MINUTES:
        raise HTTPException(status_code=400, detail="Yon orè pa ka depase 16 èdtan.")
    if (break_minutes or 0) >= span:
        raise HTTPException(status_code=400, detail="Poz la pa ka pi long pase orè a.")


def week_start(day: date) -> date:
    """Lendi semèn nan."""
    return day - timedelta(days=day.weekday())


# ---------------------------------------------------------------------------
# DWA
# ---------------------------------------------------------------------------

def _require_scheduler(user: User) -> None:
    if user.role not in SCHEDULER_ROLES:
        raise HTTPException(status_code=403, detail="Ou pa gen dwa pou aksyon sa a.")


def _scope_ids(db: Session, user: User, org_id: int) -> Optional[set[int]]:
    """None = tout biznis la (HR/admin). Sinon: moun manadjè a ka planifye."""
    _require_scheduler(user)
    if user.role in HR_ROLES:
        return None
    viewer = db.query(Employee).filter(
        Employee.user_id == user.id,
        Employee.organization_id == org_id,
    ).first()
    if viewer is None:
        raise HTTPException(status_code=403, detail="Kont ou a pa lye ak yon dosye anplwaye.")
    return _collect_subordinate_ids(db, org_id, viewer.id)


def _employee_in_scope(db: Session, user: User, org_id: int, employee_id: int) -> Employee:
    emp = db.query(Employee).filter(
        Employee.id == employee_id,
        Employee.organization_id == org_id,
        Employee.is_active.is_(True),
    ).first()
    if emp is None:
        raise HTTPException(status_code=404, detail="Anplwaye a pa jwenn.")
    scope = _scope_ids(db, user, org_id)
    if scope is not None and emp.id not in scope:
        raise HTTPException(status_code=403, detail="Ou pa ka planifye orè moun sa a.")
    return emp


def _in_scope(query, scope: Optional[set[int]]):
    return query if scope is None else query.filter(Shift.employee_id.in_(scope or {-1}))


# ---------------------------------------------------------------------------
# MODÈL ORÈ
# ---------------------------------------------------------------------------

class TemplateIn(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    start_time: time
    end_time: time
    break_minutes: int = Field(default=0, ge=0, le=240)


class TemplateUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=80)
    start_time: Optional[time] = None
    end_time: Optional[time] = None
    break_minutes: Optional[int] = Field(default=None, ge=0, le=240)
    is_active: Optional[bool] = None


class TemplateOut(BaseModel):
    id: int
    name: str
    start_time: time
    end_time: time
    break_minutes: int
    minutes: int
    overnight: bool
    is_active: bool


def _template_out(tpl: ShiftTemplate) -> TemplateOut:
    return TemplateOut(
        id=tpl.id, name=tpl.name, start_time=tpl.start_time, end_time=tpl.end_time,
        break_minutes=tpl.break_minutes or 0,
        minutes=shift_minutes(tpl.start_time, tpl.end_time, tpl.break_minutes),
        overnight=tpl.end_time <= tpl.start_time,
        is_active=tpl.is_active,
    )


def _get_template(db: Session, org_id: int, template_id: int) -> ShiftTemplate:
    tpl = db.query(ShiftTemplate).filter(
        ShiftTemplate.id == template_id,
        ShiftTemplate.organization_id == org_id,
    ).first()
    if tpl is None:
        raise HTTPException(status_code=404, detail="Modèl orè a pa jwenn.")
    return tpl


@router.get("/templates", response_model=list[TemplateOut])
def list_templates(user: CurrentUser, org_id: TenantId, db: DbSession, include_inactive: bool = False):
    _require_scheduler(user)
    q = db.query(ShiftTemplate).filter(ShiftTemplate.organization_id == org_id)
    if not include_inactive:
        q = q.filter(ShiftTemplate.is_active.is_(True))
    return [_template_out(t) for t in q.order_by(ShiftTemplate.start_time, ShiftTemplate.name).all()]


@router.post("/templates", response_model=TemplateOut, status_code=status.HTTP_201_CREATED,
             dependencies=[Depends(require_hr)])
def create_template(payload: TemplateIn, org_id: TenantId, db: DbSession):
    _check_times(payload.start_time, payload.end_time, payload.break_minutes)
    tpl = ShiftTemplate(organization_id=org_id, name=payload.name.strip(),
                        start_time=payload.start_time, end_time=payload.end_time,
                        break_minutes=payload.break_minutes, is_active=True)
    db.add(tpl)
    db.commit()
    db.refresh(tpl)
    return _template_out(tpl)


@router.patch("/templates/{template_id}", response_model=TemplateOut, dependencies=[Depends(require_hr)])
def update_template(template_id: int, payload: TemplateUpdate, org_id: TenantId, db: DbSession):
    tpl = _get_template(db, org_id, template_id)
    for field, value in payload.model_dump(exclude_unset=True).items():
        if value is None:
            continue
        setattr(tpl, field, value.strip() if field == "name" else value)
    _check_times(tpl.start_time, tpl.end_time, tpl.break_minutes)
    db.commit()
    db.refresh(tpl)
    # Orè ki deja planifye yo pa chanje: se yon kopi lè yo nan moman an.
    return _template_out(tpl)


# ---------------------------------------------------------------------------
# ORÈ
# ---------------------------------------------------------------------------

class ShiftUpsert(BaseModel):
    employee_id: int
    work_date: date
    template_id: Optional[int] = None
    start_time: Optional[time] = None
    end_time: Optional[time] = None
    break_minutes: Optional[int] = Field(default=None, ge=0, le=240)
    note: Optional[str] = Field(default=None, max_length=300)


class ShiftOut(BaseModel):
    id: int
    employee_id: int
    template_id: Optional[int]
    template_name: Optional[str] = None
    work_date: date
    start_time: time
    end_time: time
    break_minutes: int
    minutes: int
    overnight: bool
    note: Optional[str]
    is_published: bool


def _shift_out(shift: Shift, names: Optional[dict[int, str]] = None) -> ShiftOut:
    return ShiftOut(
        id=shift.id, employee_id=shift.employee_id, template_id=shift.template_id,
        template_name=(names or {}).get(shift.template_id) if shift.template_id else None,
        work_date=shift.work_date, start_time=shift.start_time, end_time=shift.end_time,
        break_minutes=shift.break_minutes or 0,
        minutes=shift_minutes(shift.start_time, shift.end_time, shift.break_minutes),
        overnight=shift.end_time <= shift.start_time,
        note=shift.note, is_published=shift.is_published,
    )


def _template_names(db: Session, org_id: int) -> dict[int, str]:
    rows = db.query(ShiftTemplate.id, ShiftTemplate.name).filter(
        ShiftTemplate.organization_id == org_id).all()
    return {r[0]: r[1] for r in rows}


@router.put("/shifts", response_model=ShiftOut)
def upsert_shift(payload: ShiftUpsert, user: CurrentUser, org_id: TenantId, db: DbSession):
    """Kreye orè yon moun pou yon jou, oswa ranplase sa ki te la."""
    emp = _employee_in_scope(db, user, org_id, payload.employee_id)

    if payload.template_id is not None:
        tpl = _get_template(db, org_id, payload.template_id)
        start, end, brk = tpl.start_time, tpl.end_time, tpl.break_minutes or 0
    elif payload.start_time is not None and payload.end_time is not None:
        start, end, brk = payload.start_time, payload.end_time, payload.break_minutes or 0
    else:
        raise HTTPException(status_code=400,
                            detail="Chwazi yon modèl oswa bay lè kòmansman ak lè fen.")
    _check_times(start, end, brk)

    shift = db.query(Shift).filter(
        Shift.organization_id == org_id,
        Shift.employee_id == emp.id,
        Shift.work_date == payload.work_date,
    ).first()
    if shift is None:
        shift = Shift(organization_id=org_id, employee_id=emp.id, work_date=payload.work_date,
                      is_published=False, created_by_id=user.id)
        db.add(shift)
    # Yon orè ki deja pibliye rete pibliye: anplwaye a wè chanjman an touswit.
    shift.template_id = payload.template_id
    shift.start_time, shift.end_time, shift.break_minutes = start, end, brk
    shift.note = (payload.note or "").strip() or None
    db.commit()
    db.refresh(shift)
    return _shift_out(shift, _template_names(db, org_id))


@router.delete("/shifts/{shift_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_shift(shift_id: int, user: CurrentUser, org_id: TenantId, db: DbSession):
    shift = db.query(Shift).filter(Shift.id == shift_id, Shift.organization_id == org_id).first()
    if shift is None:
        raise HTTPException(status_code=404, detail="Orè a pa jwenn.")
    _employee_in_scope(db, user, org_id, shift.employee_id)
    db.delete(shift)
    db.commit()


# ---------------------------------------------------------------------------
# SEMÈN NAN
# ---------------------------------------------------------------------------

class WeekRow(BaseModel):
    employee_id: int
    employee_name: str
    employee_number: str
    minutes_total: int
    over_weekly_limit: bool
    shifts: list[ShiftOut]


class WeekView(BaseModel):
    week_start: date
    week_end: date
    total: int
    page: int
    size: int
    unpublished: int
    weekly_warning_minutes: int
    rows: list[WeekRow]


@router.get("/week", response_model=WeekView)
def week_view(
    user: CurrentUser,
    org_id: TenantId,
    db: DbSession,
    start: Optional[date] = None,
    q: Annotated[Optional[str], Query(max_length=100)] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    size: Annotated[int, Query(ge=1, le=50)] = 25,
):
    """Grid la: anplwaye yo (paj pa paj, ak rechèch) ak orè yo pou 7 jou yo."""
    scope = _scope_ids(db, user, org_id)
    # Semèn pa defo: semèn JODI A an lè biznis la (pa lè sèvè a).
    monday = week_start(start or get_local_today(db, org_id))
    sunday = monday + timedelta(days=6)

    emp_q = db.query(Employee).filter(
        Employee.organization_id == org_id,
        Employee.is_active.is_(True),
    )
    if scope is not None:
        emp_q = emp_q.filter(Employee.id.in_(scope or {-1}))
    if q and q.strip():
        pattern = f"%{q.strip()}%"
        emp_q = emp_q.filter(or_(
            Employee.first_name.ilike(pattern),
            Employee.last_name.ilike(pattern),
            Employee.employee_number.ilike(pattern),
        ))
    total = emp_q.count()
    employees = (emp_q.order_by(Employee.last_name, Employee.first_name)
                 .offset((page - 1) * size).limit(size).all())

    ids = [e.id for e in employees]
    shifts = db.query(Shift).filter(
        Shift.organization_id == org_id,
        Shift.employee_id.in_(ids or [-1]),
        Shift.work_date >= monday,
        Shift.work_date <= sunday,
    ).order_by(Shift.work_date).all()

    names = _template_names(db, org_id)
    by_emp: dict[int, list[ShiftOut]] = {}
    for s in shifts:
        by_emp.setdefault(s.employee_id, []).append(_shift_out(s, names))

    rows = []
    for e in employees:
        items = by_emp.get(e.id, [])
        total_minutes = sum(s.minutes for s in items)
        rows.append(WeekRow(
            employee_id=e.id, employee_name=f"{e.first_name} {e.last_name}",
            employee_number=e.employee_number, minutes_total=total_minutes,
            over_weekly_limit=total_minutes > WEEKLY_WARNING_MINUTES, shifts=items,
        ))

    unpublished = _in_scope(db.query(Shift).filter(
        Shift.organization_id == org_id,
        Shift.work_date >= monday,
        Shift.work_date <= sunday,
        Shift.is_published.is_(False),
    ), scope).count()

    return WeekView(week_start=monday, week_end=sunday, total=total, page=page, size=size,
                    unpublished=unpublished, weekly_warning_minutes=WEEKLY_WARNING_MINUTES,
                    rows=rows)


class WeekAction(BaseModel):
    week_start: date


class PublishResult(BaseModel):
    published: int


class CopyResult(BaseModel):
    created: int
    skipped: int


@router.post("/week/publish", response_model=PublishResult)
def publish_week(payload: WeekAction, user: CurrentUser, org_id: TenantId, db: DbSession):
    """Anplwaye yo wè orè yo sèlman apre sa."""
    scope = _scope_ids(db, user, org_id)
    monday = week_start(payload.week_start)
    shifts = _in_scope(db.query(Shift).filter(
        Shift.organization_id == org_id,
        Shift.work_date >= monday,
        Shift.work_date <= monday + timedelta(days=6),
        Shift.is_published.is_(False),
    ), scope).all()
    for s in shifts:
        s.is_published = True
    db.commit()
    return PublishResult(published=len(shifts))


@router.post("/week/copy", response_model=CopyResult)
def copy_previous_week(payload: WeekAction, user: CurrentUser, org_id: TenantId, db: DbSession):
    """
    Kopye orè semèn anvan an nan semèn sa a (rotasyon). Jou ki deja gen yon
    orè pa chanje. Kopi yo pa pibliye: manadjè a verifye yo anvan.
    """
    scope = _scope_ids(db, user, org_id)
    monday = week_start(payload.week_start)
    source = _in_scope(db.query(Shift).join(Employee, Employee.id == Shift.employee_id).filter(
        Shift.organization_id == org_id,
        Shift.work_date >= monday - timedelta(days=7),
        Shift.work_date <= monday - timedelta(days=1),
        Employee.is_active.is_(True),
    ), scope).all()

    existing = {
        (r[0], r[1]) for r in db.query(Shift.employee_id, Shift.work_date).filter(
            Shift.organization_id == org_id,
            Shift.work_date >= monday,
            Shift.work_date <= monday + timedelta(days=6),
        ).all()
    }

    created = skipped = 0
    for s in source:
        target = s.work_date + timedelta(days=7)
        if (s.employee_id, target) in existing:
            skipped += 1
            continue
        db.add(Shift(
            organization_id=org_id, employee_id=s.employee_id, template_id=s.template_id,
            work_date=target, start_time=s.start_time, end_time=s.end_time,
            break_minutes=s.break_minutes, note=s.note, is_published=False,
            created_by_id=user.id,
        ))
        created += 1
    db.commit()
    return CopyResult(created=created, skipped=skipped)


# ---------------------------------------------------------------------------
# PWÒP ORÈ MWEN
# ---------------------------------------------------------------------------

class MyWeek(BaseModel):
    week_start: date
    week_end: date
    minutes_total: int
    shifts: list[ShiftOut]


@router.get("/me", response_model=MyWeek)
def my_week(emp: CurrentEmployee, org_id: TenantId, db: DbSession, start: Optional[date] = None):
    """Orè anplwaye a pou yon semèn — sèlman sa manadjè a pibliye."""
    monday = week_start(start or get_local_today(db, org_id))
    sunday = monday + timedelta(days=6)
    shifts = db.query(Shift).filter(
        Shift.organization_id == org_id,
        Shift.employee_id == emp.id,
        Shift.work_date >= monday,
        Shift.work_date <= sunday,
        Shift.is_published.is_(True),
    ).order_by(Shift.work_date).all()
    names = _template_names(db, org_id)
    items = [_shift_out(s, names) for s in shifts]
    return MyWeek(week_start=monday, week_end=sunday,
                  minutes_total=sum(s.minutes for s in items), shifts=items)