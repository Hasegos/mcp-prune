"""ponytail self-check: run `python test_mcp_prune.py` directly. No framework."""
from inventory import _find_mcp_servers
from parse_logs import server_of
from report import build_rows, render_markdown


def test_server_of():
    assert server_of("mcp__notion__search") == "notion"
    assert server_of("Bash") is None
    assert server_of("mcp__a") is None  # missing tool segment


def test_find_mcp_servers_nested():
    out = {}
    data = {"projects": {"/x": {"mcpServers": {"foo": {"command": "node"}}}}}
    _find_mcp_servers(data, "test", out)
    assert out["foo"]["command"] == "node"


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


if __name__ == "__main__":
    test_server_of()
    test_find_mcp_servers_nested()
    test_build_rows_and_ranking()
    print("OK - all self-checks passed")
