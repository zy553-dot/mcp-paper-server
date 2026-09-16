"""Client for the Crossref REST API.

Crossref is the registration agency for DOIs, so its records carry exactly the
fields a bibliography needs: DOI, journal, volume, year, and the author list.
No API key is required; callers who supply an email address are served from the
"polite pool", which has better availability than the anonymous pool.

Endpoint, parameter names (query, rows, mailto) and the response shape below are
documented in the Crossref REST API guide:
https://api.crossref.org/swagger-ui/index.html
https://github.com/CrossRef/rest-api-doc#etiquette

Replaces an earlier arXiv implementation: arXiv's API returned HTTP 429 and then
503 during development, and it only indexes preprints.
"""

import time
from typing import Any

import httpx

from paper_server.config import CROSSREF_MAILTO
from paper_server.rate_limit import RateLimiter

CROSSREF_API_URL = "https://api.crossref.org/works"
REQUEST_TIMEOUT = 20.0
USER_AGENT = f"mcp-paper-server/0.1 (mailto:{CROSSREF_MAILTO})"

# Crossref publishes no hard limit for the polite pool, so this ceiling is the
# server's own budget rather than a number the API forces on us.
_LIMITER = RateLimiter(max_calls=10, period=60.0, min_interval=1.0)

MAX_ATTEMPTS = 3
BACKOFF_SECONDS = 4.0

# Crossref registers DOIs for far more than journal articles. Restricting to
# these two types is what keeps the results usable as a bibliography.
WANTED_TYPES = ("journal-article", "proceedings-article")


def search(query: str, rows: int = 5) -> list[dict]:
    """Search Crossref and return a list of plain dictionaries.

    Raises RateLimitExceeded when over this server's own budget, or
    httpx.HTTPError when Crossref is unreachable or returns an error status.
    """
    _LIMITER.acquire()

    params = {
        "query": query,
        # Over-fetch: the filter below is applied by Crossref, but records with
        # an empty title still come back and are dropped locally, so asking for
        # exactly `rows` would usually return fewer.
        "rows": min(rows * 3, 60),
        "mailto": CROSSREF_MAILTO,
        # Without a type filter the results mix in theses, podcast episodes,
        # standards documents and conference abstracts, ranked together by
        # relevance. Repeating a filter name is how Crossref expresses OR.
        "filter": ",".join(f"type:{t}" for t in WANTED_TYPES),
        # Ask for only the fields used below; a full record is far larger.
        "select": "DOI,title,author,container-title,issued,URL,type",
    }

    for attempt in range(MAX_ATTEMPTS):
        response = httpx.get(
            CROSSREF_API_URL,
            params=params,
            timeout=REQUEST_TIMEOUT,
            follow_redirects=True,
            headers={"User-Agent": USER_AGENT},
        )
        if response.status_code in (429, 503) and attempt < MAX_ATTEMPTS - 1:
            time.sleep(BACKOFF_SECONDS * (attempt + 1))
            continue
        break

    response.raise_for_status()
    payload = response.json()

    papers = [_to_paper(item) for item in payload["message"]["items"]]
    # A record with no title is unusable in a bibliography, whatever its type.
    papers = [p for p in papers if p["title"] and p["doi"]]
    return papers[:rows]


def _to_paper(item: dict[str, Any]) -> dict:
    """Flatten one Crossref record into the shape this server stores."""
    return {
        "doi": item.get("DOI", ""),
        "title": _first(item.get("title")),
        "authors": _authors(item.get("author")),
        "journal": _first(item.get("container-title")) or "",
        "year": _year(item.get("issued")),
        "url": item.get("URL", ""),
        "type": item.get("type", ""),
    }


def _first(value: list[str] | None) -> str:
    """Crossref wraps several single-valued fields in a list."""
    return value[0].strip() if value else ""


def _authors(authors: list[dict] | None) -> list[str]:
    """Build 'Given Family' strings, tolerating records with either part missing."""
    if not authors:
        return []
    names = []
    for person in authors:
        parts = [person.get("given", ""), person.get("family", "")]
        name = " ".join(part for part in parts if part).strip()
        names.append(name or person.get("name", "Unknown"))
    return names


def _year(issued: dict | None) -> str:
    """Pull the year out of Crossref's nested date-parts structure.

    The shape is {"date-parts": [[2024, 5, 1]]}; month and day are often absent.
    """
    if not issued:
        return ""
    parts = issued.get("date-parts") or [[]]
    # A record with no usable date still carries the structure, as
    # {"date-parts": [[None]]}. That list is truthy, so the element itself has
    # to be checked - otherwise str(None) quietly stores the text "None".
    year = parts[0][0] if parts and parts[0] else None
    return str(year) if year is not None else ""
