"""
Konbit — Enpòte anplwaye pa CSV
Chemen: backend/app/routers/employee_import.py

    POST /api/employee-import/preview   Tcheke fichye a, liy pa liy. PA EKRI ANYEN.
    POST /api/employee-import/commit    Kreye tout anplwaye yo — TOUT OSWA ANYEN.

HR / admin sèlman. Frontend lan li fichye a epi voye tèks la ({"csv_text": ...}).

FÒMA:
  - Separatè "," oswa ";" (Excel an franse) — nou devine l sou premye liy lan.
  - Premye liy lan = non kolòn yo, an kreyòl oswa an angle, ak oswa san aksan
    ("prenon" / "first_name", "dat_anbochaj" / "hire_date"...). Gade COLUMNS.
  - Dat: 2026-09-01 oswa 01/09/2026 (jou/mwa/ane).
  - Lajan an GOUD (oswa dola): "45000", "45 000,50", "45000.50". Nou konvèti an santim.
  - "manadje": nimewo yon anplwaye ki egziste deja, oswa ki nan menm fichye a.

ERÈ YO se KÒD (egz: "invalid_date"), pa tèks: frontend lan tradui yo nan lang
moun nan. Yon sèl erè nan yon sèl liy = anyen pa kreye (pa gen mwatye enpòtasyon).
"""

import csv
import io
import logging
import re
import unicodedata
from datetime import date, datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from ..deps import CurrentUser, DbSession, TenantId, require_hr
from ..models import (
    AuditLog, Currency, Employee, EmploymentStatus, EmploymentType, PaymentMethod, User, UserRole,
)
from ..security import generate_temp_password, hash_password

logger = logging.getLogger("konbit")

router = APIRouter()

MAX_ROWS = 500
MAX_LOGINS = 100          # bcrypt pran tan: 100 kont ≈ 30 segonn
MAX_TEXT = 1_500_000

# Non kolòn (san aksan, miniskil, "_" pou espas) -> chan anplwaye a
COLUMNS = {
    "prenon": "first_name", "first_name": "first_name", "firstname": "first_name",
    "non": "last_name", "last_name": "last_name", "lastname": "last_name", "siyati": "last_name",
    "dat_anbochaj": "hire_date", "hire_date": "hire_date", "dat_anbochman": "hire_date",
    "imel": "personal_email", "email": "personal_email", "personal_email": "personal_email",
    "telefon": "phone", "phone": "phone",
    "nimewo": "employee_number", "employee_number": "employee_number",
    "sale": "base_salary", "salary": "base_salary", "base_salary": "base_salary",
    "to_pa_le": "hourly_rate", "hourly_rate": "hourly_rate",
    "lajan": "currency", "currency": "currency",
    "metod_peman": "payment_method", "payment_method": "payment_method",
    "bank": "bank_name", "bank_name": "bank_name",
    "kont": "bank_account_number", "bank_account": "bank_account_number",
    "bank_account_number": "bank_account_number",
    "moncash": "mobile_money_number", "natcash": "mobile_money_number",
    "mobile_money": "mobile_money_number", "mobile_money_number": "mobile_money_number",
    "nif": "national_id", "cin": "national_id", "national_id": "national_id",
    "adres": "address", "address": "address",
    "vil": "city", "city": "city",
    "kalite": "employment_type", "employment_type": "employment_type",
    "manadje": "manager_number", "manager": "manager_number", "manager_number": "manager_number",
}
REQUIRED = ("first_name", "last_name", "hire_date")
LIMITS = {"first_name": 100, "last_name": 100, "personal_email": 255, "phone": 50,
          "employee_number": 50, "bank_name": 150, "bank_account_number": 80,
          "mobile_money_number": 50, "national_id": 60, "address": 500, "city": 100}

METHODS = {
    "check": "check", "chek": "check", "cheque": "check",
    "direct_deposit": "direct_deposit", "depo": "direct_deposit", "depo_direk": "direct_deposit",
    "bank": "direct_deposit", "virement": "direct_deposit",
    "cash": "cash", "kach": "cash", "especes": "cash",
    "moncash": "moncash", "natcash": "natcash",
}
TYPES = {
    "full_time": "full_time", "tan_plen": "full_time",
    "part_time": "part_time", "tan_pasyel": "part_time",
    "contract": "contract", "kontra": "contract",
    "intern": "intern", "estaj": "intern",
    "seasonal": "seasonal", "sezon": "seasonal",
}
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _free_numbers(db, org_id: int, reserved: set[str]):
    """
    KB-0001, KB-0002... ki pa pran NAN BAZ LA ni NAN FICHYE A. San sa, yon
    nimewo otomatik pou liy 2 ta ka tonbe sou yon nimewo liy 5 bay.
    """
    taken = {n for (n,) in db.query(Employee.employee_number).filter(
        Employee.organization_id == org_id).all()} | reserved
    n = len(taken) + 1 - len(reserved)
    while True:
        candidate = f"KB-{max(n, 1):04d}"
        if candidate not in taken:
            taken.add(candidate)
            yield candidate
        n += 1


# ---------------------------------------------------------------------------
# LEKTI AK NÒMALIZASYON
# ---------------------------------------------------------------------------

def _key(text: str) -> str:
    """"Dat anbochaj" -> "dat_anbochaj"; "Salè" -> "sale"."""
    text = unicodedata.normalize("NFKD", text.strip().lower())
    text = "".join(c for c in text if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+", "_", text).strip("_")


def _parse_date(value: str) -> Optional[date]:
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y"):
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            continue
    return None


def _parse_money(value: str) -> Optional[int]:
    """"45 000,50" / "45000.50" / "45,000.50" -> santim. None si pa valab."""
    s = value.replace("\u00a0", "").replace(" ", "")
    if "," in s and "." in s:
        s = s.replace(",", "") if s.rfind(".") > s.rfind(",") else s.replace(".", "").replace(",", ".")
    elif "," in s:
        s = s.replace(",", ".")
    if not re.fullmatch(r"\d+(\.\d{1,2})?", s):
        return None
    whole, _, frac = s.partition(".")
    return int(whole) * 100 + int((frac + "00")[:2])


class RowError(BaseModel):
    row: int                  # nimewo liy nan fichye a (1 = tèt kolòn yo)
    field: str
    code: str


class RowPreview(BaseModel):
    row: int
    first_name: str
    last_name: str
    employee_number: Optional[str] = None
    hire_date: Optional[date] = None
    personal_email: Optional[str] = None
    payment_method: str
    manager_number: Optional[str] = None


class ImportRequest(BaseModel):
    csv_text: str = Field(min_length=1, max_length=MAX_TEXT)
    create_logins: bool = False


class PreviewOut(BaseModel):
    delimiter: str
    columns: list[str]              # kolòn nou rekonèt
    ignored_columns: list[str]      # kolòn nou pa konnen (nou pa sèvi ak yo)
    rows: list[RowPreview]
    errors: list[RowError]


def _analyze(db, org_id: int, text: str, create_logins: bool):
    """Retounen (PreviewOut, lis diksyonè pare pou kreye)."""
    text = text.lstrip("\ufeff")
    lines = text.splitlines()
    first_line = lines[0] if lines else ""
    # "sep=;" (premye liy modèl nou an): Excel li l nan nenpòt lang.
    if first_line.strip().lower().startswith("sep=") and len(first_line.strip()) == 5:
        delimiter = first_line.strip()[4]
        text = "\n".join(lines[1:])
    else:
        delimiter = ";" if first_line.count(";") > first_line.count(",") else ","
    reader = csv.reader(io.StringIO(text), delimiter=delimiter)
    try:
        table = [r for r in reader]
    except csv.Error:
        table = []
    table = [r for r in table if any(cell.strip() for cell in r)]

    errors: list[RowError] = []
    if not table:
        return PreviewOut(delimiter=delimiter, columns=[], ignored_columns=[], rows=[],
                          errors=[RowError(row=1, field="file", code="empty")]), []

    header = [_key(h) for h in table[0]]
    mapping = {i: COLUMNS[h] for i, h in enumerate(header) if h in COLUMNS}
    ignored = [table[0][i].strip() for i, h in enumerate(header) if h and h not in COLUMNS]
    for field in REQUIRED:
        if field not in mapping.values():
            errors.append(RowError(row=1, field=field, code="missing_column"))
    body = table[1:]
    if not body:
        errors.append(RowError(row=1, field="file", code="empty"))
    if len(body) > MAX_ROWS:
        errors.append(RowError(row=1, field="file", code="too_many_rows"))
    if create_logins and len(body) > MAX_LOGINS:
        errors.append(RowError(row=1, field="file", code="too_many_logins"))
    if errors:
        return PreviewOut(delimiter=delimiter, columns=sorted(set(mapping.values())),
                          ignored_columns=ignored, rows=[], errors=errors), []

    existing_numbers = {n for (n,) in db.query(Employee.employee_number).filter(
        Employee.organization_id == org_id).all()}
    file_numbers = set()
    file_emails = set()
    rows, ready = [], []

    for index, cells in enumerate(body, start=2):
        raw = {field: (cells[i].strip() if i < len(cells) else "") for i, field in mapping.items()}
        err = lambda field, code: errors.append(RowError(row=index, field=field, code=code))  # noqa: E731
        data: dict = {}

        for field in REQUIRED:
            if not raw.get(field):
                err(field, "required")
        for field, limit in LIMITS.items():
            if len(raw.get(field, "")) > limit:
                err(field, "too_long")

        hire = _parse_date(raw["hire_date"]) if raw.get("hire_date") else None
        if raw.get("hire_date") and hire is None:
            err("hire_date", "invalid_date")

        email = raw.get("personal_email", "").lower() or None
        if email and not EMAIL_RE.match(email):
            err("personal_email", "invalid_email")
        if create_logins:
            if not email:
                err("personal_email", "required_for_login")
            elif email in file_emails or db.query(User.id).filter(User.email == email).first():
                err("personal_email", "duplicate_email")
        if email:
            file_emails.add(email)

        number = raw.get("employee_number") or None
        if number:
            if number in existing_numbers or number in file_numbers:
                err("employee_number", "duplicate_number")
            file_numbers.add(number)

        for money_field in ("base_salary", "hourly_rate"):
            if raw.get(money_field):
                cents = _parse_money(raw[money_field])
                if cents is None:
                    err(money_field, "invalid_number")
                data[money_field] = cents

        currency = (raw.get("currency") or "HTG").upper()
        if currency not in ("HTG", "USD"):
            err("currency", "invalid_currency")

        method = METHODS.get(_key(raw.get("payment_method") or "check"))
        if method is None:
            err("payment_method", "invalid_method")
            method = "check"
        if method == "direct_deposit" and not (raw.get("bank_name") and raw.get("bank_account_number")):
            err("bank_account_number", "missing_account")
        if method in ("moncash", "natcash") and not raw.get("mobile_money_number"):
            err("mobile_money_number", "missing_account")

        emp_type = TYPES.get(_key(raw.get("employment_type") or "full_time"))
        if emp_type is None:
            err("employment_type", "invalid_type")
            emp_type = "full_time"

        rows.append(RowPreview(
            row=index, first_name=raw.get("first_name", ""), last_name=raw.get("last_name", ""),
            employee_number=number, hire_date=hire, personal_email=email,
            payment_method=method, manager_number=raw.get("manager_number") or None,
        ))
        data.update(
            first_name=raw.get("first_name", ""), last_name=raw.get("last_name", ""),
            hire_date=hire, personal_email=email, employee_number=number,
            currency=currency, payment_method=method, employment_type=emp_type,
            manager_number=raw.get("manager_number") or None, _row=index,
            **{f: raw.get(f) or None for f in ("phone", "bank_name", "bank_account_number",
                                               "mobile_money_number", "national_id", "address", "city")},
        )
        ready.append(data)

    # Manadjè: yon anplwaye ki la deja, oswa yon nimewo nan menm fichye a.
    for data in ready:
        manager = data["manager_number"]
        if manager and manager not in existing_numbers and manager not in file_numbers:
            errors.append(RowError(row=data["_row"], field="manager_number", code="unknown_manager"))
        if manager and manager == data["employee_number"]:
            errors.append(RowError(row=data["_row"], field="manager_number", code="self_manager"))

    return PreviewOut(delimiter=delimiter, columns=sorted(set(mapping.values())),
                      ignored_columns=ignored, rows=rows, errors=errors), ready


# ---------------------------------------------------------------------------
# ENDPOINT YO
# ---------------------------------------------------------------------------

@router.post("/preview", response_model=PreviewOut, dependencies=[Depends(require_hr)])
def preview(payload: ImportRequest, org_id: TenantId, db: DbSession):
    result, _ = _analyze(db, org_id, payload.csv_text, payload.create_logins)
    return result


class CreatedLogin(BaseModel):
    employee_number: str
    name: str
    login_email: str
    temporary_password: str


class CommitOut(BaseModel):
    created: int
    logins: list[CreatedLogin]        # modpas tanporè yo parèt YON SÈL FWA
    errors: list[RowError] = []


@router.post("/commit", response_model=CommitOut, dependencies=[Depends(require_hr)])
def commit(payload: ImportRequest, user: CurrentUser, org_id: TenantId,
           request: Request, db: DbSession):
    result, ready = _analyze(db, org_id, payload.csv_text, payload.create_logins)
    if result.errors:
        # Anyen pa kreye. Frontend lan montre erè yo (menm jan ak apèsi a).
        return CommitOut(created=0, logins=[], errors=result.errors)

    logins: list[CreatedLogin] = []
    by_number: dict[str, Employee] = {}
    auto_numbers = _free_numbers(db, org_id, {d["employee_number"] for d in ready if d["employee_number"]})
    try:
        created: list[tuple[Employee, dict]] = []
        for data in ready:
            number = data["employee_number"] or next(auto_numbers)
            new_user = None
            if payload.create_logins:
                temp = generate_temp_password()
                new_user = User(
                    organization_id=org_id, email=data["personal_email"],
                    hashed_password=hash_password(temp), must_change_password=True,
                    full_name=f"{data['first_name']} {data['last_name']}",
                    role=UserRole.EMPLOYEE, is_active=True, email_verified=False,
                )
                db.add(new_user)
                db.flush()
                logins.append(CreatedLogin(
                    employee_number=number, name=new_user.full_name,
                    login_email=new_user.email, temporary_password=temp))

            emp = Employee(
                organization_id=org_id, employee_number=number,
                user_id=new_user.id if new_user else None,
                first_name=data["first_name"], last_name=data["last_name"],
                hire_date=data["hire_date"], personal_email=data["personal_email"],
                phone=data["phone"], national_id=data["national_id"],
                address=data["address"], city=data["city"],
                base_salary=data.get("base_salary"), hourly_rate=data.get("hourly_rate"),
                currency=Currency(data["currency"]),
                preferred_payment_method=PaymentMethod(data["payment_method"]),
                bank_name=data["bank_name"], bank_account_number=data["bank_account_number"],
                mobile_money_number=data["mobile_money_number"],
                employment_type=EmploymentType(data["employment_type"]),
                status=EmploymentStatus.ACTIVE, is_active=True,
            )
            db.add(emp)
            db.flush()
            by_number[number] = emp
            created.append((emp, data))

        for emp, data in created:
            manager = data["manager_number"]
            if not manager:
                continue
            target = by_number.get(manager) or db.query(Employee).filter(
                Employee.organization_id == org_id, Employee.employee_number == manager).first()
            emp.manager_id = target.id if target else None

        db.add(AuditLog(
            organization_id=org_id, user_id=user.id, action="import", entity_type="employee",
            changes=f"{len(created)} anplwaye enpòte pa CSV ({len(logins)} kont koneksyon).",
            ip_address=request.client.host if request.client else None,
            user_agent=(request.headers.get("user-agent") or "")[:255],
        ))
        db.commit()
    except Exception:
        db.rollback()
        logger.exception("Enpòtasyon anplwaye echwe")
        raise HTTPException(status_code=500, detail="Yon erè entèn rive.")

    return CommitOut(created=len(created), logins=logins)