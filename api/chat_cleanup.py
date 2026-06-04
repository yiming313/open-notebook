"""Background cleanup of expired chat sessions.

Chat sessions are private per browser and meant to be ephemeral: once a browser
tab closes, its `client_id` (kept in sessionStorage) is gone and the old sessions
become invisible in the UI. This sweeper makes that ephemerality real on disk by
periodically deleting chat_session records that have been idle longer than a TTL,
along with their LangGraph conversation checkpoints and notebook relationships.

Configured via CHAT_SESSION_TTL_HOURS (default 24). Set to 0 to disable the sweeper.
"""

import asyncio
import os
from datetime import datetime, timedelta

from loguru import logger

from open_notebook.database.repository import (
    ensure_record_id,
    repo_delete,
    repo_query,
)
from open_notebook.graphs.chat import delete_thread as delete_chat_thread

# Timestamp format used by ObjectModel.save() for `created` / `updated`.
_TS_FORMAT = "%Y-%m-%d %H:%M:%S"


def _ttl_hours() -> float:
    try:
        return float(os.getenv("CHAT_SESSION_TTL_HOURS", "24"))
    except ValueError:
        return 24.0


async def sweep_expired_chat_sessions(ttl_hours: float) -> int:
    """Delete chat sessions idle longer than ttl_hours. Returns count removed."""
    if ttl_hours <= 0:
        return 0

    cutoff = (datetime.now() - timedelta(hours=ttl_hours)).strftime(_TS_FORMAT)
    rows = await repo_query(
        "SELECT id FROM chat_session WHERE updated < $cutoff",
        {"cutoff": cutoff},
    )
    if not rows:
        return 0

    removed = 0
    for row in rows:
        session_id = row.get("id")
        if session_id is None:
            continue
        full_id = str(session_id)
        try:
            # Remove conversation history from the LangGraph checkpoint store.
            await asyncio.to_thread(delete_chat_thread, full_id)
            # Remove the notebook relationship edge, then the session record.
            record_id = ensure_record_id(full_id)
            await repo_query("DELETE refers_to WHERE in = $id", {"id": record_id})
            await repo_delete(record_id)
            removed += 1
        except Exception as e:
            logger.warning(f"Failed to purge expired chat session {full_id}: {e}")

    if removed:
        logger.info(
            f"Chat session sweeper removed {removed} session(s) idle > {ttl_hours}h"
        )
    return removed


async def chat_session_sweeper_loop(interval_seconds: float = 3600.0) -> None:
    """Run sweep_expired_chat_sessions on a loop until cancelled."""
    ttl_hours = _ttl_hours()
    if ttl_hours <= 0:
        logger.info("Chat session sweeper disabled (CHAT_SESSION_TTL_HOURS=0).")
        return

    logger.info(
        f"Chat session sweeper started (TTL={ttl_hours}h, interval={interval_seconds}s)."
    )
    try:
        while True:
            try:
                await sweep_expired_chat_sessions(ttl_hours)
            except asyncio.CancelledError:
                raise
            except Exception as e:
                logger.warning(f"Chat session sweep failed: {e}")
            await asyncio.sleep(interval_seconds)
    except asyncio.CancelledError:
        logger.info("Chat session sweeper stopped.")
        raise
