"""
agent/local_state.py — Lightweight SQLite store for agent-side durable state.

Role in the architecture
------------------------
The agent is deliberately stateless across sessions to keep it simple, but
two pieces of state genuinely need to survive a crash:

1. **Pending results** — task_ids where ``execute_allowed`` completed but the
   server has not yet sent ``RESULT_ACK``.  Without durability, a crash
   between sending RESULT and receiving RESULT_ACK means the operator sees
   the task as failed even though it completed successfully.

2. **Runtime marker** — the existing per-run JSON file in lab_dir (unchanged).

This module provides a minimal SQLite façade scoped to the agent's lab_dir
so no extra configuration is needed.  The DB is tiny (~4 KiB typical) and
is cleaned up on normal shutdown.

Usage
-----
    state = AgentLocalState(lab_dir="/data/agent_files")
    await state.open()
    await state.add_pending_result("task-uuid", "result-uuid", "echo", "hello")
    results = await state.list_pending_results()
    await state.remove_pending_result("task-uuid")
    await state.close()
"""
from __future__ import annotations

import asyncio
import logging
import sqlite3
from pathlib import Path

LOG = logging.getLogger("agent.state")


class AgentLocalState:
    """Minimal per-agent SQLite store for durable in-flight result tracking.

    Parameters
    ----------
    lab_dir : str or Path
        The agent's working directory.  The SQLite file is created as
        ``<lab_dir>/.agent_state.db``.  The leading dot makes it
        invisible to directory listings used in file transfer tests.
    """

    def __init__(self, lab_dir: str | Path) -> None:
        """Initialise with the path to the agent's lab directory."""
        self._path = Path(lab_dir) / ".agent_state.db"
        self._conn: sqlite3.Connection | None = None
        self._lock = asyncio.Lock()

    async def open(self) -> None:
        """Open (or create) the SQLite database and create the schema."""
        async with self._lock:
            self._conn = sqlite3.connect(str(self._path))
            self._conn.row_factory = sqlite3.Row
            self._conn.executescript("""
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS pending_results (
                    task_id   TEXT PRIMARY KEY,
                    result_id TEXT NOT NULL,
                    command   TEXT NOT NULL,
                    output    TEXT NOT NULL,
                    status    TEXT NOT NULL,
                    created_at REAL NOT NULL
                );
            """)
            self._conn.commit()

    async def add_pending_result(self, task_id: str, result_id: str,
                                 command: str, output: str,
                                 status: str = "COMPLETED") -> None:
        """Record a result that has been sent but not yet ACK'd by the server.

        Parameters
        ----------
        task_id, result_id : str
            The task and result UUIDs from the RESULT message.
        command : str
            The command name, for context when restoring state.
        output : str
            The task output string.
        status : str
            The terminal status ("COMPLETED" or "FAILED").
        """
        import time as _time
        async with self._lock:
            if self._conn is None:
                return
            self._conn.execute(
                "INSERT OR REPLACE INTO pending_results "
                "(task_id, result_id, command, output, status, created_at) "
                "VALUES (?,?,?,?,?,?)",
                (task_id, result_id, command, output, status, _time.time()),
            )
            self._conn.commit()

    async def remove_pending_result(self, task_id: str) -> None:
        """Remove a pending result once the server sends RESULT_ACK."""
        async with self._lock:
            if self._conn is None:
                return
            self._conn.execute(
                "DELETE FROM pending_results WHERE task_id=?", (task_id,)
            )
            self._conn.commit()

    async def list_pending_results(self) -> list[dict]:
        """Return all pending result records, oldest first.

        Used at startup to discover results that need to be retransmitted
        or whose task_ids should appear in SYNC_STATE pending_result_ids.
        """
        async with self._lock:
            if self._conn is None:
                return []
            rows = self._conn.execute(
                "SELECT * FROM pending_results ORDER BY created_at"
            ).fetchall()
            return [dict(r) for r in rows]

    async def clear(self) -> None:
        """Delete all rows — called on clean session shutdown."""
        async with self._lock:
            if self._conn is None:
                return
            self._conn.execute("DELETE FROM pending_results")
            self._conn.commit()

    async def close(self) -> None:
        """Close the database connection."""
        async with self._lock:
            if self._conn:
                self._conn.close()
                self._conn = None

    def delete_db(self) -> None:
        """Remove the SQLite file from disk (called on self_remove)."""
        self._path.unlink(missing_ok=True)
