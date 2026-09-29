"""
Konbit — Tès klòch notifikasyon
Chemen: backend/tests/test_notifications.py
"""

import uuid

from app.database import SessionLocal
from app.models import Notification, User


def _add(user_email, title, n=1):
    with SessionLocal() as db:
        user = db.query(User).filter(User.email == user_email).first()
        for i in range(n):
            db.add(Notification(organization_id=user.organization_id, user_id=user.id,
                                title=f"{title} {i}", body="Tès", link_url="/dashboard.html",
                                category="payroll"))
        db.commit()


def test_list_count_and_mark_read(client, org_admin):
    h = org_admin["headers"]
    _add(org_admin["email"], "Pewòl", n=3)

    assert client.get("/api/notifications/count", headers=h).json() == {"unread": 3}
    data = client.get("/api/notifications", headers=h).json()
    assert data["unread"] == 3 and len(data["items"]) == 3
    assert data["items"][0]["title"] == "Pewòl 2"             # pi resan an premye

    one = data["items"][0]["id"]
    assert client.post(f"/api/notifications/{one}/read", headers=h).json() == {"unread": 2}
    assert client.post("/api/notifications/read-all", headers=h).json() == {"unread": 0}
    assert all(i["is_read"] for i in client.get("/api/notifications", headers=h).json()["items"])


def test_nobody_reads_someone_elses(client, org_admin, make_org):
    _add(org_admin["email"], "Prive")
    mine = client.get("/api/notifications", headers=org_admin["headers"]).json()["items"][0]["id"]

    other = make_org()
    assert client.get("/api/notifications", headers=other["headers"]).json()["items"] == []
    assert client.post(f"/api/notifications/{mine}/read", headers=other["headers"]).status_code == 404
    assert client.get("/api/notifications/count", headers=org_admin["headers"]).json()["unread"] == 1


def test_payment_change_creates_a_notification_for_hr(client, org_admin, make_employee):
    h = org_admin["headers"]
    result = make_employee(h, create_login=True, personal_email=f"notif-{uuid.uuid4().hex[:6]}@example.com")
    token = client.post("/api/auth/login", json={
        "email": result["login_email"], "password": result["temporary_password"]}).json()["access_token"]
    me = {"Authorization": f"Bearer {token}"}
    client.post("/api/payment-changes/me", json={
        "method": "moncash", "account_number": "37123456",
        "password": result["temporary_password"]}, headers=me)

    items = client.get("/api/notifications", headers=h).json()["items"]
    assert any(i["title"] == "Demann chanjman peman" and i["link_url"] == "/payment-changes.html"
               for i in items)