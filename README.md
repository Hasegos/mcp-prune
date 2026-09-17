# mcp-prune

Claude Code plugin that audits configured MCP servers: how many context
tokens each one's tool schemas cost per session, versus how often its
tools were actually called in your recent session logs. Ranks servers by
cost-per-use and suggests `claude mcp remove` for dead weight.

## Install

```
claude plugin marketplace add <this-repo>
claude plugin install mcp-prune
```

## Requirements

```
pip install -r requirements.txt
```

`ANTHROPIC_API_KEY` is optional:
- **set** → exact token costs via Anthropic's count_tokens endpoint (a paid
  Console API key, separate from a Claude Code subscription)
- **unset** → free local approximation (~4 chars/token), marked `~` in the
  report

Most people can just skip the API key.

## Usage

```
/mcp-prune
```

or directly:

```
python skills/mcp-prune/scripts/report.py --days 30
```

## Self-check

```
python skills/mcp-prune/scripts/test_mcp_prune.py
```

## How it works

See `skills/mcp-prune/scripts/`:
- `inventory.py` — reads `.mcp.json` / `~/.claude.json` for configured servers
- `parse_logs.py` — counts actual tool calls from `~/.claude/projects/**/*.jsonl`
- `schema_cost.py` — connects to each server via the `mcp` SDK, sizes its
  tool schemas with Anthropic's `count_tokens` endpoint
- `report.py` — ranks servers by cost ÷ calls, prints a markdown report