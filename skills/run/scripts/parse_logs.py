"""Count how often each MCP server's tools were actually invoked, using
Claude Code's local session transcripts (~/.claude/projects/**/*.jsonl).
"""
import json
import time
from collections import Counter, defaultdict
from pathlib import Path

SESSIONS_ROOT = Path.home() / ".claude" / "projects"


def _tool_use_names(line: str):
    try:
        event = json.loads(line)
    except json.JSONDecodeError:
        return
    message = event.get("message")
    if not isinstance(message, dict):
        return
    content = message.get("content")
    if not isinstance(content, list):
        return
    for block in content:
        if isinstance(block, dict) and block.get("type") == "tool_use":
            name = block.get("name")
            if name:
                yield name


def server_of(tool_name: str):
    """'mcp__notion__search' -> 'notion'. Non-MCP tools return None."""
    if not tool_name.startswith("mcp__"):
        return None
    parts = tool_name.split("__")
    return parts[1] if len(parts) >= 3 and parts[1] else None


def bare_tool_name(tool_name: str):
    """'mcp__notion__search' -> 'search' (strips the 'mcp__<server>__' prefix)."""
    server = server_of(tool_name)
    if server is None:
        return None
    return tool_name[len(f"mcp__{server}__"):]


def _scan(days: int) -> tuple[Counter, dict]:
    """One pass over recent session logs. Returns (calls_per_full_tool_name,
    last_used_mtime_per_full_tool_name). Both count_calls() and
    count_calls_by_tool() derive from this so logs are only read once.
    """
    cutoff = time.time() - days * 86400
    calls = Counter()
    last_used = defaultdict(float)

    if not SESSIONS_ROOT.exists():
        return calls, last_used

    for jsonl_path in SESSIONS_ROOT.glob("**/*.jsonl"):
        try:
            mtime = jsonl_path.stat().st_mtime
        except OSError:
            continue
        if mtime < cutoff:
            continue
        try:
            with jsonl_path.open(encoding="utf-8", errors="ignore") as f:
                for line in f:
                    for tool_name in _tool_use_names(line):
                        if server_of(tool_name):
                            calls[tool_name] += 1
                            last_used[tool_name] = max(last_used[tool_name], mtime)
        except OSError:
            continue

    return calls, last_used


def count_calls(days: int = 30) -> dict:
    """Return {server_name: {"calls": int, "last_used": float|None}}."""
    raw_calls, raw_last = _scan(days)
    calls = Counter()
    last_used = defaultdict(float)
    for tool_name, n in raw_calls.items():
        server = server_of(tool_name)
        calls[server] += n
        last_used[server] = max(last_used[server], raw_last[tool_name])
    return {
        server: {"calls": n, "last_used": last_used[server] or None}
        for server, n in calls.items()
    }


def count_calls_by_tool(days: int = 30) -> dict:
    """Return {(server, bare_tool_name): calls} for the per-tool breakdown."""
    raw_calls, _ = _scan(days)
    return {
        (server_of(tool_name), bare_tool_name(tool_name)): n
        for tool_name, n in raw_calls.items()
    }


if __name__ == "__main__":
    stats = count_calls()
    if not stats:
        print("no MCP tool calls found in the last 30 days")
    for server, info in stats.items():
        print(f"{server}: {info['calls']} calls")
