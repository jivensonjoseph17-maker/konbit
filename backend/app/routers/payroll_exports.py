"""
Konbit — Rapò pewòl ak fichye bank (CSV)
Chemen: backend/app/routers/payroll_exports.py

    GET /api/payroll/periods/{id}/export/bank     Fichye bank / MonCash / NatCash (net pou chak moun)
    GET /api/payroll/periods/{id}/export/ona      ONA — brit ak retni 6% (pati anplwaye a)
    GET /api/payroll/periods/{id}/export/ofatma   OFATMA — brit ak retni 3%
    GET /api/payroll/periods/{id}/export/dgi      DGI — IRI, retni sou bonis, CFGDCT, FDU/CAS

RÈG:
  - HR / admin sèlman, epi sèlman pou yon pewòl APWOUVE oswa PEYE
    (yon bouyon ka chanje ankò — yon rapò sou li ta fo).
  - Fichye bank lan gen NIMEWO KONT KONPLÈ yo: chak telechajman ale nan
    jounal odit la (kiyès, kilè, ki peryòd).
  - CSV UTF-8 ak BOM (Excel louvri aksan yo byen), vigil kòm separatè,
    montan an goud ak 2 desimal ("45000.00"), yon liy TOTAL anba.

ATANSYON: fòma ofisyèl ONA / OFATMA / DGI yo ka mande lòt kolòn.
Yon kontab dwe verifye rapò yo anvan yo soumèt.
"""

import csv
import io
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request, Response

from ..deps import CurrentUser, DbSession, TenantId, require_hr
from ..models import (
    AuditLog, Employee, Organization, PaymentMethod, PayPeriod, PayrollStatus, Payslip,
)

router = APIRouter()

ExportKind = Literal["bank", "ona", "ofatma", "dgi"]


def _money(cents) -> str:
    return f"{(cents or 0) / 100:.2f}"


def _rows(db, org_id: int, period_id: int):
    return (
        db.query(Payslip, Employee)
        .join(Employee, Payslip.employee_id == Employee.id)
        .filter(Payslip.organization_id == org_id, Payslip.pay_period_id == period_id)
        .order_by(Employee.last_name, Employee.first_name)
        .all()
    )


def _bank(rows):
    header = ["Nimewo", "Non", "Metòd", "Bank", "Kont / Telefòn", "Net", "Lajan", "Chèk"]
    body, total = [], 0
    for slip, emp in rows:
        method = slip.payment_method
        if method == PaymentMethod.DIRECT_DEPOSIT:
            account = emp.bank_account_number or ""
        elif method in (PaymentMethod.MONCASH, PaymentMethod.NATCASH):
            account = emp.mobile_money_number or ""
        else:
            account = ""
        total += slip.net_amount or 0
        body.append([emp.employee_number, emp.full_name, method.value, slip.bank_name or "",
                     account, _money(slip.net_amount), slip.currency.value, slip.check_number or ""])
    body.append(["TOTAL", "", "", "", "", _money(total), "", ""])
    return header, body


def _social(rows, field: str, label: str):
    header = ["Nimewo", "Non", "NIF / CIN", "Brit", label]
    body, t_gross, t_amount = [], 0, 0
    for slip, emp in rows:
        amount = getattr(slip, field) or 0
        t_gross += slip.gross_amount or 0
        t_amount += amount
        body.append([emp.employee_number, emp.full_name, emp.national_id or "",
                     _money(slip.gross_amount), _money(amount)])
    body.append(["TOTAL", "", "", _money(t_gross), _money(t_amount)])
    return header, body


def _dgi(rows):
    header = ["Nimewo", "Non", "NIF / CIN", "Brit", "IRI", "Retni sou bonis", "CFGDCT", "FDU / CAS", "Total retni"]
    body = []
    totals = [0] * 6
    for slip, emp in rows:
        values = [slip.gross_amount, slip.tax_amount, slip.supplemental_tax_amount,
                  slip.cfgdct_amount, slip.fdu_cas_amount]
        values = [v or 0 for v in values]
        withheld = sum(values[1:])
        for i, v in enumerate(values + [withheld]):
            totals[i] += v
        body.append([emp.employee_number, emp.full_name, emp.national_id or "",
                     *[_money(v) for v in values], _money(withheld)])
    body.append(["TOTAL", "", "", *[_money(v) for v in totals]])
    return header, body


@router.get("/periods/{period_id}/export/{kind}", dependencies=[Depends(require_hr)])
def export_period(period_id: int, kind: ExportKind, user: CurrentUser, org_id: TenantId,
                  request: Request, db: DbSession):
    period = db.query(PayPeriod).filter(
        PayPeriod.id == period_id, PayPeriod.organization_id == org_id,
    ).first()
    if period is None:
        raise HTTPException(status_code=404, detail="Peryòd la pa jwenn.")
    if period.status not in (PayrollStatus.APPROVED, PayrollStatus.PAID):
        raise HTTPException(status_code=400,
                            detail="Apwouve pewòl la anvan ou telechaje rapò yo.")

    rows = _rows(db, org_id, period.id)
    if kind == "bank":
        header, body = _bank(rows)
    elif kind == "ona":
        header, body = _social(rows, "ona_amount", "ONA (6%)")
    elif kind == "ofatma":
        header, body = _social(rows, "ofatma_amount", "OFATMA (3%)")
    else:
        header, body = _dgi(rows)

    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\r\n")
    writer.writerow(header)
    writer.writerows(body)

    org = db.get(Organization, org_id)
    db.add(AuditLog(
        organization_id=org_id, user_id=user.id, action="export", entity_type="pay_period",
        entity_id=period.id, changes=f"Rapò {kind}: {len(rows)} fich.",
        ip_address=request.client.host if request.client else None,
        user_agent=(request.headers.get("user-agent") or "")[:255],
    ))
    db.commit()

    slug = "".join(c for c in (org.slug if org else "biznis") if c.isalnum() or c == "-")
    filename = f"{kind}-{slug}-{period.start_date:%Y-%m-%d}.csv"
    return Response(
        content="\ufeff" + buf.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"',
                 "Cache-Control": "no-store"},
    )