"""
Konbit — Tès Dosye mwen, kòlèg mwen, ak demann chanjman peman
Chemen: backend/tests/test_payment_changes.py
"""


def _worker(client, make_employee, h, **overrides):
    """(dosye, headers, modpas) pou yon anplwaye ki gen kont."""
    import uuid
    email = f"peman-{uuid.uuid4().hex[:6]}@konbit-test.ht"
    overrides.setdefault("personal_email", email)
    result = make_employee(h, create_login=True, **overrides)
    login = client.post("/api/auth/login", json={
        "email": result["login_email"], "password": result["temporary_password"]})
    assert login.status_code == 200, login.text
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
    return result["employee"], headers, result["temporary_password"]


def _moncash(client, headers, password, number="3712 3456"):
    return client.post("/api/payment-changes/me", json={
        "method": "moncash", "account_number": number, "password": password}, headers=headers)


# ---------------------------------------------------------------------------
# DOSYE MWEN
# ---------------------------------------------------------------------------

def test_profile_read_and_contact_update(client, org_admin, make_employee):
    h = org_admin["headers"]
    emp, me, _ = _worker(client, make_employee, h, preferred_payment_method="direct_deposit",
                         bank_name="Unibank", bank_account_number="1234567890")

    prof = client.get("/api/profile/me", headers=me).json()
    assert prof["employee_number"] == emp["employee_number"]
    assert prof["payment"] == {"method": "direct_deposit", "bank_name": "Unibank", "account_last4": "7890"}
    assert "1234567890" not in str(prof)

    resp = client.patch("/api/profile/me", json={
        "phone": "+509 3700 0000", "city": "Okap",
        "emergency_contact_name": "Mari", "emergency_contact_phone": "+509 3800 0000",
    }, headers=me)
    assert resp.status_code == 200, resp.text
    assert resp.json()["city"] == "Okap" and resp.json()["emergency_contact_name"] == "Mari"

    assert client.patch("/api/profile/me", json={"personal_email": "pa-imel"}, headers=me).status_code == 422
    assert client.patch("/api/profile/me", json={"base_salary": 1}, headers=me).status_code == 422
    assert client.patch("/api/profile/me", json={"city": ""}, headers=me).json()["city"] is None


def test_employee_cannot_change_mobile_money_directly(client, org_admin, make_employee):
    emp, me, _ = _worker(client, make_employee, org_admin["headers"])
    resp = client.patch(f"/api/employees/{emp['id']}", json={"mobile_money_number": "37000000"}, headers=me)
    assert resp.status_code == 403
    # Kontak li toujou mache pa ansyen chemen an.
    ok = client.patch(f"/api/employees/{emp['id']}", json={"phone": "37111111"}, headers=me)
    assert ok.status_code == 200, ok.text


def test_team_shows_manager_and_colleagues_only(client, org_admin, make_employee, make_employee_login):
    h = org_admin["headers"]
    boss = make_employee_login(h, login_role="manager")
    boss_id = boss["employee"]["id"]
    _, me, _ = _worker(client, make_employee, h, manager_id=boss_id)
    peer = make_employee_login(h, manager_id=boss_id)
    stranger = make_employee_login(h)

    team = client.get("/api/profile/team", headers=me).json()
    assert team["manager"]["employee_id"] == boss_id
    ids = {c["employee_id"] for c in team["colleagues"]}
    assert peer["employee"]["id"] in ids and stranger["employee"]["id"] not in ids
    assert set(team["colleagues"][0]) == {"employee_id", "name", "employee_number", "position_title"}

    alone = client.get("/api/profile/team", headers=stranger["headers"]).json()
    assert alone == {"manager": None, "colleagues": []}


# ---------------------------------------------------------------------------
# DEMANN CHANJMAN PEMAN
# ---------------------------------------------------------------------------

def test_request_needs_password_and_valid_account(client, org_admin, make_employee):
    _, me, pw = _worker(client, make_employee, org_admin["headers"])
    assert _moncash(client, me, "move-modpas").status_code == 400
    assert _moncash(client, me, pw, number="12").status_code == 422
    bad_bank = client.post("/api/payment-changes/me", json={
        "method": "direct_deposit", "account_number": "123456", "password": pw}, headers=me)
    assert bad_bank.status_code == 422
    assert client.post("/api/payment-changes/me", json={
        "method": "check", "password": pw}, headers=me).status_code == 400      # deja chèk


def test_request_is_pending_until_hr_approves(client, org_admin, make_employee):
    h = org_admin["headers"]
    emp, me, pw = _worker(client, make_employee, h)

    resp = _moncash(client, me, pw)
    assert resp.status_code == 201, resp.text
    req = resp.json()
    assert req["status"] == "pending" and req["account_last4"] == "3456"
    assert client.get("/api/profile/me", headers=me).json()["payment"]["method"] == "check"
    assert _moncash(client, me, pw, number="37999999").status_code == 409     # yon sèl k ap tann

    listing = client.get("/api/payment-changes", headers=h)
    assert listing.status_code == 200
    assert req["id"] in {i["id"] for i in listing.json()["items"]}
    assert "37123456" not in listing.text                                      # HR wè 4 chif sèlman

    ok = client.post(f"/api/payment-changes/{req['id']}/decide", json={"approve": True}, headers=h)
    assert ok.status_code == 200, ok.text
    assert ok.json()["status"] == "approved"
    assert client.get("/api/profile/me", headers=me).json()["payment"] == {
        "method": "moncash", "bank_name": None, "account_last4": "3456"}

    again = client.post(f"/api/payment-changes/{req['id']}/decide", json={"approve": False}, headers=h)
    assert again.status_code == 409

    logged = client.get("/api/audit", params={"action": "payment_change_approve"}, headers=h).json()
    assert logged["items"][0]["sensitive"] is True


def test_cancel_and_reject(client, org_admin, make_employee):
    h = org_admin["headers"]
    _, me, pw = _worker(client, make_employee, h)
    first = _moncash(client, me, pw).json()
    assert client.post(f"/api/payment-changes/me/{first['id']}/cancel", headers=me).json()["status"] == "cancelled"

    second = _moncash(client, me, pw).json()
    no = client.post(f"/api/payment-changes/{second['id']}/decide",
                     json={"approve": False, "note": "Rele HR."}, headers=h)
    assert no.json()["status"] == "rejected" and no.json()["decision_note"] == "Rele HR."
    assert client.get("/api/profile/me", headers=me).json()["payment"]["method"] == "check"
    mine = client.get("/api/payment-changes/me", headers=me).json()["items"]
    assert [i["status"] for i in mine] == ["rejected", "cancelled"]


def test_nobody_approves_own_request_and_workers_cannot_decide(client, org_admin, make_employee):
    h = org_admin["headers"]
    _, hr_me, hr_pw = _worker(client, make_employee, h, login_role="hr")
    req = _moncash(client, hr_me, hr_pw).json()

    own = client.post(f"/api/payment-changes/{req['id']}/decide", json={"approve": True}, headers=hr_me)
    assert own.status_code == 403

    _, worker, _ = _worker(client, make_employee, h)
    assert client.get("/api/payment-changes", headers=worker).status_code == 403
    assert client.post(f"/api/payment-changes/{req['id']}/decide",
                       json={"approve": True}, headers=worker).status_code == 403

    # Yon lòt moun HR (isit la admin nan) ka apwouve l.
    assert client.post(f"/api/payment-changes/{req['id']}/decide",
                       json={"approve": True}, headers=h).status_code == 200


def test_requests_stay_in_their_business(client, make_org, make_employee):
    a, b = make_org(), make_org()
    _, me, pw = _worker(client, make_employee, a["headers"])
    req = _moncash(client, me, pw).json()

    assert req["id"] not in {i["id"] for i in client.get(
        "/api/payment-changes", params={"status": "all"}, headers=b["headers"]).json()["items"]}
    assert client.post(f"/api/payment-changes/{req['id']}/decide",
                       json={"approve": True}, headers=b["headers"]).status_code == 404