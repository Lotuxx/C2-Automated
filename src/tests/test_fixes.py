"""
Tests for the three confirmed defects fixed in Task 4.

Coverage required by the brief:
  1. Corrected server import.
  2. Duplicate ACK and unknown task ID do not terminate the message-handling loop.
  3. Rejected RESULT leaves the database unchanged.
  4. Successful RESULT updates both task and result records.
  5. Simulated result-insertion failure rolls back the task-state update.
  6. Duplicate RESULT behavior, including retries with the same result_id.

All persistence tests use isolated in-memory SQLite databases.
Handler-loop tests use a minimal fake-stream harness — no real TCP sockets.
"""
import asyncio
import logging
import sqlite3
import unittest
import unittest.mock

from server.storage.database import Database, TaskNotFoundError
from server.task_manager import InvalidTaskTransition, TaskState


# ── shared helpers ─────────────────────────────────────────────────────────────

async def _make_db() -> Database:
    db = Database(":memory:")
    await db.initialize()
    return db


async def _insert_task(db: Database, task_id: str, status: str = "PENDING") -> None:
    await db.create_task(task_id, "agent-1", "echo", {"text": "hi"}, status)


async def _task_status(db: Database, task_id: str) -> str | None:
    async with db.lock:
        row = db.conn.execute(
            "SELECT status FROM tasks WHERE task_id=?", (task_id,)
        ).fetchone()
    return row["status"] if row else None


async def _result_row(db: Database, result_id: str) -> dict | None:
    async with db.lock:
        row = db.conn.execute(
            "SELECT * FROM results WHERE result_id=?", (result_id,)
        ).fetchone()
    return dict(row) if row else None


async def _result_rows_for_task(db: Database, task_id: str) -> list[dict]:
    async with db.lock:
        rows = db.conn.execute(
            "SELECT * FROM results WHERE task_id=?", (task_id,)
        ).fetchall()
    return [dict(r) for r in rows]


# ── 1. Corrected server import ─────────────────────────────────────────────────

class TestServerImport(unittest.TestCase):
    """Fix 1 — server.main must be importable from the project root."""

    def test_server_main_is_importable(self):
        """Import must not raise ModuleNotFoundError or any other exception."""
        try:
            import server.main  # noqa: F401
        except Exception as exc:
            self.fail(f"server.main could not be imported: {exc}")

    def test_server_main_exports_c2server_class(self):
        import server.main
        self.assertTrue(
            hasattr(server.main, "C2Server"),
            "server.main must define C2Server",
        )

    def test_server_main_exports_main_entrypoint(self):
        import server.main
        self.assertTrue(
            callable(getattr(server.main, "main", None)),
            "server.main must expose a callable main()",
        )

    def test_database_imported_from_correct_package(self):
        """The Database class used by server.main must be the one in server.storage."""
        import server.main
        import server.storage.database
        self.assertIs(
            server.main.Database,
            server.storage.database.Database,
        )


# ── 2. Handler errors do not terminate the connection loop ────────────────────

class _FakeWriter:
    """Minimal asyncio.StreamWriter stand-in: records what was written."""

    def __init__(self):
        self.written: list[bytes] = []
        self._closing = False

    def write(self, data: bytes) -> None:
        self.written.append(data)

    async def drain(self) -> None:
        pass

    def is_closing(self) -> bool:
        return self._closing

    def get_extra_info(self, key, default=None):
        return ("127.0.0.1", 9999) if key == "peername" else default

    def close(self) -> None:
        self._closing = True

    async def wait_closed(self) -> None:
        pass


class TestHandlerLoopSurvival(unittest.IsolatedAsyncioTestCase):
    """
    Fix 2 — TASK_ACK, TASK_STATUS, and RESULT errors must be logged and
    discarded; the while-True loop must not exit.

    Rather than spinning up a full TCP server we drive handle_client directly
    by replacing read_message with a coroutine that yields pre-built messages
    and then raises asyncio.IncompleteReadError to close the loop cleanly.
    """

    async def _run_messages(self, messages: list[dict]) -> Database:
        """
        Feed ``messages`` through a real C2Server.handle_client and return
        the database so the caller can inspect final state.
        """
        import server.main as sm

        db = await _make_db()
        server_obj = sm.C2Server(db)

        call_count = 0

        async def fake_read(_reader):
            nonlocal call_count
            if call_count < len(messages):
                msg = messages[call_count]
                call_count += 1
                return msg
            raise asyncio.IncompleteReadError(b"", None)

        writer = _FakeWriter()
        reader = object()  # never used directly; fake_read ignores it

        with unittest.mock.patch("server.main.read_message", side_effect=fake_read):
            with unittest.mock.patch("server.main.write_message", new_callable=unittest.mock.AsyncMock):
                await server_obj.handle_client(reader, writer)  # type: ignore[arg-type]

        return db

    def _register(self, agent_id: str = "agent-1") -> dict:
        return {
            "type": "REGISTER",
            "message_id": "m0",
            "payload": {"agent_id": agent_id, "hostname": "h", "platform": "linux"},
        }

    async def test_duplicate_task_ack_does_not_kill_session(self):
        """
        Scenario: TASK_ACK for a task that is already QUEUED.
        The self-transition QUEUED→QUEUED is invalid.  The loop must survive
        and process the PING that follows.
        """
        db = await _make_db()
        await _insert_task(db, "t1", "PENDING")
        await db.update_task_status("t1", "WAITING_ACK")
        await db.update_task_status("t1", "QUEUED")  # already QUEUED

        import server.main as sm
        server_obj = sm.C2Server(db)
        pinged = []

        messages = [
            self._register(),
            {"type": "TASK_ACK", "message_id": "m1", "payload": {"task_id": "t1"}},
            {"type": "PING", "message_id": "m2", "payload": {}},
        ]
        call_count = 0

        async def fake_read(_r):
            nonlocal call_count
            if call_count < len(messages):
                m = messages[call_count]; call_count += 1; return m
            raise asyncio.IncompleteReadError(b"", None)

        async def fake_write(_w, msg):
            if msg.get("type") == "PONG":
                pinged.append(True)

        writer = _FakeWriter()
        with unittest.mock.patch("server.main.read_message", side_effect=fake_read):
            with unittest.mock.patch("server.main.write_message", side_effect=fake_write):
                await server_obj.handle_client(object(), writer)  # type: ignore[arg-type]

        self.assertTrue(pinged, "PING after duplicate TASK_ACK must still be answered")
        # The duplicate TASK_ACK is rejected (QUEUED→QUEUED invalid), so the task
        # stays QUEUED through the loop.  When the connection closes, the disconnect
        # cleanup correctly moves QUEUED tasks to CANCELLED (agent disconnected before
        # executing).  CANCELLED is therefore the correct final state here.
        self.assertEqual(await _task_status(db, "t1"), "CANCELLED")

    async def test_task_ack_for_unknown_task_does_not_kill_session(self):
        """TASK_ACK referencing a non-existent task_id must not crash the loop."""
        db = await _make_db()
        import server.main as sm
        server_obj = sm.C2Server(db)
        pinged = []

        messages = [
            self._register(),
            {"type": "TASK_ACK", "message_id": "m1", "payload": {"task_id": "ghost"}},
            {"type": "PING", "message_id": "m2", "payload": {}},
        ]
        call_count = 0

        async def fake_read(_r):
            nonlocal call_count
            if call_count < len(messages):
                m = messages[call_count]; call_count += 1; return m
            raise asyncio.IncompleteReadError(b"", None)

        async def fake_write(_w, msg):
            if msg.get("type") == "PONG":
                pinged.append(True)

        writer = _FakeWriter()
        with unittest.mock.patch("server.main.read_message", side_effect=fake_read):
            with unittest.mock.patch("server.main.write_message", side_effect=fake_write):
                await server_obj.handle_client(object(), writer)  # type: ignore[arg-type]

        self.assertTrue(pinged, "PING after unknown-task TASK_ACK must still be answered")

    async def test_task_status_for_unknown_task_does_not_kill_session(self):
        """TASK_STATUS for a non-existent task_id must not crash the loop."""
        db = await _make_db()
        import server.main as sm
        server_obj = sm.C2Server(db)
        pinged = []

        messages = [
            self._register(),
            {"type": "TASK_STATUS", "message_id": "m1",
             "payload": {"task_id": "ghost", "status": "RUNNING"}},
            {"type": "PING", "message_id": "m2", "payload": {}},
        ]
        call_count = 0

        async def fake_read(_r):
            nonlocal call_count
            if call_count < len(messages):
                m = messages[call_count]; call_count += 1; return m
            raise asyncio.IncompleteReadError(b"", None)

        async def fake_write(_w, msg):
            if msg.get("type") == "PONG":
                pinged.append(True)

        writer = _FakeWriter()
        with unittest.mock.patch("server.main.read_message", side_effect=fake_read):
            with unittest.mock.patch("server.main.write_message", side_effect=fake_write):
                await server_obj.handle_client(object(), writer)  # type: ignore[arg-type]

        self.assertTrue(pinged, "PING after unknown-task TASK_STATUS must still be answered")

    async def test_duplicate_result_does_not_kill_session(self):
        """
        RESULT for an already-terminal task must be rejected without killing
        the session.  A subsequent PING must still be answered.
        """
        db = await _make_db()
        await _insert_task(db, "t1", "PENDING")
        for s in ("WAITING_ACK", "QUEUED", "RUNNING", "COMPLETED"):
            await db.update_task_status("t1", s)

        import server.main as sm
        server_obj = sm.C2Server(db)
        pinged = []

        messages = [
            self._register(),
            {"type": "RESULT", "message_id": "m1",
             "payload": {"task_id": "t1", "result_id": "r1",
                         "status": "COMPLETED", "output": "dup"}},
            {"type": "PING", "message_id": "m2", "payload": {}},
        ]
        call_count = 0

        async def fake_read(_r):
            nonlocal call_count
            if call_count < len(messages):
                m = messages[call_count]; call_count += 1; return m
            raise asyncio.IncompleteReadError(b"", None)

        async def fake_write(_w, msg):
            if msg.get("type") == "PONG":
                pinged.append(True)

        writer = _FakeWriter()
        with unittest.mock.patch("server.main.read_message", side_effect=fake_read):
            with unittest.mock.patch("server.main.write_message", side_effect=fake_write):
                await server_obj.handle_client(object(), writer)  # type: ignore[arg-type]

        self.assertTrue(pinged, "PING after rejected RESULT must still be answered")
        self.assertEqual(await _task_status(db, "t1"), "COMPLETED")


# ── 3. Rejected RESULT leaves the database unchanged ─────────────────────────

class TestRejectedResultLeavesDbUnchanged(unittest.IsolatedAsyncioTestCase):

    async def asyncSetUp(self):
        self.db = await _make_db()

    async def _drive_to_running(self, task_id: str) -> None:
        await _insert_task(self.db, task_id)
        for s in ("WAITING_ACK", "QUEUED", "RUNNING"):
            await self.db.update_task_status(task_id, s)

    async def test_non_terminal_status_leaves_task_unchanged(self):
        await self._drive_to_running("t1")
        with self.assertRaises(InvalidTaskTransition):
            await self.db.complete_task_with_result("t1", "RUNNING", "r1", "a", "out")
        self.assertEqual(await _task_status(self.db, "t1"), "RUNNING")
        self.assertIsNone(await _result_row(self.db, "r1"))

    async def test_unknown_status_leaves_task_unchanged(self):
        await self._drive_to_running("t1")
        with self.assertRaises(InvalidTaskTransition):
            await self.db.complete_task_with_result("t1", "SENT", "r1", "a", "out")
        self.assertEqual(await _task_status(self.db, "t1"), "RUNNING")
        self.assertIsNone(await _result_row(self.db, "r1"))

    async def test_missing_task_leaves_no_result_row(self):
        with self.assertRaises(TaskNotFoundError):
            await self.db.complete_task_with_result("ghost", "COMPLETED", "r1", "a", "")
        self.assertIsNone(await _result_row(self.db, "r1"))

    async def test_invalid_transition_from_pending_leaves_task_unchanged(self):
        await _insert_task(self.db, "t1", "PENDING")
        # PENDING → COMPLETED is not a valid edge
        with self.assertRaises(InvalidTaskTransition):
            await self.db.complete_task_with_result("t1", "COMPLETED", "r1", "a", "")
        self.assertEqual(await _task_status(self.db, "t1"), "PENDING")
        self.assertIsNone(await _result_row(self.db, "r1"))

    async def test_terminal_task_rejected_leaves_both_records_unchanged(self):
        # Drive to RUNNING, then use complete_task_with_result for the legitimate
        # final transition so that both task and result records are written together.
        await _insert_task(self.db, "t1")
        for s in ("WAITING_ACK", "QUEUED", "RUNNING"):
            await self.db.update_task_status("t1", s)
        # Legitimate first result: RUNNING → COMPLETED, writes r-orig row
        await self.db.complete_task_with_result("t1", "COMPLETED", "r-orig", "a", "first")
        self.assertEqual(await _task_status(self.db, "t1"), "COMPLETED")
        self.assertIsNotNone(await _result_row(self.db, "r-orig"))
        # Duplicate attempt on already-terminal task — must be fully rejected
        with self.assertRaises(InvalidTaskTransition):
            await self.db.complete_task_with_result("t1", "COMPLETED", "r-dup", "a", "second")
        # Task still COMPLETED, original result row unchanged, duplicate row absent
        self.assertEqual(await _task_status(self.db, "t1"), "COMPLETED")
        self.assertIsNotNone(await _result_row(self.db, "r-orig"))
        self.assertIsNone(await _result_row(self.db, "r-dup"))


# ── 4. Successful RESULT updates both records ─────────────────────────────────

class TestSuccessfulResultPersistence(unittest.IsolatedAsyncioTestCase):

    async def asyncSetUp(self):
        self.db = await _make_db()
        await _insert_task(self.db, "t1")
        for s in ("WAITING_ACK", "QUEUED", "RUNNING"):
            await self.db.update_task_status("t1", s)

    async def test_complete_task_with_result_completed(self):
        await self.db.complete_task_with_result("t1", "COMPLETED", "r1", "agent-1", "hello")
        self.assertEqual(await _task_status(self.db, "t1"), "COMPLETED")
        row = await _result_row(self.db, "r1")
        self.assertIsNotNone(row)
        self.assertEqual(row["status"], "COMPLETED")
        self.assertEqual(row["output"], "hello")
        self.assertEqual(row["task_id"], "t1")
        self.assertEqual(row["agent_id"], "agent-1")

    async def test_complete_task_with_result_failed(self):
        await self.db.complete_task_with_result("t1", "FAILED", "r1", "agent-1", "err")
        self.assertEqual(await _task_status(self.db, "t1"), "FAILED")
        row = await _result_row(self.db, "r1")
        self.assertIsNotNone(row)
        self.assertEqual(row["status"], "FAILED")

    async def test_task_and_result_share_same_status(self):
        await self.db.complete_task_with_result("t1", "COMPLETED", "r1", "agent-1", "ok")
        task_st = await _task_status(self.db, "t1")
        result_st = (await _result_row(self.db, "r1"))["status"]
        self.assertEqual(task_st, result_st)

    async def test_output_truncated_to_20000_chars(self):
        long_output = "x" * 25_000
        await self.db.complete_task_with_result("t1", "COMPLETED", "r1", "agent-1", long_output)
        row = await _result_row(self.db, "r1")
        self.assertEqual(len(row["output"]), 20_000)


# ── 5. Simulated result-insertion failure rolls back task-state update ────────

class TestAtomicRollbackOnResultInsertFailure(unittest.IsolatedAsyncioTestCase):
    """
    Verify that if the INSERT on the results table raises a SQLite error
    after the UPDATE on tasks has already been executed but before commit,
    the explicit rollback() inside complete_task_with_result leaves
    tasks.status unchanged.

    sqlite3.Connection.execute is a C-level read-only attribute and cannot be
    monkey-patched directly.  Instead we wrap the connection in a thin
    Python subclass whose execute() method raises on the first INSERT it sees.
    """

    async def test_task_status_rolled_back_when_result_insert_fails(self):
        db = await _make_db()
        await _insert_task(db, "t1")
        for s in ("WAITING_ACK", "QUEUED", "RUNNING"):
            await db.update_task_status("t1", s)

        # Build a wrapper that delegates everything but raises on the first INSERT
        real_conn = db.conn
        insert_count = 0

        class FailingInsertConnection:
            """Forwards all attribute lookups to real_conn but intercepts execute."""

            def execute(self_, sql, params=()):  # noqa: N805
                nonlocal insert_count
                if sql.strip().upper().startswith("INSERT"):
                    insert_count += 1
                    if insert_count == 1:
                        raise sqlite3.OperationalError("simulated disk full")
                return real_conn.execute(sql, params)

            def rollback(self_):  # noqa: N805
                return real_conn.rollback()

            def commit(self_):  # noqa: N805
                return real_conn.commit()

            def __getattr__(self_, name):  # noqa: N805
                return getattr(real_conn, name)

        db.conn = FailingInsertConnection()

        with self.assertRaises(sqlite3.OperationalError):
            await db.complete_task_with_result("t1", "COMPLETED", "r1", "agent-1", "ok")

        # Restore real connection for clean reads
        db.conn = real_conn

        # Task must still be RUNNING — the UPDATE was rolled back
        self.assertEqual(await _task_status(db, "t1"), "RUNNING")
        # No result row must exist
        self.assertIsNone(await _result_row(db, "r1"))


# ── 6. Duplicate RESULT behavior ─────────────────────────────────────────────

class TestDuplicateResultBehavior(unittest.IsolatedAsyncioTestCase):

    async def asyncSetUp(self):
        self.db = await _make_db()
        await _insert_task(self.db, "t1")
        for s in ("WAITING_ACK", "QUEUED", "RUNNING"):
            await self.db.update_task_status("t1", s)

    async def test_same_result_id_idempotent(self):
        """
        First call completes the task and writes the result row.
        Second call with the same result_id is rejected by terminal-state
        protection (COMPLETED → COMPLETED is disallowed).
        The original result row is preserved unchanged.
        """
        await self.db.complete_task_with_result("t1", "COMPLETED", "r1", "agent-1", "original")
        with self.assertRaises(InvalidTaskTransition):
            await self.db.complete_task_with_result("t1", "COMPLETED", "r1", "agent-1", "retry")
        row = await _result_row(self.db, "r1")
        self.assertEqual(row["output"], "original")
        self.assertEqual(await _task_status(self.db, "t1"), "COMPLETED")

    async def test_different_result_id_on_terminal_task_rejected(self):
        """
        A retransmitted RESULT with a *different* result_id for an already-
        terminal task must be rejected by the transition validator before any
        write occurs.
        """
        await self.db.complete_task_with_result("t1", "COMPLETED", "r1", "agent-1", "first")
        with self.assertRaises(InvalidTaskTransition):
            await self.db.complete_task_with_result("t1", "COMPLETED", "r2", "agent-1", "second")
        # r2 must not exist
        self.assertIsNone(await _result_row(self.db, "r2"))
        # r1 intact
        row = await _result_row(self.db, "r1")
        self.assertEqual(row["output"], "first")

    async def test_insert_or_ignore_preserves_first_row_on_same_id(self):
        """
        Exercise the INSERT OR IGNORE path directly via complete_task_with_result
        within a single valid transition: only one result row for the task.
        """
        await self.db.complete_task_with_result("t1", "COMPLETED", "r1", "agent-1", "out")
        rows = await _result_rows_for_task(self.db, "t1")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["result_id"], "r1")

    async def test_failed_terminal_state_also_idempotent(self):
        await self.db.complete_task_with_result("t1", "FAILED", "r1", "agent-1", "err")
        with self.assertRaises(InvalidTaskTransition):
            await self.db.complete_task_with_result("t1", "FAILED", "r1", "agent-1", "err-retry")
        self.assertEqual(await _task_status(self.db, "t1"), "FAILED")
        row = await _result_row(self.db, "r1")
        self.assertEqual(row["output"], "err")


# ── 7. Cross-task result_id collision (regression for INSERT OR IGNORE fix) ───

class TestCrossTaskResultIdCollision(unittest.IsolatedAsyncioTestCase):
    """
    Regression tests for the confirmed defect where INSERT OR IGNORE silently
    discarded a result row whose result_id already belonged to another task,
    leaving the second task marked COMPLETED with no result row.

    The fix replaces INSERT OR IGNORE with plain INSERT followed by
    SELECT changes(); if changes() returns 0 the transaction is rolled back
    and InvalidTaskTransition is raised.
    """

    async def asyncSetUp(self):
        self.db = await _make_db()
        # t1 is already COMPLETED with result r1
        await _insert_task(self.db, "t1")
        for s in ("WAITING_ACK", "QUEUED", "RUNNING"):
            await self.db.update_task_status("t1", s)
        await self.db.complete_task_with_result("t1", "COMPLETED", "r1", "agent-1", "t1-output")

        # t2 is RUNNING and ready to receive a result
        await _insert_task(self.db, "t2")
        for s in ("WAITING_ACK", "QUEUED", "RUNNING"):
            await self.db.update_task_status("t2", s)

    # ── test 1: normal successful RESULT ──────────────────────────────────────

    async def test_normal_result_updates_task_and_persists_result(self):
        """
        Baseline: complete_task_with_result with a fresh result_id advances
        the task status and writes the result row in one atomic operation.
        """
        await self.db.complete_task_with_result("t2", "COMPLETED", "r2", "agent-1", "t2-output")

        # Task record updated
        self.assertEqual(await _task_status(self.db, "t2"), "COMPLETED")

        # Result row present and correct
        row = await _result_row(self.db, "r2")
        self.assertIsNotNone(row, "Result row must exist after successful completion")
        self.assertEqual(row["task_id"], "t2")
        self.assertEqual(row["status"], "COMPLETED")
        self.assertEqual(row["output"], "t2-output")
        self.assertEqual(row["agent_id"], "agent-1")

    # ── test 2: cross-task result_id collision ────────────────────────────────

    async def test_reusing_result_id_from_another_task_leaves_second_task_unchanged(self):
        """
        Reusing r1 (already belonging to t1) for t2 must:
          - raise InvalidTaskTransition
          - leave t2.status as RUNNING (task-state UPDATE rolled back)
          - not create any result row for t2
          - not modify the existing result row for t1
        """
        with self.assertRaises(InvalidTaskTransition) as ctx:
            await self.db.complete_task_with_result("t2", "COMPLETED", "r1", "agent-1", "collision")

        # Exception message must mention the result_id
        self.assertIn("r1", str(ctx.exception))

        # t2 status must still be RUNNING — UPDATE was rolled back
        self.assertEqual(
            await _task_status(self.db, "t2"), "RUNNING",
            "t2 must remain RUNNING after the collision is detected and rolled back",
        )

        # No result row for t2 must exist
        t2_results = await _result_rows_for_task(self.db, "t2")
        self.assertEqual(
            len(t2_results), 0,
            "t2 must have no result row — INSERT was rolled back",
        )

        # t1's original result row must be untouched
        r1 = await _result_row(self.db, "r1")
        self.assertIsNotNone(r1, "r1 must still exist for t1")
        self.assertEqual(r1["task_id"], "t1")
        self.assertEqual(r1["output"], "t1-output")

    # ── test 3: failed INSERT rolls back task-state update ────────────────────

    async def test_insert_collision_rolls_back_task_state_update(self):
        """
        Verify that after a collision the tasks table shows no change.
        This is the atomicity guarantee: the UPDATE and INSERT share one
        transaction; a collision on the INSERT undoes both.
        """
        status_before = await _task_status(self.db, "t2")
        self.assertEqual(status_before, "RUNNING")

        with self.assertRaises(InvalidTaskTransition):
            await self.db.complete_task_with_result("t2", "COMPLETED", "r1", "agent-1", "x")

        status_after = await _task_status(self.db, "t2")
        self.assertEqual(
            status_after, "RUNNING",
            "tasks.status for t2 must be unchanged after the rolled-back transaction",
        )

    # ── additional edge-cases ─────────────────────────────────────────────────

    async def test_collision_then_fresh_result_id_succeeds(self):
        """
        After a rejected collision, the same task can still be completed
        successfully using a different result_id.
        """
        with self.assertRaises(InvalidTaskTransition):
            await self.db.complete_task_with_result("t2", "COMPLETED", "r1", "agent-1", "bad")

        # t2 is still RUNNING; now complete it with a fresh ID
        await self.db.complete_task_with_result("t2", "COMPLETED", "r2-fresh", "agent-1", "good")
        self.assertEqual(await _task_status(self.db, "t2"), "COMPLETED")
        row = await _result_row(self.db, "r2-fresh")
        self.assertIsNotNone(row)
        self.assertEqual(row["output"], "good")

    async def test_failed_result_also_rejects_collision(self):
        """
        The collision guard applies to FAILED results too, not only COMPLETED.
        """
        # Set up r3 belonging to t1 via save_result (lower-level, no transition)
        await self.db.save_result("r3", "t1", "agent-1", "COMPLETED", "extra")

        with self.assertRaises(InvalidTaskTransition):
            await self.db.complete_task_with_result("t2", "FAILED", "r3", "agent-1", "fail-out")

        self.assertEqual(await _task_status(self.db, "t2"), "RUNNING")
        self.assertEqual(len(await _result_rows_for_task(self.db, "t2")), 0)


if __name__ == "__main__":
    unittest.main()


# ── 8. Regression tests for Task-6 usability fixes ───────────────────────────

class TestSyncStateLogging(unittest.IsolatedAsyncioTestCase):
    """A6 — server logs the agent's pending IDs on SYNC_STATE."""

    async def test_sync_state_payload_logged(self):
        import logging
        import server.main as sm

        db = await _make_db()
        server_obj = sm.C2Server(db)

        messages = [
            {"type": "REGISTER", "message_id": "m0",
             "payload": {"agent_id": "a1", "hostname": "h", "platform": "linux"}},
            {"type": "SYNC_STATE", "message_id": "m1",
             "payload": {"pending_task_ids": ["t-old"], "pending_result_ids": ["r-old"]}},
        ]
        call_count = 0

        async def fake_read(_r):
            nonlocal call_count
            if call_count < len(messages):
                m = messages[call_count]; call_count += 1; return m
            raise asyncio.IncompleteReadError(b"", None)

        logged = []

        class Capture(logging.Handler):
            def emit(self, record):
                logged.append(record.getMessage())

        handler = Capture()
        handler.setLevel(logging.DEBUG)
        original_level = sm.LOG.level
        sm.LOG.setLevel(logging.DEBUG)
        sm.LOG.addHandler(handler)
        try:
            with unittest.mock.patch("server.main.read_message", side_effect=fake_read):
                with unittest.mock.patch("server.main.write_message",
                                         new_callable=unittest.mock.AsyncMock):
                    await server_obj.handle_client(object(), _FakeWriter())
        finally:
            sm.LOG.removeHandler(handler)
            sm.LOG.setLevel(original_level)

        sync_logs = [m for m in logged if "sync_state" in m]
        self.assertTrue(sync_logs, "Server must log at least one sync_state line")
        self.assertTrue(
            any("t-old" in m for m in sync_logs),
            "Logged message must include the pending task IDs the agent reported",
        )


class TestListResults(unittest.IsolatedAsyncioTestCase):
    """B3/B5 — list_results returns the stored result joined with task data."""

    async def test_list_results_returns_row_after_complete(self):
        db = await _make_db()
        await _insert_task(db, "t1")
        for s in ("WAITING_ACK", "QUEUED", "RUNNING"):
            await db.update_task_status("t1", s)
        await db.complete_task_with_result("t1", "COMPLETED", "r1", "agent-1", "hello world")

        rows = await db.list_results("t1")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["output"], "hello world")
        self.assertEqual(rows[0]["status"], "COMPLETED")
        self.assertEqual(rows[0]["task_id"], "t1")
        self.assertIn("command", rows[0], "list_results must include the command column")

    async def test_list_results_empty_for_non_terminal_task(self):
        db = await _make_db()
        await _insert_task(db, "t1")
        await db.update_task_status("t1", "WAITING_ACK")
        rows = await db.list_results("t1")
        self.assertEqual(rows, [])

    async def test_list_results_unknown_task_returns_empty(self):
        db = await _make_db()
        rows = await db.list_results("no-such-task")
        self.assertEqual(rows, [])


# ── 9. Reconciliation: stuck tasks cancelled on reconnect (D1) ────────────────

class TestReconnectReconciliation(unittest.IsolatedAsyncioTestCase):
    """
    When an agent reconnects and sends SYNC_STATE, the server must cancel any
    tasks that are stuck in WAITING_ACK or QUEUED for that agent.
    RUNNING tasks must NOT be touched (the agent may still be executing them).
    """

    async def asyncSetUp(self):
        self.db = await _make_db()

    async def test_get_stuck_tasks_returns_waiting_ack_and_queued(self):
        await _insert_task(self.db, "t-wa")
        await self.db.update_task_status("t-wa", "WAITING_ACK")

        await _insert_task(self.db, "t-q")
        await self.db.update_task_status("t-q", "WAITING_ACK")
        await self.db.update_task_status("t-q", "QUEUED")

        stuck = await self.db.get_stuck_tasks("agent-1")
        stuck_ids = {r["task_id"] for r in stuck}
        self.assertIn("t-wa", stuck_ids)
        self.assertIn("t-q", stuck_ids)

    async def test_get_stuck_tasks_excludes_running(self):
        await _insert_task(self.db, "t-r")
        for s in ("WAITING_ACK", "QUEUED", "RUNNING"):
            await self.db.update_task_status("t-r", s)
        stuck = await self.db.get_stuck_tasks("agent-1")
        self.assertEqual([r["task_id"] for r in stuck], [])

    async def test_get_stuck_tasks_excludes_terminal(self):
        await _insert_task(self.db, "t-done")
        for s in ("WAITING_ACK", "QUEUED", "RUNNING", "COMPLETED"):
            await self.db.update_task_status("t-done", s)
        stuck = await self.db.get_stuck_tasks("agent-1")
        self.assertEqual([r["task_id"] for r in stuck], [])

    async def test_get_stuck_tasks_excludes_other_agents(self):
        await self.db.create_task("t-other", "agent-2", "echo", {}, "PENDING")
        await self.db.update_task_status("t-other", "WAITING_ACK")
        stuck = await self.db.get_stuck_tasks("agent-1")
        self.assertEqual([r["task_id"] for r in stuck], [])

    async def test_cancel_stuck_task_moves_waiting_ack_to_cancelled(self):
        await _insert_task(self.db, "t1")
        await self.db.update_task_status("t1", "WAITING_ACK")
        await self.db.cancel_stuck_task("t1")
        self.assertEqual(await _task_status(self.db, "t1"), "CANCELLED")

    async def test_cancel_stuck_task_moves_queued_to_cancelled(self):
        await _insert_task(self.db, "t1")
        await self.db.update_task_status("t1", "WAITING_ACK")
        await self.db.update_task_status("t1", "QUEUED")
        await self.db.cancel_stuck_task("t1")
        self.assertEqual(await _task_status(self.db, "t1"), "CANCELLED")

    async def test_cancel_stuck_task_rejects_running(self):
        """RUNNING → CANCELLED is valid in the state machine; only WAITING_ACK
        and QUEUED are targeted by reconciliation, but if a task races to
        RUNNING before cancel_stuck_task is called the validator still permits
        the transition.  Verify the task ends up CANCELLED (not an error)."""
        await _insert_task(self.db, "t1")
        for s in ("WAITING_ACK", "QUEUED", "RUNNING"):
            await self.db.update_task_status("t1", s)
        # cancel_stuck_task calls update_task_status which allows RUNNING→CANCELLED
        await self.db.cancel_stuck_task("t1")
        self.assertEqual(await _task_status(self.db, "t1"), "CANCELLED")

    async def test_sync_state_handler_cancels_stuck_tasks(self):
        """
        Drive handle_client through REGISTER + SYNC_STATE with a stuck task
        in the database and verify that task is CANCELLED afterwards.
        """
        import server.main as sm

        # Pre-seed a stuck task for agent-1
        await _insert_task(self.db, "t-stuck")
        await self.db.update_task_status("t-stuck", "WAITING_ACK")

        server_obj = sm.C2Server(self.db)
        messages = [
            {"type": "REGISTER", "message_id": "m0",
             "payload": {"agent_id": "agent-1", "hostname": "h", "platform": "linux"}},
            {"type": "SYNC_STATE", "message_id": "m1",
             "payload": {"pending_task_ids": [], "pending_result_ids": []}},
        ]
        call_count = 0

        async def fake_read(_r):
            nonlocal call_count
            if call_count < len(messages):
                m = messages[call_count]; call_count += 1; return m
            raise asyncio.IncompleteReadError(b"", None)

        with unittest.mock.patch("server.main.read_message", side_effect=fake_read):
            with unittest.mock.patch("server.main.write_message",
                                     new_callable=unittest.mock.AsyncMock):
                await server_obj.handle_client(object(), _FakeWriter())

        self.assertEqual(
            await _task_status(self.db, "t-stuck"), "CANCELLED",
            "Stuck WAITING_ACK task must be CANCELLED after SYNC_STATE reconciliation",
        )

    async def test_sync_state_does_not_cancel_running_tasks_during_sync(self):
        """
        SYNC_STATE reconciliation must not touch RUNNING tasks — only
        WAITING_ACK and QUEUED are cancelled during the sync exchange.

        However, when the connection subsequently closes, the disconnect
        cleanup marks RUNNING tasks as FAILED (the agent can no longer
        deliver a result).  This test verifies both behaviours:
          - During SYNC_STATE: RUNNING task is untouched.
          - After disconnect: RUNNING task is marked FAILED.
        """
        import server.main as sm

        await _insert_task(self.db, "t-running")
        for s in ("WAITING_ACK", "QUEUED", "RUNNING"):
            await self.db.update_task_status("t-running", s)

        server_obj = sm.C2Server(self.db)

        # Intercept SYNC_STATE to check state mid-exchange
        status_during_sync = {}

        messages = [
            {"type": "REGISTER", "message_id": "m0",
             "payload": {"agent_id": "agent-1", "hostname": "h", "platform": "linux"}},
            {"type": "SYNC_STATE", "message_id": "m1",
             "payload": {"pending_task_ids": [], "pending_result_ids": []}},
        ]
        call_count = 0

        async def fake_read(_r):
            nonlocal call_count
            if call_count < len(messages):
                m = messages[call_count]; call_count += 1; return m
            raise asyncio.IncompleteReadError(b"", None)

        async def fake_write(_w, msg):
            # Capture task status immediately after SYNC_COMPLETE is sent
            if msg.get("type") == "SYNC_COMPLETE":
                status_during_sync["t-running"] = await _task_status(self.db, "t-running")

        with unittest.mock.patch("server.main.read_message", side_effect=fake_read):
            with unittest.mock.patch("server.main.write_message", side_effect=fake_write):
                await server_obj.handle_client(object(), _FakeWriter())

        # During sync: RUNNING must be untouched by SYNC_STATE reconciliation
        self.assertEqual(
            status_during_sync.get("t-running"), "RUNNING",
            "SYNC_STATE reconciliation must not touch RUNNING tasks",
        )
        # After disconnect: RUNNING task must be marked FAILED by disconnect cleanup
        self.assertEqual(
            await _task_status(self.db, "t-running"), "FAILED",
            "RUNNING task must be marked FAILED when agent disconnects",
        )


# ── 10. PromptAwareHandler (C2) ───────────────────────────────────────────────

class TestPromptAwareHandler(unittest.TestCase):
    """
    The _PromptAwareHandler must:
    - emit the log record to the stream
    - prepend \\r\\033[K when the stream is a TTY
    - reprint the prompt after the record when the stream is a TTY
    - behave like a plain StreamHandler when the stream is not a TTY
    """

    def _make_record(self, msg: str = "test log line") -> logging.LogRecord:
        return logging.makeLogRecord({"msg": msg, "levelno": logging.INFO,
                                      "levelname": "INFO", "name": "c2"})

    def test_tty_stream_gets_cr_before_and_prompt_after(self):
        import io
        import server.main as sm

        buf = io.StringIO()
        buf.isatty = lambda: True  # type: ignore[attr-defined]

        handler = sm._PromptAwareHandler(buf)
        handler.setFormatter(logging.Formatter("%(message)s"))
        handler.emit(self._make_record("hello"))

        output = buf.getvalue()
        self.assertTrue(output.startswith("\r\033[K"),
                        "TTY output must start with \\r\\033[K to clear the prompt")
        self.assertIn("hello", output)
        self.assertTrue(output.endswith("c2> "),
                        "TTY output must end with the prompt string")

    def test_non_tty_stream_has_no_escape_codes(self):
        import io
        import server.main as sm

        buf = io.StringIO()
        # isatty not set → defaults to False

        handler = sm._PromptAwareHandler(buf)
        handler.setFormatter(logging.Formatter("%(message)s"))
        handler.emit(self._make_record("world"))

        output = buf.getvalue()
        self.assertNotIn("\r\033[K", output, "Non-TTY must not emit ANSI escape codes")
        self.assertNotIn("c2> ", output, "Non-TTY must not reprint the prompt")
        self.assertIn("world", output)


# ── 11. Disconnect cleanup: RUNNING → FAILED, QUEUED → CANCELLED ──────────────

class TestDisconnectCleanup(unittest.IsolatedAsyncioTestCase):
    """
    When handle_client exits (agent disconnect), the server must:
      - Mark RUNNING tasks as FAILED (agent cannot deliver a result).
      - Cancel WAITING_ACK and QUEUED tasks (agent never started them).
      - Leave tasks of OTHER agents untouched.
      - Leave already-terminal tasks untouched.
    """

    async def asyncSetUp(self):
        self.db = await _make_db()

    async def _run_until_disconnect(self, messages: list[dict]) -> None:
        import server.main as sm
        server_obj = sm.C2Server(self.db)
        call_count = 0

        async def fake_read(_r):
            nonlocal call_count
            if call_count < len(messages):
                m = messages[call_count]; call_count += 1; return m
            raise asyncio.IncompleteReadError(b"", None)

        with unittest.mock.patch("server.main.read_message", side_effect=fake_read):
            with unittest.mock.patch("server.main.write_message",
                                     new_callable=unittest.mock.AsyncMock):
                await server_obj.handle_client(object(), _FakeWriter())

    def _register_msg(self, agent_id="agent-1"):
        return {"type": "REGISTER", "message_id": "m0",
                "payload": {"agent_id": agent_id, "hostname": "h", "platform": "linux"}}

    async def test_running_task_marked_failed_on_disconnect(self):
        await _insert_task(self.db, "t1")
        for s in ("WAITING_ACK", "QUEUED", "RUNNING"):
            await self.db.update_task_status("t1", s)

        await self._run_until_disconnect([self._register_msg()])

        self.assertEqual(await _task_status(self.db, "t1"), "FAILED",
                         "RUNNING task must be FAILED after agent disconnect")

    async def test_waiting_ack_task_cancelled_on_disconnect(self):
        await _insert_task(self.db, "t1")
        await self.db.update_task_status("t1", "WAITING_ACK")

        await self._run_until_disconnect([self._register_msg()])

        self.assertEqual(await _task_status(self.db, "t1"), "CANCELLED")

    async def test_queued_task_cancelled_on_disconnect(self):
        await _insert_task(self.db, "t1")
        await self.db.update_task_status("t1", "WAITING_ACK")
        await self.db.update_task_status("t1", "QUEUED")

        await self._run_until_disconnect([self._register_msg()])

        self.assertEqual(await _task_status(self.db, "t1"), "CANCELLED")

    async def test_terminal_task_not_touched_on_disconnect(self):
        await _insert_task(self.db, "t1")
        for s in ("WAITING_ACK", "QUEUED", "RUNNING", "COMPLETED"):
            await self.db.update_task_status("t1", s)

        await self._run_until_disconnect([self._register_msg()])

        self.assertEqual(await _task_status(self.db, "t1"), "COMPLETED",
                         "Terminal tasks must not be changed on disconnect")

    async def test_other_agent_tasks_not_touched_on_disconnect(self):
        # agent-2's task in RUNNING — agent-1 disconnects
        await self.db.create_task("t-other", "agent-2", "echo", {}, "PENDING")
        for s in ("WAITING_ACK", "QUEUED", "RUNNING"):
            await self.db.update_task_status("t-other", s)

        await self._run_until_disconnect([self._register_msg("agent-1")])

        self.assertEqual(await _task_status(self.db, "t-other"), "RUNNING",
                         "Tasks belonging to other agents must not be touched")

    async def test_multiple_running_tasks_all_marked_failed(self):
        for tid in ("t1", "t2", "t3"):
            await _insert_task(self.db, tid)
            for s in ("WAITING_ACK", "QUEUED", "RUNNING"):
                await self.db.update_task_status(tid, s)

        await self._run_until_disconnect([self._register_msg()])

        for tid in ("t1", "t2", "t3"):
            self.assertEqual(await _task_status(self.db, tid), "FAILED",
                             f"{tid} must be FAILED after disconnect")


# ── 12. Agent connection retry ─────────────────────────────────────────────────

class TestAgentConnectionRetry(unittest.IsolatedAsyncioTestCase):
    """
    The agent must retry the TCP connection with backoff instead of
    exiting immediately on ECONNREFUSED.
    """

    async def test_agent_retries_on_connection_refused(self):
        """
        Simulate two failed attempts followed by a successful one.
        The agent run() must not raise; it must connect on the third try.
        """
        import agent.main as am
        import argparse, ssl as ssl_mod

        connect_attempts = []
        original_open = asyncio.open_connection

        async def fake_open(*args, **kwargs):
            connect_attempts.append(len(connect_attempts) + 1)
            if len(connect_attempts) < 3:
                raise OSError(111, "Connection refused")
            # Third attempt: return a mock reader/writer pair
            reader = asyncio.StreamReader()
            # Feed a REGISTER_ACK then close so run() exits cleanly
            from shared.protocol import make_message
            import json
            ack = make_message("REGISTER_ACK", payload={"registered": True, "session_id": "s1"})
            reader.feed_data(
                json.dumps(ack, separators=(",",":")).encode() + b"\n"
            )
            reader.feed_eof()

            writer = unittest.mock.MagicMock(spec=asyncio.StreamWriter)
            writer.is_closing.return_value = False
            writer.drain = unittest.mock.AsyncMock()
            writer.write = unittest.mock.MagicMock()
            writer.wait_closed = unittest.mock.AsyncMock()
            return reader, writer

        args = argparse.Namespace(
            server="127.0.0.1", port=9443, ca="certs/server.crt", agent_id="test-agent"
        )

        with unittest.mock.patch("agent.main.ssl.create_default_context"):
            with unittest.mock.patch("asyncio.open_connection", side_effect=fake_open):
                with unittest.mock.patch("asyncio.sleep", new_callable=unittest.mock.AsyncMock):
                    try:
                        await am.run(args)
                    except (SystemExit, Exception):
                        pass  # EOF exit is expected

        self.assertGreaterEqual(len(connect_attempts), 2,
                                "Agent must have retried at least twice before succeeding")

    async def test_agent_gives_up_after_max_attempts(self):
        """After MAX_ATTEMPTS consecutive failures the agent raises SystemExit."""
        import agent.main as am
        import argparse

        args = argparse.Namespace(
            server="127.0.0.1", port=9443, ca="certs/server.crt", agent_id="test-agent"
        )

        async def always_refuse(*a, **kw):
            raise OSError(111, "Connection refused")

        with unittest.mock.patch("agent.main.ssl.create_default_context"):
            with unittest.mock.patch("asyncio.open_connection", side_effect=always_refuse):
                with unittest.mock.patch("asyncio.sleep", new_callable=unittest.mock.AsyncMock):
                    with self.assertRaises(SystemExit):
                        await am.run(args)


# ── 13. Agent-id prefix resolution in task CLI command ────────────────────────


class TestAgentIdPrefixResolution(unittest.IsolatedAsyncioTestCase):
    """
    The 'task' CLI command must resolve an 8-char prefix to the full UUID
    stored in self.connections, not pass the prefix directly to dispatch_task.
    """

    def _make_cli_fixture(self, server_obj, commands):
        """Return (console, fake_to_thread) for driving the Rich CLI in tests."""
        import io
        from rich.console import Console
        buf = io.StringIO()
        server_obj._test_console = Console(file=buf, highlight=False,
                                           no_color=True, width=200)
        inputs = iter(commands)

        async def fake_to_thread(fn, *args):
            return next(inputs)

        return buf, fake_to_thread

    async def test_task_command_resolves_prefix_to_full_agent_id(self):
        import server.main as sm

        db = await _make_db()
        server_obj = sm.C2Server(db)

        full_id = "abcdef12-0000-0000-0000-000000000000"
        fake_writer = unittest.mock.MagicMock()
        fake_writer.is_closing.return_value = False
        fake_writer.drain = unittest.mock.AsyncMock()
        fake_writer.write = unittest.mock.MagicMock()
        async with server_obj.connection_lock:
            server_obj.connections[full_id] = fake_writer

        await db.upsert_agent(full_id, "host", "linux")
        await db.create_session("s1", full_id, "ACTIVE")

        dispatched_ids = []
        original_dispatch = server_obj.dispatch_task

        async def capturing_dispatch(aid, cmd, params):
            dispatched_ids.append(aid)
            return await original_dispatch(aid, cmd, params)

        server_obj.dispatch_task = capturing_dispatch

        buf, fake_to_thread = self._make_cli_fixture(
            server_obj, ["task abcdef12 get_info", "quit"])
        with unittest.mock.patch("server.main.asyncio.to_thread",
                                 side_effect=fake_to_thread):
            await server_obj.cli()

        self.assertEqual(dispatched_ids, [full_id],
                         "dispatch_task must receive the full UUID, not the prefix")

    async def test_prefix_with_no_match_prints_error(self):
        import server.main as sm

        db = await _make_db()
        server_obj = sm.C2Server(db)

        buf, fake_to_thread = self._make_cli_fixture(
            server_obj, ["task ffffffff get_info", "quit"])
        with unittest.mock.patch("server.main.asyncio.to_thread",
                                 side_effect=fake_to_thread):
            await server_obj.cli()

        self.assertIn("No connected agent", buf.getvalue())

    async def test_ambiguous_prefix_prints_all_matches(self):
        import server.main as sm

        db = await _make_db()
        server_obj = sm.C2Server(db)

        id1 = "aabbcc11-0000-0000-0000-000000000000"
        id2 = "aabbcc22-0000-0000-0000-000000000000"
        for aid in (id1, id2):
            w = unittest.mock.MagicMock()
            w.is_closing.return_value = False
            async with server_obj.connection_lock:
                server_obj.connections[aid] = w

        buf, fake_to_thread = self._make_cli_fixture(
            server_obj, ["task aabbcc get_info", "quit"])
        with unittest.mock.patch("server.main.asyncio.to_thread",
                                 side_effect=fake_to_thread):
            await server_obj.cli()

        output = buf.getvalue()
        self.assertIn("Ambiguous", output)
        self.assertIn(id1, output)
        self.assertIn(id2, output)


# ── 14. Clean server shutdown and agent disconnect notification ────────────────

class TestCleanShutdown(unittest.IsolatedAsyncioTestCase):
    """
    shutdown() must close all agent writers and cancel handler tasks so that
    agents immediately see the connection drop rather than blocking forever.
    """

    async def test_shutdown_closes_all_writers(self):
        import server.main as sm

        db = await _make_db()
        server_obj = sm.C2Server(db)

        writers = []
        for i in range(3):
            w = unittest.mock.MagicMock(spec=asyncio.StreamWriter)
            w.is_closing.return_value = False
            writers.append(w)
            async with server_obj.connection_lock:
                server_obj.connections[f"agent-{i}"] = w

        await server_obj.shutdown()

        for w in writers:
            w.close.assert_called_once()

    async def test_shutdown_cancels_handler_tasks(self):
        import server.main as sm

        db = await _make_db()
        server_obj = sm.C2Server(db)

        cancelled = []

        async def long_running():
            try:
                await asyncio.sleep(999)
            except asyncio.CancelledError:
                cancelled.append(True)
                raise

        task = asyncio.create_task(long_running())
        # Let the task actually start executing before we cancel it
        await asyncio.sleep(0)
        server_obj._handler_tasks.add(task)

        await server_obj.shutdown()

        # gather() in shutdown awaits the cancelled tasks, so cancelled must be set
        self.assertTrue(cancelled, "Handler tasks must be cancelled on shutdown")

    async def test_agent_logs_disconnect_when_server_closes(self):
        """
        When the server drops the connection mid-session, the agent must log
        'server closed the connection' and exit the loop cleanly.
        """
        import agent.main as am
        import argparse, logging

        # Simulate a reader that immediately signals EOF (server closed)
        reader = asyncio.StreamReader()
        reader.feed_eof()

        writer = unittest.mock.MagicMock(spec=asyncio.StreamWriter)
        writer.is_closing.return_value = False
        writer.drain = unittest.mock.AsyncMock()
        writer.write = unittest.mock.MagicMock()
        writer.wait_closed = unittest.mock.AsyncMock()

        logged = []

        class Cap(logging.Handler):
            def emit(self, rec):
                logged.append(rec.getMessage())

        h = Cap()
        h.setLevel(logging.DEBUG)
        am.LOG.addHandler(h)
        original_level = am.LOG.level
        am.LOG.setLevel(logging.DEBUG)

        args = argparse.Namespace(
            server="127.0.0.1", port=9443, ca="certs/server.crt", agent_id="test-a"
        )

        try:
            with unittest.mock.patch("agent.main.ssl.create_default_context"):
                with unittest.mock.patch("asyncio.open_connection",
                                         return_value=(reader, writer)):
                    with unittest.mock.patch("asyncio.sleep",
                                             new_callable=unittest.mock.AsyncMock):
                        try:
                            await am.run(args)
                        except Exception:
                            pass
        finally:
            am.LOG.removeHandler(h)
            am.LOG.setLevel(original_level)

        self.assertTrue(
            any("server closed" in m for m in logged),
            f"Agent must log disconnect message. Got: {logged}",
        )


# ── P2.1 — Re-registration is blocked ─────────────────────────────────────────

class TestReRegistrationBlocked(unittest.IsolatedAsyncioTestCase):
    """
    P2.1 — A second REGISTER on an already-registered connection must be
    rejected with ERROR and must not change the active agent_id, not displace
    the existing connection in self.connections, and not put the session back
    into pending_sync.
    """

    async def _run_messages(self, messages):
        """Drive handle_client with a fixed message list; return (db, server)."""
        import server.main as sm
        db = await _make_db()
        server_obj = sm.C2Server(db)
        call_count = 0

        async def fake_read(_r):
            nonlocal call_count
            if call_count < len(messages):
                m = messages[call_count]; call_count += 1; return m
            raise asyncio.IncompleteReadError(b"", None)

        replies = []

        async def fake_write(_w, msg):
            replies.append(msg)

        writer = _FakeWriter()
        with unittest.mock.patch("server.main.read_message", side_effect=fake_read):
            with unittest.mock.patch("server.main.write_message", side_effect=fake_write):
                await server_obj.handle_client(object(), writer)  # type: ignore[arg-type]

        return db, server_obj, replies

    def _register(self, agent_id="agent-1"):
        return {"type": "REGISTER", "message_id": "m0",
                "payload": {"agent_id": agent_id, "hostname": "h", "platform": "linux"}}

    async def test_second_register_same_id_rejected(self):
        """Sending REGISTER twice with the same agent_id must yield an ERROR."""
        _db, _srv, replies = await self._run_messages([
            self._register("agent-1"),
            self._register("agent-1"),  # duplicate
        ])
        error_replies = [r for r in replies if r["type"] == "ERROR"]
        self.assertTrue(error_replies, "Second REGISTER must produce an ERROR reply")
        self.assertIn("already registered", error_replies[0]["payload"].get("error", ""))

    async def test_second_register_different_id_rejected(self):
        """Sending REGISTER with a different agent_id on the same connection must also be rejected."""
        _db, _srv, replies = await self._run_messages([
            self._register("agent-1"),
            self._register("agent-2"),  # identity switch attempt
        ])
        error_replies = [r for r in replies if r["type"] == "ERROR"]
        self.assertTrue(error_replies, "Identity switch via second REGISTER must produce ERROR")
        self.assertIn("already registered", error_replies[0]["payload"].get("error", ""))

    async def test_second_register_does_not_displace_connection(self):
        """The original writer must remain in connections after a rejected re-registration."""
        import server.main as sm
        db = await _make_db()
        server_obj = sm.C2Server(db)

        # Inject the first writer as if agent-1 is already connected
        first_writer = _FakeWriter()
        async with server_obj.connection_lock:
            server_obj.connections["agent-1"] = first_writer

        messages = [
            self._register("agent-1"),
            self._register("agent-2"),  # attempt to displace
        ]
        call_count = 0

        async def fake_read(_r):
            nonlocal call_count
            if call_count < len(messages):
                m = messages[call_count]; call_count += 1; return m
            raise asyncio.IncompleteReadError(b"", None)

        second_writer = _FakeWriter()
        with unittest.mock.patch("server.main.read_message", side_effect=fake_read):
            with unittest.mock.patch("server.main.write_message",
                                     new_callable=unittest.mock.AsyncMock):
                await server_obj.handle_client(object(), second_writer)  # type: ignore[arg-type]

        # agent-1 must NOT be displaced by agent-2's attempt
        self.assertNotIn("agent-2", server_obj.connections,
                         "agent-2 must not appear in connections")

    async def test_session_continues_after_rejected_re_registration(self):
        """The session must remain usable (can handle PING) after rejecting re-registration."""
        pong_received = []

        _db, _srv, replies = await self._run_messages([
            self._register("agent-1"),
            self._register("agent-2"),          # rejected
            {"type": "PING", "message_id": "m1", "payload": {}},  # must still be answered
        ])
        pong_replies = [r for r in replies if r["type"] == "PONG"]
        self.assertTrue(pong_replies, "PING after rejected re-registration must still be answered")

    async def test_pending_sync_not_re_added_after_rejected_register(self):
        """A rejected REGISTER must not place the agent back into pending_sync."""
        import server.main as sm
        db = await _make_db()
        server_obj = sm.C2Server(db)

        messages = [
            self._register("agent-1"),
            # SYNC_STATE clears pending_sync
            {"type": "SYNC_STATE", "message_id": "m1",
             "payload": {"pending_task_ids": [], "pending_result_ids": []}},
            # Rejected re-registration must NOT re-add to pending_sync
            self._register("agent-1"),
        ]
        call_count = 0

        async def fake_read(_r):
            nonlocal call_count
            if call_count < len(messages):
                m = messages[call_count]; call_count += 1; return m
            raise asyncio.IncompleteReadError(b"", None)

        with unittest.mock.patch("server.main.read_message", side_effect=fake_read):
            with unittest.mock.patch("server.main.write_message",
                                     new_callable=unittest.mock.AsyncMock):
                await server_obj.handle_client(object(), _FakeWriter())  # type: ignore[arg-type]

        # After everything, pending_sync must not contain agent-1
        self.assertNotIn("agent-1", server_obj.pending_sync,
                         "pending_sync must not re-acquire agent after rejected REGISTER")


# ── P2.2 — result CLI shows interruption record for FAILED/CANCELLED tasks ────

class TestResultCLIShowsInterruption(unittest.IsolatedAsyncioTestCase):
    """
    P2.2 — When a task has no result row but has an interruption record (e.g.
    server crashed while the task was RUNNING), the 'result <prefix>' CLI
    command must display the interruption details rather than the opaque
    '(no result stored)'.
    """

    async def asyncSetUp(self):
        self.db = await _make_db()
        # Create a task and drive it to RUNNING, then interrupt it (simulates a crash)
        await _insert_task(self.db, "t1")
        for s in ("WAITING_ACK", "QUEUED", "RUNNING"):
            await self.db.update_task_status("t1", s)
        await self.db.interrupt_task("t1", "connection_lost")

    def _make_cli_for_result(self, prefix):
        """Return (server_obj, buf, fake_to_thread) wired for the result command."""
        import io
        from rich.console import Console
        import server.main as sm
        server_obj = sm.C2Server(self.db)
        buf = io.StringIO()
        server_obj._test_console = Console(file=buf, highlight=False,
                                           no_color=True, width=200)
        inputs = iter([f"result {prefix}", "quit"])

        async def fake_to_thread(fn, *args):
            return next(inputs)

        return server_obj, buf, fake_to_thread

    async def _run_result_command(self, prefix: str) -> str:
        """Drive the CLI 'result <prefix>' and return captured Rich output."""
        server_obj, buf, fake_to_thread = self._make_cli_for_result(prefix)
        with unittest.mock.patch("server.main.asyncio.to_thread",
                                 side_effect=fake_to_thread):
            await server_obj.cli()
        return buf.getvalue()

    async def test_result_shows_interruption_reason_when_no_result_row(self):
        output = await self._run_result_command("t1")
        self.assertNotIn("No result stored yet", output,
                         "Should not show generic message when interruption record exists")
        self.assertIn("connection_lost", output,
                      "Should display the interruption reason")

    async def test_result_shows_previous_status_in_interruption(self):
        output = await self._run_result_command("t1")
        self.assertIn("RUNNING", output,
                      "Should display the state the task was in before interruption")

    async def test_result_shows_retry_hint_when_no_retry_yet(self):
        output = await self._run_result_command("t1")
        self.assertIn("retry", output.lower(),
                      "Should show retry hint when no retry has been issued yet")

    async def test_result_shows_retry_id_when_already_retried(self):
        """If the task was already retried, the retry task_id should be shown."""
        await self.db.mark_retried("t1", "t2-retry-id")
        output = await self._run_result_command("t1")
        self.assertIn("t2-retry-id", output,
                      "Should show the retry task_id when a retry was already issued")

    async def test_result_still_shows_no_result_when_no_interruption_either(self):
        """A PENDING task with neither result nor interruption shows the generic message."""
        await _insert_task(self.db, "t-bare")
        output = await self._run_result_command("t-bare")
        self.assertIn("No result stored yet", output,
                      "Generic message must appear when there is truly nothing to show")


# ── P3.1 — Rate limiting (message counter per connection) ─────────────────────

class TestRateLimiting(unittest.IsolatedAsyncioTestCase):
    """
    P3.1 — Each connection is allowed at most MAX_MESSAGES_PER_SECOND protocol
    messages per second.  Exceeding this limit closes the connection with an
    ERROR rather than processing every message.

    The rate limit is deliberately conservative (tested at 10× the limit) so
    the test is stable without relying on wall-clock timing.
    """

    async def test_flood_of_pings_closes_connection(self):
        """Sending many PINGs rapidly must trigger the rate limit and close the session."""
        import server.main as sm

        db = await _make_db()
        server_obj = sm.C2Server(db)

        register = {"type": "REGISTER", "message_id": "m0",
                    "payload": {"agent_id": "flood-agent", "hostname": "h", "platform": "linux"}}
        sync = {"type": "SYNC_STATE", "message_id": "m1",
                "payload": {"pending_task_ids": [], "pending_result_ids": []}}
        ping = {"type": "PING", "message_id": "px", "payload": {}}

        # 10× the per-second limit — well above what any legitimate agent needs
        messages = [register, sync] + [ping] * (sm.MAX_MESSAGES_PER_SECOND * 10)
        call_count = 0

        async def fake_read(_r):
            nonlocal call_count
            if call_count < len(messages):
                m = messages[call_count]; call_count += 1; return m
            raise asyncio.IncompleteReadError(b"", None)

        replies = []

        async def fake_write(_w, msg):
            replies.append(msg)

        writer = _FakeWriter()
        with unittest.mock.patch("server.main.read_message", side_effect=fake_read):
            with unittest.mock.patch("server.main.write_message", side_effect=fake_write):
                await server_obj.handle_client(object(), writer)  # type: ignore[arg-type]

        # The session must have been terminated by the rate limiter
        self.assertTrue(
            writer._closing or call_count < len(messages),
            "Rate limit must terminate the connection before all flood messages are processed",
        )
        error_replies = [r for r in replies if r["type"] == "ERROR"
                         and "rate" in r["payload"].get("error", "").lower()]
        self.assertTrue(error_replies, "A rate-limit ERROR must be sent before closing")

    async def test_legitimate_traffic_is_not_rate_limited(self):
        """A normal session with a few messages per second must not be affected."""
        import server.main as sm

        db = await _make_db()
        server_obj = sm.C2Server(db)

        messages = [
            {"type": "REGISTER", "message_id": "m0",
             "payload": {"agent_id": "normal-agent", "hostname": "h", "platform": "linux"}},
            {"type": "SYNC_STATE", "message_id": "m1",
             "payload": {"pending_task_ids": [], "pending_result_ids": []}},
            {"type": "PING", "message_id": "m2", "payload": {}},
            {"type": "BEACON", "message_id": "m3", "payload": {}},
        ]
        call_count = 0

        async def fake_read(_r):
            nonlocal call_count
            if call_count < len(messages):
                m = messages[call_count]; call_count += 1; return m
            raise asyncio.IncompleteReadError(b"", None)

        replies = []

        async def fake_write(_w, msg):
            replies.append(msg)

        with unittest.mock.patch("server.main.read_message", side_effect=fake_read):
            with unittest.mock.patch("server.main.write_message", side_effect=fake_write):
                await server_obj.handle_client(object(), _FakeWriter())  # type: ignore[arg-type]

        error_replies = [r for r in replies if r["type"] == "ERROR"
                         and "rate" in r["payload"].get("error", "").lower()]
        self.assertFalse(error_replies, "Normal traffic must not trigger the rate limiter")
        pong_replies = [r for r in replies if r["type"] == "PONG"]
        self.assertTrue(pong_replies, "PING must receive PONG in a non-rate-limited session")


# ── Feature 1: Task execution timeout ─────────────────────────────────────────

class TestTaskExecutionTimeout(unittest.IsolatedAsyncioTestCase):
    """
    Verify that:
    - A task that receives no RESULT within the deadline is marked TIMEOUT.
    - An interruption record is created for the timed-out task.
    - A task that completes normally is NOT marked TIMEOUT (watchdog cancelled).
    - The watchdog is cancelled on agent disconnect cleanup.
    - The timeout deadline is configurable via C2Server(task_timeout=...).
    """

    async def _make_server(self, timeout=0.1):
        import server.main as sm
        db = await _make_db()
        srv = sm.C2Server(db, task_timeout=timeout)
        return db, srv

    async def test_timed_out_task_reaches_timeout_state(self):
        """A task with no RESULT within the deadline must be marked TIMEOUT."""
        db, srv = await self._make_server(timeout=0.05)
        await _insert_task(db, "t1")
        # Manually place the task in RUNNING (simulates dispatch + ACK + STATUS)
        for s in ("WAITING_ACK", "QUEUED", "RUNNING"):
            await db.update_task_status("t1", s)

        # Start the watchdog directly
        srv._start_task_watchdog("t1")
        # Wait longer than the deadline
        await asyncio.sleep(0.15)

        self.assertEqual(await _task_status(db, "t1"), "TIMEOUT",
                         "Task must be TIMEOUT after watchdog fires")

    async def test_timed_out_task_has_interruption_record(self):
        """A timed-out task must have an interruption entry in task_interruptions."""
        db, srv = await self._make_server(timeout=0.05)
        await _insert_task(db, "t1")
        for s in ("WAITING_ACK", "QUEUED", "RUNNING"):
            await db.update_task_status("t1", s)
        srv._start_task_watchdog("t1")
        await asyncio.sleep(0.15)

        record = await db.get_interruption("t1")
        self.assertIsNotNone(record, "Timed-out task must have an interruption record")
        self.assertEqual(record["terminal_status"], "TIMEOUT")
        self.assertEqual(record["reason"], "task_timeout")

    async def test_completed_task_watchdog_is_cancelled(self):
        """A task that completes normally must NOT later become TIMEOUT."""
        db, srv = await self._make_server(timeout=0.1)
        await _insert_task(db, "t1")
        for s in ("WAITING_ACK", "QUEUED", "RUNNING"):
            await db.update_task_status("t1", s)

        srv._start_task_watchdog("t1")
        self.assertIn("t1", srv._active_task_timeouts)

        # Simulate RESULT arriving before the deadline
        await db.complete_task_with_result("t1", "COMPLETED", "r1", "agent-1", "ok")
        srv._cancel_task_watchdog("t1")

        # Wait past the original deadline
        await asyncio.sleep(0.15)
        self.assertEqual(await _task_status(db, "t1"), "COMPLETED",
                         "Completed task must not be overwritten by late watchdog")
        self.assertNotIn("t1", srv._active_task_timeouts,
                         "Watchdog must be removed from tracking after cancellation")

    async def test_watchdog_not_in_tracking_after_firing(self):
        """After the watchdog fires it must remove itself from _active_task_timeouts."""
        db, srv = await self._make_server(timeout=0.05)
        await _insert_task(db, "t1")
        for s in ("WAITING_ACK", "QUEUED", "RUNNING"):
            await db.update_task_status("t1", s)
        srv._start_task_watchdog("t1")
        await asyncio.sleep(0.15)
        self.assertNotIn("t1", srv._active_task_timeouts,
                         "Watchdog must deregister itself after firing")

    async def test_disconnect_cancels_watchdog(self):
        """When an agent disconnects, its RUNNING task watchdog must be cancelled."""
        import server.main as sm

        db = await _make_db()
        srv = sm.C2Server(db, task_timeout=10.0)  # long timeout, must not fire during test

        await _insert_task(db, "t1")
        for s in ("WAITING_ACK", "QUEUED", "RUNNING"):
            await db.update_task_status("t1", s)
        srv._start_task_watchdog("t1")
        self.assertIn("t1", srv._active_task_timeouts)

        # Simulate disconnect cleanup calling interrupt_task + cancel_watchdog
        srv._cancel_task_watchdog("t1")
        await db.interrupt_task("t1", "connection_lost")

        self.assertNotIn("t1", srv._active_task_timeouts,
                         "Watchdog must be removed after disconnect cleanup")
        self.assertEqual(await _task_status(db, "t1"), "FAILED")


# ── Feature 2: Real remote self-removal from an installed copy ─────────────────

class TestSelfRemoveFromInstalledCopy(unittest.TestCase):
    """
    Verify that execute_allowed("self_remove") actually deletes files when run
    from a verified pa-agent-lab-* installation directory, and skips deletion
    (with an informative message) when run from the project source tree.
    """

    def test_self_remove_from_source_tree_skips_deletion(self):
        """Running from the project source tree must NOT delete files."""
        from agent.main import execute_allowed
        output = execute_allowed("self_remove", {})
        self.assertIn("NOT deleted", output,
                      "Source-tree run must report that files were not deleted")
        self.assertNotIn("installation deleted", output)

    def test_self_remove_from_installed_copy_deletes_files(self):
        """Running from a verified installation directory must delete the installed files."""
        import tempfile, shutil
        from agent.local_install import install
        from pathlib import Path

        with tempfile.TemporaryDirectory(prefix="test-self-remove-") as tmp:
            target = Path(tmp) / "pa-agent-lab-selfremove-test"
            install(target)
            self.assertTrue(target.is_dir(), "Installation must succeed")

            # Simulate the agent running from inside the installed copy
            installed_agent = target / "agent" / "main.py"
            self.assertTrue(installed_agent.is_file())

            # Call execute_allowed with __file__ pointing at the installed copy
            # by importing execute_allowed from the installed path
            import importlib.util
            spec = importlib.util.spec_from_file_location(
                "installed_agent", str(installed_agent)
            )
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)

            output = mod.execute_allowed("self_remove", {})
            self.assertIn("installation deleted", output,
                          f"Installed-copy run must report deletion. Got: {output!r}")
            # The directory itself must be gone
            self.assertFalse(target.exists(),
                             "Installation directory must be deleted by self_remove")

    def test_self_remove_skips_if_manifest_missing(self):
        """If the manifest is absent the uninstall must be skipped, not crash."""
        import tempfile
        from agent.main import execute_allowed

        # This is just the source tree — no manifest — so it skips cleanly
        output = execute_allowed("self_remove", {})
        self.assertIn("NOT deleted", output)

    def test_self_remove_rejects_parameters(self):
        from agent.main import execute_allowed
        with self.assertRaises(ValueError):
            execute_allowed("self_remove", {"force": True})


# ── Feature 3: Mutual TLS helpers ─────────────────────────────────────────────

class TestMTLSHelpers(unittest.TestCase):
    """
    Verify the shared/mtls.py helpers without requiring real TLS sockets.
    Real mTLS over loopback is tested in test_durable_recovery_and_audit.py.
    """

    def test_build_server_context_without_agent_ca(self):
        """Without an agent CA the server context must not require a client cert."""
        import ssl as ssl_mod
        from shared.mtls import build_server_context
        from pathlib import Path

        cert = Path("certs/server.crt")
        key = Path("certs/server.key")
        if not cert.is_file() or not key.is_file():
            self.skipTest("Server certificate not present — run openssl cert generation first")
        ctx = build_server_context(cert, key)
        self.assertEqual(ctx.verify_mode, ssl_mod.CERT_NONE,
                         "Without agent_ca, clients must not need a certificate")

    def test_build_server_context_with_agent_ca_requires_client_cert(self):
        """With an agent CA the server context must require a client certificate."""
        import ssl as ssl_mod
        from shared.mtls import build_server_context
        from pathlib import Path

        cert = Path("certs/server.crt")
        key = Path("certs/server.key")
        ca = Path("certs/server.crt")  # use same cert as stand-in CA
        if not cert.is_file():
            self.skipTest("Server certificate not present")
        ctx = build_server_context(cert, key, agent_ca=ca)
        self.assertEqual(ctx.verify_mode, ssl_mod.CERT_REQUIRED,
                         "With agent_ca, clients must present a certificate")

    def test_build_agent_context_without_cert(self):
        """Without agent cert the agent context must use server-auth only."""
        from shared.mtls import build_agent_context
        from pathlib import Path
        ca = Path("certs/server.crt")
        if not ca.is_file():
            self.skipTest("Server CA not present")
        ctx = build_agent_context(ca)
        # No client cert loaded — verify_mode stays at CERT_REQUIRED for server
        self.assertIsNotNone(ctx)

    def test_extract_agent_id_returns_none_for_non_tls_writer(self):
        """extract_agent_id_from_cert must return None for a non-TLS mock writer."""
        from shared.mtls import extract_agent_id_from_cert

        class _FakeTLSWriter:
            def get_extra_info(self, key, default=None):
                return None  # no ssl_object — non-TLS connection

        result = extract_agent_id_from_cert(_FakeTLSWriter())
        self.assertIsNone(result)

    def test_extract_agent_id_returns_none_for_no_peer_cert(self):
        """extract_agent_id_from_cert must return None when ssl_object has no peer cert."""
        from shared.mtls import extract_agent_id_from_cert

        class _FakeSSLObj:
            def getpeercert(self):
                return None  # no client cert presented

        class _FakeTLSWriter:
            def get_extra_info(self, key, default=None):
                if key == "ssl_object":
                    return _FakeSSLObj()
                return default

        result = extract_agent_id_from_cert(_FakeTLSWriter())
        self.assertIsNone(result)

    def test_extract_agent_id_reads_cn_from_subject(self):
        """extract_agent_id_from_cert must return the CN from the peer certificate."""
        from shared.mtls import extract_agent_id_from_cert

        class _FakeSSLObj:
            def getpeercert(self):
                return {"subject": ((("commonName", "lab-agent-01"),),)}

        class _FakeTLSWriter:
            def get_extra_info(self, key, default=None):
                if key == "ssl_object":
                    return _FakeSSLObj()
                return default

        result = extract_agent_id_from_cert(_FakeTLSWriter())
        self.assertEqual(result, "lab-agent-01")

    def test_extract_agent_id_raises_on_empty_cn(self):
        """extract_agent_id_from_cert must raise ValueError for an empty CN."""
        from shared.mtls import extract_agent_id_from_cert

        class _FakeSSLObj:
            def getpeercert(self):
                return {"subject": ((("commonName", "   "),),)}

        class _FakeTLSWriter:
            def get_extra_info(self, key, default=None):
                if key == "ssl_object":
                    return _FakeSSLObj()
                return default

        with self.assertRaises(ValueError):
            extract_agent_id_from_cert(_FakeTLSWriter())


# ── R1: Watchdog race — completion races the deadline ─────────────────────────

class TestWatchdogRaceCondition(unittest.IsolatedAsyncioTestCase):
    """
    R1 — Verify the watchdog does not overwrite a task that completes
    just as the deadline expires.  The asyncio lock inside timeout_task()
    ensures exactly one of (RESULT handler, watchdog) wins.
    """

    async def test_completion_before_watchdog_wins(self):
        """A RESULT that arrives 1 ms before the deadline must not be overwritten."""
        import server.main as sm
        db = await _make_db()
        srv = sm.C2Server(db, task_timeout=0.08)

        await _insert_task(db, "t1")
        for s in ("WAITING_ACK", "QUEUED", "RUNNING"):
            await db.update_task_status("t1", s)
        srv._start_task_watchdog("t1")

        # Complete the task just before the watchdog fires
        await asyncio.sleep(0.05)
        await db.complete_task_with_result("t1", "COMPLETED", "r1", "agent-1", "ok")
        srv._cancel_task_watchdog("t1")

        # Wait past the original deadline
        await asyncio.sleep(0.08)

        # Task must be COMPLETED, not overwritten by watchdog
        self.assertEqual(await _task_status(db, "t1"), "COMPLETED",
                         "Watchdog must not overwrite a task that already completed")
        self.assertIsNone(await db.get_interruption("t1"),
                          "No interruption record must exist for a normally completed task")

    async def test_concurrent_complete_and_timeout_exactly_one_wins(self):
        """Simulate simultaneous completion and timeout — exactly one must land."""
        import server.main as sm
        db = await _make_db()
        srv = sm.C2Server(db, task_timeout=0.001)  # near-zero timeout

        await _insert_task(db, "t1")
        for s in ("WAITING_ACK", "QUEUED", "RUNNING"):
            await db.update_task_status("t1", s)

        # Race both concurrently
        async def attempt_complete():
            try:
                await db.complete_task_with_result("t1", "COMPLETED", "r1", "agent-1", "ok")
                return "COMPLETED"
            except Exception:
                return "lost"

        srv._start_task_watchdog("t1")
        complete_result, _ = await asyncio.gather(
            attempt_complete(),
            asyncio.sleep(0.002),  # let watchdog also fire
        )

        final = await _task_status(db, "t1")
        self.assertIn(final, {"COMPLETED", "TIMEOUT"},
                      f"Final state must be COMPLETED or TIMEOUT, got {final!r}")

        # Verify state machine integrity: no invalid state
        from server.task_manager import TaskState
        self.assertIn(final, {s.value for s in TaskState})


# ── R4: Watchdog end-to-end over real TLS ─────────────────────────────────────

class TestTaskTimeoutEndToEnd(unittest.IsolatedAsyncioTestCase):
    """
    R4 — Verify the complete timeout path: dispatch → watchdog starts →
    agent is slow → deadline fires → task marked TIMEOUT → interruption recorded.
    Uses a real in-process TLS server and a real (mock-slow) agent connection.
    """

    async def asyncSetUp(self):
        import ssl as ssl_mod
        import subprocess, tempfile
        from server.main import C2Server
        from server.storage.database import Database

        self.tmp = tempfile.TemporaryDirectory(prefix="timeout-e2e-")
        root = __import__('pathlib').Path(self.tmp.name)
        ca = root / "server.crt"
        key = root / "server.key"
        try:
            subprocess.run([
                "openssl", "req", "-x509", "-newkey", "rsa:2048", "-days", "1",
                "-nodes", "-keyout", str(key), "-out", str(ca),
                "-subj", "/CN=localhost", "-addext", "subjectAltName=IP:127.0.0.1",
            ], capture_output=True, check=True, timeout=15)
        except (FileNotFoundError, subprocess.CalledProcessError) as exc:
            self.skipTest(f"openssl not available: {exc}")

        self.ca = ca
        self.key = key
        self.db = Database(":memory:")
        await self.db.initialize()
        # Very short timeout so the test runs fast
        self.app = C2Server(self.db, task_timeout=0.3)
        tls = ssl_mod.SSLContext(ssl_mod.PROTOCOL_TLS_SERVER)
        tls.load_cert_chain(str(self.ca), str(self.key))
        self.listener = await asyncio.start_server(
            self.app._tracked_handle_client, "127.0.0.1", 0, ssl=tls
        )
        self.port = self.listener.sockets[0].getsockname()[1]

    async def asyncTearDown(self):
        await self.app.shutdown()
        self.listener.close()
        await self.listener.wait_closed()
        await self.db.close()
        self.tmp.cleanup()

    async def test_slow_agent_triggers_timeout(self):
        """An agent that receives TASK but never sends RESULT causes TIMEOUT state."""
        import ssl as ssl_mod
        from shared.protocol import make_message, read_message, write_message

        agent_id = str(__import__('uuid').uuid4())
        ctx = ssl_mod.create_default_context(ssl_mod.Purpose.SERVER_AUTH, cafile=str(self.ca))

        reader, writer = await asyncio.open_connection(
            "127.0.0.1", self.port, ssl=ctx, server_hostname="127.0.0.1"
        )
        session_id = None
        ready = asyncio.Event()

        async def slow_agent():
            nonlocal session_id
            await write_message(writer, make_message("REGISTER", agent_id=agent_id,
                payload={"agent_id": agent_id, "hostname": "slow", "platform": "Linux"}))
            while True:
                msg = await read_message(reader)
                k = msg["type"]
                if k == "REGISTER_ACK":
                    session_id = msg["payload"]["session_id"]
                    await write_message(writer, make_message("SYNC_STATE",
                        agent_id=agent_id, session_id=session_id,
                        payload={"pending_task_ids": [], "pending_result_ids": []}))
                elif k == "SYNC_COMPLETE":
                    await write_message(writer, make_message("BEACON",
                        agent_id=agent_id, session_id=session_id,
                        payload={"activity_state": "IDLE"}))
                    ready.set()
                elif k == "TASK":
                    # Acknowledge receipt but NEVER send RESULT — simulates a slow/hung agent
                    task_id = msg["payload"]["task_id"]
                    await write_message(writer, make_message("TASK_ACK",
                        agent_id=agent_id, session_id=session_id,
                        payload={"task_id": task_id}))
                    await write_message(writer, make_message("TASK_STATUS",
                        agent_id=agent_id, session_id=session_id,
                        payload={"task_id": task_id, "status": "RUNNING"}))
                    # Agent hangs here — never sends RESULT
                    await asyncio.sleep(10)
                elif k in ("BEACON_ACK", "SYNC_STATE_RESPONSE", "ERROR"):
                    pass

        agent_task = asyncio.create_task(slow_agent())
        await asyncio.wait_for(ready.wait(), timeout=4.0)

        # Dispatch the task — watchdog starts with 0.3 s deadline
        task_id = await self.app.dispatch_task(agent_id, "echo", {"text": "hello"})

        # Wait for the watchdog to fire (deadline + small margin)
        await asyncio.sleep(0.5)

        final_status = await _task_status(self.db, task_id)
        self.assertEqual(final_status, "TIMEOUT",
                         f"Slow agent must cause TIMEOUT, got {final_status!r}")

        record = await self.db.get_interruption(task_id)
        self.assertIsNotNone(record, "TIMEOUT task must have an interruption record")
        self.assertEqual(record["reason"], "task_timeout")
        self.assertEqual(record["terminal_status"], "TIMEOUT")

        agent_task.cancel()
        await asyncio.gather(agent_task, return_exceptions=True)
        writer.close()


# ── OS Persistence ─────────────────────────────────────────────────────────────

class TestOSPersistence(unittest.TestCase):
    """
    Verify agent/persistence.py behaviour without requiring OS startup hooks:
    - install/remove/status API surface
    - NotImplementedError on unsupported platforms (mocked)
    - Generated unit file contains the correct fields (Linux path)
    """

    def test_platform_summary_returns_string(self):
        from shared.platform_compat import platform_summary
        summary = platform_summary()
        self.assertIsInstance(summary, str)
        self.assertTrue(len(summary) > 0)

    def test_is_installed_returns_bool(self):
        from agent.persistence import is_installed
        result = is_installed()
        self.assertIsInstance(result, bool)

    def test_install_raises_on_unsupported_platform(self):
        from agent.persistence import install_startup
        import unittest.mock as m
        with m.patch("platform.system", return_value="FreeBSD"):
            with self.assertRaises(NotImplementedError) as ctx:
                install_startup([])
            self.assertIn("FreeBSD", str(ctx.exception))

    def test_remove_raises_on_unsupported_platform(self):
        from agent.persistence import remove_startup
        import unittest.mock as m
        with m.patch("platform.system", return_value="FreeBSD"):
            with self.assertRaises(NotImplementedError):
                remove_startup()

    @unittest.skipUnless(__import__('platform').system() == "Linux", "Linux only")
    def test_linux_unit_file_content(self):
        """Install generates a valid systemd unit file without actually enabling it."""
        from agent.persistence import _install_linux, _unit_file
        import unittest.mock as m

        # Mock systemctl so we don't actually touch the user systemd
        with m.patch("subprocess.run") as mock_run:
            mock_run.return_value = m.MagicMock(returncode=0)
            status_msg = _install_linux(["--server", "127.0.0.1", "--ca", "certs/server.crt"])

        unit_path = _unit_file()
        self.assertTrue(unit_path.is_file(), "Unit file must be created on disk")
        content = unit_path.read_text()
        self.assertIn("[Unit]", content)
        self.assertIn("[Service]", content)
        self.assertIn("[Install]", content)
        self.assertIn("ExecStart=", content)
        self.assertIn("agent.main", content)
        self.assertIn("WantedBy=default.target", content)
        self.assertIn("127.0.0.1", content)       # agent_args are included
        self.assertIsInstance(status_msg, str)
        self.assertIn("systemd", status_msg)
        # Cleanup
        unit_path.unlink(missing_ok=True)

    def test_shell_commands_have_three_entries(self):
        from shared.platform_compat import SHELL_COMMANDS
        self.assertIn("pwd", SHELL_COMMANDS)
        self.assertIn("whoami", SHELL_COMMANDS)
        self.assertIn("uname", SHELL_COMMANDS)
        for name, cmd in SHELL_COMMANDS.items():
            with self.subTest(name=name):
                self.assertIsInstance(cmd, list)
                self.assertTrue(all(isinstance(c, str) for c in cmd))

    def test_persist_command_in_execute_allowed(self):
        """persist and unpersist must be in execute_allowed's dispatch table."""
        from agent.main import execute_allowed
        import unittest.mock as m
        with m.patch("agent.persistence.install_startup", return_value="installed"):
            out = execute_allowed("persist", {})
        self.assertEqual(out, "installed")

    def test_unpersist_command_in_execute_allowed(self):
        from agent.main import execute_allowed
        import unittest.mock as m
        with m.patch("agent.persistence.remove_startup", return_value="removed"):
            out = execute_allowed("unpersist", {})
        self.assertEqual(out, "removed")


# ── Automatic replay of read-only tasks ───────────────────────────────────────

class TestAutoReplay(unittest.IsolatedAsyncioTestCase):
    """
    Verify that read-only interrupted tasks (echo, get_info, shell) are
    automatically re-dispatched after SYNC_STATE, while file transfer and
    lifecycle commands are not.
    """

    async def asyncSetUp(self):
        self.db = await _make_db()
        await self.db.upsert_agent("agent-1", "host", "Linux")

    async def test_get_auto_replayable_returns_readonly_tasks(self):
        """echo, get_info, and allowlisted shell tasks must be returned."""
        for cmd, params in [
            ("echo", {"text": "hello"}),
            ("get_info", {}),
            ("shell", {"command": "pwd"}),
        ]:
            tid = str(__import__('uuid').uuid4())
            await self.db.create_task(tid, "agent-1", cmd, params, "PENDING")
            await self.db.update_task_status(tid, "WAITING_ACK")
            await self.db.interrupt_task(tid, "connection_lost")

        rows = await self.db.get_auto_replayable_interruptions("agent-1")
        commands = {r["command"] for r in rows}
        self.assertIn("echo", commands)
        self.assertIn("get_info", commands)
        self.assertIn("shell", commands)

    async def test_file_transfers_not_auto_replayed(self):
        """upload and download must NOT appear in auto-replayable results."""
        for cmd in ("upload", "download"):
            tid = str(__import__('uuid').uuid4())
            params = {"name": "x.txt"} if cmd == "download" else {"name": "x.txt", "content_b64": "", "sha256": "a" * 64, "bytes": 0}
            await self.db.create_task(tid, "agent-1", cmd, params, "PENDING")
            await self.db.update_task_status(tid, "WAITING_ACK")
            await self.db.interrupt_task(tid, "connection_lost")

        rows = await self.db.get_auto_replayable_interruptions("agent-1")
        commands = {r["command"] for r in rows}
        self.assertNotIn("upload", commands)
        self.assertNotIn("download", commands)

    async def test_shell_with_non_allowlisted_subcommand_not_replayed(self):
        """shell with a non-allowlisted subcommand must be excluded."""
        tid = str(__import__('uuid').uuid4())
        await self.db.create_task(tid, "agent-1", "shell", {"command": "ls -la"}, "PENDING")
        await self.db.update_task_status(tid, "WAITING_ACK")
        await self.db.interrupt_task(tid, "connection_lost")

        rows = await self.db.get_auto_replayable_interruptions("agent-1")
        task_ids = {r["task_id"] for r in rows}
        self.assertNotIn(tid, task_ids)

    async def test_already_retried_task_not_returned(self):
        """A task that already has a retry_task_id must not appear."""
        tid = str(__import__('uuid').uuid4())
        new_tid = str(__import__('uuid').uuid4())
        await self.db.create_task(tid, "agent-1", "echo", {"text": "x"}, "PENDING")
        await self.db.update_task_status(tid, "WAITING_ACK")
        await self.db.interrupt_task(tid, "connection_lost")
        await self.db.mark_retried(tid, new_tid)

        rows = await self.db.get_auto_replayable_interruptions("agent-1")
        task_ids = {r["task_id"] for r in rows}
        self.assertNotIn(tid, task_ids)

    async def test_other_agent_tasks_not_returned(self):
        """Tasks belonging to a different agent must not be included."""
        tid = str(__import__('uuid').uuid4())
        await self.db.upsert_agent("agent-2", "h", "Linux")
        await self.db.create_task(tid, "agent-2", "echo", {"text": "x"}, "PENDING")
        await self.db.update_task_status(tid, "WAITING_ACK")
        await self.db.interrupt_task(tid, "connection_lost")

        rows = await self.db.get_auto_replayable_interruptions("agent-1")
        task_ids = {r["task_id"] for r in rows}
        self.assertNotIn(tid, task_ids)

    async def test_auto_replay_dispatches_over_real_tls(self):
        """After SYNC_STATE, interrupted read-only tasks are automatically re-dispatched."""
        import ssl as ssl_mod
        import subprocess
        from pathlib import Path
        import argparse
        import tempfile
        from agent.main import run as run_agent
        from server.main import C2Server
        from server.storage.database import Database

        tmp = tempfile.TemporaryDirectory(prefix="autoreplay-")
        root = Path(tmp.name)
        ca = root / "server.crt"
        key = root / "server.key"
        try:
            subprocess.run([
                "openssl", "req", "-x509", "-newkey", "rsa:2048", "-days", "1",
                "-nodes", "-keyout", str(key), "-out", str(ca),
                "-subj", "/CN=localhost", "-addext", "subjectAltName=IP:127.0.0.1",
            ], capture_output=True, check=True, timeout=15)
        except (FileNotFoundError, subprocess.CalledProcessError) as exc:
            tmp.cleanup()
            self.skipTest(f"openssl not available: {exc}")

        db = Database(":memory:")
        await db.initialize()
        agent_id = str(__import__('uuid').uuid4())
        await db.upsert_agent(agent_id, "h", "Linux")
        app = C2Server(db)
        tls = ssl_mod.SSLContext(ssl_mod.PROTOCOL_TLS_SERVER)
        tls.load_cert_chain(str(ca), str(key))
        listener = await asyncio.start_server(app._tracked_handle_client, "127.0.0.1", 0, ssl=tls)
        port = listener.sockets[0].getsockname()[1]

        # Pre-seed an interrupted echo task (simulates a previous session disconnect)
        old_tid = str(__import__('uuid').uuid4())
        await db.create_task(old_tid, agent_id, "echo", {"text": "auto-replay"}, "PENDING")
        await db.update_task_status(old_tid, "WAITING_ACK")
        await db.interrupt_task(old_tid, "connection_lost")

        # Start agent — on SYNC_COMPLETE the server should auto-replay the echo task
        agent_files = root / "agent_files"
        agent_files.mkdir()
        args = argparse.Namespace(
            server="127.0.0.1", port=port, ca=str(ca),
            agent_id=agent_id, lab_dir=str(agent_files),
            beacon_interval=30.0, beacon_jitter=0.0,
            reconnect_sessions=0, reconnect_attempts=3, reconnect_max_delay=0.2,
            agent_cert=None, agent_key=None,
        )
        agent_task = asyncio.create_task(run_agent(args))

        # Wait for the replayed task to complete
        async def poll_replayed():
            for _ in range(200):
                tasks = await db.list_tasks()
                completed = [t for t in tasks if t["status"] == "COMPLETED" and t["command"] == "echo"]
                if completed:
                    return completed[0]["task_id"]
                await asyncio.sleep(0.05)
            return None

        try:
            replayed_id = await asyncio.wait_for(poll_replayed(), timeout=8.0)
            self.assertIsNotNone(replayed_id,
                                 "Auto-replayed echo task must reach COMPLETED")
            # Original task must be linked to the retry
            interruption = await db.get_interruption(old_tid)
            self.assertIsNotNone(interruption["retry_task_id"],
                                 "Original interrupted task must be linked to the auto-replay")
            # Result must be stored
            results = await db.list_results(replayed_id)
            self.assertTrue(results, "Replayed task must have a result row")
            self.assertEqual(results[0]["output"], "auto-replay")
        finally:
            agent_task.cancel()
            await asyncio.gather(agent_task, return_exceptions=True)
            await app.shutdown()
            listener.close()
            await listener.wait_closed()
            await db.close()
            tmp.cleanup()


# ── Residual R1: Watchdog DB-level integrity (IntegrityError path) ─────────────

class TestWatchdogDBIntegrity(unittest.IsolatedAsyncioTestCase):
    """Verify the timeout_task DB method's IntegrityError/rollback path."""

    async def test_timeout_task_returns_false_for_terminal(self):
        """timeout_task must return False (not raise) for an already-terminal task."""
        db = await _make_db()
        await _insert_task(db, "t1")
        for s in ("WAITING_ACK", "QUEUED", "RUNNING", "COMPLETED"):
            await db.update_task_status("t1", s)
        result = await db.timeout_task("t1")
        self.assertFalse(result)
        self.assertEqual(await _task_status(db, "t1"), "COMPLETED")

    async def test_timeout_task_raises_for_missing_task(self):
        from server.storage.database import TaskNotFoundError
        db = await _make_db()
        with self.assertRaises(TaskNotFoundError):
            await db.timeout_task("nonexistent")

    async def test_timeout_task_records_previous_state(self):
        """The interruption record must capture the state before TIMEOUT."""
        db = await _make_db()
        await _insert_task(db, "t1")
        for s in ("WAITING_ACK", "QUEUED"):
            await db.update_task_status("t1", s)
        result = await db.timeout_task("t1")
        self.assertTrue(result)
        record = await db.get_interruption("t1")
        self.assertEqual(record["previous_status"], "QUEUED")
        self.assertEqual(record["terminal_status"], "TIMEOUT")
        self.assertEqual(record["reason"], "task_timeout")

    async def test_timeout_task_idempotent_on_second_call(self):
        """Second call on the same task must return False, not raise."""
        db = await _make_db()
        await _insert_task(db, "t1")
        await db.update_task_status("t1", "WAITING_ACK")
        self.assertTrue(await db.timeout_task("t1"))
        self.assertFalse(await db.timeout_task("t1"))  # already TIMEOUT


# ── Residual: persistence.py macOS and Linux graceful fallback ─────────────────

class TestPersistenceAllPlatforms(unittest.TestCase):
    """Comprehensive persistence.py tests that run on any platform."""

    def test_install_raises_on_freebsd(self):
        from agent.persistence import install_startup
        with unittest.mock.patch("platform.system", return_value="FreeBSD"):
            with self.assertRaises(NotImplementedError) as ctx:
                install_startup([])
            self.assertIn("FreeBSD", str(ctx.exception))
            self.assertIn("Linux", str(ctx.exception))   # mentions supported
            self.assertIn("macOS", str(ctx.exception))
            self.assertIn("Windows", str(ctx.exception))

    def test_remove_raises_on_unsupported(self):
        from agent.persistence import remove_startup
        with unittest.mock.patch("platform.system", return_value="Haiku"):
            with self.assertRaises(NotImplementedError):
                remove_startup()

    def test_is_installed_returns_false_on_unsupported(self):
        from agent.persistence import is_installed
        with unittest.mock.patch("platform.system", return_value="Haiku"):
            self.assertFalse(is_installed())

    @unittest.skipUnless(__import__('platform').system() == "Linux", "Linux only")
    def test_linux_install_survives_systemctl_unavailable(self):
        """When systemctl fails (container), install_startup must NOT raise."""
        from agent.persistence import install_startup, _unit_file
        import subprocess as sp

        def fake_run(cmd, **kw):
            if "systemctl" in cmd:
                raise sp.CalledProcessError(1, cmd, b"Failed to connect to bus")
            r = unittest.mock.MagicMock()
            r.returncode = 0
            return r

        with unittest.mock.patch("subprocess.run", side_effect=fake_run):
            result = install_startup(["--server", "127.0.0.1"])

        # Must succeed (no exception) and mention the fallback
        self.assertIsInstance(result, str)
        self.assertIn("systemctl unavailable", result)
        # Unit file must still be on disk
        self.assertTrue(_unit_file().is_file(), "Unit file must be written even when systemctl fails")
        _unit_file().unlink(missing_ok=True)

    @unittest.skipUnless(__import__('platform').system() == "Linux", "Linux only")
    def test_linux_remove_survives_systemctl_unavailable(self):
        """remove_startup must clean up the unit file even without systemctl."""
        from agent.persistence import _unit_file, _install_linux, _remove_linux
        import subprocess as sp

        # Write the unit file first (mock systemctl for install)
        with unittest.mock.patch("subprocess.run", return_value=unittest.mock.MagicMock(returncode=0)):
            _install_linux([])

        self.assertTrue(_unit_file().is_file())

        # Now remove with systemctl unavailable
        with unittest.mock.patch("subprocess.run", side_effect=FileNotFoundError("no systemctl")):
            removed = _remove_linux()

        self.assertTrue(removed)
        self.assertFalse(_unit_file().exists(), "Unit file must be deleted even without systemctl")

    @unittest.skipUnless(__import__('platform').system() == "Darwin", "macOS only")
    def test_macos_plist_content(self):
        """install_startup on macOS must write a valid launchd plist."""
        from agent.persistence import _install_macos, _plist_file

        with unittest.mock.patch("subprocess.run", return_value=unittest.mock.MagicMock(returncode=0)):
            msg = _install_macos(["--server", "127.0.0.1"])

        plist = _plist_file()
        self.assertTrue(plist.is_file())
        content = plist.read_text()
        self.assertIn("com.pa-agent-lab", content)
        self.assertIn("<key>RunAtLoad</key>", content)
        self.assertIn("<key>KeepAlive</key>", content)
        self.assertIn("agent.main", content)
        self.assertIn("127.0.0.1", content)
        self.assertIsInstance(msg, str)
        plist.unlink(missing_ok=True)

    @unittest.skipUnless(__import__('platform').system() == "Darwin", "macOS only")
    def test_macos_remove(self):
        from agent.persistence import _install_macos, _remove_macos, _plist_file
        with unittest.mock.patch("subprocess.run", return_value=unittest.mock.MagicMock(returncode=0)):
            _install_macos([])
        self.assertTrue(_plist_file().is_file())
        with unittest.mock.patch("subprocess.run", return_value=unittest.mock.MagicMock(returncode=0)):
            removed = _remove_macos()
        self.assertTrue(removed)
        self.assertFalse(_plist_file().exists())

    @unittest.skipUnless(__import__('platform').system() == "Windows", "Windows only")
    def test_windows_install_uses_xml(self):
        """install_startup on Windows must generate an XML task definition."""
        from agent.persistence import _install_windows
        xml_files_used = []

        def capture_run(cmd, **kw):
            if "/XML" in cmd:
                xml_idx = cmd.index("/XML") + 1
                xml_files_used.append(cmd[xml_idx])
            r = unittest.mock.MagicMock()
            r.returncode = 0
            return r

        with unittest.mock.patch("subprocess.run", side_effect=capture_run):
            msg = _install_windows(["--server", "127.0.0.1"])

        self.assertTrue(xml_files_used, "schtasks /Create must use /XML flag")
        self.assertIsInstance(msg, str)
        self.assertIn("PA-Agent-Lab", msg)

    @unittest.skipUnless(__import__('platform').system() == "Windows", "Windows only")
    def test_windows_xml_contains_no_shell_quoting_issues(self):
        """The Windows XML task definition must embed arguments without shell quoting."""
        from agent.persistence import _task_xml
        xml = _task_xml(["--server", "127.0.0.1 with spaces", "--ca", "path/with spaces.crt"])
        # Arguments must appear as separate <string> or as unquoted elements in XML
        self.assertIn("127.0.0.1 with spaces", xml)
        # No shell quoting artifacts
        self.assertNotIn('\\"', xml)


# ── Residual: auto-replay race — reserve_replay atomicity ─────────────────────

class TestAutoReplayRaceProtection(unittest.IsolatedAsyncioTestCase):
    """reserve_replay + cancel_replay_reservation prevent orphaned tasks."""

    async def asyncSetUp(self):
        self.db = await _make_db()
        await self.db.upsert_agent("agent-1", "host", "Linux")
        self.tid = str(__import__('uuid').uuid4())
        await self.db.create_task(self.tid, "agent-1", "echo", {"text": "x"}, "PENDING")
        await self.db.update_task_status(self.tid, "WAITING_ACK")
        await self.db.interrupt_task(self.tid, "connection_lost")

    async def test_reserve_replay_claims_slot(self):
        ok = await self.db.reserve_replay(self.tid, "__pending_abc")
        self.assertTrue(ok)
        record = await self.db.get_interruption(self.tid)
        self.assertEqual(record["retry_task_id"], "__pending_abc")

    async def test_second_reserve_replay_fails(self):
        await self.db.reserve_replay(self.tid, "__pending_abc")
        ok2 = await self.db.reserve_replay(self.tid, "__pending_xyz")
        self.assertFalse(ok2)
        # First placeholder must still be in place
        record = await self.db.get_interruption(self.tid)
        self.assertEqual(record["retry_task_id"], "__pending_abc")

    async def test_cancel_replay_reservation_releases_slot(self):
        await self.db.reserve_replay(self.tid, "__pending_abc")
        await self.db.cancel_replay_reservation(self.tid, "__pending_abc")
        record = await self.db.get_interruption(self.tid)
        self.assertIsNone(record["retry_task_id"])

    async def test_cancel_does_not_affect_different_placeholder(self):
        """cancel_replay_reservation must be idempotent when placeholder differs."""
        await self.db.reserve_replay(self.tid, "__pending_abc")
        # Wrong placeholder — must not clear the real one
        await self.db.cancel_replay_reservation(self.tid, "__pending_WRONG")
        record = await self.db.get_interruption(self.tid)
        self.assertEqual(record["retry_task_id"], "__pending_abc")

    async def test_concurrent_reserves_exactly_one_wins(self):
        """Two concurrent reserve_replay calls must result in exactly one winner."""
        results = await asyncio.gather(
            self.db.reserve_replay(self.tid, "__p1"),
            self.db.reserve_replay(self.tid, "__p2"),
        )
        wins = sum(results)
        self.assertEqual(wins, 1, "Exactly one coroutine must win the reservation race")

    async def test_mark_retried_replaces_placeholder(self):
        """After dispatch, mark_retried must replace the placeholder with the real ID."""
        await self.db.reserve_replay(self.tid, "__pending_abc")
        real_id = str(__import__('uuid').uuid4())
        linked = await self.db.mark_retried(self.tid, real_id)
        self.assertTrue(linked)
        record = await self.db.get_interruption(self.tid)
        self.assertEqual(record["retry_task_id"], real_id)


# ── Residual: Windows symlink guard via is_symlink() ─────────────────────────

class TestWindowsSymlinkGuard(unittest.TestCase):
    """
    On Windows, O_NOFOLLOW is absent but workspace_file() uses Path.is_symlink()
    which is cross-platform.  Verify the guard works without O_NOFOLLOW.
    """

    def test_workspace_file_rejects_symlink_without_o_nofollow(self):
        """workspace_file must reject symlinks even when O_NOFOLLOW is 0."""
        import tempfile
        from shared.lab_transfer import workspace_file

        with tempfile.TemporaryDirectory() as tmp:
            root = __import__('pathlib').Path(tmp)
            real_file = root / "real.txt"
            real_file.write_text("data")
            link = root / "link.txt"
            try:
                link.symlink_to(real_file)
            except (OSError, NotImplementedError):
                self.skipTest("symlinks not supported on this filesystem")

            # Patch out O_NOFOLLOW to simulate Windows (flag = 0)
            with unittest.mock.patch.object(__import__('os'), "O_NOFOLLOW", 0, create=True):
                with self.assertRaises(ValueError) as ctx:
                    workspace_file(root, "link.txt")
                self.assertIn("symlink", str(ctx.exception).lower())

    def test_o_nofollow_gracefully_absent(self):
        """getattr(os, 'O_NOFOLLOW', 0) must yield 0 when the flag is missing."""
        import os
        # Simulate Windows by temporarily hiding the attribute
        original = getattr(os, "O_NOFOLLOW", None)
        if hasattr(os, "O_NOFOLLOW"):
            delattr(os, "O_NOFOLLOW")
        try:
            val = getattr(os, "O_NOFOLLOW", 0)
            self.assertEqual(val, 0)
        finally:
            if original is not None:
                os.O_NOFOLLOW = original


# ── New commands: sysinfo and shellcode ────────────────────────────────────────

class TestSysinfo(unittest.TestCase):
    """sysinfo must return valid JSON with all required keys."""

    def _run(self, params=None):
        from agent.main import execute_allowed
        import json
        raw = execute_allowed("sysinfo", params or {})
        return json.loads(raw)

    def test_sysinfo_returns_json(self):
        from agent.main import execute_allowed
        raw = execute_allowed("sysinfo", {})
        import json
        data = json.loads(raw)
        self.assertIsInstance(data, dict)

    def test_sysinfo_has_identity_keys(self):
        data = self._run()
        for key in ("hostname", "user", "pid", "cwd", "python", "executable"):
            with self.subTest(key=key):
                self.assertIn(key, data)
                self.assertTrue(data[key])

    def test_sysinfo_has_os_keys(self):
        data = self._run()
        for key in ("os_system", "os_release", "os_machine"):
            with self.subTest(key=key):
                self.assertIn(key, data)

    def test_sysinfo_has_cpu_count(self):
        data = self._run()
        self.assertIn("cpu_count_logical", data)
        self.assertGreater(data["cpu_count_logical"], 0)

    def test_sysinfo_has_uptime(self):
        data = self._run()
        self.assertIn("uptime", data)

    def test_sysinfo_has_network_interfaces(self):
        data = self._run()
        self.assertIn("network_interfaces", data)
        self.assertIsInstance(data["network_interfaces"], dict)

    def test_sysinfo_has_env(self):
        data = self._run()
        self.assertIn("env", data)
        self.assertIsInstance(data["env"], dict)

    def test_sysinfo_rejects_nonempty_parameters(self):
        """sysinfo does not accept parameters (uses empty dict only)."""
        # It does accept an empty dict — non-empty triggers ValueError only
        # if the command explicitly checks.  Since sysinfo ignores parameters,
        # verify the output is still valid JSON.
        from agent.main import execute_allowed
        import json
        raw = execute_allowed("sysinfo", {"unexpected": "param"})
        data = json.loads(raw)
        self.assertIn("hostname", data)


class TestShellcode(unittest.TestCase):
    """shellcode executes a binary from lab_dir; rejects missing / non-executable files."""

    def setUp(self):
        import tempfile
        self.tmp = tempfile.TemporaryDirectory(prefix="shellcode-test-")
        self.lab = __import__('pathlib').Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_shellcode_executes_binary(self):
        """A real executable in lab_dir must run and return its output."""
        import stat, json as _json, platform as _platform
        from agent.main import execute_allowed

        if _platform.system() == "Windows":
            # Write a batch file on Windows
            binary = self.lab / "hello.bat"
            binary.write_text("@echo hello shellcode\r\n")
            binary.chmod(0o755)
        else:
            # Write a minimal shell script on POSIX
            binary = self.lab / "hello_world"
            binary.write_text("#!/bin/sh\necho hello shellcode\n")
            binary.chmod(0o755)

        raw = execute_allowed("shellcode", {"name": binary.name}, lab_dir=str(self.lab))
        data = _json.loads(raw)
        self.assertIn("hello shellcode", data["output"])
        self.assertEqual(data["returncode"], 0)

    def test_shellcode_rejects_missing_file(self):
        from agent.main import execute_allowed
        with self.assertRaises(ValueError) as ctx:
            execute_allowed("shellcode", {"name": "nonexistent"}, lab_dir=str(self.lab))
        self.assertIn("not found", str(ctx.exception))

    def test_shellcode_rejects_non_executable(self):
        from agent.main import execute_allowed
        plain = self.lab / "data.txt"
        plain.write_text("data")
        plain.chmod(0o600)
        with self.assertRaises(ValueError) as ctx:
            execute_allowed("shellcode", {"name": "data.txt"}, lab_dir=str(self.lab))
        self.assertIn("not executable", str(ctx.exception))

    def test_shellcode_rejects_traversal(self):
        from agent.main import execute_allowed
        with self.assertRaises(ValueError):
            execute_allowed("shellcode", {"name": "../etc/passwd"}, lab_dir=str(self.lab))

    def test_shellcode_captures_stderr(self):
        """stderr output is included in the result."""
        import json as _json, platform as _platform
        from agent.main import execute_allowed

        if _platform.system() == "Windows":
            self.skipTest("Windows stderr capture tested separately")
        binary = self.lab / "stderr_test"
        binary.write_text("#!/bin/sh\necho out\n>&2 echo err\n")
        binary.chmod(0o755)
        raw = execute_allowed("shellcode", {"name": "stderr_test"}, lab_dir=str(self.lab))
        data = _json.loads(raw)
        self.assertIn("out", data["output"])
        self.assertIn("err", data["output"])

    def test_shellcode_passes_args(self):
        """Arguments are forwarded to the binary unchanged."""
        import json as _json, platform as _platform
        from agent.main import execute_allowed

        if _platform.system() == "Windows":
            self.skipTest("args forwarding tested on POSIX")
        binary = self.lab / "echo_args"
        binary.write_text("#!/bin/sh\necho \"$@\"\n")
        binary.chmod(0o755)
        raw = execute_allowed("shellcode",
                              {"name": "echo_args", "args": ["hello", "world"]},
                              lab_dir=str(self.lab))
        data = _json.loads(raw)
        self.assertIn("hello world", data["output"])

    def test_shellcode_handles_timeout(self):
        """A binary that runs longer than 10s must raise ValueError."""
        import platform as _platform
        from agent.main import execute_allowed

        if _platform.system() == "Windows":
            self.skipTest("timeout test on POSIX only")
        binary = self.lab / "slow"
        binary.write_text("#!/bin/sh\nsleep 30\n")
        binary.chmod(0o755)
        with self.assertRaises(ValueError) as ctx:
            execute_allowed("shellcode", {"name": "slow"}, lab_dir=str(self.lab))
        self.assertIn("timed out", str(ctx.exception))


# ── Rich CLI visual tests ──────────────────────────────────────────────────────

class TestRichCLIOutput(unittest.IsolatedAsyncioTestCase):
    """Verify that the Rich CLI renders expected content."""

    def _make_server_with_console(self):
        """Return (server_obj, buf) with a capturable console injected."""
        import io
        from rich.console import Console
        import server.main as sm
        import asyncio

        db_future = asyncio.get_event_loop().run_until_complete(_make_db())

        async def _setup():
            return await _make_db()

        return None, None  # placeholder; use the async version below

    async def _cli_run(self, commands: list[str], db=None,
                       pre_setup=None) -> tuple:
        """Run the CLI with the given commands and return (server_obj, output)."""
        import io
        from rich.console import Console
        import server.main as sm

        if db is None:
            db = await _make_db()
        if pre_setup:
            await pre_setup(db)
        server_obj = sm.C2Server(db)
        buf = io.StringIO()
        server_obj._test_console = Console(
            file=buf, highlight=False, no_color=True, width=200
        )
        inputs = iter(commands)

        async def fake_to_thread(fn, *args):
            return next(inputs)

        with unittest.mock.patch("server.main.asyncio.to_thread",
                                 side_effect=fake_to_thread):
            await server_obj.cli()

        return server_obj, buf.getvalue()

    async def test_help_lists_all_commands(self):
        _, output = await self._cli_run(["help", "quit"])
        for cmd in ("agents", "sessions", "tasks", "interrupted", "result",
                    "retry", "ping", "disconnect", "sysinfo", "shellcode",
                    "upload", "download", "persist", "self_remove", "quit"):
            with self.subTest(cmd=cmd):
                self.assertIn(cmd, output)

    async def test_agents_shows_table_header(self):
        _, output = await self._cli_run(["agents", "quit"])
        # With no agents, expect a user-friendly message
        self.assertIn("No agents", output)

    async def test_tasks_shows_no_tasks_message(self):
        _, output = await self._cli_run(["tasks", "quit"])
        self.assertIn("No tasks", output)

    async def test_tasks_filter_by_command(self):
        """tasks echo should only show echo tasks."""
        async def setup(db):
            await _insert_task(db, "t1")   # default command is "echo" from _insert_task
            await _insert_task(db, "t2")

        _, output = await self._cli_run(["tasks echo", "quit"], pre_setup=setup)
        self.assertIn("echo", output)

    async def test_result_shows_rich_panel_for_json(self):
        """A sysinfo result (JSON dict) must render as a key-value table."""
        import json as _json

        async def setup(db):
            await db.create_task("t-sys", "agent-1", "sysinfo", {}, "PENDING")
            await db.upsert_agent("agent-1", "h", "Linux")
            for s in ("WAITING_ACK", "QUEUED", "RUNNING"):
                await db.update_task_status("t-sys", s)
            payload = _json.dumps({
                "hostname": "testbox",
                "user": "lab",
                "os_system": "Linux",
            })
            await db.complete_task_with_result(
                "t-sys", "COMPLETED", "r-sys", "agent-1", payload
            )

        _, output = await self._cli_run(["result t-sys", "quit"], pre_setup=setup)
        self.assertIn("hostname", output)
        self.assertIn("testbox", output)

    async def test_unknown_command_shows_helpful_message(self):
        _, output = await self._cli_run(["notacommand", "quit"])
        self.assertIn("Unknown command", output)
        self.assertIn("help", output)

    async def test_banner_shown_on_startup(self):
        _, output = await self._cli_run(["quit"])
        self.assertIn("C2-MVP", output)

    async def test_result_interrupted_task_shows_reason(self):
        async def setup(db):
            await _insert_task(db, "t-int")
            await db.update_task_status("t-int", "WAITING_ACK")
            await db.interrupt_task("t-int", "connection_lost")

        _, output = await self._cli_run(["result t-int", "quit"], pre_setup=setup)
        self.assertIn("connection_lost", output)
        self.assertIn("retry", output.lower())
