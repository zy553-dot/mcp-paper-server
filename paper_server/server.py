"""MCP server for academic paper search and bibliography management.

Domain: Academic Research.

Server skeleton follows the quickstart in the official MCP Python SDK (v2):
https://github.com/modelcontextprotocol/python-sdk
Note: in SDK v2 the class formerly called FastMCP is named MCPServer.
https://py.sdk.modelcontextprotocol.io/v2/migration/#fastmcp-renamed-to-mcpserver
"""

import httpx
from mcp.server.mcpserver import MCPServer

from paper_server import (
    bibliography,
    crossref_client,
    email_client,
    security,
    storage,
)
from paper_server.rate_limit import RateLimitExceeded
from paper_server.security import InvalidInput

# The name here is what Claude Desktop shows in its tool list.
mcp = MCPServer("paper-server")

# Guard rail: cap how much one call can ask for, so a malformed number from the
# model cannot turn into an enormous request.
MAX_RESULTS_LIMIT = 20

CITATION_STYLES = ("bibtex", "apa")


@mcp.tool()
def search_papers(query: str, tag: str = "inbox", max_results: int = 5) -> dict:
    """Search published academic literature and save the results to the local library.

    Use this when the user wants to find papers on a topic. Results are stored
    under a tag so they can be turned into a bibliography later with
    build_bibliography.

    Args:
        query: What to search for, e.g. "graph neural networks for traffic".
        tag: A short label to file these papers under, e.g. "thesis-ch2".
        max_results: How many papers to return, between 1 and 20.
    """
    storage.init_db()

    # Clamp instead of rejecting, so a slightly-off number from the model still
    # produces a useful answer rather than an error.
    capped = max(1, min(max_results, MAX_RESULTS_LIMIT))

    try:
        papers = crossref_client.search(query, capped)
    except RateLimitExceeded as exc:
        # Safe to show: it names no internal detail, and the model needs to know
        # it should wait rather than retry immediately.
        return {"error": str(exc), "papers": []}
    except httpx.HTTPError as exc:
        # Network errors carry the full request URL, which can include query
        # parameters. They go to the log; the caller gets a reference code.
        return {"error": security.safe_error("Literature search", exc), "papers": []}

    saved = storage.save_papers(papers, tag)

    return {
        "query": query,
        "tag": tag,
        "count": saved,
        "papers": [
            {
                "doi": paper["doi"],
                "title": paper["title"],
                "authors": paper["authors"],
                "journal": paper["journal"],
                "year": paper["year"],
                "url": paper["url"],
            }
            for paper in papers
        ],
    }


@mcp.tool()
def email_bibliography(tag: str, recipient: str, style: str = "bibtex") -> dict:
    """Format every saved paper under a tag as a bibliography and email it.

    Use this after search_papers has collected papers under a tag, when the user
    wants the citations sent to them. The formatted text is always returned, so
    the user still gets the bibliography even if the email cannot be delivered.

    Args:
        tag: Which saved group to turn into a bibliography, e.g. "thesis-ch2".
        recipient: Email address to send it to.
        style: Either "bibtex" (for LaTeX and reference managers) or "apa".
    """
    try:
        recipient = security.validate_email(recipient)
        style = security.validate_choice(style, CITATION_STYLES, "style")
    except InvalidInput as exc:
        # Validation messages describe the rule that was broken, never the
        # value that broke it, so a malicious argument is not echoed back.
        return {"error": str(exc), "sent": False}

    storage.init_db()
    papers = storage.get_papers_by_tag(tag)
    if not papers:
        return {
            "error": f"No papers are saved under the tag {tag!r}. "
                     f"Run search_papers first. Tags in use: "
                     f"{', '.join(storage.list_tags()) or 'none'}",
            "sent": False,
        }

    text = bibliography.format_entries(papers, style)
    subject = f"Bibliography: {tag} ({len(papers)} references, {style})"

    if not email_client.is_configured():
        return {
            "sent": False,
            "reason": "RESEND_API_KEY is not set in .env, so nothing was sent.",
            "count": len(papers),
            "style": style,
            "bibliography": text,
        }

    try:
        message_id = email_client.send(recipient, subject, text)
    except httpx.HTTPError as exc:
        # Delivery failed, but the work did not: hand back the bibliography so
        # the user is not left with nothing.
        return {
            "sent": False,
            "reason": security.safe_error("Sending the bibliography", exc),
            "count": len(papers),
            "style": style,
            "bibliography": text,
        }

    return {
        "sent": True,
        "message_id": message_id,
        "recipient": recipient,
        "count": len(papers),
        "style": style,
        "bibliography": text,
    }


@mcp.prompt()
def literature_review(topic: str, tag: str = "review") -> str:
    """A guided workflow for surveying a topic and producing a bibliography.

    Prompts are user-controlled: the user picks this from the client's menu,
    which is why it reads as an instruction to the assistant rather than as a
    question from it.
    """
    return f"""You are helping with a literature review on: {topic}

Work through these steps, and pause for confirmation before step 4.

1. Call search_papers with a focused query for "{topic}" and tag "{tag}".
   Prefer a specific query over a broad one; if the first search returns
   loosely related work, refine the wording and search again under the same tag.

2. Read the returned titles, journals and years. Report back:
   - which papers look central to the topic and why
   - what time span the results cover, and whether recent work is missing
   - any paper that looks off-topic and should be excluded

3. Point out what the search did NOT surface: adjacent subfields, competing
   approaches, or foundational work that a query on "{topic}" would miss.
   Say plainly when the collected set is too thin to review.

4. Once the user confirms the set is right, call email_bibliography with tag
   "{tag}" to send the citations.

Do not invent papers, authors, or DOIs. Every citation must come from a
search_papers result. If a record has no publication year, say so rather than
estimating one."""

if __name__ == "__main__":
    # stdio is the transport Claude Desktop uses: it launches this file as a
    # child process and talks JSON-RPC over stdin/stdout.
    mcp.run(transport="stdio")
