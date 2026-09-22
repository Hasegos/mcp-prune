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
            # Framed as a clearly separate status block, with an explicit
            # instruction on how to surface it - this becomes additionalContext
            # Claude sees at session start, so without that instruction it could
            # get woven into the reply to whatever the user actually asked,
            # which reads as a jarring non sequitur.
            print(
                "[mcp-prune 세션 시작 알림 - 사용자의 실제 첫 메시지에 답하기 전에는 언급하지 말 것]\n"
                f"📋 mcp-prune 현황: MCP 서버 {len(unused)}개가 30일간 호출 0번\n"
                "사용자의 실제 요청에 먼저 답변하세요. 그 답변 끝에 위 현황을 "
                "'📋 mcp-prune 현황: ...' 형태로 한 줄만 짧게 덧붙이고, "
                "필요하면 /mcp-prune:run으로 확인해보라고 안내하세요. "
                "사용자가 이미 이 대화에서 mcp-prune 관련 요청을 했다면 이 알림은 생략하세요."
            )
    except Exception:
        return  # a hook must never block or crash session start


if __name__ == "__main__":
    main()
