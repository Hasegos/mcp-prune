"""Persist per-server keep/removed decisions globally (not per-project), so
a server the user has already reviewed isn't flagged again in every future
report or session-start nudge - see report.py and hooks/session_nudge.py.
"""
import json
import time
from pathlib import Path

HISTORY_PATH = Path.home() / ".claude" / "mcp-prune" / "history.json"

# A "keep" decision holds only while cost hasn't grown past this multiple
# of what it was when the user decided - past that, enough changed to be
# worth asking about again.
RENUDGE_COST_MULTIPLIER = 1.5


def load() -> dict:
    """Read the global decision history.

    @returns: {server_name: {"decision": "keep"|"removed", "decided_at": str,
        "cost_tokens": int|None}}. {} if no history file exists yet.
    """
    try:
        return json.loads(HISTORY_PATH.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _save(history: dict):
    """Write the global decision history, creating its directory if needed.

    @param history: The full history dict to persist.
    @returns: None.
    """
    HISTORY_PATH.parent.mkdir(parents=True, exist_ok=True)
    HISTORY_PATH.write_text(json.dumps(history, ensure_ascii=False, indent=2), encoding="utf-8")


def record(name: str, decision: str, cost_tokens=None):
    """Record a decision for one server, overwriting any prior one.

    @param name: Server name.
    @param decision: "keep" or "removed".
    @param cost_tokens: This server's cost at decision time (used later to
        detect a material cost increase that should re-open the review).
    @returns: None.
    """
    history = load()
    history[name] = {
        "decision": decision,
        "decided_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "cost_tokens": cost_tokens,
    }
    _save(history)


def is_kept(name: str, history: dict) -> bool:
    """Whether a server has a recorded "keep" decision, cost-blind.

    @param name: Server name.
    @param history: A pre-loaded history dict (see `load()`).
    @returns: True if the last recorded decision for this server is "keep".
    """
    return history.get(name, {}).get("decision") == "keep"


def is_settled(name: str, current_cost_tokens, history: dict = None) -> bool:
    """Whether a server's prior "keep" decision still holds.

    @param name: Server name.
    @param current_cost_tokens: This run's measured cost for the server, or
        None if unmeasured (then cost growth can't be checked, so a "keep"
        decision holds unconditionally).
    @param history: A pre-loaded history dict, or None to load it fresh.
    @returns: True if kept before and cost hasn't grown past
        RENUDGE_COST_MULTIPLIER since - False otherwise (never decided,
        decided "removed", or cost grew enough to re-ask).
    """
    history = history if history is not None else load()
    if not is_kept(name, history):
        return False
    decided_cost = history[name].get("cost_tokens")
    if decided_cost is None or current_cost_tokens is None:
        return True
    return current_cost_tokens <= decided_cost * RENUDGE_COST_MULTIPLIER


def sync_removed(current_servers: set, history: dict = None) -> dict:
    """Auto-record "removed" for any server that has a backup but is no
    longer configured - i.e. the user actually ran `claude mcp remove`
    since the last report, with no separate chat-parsed step needed.

    @param current_servers: Names from this run's `list_servers()`.
    @param history: A pre-loaded history dict, or None to load it fresh.
    @returns: The (possibly updated) history dict, already saved if changed.
    """
    from backup import BACKUP_DIR

    history = history if history is not None else load()
    if not BACKUP_DIR.exists():
        return history
    changed = False
    for backup_file in BACKUP_DIR.glob("*.json"):
        name = backup_file.stem
        if name not in current_servers and history.get(name, {}).get("decision") != "removed":
            history[name] = {
                "decision": "removed",
                "decided_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
                "cost_tokens": None,
            }
            changed = True
    if changed:
        _save(history)
    return history


if __name__ == "__main__":
    import sys

    if len(sys.argv) not in (3, 4) or sys.argv[1] not in ("keep", "removed"):
        print("usage: python decisions.py keep|removed <server-name> [cost_tokens]")
    else:
        cost = int(sys.argv[3]) if len(sys.argv) == 4 else None
        record(sys.argv[2], sys.argv[1], cost_tokens=cost)
        print(f"'{sys.argv[2]}' 결정을 기록했습니다: {sys.argv[1]}")
