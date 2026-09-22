"""ponytail self-check: run `python test_mcp_prune.py` directly. No framework."""
import json

import decisions
from backup import BACKUP_DIR
from inventory import _find_mcp_servers
from parse_logs import _event_time, bare_tool_name, server_of
from report import build_rows, build_tool_rows, render_markdown, render_tool_markdown


def _clear_history(*names):
    """Test cleanup: remove specific keys from the real history.json instead
    of wiping the whole file, since it's a shared global store."""
    history = decisions.load()
    changed = False
    for name in names:
        if history.pop(name, None) is not None:
            changed = True
    if changed:
        decisions.HISTORY_PATH.write_text(json.dumps(history, ensure_ascii=False), encoding="utf-8")


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
    servers = {"dead": {"command": "node"}, "alive": {}}
    usage = {"alive": {"calls": 10}}
    costs = {
        "dead": {"cost_tokens": 4000, "tool_count": 3},
        "alive": {"cost_tokens": 1000, "tool_count": 2},
    }
    rows = build_rows(servers, usage, costs)
    assert rows[0]["name"] == "dead"  # 0 calls -> ranked worst first
    md = render_markdown(rows, servers, {})
    assert "claude mcp remove dead -s user" in md
    assert "restore.py" in md

    backup_path = BACKUP_DIR / "dead.json"
    assert backup_path.exists()  # a removal recommendation auto-backs up the config
    backup_path.unlink()  # test cleanup - don't leave artifacts in the real home dir


def test_decisions_settle_and_renudge():
    decisions.record("kept-server", "keep", cost_tokens=1000)
    history = decisions.load()
    assert decisions.is_kept("kept-server", history)
    assert decisions.is_settled("kept-server", 1000, history)  # unchanged cost -> still settled
    assert decisions.is_settled("kept-server", 1400, history)  # +40% -> still under the 1.5x bar
    assert not decisions.is_settled("kept-server", 2000, history)  # +100% -> re-open the review
    assert not decisions.is_settled("never-reviewed", 100, history)
    _clear_history("kept-server")


def test_render_markdown_skips_kept_server():
    servers = {"kept": {"command": "node"}}
    usage = {}
    costs = {"kept": {"cost_tokens": 1000, "tool_count": 1}}
    rows = build_rows(servers, usage, costs)
    decisions.record("kept", "keep", cost_tokens=1000)
    history = decisions.load()
    md = render_markdown(rows, servers, history)
    assert "리뷰 완료" in md
    assert "claude mcp remove kept" not in md  # a settled "keep" is never re-flagged
    assert not (BACKUP_DIR / "kept.json").exists()  # no backup - nothing was flagged
    _clear_history("kept")


def test_sync_removed_detects_actual_removal():
    from backup import backup as backup_server

    backup_server("ghost", {"command": "node"})
    history = decisions.sync_removed(set())  # server no longer in current config
    assert history["ghost"]["decision"] == "removed"
    (BACKUP_DIR / "ghost.json").unlink()
    _clear_history("ghost")


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
    test_decisions_settle_and_renudge()
    test_render_markdown_skips_kept_server()
    test_sync_removed_detects_actual_removal()
    print("OK - all self-checks passed")
