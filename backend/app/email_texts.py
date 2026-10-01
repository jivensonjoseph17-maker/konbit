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


# ---------------------------------------------------------------------------
# ESPAS KANDIDA (routers/candidate.py, routers/offers.py)
# ---------------------------------------------------------------------------

_ACCOUNT_EXISTS = {
    "ht": (
        "Ou deja gen yon kont KONMBIT",
        "Bonjou {name},\n\n"
        "Yon moun eseye kreye yon kont KONMBIT ak imel sa a, men ou deja gen "
        "yon kont. Konekte ak li. Si w bliye modpas ou, louvri lyen sa a:\n\n"
        "{link}\n\n"
        "Si se pa ou, pa fè anyen: kont ou pa chanje.\n\n"
        "— KONMBIT",
    ),
    "fr": (
        "Vous avez déjà un compte KONMBIT",
        "Bonjour {name},\n\n"
        "Quelqu'un a essayé de créer un compte KONMBIT avec cet e-mail, mais vous "
        "avez déjà un compte. Connectez-vous avec celui-ci. Si vous avez oublié "
        "votre mot de passe, ouvrez ce lien :\n\n"
        "{link}\n\n"
        "Si ce n'est pas vous, ne faites rien : votre compte reste inchangé.\n\n"
        "— KONMBIT",
    ),
    "en": (
        "You already have a KONMBIT account",
        "Hello {name},\n\n"
        "Someone tried to create a KONMBIT account with this email, but you "
        "already have one. Sign in with it. If you forgot your password, open "
        "this link:\n\n"
        "{link}\n\n"
        "If it wasn't you, do nothing: your account stays the same.\n\n"
        "— KONMBIT",
    ),
}

_OFFER_SENT = {
    "ht": (
        "Pwopozisyon travay: {job}",
        "Bonjou {name},\n\n"
        "{company} voye yon pwopozisyon travay ba ou pou pòs \"{job}\". "
        "Konekte nan espas kandida KONMBIT ou pou w wè detay yo epi reponn:\n\n"
        "{link}\n\n"
        "Si w poko gen kont, kreye youn ak imel sa a ({email}): pwopozisyon an "
        "ap parèt otomatikman.\n\n"
        "— KONMBIT",
    ),
    "fr": (
        "Offre d'emploi : {job}",
        "Bonjour {name},\n\n"
        "{company} vous a envoyé une offre d'emploi pour le poste « {job} ». "
        "Connectez-vous à votre espace candidat KONMBIT pour voir les détails et "
        "répondre :\n\n"
        "{link}\n\n"
        "Si vous n'avez pas encore de compte, créez-en un avec cet e-mail ({email}) : "
        "l'offre apparaîtra automatiquement.\n\n"
        "— KONMBIT",
    ),
    "en": (
        "Job offer: {job}",
        "Hello {name},\n\n"
        "{company} sent you a job offer for the \"{job}\" position. Sign in to "
        "your KONMBIT candidate space to see the details and respond:\n\n"
        "{link}\n\n"
        "If you don't have an account yet, create one with this email ({email}): "
        "the offer will appear automatically.\n\n"
        "— KONMBIT",
    ),
}


def _one_line(text: str | None) -> str:
    """Pa gen retou alaliy nan yon sijè imel (sa ta kase header yo)."""
    return " ".join((text or "").split())


def account_exists_text(lang: str | None, full_name: str | None, link: str) -> tuple[str, str]:
    subject, body = _ACCOUNT_EXISTS[_lang(lang)]
    return subject, body.format(name=_first_name(full_name), link=link)


def offer_sent_text(lang: str | None, full_name: str | None, company: str, job_title: str,
                    link: str, email: str) -> tuple[str, str]:
    subject, body = _OFFER_SENT[_lang(lang)]
    job = _one_line(job_title)
    return subject.format(job=job), body.format(
        name=_first_name(full_name), company=_one_line(company), job=job, link=link, email=email,
    )
