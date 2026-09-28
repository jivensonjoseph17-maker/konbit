"""
Konbit — Rapò pewòl ak fichye bank (CSV)
Chemen: backend/app/routers/payroll_exports.py

    GET /api/payroll/periods/{id}/export/bank     Transfè: depo dirèk, MonCash, NatCash (net pou chak moun)
    GET /api/payroll/periods/{id}/export/checks   Chèk ak kach: lis pou kesye a, ak kolòn siyati
    GET /api/payroll/periods/{id}/export/ona      ONA — brit ak retni 6% (pati anplwaye a)
    GET /api/payroll/periods/{id}/export/ofatma   OFATMA — brit ak retni 3%
    GET /api/payroll/periods/{id}/export/dgi      DGI — IRI, retni sou bonis, CFGDCT, FDU/CAS

    ?excel=true  →  pou Excel an franse: ";" kòm separatè, "4972,75" (vigil desimal).
                    San li: "," kòm separatè, "4972.75" — sa bank yo ak lojisyèl yo atann.

RÈG:
  - HR / admin sèlman, epi sèlman pou yon pewòl APWOUVE oswa PEYE
    (yon bouyon ka chanje ankò — yon rapò sou li ta fo).
  - Fichye bank lan gen NIMEWO KONT KONPLÈ yo: chak telechajman ale nan
    jounal odit la (kiyès, kilè, ki peryòd). Chèk ak kach PA ladan l:
    bank lan pa ka trete yo, yo nan rapò "checks" la.
  - Metòd peman an ekri an kreyòl ("Depo dirèk"), pa kòd entèn nan.
  - CSV UTF-8 ak BOM (Excel louvri aksan yo byen), yon liy TOTAL anba.

ATANSYON: fòma ofisyèl ONA / OFATMA / DGI ak fòma chak bank ka mande lòt
kolòn. Yon kontab dwe verifye rapò yo anvan yo soumèt.
"""

import csv
import io
from typing import Callable, Literal

from fastapi import APIRouter, Depends, HTTPException, Request, Response

from ..deps import CurrentUser, DbSession, TenantId, require_hr
from ..models import (
    AuditLog, Employee, Organization, PaymentMethod, PayPeriod, PayrollStatus, Payslip,
)

router = APIRouter()

ExportKind = Literal["bank", "checks", "ona", "ofatma", "dgi"]

# Sa bank lan ka voye: yon kont oswa yon nimewo telefòn.
TRANSFER_METHODS = (PaymentMethod.DIRECT_DEPOSIT, PaymentMethod.MONCASH, PaymentMethod.NATCASH)

METHOD_LABELS = {
    PaymentMethod.CHECK: "Chèk",
    PaymentMethod.DIRECT_DEPOSIT: "Depo dirèk",
    PaymentMethod.CASH: "Kach",
    PaymentMethod.MONCASH: "MonCash",
    PaymentMethod.NATCASH: "NatCash",
}

Money = Callable[[int], str]


def _money(cents) -> str:
    return f"{(cents or 0) / 100:.2f}"


def _money_fr(cents) -> str:
    """Excel an franse: vigil desimal ("4972,75")."""
    return _money(cents).replace(".", ",")


def _method_label(method: PaymentMethod) -> str:
    return METHOD_LABELS.get(method, method.value)


def _rows(db, org_id: int, period_id: int):
    return (
        db.query(Payslip, Employee)
        .join(Employee, Payslip.employee_id == Employee.id)
        .filter(Payslip.organization_id == org_id, Payslip.pay_period_id == period_id)
        .order_by(Employee.last_name, Employee.first_name)
        .all()
    )


def _bank(rows, money: Money):
    header = ["Nimewo", "Non", "Metòd", "Bank", "Kont / Telefòn", "Net", "Lajan"]
    body, total = [], 0
    for slip, emp in rows:
        method = slip.payment_method
        if method not in TRANSFER_METHODS:
            continue
        if method == PaymentMethod.DIRECT_DEPOSIT:
            account = emp.bank_account_number or ""
        else:
            account = emp.mobile_money_number or ""
        total += slip.net_amount or 0
        body.append([emp.employee_number, emp.full_name, _method_label(method),
                     slip.bank_name or "", account, money(slip.net_amount), slip.currency.value])
    body.append(["TOTAL", "", "", "", "", money(total), ""])
    return header, body


def _checks(rows, money: Money):
    """Chèk ak kach: kesye a enprime lis la, chak moun siyen lè l resevwa lajan l."""
    header = ["Nimewo", "Non", "Metòd", "Nimewo chèk", "Net", "Lajan", "Siyati"]
    body, total = [], 0
    for slip, emp in rows:
        method = slip.payment_method
        if method in TRANSFER_METHODS:
            continue
        total += slip.net_amount or 0
        body.append([emp.employee_number, emp.full_name, _method_label(method),
                     slip.check_number or "", money(slip.net_amount), slip.currency.value, ""])
    body.append(["TOTAL", "", "", "", money(total), "", ""])
    return header, body


def _social(rows, field: str, label: str, money: Money):
    header = ["Nimewo", "Non", "NIF / CIN", "Brit", label]
    body, t_gross, t_amount = [], 0, 0
    for slip, emp in rows:
        amount = getattr(slip, field) or 0
        t_gross += slip.gross_amount or 0
        t_amount += amount
        body.append([emp.employee_number, emp.full_name, emp.national_id or "",
                     money(slip.gross_amount), money(amount)])
    body.append(["TOTAL", "", "", money(t_gross), money(t_amount)])
    return header, body


def _dgi(rows, money: Money):
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
                     *[money(v) for v in values], money(withheld)])
    body.append(["TOTAL", "", "", *[money(v) for v in totals]])
    return header, body


@router.get("/periods/{period_id}/export/{kind}", dependencies=[Depends(require_hr)])
def export_period(period_id: int, kind: ExportKind, user: CurrentUser, org_id: TenantId,
                  request: Request, db: DbSession, excel: bool = False):
    period = db.query(PayPeriod).filter(
        PayPeriod.id == period_id, PayPeriod.organization_id == org_id,
    ).first()
    if period is None:
        raise HTTPException(status_code=404, detail="Peryòd la pa jwenn.")
    if period.status not in (PayrollStatus.APPROVED, PayrollStatus.PAID):
        raise HTTPException(status_code=400,
                            detail="Apwouve pewòl la anvan ou telechaje rapò yo.")

    money: Money = _money_fr if excel else _money
    rows = _rows(db, org_id, period.id)
    if kind == "bank":
        header, body = _bank(rows, money)
    elif kind == "checks":
        header, body = _checks(rows, money)
    elif kind == "ona":
        header, body = _social(rows, "ona_amount", "ONA (6%)", money)
    elif kind == "ofatma":
        header, body = _social(rows, "ofatma_amount", "OFATMA (3%)", money)
    else:
        header, body = _dgi(rows, money)

    buf = io.StringIO()
    writer = csv.writer(buf, delimiter=";" if excel else ",", lineterminator="\r\n")
    writer.writerow(header)
    writer.writerows(body)

    lines = len(body) - 1        # san liy TOTAL la
    org = db.get(Organization, org_id)
    db.add(AuditLog(
        organization_id=org_id, user_id=user.id, action="export", entity_type="pay_period",
        entity_id=period.id,
        # "Rapò bank…" an premye: audit.py make l SANSIB (nimewo kont yo).
        changes=f"Rapò {kind}: {lines} fich{' (Excel)' if excel else ''}.",
        ip_address=request.client.host if request.client else None,
        user_agent=(request.headers.get("user-agent") or "")[:255],
    ))
    db.commit()

    slug = "".join(c for c in (org.slug if org else "biznis") if c.isalnum() or c == "-")
    filename = f"{kind}-{slug}-{period.start_date:%Y-%m-%d}{'-excel' if excel else ''}.csv"
    return Response(
        content="\ufeff" + buf.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"',
                 "Cache-Control": "no-store"},
    )