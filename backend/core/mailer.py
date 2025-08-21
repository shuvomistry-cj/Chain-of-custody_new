import smtplib
from email.message import EmailMessage
from typing import Optional

import requests

from .config import settings


def _send_via_smtp(subject: str, to_email: str, body: str) -> Optional[str]:
    host = settings.smtp_host
    port = settings.smtp_port
    username = settings.smtp_username
    password = settings.smtp_password
    mail_from = settings.mail_from or (username or "noreply@example.com")

    if not host or not port or not username or not password:
        return "SMTP not configured"

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = mail_from
    msg["To"] = to_email
    msg.set_content(body)

    try:
        with smtplib.SMTP(host, port) as server:
            if settings.smtp_use_tls:
                server.starttls()
            server.login(username, password)
            server.send_message(msg)
        return None
    except Exception as e:
        return str(e)


def _send_via_formspree(subject: str, to_email: str, body: str) -> Optional[str]:
    form_id = settings.formspree_form_id
    if not form_id:
        return "FORMSPREE not configured"
    url = f"https://formspree.io/f/{form_id}"
    # Formspree typically emails the form owner. Some plans allow custom recipient routing.
    # Include the target recipient in payload for templates/routing rules.
    payload = {
        "_subject": subject,
        "to": to_email,
        "message": body,
    }
    headers = {"Accept": "application/json"}
    if settings.formspree_api_key:
        headers["Authorization"] = f"Bearer {settings.formspree_api_key}"
    try:
        resp = requests.post(url, data=payload, headers=headers, timeout=10)
        if resp.status_code in (200, 202):
            return None
        else:
            return f"Formspree error: {resp.status_code} {resp.text}"
    except Exception as e:
        return str(e)


def send_mail(subject: str, to_email: str, body: str) -> Optional[str]:
    """
    Send an email via SMTP if configured; otherwise try Formspree; otherwise return a helpful error.
    Returns None on success, or an error string.
    """
    # Try SMTP first
    smtp_err = _send_via_smtp(subject, to_email, body)
    if smtp_err is None:
        return None
    # If SMTP not configured, try Formspree
    if smtp_err == "SMTP not configured":
        fs_err = _send_via_formspree(subject, to_email, body)
        if fs_err is None:
            return None
        if fs_err == "FORMSPREE not configured":
            return "SMTP not configured"
        return fs_err
    # SMTP attempted but failed for another reason
    return smtp_err
