"""Locate configured MCP servers by reading Claude Code's own config files.

ponytail: the ~/.claude.json schema isn't publicly documented, so instead of
assuming a fixed shape this walks the JSON recursively for any "mcpServers"
key. Upgrade to a precise schema if Anthropic documents one.
"""
import json
from pathlib import Path

def _iter_config_paths():
    cwd = Path.cwd()
    for parent in [cwd, *cwd.parents]:
        candidate = parent / ".mcp.json"
        if candidate.exists():
            yield candidate
    home = Path.home()
    for rel in (".claude.json", ".claude/settings.json"):
        candidate = home / rel
        if candidate.exists():
            yield candidate


def _find_mcp_servers(obj, source, out):
    if isinstance(obj, dict):
        servers = obj.get("mcpServers")
        if isinstance(servers, dict):
            for name, cfg in servers.items():
                if name not in out and isinstance(cfg, dict):
                    out[name] = {**cfg, "_source": str(source)}
        for value in obj.values():
            _find_mcp_servers(value, source, out)
    elif isinstance(obj, list):
        for item in obj:
            _find_mcp_servers(item, source, out)


def list_servers() -> dict:
    """Return {server_name: {command, args, env, _source}}."""
    servers = {}
    for path in _iter_config_paths():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        _find_mcp_servers(data, path, servers)
    return servers


if __name__ == "__main__":
    found = list_servers()
    if not found:
        print("no MCP servers found in .mcp.json / ~/.claude.json")
    for name, cfg in found.items():
        args = " ".join(cfg.get("args", []))
        print(f"{name}: {cfg.get('command', '?')} {args}  [{cfg['_source']}]")
