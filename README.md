# mcp-prune

Claude Code plugin that audits configured MCP servers: how many context
tokens each one's tool schemas cost per session, versus how often its
tools were actually called in your recent session logs. Ranks servers by
cost-per-use and suggests `claude mcp remove` for dead weight — plus a
per-tool breakdown so you can see exactly which tool is the expensive one,
with a $ figure next to every token count so the cost isn't just an
abstract number.

Removal is reversible: any server flagged for removal has its config
auto-backed up first, and the report includes the exact command to
restore it.

Decisions are remembered globally (`~/.claude/mcp-prune/history.json`), not
per project: once you tell it to keep a server, it stops re-flagging that
server everywhere — until its cost grows past 1.5x what it was when you
decided. Actual removals are picked up automatically on the next run.

## Install

```
claude plugin marketplace add Hasegos/mcp-prune
claude plugin install mcp-prune@mcp-prune-marketplace
```

Then `/reload-plugins` (or start a new session) and run:

```
/mcp-prune:run
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
/mcp-prune:run
```

or directly:

```
python skills/run/scripts/report.py --days 30
```

Output is two markdown tables: a per-server ranking with removal
recommendations, and a per-tool cost/usage breakdown underneath it.

## Self-check

```
python skills/run/scripts/test_mcp_prune.py
```

## Passive nudge

Installing the plugin also registers a `SessionStart` hook
(`hooks/session_nudge.py`) that runs a fast, local-only check (no server
spawning, no network) at the start of every session. It stays silent
unless it finds a configured server with 0 calls in the last 30 days, in
which case it prints one line pointing you at `/mcp-prune:run` — so you
don't have to remember this plugin exists to benefit from it.

## How it works

See `skills/run/scripts/`:
- `inventory.py` — reads `.mcp.json` / `~/.claude.json` for configured servers
- `parse_logs.py` — counts actual tool calls (per server and per tool) from
  `~/.claude/projects/**/*.jsonl`
- `schema_cost.py` — connects to each server via the `mcp` SDK, sizes its
  tool schemas (server total + per-tool) with Anthropic's `count_tokens`
  endpoint or a free local approximation
- `report.py` — ranks servers by cost ÷ calls, prints both markdown reports
- `backup.py` / `restore.py` — snapshot a flagged server's config before
  removal, and restore it with one command
- `decisions.py` — records keep/removed decisions globally, so a reviewed
  server isn't re-flagged everywhere
