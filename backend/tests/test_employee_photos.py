"""
Konbit — Tès foto pwofil anplwaye
Chemen: backend/tests/test_employee_photos.py
"""

import base64
import io

from PIL import Image


def _image(size=(900, 600), fmt="JPEG", mode="RGB") -> str:
    buf = io.BytesIO()
    Image.new(mode, size, (200, 120, 40) if mode == "RGB" else (200, 120, 40, 255)).save(buf, fmt)
    return base64.b64encode(buf.getvalue()).decode()


def _upload(client, h, data=None):
    return client.put("/api/profile/photo", json={"data_base64": data or _image()}, headers=h)


def test_upload_is_square_and_shows_everywhere(client, org_admin, make_employee_login):
    worker = make_employee_login(org_admin["headers"])
    me, emp_id = worker["headers"], worker["employee"]["id"]

    resp = _upload(client, me)
    assert resp.status_code == 200, resp.text
    url = resp.json()["url"]
    assert url.startswith("/api/photos/") and url.endswith(".jpg")
    assert str(emp_id) not in url.split("/")[-1]              # pa gen id nan lyen an

    img = client.get(url)                                       # san token
    assert img.status_code == 200 and img.headers["content-type"] == "image/jpeg"
    assert img.headers["x-content-type-options"] == "nosniff"
    assert Image.open(io.BytesIO(img.content)).size == (256, 256)

    assert client.get("/api/auth/identity", headers=me).json()["photo_url"] == url
    photos = client.get("/api/photos/map", headers=org_admin["headers"]).json()["photos"]
    assert photos[str(emp_id)] == url


def test_new_photo_changes_the_link(client, org_admin, make_employee_login):
    me = make_employee_login(org_admin["headers"])["headers"]
    first = _upload(client, me).json()["url"]
    second = _upload(client, me, _image((300, 300), fmt="PNG", mode="RGBA")).json()["url"]
    assert first != second
    assert client.get(first).status_code == 404
    assert client.get(second).status_code == 200


def test_bad_files_and_guessing(client, org_admin, make_employee_login):
    me = make_employee_login(org_admin["headers"])["headers"]
    bad = base64.b64encode(b"<svg onload=alert(1)>" * 5).decode()
    assert _upload(client, me, bad).status_code == 422
    assert _upload(client, me, "pa-base64!!!").status_code == 422
    assert client.get("/api/photos/1.jpg").status_code == 404
    assert client.get("/api/photos/../../etc.jpg").status_code == 404


def test_delete_by_self_and_by_hr(client, org_admin, make_employee_login):
    h = org_admin["headers"]
    worker = make_employee_login(h)
    me, emp_id = worker["headers"], worker["employee"]["id"]

    url = _upload(client, me).json()["url"]
    assert client.delete("/api/profile/photo", headers=me).json() == {"url": None}
    assert client.get(url).status_code == 404

    _upload(client, me)
    other = make_employee_login(h)
    assert client.delete(f"/api/employees/{emp_id}/photo", headers=other["headers"]).status_code == 403
    assert client.delete(f"/api/employees/{emp_id}/photo", headers=h).status_code == 200
    assert client.get("/api/auth/identity", headers=me).json()["photo_url"] is None

    logged = client.get("/api/audit", params={"entity_type": "employee_photo"}, headers=h).json()
    assert len(logged["items"]) >= 3


def test_photos_stay_in_their_business(client, make_org, make_employee_login):
    a, b = make_org(), make_org()
    worker = make_employee_login(a["headers"])
    _upload(client, worker["headers"])

    assert client.get("/api/photos/map", headers=b["headers"]).json()["photos"] == {}
    assert client.delete(f"/api/employees/{worker['employee']['id']}/photo",
                         headers=b["headers"]).status_code == 404
    # Admin san dosye anplwaye pa ka mete foto "pa l".
    assert _upload(client, a["headers"]).status_code in (403, 404)
    assert client.get("/api/photos/map").status_code == 401