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
    """Strip anything token-shaped out of an exception's text before display.

    @param exc: The exception to render.
    @returns: The exception text with any 20+ char token-like run redacted,
        truncated to 200 chars.
    """
    return _SECRET_LIKE.sub("[REDACTED]", str(exc))[:200]


async def _list_tools(cfg: dict):
    """Spawn one MCP server over stdio and list its tools.

    @param cfg: This server's `.mcp.json`/`~/.claude.json` entry (command, args, env).
    @returns: The MCP SDK's list of Tool objects.
    """
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
    """Convert MCP SDK Tool objects into Anthropic API tool-definition dicts.

    @param mcp_tools: `_list_tools()` output.
    @returns: A list of {"name", "description", "input_schema"} dicts.
    """
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
    """Measure one tool-set's token cost via the paid count_tokens endpoint.

    Blocking network call - only call this from a thread (see
    `_token_costs_exact_sync()`), never directly on the event loop.

    @param client: An Anthropic() client.
    @param model: Model name to price the schemas against.
    @param tools: Anthropic tool-definition dicts to measure.
    @param baseline: Token count of the request with no tools, subtracted
        out so the result reflects only the tool schemas' cost.
    @returns: Token cost of `tools` alone.
    """
    with_tools = client.messages.count_tokens(model=model, messages=BASELINE_MSGS, tools=tools)
    return with_tools.input_tokens - baseline


def _token_cost_approx(tools: list) -> int:
    """Free local approximation of a tool-set's token cost (~4 chars/token).

    @param tools: Anthropic tool-definition dicts to measure.
    @returns: Estimated token cost.
    """
    return len(json.dumps(tools, ensure_ascii=False)) // CHARS_PER_TOKEN


def _token_costs_exact_sync(client, model: str, tools: list) -> tuple[int, list]:
    """Do all the exact-mode count_tokens calls for one server in one call.

    Blocking - run this via `asyncio.to_thread()`, never awaited directly,
    so one server's several sequential count_tokens round trips don't
    stall every other server's concurrent stdio I/O on the event loop.

    @param client: An Anthropic() client.
    @param model: Model name to price the schemas against.
    @param tools: This server's tools in Anthropic tool-definition shape.
    @returns: (total_cost_tokens, per_tool_cost_list) - the list holds
        {"name", "cost_tokens"} per tool.
    """
    baseline = client.messages.count_tokens(model=model, messages=BASELINE_MSGS).input_tokens
    total = _token_cost_exact(client, model, tools, baseline)
    per_tool = [
        {"name": t["name"], "cost_tokens": _token_cost_exact(client, model, [t], baseline)}
        for t in tools
    ]
    return total, per_tool


async def _estimate_one(sem: asyncio.Semaphore, client, model: str, name: str, cfg: dict):
    """Estimate one server's schema cost: connect, list tools, price them.

    @param sem: Semaphore bounding concurrent subprocess spawns.
    @param client: An Anthropic() client for exact mode, or None for approx mode.
    @param model: Model name to price the schemas against.
    @param name: This server's name (for the returned pair and error messages).
    @param cfg: This server's `.mcp.json`/`~/.claude.json` entry.
    @returns: (name, {"cost_tokens", "tool_count", "approx", "tools"}), or
        (name, {"error": str}) if the server has no local command or fails
        to connect/list tools within CONNECT_TIMEOUT.
    """
    if not cfg.get("command"):
        return name, {"error": "원격(url) 서버 - stdio 미지원, 건너뜀"}
    async with sem:
        try:
            mcp_tools = await asyncio.wait_for(_list_tools(cfg), timeout=CONNECT_TIMEOUT)
            tools = _to_anthropic_tools(mcp_tools)
            if client is not None:
                total, per_tool = await asyncio.to_thread(_token_costs_exact_sync, client, model, tools)
                return name, {"cost_tokens": total, "tool_count": len(tools), "approx": False, "tools": per_tool}
            total = _token_cost_approx(tools)
            per_tool = [{"name": t["name"], "cost_tokens": _token_cost_approx([t])} for t in tools]
            return name, {"cost_tokens": total, "tool_count": len(tools), "approx": True, "tools": per_tool}
        except Exception as exc:  # noqa: BLE001 - many distinct MCP/subprocess failure modes
            return name, {"error": _safe_error(exc)}


async def estimate_all(servers: dict, model: str = "claude-sonnet-5") -> dict:
    """Estimate every configured server's tool-schema token cost.

    Uses the exact Anthropic count_tokens endpoint when ANTHROPIC_API_KEY is
    set, otherwise falls back to the free ~4-chars/token approximation (see
    module docstring). Servers are probed concurrently (bounded by
    MAX_CONCURRENT_SERVERS) since each is an independent subprocess spawn +
    I/O wait - sequential probing made an 8-server audit take 8x as long as
    it needed to.

    @param servers: `list_servers()` output.
    @param model: Model name to price the schemas against (exact mode only).
    @returns: {server_name: {"cost_tokens", "tool_count", "approx", "tools"} | {"error"}}.
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
