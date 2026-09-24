"""
Konbit — Tès kesyon fòm aplikasyon
Chemen: backend/tests/test_application_questions.py
"""

import uuid

import pytest


def _published_job(client, org, title=None):
    job = client.post("/api/jobs", json={
        "title": title or f"Pòs {uuid.uuid4().hex[:6]}", "description": "Deskripsyon.",
    }, headers=org["headers"]).json()
    resp = client.post(f"/api/jobs/{job['id']}/publish", json={}, headers=org["headers"])
    assert resp.status_code == 200, resp.text
    return job


def _public_questions(client, org, job):
    resp = client.get(f"/api/application-questions/public/{org['org_slug']}/{job['slug']}")
    assert resp.status_code == 200, resp.text
    return resp.json()["items"]


def _by_key(questions, key):
    return next(q for q in questions if q["key"] == key)


def _apply(client, org, job, answers, email=None):
    return client.post(
        f"/api/applications/public/{org['org_slug']}/{job['slug']}",
        json={
            "full_name": "Kandida Tès",
            "email": email or f"k-{uuid.uuid4().hex[:8]}@konbit-test.ht",
            "answers": answers,
        },
    )


# ---------------------------------------------------------------------------
# KESYON PA DEFO
# ---------------------------------------------------------------------------

def test_default_questions_created_once(client, org_admin):
    first = client.get("/api/application-questions", headers=org_admin["headers"])
    assert first.status_code == 200, first.text
    keys = {q["key"] for q in first.json()["items"]}
    assert {"city", "worked_here_before", "worked_here_left_reason", "languages"} <= keys

    second = client.get("/api/application-questions", headers=org_admin["headers"])
    assert len(second.json()["items"]) == len(first.json()["items"])


def test_default_question_cannot_be_deleted_but_can_be_disabled(client, org_admin):
    h = org_admin["headers"]
    items = client.get("/api/application-questions", headers=h).json()["items"]
    address = next(q for q in items if q["key"] == "address")

    assert client.delete(f"/api/application-questions/{address['id']}", headers=h).status_code == 400

    resp = client.patch(f"/api/application-questions/{address['id']}",
                        json={"is_active": False}, headers=h)
    assert resp.status_code == 200
    job = _published_job(client, org_admin)
    assert "address" not in {q["key"] for q in _public_questions(client, org_admin, job)}


# ---------------------------------------------------------------------------
# VALIDASYON REPONS YO
# ---------------------------------------------------------------------------

def test_apply_without_required_answers_is_rejected(client, org_admin):
    job = _published_job(client, org_admin)
    resp = _apply(client, org_admin, job, answers={})
    assert resp.status_code == 422
    assert "Vil oswa komin" in resp.json()["detail"]


def test_left_reason_required_only_if_worked_here_before(
    client, org_admin, application_answers,
):
    job = _published_job(client, org_admin)
    questions = _public_questions(client, org_admin, job)
    reason = _by_key(questions, "worked_here_left_reason")

    # Te travay isit, men pa bay rezon an: refize
    answers = application_answers(org_admin["org_slug"], job["slug"], worked_here_before=True)
    assert _apply(client, org_admin, job, answers).status_code == 422

    # Ak rezon an: aksepte
    answers[str(reason["id"])] = "Mwen te retounen lekòl."
    assert _apply(client, org_admin, job, answers).status_code == 201


def test_hidden_answer_is_not_saved(client, org_admin, application_answers):
    """Si 'Te travay isit?' = non, yon rezon voye kanmenm pa dwe sere."""
    job = _published_job(client, org_admin)
    reason = _by_key(_public_questions(client, org_admin, job), "worked_here_left_reason")

    answers = application_answers(org_admin["org_slug"], job["slug"], worked_here_before=False)
    answers[str(reason["id"])] = "Tèks ki pa ta dwe sere"
    resp = _apply(client, org_admin, job, answers)
    assert resp.status_code == 201

    detail = client.get(f"/api/applications/{resp.json()['application_id']}",
                        headers=org_admin["headers"]).json()
    labels = [a["label"] for a in detail["answers"]]
    assert reason["label"] not in labels


@pytest.mark.parametrize("key, bad_value", [
    ("languages", ["Kreyòl", "Klingon"]),
    ("education_level", "Doktora sou lalin"),
    ("years_experience", "anpil"),
    ("available_from", "demen"),
])
def test_invalid_answers_are_rejected(client, org_admin, application_answers, key, bad_value):
    job = _published_job(client, org_admin)
    answers = application_answers(org_admin["org_slug"], job["slug"], **{key: bad_value})
    assert _apply(client, org_admin, job, answers).status_code == 422


def test_answers_keep_question_text_from_when_they_applied(
    client, org_admin, application_answers,
):
    h = org_admin["headers"]
    job = _published_job(client, org_admin)
    city = _by_key(_public_questions(client, org_admin, job), "city")

    answers = application_answers(org_admin["org_slug"], job["slug"], city="Jakmèl")
    app_id = _apply(client, org_admin, job, answers).json()["application_id"]

    client.patch(f"/api/application-questions/{city['id']}",
                 json={"label": "Nan ki depatman w rete?"}, headers=h)

    detail = client.get(f"/api/applications/{app_id}", headers=h).json()
    answer = next(a for a in detail["answers"] if a["question_id"] == city["id"])
    assert answer["label"] == "Vil oswa komin"
    assert answer["value"] == "Jakmèl"
    assert answer["section_label"] == "Enfòmasyon pèsonèl"


# ---------------------------------------------------------------------------
# KESYON PÈSONALIZE
# ---------------------------------------------------------------------------

def test_custom_question_for_one_job_only(client, org_admin):
    h = org_admin["headers"]
    driver = _published_job(client, org_admin, title="Chofè")
    cashier = _published_job(client, org_admin, title="Kesye Tès")

    resp = client.post("/api/application-questions", json={
        "label": "Èske w gen yon lisans kondi valab?",
        "question_type": "yes_no",
        "is_required": True,
        "job_posting_id": driver["id"],
    }, headers=h)
    assert resp.status_code == 201, resp.text
    qid = resp.json()["id"]

    assert qid in {q["id"] for q in _public_questions(client, org_admin, driver)}
    assert qid not in {q["id"] for q in _public_questions(client, org_admin, cashier)}


def test_choice_question_needs_options(client, org_admin):
    resp = client.post("/api/application-questions", json={
        "label": "Ki zòn?", "question_type": "single_choice", "options": ["Nò"],
    }, headers=org_admin["headers"])
    assert resp.status_code == 422


def test_sensitive_answer_hidden_from_manager(
    client, org_admin, application_answers, make_employee_login,
):
    h = org_admin["headers"]
    job = _published_job(client, org_admin)
    resp = client.post("/api/application-questions", json={
        "label": "Èske w te janm kondane pou yon krim?",
        "question_type": "yes_no",
        "is_sensitive": True,
        "section": "other",
    }, headers=h)
    qid = resp.json()["id"]

    answers = application_answers(org_admin["org_slug"], job["slug"])
    answers[str(qid)] = False
    app_id = _apply(client, org_admin, job, answers).json()["application_id"]

    hr_view = client.get(f"/api/applications/{app_id}", headers=h).json()
    assert qid in {a["question_id"] for a in hr_view["answers"]}

    manager = make_employee_login(h, login_role="manager")
    mgr_resp = client.get(f"/api/applications/{app_id}", headers=manager["headers"])
    assert mgr_resp.status_code == 200, mgr_resp.text
    assert qid not in {a["question_id"] for a in mgr_resp.json()["answers"]}


def test_question_with_answers_cannot_be_deleted(client, org_admin, application_answers):
    h = org_admin["headers"]
    job = _published_job(client, org_admin)
    qid = client.post("/api/application-questions", json={
        "label": "Ki machin ou konn kondi?", "question_type": "short_text",
    }, headers=h).json()["id"]

    answers = application_answers(org_admin["org_slug"], job["slug"])
    answers[str(qid)] = "Kamyon"
    assert _apply(client, org_admin, job, answers).status_code == 201

    assert client.delete(f"/api/application-questions/{qid}", headers=h).status_code == 400


def test_other_org_cannot_touch_questions(client, make_org):
    org_a, org_b = make_org(), make_org()
    qid = client.post("/api/application-questions", json={
        "label": "Kesyon biznis A", "question_type": "short_text",
    }, headers=org_a["headers"]).json()["id"]

    assert client.patch(f"/api/application-questions/{qid}", json={"label": "Hack"},
                        headers=org_b["headers"]).status_code == 404
    assert client.delete(f"/api/application-questions/{qid}",
                         headers=org_b["headers"]).status_code == 404
    listed = client.get("/api/application-questions", headers=org_b["headers"]).json()["items"]
    assert qid not in {q["id"] for q in listed}
