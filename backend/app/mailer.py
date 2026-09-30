"""
Konbit — Voye imel
Chemen: backend/app/mailer.py

Twa mòd (settings.mail_backend / varyab MAIL_BACKEND):
  console : ekri imel la nan jounal sèvè a (devlopman) — anyen pa pati.
  memory  : sere l nan OUTBOX (tès yo li l).
  smtp    : voye l vre. Zoho Mail, ZeptoMail, Resend… tout aksepte SMTP.
            Obligatwa nan pwodiksyon (config.py refize demare otreman).

Router yo rele send_email ak BackgroundTasks: repons API a pa tann sèvè
SMTP a, e yon echèk SMTP pa kraze rekèt la — li ekri nan jounal la.
Tèks sèlman (pa HTML): pi senp, e pa gen risk enjeksyon ak non moun yo.
"""

import logging
import smtplib
import ssl
from dataclasses import dataclass
from email.message import EmailMessage
from email.utils import formatdate, make_msgid, parseaddr

from .config import settings

logger = logging.getLogger("konbit")


@dataclass
class SentEmail:
    to: str
    subject: str
    text: str


# Mòd "memory" sèlman (tès yo).
OUTBOX: list[SentEmail] = []


def send_email(to: str, subject: str, text: str) -> None:
    backend = settings.mail_backend

    if backend == "memory":
        OUTBOX.append(SentEmail(to=to, subject=subject, text=text))
        return

    if backend == "console":
        logger.info("IMEL (console, pa voye) -> %s | %s\n%s", to, subject, text)
        return

    msg = EmailMessage()
    msg["From"] = settings.mail_from
    msg["To"] = to
    msg["Subject"] = subject
    msg["Date"] = formatdate(localtime=False)
    sender_domain = parseaddr(settings.mail_from)[1].rpartition("@")[2] or None
    msg["Message-ID"] = make_msgid(domain=sender_domain)
    msg.set_content(text)

    context = ssl.create_default_context()
    try:
        if settings.smtp_starttls:           # pò 587
            with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=20) as smtp:
                smtp.starttls(context=context)
                smtp.login(settings.smtp_user, settings.smtp_password)
                smtp.send_message(msg)
        else:                                # pò 465 (SSL dirèk)
            with smtplib.SMTP_SSL(settings.smtp_host, settings.smtp_port,
                                  context=context, timeout=20) as smtp:
                smtp.login(settings.smtp_user, settings.smtp_password)
                smtp.send_message(msg)
    except Exception:
        # Pa janm ekri modpas SMTP a; to ak sijè a ase pou jwenn pwoblèm lan.
        logger.exception("Imel pa pati: %s | %s", to, subject)
        