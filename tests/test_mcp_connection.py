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

    print(f"启动命令: {SERVER_PARAMS.command} -m paper_server.server")
    print(f"工作目录: {SERVER_PARAMS.cwd}\n")

    async with Client(SERVER_PARAMS) as client:
        print("握手成功\n")

        # ---------------------------------------------------- 1. 工具清单
        tools = (await client.list_tools()).tools
        print(f"[1] 工具 ({len(tools)} 个)")
        for tool in tools:
            print(f"    {tool.name}({', '.join(schema_params(tool))})")

        # ---------------------------------------------------- 2. prompt 清单
        prompts = (await client.list_prompts()).prompts
        print(f"\n[2] prompt 模板 ({len(prompts)} 个)")
        for prompt in prompts:
            args = [a.name for a in (prompt.arguments or [])]
            print(f"    {prompt.name}({', '.join(args)})")

        # ---------------------------------------------------- 3. 搜索
        print("\n[3] 调用 search_papers")
        data = payload(
            await client.call_tool(
                "search_papers",
                {"query": "algorithmic fairness", "tag": TEST_TAG, "max_results": 3},
            )
        )
        if data.get("error"):
            print(f"    失败: {data['error']}")
            sys.exit(1)
        print(f"    存入 {data['count']} 篇，tag = {data['tag']}")
        for paper in data["papers"]:
            print(f"      [{paper['year'] or 'n/a'}] {paper['title'][:70]}")

        # ---------------------------------------------------- 4. 参考文献
        print("\n[4] 调用 email_bibliography")
        if not recipient:
            print("    (没给收件人，跳过发送。想测邮件就加参数：")
            print("     python tests/test_mcp_connection.py 你的邮箱@gmail.com)")
        else:
            data = payload(
                await client.call_tool(
                    "email_bibliography",
                    {"tag": TEST_TAG, "recipient": recipient, "style": "bibtex"},
                )
            )
            if data.get("error"):
                print(f"    失败: {data['error']}")
                sys.exit(1)
            if data.get("sent"):
                print(f"    已发送到 {data['recipient']}，共 {data['count']} 条")
                print(f"    Resend 消息 id: {data['message_id']}")
            else:
                print(f"    未发送: {data.get('reason')}")
            print("\n    生成的 BibTeX（前 12 行）:")
            for line in data["bibliography"].splitlines()[:12]:
                print(f"      {line}")

        # ---------------------------------------------------- 5. prompt 取用
        print("\n[5] 取用 literature_review 模板")
        got = await client.get_prompt(
            "literature_review", {"topic": "algorithmic fairness", "tag": TEST_TAG}
        )
        first = got.messages[0]
        text = getattr(first.content, "text", str(first.content))
        print(f"    角色: {first.role}，长度 {len(text)} 字符")
        print(f"    开头: {text.splitlines()[0]}")

    print("\n全部通过。")


if __name__ == "__main__":
    asyncio.run(main())
