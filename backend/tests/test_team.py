"""
Konbit — Tès wòl manadjè a: apwobasyon konje
Chemen: backend/tests/test_team.py
"""

from datetime import date, timedelta


def _next_monday() -> date:
    today = date.today()
    return today + timedelta(days=(7 - today.weekday()) or 7)


def _request_leave(client, headers, weeks_ahead=1):
    start = _next_monday() + timedelta(weeks=weeks_ahead)
    resp = client.post("/api/leaves", json={
        "leave_type": "vacation",
        "start_date": start.isoformat(),
        "end_date": (start + timedelta(days=1)).isoformat(),
    }, headers=headers)
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


def test_manager_sees_and_approves_team_leave(client, org_admin, make_employee_login):
    h = org_admin["headers"]
    manager = make_employee_login(h, login_role="manager")
    worker = make_employee_login(h, manager_id=manager["employee"]["id"])

    req_id = _request_leave(client, worker["headers"])

    pending = client.get("/api/leaves/pending", headers=manager["headers"])
    assert pending.status_code == 200, pending.text
    assert req_id in {i["request"]["id"] for i in pending.json()["items"]}

    decided = client.post(f"/api/leaves/{req_id}/decide", json={"approve": True},
                          headers=manager["headers"])
    assert decided.status_code == 200, decided.text
    assert decided.json()["status"] == "approved"


def test_manager_cannot_decide_outside_team(client, org_admin, make_employee_login):
    h = org_admin["headers"]
    manager = make_employee_login(h, login_role="manager")
    stranger = make_employee_login(h)          # pa gen manadjè

    req_id = _request_leave(client, stranger["headers"])

    pending = client.get("/api/leaves/pending", headers=manager["headers"]).json()
    assert req_id not in {i["request"]["id"] for i in pending["items"]}

    resp = client.post(f"/api/leaves/{req_id}/decide", json={"approve": True},
                       headers=manager["headers"])
    assert resp.status_code == 403


def test_hr_cannot_approve_own_leave(client, org_admin, make_employee_login):
    """Kontwòl entèn: pèsonn pa apwouve pwòp demann li, menm HR."""
    hr = make_employee_login(org_admin["headers"], login_role="hr")
    req_id = _request_leave(client, hr["headers"])

    pending = client.get("/api/leaves/pending", headers=hr["headers"]).json()
    assert req_id not in {i["request"]["id"] for i in pending["items"]}

    resp = client.post(f"/api/leaves/{req_id}/decide", json={"approve": True},
                       headers=hr["headers"])
    assert resp.status_code == 403

    # Yon lòt moun HR (isit la admin nan) ka toujou apwouve l
    ok = client.post(f"/api/leaves/{req_id}/decide", json={"approve": True},
                     headers=org_admin["headers"])
    assert ok.status_code == 200, ok.text


def test_manager_can_review_team_member_not_self(client, org_admin, make_employee_login):
    h = org_admin["headers"]
    manager = make_employee_login(h, login_role="manager")
    worker = make_employee_login(h, manager_id=manager["employee"]["id"])

    created = client.post("/api/feedback/reviews", json={
        "employee_id": worker["employee"]["id"],
        "period_label": "2026 — 2yèm semès",
        "overall_score": 4,
        "strengths": "Toujou alè.",
    }, headers=manager["headers"])
    assert created.status_code == 201, created.text

    team = client.get("/api/feedback/reviews/team", headers=manager["headers"])
    assert created.json()["id"] in {r["id"] for r in team.json()["items"]}

    finalized = client.post(f"/api/feedback/reviews/{created.json()['id']}/finalize",
                            headers=manager["headers"])
    assert finalized.status_code == 200, finalized.text

    self_review = client.post("/api/feedback/reviews", json={
        "employee_id": manager["employee"]["id"], "period_label": "Tès",
    }, headers=manager["headers"])
    assert self_review.status_code in (400, 403)