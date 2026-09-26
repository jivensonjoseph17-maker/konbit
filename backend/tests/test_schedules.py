"""
Konbit — Tès orè travay pa semèn
Chemen: backend/tests/test_schedules.py
"""

import uuid

MONDAY = "2026-10-05"          # yon lendi
PREV_MONDAY = "2026-09-28"


def _employee(client, headers, *, login_role=None, manager_id=None):
    """Kreye yon anplwaye. Retounen (id, headers koneksyon li oswa None)."""
    email = f"sch-{uuid.uuid4().hex[:8]}@konbit-test.ht"
    payload = {
        "first_name": "Moun", "last_name": uuid.uuid4().hex[:6],
        "hire_date": "2026-01-05", "base_salary": 3_000_000,
        "preferred_payment_method": "check", "manager_id": manager_id,
        "create_login": bool(login_role), "personal_email": email if login_role else None,
        "login_email": email if login_role else None, "login_role": login_role or "employee",
    }
    r = client.post("/api/employees", json=payload, headers=headers)
    assert r.status_code in (200, 201), r.text
    data = r.json()
    emp_id = data["employee"]["id"]
    if not login_role:
        return emp_id, None
    tok = client.post("/api/auth/login", json={
        "email": data["login_email"], "password": data["temporary_password"],
    }).json()["access_token"]
    return emp_id, {"Authorization": f"Bearer {tok}"}


def _template(client, headers, start="07:00", end="15:00", brk=60, name="Maten"):
    r = client.post("/api/schedules/templates", headers=headers, json={
        "name": name, "start_time": start, "end_time": end, "break_minutes": brk,
    })
    assert r.status_code == 201, r.text
    return r.json()


def test_templates_and_night_shift_minutes(client, make_org):
    h = make_org()["headers"]
    day = _template(client, h)
    night = _template(client, h, "22:00", "06:00", 30, "Lannwit")
    assert day["minutes"] == 7 * 60 and day["overnight"] is False
    assert night["minutes"] == 8 * 60 - 30 and night["overnight"] is True
    names = [t["name"] for t in client.get("/api/schedules/templates", headers=h).json()]
    assert names == ["Maten", "Lannwit"]          # dapre lè kòmansman


def test_shift_is_hidden_until_published(client, make_org):
    h = make_org()["headers"]
    tpl = _template(client, h)
    emp_id, emp_h = _employee(client, h, login_role="employee")

    r = client.put("/api/schedules/shifts", headers=h, json={
        "employee_id": emp_id, "work_date": MONDAY, "template_id": tpl["id"],
    })
    assert r.status_code == 200 and r.json()["is_published"] is False

    week = client.get(f"/api/schedules/week?start={MONDAY}", headers=h).json()
    row = next(x for x in week["rows"] if x["employee_id"] == emp_id)
    assert row["minutes_total"] == 420 and week["unpublished"] == 1

    assert client.get(f"/api/schedules/me?start={MONDAY}", headers=emp_h).json()["shifts"] == []
    assert client.post("/api/schedules/week/publish", headers=h,
                       json={"week_start": MONDAY}).json()["published"] == 1
    mine = client.get(f"/api/schedules/me?start={MONDAY}", headers=emp_h).json()
    assert [s["work_date"] for s in mine["shifts"]] == [MONDAY]


def test_upsert_replaces_and_validates(client, make_org):
    h = make_org()["headers"]
    emp_id, _ = _employee(client, h)
    base = {"employee_id": emp_id, "work_date": MONDAY}
    first = client.put("/api/schedules/shifts", headers=h,
                       json={**base, "start_time": "08:00", "end_time": "12:00"}).json()
    second = client.put("/api/schedules/shifts", headers=h,
                        json={**base, "start_time": "13:00", "end_time": "17:00"}).json()
    assert first["id"] == second["id"] and second["start_time"].startswith("13:00")

    too_long = client.put("/api/schedules/shifts", headers=h,
                          json={**base, "start_time": "06:00", "end_time": "23:00"})
    assert too_long.status_code == 400
    assert too_long.json()["detail"] == "Yon orè pa ka depase 16 èdtan."
    assert client.put("/api/schedules/shifts", headers=h, json=base).status_code == 400

    assert client.delete(f"/api/schedules/shifts/{second['id']}", headers=h).status_code == 204


def test_copy_previous_week_skips_existing_days(client, make_org):
    h = make_org()["headers"]
    emp_id, _ = _employee(client, h)
    for day in ("2026-09-28", "2026-09-29"):
        client.put("/api/schedules/shifts", headers=h, json={
            "employee_id": emp_id, "work_date": day, "start_time": "07:00", "end_time": "15:00"})
    client.put("/api/schedules/shifts", headers=h, json={
        "employee_id": emp_id, "work_date": "2026-09-29".replace("09-29", "10-06"),
        "start_time": "09:00", "end_time": "17:00"})

    r = client.post("/api/schedules/week/copy", headers=h, json={"week_start": MONDAY}).json()
    assert r == {"created": 1, "skipped": 1}


def test_weekly_warning_over_48_hours(client, make_org):
    h = make_org()["headers"]
    emp_id, _ = _employee(client, h)
    for i in range(5, 11):                       # 6 jou × 9è = 54è
        client.put("/api/schedules/shifts", headers=h, json={
            "employee_id": emp_id, "work_date": f"2026-10-{i:02d}",
            "start_time": "07:00", "end_time": "16:00"})
    row = client.get(f"/api/schedules/week?start={MONDAY}", headers=h).json()["rows"][0]
    assert row["minutes_total"] == 54 * 60 and row["over_weekly_limit"] is True


def test_manager_schedules_only_own_team(client, make_org):
    h = make_org()["headers"]
    mgr_id, mgr_h = _employee(client, h, login_role="manager")
    mine, _ = _employee(client, h, manager_id=mgr_id)
    other, _ = _employee(client, h)
    shift = {"work_date": MONDAY, "start_time": "07:00", "end_time": "15:00"}

    assert client.put("/api/schedules/shifts", headers=mgr_h,
                      json={**shift, "employee_id": mine}).status_code == 200
    assert client.put("/api/schedules/shifts", headers=mgr_h,
                      json={**shift, "employee_id": other}).status_code == 403
    assert client.put("/api/schedules/shifts", headers=mgr_h,
                      json={**shift, "employee_id": mgr_id}).status_code == 403

    ids = [r["employee_id"] for r in
           client.get(f"/api/schedules/week?start={MONDAY}", headers=mgr_h).json()["rows"]]
    assert ids == [mine]
    # Yon manadjè pa kreye modèl: se HR ki fè sa.
    assert client.post("/api/schedules/templates", headers=mgr_h, json={
        "name": "X", "start_time": "07:00", "end_time": "15:00"}).status_code == 403