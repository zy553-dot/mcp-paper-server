"""Turn stored paper records into formatted bibliography entries.

Two styles are supported: BibTeX (for LaTeX and reference managers) and APA 7th
(for reading and pasting into a document).

Kept separate from both storage and delivery so it can be tested on its own -
formatting is pure text manipulation with no database and no network.

BibTeX field names and the @article / @inproceedings entry types follow the
BibTeX documentation:
https://www.bibtex.com/g/bibtex-format/
APA 7th reference format for a journal article follows the APA Style guide:
https://apastyle.apa.org/style-grammar-guidelines/references/examples/journal-article-references
"""

import re

# Characters that have meaning to LaTeX and must be escaped inside a field.
_LATEX_SPECIALS = {
    "\\": r"\textbackslash{}",
    "&": r"\&",
    "%": r"\%",
    "$": r"\$",
    "#": r"\#",
    "_": r"\_",
    "{": r"\{",
    "}": r"\}",
    "~": r"\textasciitilde{}",
    "^": r"\textasciicircum{}",
}

NO_DATE = "n.d."  # APA's marker for a source with no publication date


def format_entries(papers: list[dict], style: str = "bibtex") -> str:
    """Format a list of stored paper rows. Raises ValueError on an unknown style."""
    style = style.lower().strip()
    if style == "bibtex":
        return "\n\n".join(_bibtex_entry(paper) for paper in papers)
    if style == "apa":
        return "\n\n".join(_apa_entry(paper) for paper in papers)
    raise ValueError(f"Unknown citation style: {style!r}. Use 'bibtex' or 'apa'.")


# ---------------------------------------------------------------- BibTeX


def _bibtex_entry(paper: dict) -> str:
    fields = {
        "author": _bibtex_authors(paper["authors"]),
        "title": _escape_latex(paper["title"]),
        "journal": _escape_latex(paper["journal"]),
        "year": paper["year"],
        "doi": paper["doi"],
        "url": paper["url"],
    }
    body = "\n".join(
        f"  {name:<8}= {{{value}}}," for name, value in fields.items() if value
    )
    return f"@article{{{_citation_key(paper)},\n{body}\n}}"


def _citation_key(paper: dict) -> str:
    """Build a stable key like 'tsai1997hydrophobic'.

    Reference managers need the key to be unique and to contain only plain
    ASCII letters and digits, so accents and punctuation are stripped out.
    """
    first_author = (paper["authors"].split(",")[0] if paper["authors"] else "anon")
    surname = first_author.strip().split(" ")[-1] if first_author.strip() else "anon"
    year = paper["year"] or "nd"
    first_word = next(
        (w for w in re.findall(r"[A-Za-z]+", paper["title"]) if len(w) > 3), "untitled"
    )
    key = f"{surname}{year}{first_word}".lower()
    return re.sub(r"[^a-z0-9]", "", key) or "entry"


def _bibtex_authors(authors: str) -> str:
    """BibTeX separates authors with ' and ', not commas."""
    names = [name.strip() for name in authors.split(",") if name.strip()]
    return " and ".join(_escape_latex(name) for name in names)


def _escape_latex(text: str) -> str:
    """Escape characters LaTeX would otherwise interpret as markup."""
    return "".join(_LATEX_SPECIALS.get(char, char) for char in text)


# ------------------------------------------------------------------- APA


def _apa_entry(paper: dict) -> str:
    authors = _apa_authors(paper["authors"])
    year = paper["year"] or NO_DATE
    title = paper["title"].rstrip(".")
    parts = [f"{authors} ({year}). {title}."]
    if paper["journal"]:
        parts.append(f"{paper['journal']}.")
    if paper["doi"]:
        parts.append(f"https://doi.org/{paper['doi']}")
    return " ".join(parts)


def _apa_authors(authors: str) -> str:
    """Render 'Given Family' names as APA's 'Family, G.' form.

    APA lists up to 20 authors, then an ellipsis and the last one. This keeps
    the common case correct without reproducing the whole rule set.
    """
    names = [name.strip() for name in authors.split(",") if name.strip()]
    if not names:
        return "Anonymous"

    formatted = [_apa_one_name(name) for name in names]
    if len(formatted) == 1:
        return formatted[0]
    if len(formatted) <= 20:
        return ", ".join(formatted[:-1]) + f", & {formatted[-1]}"
    return ", ".join(formatted[:19]) + f", ... {formatted[-1]}"


def _apa_one_name(name: str) -> str:
    parts = name.split()
    if len(parts) == 1:
        return parts[0]
    surname = parts[-1]
    initials = " ".join(f"{part[0]}." for part in parts[:-1] if part)
    return f"{surname}, {initials}"
