"""
Konbit — Tès kiyòsk (tablèt biznis la + kòd pèsonèl)
Chemen: backend/tests/test_kiosk.py
"""

import re


# ---------------------------------------------------------------------------
# ZOUTI
# ---------------------------------------------------------------------------

def _set_mode(client, h, mode):
    resp = client.put("/api/kiosk/settings", json={"clock_mode": mode}, headers=h)
    assert resp.status_code == 200, resp.text


def _device(client, h, name="Tablèt kès"):
    resp = client.post("/api/kiosk/devices", json={"name": name}, headers=h)
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["token"].startswith("kk_")
    return body["device"]["id"], {"X-Kiosk-Token": body["token"]}


def _pin(client, h, employee_id):
    resp = client.post(f"/api/kiosk/employees/{employee_id}/pin", headers=h)
    assert resp.status_code == 200, resp.text
    pin = resp.json()["pin"]
    assert re.fullmatch(r"\d{6}", pin)
    return pin


def _punch(client, kh, number, pin, action="in", **extra):
    return client.post("/api/kiosk/punch", json={
        "employee_number": number, "pin": pin, "action": action, **extra,
    }, headers=kh)


def _setup(client, org, make_employee, mode="kiosk"):
    h = org["headers"]
    if mode:
        _set_mode(client, h, mode)
    device_id, kh = _device(client, h)
    emp = make_employee(h, first_name="Woz")["employee"]
    return h, device_id, kh, emp, _pin(client, h, emp["id"])


def _wrong(pin):
    return f"{(int(pin) + 1) % 1_000_000:06d}"


# ---------------------------------------------------------------------------
# PWENTAJ
# ---------------------------------------------------------------------------

def test_punch_in_then_out(client, org_admin, make_employee):
    h, _, kh, emp, pin = _setup(client, org_admin, make_employee)

    first = _punch(client, kh, emp["employee_number"], pin, "in")
    assert first.status_code == 200, first.text
    assert first.json()["action"] == "in"
    assert first.json()["first_name"] == "Woz"

    assert _punch(client, kh, emp["employee_number"], pin, "in").status_code == 409

    out = _punch(client, kh, emp["employee_number"], pin, "out", break_minutes=0)
    assert out.status_code == 200, out.text
    assert out.json()["action"] == "out"
    assert out.json()["worked_minutes"] == 0

    assert _punch(client, kh, emp["employee_number"], pin, "out").status_code == 404

    entries = client.get(f"/api/attendance/employee/{emp['id']}", headers=h).json()["items"]
    assert len(entries) == 1 and entries[0]["status"] == "closed"


def test_digits_only_number_works(client, org_admin, make_employee):
    _, _, kh, emp, pin = _setup(client, org_admin, make_employee)
    digits = re.sub(r"\D", "", emp["employee_number"]).lstrip("0")
    assert _punch(client, kh, digits, pin).status_code == 200


def test_phone_mode_refuses_kiosk(client, org_admin, make_employee):
    _, _, kh, emp, pin = _setup(client, org_admin, make_employee, mode=None)
    assert client.get("/api/kiosk/settings", headers=org_admin["headers"]).json() == {
        "clock_mode": "phone",
    }
    assert _punch(client, kh, emp["employee_number"], pin).status_code == 409


def test_kiosk_mode_blocks_phone_clock(client, org_admin, make_employee_login):
    h = org_admin["headers"]
    me = make_employee_login(h)
    body = {"device_info": "tes"}

    _set_mode(client, h, "kiosk")
    assert client.get("/api/kiosk/settings", headers=me["headers"]).json()["clock_mode"] == "kiosk"
    assert client.post("/api/attendance/clock-in", json=body, headers=me["headers"]).status_code == 403

    _set_mode(client, h, "both")
    resp = client.post("/api/attendance/clock-in", json=body, headers=me["headers"])
    assert resp.status_code == 201, resp.text


# ---------------------------------------------------------------------------
# SEKIRITE
# ---------------------------------------------------------------------------

def test_wrong_pins_lock_and_new_pin_unlocks(client, org_admin, make_employee):
    h, _, kh, emp, pin = _setup(client, org_admin, make_employee)
    number = emp["employee_number"]

    for _ in range(5):
        assert _punch(client, kh, number, _wrong(pin)).status_code == 401
    assert _punch(client, kh, number, pin).status_code == 423      # menm bon kòd la bloke

    new_pin = _pin(client, h, emp["id"])
    assert _punch(client, kh, number, new_pin).status_code == 200


def test_same_error_for_unknown_number_and_wrong_pin(client, org_admin, make_employee):
    _, _, kh, emp, pin = _setup(client, org_admin, make_employee)
    unknown = _punch(client, kh, "KB-9999", pin)
    wrong = _punch(client, kh, emp["employee_number"], _wrong(pin))
    assert unknown.status_code == wrong.status_code == 401
    assert unknown.json()["detail"] == wrong.json()["detail"]


def test_missing_or_revoked_token(client, org_admin, make_employee):
    h, device_id, kh, emp, pin = _setup(client, org_admin, make_employee)

    assert client.post("/api/kiosk/punch", json={
        "employee_number": emp["employee_number"], "pin": pin, "action": "in",
    }).status_code == 401
    assert client.get("/api/kiosk/device", headers=kh).json()["device_name"] == "Tablèt kès"

    assert client.delete(f"/api/kiosk/devices/{device_id}", headers=h).status_code == 200
    assert _punch(client, kh, emp["employee_number"], pin).status_code == 401
    assert client.get("/api/kiosk/device", headers=kh).status_code == 401


def test_device_of_other_business_cannot_punch(client, make_org, make_employee):
    org_a, org_b = make_org(), make_org()
    _set_mode(client, org_a["headers"], "kiosk")
    _, kh_a = _device(client, org_a["headers"])

    emp_b = make_employee(org_b["headers"])["employee"]
    pin_b = _pin(client, org_b["headers"], emp_b["id"])

    assert _punch(client, kh_a, emp_b["employee_number"], pin_b).status_code == 401


def test_who_can_issue_pins_and_manage_devices(client, org_admin, make_employee, make_employee_login):
    h = org_admin["headers"]
    manager = make_employee_login(h, login_role="manager")
    report = make_employee(h, manager_id=manager["employee"]["id"])["employee"]
    stranger = make_employee(h)["employee"]
    worker = make_employee_login(h)

    mh = manager["headers"]
    assert client.post(f"/api/kiosk/employees/{report['id']}/pin", headers=mh).status_code == 200
    assert client.post(f"/api/kiosk/employees/{stranger['id']}/pin", headers=mh).status_code == 403
    assert client.post(f"/api/kiosk/employees/{stranger['id']}/pin",
                       headers=worker["headers"]).status_code == 403

    # Sèlman admin aktive tablèt ak chanje mòd la
    assert client.post("/api/kiosk/devices", json={"name": "Tablèt"}, headers=mh).status_code == 403
    assert client.put("/api/kiosk/settings", json={"clock_mode": "kiosk"},
                      headers=mh).status_code == 403
    assert client.put("/api/kiosk/settings", json={"clock_mode": "lòt"},
                      headers=h).status_code == 422

    # Kòd la pa janm parèt nan lis tablèt yo ni nan odit la: nou verifye lis la
    listing = client.get("/api/kiosk/devices", headers=h)
    assert listing.status_code == 200
    assert "token" not in listing.text