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


def _find_mcp_servers(obj, source, out, cwd):
    """Recursively collect mcpServers blocks from a parsed config file.

    A "projects" key maps project paths to their own per-project settings
    (including their own mcpServers block) - only the entry matching `cwd`
    is descended into, so servers configured for unrelated projects that
    happen to share the same ~/.claude.json don't leak into this project's
    audit (and don't get spawned by schema_cost.py under this project's
    invocation).
    """
    if isinstance(obj, dict):
        servers = obj.get("mcpServers")
        if isinstance(servers, dict):
            for name, cfg in servers.items():
                if name not in out and isinstance(cfg, dict):
                    out[name] = {**cfg, "_source": str(source)}
        for key, value in obj.items():
            if key == "projects" and isinstance(value, dict):
                project_cfg = value.get(cwd)
                if isinstance(project_cfg, dict):
                    _find_mcp_servers(project_cfg, source, out, cwd)
                continue
            _find_mcp_servers(value, source, out, cwd)
    elif isinstance(obj, list):
        for item in obj:
            _find_mcp_servers(item, source, out, cwd)


def list_servers() -> dict:
    """Return {server_name: {command, args, env, _source}}."""
    servers = {}
    cwd = str(Path.cwd())
    for path in _iter_config_paths():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        _find_mcp_servers(data, path, servers, cwd)
    return servers


if __name__ == "__main__":
    found = list_servers()
    if not found:
        print("no MCP servers found in .mcp.json / ~/.claude.json")
    for name, cfg in found.items():
        args = " ".join(cfg.get("args", []))
        print(f"{name}: {cfg.get('command', '?')} {args}  [{cfg['_source']}]")
