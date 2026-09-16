"""Configuration and secrets, loaded from a .env file beside this project.

Two rules this module exists to enforce:

1. Secrets are read from .env, never hard-coded and never assumed to be present
   in the shell environment. Claude Desktop launches this server as a child
   process with its own environment, so anything exported in a terminal is not
   visible here.
2. The path to .env is built with pathlib, relative to this source file, so the
   server works no matter which directory it is launched from.

python-dotenv usage follows its documentation:
https://github.com/theskumar/python-dotenv#getting-started
"""

import os
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent
ENV_PATH = PROJECT_ROOT / ".env"

# override=False: a value already in the environment wins, which is what lets
# the test suite inject a fake key without editing the real .env file.
load_dotenv(ENV_PATH, override=False)


class MissingConfiguration(RuntimeError):
    """Raised when a required setting is absent from .env."""


def get(name: str, default: str | None = None, *, required: bool = False) -> str | None:
    """Read one setting. Raises MissingConfiguration if required and absent.

    The error names the setting and the file to edit, never the value, so it is
    safe to show a user.
    """
    value = os.getenv(name, default)
    if required and not value:
        raise MissingConfiguration(
            f"{name} is not set. Copy .env.example to .env and fill it in."
        )
    return value


# Crossref runs a "polite pool" with better service for callers who identify
# themselves by email. Not a secret, but it belongs with the other settings.
CROSSREF_MAILTO = get("CROSSREF_MAILTO", "anonymous@example.com")
