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


def count_calls(days: int = 30) -> dict:
    """Return {server_name: {"calls": int, "last_used": float|None}}."""
    cutoff = time.time() - days * 86400
    calls = Counter()
    last_used = defaultdict(float)

    if not SESSIONS_ROOT.exists():
        return {}

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
                        server = server_of(tool_name)
                        if server:
                            calls[server] += 1
                            last_used[server] = max(last_used[server], mtime)
        except OSError:
            continue

    return {
        server: {"calls": n, "last_used": last_used[server] or None}
        for server, n in calls.items()
    }


if __name__ == "__main__":
    stats = count_calls()
    if not stats:
        print("no MCP tool calls found in the last 30 days")
    for server, info in stats.items():
        print(f"{server}: {info['calls']} calls")
