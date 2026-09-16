"""Safe error reporting.

Best practice #2 for this assignment.

A raw traceback is useful to a developer and dangerous to everyone else: it
carries absolute filesystem paths, library versions, and - when a request
object is involved - query strings that can contain API keys. Anything returned
from a tool goes into the LLM's context and is shown to the user, so none of
that should leave the server.

The pattern here: log the full exception to a local file, hand the caller a
short generic message plus a reference code, and let the operator match the two
up in the log.

Important detail specific to MCP: a stdio server uses stdout for JSON-RPC
messages. Writing a log line to stdout corrupts the protocol stream, so the
handler below writes to a file and nothing else.
"""

import logging
import re
import uuid
from pathlib import Path

LOG_PATH = Path(__file__).resolve().parent.parent / "data" / "server.log"

logger = logging.getLogger("paper_server")


def configure_logging() -> None:
    """Attach a file handler once. Safe to call more than once."""
    if logger.handlers:
        return
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    handler = logging.FileHandler(LOG_PATH, encoding="utf-8")
    handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)s %(message)s")
    )
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    logger.propagate = False  # keep records off the root logger's stdout handler


def safe_error(action: str, exc: Exception) -> str:
    """Log the real exception, return a message that is safe to show the user."""
    configure_logging()
    reference = uuid.uuid4().hex[:8]
    # exc_info takes the exception object explicitly. logger.exception() would
    # read the *currently handled* exception instead, which is empty unless this
    # is called from inside an except block - and a silently missing traceback
    # would defeat the point of logging at all.
    logger.error("[%s] %s failed", reference, action, exc_info=exc)
    return (
        f"{action} could not be completed. "
        f"Reference code {reference} - the server operator can look this up in the log."
    )


# --------------------------------------------------------- input validation

class InvalidInput(ValueError):
    """Raised when an argument fails validation before it reaches any backend."""


# Deliberately stricter than the full RFC 5322 grammar. A narrow allowlist of
# characters is easier to reason about than a pattern that tries to permit
# everything the standard allows, and it rejects the whole class of attacks
# below rather than a list of known-bad strings.
_EMAIL_PATTERN = re.compile(r"^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$")

MAX_EMAIL_LENGTH = 254  # RFC 5321 limit on a forward path


def validate_email(address: str) -> str:
    """Return the address unchanged, or raise InvalidInput.

    The attack this blocks is header injection: a newline inside a recipient
    lets an attacker append their own mail headers, so a request to send one
    person a bibliography quietly grows a "Bcc:" line. Control characters are
    rejected before the pattern is even tried, so a multi-line value can never
    match on its first line alone.
    """
    if not isinstance(address, str) or not address:
        raise InvalidInput("Recipient address is required.")
    if len(address) > MAX_EMAIL_LENGTH:
        raise InvalidInput("Recipient address is too long.")
    if any(char in address for char in "\r\n\t\0"):
        raise InvalidInput("Recipient address contains illegal control characters.")
    if not _EMAIL_PATTERN.fullmatch(address):
        raise InvalidInput("Recipient address is not a valid email address.")
    return address


def validate_choice(value: str, allowed: tuple[str, ...], field: str) -> str:
    """Restrict a free-text argument to a fixed set of values (an allowlist)."""
    normalised = (value or "").strip().lower()
    if normalised not in allowed:
        raise InvalidInput(
            f"{field} must be one of: {', '.join(allowed)}."
        )
    return normalised
