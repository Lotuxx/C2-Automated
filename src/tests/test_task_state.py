"""
Unit tests for the task-state-transition validator.

Covers:
  - Every valid transition in ALLOWED_TRANSITIONS
  - Invalid (non-existent) transitions between known states
  - Terminal-state protection (no outbound transition allowed)
  - Unknown / misspelled state names
  - Duplicate / late updates into a terminal state
  - Case-sensitivity and type robustness
"""
import unittest
from server.task_manager import (
    TaskState,
    ALLOWED_TRANSITIONS,
    TERMINAL_STATES,
    InvalidTaskTransition,
    validate_transition,
)


class TestValidTransitions(unittest.TestCase):
    """validate_transition must NOT raise for every edge listed in ALLOWED_TRANSITIONS."""

    def _assert_valid(self, current: str, target: str):
        # Should complete without raising
        validate_transition(current, target)

    # PENDING → {WAITING_ACK, TIMEOUT, CANCELLED}
    def test_pending_to_waiting_ack(self):
        self._assert_valid("PENDING", "WAITING_ACK")

    def test_pending_to_timeout(self):
        self._assert_valid("PENDING", "TIMEOUT")

    def test_pending_to_cancelled(self):
        self._assert_valid("PENDING", "CANCELLED")

    # WAITING_ACK → {QUEUED, TIMEOUT, CANCELLED}
    def test_waiting_ack_to_queued(self):
        self._assert_valid("WAITING_ACK", "QUEUED")

    def test_waiting_ack_to_timeout(self):
        self._assert_valid("WAITING_ACK", "TIMEOUT")

    def test_waiting_ack_to_cancelled(self):
        self._assert_valid("WAITING_ACK", "CANCELLED")

    # QUEUED → {RUNNING, TIMEOUT, CANCELLED}
    def test_queued_to_running(self):
        self._assert_valid("QUEUED", "RUNNING")

    def test_queued_to_timeout(self):
        self._assert_valid("QUEUED", "TIMEOUT")

    def test_queued_to_cancelled(self):
        self._assert_valid("QUEUED", "CANCELLED")

    # RUNNING → {COMPLETED, FAILED, TIMEOUT, CANCELLED}
    def test_running_to_completed(self):
        self._assert_valid("RUNNING", "COMPLETED")

    def test_running_to_failed(self):
        self._assert_valid("RUNNING", "FAILED")

    def test_running_to_timeout(self):
        self._assert_valid("RUNNING", "TIMEOUT")

    def test_running_to_cancelled(self):
        self._assert_valid("RUNNING", "CANCELLED")

    def test_all_listed_transitions_are_accepted(self):
        """Cross-check: every edge in ALLOWED_TRANSITIONS must be accepted."""
        for current_state, targets in ALLOWED_TRANSITIONS.items():
            for target_state in targets:
                with self.subTest(current=current_state.value, target=target_state.value):
                    validate_transition(current_state.value, target_state.value)


class TestInvalidTransitions(unittest.TestCase):
    """validate_transition must raise InvalidTaskTransition for disallowed edges."""

    def _assert_invalid(self, current: str, target: str):
        with self.assertRaises(InvalidTaskTransition):
            validate_transition(current, target)

    # Forward-skipping (skips a mandatory step)
    def test_pending_to_running(self):
        self._assert_invalid("PENDING", "RUNNING")

    def test_pending_to_completed(self):
        self._assert_invalid("PENDING", "COMPLETED")

    def test_pending_to_failed(self):
        self._assert_invalid("PENDING", "FAILED")

    def test_pending_to_queued(self):
        self._assert_invalid("PENDING", "QUEUED")

    def test_waiting_ack_to_running(self):
        self._assert_invalid("WAITING_ACK", "RUNNING")

    def test_waiting_ack_to_completed(self):
        self._assert_invalid("WAITING_ACK", "COMPLETED")

    def test_queued_to_completed(self):
        self._assert_invalid("QUEUED", "COMPLETED")

    def test_queued_to_failed(self):
        self._assert_invalid("QUEUED", "FAILED")

    # Backward transitions
    def test_running_to_pending(self):
        self._assert_invalid("RUNNING", "PENDING")

    def test_running_to_waiting_ack(self):
        self._assert_invalid("RUNNING", "WAITING_ACK")

    def test_queued_to_pending(self):
        self._assert_invalid("QUEUED", "PENDING")

    def test_queued_to_waiting_ack(self):
        self._assert_invalid("QUEUED", "WAITING_ACK")

    # Self-transitions
    def test_self_transition_pending(self):
        self._assert_invalid("PENDING", "PENDING")

    def test_self_transition_running(self):
        self._assert_invalid("RUNNING", "RUNNING")


class TestTerminalStateProtection(unittest.TestCase):
    """No transition out of a terminal state is permitted."""

    TERMINAL_NAMES = ["COMPLETED", "FAILED", "TIMEOUT", "CANCELLED"]
    ALL_STATES = [s.value for s in TaskState]

    def test_terminal_states_set_is_correct(self):
        expected = {"COMPLETED", "FAILED", "TIMEOUT", "CANCELLED"}
        actual = {s.value for s in TERMINAL_STATES}
        self.assertEqual(actual, expected)

    def test_terminal_states_have_empty_transition_sets(self):
        for state in TERMINAL_STATES:
            with self.subTest(state=state.value):
                self.assertEqual(
                    ALLOWED_TRANSITIONS[state],
                    set(),
                    msg=f"{state.value} must have no outbound transitions",
                )

    def test_no_transition_from_completed(self):
        for target in self.ALL_STATES:
            with self.subTest(target=target):
                with self.assertRaises(InvalidTaskTransition):
                    validate_transition("COMPLETED", target)

    def test_no_transition_from_failed(self):
        for target in self.ALL_STATES:
            with self.subTest(target=target):
                with self.assertRaises(InvalidTaskTransition):
                    validate_transition("FAILED", target)

    def test_no_transition_from_timeout(self):
        for target in self.ALL_STATES:
            with self.subTest(target=target):
                with self.assertRaises(InvalidTaskTransition):
                    validate_transition("TIMEOUT", target)

    def test_no_transition_from_cancelled(self):
        for target in self.ALL_STATES:
            with self.subTest(target=target):
                with self.assertRaises(InvalidTaskTransition):
                    validate_transition("CANCELLED", target)


class TestUnknownStateNames(unittest.TestCase):
    """Unrecognised state strings must raise InvalidTaskTransition."""

    def test_unknown_current_state(self):
        with self.assertRaises(InvalidTaskTransition):
            validate_transition("ACKNOWLEDGED", "RUNNING")

    def test_unknown_target_state(self):
        with self.assertRaises(InvalidTaskTransition):
            validate_transition("PENDING", "SENT")

    def test_empty_string_current(self):
        with self.assertRaises(InvalidTaskTransition):
            validate_transition("", "RUNNING")

    def test_empty_string_target(self):
        with self.assertRaises(InvalidTaskTransition):
            validate_transition("PENDING", "")

    def test_misspelled_state(self):
        with self.assertRaises(InvalidTaskTransition):
            validate_transition("PENDINGG", "RUNNING")

    def test_lowercase_state_rejected(self):
        # The enum is uppercase-only; lowercase must be rejected
        with self.assertRaises(InvalidTaskTransition):
            validate_transition("pending", "running")

    def test_numeric_string_rejected(self):
        with self.assertRaises(InvalidTaskTransition):
            validate_transition("1", "2")

    def test_none_type_rejected(self):
        with self.assertRaises((InvalidTaskTransition, AttributeError, TypeError)):
            validate_transition(None, "RUNNING")  # type: ignore[arg-type]


class TestDuplicateAndLateUpdates(unittest.TestCase):
    """
    Simulate the scenario where the server receives a duplicate status update
    for a task that is already terminal.  The validator must reject it so that
    the database layer never overwrites the terminal state.
    """

    def test_late_completed_update_rejected(self):
        """Task already COMPLETED; a duplicate COMPLETED update must be rejected."""
        with self.assertRaises(InvalidTaskTransition):
            validate_transition("COMPLETED", "COMPLETED")

    def test_late_failed_update_rejected(self):
        with self.assertRaises(InvalidTaskTransition):
            validate_transition("FAILED", "FAILED")

    def test_late_running_after_completed(self):
        """Out-of-order RUNNING message after COMPLETED must be rejected."""
        with self.assertRaises(InvalidTaskTransition):
            validate_transition("COMPLETED", "RUNNING")

    def test_late_running_after_failed(self):
        with self.assertRaises(InvalidTaskTransition):
            validate_transition("FAILED", "RUNNING")

    def test_late_running_after_timeout(self):
        with self.assertRaises(InvalidTaskTransition):
            validate_transition("TIMEOUT", "RUNNING")

    def test_late_running_after_cancelled(self):
        with self.assertRaises(InvalidTaskTransition):
            validate_transition("CANCELLED", "RUNNING")


class TestExceptionDetails(unittest.TestCase):
    """The exception message must be informative."""

    def test_invalid_transition_message_contains_states(self):
        try:
            validate_transition("PENDING", "COMPLETED")
        except InvalidTaskTransition as exc:
            self.assertIn("PENDING", str(exc))
            self.assertIn("COMPLETED", str(exc))
        else:
            self.fail("InvalidTaskTransition not raised")

    def test_unknown_state_message_is_set(self):
        try:
            validate_transition("GHOST_STATE", "RUNNING")
        except InvalidTaskTransition as exc:
            self.assertTrue(len(str(exc)) > 0)
        else:
            self.fail("InvalidTaskTransition not raised")

    def test_invalid_transition_is_value_error_subclass(self):
        """InvalidTaskTransition must be a ValueError subclass (documented contract)."""
        with self.assertRaises(ValueError):
            validate_transition("PENDING", "COMPLETED")


if __name__ == "__main__":
    unittest.main()
