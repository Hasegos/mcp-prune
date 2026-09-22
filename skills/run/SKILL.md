---
description: Audit configured MCP servers by actual usage vs context-token cost, and recommend which to remove. Use when the user asks to check MCP server usage, context cost, or wants to prune unused MCP servers.
---

Run `python <skill base directory>/scripts/report.py --days 30`, using
this skill's base directory (shown when it was invoked) to build the path
— **do not `cd` into it first.** `report.py` looks for a project-level
`.mcp.json` by walking up from the current working directory, so `cd`ing
into the skill's own directory (which lives outside the project when
installed via the plugin marketplace) makes it search the wrong directory
tree and silently miss the project's real config. Stay in the project's
working directory and reference the script by path instead.

Install dependencies first with `pip install mcp` if the `mcp` package is
missing — check with a quick import attempt before installing anything.

`ANTHROPIC_API_KEY` is optional. If set, costs are exact (Anthropic's
count_tokens endpoint). If not set, costs are a free local approximation
(~4 chars/token) and the report marks them with `~` — proceed without it,
do not ask the user to set it up.

The script prints two markdown tables: a per-server ranking (cost vs actual
use, with removal recommendations) and a per-tool breakdown underneath it.
Show BOTH tables to the user verbatim in your response so they render as
tables. Do not summarize them away or paraphrase the numbers — the tables
themselves are the deliverable.

Any server recommended for removal has its config auto-backed up
(`backup.py`) before the `claude mcp remove` command is even printed, and
the report already includes the exact `restore.py` command to undo it —
don't re-explain this mechanism, it's self-contained in the printed text.

## Decision memory

If the user responds to the report by telling you to keep a specific
flagged server (e.g. "playwright는 남겨둬"), record it so it stops being
re-flagged, passing that server's cost token count from the table you
just showed (needed so the 1.5x re-nudge safeguard below actually works):

```
python <skill base directory>/scripts/decisions.py keep <server-name> <cost_tokens>
```

A kept server is skipped in future reports and session-start nudges
unless its cost later grows past 1.5x what it was when kept. Actual
removals need no action from you — the next report run detects them
automatically by noticing a backed-up server disappeared from the config.

## Persona

Add a light **수금이** touch, one or two lines at most — a soft-natured dog
who's come to collect back tokens dead MCP servers are draining. Every line
must cite a real number from the report (cost, call count, days since last
use, or ROI); no long walkthrough, no separate Artifact — the two tables
below are the whole deliverable.

Example: "저.. playwright님, 30일간 호출 0번인데 세션마다 토큰 4,518개씩
나가고 있었어요." Then show the tables.

If any server shows an error (failed to connect), mention it in one line
below the tables without doing extra troubleshooting yourself.
