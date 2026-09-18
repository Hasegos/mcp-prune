"""Ask each configured MCP server for its tool list, then size the context-
token cost those schemas add to every session - independent of whether the
tools are ever called.

Exact costs need Anthropic's paid count_tokens endpoint (a Console API key
with billing set up - separate from a Claude Code subscription). Since this
tool only needs to RANK servers against each other, not bill anyone, it
defaults to a free local approximation (~4 chars/token, the standard rule of
thumb for English text) and only calls the paid endpoint if the user has
already set ANTHROPIC_API_KEY.
"""
import asyncio
import json
import os
import re

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

CHARS_PER_TOKEN = 4  # ponytail: rough heuristic, not exact - see module docstring

CONNECT_TIMEOUT = 15  # seconds - some servers hang waiting on missing env/auth
MAX_CONCURRENT_SERVERS = 5  # cap parallel subprocess spawns

# ponytail: no cost caching between runs - every audit re-spawns every server
# (a "npx pkg@latest" server re-resolves/installs from npm each time). Add a
# (command, args) -> cost cache with a TTL (e.g. 7 days) if audits run often
# enough for this to matter.

# A failing server's exception text can echo back its own launch args/env,
# which sometimes embed a raw API key/token. This report gets pasted into a
# Claude Code chat, so redact anything token-shaped before it's ever printed.
_SECRET_LIKE = re.compile(r"[A-Za-z0-9_\-]{20,}")


def _safe_error(exc: Exception) -> str:
    return _SECRET_LIKE.sub("[REDACTED]", str(exc))[:200]


async def _list_tools(cfg: dict):
    # ANTHROPIC_API_KEY is only needed by this process itself (the exact-cost
    # count_tokens call below) - an audited server has no legitimate use for
    # it just to list its tool schemas, so it's stripped before spawning to
    # avoid handing a live secret to a third-party server process.
    spawn_env = {k: v for k, v in os.environ.items() if k != "ANTHROPIC_API_KEY"}
    params = StdioServerParameters(
        command=cfg.get("command", ""),
        args=cfg.get("args", []),
        env={**spawn_env, **cfg.get("env", {})},
    )
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.list_tools()
            return result.tools


def _to_anthropic_tools(mcp_tools):
    return [
        {
            "name": t.name,
            "description": t.description or "",
            "input_schema": t.input_schema or {"type": "object", "properties": {}},
        }
        for t in mcp_tools
    ]


BASELINE_MSGS = [{"role": "user", "content": "x"}]


def _token_cost_exact(client, model: str, tools: list, baseline: int) -> int:
    with_tools = client.messages.count_tokens(model=model, messages=BASELINE_MSGS, tools=tools)
    return with_tools.input_tokens - baseline


def _token_cost_approx(tools: list) -> int:
    return len(json.dumps(tools, ensure_ascii=False)) // CHARS_PER_TOKEN


async def _estimate_one(sem: asyncio.Semaphore, client, model: str, name: str, cfg: dict):
    if not cfg.get("command"):
        return name, {"error": "원격(url) 서버 - stdio 미지원, 건너뜀"}
    async with sem:
        try:
            mcp_tools = await asyncio.wait_for(_list_tools(cfg), timeout=CONNECT_TIMEOUT)
            tools = _to_anthropic_tools(mcp_tools)
            if client is not None:
                baseline = client.messages.count_tokens(model=model, messages=BASELINE_MSGS).input_tokens
                total = _token_cost_exact(client, model, tools, baseline)
                per_tool = [
                    {"name": t["name"], "cost_tokens": _token_cost_exact(client, model, [t], baseline)}
                    for t in tools
                ]
                return name, {"cost_tokens": total, "tool_count": len(tools), "approx": False, "tools": per_tool}
            total = _token_cost_approx(tools)
            per_tool = [{"name": t["name"], "cost_tokens": _token_cost_approx([t])} for t in tools]
            return name, {"cost_tokens": total, "tool_count": len(tools), "approx": True, "tools": per_tool}
        except Exception as exc:  # noqa: BLE001 - many distinct MCP/subprocess failure modes
            return name, {"error": _safe_error(exc)}


async def estimate_all(servers: dict, model: str = "claude-sonnet-5") -> dict:
    """Return {server_name: {"cost_tokens", "tool_count", "approx"} | {"error"}}.

    Uses the exact Anthropic count_tokens endpoint when ANTHROPIC_API_KEY is
    set, otherwise falls back to the free ~4-chars/token approximation (see
    module docstring). Servers are probed concurrently (bounded by
    MAX_CONCURRENT_SERVERS) since each is an independent subprocess spawn +
    I/O wait - sequential probing made an 8-server audit take 8x as long as
    it needed to.
    """
    client = None
    if os.environ.get("ANTHROPIC_API_KEY"):
        from anthropic import Anthropic  # optional dep, only needed for exact mode

        client = Anthropic()
    sem = asyncio.Semaphore(MAX_CONCURRENT_SERVERS)
    pairs = await asyncio.gather(
        *(_estimate_one(sem, client, model, name, cfg) for name, cfg in servers.items())
    )
    return dict(pairs)


if __name__ == "__main__":
    from inventory import list_servers

    servers = list_servers()
    costs = asyncio.run(estimate_all(servers))
    for name, info in costs.items():
        print(name, info)
