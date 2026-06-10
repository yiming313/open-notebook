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

Accepts a full id (`source:abc123`), bare id, or case-insensitive name.

## Usage

1. **Find the source** with `list-sources` — identify the single file that holds the answer; don't guess ids.
2. **Query that one source** with `open-notebook source`. If unsure which file, narrow it down first rather than querying the whole notebook.
3. **Ask precisely** — name concrete artifacts and request usable structure (e.g. "list each register's name, address, and value to write, in order"). Avoid vague prompts.
4. **Use stdout** — answer is plain text on stdout, diagnostics on stderr, exit `0` on success. Write code from the facts without opening the raw doc.

## Going deeper

- **Multi-turn follow-ups** — if one answer isn't complete or detailed enough, keep asking. Capture the `session_id` (via `--json`) and pass `--session <id>` on follow-ups so the model remembers earlier turns and you can drill into specifics until the picture is full.
- **Parallel sub-agents** — when you need several distinct facts, spawn multiple sub-agents that each query Open Notebook with a different question (same or different sources) concurrently, then aggregate their answers. This is faster than asking one big question and keeps each query sharply scoped.

## Flags (`source`)

| Flag | Effect |
|---|---|
| `--json` | Emit `{answer, target_id, session_id}`. |
| `--session <id>` | Reuse a session for multi-turn memory (else ephemeral, auto-deleted). |
| `--keep-session` | Don't delete the session afterward. |
| `--model <id>` / `--base-url <url>` | Override model / API URL. |

## Troubleshooting

- **"Could not reach the API"** — server down or `API_BASE_URL` wrong; tell the user, don't retry blindly.
- **Ambiguous / no match** — re-run with a full id, or list first to find it.
- **Thin answer** — ask more specifically, or confirm you're querying the right source.
