"""ponytail self-check: run `python test_mcp_prune.py` directly. No framework."""
from inventory import _find_mcp_servers
from parse_logs import _event_time, bare_tool_name, server_of
from report import build_rows, build_tool_rows, render_markdown, render_tool_markdown


def test_server_of():
    assert server_of("mcp__notion__search") == "notion"
    assert server_of("Bash") is None
    assert server_of("mcp__a") is None  # missing tool segment


def test_bare_tool_name():
    assert bare_tool_name("mcp__notion__search") == "search"
    assert bare_tool_name("mcp__notion__create_page") == "create_page"
    assert bare_tool_name("Bash") is None


def test_event_time():
    assert _event_time({"timestamp": "2026-09-18T00:49:24.052Z"}) is not None
    assert _event_time({"timestamp": "not-a-date"}) is None
    assert _event_time({}) is None  # missing field -> caller falls back to file mtime


def test_find_mcp_servers_nested():
    data = {"projects": {"/x": {"mcpServers": {"foo": {"command": "node"}}}}}

    matching = {}
    _find_mcp_servers(data, "test", matching, "/x")
    assert matching["foo"]["command"] == "node"

    other_project = {}
    _find_mcp_servers(data, "test", other_project, "/y")
    assert "foo" not in other_project  # unrelated project's servers must not leak in


def test_build_rows_and_ranking():
    servers = {"dead": {}, "alive": {}}
    usage = {"alive": {"calls": 10}}
    costs = {
        "dead": {"cost_tokens": 4000, "tool_count": 3},
        "alive": {"cost_tokens": 1000, "tool_count": 2},
    }
    rows = build_rows(servers, usage, costs)
    assert rows[0]["name"] == "dead"  # 0 calls -> ranked worst first
    md = render_markdown(rows)
    assert "claude mcp remove dead -s user" in md


def test_build_tool_rows():
    costs = {
        "notion": {
            "approx": True,
            "tools": [
                {"name": "search", "cost_tokens": 300},
                {"name": "create_page", "cost_tokens": 900},
            ],
        }
    }
    tool_usage = {("notion", "search"): {"calls": 5, "last_used": None}}  # create_page never called
    rows = build_tool_rows(costs, tool_usage)
    assert rows[0]["tool"] == "create_page"  # sorted by cost desc within server
    assert rows[1]["calls"] == 5
    md = render_tool_markdown(rows)
    assert "create_page" in md and "~900 토큰" in md and "사용 안 함" in md


if __name__ == "__main__":
    test_server_of()
    test_bare_tool_name()
    test_event_time()
    test_find_mcp_servers_nested()
    test_build_rows_and_ranking()
    test_build_tool_rows()
    print("OK - all self-checks passed")
