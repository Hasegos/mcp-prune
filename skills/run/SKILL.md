---
description: Audit configured MCP servers by actual usage vs context-token cost, and recommend which to remove. Use when the user asks to check MCP server usage, context cost, or wants to prune unused MCP servers.
---

Run `python scripts/report.py --days 30` from this skill's directory
(install dependencies first with `pip install -r ../../requirements.txt`
if the `mcp` package is missing — check with a quick import attempt before
installing anything).

`ANTHROPIC_API_KEY` is optional. If set, costs are exact (Anthropic's
count_tokens endpoint). If not set, costs are a free local approximation
(~4 chars/token) and the report marks them with `~` — proceed without it,
do not ask the user to set it up.

The script prints two markdown tables: a per-server ranking (cost vs actual
use, with removal recommendations) and a per-tool breakdown underneath it.
Show BOTH tables to the user verbatim in your response so they render as
tables. Do not summarize them away or paraphrase the numbers — the tables
themselves are the deliverable.

If any server shows an error (failed to connect), mention it in one line
below the tables without doing extra troubleshooting yourself.
