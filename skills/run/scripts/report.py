"""Rank configured MCP servers by cost-per-actual-use and suggest which
ones to remove. Entry point for the /mcp-prune skill.
"""
import argparse
import asyncio
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")  # Windows cp949 can't print the emoji below

sys.path.insert(0, str(Path(__file__).parent))

from inventory import list_servers
from parse_logs import count_calls, count_calls_by_tool
from schema_cost import estimate_all

ROI_REVIEW_THRESHOLD = 500  # tokens spent per actual call above which we flag for review


def build_rows(servers: dict, usage: dict, costs: dict) -> list:
    rows = []
    for name in servers:
        calls = usage.get(name, {}).get("calls", 0)
        cost_info = costs.get(name, {})
        if "error" in cost_info:
            rows.append({"name": name, "cost": None, "calls": calls, "roi": None, "note": cost_info["error"]})
            continue
        cost = cost_info["cost_tokens"]
        roi = cost / max(1, calls)
        rows.append({
            "name": name, "cost": cost, "calls": calls, "roi": roi,
            "note": "", "approx": cost_info.get("approx", False),
        })
    # worst ROI (most expensive per call) first; unmeasurable servers last
    rows.sort(key=lambda r: (r["roi"] is None, -(r["roi"] or 0)))
    return rows


def render_markdown(rows: list) -> str:
    lines = [
        "| 서버 | 세션당 비용 | 호출횟수 | ROI(비용/호출) | 권고 |",
        "|---|---|---|---|---|",
    ]
    remove_cmds = []
    any_approx = False
    for r in rows:
        if r["cost"] is None:
            lines.append(f"| {r['name']} | 측정불가 | {r['calls']} | - | ⚪ {r['note']} |")
            continue
        if r["calls"] == 0:
            verdict = "🔴 제거 권장"
            remove_cmds.append(r["name"])
        elif r["roi"] > ROI_REVIEW_THRESHOLD:
            verdict = "🟡 검토"
        else:
            verdict = "🟢 유지"
        cost_str = f"{r['cost']:,} 토큰"
        if r.get("approx"):
            cost_str = "~" + cost_str
            any_approx = True
        lines.append(f"| {r['name']} | {cost_str} | {r['calls']} | {r['roi']:.0f} | {verdict} |")

    if any_approx:
        lines.append("")
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
    """Per-tool breakdown across all servers, not just the server rollup."""
    rows = []
    for server, cost_info in costs.items():
        for t in cost_info.get("tools", []):
            calls = tool_usage.get((server, t["name"]), 0)
            rows.append({
                "server": server, "tool": t["name"], "cost": t["cost_tokens"],
                "calls": calls, "approx": cost_info.get("approx", False),
            })
    rows.sort(key=lambda r: (r["server"], -r["cost"]))
    return rows


def render_tool_markdown(rows: list) -> str:
    if not rows:
        return ""
    lines = [
        "",
        "### 도구별 상세",
        "| 서버 | 도구 | 비용 | 호출횟수 |",
        "|---|---|---|---|",
    ]
    for r in rows:
        cost_str = f"{r['cost']:,} 토큰"
        if r["approx"]:
            cost_str = "~" + cost_str
        lines.append(f"| {r['server']} | {r['tool']} | {cost_str} | {r['calls']} |")
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Audit MCP servers by cost vs actual usage.")
    parser.add_argument("--days", type=int, default=30, help="session log window in days")
    args = parser.parse_args()

    servers = list_servers()
    if not servers:
        print("설정된 MCP 서버가 없습니다 (.mcp.json / ~/.claude.json 확인).")
        return

    usage = count_calls(days=args.days)
    tool_usage = count_calls_by_tool(days=args.days)
    costs = asyncio.run(estimate_all(servers))

    rows = build_rows(servers, usage, costs)
    print(render_markdown(rows))

    tool_rows = build_tool_rows(costs, tool_usage)
    tool_md = render_tool_markdown(tool_rows)
    if tool_md:
        print(tool_md)


if __name__ == "__main__":
    main()
