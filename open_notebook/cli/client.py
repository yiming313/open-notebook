"""HTTP client used by the Open Notebook CLI.

This is a deliberately small wrapper around the running FastAPI server. It
mirrors the environment conventions of :class:`api.client.APIClient`
(``API_BASE_URL``, ``OPEN_NOTEBOOK_PASSWORD``, ``API_CLIENT_TIMEOUT``) and adds
the chat endpoints plus identifier-resolution helpers that the CLI needs.

All requests carry a consistent ``X-Client-ID`` header so that the ephemeral
chat sessions created here remain owned by (and deletable by) the CLI.
"""

from __future__ import annotations

import json
import os
from typing import Any, Dict, List, Optional

import httpx

DEFAULT_BASE_URL = "http://127.0.0.1:5055"
DEFAULT_CLIENT_ID = "open-notebook-cli"
DEFAULT_TIMEOUT = 300.0


class CLIError(Exception):
    """Raised for user-facing CLI failures (resolution, API, streaming)."""


def _normalize_timeout(raw: Optional[str]) -> float:
    if not raw:
        return DEFAULT_TIMEOUT
    try:
        value = float(raw)
    except ValueError:
        return DEFAULT_TIMEOUT
    # Keep within the same sane bounds the API client uses.
    return max(30.0, min(value, 3600.0))


class CLIClient:
    """Minimal HTTP client over the Open Notebook API for the CLI."""

    def __init__(
        self,
        base_url: Optional[str] = None,
        client_id: Optional[str] = None,
        timeout: Optional[float] = None,
    ) -> None:
        resolved_base = base_url or os.getenv("API_BASE_URL") or DEFAULT_BASE_URL
        self.base_url = resolved_base.rstrip("/")
        self.client_id = (
            client_id or os.getenv("ON_CLI_CLIENT_ID") or DEFAULT_CLIENT_ID
        )
        self.timeout = (
            timeout
            if timeout is not None
            else _normalize_timeout(os.getenv("API_CLIENT_TIMEOUT"))
        )

        self.headers: Dict[str, str] = {"X-Client-ID": self.client_id}
        password = os.getenv("OPEN_NOTEBOOK_PASSWORD")
        if password:
            self.headers["Authorization"] = f"Bearer {password}"

    # -- low-level helpers -------------------------------------------------

    def _url(self, endpoint: str) -> str:
        return f"{self.base_url}{endpoint}"

    def _request(
        self, method: str, endpoint: str, **kwargs: Any
    ) -> Any:
        headers = {**self.headers, **kwargs.pop("headers", {})}
        try:
            with httpx.Client(timeout=self.timeout) as client:
                response = client.request(
                    method, self._url(endpoint), headers=headers, **kwargs
                )
                response.raise_for_status()
                if response.content:
                    return response.json()
                return None
        except httpx.HTTPStatusError as exc:
            detail = _extract_detail(exc.response)
            raise CLIError(
                f"API error {exc.response.status_code} on {method} {endpoint}: {detail}"
            ) from exc
        except httpx.RequestError as exc:
            raise CLIError(
                f"Could not reach the Open Notebook API at {self.base_url} "
                f"({exc}). Is the server running?"
            ) from exc

    # -- listing -----------------------------------------------------------

    def list_notebooks(self) -> List[Dict[str, Any]]:
        result = self._request("GET", "/api/notebooks")
        return result if isinstance(result, list) else []

    def list_sources(
        self, notebook_id: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        # The /api/sources endpoint paginates (default 50, max 100 per page),
        # so page through it to return every source without truncation.
        page_size = 100
        offset = 0
        all_sources: List[Dict[str, Any]] = []
        while True:
            params: Dict[str, Any] = {"limit": page_size, "offset": offset}
            if notebook_id:
                params["notebook_id"] = notebook_id
            result = self._request("GET", "/api/sources", params=params)
            page = result if isinstance(result, list) else []
            all_sources.extend(page)
            if len(page) < page_size:
                break
            offset += page_size
        return all_sources

    def list_notes(
        self, notebook_id: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        params = {"notebook_id": notebook_id} if notebook_id else None
        result = self._request("GET", "/api/notes", params=params)
        return result if isinstance(result, list) else []

    # -- resolution --------------------------------------------------------

    def resolve_notebook(self, ref: str) -> str:
        """Resolve a notebook reference (id or name) to a full notebook id."""
        if ref.startswith("notebook:"):
            return ref
        notebooks = self.list_notebooks()
        return _match(
            ref,
            notebooks,
            id_key="id",
            name_key="name",
            kind="notebook",
            id_prefix="notebook:",
        )

    def resolve_source(self, ref: str) -> str:
        """Resolve a source reference (id or title) to a full source id."""
        if ref.startswith("source:"):
            return ref
        sources = self.list_sources()
        return _match(
            ref,
            sources,
            id_key="id",
            name_key="title",
            kind="source",
            id_prefix="source:",
        )

    # -- source chat -------------------------------------------------------

    def create_source_session(
        self, source_id: str, model_override: Optional[str] = None
    ) -> str:
        body: Dict[str, Any] = {"source_id": source_id, "title": "CLI session"}
        if model_override:
            body["model_override"] = model_override
        result = self._request(
            "POST", f"/api/sources/{source_id}/chat/sessions", json=body
        )
        session_id = (result or {}).get("id")
        if not session_id:
            raise CLIError("Failed to create source chat session (no id returned).")
        return session_id

    def stream_source_message(
        self,
        source_id: str,
        session_id: str,
        message: str,
        model_override: Optional[str] = None,
    ) -> str:
        """Send a message to a source chat session and return the AI answer.

        The endpoint streams ``data: {json}`` lines (text/plain). We accumulate
        every ``ai_message`` payload, raise on ``error``, and stop on
        ``complete``.
        """
        body: Dict[str, Any] = {"message": message}
        if model_override:
            body["model_override"] = model_override

        endpoint = f"/api/sources/{source_id}/chat/sessions/{session_id}/messages"
        answer_parts: List[str] = []
        try:
            with httpx.Client(timeout=self.timeout) as client:
                with client.stream(
                    "POST", self._url(endpoint), headers=self.headers, json=body
                ) as response:
                    response.raise_for_status()
                    for line in response.iter_lines():
                        event = _parse_sse_line(line)
                        if event is None:
                            continue
                        etype = event.get("type")
                        if etype == "ai_message":
                            answer_parts.append(event.get("content", ""))
                        elif etype == "error":
                            raise CLIError(
                                event.get("message", "Unknown chat error")
                            )
                        elif etype == "complete":
                            break
        except httpx.HTTPStatusError as exc:
            detail = _extract_detail(exc.response)
            raise CLIError(
                f"API error {exc.response.status_code} on source chat: {detail}"
            ) from exc
        except httpx.RequestError as exc:
            raise CLIError(
                f"Could not reach the Open Notebook API at {self.base_url} ({exc})."
            ) from exc

        return "".join(answer_parts).strip()

    def delete_source_session(self, source_id: str, session_id: str) -> None:
        self._request(
            "DELETE", f"/api/sources/{source_id}/chat/sessions/{session_id}"
        )

    # -- notebook chat -----------------------------------------------------

    def create_notebook_session(
        self, notebook_id: str, model_override: Optional[str] = None
    ) -> str:
        body: Dict[str, Any] = {"notebook_id": notebook_id, "title": "CLI session"}
        if model_override:
            body["model_override"] = model_override
        result = self._request("POST", "/api/chat/sessions", json=body)
        session_id = (result or {}).get("id")
        if not session_id:
            raise CLIError("Failed to create notebook chat session (no id returned).")
        return session_id

    def build_notebook_context(
        self, notebook_id: str, full: bool = False
    ) -> Dict[str, Any]:
        """Build chat context for a notebook.

        ``full=False`` lets the server include all sources/notes at short depth.
        ``full=True`` requests full content for every source and note.
        """
        context_config: Dict[str, Any] = {}
        if full:
            sources = self.list_sources(notebook_id)
            notes = self.list_notes(notebook_id)
            context_config = {
                "sources": {
                    s["id"]: "[x] full content" for s in sources if s.get("id")
                },
                "notes": {
                    n["id"]: "full content" for n in notes if n.get("id")
                },
            }
        result = self._request(
            "POST",
            "/api/chat/context",
            json={"notebook_id": notebook_id, "context_config": context_config},
        )
        return (result or {}).get("context", {})

    def execute_notebook_chat(
        self,
        session_id: str,
        message: str,
        context: Dict[str, Any],
        model_override: Optional[str] = None,
    ) -> str:
        body: Dict[str, Any] = {
            "session_id": session_id,
            "message": message,
            "context": context,
        }
        if model_override:
            body["model_override"] = model_override
        result = self._request("POST", "/api/chat/execute", json=body)
        messages = (result or {}).get("messages", [])
        ai_messages = [m for m in messages if m.get("type") == "ai"]
        if not ai_messages:
            raise CLIError("No AI response returned from notebook chat.")
        return (ai_messages[-1].get("content") or "").strip()

    def delete_notebook_session(self, session_id: str) -> None:
        self._request("DELETE", f"/api/chat/sessions/{session_id}")


# -- module-level helpers --------------------------------------------------


def _extract_detail(response: httpx.Response) -> str:
    try:
        payload = response.json()
        if isinstance(payload, dict) and "detail" in payload:
            return str(payload["detail"])
    except Exception:
        pass
    return response.text or response.reason_phrase


def _parse_sse_line(line: str) -> Optional[Dict[str, Any]]:
    if not line:
        return None
    line = line.strip()
    if not line.startswith("data:"):
        return None
    payload = line[len("data:") :].strip()
    if not payload:
        return None
    try:
        parsed = json.loads(payload)
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


def _match(
    ref: str,
    items: List[Dict[str, Any]],
    *,
    id_key: str,
    name_key: str,
    kind: str,
    id_prefix: str,
) -> str:
    """Resolve ``ref`` to a record id by exact id or case-insensitive name."""
    # Exact id match (bare uuid or already-prefixed value stored on the record).
    bare_candidate = f"{id_prefix}{ref}"
    for item in items:
        item_id = str(item.get(id_key, ""))
        if item_id in (ref, bare_candidate):
            return item_id

    # Case-insensitive name/title match.
    needle = ref.casefold()
    exact = [
        item
        for item in items
        if (item.get(name_key) or "").casefold() == needle
    ]
    matches = exact or [
        item
        for item in items
        if needle in (item.get(name_key) or "").casefold()
    ]

    if len(matches) == 1:
        return str(matches[0][id_key])
    if not matches:
        raise CLIError(
            f"No {kind} matched '{ref}'. "
            f"Run 'open-notebook list-{kind}s' to see available {kind}s."
        )
    labels = ", ".join(
        f"{item.get(name_key) or '(untitled)'} [{item.get(id_key)}]"
        for item in matches[:10]
    )
    raise CLIError(
        f"'{ref}' matched multiple {kind}s: {labels}. "
        f"Re-run with a full {kind} id."
    )
