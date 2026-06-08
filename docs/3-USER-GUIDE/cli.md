# Command-Line Interface (CLI)

The `open-notebook` CLI lets you ask a **scoped question** against a single
source/file or an entire notebook and get back a **distilled text answer** on
stdout — without loading the raw document yourself.

This is especially useful for **coding agents** (e.g. Claude Code). Instead of
ingesting an entire specification, an agent can shell out to the CLI and ask a
focused question:

```bash
open-notebook source "SPI Spec" \
  "Which registers must be programmed, what are their addresses, and what is the init sequence?"
```

The CLI turns that into an Open Notebook *chat-with-source* request, runs it
through the configured LLM, and prints only the answer — which the agent then
uses as context to write code.

---

## Prerequisites

The CLI is a **thin HTTP client over the running API**. Before using it:

1. Start SurrealDB and the API server (see
   [1-INSTALLATION](../1-INSTALLATION/index.md)). For local dev:
   ```bash
   uv run python run_api.py
   ```
2. Make sure you have at least one ingested source or notebook.

---

## Installation

The CLI ships with the package. After installing Open Notebook it is available
as `open-notebook`:

```bash
uv run open-notebook --help     # from a source checkout
# or simply:
open-notebook --help            # once the package is installed
```

---

## Configuration

The CLI reads the same environment variables as the rest of the stack:

| Variable | Purpose | Default |
|---|---|---|
| `API_BASE_URL` | API server base URL | `http://127.0.0.1:5055` |
| `OPEN_NOTEBOOK_PASSWORD` | Bearer token, if the server requires auth | _(none)_ |
| `API_CLIENT_TIMEOUT` | Request timeout in seconds (LLM calls can be slow) | `300` |
| `ON_CLI_CLIENT_ID` | Session-owner id the CLI sends as `X-Client-ID` | `open-notebook-cli` |

You can also override the URL per-invocation with `--base-url`.

---

## Commands

### `source` — chat with a single source/file

```bash
open-notebook source <source-id-or-title> "<your question>"
```

- `<source-id-or-title>` accepts a full id (`source:abc123`), a bare id
  (`abc123`), or a case-insensitive title match.
- Scopes the answer to that one document.

### `notebook` — chat with an entire notebook

```bash
open-notebook notebook <notebook-id-or-name> "<your question>"
```

- `<notebook-id-or-name>` accepts a full id (`notebook:xyz`), a bare id, or a
  case-insensitive name match.
- By default the notebook's sources/notes are included at short depth. Add
  `--full` to include full content (larger context, slower, more tokens).

### Discovery helpers

```bash
open-notebook list-notebooks               # id<TAB>name
open-notebook list-sources                 # all sources
open-notebook list-sources --notebook Docs # sources in one notebook
```

---

## Common options (for `source` and `notebook`)

| Option | Effect |
|---|---|
| `--model <model_id>` | Override the chat model for this query. |
| `--session <id>` | Reuse an existing chat session (enables multi-turn memory; disables auto-cleanup). |
| `--keep-session` | Keep the ephemeral session instead of deleting it. |
| `--json` | Emit `{"answer", "target_id", "session_id"}` instead of plain text. |
| `--full` | (`notebook` only) Include full source/note content in context. |

By default each query is **ephemeral**: the CLI creates a session, fetches the
answer, then deletes the session (and its conversation checkpoint).

The **answer goes to stdout**; progress and errors go to **stderr**, so output
is safe to capture:

```bash
ANSWER=$(open-notebook source "SPI Spec" "List the init registers and addresses")
```

The process exits `0` on success and non-zero on failure.

---

## Example: agent workflow

```bash
# Resolve what's available
open-notebook list-sources

# Ask a focused question and capture just the answer
open-notebook source "SPI Spec" \
  "Which registers must be programmed for controller init, their addresses, and the exact sequence?"
```

The agent receives a concise, document-grounded answer and writes the test
sequence from it — never having to load the full SPI specification.
