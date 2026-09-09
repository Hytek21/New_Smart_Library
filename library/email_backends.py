"""Send email via the Resend HTTP API instead of SMTP.

Why this exists: Render (and most PaaS free tiers) block or silently hang
outbound SMTP connections (ports 25/465/587) to fight spam abuse. A raw
smtplib.connect() call doesn't get refused — it just hangs until gunicorn's
own worker-timeout kills the whole process with SIGKILL, which even wraps
around a bare `except Exception` (a SIGKILL-triggered SystemExit isn't a
subclass of Exception). Resend's API is a normal HTTPS POST on port 443,
so it isn't affected by that blocking.

Because this is a Django EMAIL_BACKEND, every existing call to send_mail()
or EmailMultiAlternatives.send() — including Django's own built-in password
reset emails — routes through here automatically. Nothing else in the
codebase needs to change.
"""

import requests
from django.conf import settings
from django.core.mail.backends.base import BaseEmailBackend


class ResendEmailBackend(BaseEmailBackend):
    def send_messages(self, email_messages):
        if not email_messages:
            return 0

        sent_count = 0
        for message in email_messages:
            payload = {
                'from': message.from_email,
                'to': list(message.to),
                'subject': message.subject,
                'text': message.body,
            }

            # EmailMultiAlternatives (used for the HTML borrow/return
            # notifications) stores extra bodies in .alternatives as
            # (content, mimetype) tuples.
            html_body = None
            for content, mimetype in getattr(message, 'alternatives', []) or []:
                if mimetype == 'text/html':
                    html_body = content
                    break
            if html_body:
                payload['html'] = html_body

            if message.cc:
                payload['cc'] = list(message.cc)
            if message.bcc:
                payload['bcc'] = list(message.bcc)

            try:
                response = requests.post(
                    'https://api.resend.com/emails',
                    headers={
                        'Authorization': f'Bearer {settings.RESEND_API_KEY}',
                        'Content-Type': 'application/json',
                    },
                    json=payload,
                    timeout=10,
                )
                response.raise_for_status()
                sent_count += 1
            except Exception:
                if not self.fail_silently:
                    raise

        return sent_count
