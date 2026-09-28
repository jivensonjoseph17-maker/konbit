"""
Konbit — Tès zòn otorize (geofence) pou pwentaj sou telefòn
Chemen: backend/tests/test_geofence.py
"""

from app.routers.geofence import distance_m

# Yon pwen nan Pòtoprens, ak pwen ki pre / lwen li.
BIZ = (18.5392, -72.3350)
NEAR = (18.5395, -72.3352)        # ~40 m
FAR = (18.5500, -72.3350)         # ~1,2 km


def _zone(client, h, mode, radius=150, center=BIZ):
    return client.put("/api/organization/geofence", json={
        "mode": mode, "latitude": center[0], "longitude": center[1], "radius_m": radius,
    }, headers=h)


def _clock_in(client, h, pos=None):
    body = {"latitude": pos[0], "longitude": pos[1]} if pos else {}
    return client.post("/api/attendance/clock-in", json=body, headers=h)


def _clock_out(client, h, pos=None):
    body = {"break_minutes": 0}
    if pos:
        body.update(latitude=pos[0], longitude=pos[1])
    return client.post("/api/attendance/clock-out", json=body, headers=h)


def test_distance_is_in_meters():
    assert distance_m(*BIZ, *BIZ) == 0
    assert 30 <= distance_m(*BIZ, *NEAR) <= 50
    assert 1100 <= distance_m(*BIZ, *FAR) <= 1250
    # 0,001° lonjitid nan Pòtoprens ≈ 105 m
    assert 100 <= distance_m(18.5392, -72.3350, 18.5392, -72.3340) <= 112


# ---------------------------------------------------------------------------
# PARAMÈT YO
# ---------------------------------------------------------------------------

def test_settings_rules_and_rights(client, org_admin, make_employee_login):
    h = org_admin["headers"]
    assert client.get("/api/organization/geofence", headers=h).json() == {
        "mode": "off", "latitude": None, "longitude": None, "radius_m": None}

    # Pa ka aktive san pozisyon ak distans; distans twò piti refize.
    assert client.put("/api/organization/geofence", json={"mode": "block"}, headers=h).status_code == 422
    assert _zone(client, h, "block", radius=10).status_code == 422
    assert client.put("/api/organization/geofence", json={
        "mode": "off", "latitude": 18.5}, headers=h).status_code == 422

    resp = _zone(client, h, "flag")
    assert resp.status_code == 200, resp.text
    assert resp.json() == {"mode": "flag", "latitude": BIZ[0], "longitude": BIZ[1], "radius_m": 150}

    hr = make_employee_login(h, login_role="hr")
    worker = make_employee_login(h)
    assert client.get("/api/organization/geofence", headers=hr["headers"]).status_code == 200
    assert _zone(client, hr["headers"], "off").status_code == 403
    assert client.get("/api/organization/geofence", headers=worker["headers"]).status_code == 403

    logged = client.get("/api/audit", params={"entity_type": "organization_geofence"},
                        headers=h).json()["items"]
    assert logged and "mòd=flag" in logged[0]["changes"]


# ---------------------------------------------------------------------------
# PWENTAJ
# ---------------------------------------------------------------------------

def test_block_mode_refuses_far_or_hidden_clock_in(client, org_admin, make_employee_login):
    h = org_admin["headers"]
    worker = make_employee_login(h)["headers"]
    _zone(client, h, "block")

    assert _clock_in(client, worker, FAR).status_code == 403
    assert _clock_in(client, worker).status_code == 403            # pa pataje pozisyon

    resp = _clock_in(client, worker, NEAR)
    assert resp.status_code == 201, resp.text
    entry = resp.json()
    assert entry["outside_zone"] is False and entry["clock_in_distance_m"] <= 50

    # Klòk out pa janm bloke, menm lwen: li make sèlman.
    out = _clock_out(client, worker, FAR)
    assert out.status_code == 200, out.text
    assert out.json()["outside_zone"] is True
    assert out.json()["clock_out_distance_m"] > 1000


def test_flag_mode_accepts_but_marks(client, org_admin, make_employee_login):
    h = org_admin["headers"]
    worker = make_employee_login(h)["headers"]
    _zone(client, h, "flag")

    resp = _clock_in(client, worker, FAR)
    assert resp.status_code == 201, resp.text
    assert resp.json()["outside_zone"] is True
    assert resp.json()["clock_in_distance_m"] > 1000

    # Menm si l tounen pre a klòk out, antre a rete make.
    out = _clock_out(client, worker, NEAR)
    assert out.json()["outside_zone"] is True and out.json()["clock_out_distance_m"] <= 50


def test_flag_mode_marks_missing_position(client, org_admin, make_employee_login):
    h = org_admin["headers"]
    worker = make_employee_login(h)["headers"]
    _zone(client, h, "flag")
    resp = _clock_in(client, worker)
    assert resp.status_code == 201
    assert resp.json()["outside_zone"] is True and resp.json()["clock_in_distance_m"] is None


def test_off_mode_records_distance_only(client, org_admin, make_employee_login):
    h = org_admin["headers"]
    worker = make_employee_login(h)["headers"]
    _zone(client, h, "off")
    resp = _clock_in(client, worker, FAR)
    assert resp.status_code == 201
    assert resp.json()["outside_zone"] is False and resp.json()["clock_in_distance_m"] > 1000


def test_zone_stays_in_its_business(client, make_org, make_employee_login):
    a, b = make_org(), make_org()
    _zone(client, a["headers"], "block")
    worker_b = make_employee_login(b["headers"])["headers"]
    resp = _clock_in(client, worker_b, FAR)
    assert resp.status_code == 201
    assert resp.json()["outside_zone"] is False and resp.json()["clock_in_distance_m"] is None
    assert client.get("/api/organization/geofence", headers=b["headers"]).json()["mode"] == "off"