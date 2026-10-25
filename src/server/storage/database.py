"""
server/storage/database.py — Asynchronous SQLite persistence layer.

Role in the architecture
------------------------
This module is the only component that reads from or writes to the SQLite
database file.  All other modules (server/main.py, server/task_manager.py)
call methods on the Database class; they never execute SQL directly.

Concurrency model
-----------------
SQLite is not safe for concurrent writes from multiple threads.  This module
uses a single asyncio.Lock (``self.lock``) to serialise all database
operations within one process.  Because asyncio only switches coroutines at
``await`` points, acquiring the lock and then performing several synchronous
SQLite calls without an intermediate ``await`` is genuinely atomic from the
perspective of every other coroutine in the same event loop.

WAL mode (Write-Ahead Logging) is enabled at initialisation so that readers
never block writers and vice versa at the SQLite level — although in practice
the asyncio lock makes this distinction moot within a single process.

Schema overview
---------------
agents    — one row per known agent; updated on every REGISTER.
sessions  — one row per TLS connection; closed on disconnect.
tasks     — one row per dispatched task; status updated as the task progresses.
results   — one row per received RESULT message; linked to tasks by task_id.

State-machine integration
--------------------------
The ``tasks.status`` column is the authoritative record of a task's lifecycle
state.  Every write to that column (except the initial INSERT in create_task)
goes through ``validate_transition`` from server/task_manager.py.  This
ensures that the database can never hold an invalid state sequence even if a
bug in the message handlers passes a wrong value.
"""

import asyncio
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from server.task_manager import (
    InvalidTaskTransition,
    TaskState,
    TERMINAL_STATES,
    validate_transition,
)


# ── Exceptions ────────────────────────────────────────────────────────────────

class TaskNotFoundError(KeyError):
    """Raised when a task operation targets a task_id that does not exist.

    Inherits from KeyError so callers that treat missing keys generically
    still work, while handlers that need to distinguish "task not found"
    from "transition not allowed" can catch this type specifically.
    """


# ── Utility ───────────────────────────────────────────────────────────────────

def now() -> str:
    """Return the current UTC time as an ISO-8601 string.

    All timestamps in the database use this format so they are sortable
    lexicographically and unambiguous with regard to timezone.
    """
    return datetime.now(timezone.utc).isoformat()


# ── Database class ────────────────────────────────────────────────────────────

class Database:
    """Asynchronous façade over a SQLite database for the C2 MVP.

    All public methods are coroutines.  They acquire ``self.lock`` before
    executing any SQL so that concurrent callers in the same asyncio event
    loop are safely serialised.

    Usage
    -----
    db = Database("data/c2.sqlite3")
    await db.initialize()        # creates tables if they don't exist
    ...                          # use db in server handlers
    await db.close()             # called on server shutdown
    """

    def __init__(self, path: str):
        """Initialise the database object without opening the file.

        Parameters
        ----------
        path : str
            Filesystem path to the SQLite database file.  Use ``":memory:"``
            in tests to get an isolated, ephemeral database.
        """
        self.path = Path(path)
        self.conn = None         # set by initialize(); None means not yet open
        self.lock = asyncio.Lock()  # serialises all SQL operations in this process

    async def initialize(self):
        """Open the database file and create tables if they do not yet exist.

        Must be called once before any other method.  Uses WAL journal mode
        for better read/write concurrency at the SQLite level, and
        ``CREATE TABLE IF NOT EXISTS`` so the same call is safe to make on
        both a fresh file and an existing one.

        The parent directory is created automatically if it does not exist,
        which avoids a common first-run error when ``data/`` is absent.
        """
        self.path.parent.mkdir(parents=True, exist_ok=True)
        async with self.lock:
            self.conn = sqlite3.connect(self.path)
            # row_factory makes column access by name possible: row["status"]
            self.conn.row_factory = sqlite3.Row
            self.conn.executescript("""
            PRAGMA journal_mode=WAL;
            CREATE TABLE IF NOT EXISTS agents (
                agent_id   TEXT PRIMARY KEY,
                hostname   TEXT NOT NULL,
                platform   TEXT NOT NULL,
                first_seen TEXT NOT NULL,
                last_seen  TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS sessions (
                session_id TEXT PRIMARY KEY,
                agent_id   TEXT,                -- NULL until REGISTER arrives
                state      TEXT NOT NULL,
                started_at TEXT NOT NULL,
                ended_at   TEXT                 -- NULL while session is active
            );
            CREATE TABLE IF NOT EXISTS tasks (
                task_id         TEXT PRIMARY KEY,
                agent_id        TEXT NOT NULL,
                command         TEXT NOT NULL,
                parameters_json TEXT NOT NULL,
                status          TEXT NOT NULL,  -- always a TaskState value
                created_at      TEXT NOT NULL,
                updated_at      TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS task_interruptions (
                task_id TEXT PRIMARY KEY,
                previous_status TEXT NOT NULL,
                terminal_status TEXT NOT NULL,
                reason TEXT NOT NULL,
                outcome TEXT NOT NULL,
                interrupted_at TEXT NOT NULL,
                retry_task_id TEXT UNIQUE
            );
            CREATE TABLE IF NOT EXISTS results (
                result_id TEXT PRIMARY KEY,
                task_id   TEXT NOT NULL,
                agent_id  TEXT NOT NULL,
                status    TEXT NOT NULL,        -- always a terminal TaskState value
                output    TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            """)
            self.conn.commit()

    # ── Agent methods ─────────────────────────────────────────────────────────

    async def upsert_agent(self, agent_id: str, hostname: str, platform: str) -> None:
        """Insert or update an agent record.

        Called every time an agent sends a REGISTER message.  If the agent_id
        already exists (reconnect), the hostname and platform are updated and
        last_seen is refreshed.  first_seen is preserved from the initial
        insert via the ON CONFLICT clause.

        Parameters
        ----------
        agent_id : str
            UUID string as sent by the agent in the REGISTER payload.
        hostname : str
            Human-readable hostname of the machine running the agent.
        platform : str
            OS/platform string (e.g. ``platform.platform()`` output).
            Truncated to 255 characters to prevent oversized rows.
        """
        t = now()
        async with self.lock:
            self.conn.execute(
                """INSERT INTO agents VALUES(?,?,?,?,?)
                   ON CONFLICT(agent_id) DO UPDATE SET
                       hostname  = excluded.hostname,
                       platform  = excluded.platform,
                       last_seen = excluded.last_seen""",
                (agent_id, str(hostname)[:255], str(platform)[:255], t, t),
            )
            self.conn.commit()

    async def touch_agent(self, agent_id: str) -> None:
        """Refresh the ``last_seen`` timestamp for an agent.

        Called on every BEACON message to track agent liveness.  A large
        gap between now and ``last_seen`` indicates a silent agent.
        """
        async with self.lock:
            self.conn.execute(
                "UPDATE agents SET last_seen=? WHERE agent_id=?", (now(), agent_id)
            )
            self.conn.commit()

    # ── Session methods ───────────────────────────────────────────────────────

    async def create_session(self, session_id: str, agent_id, state: str) -> None:
        """Record a new TLS session.

        Called at the moment a TCP connection is accepted, before REGISTER
        arrives.  ``agent_id`` is initially None and is set later by
        ``set_session_agent`` once the REGISTER message is processed.

        Parameters
        ----------
        session_id : str
            Fresh UUID generated by handle_client for this connection.
        agent_id : str or None
            None at connection time; set to the agent's UUID after REGISTER.
        state : str
            Initial session state (typically ``"CONNECTED"``).
        """
        async with self.lock:
            self.conn.execute(
                "INSERT INTO sessions VALUES(?,?,?,?,NULL)",
                (session_id, agent_id, state, now()),
            )
            self.conn.commit()

    async def set_session_agent(self, session_id: str, agent_id: str) -> None:
        """Associate a session with the agent that registered on it.

        Called immediately after REGISTER is validated, to fill the
        ``agent_id`` column that was NULL at ``create_session`` time.
        """
        async with self.lock:
            self.conn.execute(
                "UPDATE sessions SET agent_id=? WHERE session_id=?",
                (agent_id, session_id),
            )
            self.conn.commit()

    async def mark_session_active(self, session_id: str) -> None:
        """Mark a registered and synchronized TLS session usable for tasks."""
        async with self.lock:
            self.conn.execute("UPDATE sessions SET state='ACTIVE' WHERE session_id=? AND ended_at IS NULL",
                              (session_id,))
            self.conn.commit()

    async def close_session(self, session_id: str, state: str) -> None:
        """Mark a session as closed with a final state and an end timestamp.

        Called from the ``finally`` block of ``handle_client`` so it runs
        regardless of whether the connection closed cleanly or with an error.

        Parameters
        ----------
        session_id : str
            The session to close.
        state : str
            Final state string, typically ``"DISCONNECTED"``.
        """
        async with self.lock:
            self.conn.execute(
                "UPDATE sessions SET state=?, ended_at=? WHERE session_id=?",
                (state, now(), session_id),
            )
            self.conn.commit()

    # ── Task methods ──────────────────────────────────────────────────────────

    async def create_task(
        self, task_id: str, agent_id: str, command: str, parameters: dict, status: str
    ) -> None:
        """Insert a new task record in the given initial state.

        The ``status`` argument is validated against the TaskState enum before
        the INSERT so that an invalid initial state is rejected immediately
        rather than persisted and discovered later during a transition.

        Called by ``dispatch_task`` in server/main.py with ``status="PENDING"``.

        Parameters
        ----------
        task_id : str
            Fresh UUID generated by dispatch_task.
        agent_id : str
            The agent this task is destined for.
        command : str
            Command name (e.g. ``"echo"``, ``"get_info"``).
        parameters : dict
            Command-specific parameters; serialised to JSON for storage.
        status : str
            Initial status — must be a valid TaskState value (``"PENDING"``).

        Raises
        ------
        InvalidTaskTransition
            If ``status`` is not a recognised TaskState member.
        """
        import json
        # Validate the initial status before touching the database.
        try:
            TaskState(status)
        except ValueError as exc:
            raise InvalidTaskTransition(f"Unknown initial task state: {status!r}") from exc
        async with self.lock:
            self.conn.execute(
                "INSERT INTO tasks VALUES(?,?,?,?,?,?,?)",
                (task_id, agent_id, command, json.dumps(parameters), status, now(), now()),
            )
            self.conn.commit()

    async def update_task_status(self, task_id: str, status: str) -> None:
        """Advance a task's status to ``status`` if the transition is permitted.

        The method reads the current status, runs it through the state-machine
        validator, and writes the new status — all inside a single lock
        acquisition.  Because asyncio only yields at ``await`` points, and
        there is no ``await`` between the SELECT and the UPDATE, no other
        coroutine can interleave between the read and the write.

        This is the only method (other than ``complete_task_with_result``) that
        may change ``tasks.status`` after the initial INSERT.

        Parameters
        ----------
        task_id : str
            The task to update.
        status : str
            The desired new state (e.g. ``"RUNNING"``).

        Raises
        ------
        TaskNotFoundError
            ``task_id`` does not exist in the database.
        InvalidTaskTransition
            The requested transition is not permitted by the state machine
            (unknown state, disallowed edge, terminal-state protection, or
            self-transition).
        """
        async with self.lock:
            row = self.conn.execute(
                "SELECT status FROM tasks WHERE task_id=?", (task_id,)
            ).fetchone()
            if row is None:
                raise TaskNotFoundError(f"No task with id {task_id!r}")

            current_status = row["status"]
            # Raises InvalidTaskTransition on any bad edge, including terminal → any
            # and self-transitions (e.g. RUNNING → RUNNING).
            validate_transition(current_status, status)

            self.conn.execute(
                "UPDATE tasks SET status=?, updated_at=? WHERE task_id=?",
                (status, now(), task_id),
            )
            self.conn.commit()

    async def complete_task_with_result(
        self,
        task_id: str,
        status: str,
        result_id: str,
        result_agent_id: str,
        output: str,
    ) -> None:
        """Atomically advance a task to a terminal state and persist its result.

        Why this method exists
        ----------------------
        When a RESULT message arrives, two database records must be updated:
        the task's status in ``tasks`` and a new row in ``results``.  If these
        were two separate operations with a commit in between, a crash or a
        storage error between them would leave the records inconsistent — the
        task marked COMPLETED but no result row, or a result row for a task
        that is still RUNNING.

        This method wraps both writes in one SQLite transaction under the
        asyncio lock so they commit together or roll back together.

        Collision protection
        --------------------
        ``result_id`` is the primary key of the ``results`` table.  If the
        agent retransmits the same RESULT with the same ``result_id`` for the
        same task, the second call is rejected by the transition validator
        (the task is already terminal) before any SQL runs.

        If the same ``result_id`` arrives for a *different* task (a UUID
        collision or a misbehaving agent), the plain ``INSERT`` raises
        ``sqlite3.IntegrityError``, which is caught, the transaction is rolled
        back, and ``InvalidTaskTransition`` is raised — so the second task's
        status is never advanced and no data is overwritten.

        Parameters
        ----------
        task_id : str
            The task to complete.
        status : str
            The terminal outcome — must be a member of TERMINAL_STATES
            (``"COMPLETED"`` or ``"FAILED"`` in normal operation).
        result_id : str
            UUID for the result row, generated by the agent.
        result_agent_id : str
            The agent that delivered this result (recorded for audit).
        output : str
            The command's text output.  Truncated to 20 000 characters on
            storage to prevent unbounded growth from verbose commands.

        Raises
        ------
        TaskNotFoundError
            ``task_id`` does not exist in the database.
        InvalidTaskTransition
            Any of: non-terminal ``status``, unknown ``status``, disallowed
            transition from the current state, or ``result_id`` already
            belonging to a different task (cross-task collision).
        """
        # ── Pre-flight validation (before acquiring the lock) ─────────────────
        # Validate the status is a known terminal state before touching the DB.
        # This is checked outside the lock because it's a pure computation and
        # we want the error to be raised as early as possible.
        try:
            target_state = TaskState(status)
        except ValueError as exc:
            raise InvalidTaskTransition(
                f"Result status {status!r} is not a known TaskState"
            ) from exc
        if target_state not in TERMINAL_STATES:
            raise InvalidTaskTransition(
                f"Result status {status!r} is not a terminal state"
            )

        # ── Atomic read–validate–write under the lock ─────────────────────────
        async with self.lock:
            row = self.conn.execute(
                "SELECT status FROM tasks WHERE task_id=?", (task_id,)
            ).fetchone()
            if row is None:
                raise TaskNotFoundError(f"No task with id {task_id!r}")

            current_status = row["status"]
            # Raises InvalidTaskTransition if the current→target edge is not in
            # ALLOWED_TRANSITIONS, which includes terminal → any protection.
            validate_transition(current_status, status)

            # Use one shared timestamp so both rows record the same instant.
            ts = now()
            try:
                # Step 1: advance the task status.
                self.conn.execute(
                    "UPDATE tasks SET status=?, updated_at=? WHERE task_id=?",
                    (status, ts, task_id),
                )

                # Step 2: insert the result row.
                # Plain INSERT (not INSERT OR IGNORE) so that a duplicate
                # result_id raises IntegrityError and triggers the rollback
                # below, rather than silently succeeding with the wrong data.
                try:
                    self.conn.execute(
                        "INSERT INTO results VALUES(?,?,?,?,?,?)",
                        (result_id, task_id, result_agent_id, status,
                         str(output)[:20000], ts),
                    )
                except sqlite3.IntegrityError as exc:
                    # result_id already exists — either same-task duplicate or
                    # cross-task collision.  Roll back the UPDATE and raise a
                    # descriptive domain error.
                    self.conn.rollback()
                    raise InvalidTaskTransition(
                        f"result_id {result_id!r} already exists; "
                        f"task {task_id!r} state not advanced"
                    ) from exc

                # Belt-and-suspenders: changes() should always be 1 after a
                # successful INSERT.  A 0 here would indicate an unexpected
                # trigger or schema change that suppressed the write without
                # raising an error.
                inserted = self.conn.execute("SELECT changes()").fetchone()[0]
                if inserted == 0:
                    self.conn.rollback()
                    raise InvalidTaskTransition(
                        f"result_id {result_id!r} already exists for a different task; "
                        f"task {task_id!r} state not advanced"
                    )

                # Both writes succeeded — commit the transaction.
                self.conn.commit()

            except InvalidTaskTransition:
                # Rollback already called above; re-raise without wrapping.
                raise
            except Exception:
                # Any other unexpected error (disk full, corrupted DB, etc.)
                # triggers a rollback so neither partial write persists.
                self.conn.rollback()
                raise

    async def save_result(
        self, result_id: str, task_id: str, agent_id: str, status: str, output: str
    ) -> None:
        """Persist a result row without updating the task's status.

        This method is a lower-level alternative to ``complete_task_with_result``
        intended for situations where the task status has already been advanced
        by a separate call.  The RESULT message handler in server/main.py uses
        ``complete_task_with_result`` instead, which is the preferred path.

        ``INSERT OR IGNORE`` is used so that a duplicate ``result_id`` is
        silently discarded rather than raising an error.  This is safe here
        because the task's authoritative state is already final — we are only
        recording supplementary output data.

        Parameters
        ----------
        result_id, task_id, agent_id, status, output
            See ``complete_task_with_result`` for field descriptions.

        Raises
        ------
        InvalidTaskTransition
            ``status`` is not a known terminal TaskState value.
        """
        # Only terminal states are valid as result outcomes.
        try:
            state = TaskState(status)
        except ValueError as exc:
            raise InvalidTaskTransition(
                f"Result status {status!r} is not a known TaskState"
            ) from exc
        if state not in TERMINAL_STATES:
            raise InvalidTaskTransition(
                f"Result status {status!r} is not a terminal state"
            )
        async with self.lock:
            self.conn.execute(
                "INSERT OR IGNORE INTO results VALUES(?,?,?,?,?,?)",
                (result_id, task_id, agent_id, status, str(output)[:20000], now()),
            )
            self.conn.commit()

    # ── Disconnect reconciliation helpers ─────────────────────────────────────

    async def get_running_tasks(self, agent_id: str) -> list[dict]:
        """Return all tasks in RUNNING state that belong to ``agent_id``.

        Used by ``handle_client``'s ``finally`` block when an agent
        disconnects unexpectedly.  A task that was RUNNING when the agent
        disconnected will never deliver a RESULT, so it must be marked FAILED.

        RUNNING tasks are handled separately from stuck tasks (WAITING_ACK /
        QUEUED) because their outcome is more definitive: the agent was
        actively executing and then vanished.

        Parameters
        ----------
        agent_id : str
            The disconnecting agent's UUID.

        Returns
        -------
        list[dict]
            Each dict has keys ``task_id``, ``status``, and ``command``.
        """
        async with self.lock:
            rows = self.conn.execute(
                "SELECT task_id, status, command FROM tasks"
                " WHERE agent_id=? AND status='RUNNING'"
                " ORDER BY created_at",
                (agent_id,),
            ).fetchall()
            return [dict(r) for r in rows]

    async def get_stuck_tasks(self, agent_id: str) -> list[dict]:
        """Return tasks in WAITING_ACK or QUEUED state for ``agent_id``.

        These tasks were dispatched but the agent disconnected before it could
        execute or even acknowledge them.  Their outcome is unknowable — the
        agent has no persistent memory, so after a reconnect it will never
        spontaneously report on them.

        Called in two contexts:
        1. ``SYNC_STATE`` handler: reconcile on reconnect (cancel stuck tasks
           so the operator can re-dispatch them cleanly).
        2. ``handle_client`` finally block: catch any tasks that became stuck
           between the last SYNC_STATE and the current disconnect.

        RUNNING tasks are excluded because they are handled separately by
        ``get_running_tasks``.

        Parameters
        ----------
        agent_id : str
            The reconnecting or disconnecting agent's UUID.

        Returns
        -------
        list[dict]
            Each dict has keys ``task_id``, ``status``, and ``command``.
        """
        async with self.lock:
            rows = self.conn.execute(
                "SELECT task_id, status, command FROM tasks"
                " WHERE agent_id=? AND status IN ('WAITING_ACK','QUEUED')"
                " ORDER BY created_at",
                (agent_id,),
            ).fetchall()
            return [dict(r) for r in rows]

    async def cancel_stuck_task(self, task_id: str) -> None:
        """Transition a stuck task (WAITING_ACK or QUEUED) to CANCELLED.

        Delegates to ``update_task_status`` so the same transition validator
        is applied.  If the task has already advanced past QUEUED (e.g. a
        race where the agent sent TASK_STATUS RUNNING just before
        disconnecting), the validator will either permit or reject the
        transition according to the normal rules — RUNNING → CANCELLED is
        valid, so the task will also be cancelled in that edge case.

        Parameters
        ----------
        task_id : str
            UUID of the task to cancel.

        Raises
        ------
        TaskNotFoundError
            ``task_id`` does not exist.
        InvalidTaskTransition
            The current state does not permit CANCELLED (e.g. already terminal).
        """
        await self.update_task_status(task_id, "CANCELLED")

    # ── Durable interruption tracking ─────────────────────────────────────────

    async def timeout_task(self, task_id: str) -> bool:
        """Atomically transition a non-terminal task to TIMEOUT and record the event.

        Called exclusively by the server-side timeout watchdog coroutine.
        Uses the same atomic pattern as interrupt_task: reads current state,
        validates the TIMEOUT transition, writes the update, and inserts an
        interruption record — all in one transaction.

        Returns True if the task was advanced to TIMEOUT, False if it was
        already in a terminal state (normal completion raced the watchdog).

        Raises:
            TaskNotFoundError: task_id does not exist.
        """
        async with self.lock:
            row = self.conn.execute(
                "SELECT status FROM tasks WHERE task_id=?", (task_id,)
            ).fetchone()
            if row is None:
                raise TaskNotFoundError(task_id)
            old = row["status"]
            if old not in {"PENDING", "WAITING_ACK", "QUEUED", "RUNNING"}:
                return False  # already terminal — completion raced the watchdog
            validate_transition(old, "TIMEOUT")
            ts = now()
            try:
                self.conn.execute(
                    "UPDATE tasks SET status='TIMEOUT', updated_at=? WHERE task_id=?",
                    (ts, task_id),
                )
                self.conn.execute(
                    "INSERT OR IGNORE INTO task_interruptions "
                    "(task_id, previous_status, terminal_status, reason, outcome, interrupted_at) "
                    "VALUES (?,?,?,?,?,?)",
                    (task_id, old, "TIMEOUT", "task_timeout", "UNKNOWN_OUTCOME", ts),
                )
                self.conn.commit()
            except Exception:
                self.conn.rollback()
                raise
            return True

    async def interrupt_task(self, task_id: str, reason: str) -> bool:
        """Atomically record uncertain delivery/execution, without replaying work.

        The original task receives a terminal state consistent with the existing
        state machine, while the separate durable record preserves the original
        state and explanation. A caller may inspect this after process restart.
        """
        if not isinstance(reason, str) or not reason or len(reason) > 120:
            raise ValueError("interruption reason must be 1–120 characters")
        async with self.lock:
            row = self.conn.execute(
                "SELECT status FROM tasks WHERE task_id=?", (task_id,)
            ).fetchone()
            if row is None:
                raise TaskNotFoundError(task_id)
            old = row["status"]
            if old not in {"PENDING", "WAITING_ACK", "QUEUED", "RUNNING"}:
                return False
            target = "FAILED" if old == "RUNNING" else "CANCELLED"
            disposition = "NOT_SENT" if old == "PENDING" else "UNKNOWN_OUTCOME"
            validate_transition(old, target)
            ts = now()
            try:
                self.conn.execute(
                    "UPDATE tasks SET status=?, updated_at=? WHERE task_id=?",
                    (target, ts, task_id),
                )
                self.conn.execute(
                    "INSERT INTO task_interruptions "
                    "(task_id, previous_status, terminal_status, reason, outcome, interrupted_at) "
                    "VALUES (?,?,?,?,?,?)",
                    (task_id, old, target, reason, disposition, ts),
                )
                self.conn.commit()
            except Exception:
                self.conn.rollback()
                raise
            return True

    async def reconcile_process_restart(self) -> int:
        """Close orphaned sessions and record interrupted tasks on server restart.

        Must be called once during server startup, before accepting new peers.
        Does *not* replay any operations with uncertain outcomes.
        """
        async with self.lock:
            ts = now()
            rows = self.conn.execute(
                "SELECT task_id, status FROM tasks WHERE "
                "status IN ('PENDING','WAITING_ACK','QUEUED','RUNNING')"
            ).fetchall()
            try:
                for row in rows:
                    old = row["status"]
                    target = "FAILED" if old == "RUNNING" else "CANCELLED"
                    disposition = "NOT_SENT" if old == "PENDING" else "UNKNOWN_OUTCOME"
                    validate_transition(old, target)
                    self.conn.execute(
                        "UPDATE tasks SET status=?, updated_at=? WHERE task_id=?",
                        (target, ts, row["task_id"]),
                    )
                    self.conn.execute(
                        "INSERT OR IGNORE INTO task_interruptions "
                        "(task_id, previous_status, terminal_status, reason, outcome, interrupted_at) "
                        "VALUES (?,?,?,?,?,?)",
                        (row["task_id"], old, target, "server_restart", disposition, ts),
                    )
                self.conn.execute(
                    "UPDATE sessions SET state='DISCONNECTED', ended_at=? "
                    "WHERE ended_at IS NULL", (ts,)
                )
                self.conn.commit()
            except Exception:
                self.conn.rollback()
                raise
            return len(rows)

    async def reserve_replay(self, original_task_id: str, placeholder: str) -> bool:
        """Atomically claim the retry slot before dispatching the replacement task.

        Sets ``retry_task_id`` to ``placeholder`` (a sentinel string) only if
        the slot is still NULL.  Returns True if this caller won the race,
        False if another caller already claimed it.

        The caller must call ``mark_retried(original_task_id, real_new_id)``
        immediately after dispatch to replace the placeholder with the real ID.
        If dispatch fails, ``cancel_replay_reservation(original_task_id)`` clears
        the placeholder so the slot becomes available again.

        This prevents two concurrent callers from both dispatching a replacement
        for the same interrupted task.
        """
        async with self.lock:
            self.conn.execute(
                "UPDATE task_interruptions SET retry_task_id=? "
                "WHERE task_id=? AND retry_task_id IS NULL",
                (placeholder, original_task_id),
            )
            changed = self.conn.execute("SELECT changes()").fetchone()[0]
            self.conn.commit()
        return bool(changed)

    async def cancel_replay_reservation(self, original_task_id: str,
                                        placeholder: str) -> None:
        """Release a retry slot that was reserved but whose dispatch failed.

        Only clears the slot if it still holds the exact placeholder written
        by reserve_replay(), so a concurrent successful caller is never disturbed.
        """
        async with self.lock:
            self.conn.execute(
                "UPDATE task_interruptions SET retry_task_id=NULL "
                "WHERE task_id=? AND retry_task_id=?",
                (original_task_id, placeholder),
            )
            self.conn.commit()

    async def get_auto_replayable_interruptions(self, agent_id: str) -> list[dict]:
        """Return interrupted tasks that are safe to replay automatically.

        A task is auto-replayable when ALL of the following hold:
        1. It belongs to ``agent_id`` (no cross-agent replay).
        2. It has not already been retried (``retry_task_id IS NULL``).
        3. Its command is in the read-only allowlist (``echo``, ``get_info``,
           restricted ``shell``).  File transfers and lifecycle commands
           (``upload``, ``download``, ``self_remove``, ``persist``,
           ``unpersist``) are NEVER auto-replayed because they may have
           completed before the link dropped.
        4. For ``shell`` commands, the ``parameters_json`` must specify one of
           the three allowlisted sub-commands (``pwd``, ``whoami``, ``uname``).

        Returns the rows ordered by original creation time so the oldest
        pending task is replayed first.
        """
        import json as _json
        async with self.lock:
            rows = self.conn.execute(
                """SELECT i.task_id, i.previous_status, i.reason,
                          t.agent_id, t.command, t.parameters_json
                   FROM task_interruptions i
                   JOIN tasks t ON t.task_id = i.task_id
                   WHERE t.agent_id = ?
                     AND i.retry_task_id IS NULL
                     AND t.command IN ('echo', 'get_info', 'shell')
                   ORDER BY t.created_at""",
                (agent_id,),
            ).fetchall()
        result = []
        for row in rows:
            d = dict(row)
            if d["command"] == "shell":
                try:
                    params = _json.loads(d["parameters_json"])
                    if params.get("command") not in {"pwd", "whoami", "uname"}:
                        continue   # shell with non-allowlisted sub-command — skip
                except (ValueError, TypeError):
                    continue
            result.append(d)
        return result

    async def list_interruptions(self) -> list[dict]:
        """Return all interruption records joined with task metadata, newest first.

        Each row includes the original task's agent_id, command, and parameters_json
        so the CLI can display full context without a second query.
        """
        return await self._all(
            "SELECT i.*, t.agent_id, t.command, t.parameters_json "
            "FROM task_interruptions i JOIN tasks t ON t.task_id=i.task_id "
            "ORDER BY i.interrupted_at DESC, i.task_id"
        )

    async def get_interruption(self, task_id: str) -> dict | None:
        """Return the single interruption record for ``task_id``, or None.

        Used by the ``result`` CLI command to display uncertainty details
        when no result row exists for a task.
        """
        async with self.lock:
            row = self.conn.execute(
                "SELECT i.*, t.agent_id, t.command, t.parameters_json "
                "FROM task_interruptions i JOIN tasks t ON t.task_id=i.task_id "
                "WHERE i.task_id=?", (task_id,)
            ).fetchone()
            return dict(row) if row else None

    async def mark_retried(self, original_id: str, retry_id: str) -> bool:
        """Write the retry lineage, replacing NULL or a __pending_ placeholder.

        Accepts the slot when it is either NULL (manual retry path) or when
        it holds a ``__pending_*`` sentinel written by reserve_replay() (auto-
        replay path).  Refuses to overwrite a real (non-placeholder) retry_id
        so the one-shot guarantee is preserved.
        """
        async with self.lock:
            self.conn.execute(
                "UPDATE task_interruptions SET retry_task_id=? "
                "WHERE task_id=? AND (retry_task_id IS NULL OR retry_task_id LIKE '__pending_%')",
                (retry_id, original_id),
            )
            updated = self.conn.execute("SELECT changes()").fetchone()[0]
            self.conn.commit()
            return bool(updated)

    # ── Listing helpers ───────────────────────────────────────────────────────

    async def _all(self, sql: str) -> list[dict]:
        """Execute a SELECT and return all rows as plain dicts.

        Internal helper used by the public listing methods.  Converts
        sqlite3.Row objects (which look like dicts but are not picklable or
        serialisable) into real dicts so callers can use them freely.
        """
        async with self.lock:
            return [dict(r) for r in self.conn.execute(sql).fetchall()]

    async def list_agents(self) -> list[dict]:
        """Return all agent records ordered by first connection time (oldest first)."""
        return await self._all("SELECT * FROM agents ORDER BY first_seen")

    async def list_sessions(self) -> list[dict]:
        """Return all session records, most recent first."""
        return await self._all("SELECT * FROM sessions ORDER BY started_at DESC")

    async def list_tasks(self) -> list[dict]:
        """Return all task records, most recently created first."""
        return await self._all("SELECT * FROM tasks ORDER BY created_at DESC")

    async def get_task(self, task_id: str) -> dict | None:
        """Fetch one task for ownership checks without loading all tasks."""
        async with self.lock:
            row = self.conn.execute("SELECT * FROM tasks WHERE task_id=?", (task_id,)).fetchone()
            return dict(row) if row else None

    async def list_results(self, task_id: str) -> list[dict]:
        """Return result rows for ``task_id``, joined with task metadata.

        The JOIN includes ``command`` and ``parameters_json`` from the
        ``tasks`` table so the CLI's ``result`` command can display the
        full context (what was run, what came back) in a single query.

        Parameters
        ----------
        task_id : str
            The task whose results to retrieve.

        Returns
        -------
        list[dict]
            Ordered by result creation time (oldest first).  Empty list if
            the task has no result yet or the task_id does not exist.
        """
        async with self.lock:
            rows = self.conn.execute(
                """SELECT r.result_id,  r.task_id,  r.agent_id, r.status,
                          r.output,     r.created_at,
                          t.command,    t.parameters_json
                   FROM results r
                   JOIN tasks   t ON t.task_id = r.task_id
                   WHERE r.task_id = ?
                   ORDER BY r.created_at""",
                (task_id,),
            ).fetchall()
            return [dict(r) for r in rows]

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    async def close(self) -> None:
        """Close the SQLite connection.

        Called by ``run()`` in server/main.py after all connections have been
        closed and the server has stopped accepting new ones.  Safe to call
        more than once (guarded by the ``if self.conn`` check).
        """
        async with self.lock:
            if self.conn:
                self.conn.close()
                self.conn = None
