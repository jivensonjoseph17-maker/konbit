"""
Konbit — Tès fich peye PDF
Chemen: backend/tests/test_payslip_pdf.py
"""

from datetime import date

from app.payslip_pdf import PayslipDoc, render_payslip_pdf

PERIOD = {
    "name": "Out 2026",
    "start_date": "2026-08-01",
    "end_date": "2026-08-31",
    "pay_date": "2026-08-31",
}


def _slip_id(client, h, make_employee):
    make_employee(h, base_salary=4_500_000, hire_date="2025-01-01")
    pid = client.post("/api/payroll/periods", json=PERIOD, headers=h).json()["id"]
    run = client.post(f"/api/payroll/periods/{pid}/run", json={"pay_period_id": pid}, headers=h)
    assert run.status_code == 200, run.text
    rows = client.get(f"/api/payroll/periods/{pid}/payslips", headers=h).json()["items"]
    return pid, rows[0]["payslip"]["id"]


def test_hr_downloads_pdf(client, org_admin, make_employee):
    h = org_admin["headers"]
    _, sid = _slip_id(client, h, make_employee)

    resp = client.get(f"/api/payroll/payslips/{sid}/pdf?lang=fr", headers=h)
    assert resp.status_code == 200, resp.text
    assert resp.headers["content-type"] == "application/pdf"
    assert resp.content.startswith(b"%PDF")
    disposition = resp.headers["content-disposition"]
    assert disposition.startswith("attachment;") and "2026-08.pdf" in disposition


def test_pdf_needs_login(client, org_admin, make_employee):
    _, sid = _slip_id(client, org_admin["headers"], make_employee)
    assert client.get(f"/api/payroll/payslips/{sid}/pdf").status_code == 401


def test_unknown_payslip_is_404(client, org_admin):
    resp = client.get("/api/payroll/payslips/999999/pdf", headers=org_admin["headers"])
    assert resp.status_code == 404


def _doc(**over) -> PayslipDoc:
    base = dict(
        lang="ht", slip_id=7, status="paid", currency="HTG",
        org_name="Boulanjri Soley", org_address="Pòtoprens", org_tax_id="000-111-222-3",
        employee_name="Mari Jozèf", employee_number="KB-0007", position_title="Kesyè",
        period_name="Out 2026", start_date=date(2026, 8, 1), end_date=date(2026, 8, 31),
        pay_date=date(2026, 8, 31), paid_on=date(2026, 8, 31), generated_on=date(2026, 9, 1),
        base_amount=4_500_000, overtime_amount=0, overtime_hours=0.0, bonus_amount=500_000,
        gross_amount=5_000_000, tax_amount=300_000, supplemental_tax_amount=50_000,
        ona_amount=300_000, ofatma_amount=150_000, cfgdct_amount=50_000, fdu_cas_amount=50_000,
        other_deductions=0, net_amount=4_100_000,
        supplemental_rate=0.10, ona_rate=0.06, ofatma_rate=0.03, cfgdct_rate=0.01, fdu_cas_rate=0.01,
        payment_method="check", check_number="1001", bank_name=None, account_last4=None,
        transaction_ref=None,
    )
    base.update(over)
    return PayslipDoc(**base)


def test_labels_follow_language():
    assert b"FICH PEYE" in render_payslip_pdf(_doc(lang="ht"), compress=False)
    assert b"BULLETIN DE PAIE" in render_payslip_pdf(_doc(lang="fr"), compress=False)
    assert b"PAYSLIP" in render_payslip_pdf(_doc(lang="en"), compress=False)
    # Lang backend la pa konnen: angle
    assert b"PAYSLIP" in render_payslip_pdf(_doc(lang="zh"), compress=False)


def test_draft_is_watermarked_and_amounts_are_formatted():
    raw = render_payslip_pdf(_doc(status="draft"), compress=False)
    assert b"BOUYON" in raw
    assert b"41 000,00" in raw             # 4 100 000 santim, fòma kreyòl/franse
    raw_en = render_payslip_pdf(_doc(lang="en"), compress=False)
    assert b"41,000.00" in raw_en