---
name: open-notebook-cli
description: >-
  Retrieve focused, LLM-distilled answers from documents (specs, datasheets,
  manuals, papers, internal docs) stored in Open Notebook using the
  `open-notebook` CLI, instead of reading whole source files into context. Use
  this skill whenever a task depends on documentation that lives in Open
  Notebook — for example the user references a spec/datasheet/manual/notebook by
  name, points you at an Open Notebook source, says the answer is "in the
  notebook" or "in open notebook", or the project is configured to use Open
  Notebook as its knowledge base. It is especially valuable when you need
  specific facts — register addresses, API contracts, configuration steps,
  pin assignments, procedures, parameter values — out of a large document you
  would otherwise have to ingest in full. Prefer asking Open Notebook a precise
  question over loading the raw document.
---

# Using the Open Notebook CLI

## What this is and why it matters

Open Notebook is a self-hosted research assistant that holds ingested documents
(PDFs, web pages, transcripts, notes) and can answer questions about them with an
LLM that already has the full text in context. The `open-notebook` CLI is a thin
client over its API: you send a **scoped question** about one document (a
"source") or a whole "notebook", and it prints back a **distilled text answer**.

The reason to use it: when a task depends on a large reference document — a
500-page chip datasheet, a protocol spec, an API manual — pulling the whole thing
into your context is slow, expensive, and crowds out the actual work. Instead,
ask Open Notebook the specific question you need answered ("which registers
configure the SPI clock, and what are their addresses and reset values?") and get
back just the relevant facts. You stay focused on writing code; Open Notebook does
the document reading.

Think of it as a knowledgeable colleague who has already read the manual. You ask
them a pointed question; you don't borrow the manual and read it cover to cover.

## When to use it

Reach for this skill when **the information you need lives in Open Notebook**:

- The user names a document/spec/manual/notebook and expects you to consult it.
- The user says things like "check the notebook", "it's in open notebook", "ask
  the SPI spec", or points you at a source.
- The project's instructions (e.g. `CLAUDE.md`) say to use Open Notebook as the
  source of truth for certain domain knowledge.

Do **not** invent an Open Notebook dependency where none exists. If there is no
sign the relevant docs are in Open Notebook, solve the task normally. If you
suspect it but aren't sure, a quick `open-notebook list-notebooks` (below) tells
you whether a server with relevant content is even reachable.

## Step 0: Confirm the CLI is available

The command may be installed globally as `open-notebook`, or only runnable from an
Open Notebook checkout via `uv run open-notebook`. Detect which:

```bash
open-notebook --help 2>/dev/null && echo "GLOBAL" \
  || echo "try: cd <open-notebook-repo> && uv run open-notebook --help"
```

If the global command is missing, look for the repo (often the project you're in,
or a sibling directory) and prefix commands with `uv run` from there. Everywhere
below, `open-notebook ...` means "the working invocation you found".

The CLI talks to a running API server. Relevant environment variables (usually
already set in the user's shell or the repo's `.env`):

| Variable | Purpose | Default |
|---|---|---|
| `API_BASE_URL` | API server URL | `http://127.0.0.1:5055` |
| `OPEN_NOTEBOOK_PASSWORD` | Bearer token if the server requires auth | _(none)_ |
| `API_CLIENT_TIMEOUT` | Request timeout, seconds (LLM calls are slow) | `300` |

If a command fails with "Could not reach the Open Notebook API … Is the server
running?", the server isn't up. Tell the user rather than guessing — they may need
to start it (`uv run python run_api.py` in the repo) or set `API_BASE_URL`.

## Step 1: Discover what's available

Don't guess ids. List what exists, then match the user's reference to a real
notebook or source. Output is `id<TAB>name`:

```bash
open-notebook list-notebooks
open-notebook list-sources                      # every source
open-notebook list-sources --notebook "Hardware Docs"   # scoped to one notebook
```

You can pass either a full id (`source:abc123`), a bare id (`abc123`), or a
case-insensitive name/title — the CLI resolves names for you and will tell you if
a name is ambiguous or unknown.

## Step 2: Choose the right scope

**Query one source** when you know which single document holds the answer (a
specific datasheet, one RFC, one paper). It's the most precise and the cheapest.

```bash
open-notebook source <id|title> "<your question>"
```

**Query a whole notebook** when the answer may be spread across several documents
in a topic, or you don't know which source has it.

```bash
open-notebook notebook <id|name> "<your question>"
# add --full to include complete source/note content instead of summaries
# (larger, slower, more tokens — use only when summaries miss detail)
```

Default to **source** scope when you can identify the document — narrower context
means a sharper answer. Fall back to **notebook** scope when the right source
isn't obvious.

## Step 3: Ask a precise question

This is where the value is won or lost. The CLI just relays your question to an
LLM that has the document; the quality of the answer tracks the quality of the
question. Ask for the concrete artifacts you actually need:

- Name the specific items: "Which registers must be programmed to initialize the
  SPI controller? Give each register's name, address, and the value to write, in
  program order."
- Ask for structure you can act on: "List as a numbered sequence of steps."
- Pull out parameters, not prose: "What are the min/typ/max values for the SPI
  clock setup and hold times?"

Avoid vague prompts ("tell me about SPI") — they waste a round trip and return an
essay. If the first answer is incomplete, ask a **follow-up** narrowing in, rather
than escalating to dumping the whole document into your context.

**Example — Input/Output:**

Input (you run):
```bash
open-notebook source "SPI Spec" \
  "Which registers must be programmed to initialize the SPI controller? \
For each: name, address, and the value to write, in the order they must be set."
```
Output (printed to stdout — use it as context to write code):
```
1. SPI_CTRL (0x40003000): write 0x00000001 to enable the peripheral clock...
2. SPI_BAUD (0x40003008): write the prescaler...
...
```

## Step 4: Use the answer

The answer is plain text on **stdout**; progress/diagnostics go to **stderr**, so
it's safe to capture. Read it, then write your code from the distilled facts —
you generally do **not** need to open the raw document afterward.

To capture programmatically:
```bash
ANSWER=$(open-notebook source "SPI Spec" "List the init registers and addresses")
```
Or get structured output with `--json` (`{"answer", "target_id", "session_id"}`):
```bash
open-notebook source "SPI Spec" "..." --json
```

Exit code is `0` on success, non-zero on failure — check it if scripting.

## Follow-up questions in one conversation

Each query is independent by default (the CLI creates a throwaway chat session,
gets the answer, deletes it). When you want the model to remember earlier
turns — e.g. drilling deeper into the same topic — reuse a session id:

```bash
# First call; note the session id printed on stderr (or use --json to capture it)
open-notebook source "SPI Spec" "Summarize the init sequence" --json
# Then continue that thread:
open-notebook source "SPI Spec" "Now detail step 3's register writes" \
  --session chat_session:<id>
```

`--session` (and `--keep-session`) keep the session alive so the conversation has
memory. Without them, sessions are cleaned up automatically — preferred for
one-off lookups so nothing accumulates server-side.

## Command + flag reference

```
open-notebook source   <id|title> "question"   # chat with one source/file
open-notebook notebook <id|name>  "question"   # chat with a whole notebook
open-notebook list-notebooks
open-notebook list-sources [--notebook <id|name>]
```

Shared flags for `source` / `notebook`:

| Flag | Effect |
|---|---|
| `--model <model_id>` | Override the chat model for this query. |
| `--session <id>` | Reuse a session (multi-turn memory; skips auto-cleanup). |
| `--keep-session` | Don't delete the ephemeral session afterward. |
| `--json` | Emit `{answer, target_id, session_id}` instead of plain text. |
| `--full` | (`notebook` only) Include full content, not summaries. |
| `--base-url <url>` | Override the API URL for this invocation. |

## Handling problems

- **"Could not reach the API … Is the server running?"** — The API server is
  down or `API_BASE_URL` is wrong. Don't retry blindly; surface this to the user.
- **Ambiguous name** ("matched multiple sources: …") — Re-run with a full id from
  the listed candidates, or ask the user which one.
- **No match** — Run `list-sources` / `list-notebooks` and pick the closest, or
  confirm the document is actually in Open Notebook.
- **Empty or thin answer** — Your question may be too broad or the wrong scope.
  Re-ask more specifically, switch from notebook to source scope (or vice versa),
  or add `--full` for a notebook query.

## The mindset

The whole point is **economy of context**: let Open Notebook read the big document
so you don't have to. Before you reach for a Read tool on a giant spec that you
know is in Open Notebook, ask yourself whether a single well-aimed
`open-notebook source …` question would get you the three facts you actually need.
Usually it will.
