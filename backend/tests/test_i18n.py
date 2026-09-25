"""
Konbit — Tès lang (kreyòl, franse, angle)
Chemen: backend/tests/test_i18n.py
"""

from app.i18n import (
    requested_language,
    resolve_language,
    translate,
    translate_detail,
    validation_message,
)


# ---------------------------------------------------------------------------
# FONKSYON YO
# ---------------------------------------------------------------------------

def test_resolve_language():
    assert resolve_language(None) == "ht"
    assert resolve_language("") == "ht"
    assert resolve_language("fr") == "fr"
    assert resolve_language("fr-FR,fr;q=0.9,en;q=0.8") == "fr"
    assert resolve_language("en-US") == "en"
    assert resolve_language("es-ES,es;q=0.9") == "ht"
    assert resolve_language("es, en") == "en"


def test_requested_language_keeps_ui_languages():
    # Backend la pa gen mesaj an panyòl, men kont lan ka an panyòl.
    assert resolve_language("es, en;q=0.5") == "en"
    assert requested_language("es, en;q=0.5") == "es"
    assert requested_language("zh-CN,zh;q=0.9") == "zh"
    assert requested_language("xx, yy") == "ht"
    assert requested_language(None) == "ht"


def test_translate_fixed_message():
    msg = "Imel oswa modpas la pa kòrèk."
    assert translate(msg, "ht") == msg
    assert translate(msg, "fr") == "L'e-mail ou le mot de passe est incorrect."
    assert translate(msg, "en") == "The email or password is incorrect."


def test_unknown_message_stays_in_creole():
    msg = "Yon mesaj ki pa nan katalòg la."
    assert translate(msg, "fr") == msg
    assert translate(msg, "en") == msg


def test_translate_pattern_keeps_value():
    msg = "Idantifyan 'boulanjri-jak' la deja pran. Chwazi yon lòt."
    assert translate(msg, "en") == "The identifier 'boulanjri-jak' is already taken. Choose another one."


def test_translate_list_detail():
    detail = ["Modpas la dwe gen omwen 10 karaktè.", "Modpas la dwe gen omwen yon chif."]
    assert translate_detail(detail, "fr") == [
        "Le mot de passe doit contenir au moins 10 caractères.",
        "Le mot de passe doit contenir au moins un chiffre.",
    ]


def test_pydantic_messages_are_replaced_even_in_creole():
    err = {"type": "missing", "msg": "Field required"}
    assert validation_message(err, "ht") == "Jaden sa a obligatwa."
    err = {"type": "string_too_short", "msg": "...", "ctx": {"min_length": 3}}
    assert validation_message(err, "en") == "At least 3 characters."


def test_value_error_prefix_is_removed_and_translated():
    err = {"type": "value_error", "msg": "Value error, Dat nesans lan pa sanble kòrèk."}
    assert validation_message(err, "ht") == "Dat nesans lan pa sanble kòrèk."
    assert validation_message(err, "en") == "The date of birth does not look correct."


def test_value_words_are_translated_inside_patterns():
    msg = "Ou pa ka pase de 'hired' a 'received'. Etap ki posib: okenn."
    assert translate(msg, "en") == "You cannot move from 'hired' to 'received'. Possible steps: none."


def test_application_answer_problems_are_translated_piece_by_piece():
    msg = ("Kesyon obligatwa ki manke: «Vil oswa komin», «Lang». "
           "«Laj»: mete yon chif. «Èske w gen lisans?»: reponn wi oswa non.")
    assert translate(msg, "fr") == (
        "Questions obligatoires manquantes : «Vil oswa komin», «Lang». "
        "«Laj»: saisissez un nombre. «Èske w gen lisans?»: répondez oui ou non."
    )
    assert translate("«Non»: repons lan twò long (300 karaktè maksimòm).", "en") == (
        "«Non»: the answer is too long (300 characters maximum)."
    )


def test_every_row_has_both_translations():
    from app.i18n import _ROWS
    for ht, fr, en in _ROWS:
        assert ht and fr and en, ht
    assert len({row[0] for row in _ROWS}) == len(_ROWS), "gen yon mesaj kreyòl ki repete"


# ---------------------------------------------------------------------------
# API A
# ---------------------------------------------------------------------------

def _bad_login(client, email, lang=None):
    headers = {"Accept-Language": lang} if lang else {}
    return client.post(
        "/api/auth/login",
        json={"email": email, "password": "modpasfalspaseditou"},
        headers=headers,
    )


def test_login_error_follows_accept_language(client, org_admin):
    ht = _bad_login(client, org_admin["email"])
    fr = _bad_login(client, org_admin["email"], "fr")
    en = _bad_login(client, org_admin["email"], "en-US,en;q=0.9")

    assert ht.status_code == fr.status_code == en.status_code == 401
    assert ht.json()["detail"] == "Imel oswa modpas la pa kòrèk."
    assert fr.json()["detail"] == "L'e-mail ou le mot de passe est incorrect."
    assert en.json()["detail"] == "The email or password is incorrect."
    # Header yo pa dwe pèdi nan tradiksyon an.
    assert en.headers.get("www-authenticate") == "Bearer"


def test_unknown_route_is_translated(client):
    resp = client.get("/api/pa-egziste-ditou")
    assert resp.status_code == 404
    assert resp.json()["detail"] == "Sa ou chèche a pa egziste."

    resp = client.get("/api/pa-egziste-ditou", headers={"Accept-Language": "fr"})
    assert resp.json()["detail"] == "La ressource demandée n'existe pas."


def test_update_preferred_language(client, make_org):
    org = make_org()
    resp = client.patch("/api/auth/me", json={"preferred_language": "fr"}, headers=org["headers"])
    assert resp.status_code == 200
    assert resp.json()["preferred_language"] == "fr"

    identity = client.get("/api/auth/identity", headers=org["headers"]).json()
    assert identity["user"]["preferred_language"] == "fr"


def test_ui_language_without_backend_catalog_is_accepted(client, make_org):
    org = make_org()
    resp = client.patch("/api/auth/me", json={"preferred_language": "es"}, headers=org["headers"])
    assert resp.status_code == 200
    assert resp.json()["preferred_language"] == "es"


def test_unknown_language_is_rejected(client, make_org):
    org = make_org()
    headers = {**org["headers"], "Accept-Language": "en"}
    resp = client.patch("/api/auth/me", json={"preferred_language": "xx"}, headers=headers)
    assert resp.status_code == 422
    body = resp.json()
    assert body["detail"] == "The data you sent is not valid."
    assert body["errors"][0]["field"] == "preferred_language"
    assert body["errors"][0]["message"] == "This language is not available."


def test_null_name_does_not_crash(client, make_org):
    org = make_org()
    before = client.get("/api/auth/me", headers=org["headers"]).json()["full_name"]
    resp = client.patch("/api/auth/me", json={"full_name": None}, headers=org["headers"])
    assert resp.status_code == 200
    assert resp.json()["full_name"] == before


def test_signup_uses_header_language_and_translates_password_rules(client):
    payload = {
        "organization": {
            "name": "Biznis Lang",
            "slug": "biznis-lang-test",
            "country": "HT",
            "default_currency": "HTG",
        },
        "admin_full_name": "Admin Lang",
        "admin_email": "lang@konbit-test.ht",
        "admin_password": "sanchifditoumenmyon",
    }

    weak = client.post("/api/auth/signup", json=payload, headers={"Accept-Language": "fr"})
    assert weak.status_code == 422
    assert "Le mot de passe doit contenir au moins un chiffre." in weak.json()["detail"]

    payload["admin_password"] = "TestPassw0rd2026"
    # Konsa api.js voye l pou yon moun ki chwazi panyòl.
    ok = client.post("/api/auth/signup", json=payload, headers={"Accept-Language": "es, en;q=0.5"})
    assert ok.status_code == 201
    token = ok.json()["access_token"]
    me = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"}).json()
    assert me["preferred_language"] == "es"