"""Send email through the Resend HTTP API.

This is the only part of the server that needs a credential. The key is read
through config.py (which loads .env with pathlib), never hard-coded and never
taken from the ambient shell environment.

Request shape and the Bearer-token header follow the Resend API reference:
https://resend.com/docs/api-reference/emails/send-email
"""

import httpx

from paper_server.config import get

RESEND_API_URL = "https://api.resend.com/emails"
REQUEST_TIMEOUT = 20.0

DEFAULT_SENDER = "onboarding@resend.dev"


class EmailNotConfigured(RuntimeError):
    """Raised when no API key is present, so the caller can fall back gracefully."""


def is_configured() -> bool:
    """True when an API key is available. Used to decide whether to try sending."""
    return bool(get("RESEND_API_KEY"))


def send(recipient: str, subject: str, body: str) -> str:
    """Send a plain-text email. Returns Resend's message id.

    Raises EmailNotConfigured if no key is set, or httpx.HTTPError on a
    transport or status failure. The key itself never appears in either.
    """
    api_key = get("RESEND_API_KEY")
    if not api_key:
        raise EmailNotConfigured(
            "RESEND_API_KEY is not set in .env, so no email was sent."
        )

    response = httpx.post(
        RESEND_API_URL,
        headers={
            # The credential travels in a header, not in the URL, so it stays
            # out of logs, error messages and anything that echoes a request URL.
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        json={
            "from": get("RESEND_SENDER", DEFAULT_SENDER),
            "to": [recipient],
            "subject": subject,
            "text": body,
        },
        timeout=REQUEST_TIMEOUT,
    )
    response.raise_for_status()
    return response.json().get("id", "")
