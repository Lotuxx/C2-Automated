"""
Integration tests: task-state validation wired into SQLite persistence.

Every test that touches the database uses an isolated in-memory SQLite instance
so tests are fully independent and leave no files on disk.

Coverage:
  1. Valid persisted transitions
  2. Rejected invalid transitions
  3. Unknown states and missing task IDs
  4. Terminal-state protection
  5. Duplicate and late status updates
  6. Concurrent attempts to update the same task
  7. Rollback / unchanged state after a rejected update
  8. Dispatch and acknowledgement flow (PENDING→WAITING_ACK→QUEUED)
  9. Regression: existing behaviour unchanged where valid
"""
import asyncio
import unittest

from server.storage.database import Database, TaskNotFoundError
from server.task_manager import InvalidTaskTransition, TaskState


# ── helpers ────────────────────────────────────────────────────────────────────

async def _make_db() -> Database:
    """Return an initialised in-memory database."""
    db = Database(":memory:")
    await db.initialize()
    return db


async def _insert_task(db: Database, task_id: str, status: str = "PENDING") -> None:
    await db.create_task(task_id, "agent-1", "echo", {"text": "hi"}, status)


async def _current_status(db: Database, task_id: str) -> str:
    async with db.lock:
        row = db.conn.execute(
            "SELECT status FROM tasks WHERE task_id=?", (task_id,)
        ).fetchone()
    return row["status"] if row else None


# ── 1. Valid persisted transitions ─────────────────────────────────────────────

class TestValidPersistedTransitions(unittest.IsolatedAsyncioTestCase):

    async def asyncSetUp(self):
        self.db = await _make_db()

    async def test_pending_to_waiting_ack(self):
        await _insert_task(self.db, "t1", "PENDING")
        await self.db.update_task_status("t1", "WAITING_ACK")
        self.assertEqual(await _current_status(self.db, "t1"), "WAITING_ACK")

    async def test_waiting_ack_to_queued(self):
        await _insert_task(self.db, "t1", "PENDING")
        await self.db.update_task_status("t1", "WAITING_ACK")
        await self.db.update_task_status("t1", "QUEUED")
        self.assertEqual(await _current_status(self.db, "t1"), "QUEUED")

    async def test_queued_to_running(self):
        await _insert_task(self.db, "t1", "PENDING")
        await self.db.update_task_status("t1", "WAITING_ACK")
        await self.db.update_task_status("t1", "QUEUED")
        await self.db.update_task_status("t1", "RUNNING")
        self.assertEqual(await _current_status(self.db, "t1"), "RUNNING")

    async def test_full_happy_path_to_completed(self):
        await _insert_task(self.db, "t1", "PENDING")
        for state in ("WAITING_ACK", "QUEUED", "RUNNING", "COMPLETED"):
            await self.db.update_task_status("t1", state)
        self.assertEqual(await _current_status(self.db, "t1"), "COMPLETED")

    async def test_full_happy_path_to_failed(self):
        await _insert_task(self.db, "t1", "PENDING")
        for state in ("WAITING_ACK", "QUEUED", "RUNNING", "FAILED"):
            await self.db.update_task_status("t1", state)
        self.assertEqual(await _current_status(self.db, "t1"), "FAILED")

    async def test_timeout_from_pending(self):
        await _insert_task(self.db, "t1", "PENDING")
        await self.db.update_task_status("t1", "TIMEOUT")
        self.assertEqual(await _current_status(self.db, "t1"), "TIMEOUT")

    async def test_cancel_from_queued(self):
        await _insert_task(self.db, "t1", "PENDING")
        await self.db.update_task_status("t1", "WAITING_ACK")
        await self.db.update_task_status("t1", "QUEUED")
        await self.db.update_task_status("t1", "CANCELLED")
        self.assertEqual(await _current_status(self.db, "t1"), "CANCELLED")


# ── 2. Rejected invalid transitions ───────────────────────────────────────────

class TestRejectedInvalidTransitions(unittest.IsolatedAsyncioTestCase):

    async def asyncSetUp(self):
        self.db = await _make_db()

    async def test_pending_to_running_rejected(self):
        await _insert_task(self.db, "t1", "PENDING")
        with self.assertRaises(InvalidTaskTransition):
            await self.db.update_task_status("t1", "RUNNING")

    async def test_pending_to_completed_rejected(self):
        await _insert_task(self.db, "t1", "PENDING")
        with self.assertRaises(InvalidTaskTransition):
            await self.db.update_task_status("t1", "COMPLETED")

    async def test_waiting_ack_to_running_rejected(self):
        await _insert_task(self.db, "t1", "PENDING")
        await self.db.update_task_status("t1", "WAITING_ACK")
        with self.assertRaises(InvalidTaskTransition):
            await self.db.update_task_status("t1", "RUNNING")

    async def test_queued_to_completed_rejected(self):
        await _insert_task(self.db, "t1", "PENDING")
        await self.db.update_task_status("t1", "WAITING_ACK")
        await self.db.update_task_status("t1", "QUEUED")
        with self.assertRaises(InvalidTaskTransition):
            await self.db.update_task_status("t1", "COMPLETED")

    async def test_backward_transition_rejected(self):
        await _insert_task(self.db, "t1", "PENDING")
        await self.db.update_task_status("t1", "WAITING_ACK")
        with self.assertRaises(InvalidTaskTransition):
            await self.db.update_task_status("t1", "PENDING")


# ── 3. Unknown states and missing task IDs ────────────────────────────────────

class TestUnknownStatesAndMissingTasks(unittest.IsolatedAsyncioTestCase):

    async def asyncSetUp(self):
        self.db = await _make_db()

    async def test_missing_task_raises_task_not_found(self):
        with self.assertRaises(TaskNotFoundError):
            await self.db.update_task_status("no-such-id", "RUNNING")

    async def test_unknown_target_state_raises_invalid_transition(self):
        await _insert_task(self.db, "t1", "PENDING")
        with self.assertRaises(InvalidTaskTransition):
            await self.db.update_task_status("t1", "SENT")

    async def test_acknowledged_not_a_valid_state(self):
        await _insert_task(self.db, "t1", "PENDING")
        with self.assertRaises(InvalidTaskTransition):
            await self.db.update_task_status("t1", "ACKNOWLEDGED")

    async def test_empty_string_target_rejected(self):
        await _insert_task(self.db, "t1", "PENDING")
        with self.assertRaises(InvalidTaskTransition):
            await self.db.update_task_status("t1", "")

    async def test_lowercase_target_rejected(self):
        await _insert_task(self.db, "t1", "PENDING")
        with self.assertRaises(InvalidTaskTransition):
            await self.db.update_task_status("t1", "waiting_ack")

    async def test_create_task_with_unknown_status_rejected(self):
        with self.assertRaises(InvalidTaskTransition):
            await self.db.create_task("t1", "agent-1", "echo", {}, "SENT")

    async def test_task_not_found_is_key_error_subclass(self):
        with self.assertRaises(KeyError):
            await self.db.update_task_status("ghost", "RUNNING")


# ── 4. Terminal-state protection ──────────────────────────────────────────────

class TestTerminalStateProtection(unittest.IsolatedAsyncioTestCase):

    async def asyncSetUp(self):
        self.db = await _make_db()

    async def _reach_terminal(self, task_id: str, terminal: str):
        await _insert_task(self.db, task_id, "PENDING")
        # Drive to RUNNING first for COMPLETED/FAILED, else go direct
        if terminal in ("COMPLETED", "FAILED"):
            for s in ("WAITING_ACK", "QUEUED", "RUNNING"):
                await self.db.update_task_status(task_id, s)
        await self.db.update_task_status(task_id, terminal)

    async def test_no_transition_from_completed(self):
        await self._reach_terminal("t1", "COMPLETED")
        for target in [s.value for s in TaskState]:
            with self.subTest(target=target):
                with self.assertRaises(InvalidTaskTransition):
                    await self.db.update_task_status("t1", target)

    async def test_no_transition_from_failed(self):
        await self._reach_terminal("t1", "FAILED")
        with self.assertRaises(InvalidTaskTransition):
            await self.db.update_task_status("t1", "RUNNING")

    async def test_no_transition_from_timeout(self):
        await _insert_task(self.db, "t1", "PENDING")
        await self.db.update_task_status("t1", "TIMEOUT")
        with self.assertRaises(InvalidTaskTransition):
            await self.db.update_task_status("t1", "RUNNING")

    async def test_no_transition_from_cancelled(self):
        await _insert_task(self.db, "t1", "PENDING")
        await self.db.update_task_status("t1", "CANCELLED")
        with self.assertRaises(InvalidTaskTransition):
            await self.db.update_task_status("t1", "RUNNING")


# ── 5. Duplicate and late status updates ──────────────────────────────────────

class TestDuplicateAndLateUpdates(unittest.IsolatedAsyncioTestCase):

    async def asyncSetUp(self):
        self.db = await _make_db()

    async def test_duplicate_completed_rejected(self):
        await _insert_task(self.db, "t1", "PENDING")
        for s in ("WAITING_ACK", "QUEUED", "RUNNING", "COMPLETED"):
            await self.db.update_task_status("t1", s)
        with self.assertRaises(InvalidTaskTransition):
            await self.db.update_task_status("t1", "COMPLETED")

    async def test_late_running_after_completed_rejected(self):
        await _insert_task(self.db, "t1", "PENDING")
        for s in ("WAITING_ACK", "QUEUED", "RUNNING", "COMPLETED"):
            await self.db.update_task_status("t1", s)
        with self.assertRaises(InvalidTaskTransition):
            await self.db.update_task_status("t1", "RUNNING")

    async def test_late_failed_after_completed_rejected(self):
        await _insert_task(self.db, "t1", "PENDING")
        for s in ("WAITING_ACK", "QUEUED", "RUNNING", "COMPLETED"):
            await self.db.update_task_status("t1", s)
        with self.assertRaises(InvalidTaskTransition):
            await self.db.update_task_status("t1", "FAILED")


# ── 6. Concurrent attempts to update the same task ────────────────────────────

class TestConcurrentUpdates(unittest.IsolatedAsyncioTestCase):
    """
    Genuinely exercises competing coroutines on the same task.
    The asyncio.Lock in Database serialises them, so exactly one
    transition wins and the other is rejected as invalid.
    The test does not prescribe which wins — it checks that exactly
    one succeeds and the other raises InvalidTaskTransition.
    """

    async def asyncSetUp(self):
        self.db = await _make_db()

    async def test_two_concurrent_transitions_from_pending(self):
        await _insert_task(self.db, "t1", "PENDING")

        results = []

        async def attempt(target):
            try:
                await self.db.update_task_status("t1", target)
                results.append(("ok", target))
            except InvalidTaskTransition as exc:
                results.append(("err", target, str(exc)))

        # Both coroutines race from PENDING; only one valid target per attempt.
        # WAITING_ACK is the only valid next state from PENDING.
        # The second caller will see a non-PENDING current state and be rejected.
        await asyncio.gather(
            attempt("WAITING_ACK"),
            attempt("WAITING_ACK"),
        )

        ok = [r for r in results if r[0] == "ok"]
        err = [r for r in results if r[0] == "err"]
        self.assertEqual(len(ok), 1, "Exactly one update should succeed")
        self.assertEqual(len(err), 1, "Exactly one update should be rejected")

    async def test_two_concurrent_different_valid_targets_sequential_both_can_land(self):
        """
        The asyncio lock serialises concurrent coroutines into a strict sequence.
        When two coroutines race with *different* valid targets from PENDING
        (e.g. WAITING_ACK and TIMEOUT), the first to acquire the lock succeeds;
        the second then reads the state the first left behind.  If that new state
        also permits the second target the second transition will also succeed —
        producing a sequential chain that is individually valid at each step but
        may not be the intended lifecycle outcome.

        This test asserts the *actual* guarantee provided by the lock: the final
        state is a known TaskState and was reached by a sequence of individually
        valid transitions.  It does NOT assert that only one transition succeeds,
        because the lock does not provide that guarantee when both targets are
        valid from the starting state.

        The known limitation is: PENDING→WAITING_ACK followed immediately by
        WAITING_ACK→TIMEOUT is a valid chain, so both coroutines can succeed.
        Preventing this would require caller-level coordination (e.g. a compare-
        and-swap that pins the expected prior state), which is outside the scope
        of the database layer.
        """
        await _insert_task(self.db, "t1", "PENDING")

        outcomes = []

        async def attempt(target):
            try:
                await self.db.update_task_status("t1", target)
                outcomes.append(("ok", target))
            except InvalidTaskTransition:
                outcomes.append(("err", target))

        await asyncio.gather(
            attempt("WAITING_ACK"),
            attempt("TIMEOUT"),
        )

        # At least one must succeed (the first to acquire the lock always can).
        ok = [r for r in outcomes if r[0] == "ok"]
        self.assertGreaterEqual(len(ok), 1, "At least one transition must succeed")

        # Final state must be a known TaskState — no corruption, no unknown strings.
        final = await _current_status(self.db, "t1")
        self.assertIn(final, {s.value for s in TaskState},
                      f"Final state {final!r} is not a valid TaskState")

    async def test_three_concurrent_same_target_exactly_one_wins(self):
        """
        Three coroutines all attempt the same transition (PENDING → WAITING_ACK).
        The first to acquire the lock succeeds; the other two see WAITING_ACK as
        the current state and their WAITING_ACK target is invalid from there,
        so they are rejected.  This exercises the genuine TOCTOU protection the
        lock provides for identical competing updates.
        """
        await _insert_task(self.db, "t1", "PENDING")

        results = []

        async def attempt():
            try:
                await self.db.update_task_status("t1", "WAITING_ACK")
                results.append("ok")
            except (InvalidTaskTransition, TaskNotFoundError):
                results.append("err")

        await asyncio.gather(attempt(), attempt(), attempt())

        self.assertEqual(results.count("ok"), 1)
        self.assertEqual(results.count("err"), 2)
        self.assertEqual(await _current_status(self.db, "t1"), "WAITING_ACK")


# ── 7. Rollback / unchanged state after rejected update ───────────────────────

class TestStateUnchangedAfterRejection(unittest.IsolatedAsyncioTestCase):

    async def asyncSetUp(self):
        self.db = await _make_db()

    async def test_state_unchanged_after_invalid_transition(self):
        await _insert_task(self.db, "t1", "PENDING")
        with self.assertRaises(InvalidTaskTransition):
            await self.db.update_task_status("t1", "COMPLETED")
        # DB must still hold PENDING
        self.assertEqual(await _current_status(self.db, "t1"), "PENDING")

    async def test_state_unchanged_after_terminal_protection(self):
        await _insert_task(self.db, "t1", "PENDING")
        for s in ("WAITING_ACK", "QUEUED", "RUNNING", "COMPLETED"):
            await self.db.update_task_status("t1", s)
        with self.assertRaises(InvalidTaskTransition):
            await self.db.update_task_status("t1", "RUNNING")
        self.assertEqual(await _current_status(self.db, "t1"), "COMPLETED")

    async def test_state_unchanged_after_unknown_target(self):
        await _insert_task(self.db, "t1", "PENDING")
        with self.assertRaises(InvalidTaskTransition):
            await self.db.update_task_status("t1", "SENT")
        self.assertEqual(await _current_status(self.db, "t1"), "PENDING")


# ── 8. Dispatch and acknowledgement flow ──────────────────────────────────────

class TestDispatchAndAcknowledgementFlow(unittest.IsolatedAsyncioTestCase):
    """
    Verify the corrected status strings used in server/main.py:
      PENDING → WAITING_ACK   (after dispatch_task writes the TASK message)
      WAITING_ACK → QUEUED    (after TASK_ACK is received from the agent)
      QUEUED → RUNNING        (agent sends TASK_STATUS running)
      RUNNING → COMPLETED     (agent sends RESULT completed)
    """

    async def asyncSetUp(self):
        self.db = await _make_db()

    async def test_dispatch_flow_uses_waiting_ack(self):
        """Simulates dispatch_task: PENDING then WAITING_ACK."""
        await _insert_task(self.db, "t1", "PENDING")
        await self.db.update_task_status("t1", "WAITING_ACK")
        self.assertEqual(await _current_status(self.db, "t1"), "WAITING_ACK")

    async def test_task_ack_flow_uses_queued(self):
        """Simulates TASK_ACK handler: WAITING_ACK then QUEUED."""
        await _insert_task(self.db, "t1", "PENDING")
        await self.db.update_task_status("t1", "WAITING_ACK")
        await self.db.update_task_status("t1", "QUEUED")
        self.assertEqual(await _current_status(self.db, "t1"), "QUEUED")

    async def test_sent_string_is_rejected(self):
        """'SENT' must no longer be accepted by update_task_status."""
        await _insert_task(self.db, "t1", "PENDING")
        with self.assertRaises(InvalidTaskTransition):
            await self.db.update_task_status("t1", "SENT")

    async def test_acknowledged_string_is_rejected(self):
        """'ACKNOWLEDGED' must no longer be accepted by update_task_status."""
        await _insert_task(self.db, "t1", "PENDING")
        with self.assertRaises(InvalidTaskTransition):
            await self.db.update_task_status("t1", "ACKNOWLEDGED")

    async def test_full_dispatch_to_result_flow(self):
        await _insert_task(self.db, "t1", "PENDING")
        await self.db.update_task_status("t1", "WAITING_ACK")   # dispatch_task
        await self.db.update_task_status("t1", "QUEUED")         # TASK_ACK received
        await self.db.update_task_status("t1", "RUNNING")        # TASK_STATUS running
        await self.db.update_task_status("t1", "COMPLETED")      # RESULT completed
        self.assertEqual(await _current_status(self.db, "t1"), "COMPLETED")


# ── 9. save_result validation ────────────────────────────────────────────────

class TestSaveResultValidation(unittest.IsolatedAsyncioTestCase):
    """
    save_result must only accept terminal TaskState values and must not
    silently overwrite an existing result row (duplicate RESULT protection).
    """

    async def asyncSetUp(self):
        self.db = await _make_db()
        await _insert_task(self.db, "t1", "PENDING")
        for s in ("WAITING_ACK", "QUEUED", "RUNNING"):
            await self.db.update_task_status("t1", s)

    async def test_save_result_accepts_completed(self):
        await self.db.update_task_status("t1", "COMPLETED")
        await self.db.save_result("r1", "t1", "agent-1", "COMPLETED", "ok")
        async with self.db.lock:
            row = self.db.conn.execute(
                "SELECT status FROM results WHERE result_id='r1'"
            ).fetchone()
        self.assertEqual(row["status"], "COMPLETED")

    async def test_save_result_accepts_failed(self):
        await self.db.update_task_status("t1", "FAILED")
        await self.db.save_result("r1", "t1", "agent-1", "FAILED", "err")
        async with self.db.lock:
            row = self.db.conn.execute(
                "SELECT status FROM results WHERE result_id='r1'"
            ).fetchone()
        self.assertEqual(row["status"], "FAILED")

    async def test_save_result_rejects_non_terminal_running(self):
        with self.assertRaises(InvalidTaskTransition):
            await self.db.save_result("r1", "t1", "agent-1", "RUNNING", "")

    async def test_save_result_rejects_non_terminal_pending(self):
        with self.assertRaises(InvalidTaskTransition):
            await self.db.save_result("r1", "t1", "agent-1", "PENDING", "")

    async def test_save_result_rejects_unknown_status_string(self):
        with self.assertRaises(InvalidTaskTransition):
            await self.db.save_result("r1", "t1", "agent-1", "SENT", "")

    async def test_save_result_rejects_empty_status(self):
        with self.assertRaises(InvalidTaskTransition):
            await self.db.save_result("r1", "t1", "agent-1", "", "")

    async def test_duplicate_result_id_does_not_overwrite(self):
        """INSERT OR IGNORE: a second save with the same result_id keeps the first row."""
        await self.db.update_task_status("t1", "COMPLETED")
        await self.db.save_result("r1", "t1", "agent-1", "COMPLETED", "first output")
        # Simulate duplicate RESULT message with different output
        await self.db.save_result("r1", "t1", "agent-1", "COMPLETED", "duplicate output")
        async with self.db.lock:
            row = self.db.conn.execute(
                "SELECT output FROM results WHERE result_id='r1'"
            ).fetchone()
        self.assertEqual(row["output"], "first output",
                         "Duplicate result_id must not overwrite the original row")

    async def test_different_result_ids_both_stored(self):
        """Two RESULT messages with distinct IDs for the same task are both stored."""
        await self.db.update_task_status("t1", "COMPLETED")
        await self.db.save_result("r1", "t1", "agent-1", "COMPLETED", "output-1")
        # Note: the task is already COMPLETED so a second update_task_status would
        # be rejected; this test exercises save_result in isolation.
        await self.db.save_result("r2", "t1", "agent-1", "COMPLETED", "output-2")
        async with self.db.lock:
            rows = self.db.conn.execute(
                "SELECT result_id FROM results WHERE task_id='t1' ORDER BY result_id"
            ).fetchall()
        self.assertEqual([r["result_id"] for r in rows], ["r1", "r2"])


# ── 10. RESULT handler ordering: transition before persistence ─────────────────

class TestResultHandlerOrdering(unittest.IsolatedAsyncioTestCase):
    """
    Verify the invariant enforced by the corrected server/main.py RESULT handler:
    update_task_status is called before save_result, so a rejected transition
    (e.g. duplicate RESULT on a terminal task) prevents the result row from
    being written or overwritten.
    """

    async def asyncSetUp(self):
        self.db = await _make_db()
        await _insert_task(self.db, "t1", "PENDING")
        for s in ("WAITING_ACK", "QUEUED", "RUNNING", "COMPLETED"):
            await self.db.update_task_status("t1", s)
        # Store the original result row
        await self.db.save_result("r-orig", "t1", "agent-1", "COMPLETED", "original output")

    async def test_duplicate_result_on_terminal_task_leaves_task_unchanged(self):
        """
        Simulates the RESULT handler receiving a duplicate message after the
        task is already COMPLETED.  update_task_status raises; save_result is
        never called; the task status remains COMPLETED.
        """
        with self.assertRaises(InvalidTaskTransition):
            await self.db.update_task_status("t1", "COMPLETED")  # transition rejected
        # save_result is not called (caller responsibility after the raise)
        self.assertEqual(await _current_status(self.db, "t1"), "COMPLETED")

    async def test_duplicate_result_id_does_not_overwrite_original_row(self):
        """
        Even if save_result is called again with the same result_id, INSERT OR
        IGNORE ensures the original row survives.
        """
        # This would only be reached if update_task_status somehow succeeded,
        # but we call save_result directly here to verify the DB-level guard.
        await self.db.save_result("r-orig", "t1", "agent-1", "COMPLETED", "overwrite attempt")
        async with self.db.lock:
            row = self.db.conn.execute(
                "SELECT output FROM results WHERE result_id='r-orig'"
            ).fetchone()
        self.assertEqual(row["output"], "original output")

    async def test_non_terminal_result_status_rejected_before_any_persistence(self):
        """
        A RESULT message carrying a non-terminal status (malformed agent message)
        is rejected by save_result's own guard before touching the DB.
        """
        with self.assertRaises(InvalidTaskTransition):
            await self.db.save_result("r-bad", "t1", "agent-1", "RUNNING", "bad")
        async with self.db.lock:
            row = self.db.conn.execute(
                "SELECT result_id FROM results WHERE result_id='r-bad'"
            ).fetchone()
        self.assertIsNone(row, "No result row should have been written")


if __name__ == "__main__":
    unittest.main()
