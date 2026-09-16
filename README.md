# MCP Paper Server

An MCP (Model Context Protocol) server for academic literature work. It searches
published papers through the Crossref API, keeps the results in a local SQLite
library, and turns any group of saved papers into a BibTeX or APA bibliography
delivered by email.

**Domain:** Academic Research
**Best practices implemented:** Input Sanitization, Error Disclosure
(rate limiting is also implemented — see [Rate limiting](#rate-limiting))

---

## What it exposes

| Kind | Name | Purpose |
|------|------|---------|
| Tool | `search_papers(query, tag, max_results)` | Search Crossref, save results under a tag |
| Tool | `email_bibliography(tag, recipient, style)` | Format saved papers as BibTeX/APA and email them |
| Prompt | `literature_review(topic, tag)` | Guided workflow: search, assess, then send |

The two tools split along a clear line: one brings data in from the outside
world, the other sends a finished product out. Search and storage are combined
in `search_papers` because finding papers is a single action from the user's
point of view — splitting them invites the model to search and then forget to
save.

---

## Requirements

- macOS or Linux
- Python 3.10 or newer
- [uv](https://docs.astral.sh/uv/) for environment management
- Claude Desktop (the MCP client)
- A [Resend](https://resend.com) API key (free tier) for the email tool

---

## Setup

```bash
# 1. Clone and enter the project
git clone <your-repo-url> mcp-paper-server
cd mcp-paper-server

# 2. Create and activate a virtual environment
uv venv
source .venv/bin/activate

# 3. Install dependencies
uv pip install -r requirements.txt

# 4. Configure secrets
cp .env.example .env
# then open .env and fill in the values
```

### `.env`

| Variable | Required | Notes |
|----------|----------|-------|
| `CROSSREF_MAILTO` | no | Your email. Crossref serves identified callers from a faster "polite pool". |
| `RESEND_API_KEY` | for email | From the Resend dashboard. Without it, `email_bibliography` returns the bibliography text instead of sending. |
| `RESEND_SENDER` | no | Defaults to `onboarding@resend.dev`. A Resend free account can only send to the address it was registered with. |

`.env` is listed in `.gitignore` and is never committed. Secrets are read
through `paper_server/config.py`, which locates the file with `pathlib` relative
to the source tree — not with `os.path`, and not from shell environment
variables, because Claude Desktop launches the server as a child process with
its own minimal environment.

---

## Connecting to Claude Desktop

```bash
python scripts/install_claude_config.py
```

The script backs up the existing `claude_desktop_config.json`, adds one
`mcpServers` entry, and leaves every other setting untouched. Then quit Claude
Desktop completely (⌘Q — closing the window is not enough) and reopen it.

The entry it writes:

```json
{
  "mcpServers": {
    "paper-server": {
      "command": "/absolute/path/to/mcp-paper-server/.venv/bin/python",
      "args": ["-m", "paper_server.server"],
      "cwd": "/absolute/path/to/mcp-paper-server",
      "env": { "PYTHONPATH": "/absolute/path/to/mcp-paper-server" }
    }
  }
}
```

Every path is absolute. Claude Desktop does not run the server through a shell,
so an "activated" virtualenv, a relative path, or a `PATH` lookup will not work.
A copy of this file, with the paths as configured on the development machine, is
in `claude_desktop_config.json`.

---

## Verifying it works

```bash
# Full round trip: starts the server as a subprocess exactly the way Claude
# Desktop does, lists tools and prompts, and calls both tools.
python tests/test_mcp_connection.py

# Add an address to also test email delivery
python tests/test_mcp_connection.py you@example.com
```

---

## Security practices

### Input sanitization

Two user-controlled arguments reach a backend, and each is constrained before it
gets there.

`tag` reaches SQLite. Every query in `paper_server/storage.py` uses parameter
binding (`?` placeholders), so a value is passed as data and can never be parsed
as SQL.

`recipient` reaches the email API. `paper_server/security.py` rejects control
characters before pattern matching, then requires the whole string to match a
narrow allowlist pattern. This blocks header injection, where a newline inside
an address lets an attacker append their own `Bcc:` header.

`style` is restricted to a fixed allowlist rather than validated by rejecting
known-bad values.

```bash
python tests/exploit_injection.py
```

The script runs both attacks twice — once against a deliberately vulnerable
implementation defined inside the test file, once against the real one — so the
difference is demonstrated rather than asserted. Against the vulnerable version
the `papers` table is dropped and a hidden `Bcc:` recipient appears; against the
real implementation the table survives and the address is rejected.

### Error disclosure

Anything a tool returns is placed in the model's context and shown to the user,
so a raw traceback is a disclosure channel: it carries absolute filesystem
paths, library versions, and request URLs that can contain credentials.

`security.safe_error()` logs the full exception to `data/server.log` and returns
a generic message with a short reference code. An operator can match the two;
the caller gets nothing useful to an attacker.

One MCP-specific detail: a stdio server uses **stdout** for JSON-RPC messages,
so a log line written to stdout corrupts the protocol stream and kills the
connection. The logger attaches a `FileHandler` and sets `propagate = False` to
keep records off the root logger's stdout handler.

```bash
python tests/exploit_error_disclosure.py
```

### Rate limiting

Implemented in `paper_server/rate_limit.py` and applied to every outbound
Crossref request. It enforces both a minimum interval between requests and a
ceiling per rolling time window. The window ceiling matters because an LLM
client can call a tool in a loop; the interval matters because APIs throttle
callers who burst.

---

## Project structure

```
mcp-paper-server/
├── paper_server/
│   ├── server.py            MCP entry point: tool and prompt definitions
│   ├── crossref_client.py   Crossref REST API calls
│   ├── storage.py           SQLite persistence (parameterized queries)
│   ├── bibliography.py      BibTeX and APA formatting
│   ├── email_client.py      Resend API delivery
│   ├── security.py          Input validation and safe error reporting
│   ├── rate_limit.py        Sliding-window rate limiter
│   └── config.py            .env loading via pathlib
├── tests/
│   ├── test_mcp_connection.py     End-to-end check over stdio
│   ├── exploit_injection.py       Exploit demo: input sanitization
│   └── exploit_error_disclosure.py Exploit demo: error disclosure
├── scripts/
│   └── install_claude_config.py   Merges the server into Claude Desktop's config
├── claude_desktop_config.json     The MCP configuration, for reference
├── requirements.txt
└── .env.example
```

---

## Code citations

No code was copied verbatim from another project. The following external
sources informed specific parts of the implementation, and each is cited in a
comment at the point of use:

| Source | Used for | Where |
|--------|----------|-------|
| [MCP Python SDK](https://github.com/modelcontextprotocol/python-sdk) | Server skeleton, `@tool` / `@prompt` decorators, stdio transport | `paper_server/server.py` |
| [MCP SDK v2 migration guide](https://py.sdk.modelcontextprotocol.io/v2/migration/#fastmcp-renamed-to-mcpserver) | `FastMCP` → `MCPServer` rename in SDK 2.x | `paper_server/server.py` |
| [MCP Python SDK client docs](https://github.com/modelcontextprotocol/python-sdk) | `Client` + `StdioServerParameters` usage | `tests/test_mcp_connection.py` |
| [Crossref REST API docs](https://api.crossref.org/swagger-ui/index.html) and [etiquette guide](https://github.com/CrossRef/rest-api-doc#etiquette) | Endpoint, `query`/`rows`/`filter`/`select` parameters, polite-pool convention | `paper_server/crossref_client.py` |
| [Python `sqlite3` docs](https://docs.python.org/3/library/sqlite3.html#sqlite3-placeholders) | Parameterized query pattern | `paper_server/storage.py` |
| [python-dotenv docs](https://github.com/theskumar/python-dotenv#getting-started) | `.env` loading | `paper_server/config.py` |
| [Resend API reference](https://resend.com/docs/api-reference/emails/send-email) | Request body and Bearer-token header | `paper_server/email_client.py` |
| [BibTeX format reference](https://www.bibtex.com/g/bibtex-format/) | Entry types and field names | `paper_server/bibliography.py` |
| [APA Style: journal article references](https://apastyle.apa.org/style-grammar-guidelines/references/examples/journal-article-references) | APA 7th reference format | `paper_server/bibliography.py` |
| [Cloudflare: rate limiting techniques](https://blog.cloudflare.com/counting-things-a-lot-of-different-things/) | Sliding-window counter approach | `paper_server/rate_limit.py` |
| [MCP quickstart](https://modelcontextprotocol.io/quickstart/user) | macOS location of `claude_desktop_config.json` | `scripts/install_claude_config.py` |

Official MCP [example servers](https://github.com/modelcontextprotocol/servers)
were consulted as references for project layout and error handling — the `git`
server for Python module organization, and `everything` for how prompts are
defined alongside tools. No code was taken from either.

---

## AI assistance

Per the course policy, AI tools used on this assignment:

- **Claude (Opus 5)**, via Claude Code in VS Code and Claude Desktop — used to
  draft the implementation, diagnose runtime failures, and review the code.

All code was reviewed and is understood by the author.

---

## Known limitations

- Crossref indexes published literature, so preprints (arXiv, bioRxiv) do not
  appear. An earlier version used the arXiv API and was replaced after it
  returned HTTP 429 and then 503 during development.
- Results are filtered to `journal-article` and `proceedings-article`. Books and
  book chapters are excluded, which is wrong for some fields.
- Some Crossref records carry no publication year; those are rendered as `n.d.`
  rather than guessed at.
- The rate limiter lives in process memory, so restarting the server resets the
  window. A persistent store would be needed if several instances ran at once.
- A Resend free account can only send to the address it was registered with.
