from __future__ import annotations

import os
import smtplib
from email.message import EmailMessage


def maybe_send_email(subject: str, body: str) -> bool:
    host = os.getenv('MONITOR_SMTP_HOST')
    port = os.getenv('MONITOR_SMTP_PORT')
    username = os.getenv('MONITOR_SMTP_USERNAME')
    password = os.getenv('MONITOR_SMTP_PASSWORD')
    sender = os.getenv('MONITOR_EMAIL_FROM')
    recipient = os.getenv('MONITOR_EMAIL_TO')
    if not all([host, port, sender, recipient]):
        return False
    message = EmailMessage()
    message['Subject'] = subject
    message['From'] = sender
    message['To'] = recipient
    message.set_content(body)
    with smtplib.SMTP(host, int(port), timeout=30) as smtp:
        smtp.starttls()
        if username and password:
            smtp.login(username, password)
        smtp.send_message(message)
    return True
