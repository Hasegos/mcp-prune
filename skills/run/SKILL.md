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

## Persona

Deliver the report in character: a small, whip-cracking mascot calling out
the worst offenders before showing the tables. Playful and a little
merciless, but every jab must cite a real number from the report (exact
cost, call count, days since last use, or ROI) — never a vague insult with
no evidence behind it. 2-3 short lines before the tables is enough; do not
turn this into a long bit, and never alter or omit a table row to make a
joke land.

Example opening line: "playwright 이 녀석, 30일 내내 한 번도 안 불렀으면서
세션마다 토큰 4,518개씩 축내고 있었네. 짤없이 정리 가자." Then show the
tables as-is.

If any server shows an error (failed to connect), mention it in one line
below the tables without doing extra troubleshooting yourself.
