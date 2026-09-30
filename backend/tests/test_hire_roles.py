"""
Tès anbochaj (routers/offers.py): menm règ wòl ak POST /api/employees.
HR pa ka anboche yon kandida kòm org_admin; pèsonn pa ka bay super_admin.
Pwopozisyon "aksepte" a kreye dirèk nan baz done a pou tès la rete kout.
"""
import uuid

from app.database import SessionLocal
from app.models import (
    Application, ApplicationStage, JobPosting, JobStatus, Offer, OfferStatus, Organization,
)


def _accepted_offer(org_slug: str) -> int:
    """Yon òf travay + yon aplikasyon + yon pwopozisyon kandida a aksepte."""
    unique = uuid.uuid4().hex[:8]
    with SessionLocal() as db:
        org = db.query(Organization).filter(Organization.slug == org_slug).first()
        job = JobPosting(organization_id=org.id, title=f"Kesye {unique}",
                         status=JobStatus.PUBLISHED, openings=5)
        db.add(job)
        db.flush()
        app = Application(organization_id=org.id, job_posting_id=job.id,
                          full_name="Kandida Tès", email=f"kandida-{unique}@konbit-test.ht",
                          stage=ApplicationStage.OFFER)
        db.add(app)
        db.flush()
        offer = Offer(organization_id=org.id, application_id=app.id,
                      salary=4_500_000, status=OfferStatus.ACCEPTED)
        db.add(offer)
        db.commit()
        return offer.id


def _hire(client, headers, offer_id, role):
    return client.post(f"/api/offers/{offer_id}/hire", json={
        "first_name": "Kandida",
        "last_name": "Tès",
        "create_login": True,
        "login_email": f"anboche-{uuid.uuid4().hex[:8]}@konbit-test.ht",
        "login_role": role,
    }, headers=headers)


def test_hr_cannot_hire_as_admin(client, org_admin, make_employee_login):
    hr = make_employee_login(org_admin["headers"], login_role="hr")["headers"]
    assert _hire(client, hr, _accepted_offer(org_admin["org_slug"]), "org_admin").status_code == 403
    assert _hire(client, hr, _accepted_offer(org_admin["org_slug"]), "super_admin").status_code == 422


def test_admin_can_hire_as_admin_but_never_super_admin(client, org_admin):
    h = org_admin["headers"]
    assert _hire(client, h, _accepted_offer(org_admin["org_slug"]), "super_admin").status_code == 422
    r = _hire(client, h, _accepted_offer(org_admin["org_slug"]), "org_admin")
    assert r.status_code == 201, r.text


def test_hr_can_still_hire_an_employee(client, org_admin, make_employee_login):
    hr = make_employee_login(org_admin["headers"], login_role="hr")["headers"]
    r = _hire(client, hr, _accepted_offer(org_admin["org_slug"]), "employee")
    assert r.status_code == 201, r.text