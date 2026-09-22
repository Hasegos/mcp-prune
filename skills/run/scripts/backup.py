"""Back up a configured MCP server's JSON config the moment report.py
flags it for removal, so a `claude mcp remove` the user copies from the
report is reversible with one command instead of a permanent decision.
"""
import json
import time
from pathlib import Path

BACKUP_DIR = Path.home() / ".claude" / "mcp-prune" / "removed"


def _to_add_json(cfg: dict) -> dict:
    """Normalize a `list_servers()` entry into `claude mcp add-json` shape.

    @param cfg: One server's entry from `list_servers()` - may carry an
        internal `_source` key that `add-json` doesn't accept, and may
        lack the `type` field `add-json` requires.
    @returns: cfg without `_source`, with `type` set to "stdio" (has a
        `command`) or "http" (has a `url`) if not already present.
    """
    payload = {k: v for k, v in cfg.items() if k != "_source"}
    payload.setdefault("type", "stdio" if "command" in payload else "http")
    return payload


def backup(name: str, cfg: dict) -> Path:
    """Write a restorable snapshot of one server's config to disk.

    @param name: Server name.
    @param cfg: This server's `list_servers()` entry.
    @returns: Path the backup was written to.
    """
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    path = BACKUP_DIR / f"{name}.json"
    path.write_text(
        json.dumps(
            {
                "removed_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
                "add_json": _to_add_json(cfg),
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    return path
