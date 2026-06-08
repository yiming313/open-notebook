"""Unit tests for the Open Notebook CLI (open_notebook.cli).

These tests exercise the pure logic — id/name resolution, SSE parsing, and
subcommand dispatch — by stubbing out network access on CLIClient. No running
API server is required.
"""

import pytest

from open_notebook.cli.client import CLIClient, CLIError, _match, _parse_sse_line
from open_notebook.cli.main import main

# ---------------------------------------------------------------------------
# _match (id / name resolution)
# ---------------------------------------------------------------------------


SOURCES = [
    {"id": "source:abc", "title": "SPI Spec"},
    {"id": "source:def", "title": "SPI Controller Notes"},
    {"id": "source:ghi", "title": "UART Spec"},
]


def test_match_exact_full_id():
    assert (
        _match(
            "source:abc",
            SOURCES,
            id_key="id",
            name_key="title",
            kind="source",
            id_prefix="source:",
        )
        == "source:abc"
    )


def test_match_bare_id():
    assert (
        _match(
            "ghi",
            SOURCES,
            id_key="id",
            name_key="title",
            kind="source",
            id_prefix="source:",
        )
        == "source:ghi"
    )


def test_match_exact_name_case_insensitive():
    assert (
        _match(
            "uart spec",
            SOURCES,
            id_key="id",
            name_key="title",
            kind="source",
            id_prefix="source:",
        )
        == "source:ghi"
    )


def test_match_exact_name_wins_over_substring():
    # "SPI Spec" is both an exact match and a substring of nothing else;
    # ensure the exact match is selected rather than erroring on ambiguity.
    assert (
        _match(
            "SPI Spec",
            SOURCES,
            id_key="id",
            name_key="title",
            kind="source",
            id_prefix="source:",
        )
        == "source:abc"
    )


def test_match_ambiguous_substring_raises():
    with pytest.raises(CLIError) as exc:
        _match(
            "spi",
            SOURCES,
            id_key="id",
            name_key="title",
            kind="source",
            id_prefix="source:",
        )
    assert "multiple" in str(exc.value).lower()


def test_match_not_found_raises():
    with pytest.raises(CLIError) as exc:
        _match(
            "nonexistent",
            SOURCES,
            id_key="id",
            name_key="title",
            kind="source",
            id_prefix="source:",
        )
    assert "no source matched" in str(exc.value).lower()


# ---------------------------------------------------------------------------
# SSE line parsing
# ---------------------------------------------------------------------------


def test_parse_sse_line_valid():
    assert _parse_sse_line('data: {"type": "ai_message", "content": "hi"}') == {
        "type": "ai_message",
        "content": "hi",
    }


@pytest.mark.parametrize(
    "line",
    ["", "   ", ": comment", "data:", "data: not-json", "event: ping"],
)
def test_parse_sse_line_ignored(line):
    assert _parse_sse_line(line) is None


# ---------------------------------------------------------------------------
# Client construction / headers
# ---------------------------------------------------------------------------


def test_client_headers_include_client_id(monkeypatch):
    monkeypatch.delenv("OPEN_NOTEBOOK_PASSWORD", raising=False)
    monkeypatch.setenv("ON_CLI_CLIENT_ID", "test-cli")
    c = CLIClient(base_url="http://example:5055/")
    assert c.base_url == "http://example:5055"
    assert c.headers["X-Client-ID"] == "test-cli"
    assert "Authorization" not in c.headers


def test_client_headers_include_auth(monkeypatch):
    monkeypatch.setenv("OPEN_NOTEBOOK_PASSWORD", "secret")
    c = CLIClient()
    assert c.headers["Authorization"] == "Bearer secret"


# ---------------------------------------------------------------------------
# Subcommand dispatch (create -> query -> delete)
# ---------------------------------------------------------------------------


class FakeClient:
    """Records the call sequence for the chat commands."""

    def __init__(self):
        self.calls = []

    # resolution
    def resolve_source(self, ref):
        self.calls.append(("resolve_source", ref))
        return "source:abc"

    def resolve_notebook(self, ref):
        self.calls.append(("resolve_notebook", ref))
        return "notebook:xyz"

    # source chat
    def create_source_session(self, source_id, model_override=None):
        self.calls.append(("create_source_session", source_id, model_override))
        return "chat_session:1"

    def stream_source_message(self, source_id, session_id, message, model_override=None):
        self.calls.append(("stream_source_message", source_id, session_id, message))
        return "the source answer"

    def delete_source_session(self, source_id, session_id):
        self.calls.append(("delete_source_session", source_id, session_id))

    # notebook chat
    def create_notebook_session(self, notebook_id, model_override=None):
        self.calls.append(("create_notebook_session", notebook_id, model_override))
        return "chat_session:2"

    def build_notebook_context(self, notebook_id, full=False):
        self.calls.append(("build_notebook_context", notebook_id, full))
        return {"sources": [], "notes": []}

    def execute_notebook_chat(self, session_id, message, context, model_override=None):
        self.calls.append(("execute_notebook_chat", session_id, message))
        return "the notebook answer"

    def delete_notebook_session(self, session_id):
        self.calls.append(("delete_notebook_session", session_id))


@pytest.fixture
def patched_client(monkeypatch):
    fake = FakeClient()
    monkeypatch.setattr("open_notebook.cli.main.CLIClient", lambda **kwargs: fake)
    return fake


def test_source_command_flow(patched_client, capsys):
    rc = main(["source", "SPI Spec", "what registers?"])
    assert rc == 0
    out = capsys.readouterr().out.strip()
    assert out == "the source answer"
    names = [c[0] for c in patched_client.calls]
    assert names == [
        "resolve_source",
        "create_source_session",
        "stream_source_message",
        "delete_source_session",
    ]


def test_notebook_command_flow(patched_client, capsys):
    rc = main(["notebook", "Docs", "summarize"])
    assert rc == 0
    out = capsys.readouterr().out.strip()
    assert out == "the notebook answer"
    names = [c[0] for c in patched_client.calls]
    assert names == [
        "resolve_notebook",
        "create_notebook_session",
        "build_notebook_context",
        "execute_notebook_chat",
        "delete_notebook_session",
    ]


def test_session_reuse_skips_cleanup(patched_client):
    rc = main(["source", "SPI Spec", "q", "--session", "chat_session:existing"])
    assert rc == 0
    names = [c[0] for c in patched_client.calls]
    assert "create_source_session" not in names
    assert "delete_source_session" not in names


def test_keep_session_skips_cleanup(patched_client):
    rc = main(["notebook", "Docs", "q", "--keep-session"])
    assert rc == 0
    names = [c[0] for c in patched_client.calls]
    assert "create_notebook_session" in names
    assert "delete_notebook_session" not in names


def test_json_output(patched_client, capsys):
    rc = main(["source", "SPI Spec", "q", "--json"])
    assert rc == 0
    import json

    payload = json.loads(capsys.readouterr().out)
    assert payload["answer"] == "the source answer"
    assert payload["target_id"] == "source:abc"
    assert payload["session_id"] == "chat_session:1"


def test_cli_error_returns_exit_code_1(monkeypatch, capsys):
    class Boom:
        def resolve_source(self, ref):
            raise CLIError("nope")

    monkeypatch.setattr("open_notebook.cli.main.CLIClient", lambda **kwargs: Boom())
    rc = main(["source", "x", "q"])
    assert rc == 1
    assert "nope" in capsys.readouterr().err


def test_notebook_cleanup_runs_even_on_error(monkeypatch, capsys):
    """The ephemeral session must be deleted even if the chat call fails."""

    class FailingChat(FakeClient):
        def execute_notebook_chat(self, *a, **k):
            raise CLIError("model exploded")

    fake = FailingChat()
    monkeypatch.setattr("open_notebook.cli.main.CLIClient", lambda **kwargs: fake)
    rc = main(["notebook", "Docs", "q"])
    assert rc == 1
    assert ("delete_notebook_session", "chat_session:2") in fake.calls
