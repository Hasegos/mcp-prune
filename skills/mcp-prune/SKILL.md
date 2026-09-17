---
name: mcp-prune
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

Show the full markdown table output to the user verbatim in your response
so it renders as a table. Do not summarize it away or paraphrase the
numbers — the table itself is the deliverable.

If any server shows an error (failed to connect), mention it in one line
below the table without doing extra troubleshooting yourself.