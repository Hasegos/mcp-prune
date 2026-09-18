"""Count how often each MCP server's tools were actually invoked, using
Claude Code's local session transcripts (~/.claude/projects/**/*.jsonl).
"""
import json
import time
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

SESSIONS_ROOT = Path.home() / ".claude" / "projects"


def _event_time(event: dict):
    """Parse a session event's own ISO 8601 `timestamp` field (e.g.
    "2026-09-18T00:49:24.052Z") into epoch seconds. Returns None when the
    field is missing or malformed - the caller falls back to the
    containing file's mtime in that case.
    """
    ts = event.get("timestamp")
    if not isinstance(ts, str):
        return None
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return None


def _tool_use_names(event: dict):
    """Yield each tool_use block's name from one parsed session event."""
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
    last_used_epoch_per_full_tool_name). Both count_calls() and
    count_calls_by_tool() derive from this so logs are only read once.

    Each tool call is filtered and timestamped by its own event
    `timestamp` field, not the containing file's mtime - a session file
    that's resumed/appended to over weeks would otherwise misdate every
    call inside it (including ones from well outside the --days window)
    as having just happened, since mtime reflects the file's last write,
    not any individual event's time.
    """
    cutoff = time.time() - days * 86400
    calls = Counter()
    last_used = defaultdict(float)

    if not SESSIONS_ROOT.exists():
        return calls, last_used

    for jsonl_path in SESSIONS_ROOT.glob("**/*.jsonl"):
        try:
            file_mtime = jsonl_path.stat().st_mtime
        except OSError:
            continue
        if file_mtime < cutoff:
            continue  # file untouched since the window opened - cheap skip
        try:
            with jsonl_path.open(encoding="utf-8", errors="ignore") as f:
                for line in f:
                    try:
                        event = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    event_time = _event_time(event)
                    if event_time is None:
                        event_time = file_mtime
                    if event_time < cutoff:
                        continue
                    for tool_name in _tool_use_names(event):
                        if server_of(tool_name):
                            calls[tool_name] += 1
                            last_used[tool_name] = max(last_used[tool_name], event_time)
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
    """Return {(server, bare_tool_name): {"calls": int, "last_used": float|None}}."""
    raw_calls, raw_last = _scan(days)
    return {
        (server_of(tool_name), bare_tool_name(tool_name)): {
            "calls": n,
            "last_used": raw_last[tool_name] or None,
        }
        for tool_name, n in raw_calls.items()
    }


if __name__ == "__main__":
    stats = count_calls()
    if not stats:
        print("no MCP tool calls found in the last 30 days")
    for server, info in stats.items():
        print(f"{server}: {info['calls']} calls")
