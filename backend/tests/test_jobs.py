"""
Konbit — Tès Rekritman (òf travay)
Chemen: backend/tests/test_jobs.py
"""


def test_create_job_starts_as_draft(client, org_admin):
    resp = client.post("/api/jobs", json={"title": "Kesye"}, headers=org_admin["headers"])
    assert resp.status_code == 201
    body = resp.json()
    assert body["status"] == "draft"
    assert body["slug"]


def test_cannot_publish_without_description(client, org_admin):
    job = client.post("/api/jobs", json={"title": "San Deskripsyon"},
                       headers=org_admin["headers"]).json()

    resp = client.post(f"/api/jobs/{job['id']}/publish", json={},
                        headers=org_admin["headers"])
    assert resp.status_code == 400


def test_publish_after_adding_description(client, org_admin):
    job = client.post("/api/jobs", json={"title": "Enjenyè"},
                       headers=org_admin["headers"]).json()

    client.patch(f"/api/jobs/{job['id']}", json={"description": "Yon bon travay."},
                 headers=org_admin["headers"])

    resp = client.post(f"/api/jobs/{job['id']}/publish", json={},
                        headers=org_admin["headers"])
    assert resp.status_code == 200
    assert resp.json()["status"] == "published"


def test_close_then_reopen_job(client, org_admin):
    job = client.post("/api/jobs", json={
        "title": "Kòmi", "description": "Deskripsyon.",
    }, headers=org_admin["headers"]).json()
    client.post(f"/api/jobs/{job['id']}/publish", json={}, headers=org_admin["headers"])

    closed = client.post(f"/api/jobs/{job['id']}/close", json={"reject_pending": False},
                          headers=org_admin["headers"])
    assert closed.status_code == 200
    assert closed.json()["job"]["status"] == "closed"

    reopened = client.post(f"/api/jobs/{job['id']}/reopen", json={},
                            headers=org_admin["headers"])
    assert reopened.status_code == 200
    assert reopened.json()["status"] == "published"


def test_cannot_reopen_a_job_that_is_not_closed(client, org_admin):
    job = client.post("/api/jobs", json={"title": "Bouyon"},
                       headers=org_admin["headers"]).json()

    resp = client.post(f"/api/jobs/{job['id']}/reopen", json={},
                        headers=org_admin["headers"])
    assert resp.status_code == 400


def test_list_jobs_filters_by_status(client, org_admin):
    client.post("/api/jobs", json={"title": "Bouyon A"}, headers=org_admin["headers"])
    published = client.post("/api/jobs", json={
        "title": "Pibliye A", "description": "OK",
    }, headers=org_admin["headers"]).json()
    client.post(f"/api/jobs/{published['id']}/publish", json={}, headers=org_admin["headers"])

    resp = client.get("/api/jobs", params={"status": "published"}, headers=org_admin["headers"])
    assert resp.status_code == 200
    titles = [j["title"] for j in resp.json()["items"]]
    assert "Pibliye A" in titles
    assert "Bouyon A" not in titles


def test_patch_cannot_change_status(client, org_admin):
    # San pwoteksyon sa a, PATCH ta pibliye yon òf san deskripsyon
    job = client.post("/api/jobs", json={"title": "Kontoune"},
                       headers=org_admin["headers"]).json()

    resp = client.patch(f"/api/jobs/{job['id']}", json={"status": "published"},
                         headers=org_admin["headers"])
    assert resp.status_code == 400

    again = client.get(f"/api/jobs/{job['id']}", headers=org_admin["headers"]).json()
    assert again["status"] == "draft"


def test_patch_rejects_zero_openings(client, org_admin):
    job = client.post("/api/jobs", json={"title": "Zewo Pòs"},
                       headers=org_admin["headers"]).json()

    resp = client.patch(f"/api/jobs/{job['id']}", json={"openings": 0},
                         headers=org_admin["headers"])
    assert resp.status_code == 400


def test_careers_link_gives_org_slug(client, org_admin):
    resp = client.get("/api/jobs/careers-link", headers=org_admin["headers"])
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["org_slug"] == org_admin["org_slug"]
    assert body["path"] == f"careers.html?org={org_admin['org_slug']}"


def test_public_salary_only_when_show_salary(client, org_admin):
    h = org_admin["headers"]
    slug = org_admin["org_slug"]

    hidden = client.post("/api/jobs", json={
        "title": "Salè Kache", "description": "OK",
        "salary_min": 2_500_000, "salary_max": 3_500_000, "show_salary": False,
    }, headers=h).json()
    shown = client.post("/api/jobs", json={
        "title": "Salè Vizib", "description": "OK",
        "salary_min": 2_500_000, "salary_max": 3_500_000, "show_salary": True,
    }, headers=h).json()
    for job in (hidden, shown):
        client.post(f"/api/jobs/{job['id']}/publish", json={}, headers=h)

    pub_hidden = client.get(f"/api/jobs/public/{slug}/{hidden['slug']}").json()
    assert pub_hidden["salary_min"] is None and pub_hidden["salary_max"] is None

    pub_shown = client.get(f"/api/jobs/public/{slug}/{shown['slug']}").json()
    assert pub_shown["salary_min"] == 2_500_000
    assert pub_shown["salary_max"] == 3_500_000
    assert pub_shown["currency"] == "HTG"