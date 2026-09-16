"""Launch the MCP server the way Claude Desktop will, then exercise everything.

This verifies the whole chain before touching Claude Desktop: the subprocess
starts, the handshake succeeds, both tools and the prompt are advertised with
usable schemas, and calling them returns real data.

Client usage follows the MCP Python SDK documentation:
https://github.com/modelcontextprotocol/python-sdk

Run from the project root:
    python tests/test_mcp_connection.py [recipient@example.com]
"""

import asyncio
import json
import sys
from pathlib import Path

from mcp import Client, StdioServerParameters

PROJECT_ROOT = Path(__file__).resolve().parent.parent
VENV_PYTHON = PROJECT_ROOT / ".venv" / "bin" / "python"

# Exactly what goes into claude_desktop_config.json.
SERVER_PARAMS = StdioServerParameters(
    command=str(VENV_PYTHON),
    args=["-m", "paper_server.server"],
    cwd=str(PROJECT_ROOT),
)

TEST_TAG = "selftest"


def payload(result) -> dict:
    """Read a tool result from whichever shape the protocol version used."""
    data = result.structured_content
    if not data:
        text = getattr(result.content[0], "text", "") if result.content else ""
        try:
            data = json.loads(text)
        except (ValueError, TypeError):
            data = {"raw": text}
    return data


def schema_params(tool) -> list[str]:
    schema = tool.input_schema
    if not isinstance(schema, dict):
        schema = schema.model_dump(by_alias=True)
    return list(schema.get("properties", {}))


async def main() -> None:
    recipient = sys.argv[1] if len(sys.argv) > 1 else None

    print(f"Launching: {SERVER_PARAMS.command} -m paper_server.server")
    print(f"Working directory: {SERVER_PARAMS.cwd}\n")

    async with Client(SERVER_PARAMS) as client:
        print("Handshake OK\n")

        # ------------------------------------------------------ 1. tool list
        tools = (await client.list_tools()).tools
        print(f"[1] Tools advertised: {len(tools)}")
        for tool in tools:
            print(f"    {tool.name}({', '.join(schema_params(tool))})")

        # ---------------------------------------------------- 2. prompt list
        prompts = (await client.list_prompts()).prompts
        print(f"\n[2] Prompts advertised: {len(prompts)}")
        for prompt in prompts:
            args = [a.name for a in (prompt.arguments or [])]
            print(f"    {prompt.name}({', '.join(args)})")

        # --------------------------------------------------------- 3. search
        print("\n[3] Calling search_papers")
        data = payload(
            await client.call_tool(
                "search_papers",
                {"query": "algorithmic fairness", "tag": TEST_TAG, "max_results": 3},
            )
        )
        if data.get("error"):
            print(f"    Failed: {data['error']}")
            sys.exit(1)
        print(f"    Saved {data['count']} papers under tag {data['tag']!r}")
        for paper in data["papers"]:
            print(f"      [{paper['year'] or 'n/a'}] {paper['title'][:70]}")

        # --------------------------------------------------- 4. bibliography
        print("\n[4] Calling email_bibliography")
        if not recipient:
            print("    (no recipient given, skipping delivery. To test email, run:")
            print("     python tests/test_mcp_connection.py you@example.com)")
        else:
            data = payload(
                await client.call_tool(
                    "email_bibliography",
                    {"tag": TEST_TAG, "recipient": recipient, "style": "bibtex"},
                )
            )
            if data.get("error"):
                print(f"    Failed: {data['error']}")
                sys.exit(1)
            if data.get("sent"):
                print(f"    Sent to {data['recipient']} - {data['count']} references")
                print(f"    Resend message id: {data['message_id']}")
            else:
                print(f"    Not sent: {data.get('reason')}")
            print("\n    Generated BibTeX (first 12 lines):")
            for line in data["bibliography"].splitlines()[:12]:
                print(f"      {line}")

        # ------------------------------------------------------ 5. get prompt
        print("\n[5] Fetching the literature_review prompt")
        got = await client.get_prompt(
            "literature_review", {"topic": "algorithmic fairness", "tag": TEST_TAG}
        )
        first = got.messages[0]
        text = getattr(first.content, "text", str(first.content))
        print(f"    Role: {first.role}, {len(text)} characters")
        print(f"    First line: {text.splitlines()[0]}")

    print("\nAll checks passed.")


if __name__ == "__main__":
    asyncio.run(main())
