#!/usr/bin/env python3
"""SessionStart hook: nudge the user when configured MCP servers look unused.

Fast, local-only check - reads the same config/log files inventory.py and
parse_logs.py already read (no server spawning, no network, no paid API
calls), so it costs nothing to run on every session start. Prints nothing
when there's nothing worth flagging - a hook that nags every session trains
people to ignore it.
"""
import os
import sys
from pathlib import Path

_PLUGIN_ROOT = os.environ.get("CLAUDE_PLUGIN_ROOT") or str(Path(__file__).resolve().parent.parent)
sys.path.insert(0, str(Path(_PLUGIN_ROOT) / "skills" / "run" / "scripts"))


def main():
    """Print a one-line nudge if any configured MCP server had 0 calls in 30 days.

    @returns: None. Prints at most one line to stdout - SessionStart hooks
        surface plain stdout as context the user and Claude both see.
        Stays silent (and never raises) on any error or when nothing is
        wasted, since a hook must never block or spam session start.
    """
    try:
        from inventory import list_servers
        from parse_logs import usage_report

        servers = list_servers()
        if not servers:
            return
        usage, _ = usage_report(days=30)
        unused = [name for name in servers if usage.get(name, {}).get("calls", 0) == 0]
        if unused:
            print(
                f"💤 mcp-prune: MCP 서버 {len(unused)}개가 30일간 한 번도 안 불렸어요 "
                "— /mcp-prune 실행해서 확인해보세요"
            )
    except Exception:
        return  # a hook must never block or crash session start


if __name__ == "__main__":
    main()
