"""Open Notebook CLI entry point.

Lets an external caller ask a scoped question against a single source/file or an
entire notebook and get a distilled text answer on stdout. The answer goes to
stdout; all progress/diagnostics go to stderr so the output is safe to capture.

Examples::

    open-notebook source "SPI Spec" "Which registers must be programmed, their addresses, and the init sequence?"
    open-notebook notebook "Hardware Docs" "Summarize the SPI controller init flow"
    open-notebook list-notebooks
    open-notebook list-sources --notebook "Hardware Docs"
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Optional

from open_notebook.cli.client import CLIClient, CLIError


def _eprint(message: str) -> None:
    print(message, file=sys.stderr)


def _emit_answer(answer: str, target_id: str, session_id: str, as_json: bool) -> None:
    if as_json:
        print(
            json.dumps(
                {"answer": answer, "target_id": target_id, "session_id": session_id}
            )
        )
    else:
        print(answer)


def cmd_source(client: CLIClient, args: argparse.Namespace) -> int:
    source_id = client.resolve_source(args.target)
    _eprint(f"[open-notebook] querying source {source_id} ...")

    session_id = args.session or client.create_source_session(
        source_id, model_override=args.model
    )
    ephemeral = args.session is None and not args.keep_session
    try:
        answer = client.stream_source_message(
            source_id, session_id, args.query, model_override=args.model
        )
    finally:
        if ephemeral:
            _safe_delete(lambda: client.delete_source_session(source_id, session_id))

    if not answer:
        _eprint("[open-notebook] warning: empty answer returned.")
    _emit_answer(answer, source_id, session_id, args.json)
    return 0


def cmd_notebook(client: CLIClient, args: argparse.Namespace) -> int:
    notebook_id = client.resolve_notebook(args.target)
    _eprint(f"[open-notebook] querying notebook {notebook_id} ...")

    session_id = args.session or client.create_notebook_session(
        notebook_id, model_override=args.model
    )
    ephemeral = args.session is None and not args.keep_session
    try:
        context = client.build_notebook_context(notebook_id, full=args.full)
        answer = client.execute_notebook_chat(
            session_id, args.query, context, model_override=args.model
        )
    finally:
        if ephemeral:
            _safe_delete(lambda: client.delete_notebook_session(session_id))

    if not answer:
        _eprint("[open-notebook] warning: empty answer returned.")
    _emit_answer(answer, notebook_id, session_id, args.json)
    return 0


def cmd_list_notebooks(client: CLIClient, args: argparse.Namespace) -> int:
    notebooks = client.list_notebooks()
    if args.json:
        print(json.dumps(notebooks))
        return 0
    if not notebooks:
        _eprint("No notebooks found.")
        return 0
    for nb in notebooks:
        print(f"{nb.get('id')}\t{nb.get('name', '(unnamed)')}")
    return 0


def cmd_list_sources(client: CLIClient, args: argparse.Namespace) -> int:
    notebook_id: Optional[str] = None
    if args.notebook:
        notebook_id = client.resolve_notebook(args.notebook)
    sources = client.list_sources(notebook_id)
    if args.json:
        print(json.dumps(sources))
        return 0
    if not sources:
        _eprint("No sources found.")
        return 0
    for src in sources:
        print(f"{src.get('id')}\t{src.get('title') or '(untitled)'}")
    return 0


def _safe_delete(fn) -> None:
    try:
        fn()
    except CLIError as exc:
        _eprint(f"[open-notebook] warning: session cleanup failed: {exc}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="open-notebook",
        description="Query Open Notebook sources or notebooks from the command line.",
    )
    parser.add_argument(
        "--base-url",
        default=None,
        help="Open Notebook API base URL (default: $API_BASE_URL or http://127.0.0.1:5055).",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # Shared options for the two chat commands.
    def add_chat_options(p: argparse.ArgumentParser) -> None:
        p.add_argument("target", help="Source/notebook id, or name/title to resolve.")
        p.add_argument("query", help="The question to ask.")
        p.add_argument(
            "--model", default=None, help="Optional model id override for this query."
        )
        p.add_argument(
            "--session",
            default=None,
            help="Reuse an existing chat session id (disables auto-cleanup).",
        )
        p.add_argument(
            "--keep-session",
            action="store_true",
            help="Do not delete the ephemeral session after the query.",
        )
        p.add_argument(
            "--json",
            action="store_true",
            help="Emit a JSON object {answer, target_id, session_id} instead of text.",
        )

    p_source = sub.add_parser(
        "source", help="Chat with a single source/file (chat with sources)."
    )
    add_chat_options(p_source)
    p_source.set_defaults(func=cmd_source)

    p_notebook = sub.add_parser(
        "notebook", help="Chat with an entire notebook (chat with notebook)."
    )
    add_chat_options(p_notebook)
    p_notebook.add_argument(
        "--full",
        action="store_true",
        help="Include full source/note content in context (default: short).",
    )
    p_notebook.set_defaults(func=cmd_notebook)

    p_ln = sub.add_parser("list-notebooks", help="List notebooks (id and name).")
    p_ln.add_argument("--json", action="store_true", help="Emit raw JSON.")
    p_ln.set_defaults(func=cmd_list_notebooks)

    p_ls = sub.add_parser("list-sources", help="List sources (id and title).")
    p_ls.add_argument(
        "--notebook", default=None, help="Filter by notebook id or name."
    )
    p_ls.add_argument("--json", action="store_true", help="Emit raw JSON.")
    p_ls.set_defaults(func=cmd_list_sources)

    return parser


def main(argv: Optional[list] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    client = CLIClient(base_url=args.base_url)
    try:
        return args.func(client, args)
    except CLIError as exc:
        _eprint(f"[open-notebook] error: {exc}")
        return 1
    except KeyboardInterrupt:
        _eprint("[open-notebook] interrupted.")
        return 130


if __name__ == "__main__":
    sys.exit(main())
