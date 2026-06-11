---
name: open-notebook-cli
description: >-
  Get focused, LLM-distilled answers from documents (specs, datasheets, manuals,
  papers, internal docs) in Open Notebook via the `open-notebook` CLI, instead
  of reading whole files into context. Use when a task needs docs in Open
  Notebook — the user names a spec/manual/notebook, points at a source, says the
  answer is "in the notebook", or the project uses it as its knowledge base.
  Best for pulling specific facts (register addresses, API contracts, config
  steps, parameter values) from large docs.
---

# Open Notebook CLI

Ask a scoped question about one **source** (a single document) and get back a distilled text answer — instead of reading a large reference into context.

**Always query a single source, never a whole notebook.** Notebook-wide queries dilute context across many documents and give vaguer answers. Use `list-sources` to find the exact file, then query it directly.

## Setup

Detect how it runs: `open-notebook --help`. If that fails, prefix with `uv run` from an Open Notebook checkout. Env vars (usually preset): `API_BASE_URL` (default `http://127.0.0.1:5055`), `OPEN_NOTEBOOK_PASSWORD` (auth token), `API_CLIENT_TIMEOUT` (default `300`).

## Commands

```bash
open-notebook list-notebooks
open-notebook list-sources [--notebook <id|name>]
open-notebook source <id|title> "question"   # query ONE document — always use this
```

**Prefer the full `source:` id** (e.g. `source:abc123`) ? it resolves across ALL notebooks. Bare ids and names only resolve within the DEFAULT notebook; passing a bare id from a non-default notebook fails with "No source matched". Always copy the full `source:...` string from `list-sources` output.

## Usage

1. **Find the source.** `list-sources` with NO `--notebook` lists only the DEFAULT notebook ? an empty grep here does NOT mean the doc is absent. If you don't see it, run `list-notebooks`, then `list-sources --notebook <name>` for the likely notebook. Copy the full `source:...` id; don't guess ids.
2. **Query that one source** with `open-notebook source`. If unsure which file, narrow it down first rather than querying the whole notebook.
3. **Ask precisely** — name concrete artifacts and request usable structure (e.g. "list each register's name, address, and value to write, in order"). Avoid vague prompts.
4. **Use stdout** — answer is plain text on stdout, diagnostics on stderr, exit `0` on success. Write code from the facts without opening the raw doc.

## Going deeper

- **Multi-turn follow-ups** — if one answer isn't complete or detailed enough, keep asking. Capture the `session_id` (via `--json`) and pass `--session <id>` on follow-ups so the model remembers earlier turns and you can drill into specifics until the picture is full.
- **Parallel sub-agents**  when you need several distinct facts, spawn multiple sub-agents that each query Open Notebook with a different question (same or different sources) concurrently, then aggregate their answers. This is faster than asking one big question and keeps each query sharply scoped. Give each agent a SELF-CONTAINED prompt: the verbatim question(s) AND the full `source:<id>` (never a bare id ? the sub-agent can't see your `list-sources` output). Tell it the retry recipe: "if 'No source matched', the id needs the `source:` prefix."

## Flags (`source`)

| Flag | Effect |
|---|---|
| `--json` | Emit `{answer, target_id, session_id}`. |
| `--session <id>` | Reuse a session for multi-turn memory (else ephemeral, auto-deleted). |
| `--keep-session` | Don't delete the session afterward. |
| `--model <id>` / `--base-url <url>` | Override model / API URL. |

## Troubleshooting

- **"Could not reach the API"** — server down or `API_BASE_URL` wrong; tell the user, don't retry blindly.
- **"No source matched"**  almost always a bare id from a non-default notebook. Re-run with the FULL `source:<id>` prefix. If still failing, `list-notebooks` ? `list-sources --notebook <name>` to get the correct full id; do not conclude the doc is missing until you've checked every notebook.
- **Thin answer** — ask more specifically, or confirm you're querying the right source.