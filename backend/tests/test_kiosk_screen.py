"""
Konbit — Tès nouvo ekran pwentaj la: idantifikasyon (etap 1), mòd "kòd sèlman", foto
Chemen: backend/tests/test_kiosk_screen.py
"""

import base64
import io

from PIL import Image

import app.routers.kiosk as kiosk
from app.database import SessionLocal
from app.models import Employee


def _setup(client, h, pin_mode=None):
    body = {"clock_mode": "both"}
    if pin_mode:
        body["pin_mode"] = pin_mode
    assert client.put("/api/kiosk/settings", json=body, headers=h).status_code == 200
    token = client.post("/api/kiosk/devices", json={"name": "Tablèt tès"}, headers=h).json()["token"]
    return {"X-Kiosk-Token": token}


def _pin(client, h, emp_id):
    resp = client.post(f"/api/kiosk/employees/{emp_id}/pin", headers=h)
    assert resp.status_code == 200, resp.text
    return resp.json()


def test_identify_then_punch_with_number_and_pin(client, org_admin, make_employee):
    h = org_admin["headers"]
    tab = _setup(client, h)
    emp = make_employee(h)["employee"]
    issued = _pin(client, h, emp["id"])

    who = client.post("/api/kiosk/identify", json={
        "employee_number": issued["employee_number"], "pin": issued["pin"]}, headers=tab)
    assert who.status_code == 200, who.text
    assert who.json()["first_name"] == emp["first_name"] and who.json()["clocked_in"] is False

    # Mòd "nimewo + kòd": kòd la pou kont li pa sifi.
    assert client.post("/api/kiosk/identify", json={"pin": issued["pin"]}, headers=tab).status_code == 401

    done = client.post("/api/kiosk/punch", json={
        "employee_number": issued["employee_number"], "pin": issued["pin"], "action": "in"}, headers=tab)
    assert done.status_code == 200, done.text
    again = client.post("/api/kiosk/identify", json={
        "employee_number": issued["employee_number"], "pin": issued["pin"]}, headers=tab).json()
    assert again["clocked_in"] is True and again["elapsed_minutes"] == 0


def test_pin_only_mode(client, org_admin, make_employee):
    h = org_admin["headers"]
    tab = _setup(client, h, pin_mode="pin_only")
    settings = client.get("/api/kiosk/settings", headers=h).json()
    assert settings["pin_mode"] == "pin_only"

    emp = make_employee(h)["employee"]
    issued = _pin(client, h, emp["id"])
    who = client.post("/api/kiosk/identify", json={"pin": issued["pin"]}, headers=tab)
    assert who.status_code == 200 and who.json()["first_name"] == emp["first_name"]

    wrong = "999998" if issued["pin"] != "999998" else "999997"
    assert client.post("/api/kiosk/identify", json={"pin": wrong}, headers=tab).status_code == 401

    punch = client.post("/api/kiosk/punch", json={"pin": issued["pin"], "action": "in"}, headers=tab)
    assert punch.status_code == 200, punch.text

    info = client.get("/api/kiosk/device", headers=tab).json()
    assert info["pin_mode"] == "pin_only"


def test_pins_are_unique_in_a_business(client, org_admin, make_employee, monkeypatch):
    h = org_admin["headers"]
    a = make_employee(h)["employee"]
    b = make_employee(h)["employee"]
    sequence = iter(["246810", "246810", "135790"])
    monkeypatch.setattr(kiosk, "_new_pin", lambda: next(sequence))
    assert _pin(client, h, a["id"])["pin"] == "246810"
    assert _pin(client, h, b["id"])["pin"] == "135790"      # 246810 deja pran


def test_old_pins_get_their_lookup_on_first_use(client, org_admin, make_employee):
    h = org_admin["headers"]
    tab = _setup(client, h)
    emp = make_employee(h)["employee"]
    issued = _pin(client, h, emp["id"])
    with SessionLocal() as db:                              # tankou yon kòd anvan migrasyon an
        db.get(Employee, emp["id"]).kiosk_pin_lookup = None
        db.commit()
    assert client.get("/api/kiosk/settings", headers=h).json()["pins_need_reset"] == 1

    client.post("/api/kiosk/identify", json={
        "employee_number": issued["employee_number"], "pin": issued["pin"]}, headers=tab)
    assert client.get("/api/kiosk/settings", headers=h).json()["pins_need_reset"] == 0


def test_photo_is_shown_on_the_tablet(client, org_admin, make_employee_login):
    h = org_admin["headers"]
    tab = _setup(client, h)
    worker = make_employee_login(h)
    buf = io.BytesIO()
    Image.new("RGB", (300, 300), (10, 120, 200)).save(buf, "JPEG")
    url = client.put("/api/profile/photo", json={"data_base64": base64.b64encode(buf.getvalue()).decode()},
                     headers=worker["headers"]).json()["url"]
    issued = _pin(client, h, worker["employee"]["id"])
    who = client.post("/api/kiosk/identify", json={
        "employee_number": issued["employee_number"], "pin": issued["pin"]}, headers=tab).json()
    assert who["photo_url"] == url


def test_identify_counts_failures_and_stays_in_its_business(client, org_admin, make_org, make_employee):
    h = org_admin["headers"]
    _setup(client, h, pin_mode="pin_only")
    issued = _pin(client, h, make_employee(h)["employee"]["id"])

    other = make_org()
    tab_b = _setup(client, other["headers"], pin_mode="pin_only")
    assert client.post("/api/kiosk/identify", json={"pin": issued["pin"]}, headers=tab_b).status_code == 401

    for _ in range(kiosk.MAX_DEVICE_FAILURES - 1):
        client.post("/api/kiosk/identify", json={"pin": "000001"}, headers=tab_b)
    locked = client.post("/api/kiosk/identify", json={"pin": "000001"}, headers=tab_b)
    assert locked.status_code == 429