"""Local SQLite storage for papers saved from Crossref.

All queries use parameter binding (the ? placeholders) rather than string
formatting. This is the input-sanitization best practice for this project: a
value supplied by the caller is handed to SQLite as data and can never be
parsed as SQL, so a tag like "x'; DROP TABLE papers;--" is just a tag that
matches nothing.

Parameterized-query pattern follows the Python standard library docs:
https://docs.python.org/3/library/sqlite3.html#sqlite3-placeholders
"""

import sqlite3
from pathlib import Path

# pathlib is used (not os.path) so the database path resolves relative to this
# source file, no matter which directory the server is launched from.
DB_PATH = Path(__file__).resolve().parent.parent / "data" / "papers.db"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS papers (
    doi        TEXT PRIMARY KEY,
    title      TEXT NOT NULL,
    authors    TEXT NOT NULL,
    journal    TEXT NOT NULL,
    year       TEXT NOT NULL,
    url        TEXT NOT NULL,
    tag        TEXT NOT NULL,
    saved_at   TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_papers_tag ON papers (tag);
"""


def get_connection() -> sqlite3.Connection:
    """Open a connection to the local database, creating the folder if needed."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    """Create the papers table if it does not exist yet."""
    with get_connection() as conn:
        conn.executescript(_SCHEMA)


def save_papers(papers: list[dict], tag: str) -> int:
    """Insert papers under the given tag. Returns how many rows were written.

    INSERT OR REPLACE means re-running the same search refreshes the existing
    row instead of raising a primary-key conflict. Records without a DOI are
    skipped, since the DOI is the primary key.
    """
    rows = [
        (
            paper["doi"],
            paper["title"],
            ", ".join(paper["authors"]),
            paper["journal"],
            paper["year"],
            paper["url"],
            tag,
        )
        for paper in papers
        if paper.get("doi")
    ]
    with get_connection() as conn:
        conn.executemany(
            """INSERT OR REPLACE INTO papers
               (doi, title, authors, journal, year, url, tag)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            rows,
        )
    return len(rows)


def get_papers_by_tag(tag: str) -> list[dict]:
    """Return every saved paper carrying the given tag, newest publication first."""
    with get_connection() as conn:
        cursor = conn.execute(
            "SELECT * FROM papers WHERE tag = ? ORDER BY year DESC, title",
            (tag,),
        )
        return [dict(row) for row in cursor.fetchall()]


def list_tags() -> list[str]:
    """Return every tag currently in use, with how many papers each holds."""
    with get_connection() as conn:
        cursor = conn.execute(
            "SELECT tag, COUNT(*) AS n FROM papers GROUP BY tag ORDER BY tag"
        )
        return [f"{row['tag']} ({row['n']})" for row in cursor.fetchall()]
