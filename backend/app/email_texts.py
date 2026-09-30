"""
Konbit — Tèks imel yo (kreyòl, franse, angle)
Chemen: backend/app/email_texts.py

Lang lan soti nan User.preferred_language. Lòt lang yo (es, pt, de…)
resevwa vèsyon angle a. Non moun nan antre kòm VALÈ nan .format():
yon non ki gen {} pa ka chanje modèl la.
"""

_RESET = {
    "ht": (
        "Chanje modpas KONMBIT ou",
        "Bonjou {name},\n\n"
        "Yon moun mande pou chanje modpas kont KONMBIT ou a. Si se ou, louvri "
        "lyen sa a (li valab {minutes} minit, yon sèl fwa):\n\n"
        "{link}\n\n"
        "Si se pa ou, pa fè anyen: modpas ou pa chanje.\n\n"
        "— KONMBIT",
    ),
    "fr": (
        "Réinitialiser votre mot de passe KONMBIT",
        "Bonjour {name},\n\n"
        "Une demande de réinitialisation du mot de passe de votre compte KONMBIT "
        "a été faite. Si c'est vous, ouvrez ce lien (valable {minutes} minutes, "
        "une seule fois) :\n\n"
        "{link}\n\n"
        "Si ce n'est pas vous, ne faites rien : votre mot de passe reste inchangé.\n\n"
        "— KONMBIT",
    ),
    "en": (
        "Reset your KONMBIT password",
        "Hello {name},\n\n"
        "Someone asked to reset the password of your KONMBIT account. If it was "
        "you, open this link (valid for {minutes} minutes, one use only):\n\n"
        "{link}\n\n"
        "If it wasn't you, do nothing: your password stays the same.\n\n"
        "— KONMBIT",
    ),
}

_VERIFY = {
    "ht": (
        "Verifye imel ou sou KONMBIT",
        "Bonjou {name},\n\n"
        "Mèsi paske w enskri sou KONMBIT. Louvri lyen sa a pou konfime imel ou "
        "(li valab {hours} èdtan):\n\n"
        "{link}\n\n"
        "Si se pa ou ki te enskri, pa fè anyen.\n\n"
        "— KONMBIT",
    ),
    "fr": (
        "Vérifiez votre e-mail sur KONMBIT",
        "Bonjour {name},\n\n"
        "Merci de vous être inscrit sur KONMBIT. Ouvrez ce lien pour confirmer "
        "votre adresse e-mail (valable {hours} heures) :\n\n"
        "{link}\n\n"
        "Si vous n'êtes pas à l'origine de cette inscription, ne faites rien.\n\n"
        "— KONMBIT",
    ),
    "en": (
        "Verify your email on KONMBIT",
        "Hello {name},\n\n"
        "Thank you for signing up for KONMBIT. Open this link to confirm your "
        "email address (valid for {hours} hours):\n\n"
        "{link}\n\n"
        "If you did not sign up, do nothing.\n\n"
        "— KONMBIT",
    ),
}


def _lang(code: str | None) -> str:
    return code if code in ("ht", "fr", "en") else "en"


def _first_name(full_name: str | None) -> str:
    parts = (full_name or "").split()
    return parts[0] if parts else ""


def reset_email_text(lang: str | None, full_name: str | None, link: str, minutes: int) -> tuple[str, str]:
    subject, body = _RESET[_lang(lang)]
    return subject, body.format(name=_first_name(full_name), link=link, minutes=minutes)


def verify_email_text(lang: str | None, full_name: str | None, link: str, hours: int) -> tuple[str, str]:
    subject, body = _VERIFY[_lang(lang)]
    return subject, body.format(name=_first_name(full_name), link=link, hours=hours)