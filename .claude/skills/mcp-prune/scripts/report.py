"""Rank configured MCP servers by cost-per-actual-use and suggest which
ones to remove. Entry point for the /mcp-prune skill.
"""
import argparse
import asyncio
import sys
import time
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")  # Windows cp949 can't print the emoji below

sys.path.insert(0, str(Path(__file__).parent))

from inventory import list_servers
from parse_logs import usage_report
from schema_cost import DEFAULT_MODEL, estimate_all

ROI_REVIEW_THRESHOLD = 500  # tokens spent per actual call above which we flag for review

# USD per million input tokens (Anthropic base input price) - turns an
# abstract token count into a concrete dollar figure, since a raw token
# number doesn't register as a real cost to most people.
# Source: https://platform.claude.com/docs/en/about-claude/pricing (fetched 2026-09-22).
PRICE_PER_MTOK = {
    "claude-sonnet-5": 2.0,
    "claude-opus-5": 5.0,
    "claude-haiku-4-5-20251001": 1.0,
}
USD_PER_TOKEN = PRICE_PER_MTOK.get(DEFAULT_MODEL, 2.0) / 1_000_000


def fmt_usd(tokens: int) -> str:
    """Convert a token count into a USD string at the base input rate.

    @param tokens: Token count to price (approximate or exact alike).
    @returns: e.g. '$0.0090'. Always an estimate - see the report's
        footnote for the rate and its caveats (caching, model mismatch).
    """
    return f"${tokens * USD_PER_TOKEN:.4f}"


def fmt_last_used(ts) -> str:
    """Format an epoch-seconds timestamp as a relative Korean label.

    @param ts: Epoch seconds, or a falsy value if the server/tool was
        never called in the audit window.
    @returns: '3일 전' / '오늘' / '사용 안 함'.
    """
    if not ts:
        return "사용 안 함"
    days = int((time.time() - ts) // 86400)
    if days <= 0:
        return "오늘"
    return f"{days}일 전"


def build_rows(servers: dict, usage: dict, costs: dict) -> list:
    """Join server list, usage counts, and schema costs into rankable rows.

    @param servers: `list_servers()` output.
    @param usage: Per-server usage, as returned by `usage_report()`'s first element.
    @param costs: `estimate_all()` output.
    @returns: Rows sorted worst-ROI-first (unmeasurable servers last), each
        {"name", "cost", "calls", "roi", "note", "approx", "last_used"}.
    """
    rows = []
    for name in servers:
        info = usage.get(name, {})
        calls = info.get("calls", 0)
        last_used = info.get("last_used")
        cost_info = costs.get(name, {})
        if "error" in cost_info:
            rows.append({
                "name": name, "cost": None, "calls": calls, "roi": None,
                "note": cost_info["error"], "last_used": last_used,
            })
            continue
        cost = cost_info["cost_tokens"]
        roi = cost / max(1, calls)
        rows.append({
            "name": name, "cost": cost, "calls": calls, "roi": roi,
            "note": "", "approx": cost_info.get("approx", False), "last_used": last_used,
        })
    # worst ROI (most expensive per call) first; unmeasurable servers last
    rows.sort(key=lambda r: (r["roi"] is None, -(r["roi"] or 0)))
    return rows


def render_markdown(rows: list) -> str:
    """Render the per-server ranking table (and removal commands) as markdown.

    @param rows: `build_rows()` output.
    @returns: A markdown table, plus a fenced `claude mcp remove` block for
        any 0-call server and an approximation footnote when any cost was
        estimated rather than measured exactly.
    """
    lines = [
        "| 서버 | 세션당 비용 | 호출횟수 | 마지막 사용 | ROI(비용/호출) | 권고 |",
        "|---|---|---|---|---|---|",
    ]
    remove_cmds = []
    any_approx = False
    for r in rows:
        last_used = fmt_last_used(r["last_used"])
        if r["cost"] is None:
            lines.append(f"| {r['name']} | 측정불가 | {r['calls']} | {last_used} | - | ⚪ {r['note']} |")
            continue
        if r["calls"] == 0:
            verdict = "🔴 제거 권장"
            remove_cmds.append(r["name"])
        elif r["roi"] > ROI_REVIEW_THRESHOLD:
            verdict = "🟡 검토"
        else:
            verdict = "🟢 유지"
        cost_str = f"{r['cost']:,} 토큰 (~{fmt_usd(r['cost'])})"
        if r.get("approx"):
            cost_str = "~" + cost_str
            any_approx = True
        lines.append(f"| {r['name']} | {cost_str} | {r['calls']} | {last_used} | {r['roi']:.0f} | {verdict} |")

    lines.append("")
    lines.append(
        f"※ $ 환산 기준: {DEFAULT_MODEL} API 기본 input 단가 "
        f"(${PRICE_PER_MTOK.get(DEFAULT_MODEL, 2.0):.0f}/MTok, Anthropic 공식 pricing 2026-09 기준). "
        "세션을 새로 시작할 때마다 이 비용이 반복 청구되므로, 세션이 잦을수록 그만큼 누적됩니다."
    )
    if any_approx:
        lines.append("※ ~표시 = 근사치(문자수/4). 정확한 값 원하면 ANTHROPIC_API_KEY 설정 후 재실행.")

    if remove_cmds:
        lines.append("")
        lines.append("제거 명령어:")
        lines.append("```")
        for name in remove_cmds:
            lines.append(f"claude mcp remove {name} -s user")
        lines.append("```")
    return "\n".join(lines)


def build_tool_rows(costs: dict, tool_usage: dict) -> list:
    """Build the per-tool breakdown across all servers, not just the server rollup.

    @param costs: `estimate_all()` output (its per-server "tools" list supplies cost).
    @param tool_usage: Per-tool usage, as returned by `usage_report()`'s second element.
    @returns: Rows sorted by server, then by cost descending within each server.
    """
    rows = []
    for server, cost_info in costs.items():
        for t in cost_info.get("tools", []):
            usage = tool_usage.get((server, t["name"]), {})
            rows.append({
                "server": server, "tool": t["name"], "cost": t["cost_tokens"],
                "calls": usage.get("calls", 0), "last_used": usage.get("last_used"),
                "approx": cost_info.get("approx", False),
            })
    rows.sort(key=lambda r: (r["server"], -r["cost"]))
    return rows


def render_tool_markdown(rows: list) -> str:
    """Render the per-tool breakdown table as markdown.

    @param rows: `build_tool_rows()` output.
    @returns: A markdown table under a "### 도구별 상세" heading, or "" when
        there are no tool rows to show (no server had a measured schema).
    """
    if not rows:
        return ""
    lines = [
        "",
        "### 도구별 상세",
        "| 서버 | 도구 | 비용 | 호출횟수 | 마지막 사용 |",
        "|---|---|---|---|---|",
    ]
    for r in rows:
        cost_str = f"{r['cost']:,} 토큰 (~{fmt_usd(r['cost'])})"
        if r["approx"]:
            cost_str = "~" + cost_str
        lines.append(f"| {r['server']} | {r['tool']} | {cost_str} | {r['calls']} | {fmt_last_used(r['last_used'])} |")
    return "\n".join(lines)


def main():
    """CLI entry point: print the per-server and per-tool audit tables.

    @returns: None. Prints the markdown report(s) to stdout, or a
        no-servers-configured message if `list_servers()` finds nothing.
    """
    parser = argparse.ArgumentParser(description="Audit MCP servers by cost vs actual usage.")
    parser.add_argument("--days", type=int, default=30, help="session log window in days")
    args = parser.parse_args()

    servers = list_servers()
    if not servers:
        print("설정된 MCP 서버가 없습니다 (.mcp.json / ~/.claude.json 확인).")
        return

    usage, tool_usage = usage_report(days=args.days)  # single log scan for both views
    costs = asyncio.run(estimate_all(servers))

    rows = build_rows(servers, usage, costs)
    print(render_markdown(rows))

    tool_rows = build_tool_rows(costs, tool_usage)
    tool_md = render_tool_markdown(tool_rows)
    if tool_md:
        print(tool_md)


if __name__ == "__main__":
    main()
