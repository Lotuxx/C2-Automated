"""
server/task_manager.py — Authoritative task state machine for the lab C2 MVP.

Role in the architecture
------------------------
This module defines the complete lifecycle of a task from the moment the
operator dispatches it from the CLI to the moment a terminal outcome is
persisted.  It is the single source of truth for:

  * Every valid task state (TaskState enum).
  * Which states are considered final / irreversible (TERMINAL_STATES).
  * Which state-to-state transitions are permitted (ALLOWED_TRANSITIONS).
  * The validation function that enforces those rules (validate_transition).

Both the database layer (server/storage/database.py) and the message handlers
(server/main.py) import from this module.  Neither layer duplicates any
transition logic; they delegate all enforcement here.

Task lifecycle overview
-----------------------
                        +----------+
                        |  PENDING |  ← task created, not yet sent to agent
                        +----+-----+
                             |
                    write TASK to agent stream
                             |
                        +----v--------+
                        | WAITING_ACK |  ← server waiting for TASK_ACK
                        +----+--------+
                             |
                      agent sends TASK_ACK
                             |
                        +----v----+
                        |  QUEUED |  ← agent has it, about to execute
                        +----+----+
                             |
                    agent sends TASK_STATUS RUNNING
                             |
                        +----v-----+
                        | RUNNING  |  ← execution in progress
                        +----+-----+
                    /         |       \\
             (success)   (exception)  (server-side)
                /             |              \\
        +----------+    +--------+      +-----------+   +-----------+
        |COMPLETED |    | FAILED |      |  TIMEOUT  |   | CANCELLED |
        +----------+    +--------+      +-----------+   +-----------+

TIMEOUT and CANCELLED are reachable from every non-terminal state; they
represent server-initiated outcomes (timeout watchdog or operator cancel).
They are defined in the state machine but the timeout watchdog is not yet
implemented in this MVP — the transitions are reserved for future use.
"""

from enum import Enum


# ── State definitions ─────────────────────────────────────────────────────────

class TaskState(str, Enum):
    """All possible states of a task throughout its lifecycle.

    Inheriting from ``str`` allows TaskState members to be used directly as
    string values in SQLite queries and JSON payloads without explicit
    ``.value`` access, while still benefiting from enum type safety.

    States:
        PENDING      Task record created in the database; TASK message not
                     yet written to the agent's TCP stream.
        WAITING_ACK  TASK message written to the stream; server is waiting
                     for the agent's TASK_ACK reply.
        QUEUED       Agent confirmed receipt (TASK_ACK); task is queued
                     locally on the agent awaiting execution resources.
        RUNNING      Agent sent TASK_STATUS RUNNING; execution is active.
        COMPLETED    Agent delivered a RESULT with status COMPLETED.
                     Terminal — no further transitions permitted.
        FAILED       Agent delivered a RESULT with status FAILED, or the
                     server marked the task failed after agent disconnect.
                     Terminal — no further transitions permitted.
        TIMEOUT      Server-initiated timeout (NOT YET IMPLEMENTED — no coroutine
                     currently transitions any task into this state).
                     Terminal — reserved for a future watchdog coroutine.
                     Upgrade path: wrap dispatch_task with asyncio.wait_for and
                     call update_task_status(task_id, "TIMEOUT") on TimeoutError.
        CANCELLED    Operator-initiated cancel, or server reconciliation
                     after an agent reconnects with unknown prior tasks.
                     Terminal — no further transitions permitted.
    """
    PENDING     = "PENDING"
    WAITING_ACK = "WAITING_ACK"
    QUEUED      = "QUEUED"
    RUNNING     = "RUNNING"
    COMPLETED   = "COMPLETED"
    FAILED      = "FAILED"
    TIMEOUT     = "TIMEOUT"
    CANCELLED   = "CANCELLED"


# ── Terminal state set ────────────────────────────────────────────────────────

# States in this set have an empty successor set in ALLOWED_TRANSITIONS.
# Once a task reaches any of these states it can never be updated again.
# This set is used by the database layer and by save_result() to guard
# against duplicate messages overwriting a final outcome.
TERMINAL_STATES: set[TaskState] = {
    TaskState.COMPLETED,
    TaskState.FAILED,
    TaskState.TIMEOUT,
    TaskState.CANCELLED,
}


# ── Transition table ──────────────────────────────────────────────────────────

# The complete, exhaustive list of permitted state transitions.
# Every TaskState must appear as a key so that validate_transition() can
# detect missing states rather than silently KeyError-ing.
#
# Reading the table: ALLOWED_TRANSITIONS[X] is the set of states that X
# may transition INTO.  An empty set means X is terminal.
ALLOWED_TRANSITIONS: dict[TaskState, set[TaskState]] = {
    TaskState.PENDING: {
        TaskState.WAITING_ACK,  # normal path: TASK sent to agent
        TaskState.TIMEOUT,      # RESERVED — watchdog not yet implemented (no coroutine fires this)
        TaskState.CANCELLED,    # operator cancelled before send
    },
    TaskState.WAITING_ACK: {
        TaskState.QUEUED,       # normal path: agent sent TASK_ACK
        TaskState.TIMEOUT,      # RESERVED — watchdog not yet implemented
        TaskState.CANCELLED,    # operator cancelled while waiting
    },
    TaskState.QUEUED: {
        TaskState.RUNNING,      # normal path: agent sent TASK_STATUS RUNNING
        TaskState.TIMEOUT,      # RESERVED — watchdog not yet implemented
        TaskState.CANCELLED,    # operator cancelled while queued
    },
    TaskState.RUNNING: {
        TaskState.COMPLETED,    # normal path: agent sent RESULT COMPLETED
        TaskState.FAILED,       # agent sent RESULT FAILED, or agent disconnected
        TaskState.TIMEOUT,      # RESERVED — watchdog not yet implemented
        TaskState.CANCELLED,    # operator cancelled mid-execution
    },
    # Terminal states: empty sets enforce the "no exit from terminal" rule.
    TaskState.COMPLETED: set(),
    TaskState.FAILED:    set(),
    TaskState.TIMEOUT:   set(),
    TaskState.CANCELLED: set(),
}


# ── Exception ─────────────────────────────────────────────────────────────────

class InvalidTaskTransition(ValueError):
    """Raised when a requested state transition is not permitted.

    Inherits from ValueError so callers that only need to distinguish
    "expected lifecycle error" from "unexpected runtime error" can use a
    single ``except ValueError`` clause.  Server handlers catch this type
    explicitly to log a warning and continue without killing the session.
    """


# ── Validation function ───────────────────────────────────────────────────────

def validate_transition(current: str, target: str) -> None:
    """Assert that moving a task from ``current`` to ``target`` is permitted.

    This is a pure function with no side effects: it reads the transition
    table and either returns None (transition allowed) or raises an exception
    (transition forbidden).  It is intentionally stateless so it can be called
    from synchronous and asynchronous contexts alike.

    Parameters
    ----------
    current : str
        The task's present state as a raw string (e.g. ``"RUNNING"``).
        Must be a member of TaskState; unknown strings raise InvalidTaskTransition.
    target : str
        The desired next state as a raw string (e.g. ``"COMPLETED"``).
        Must be a member of TaskState; unknown strings raise InvalidTaskTransition.

    Returns
    -------
    None
        Returned implicitly when the transition is allowed.

    Raises
    ------
    InvalidTaskTransition
        * ``current`` or ``target`` is not a valid TaskState member.
        * ``target`` is not in the permitted successor set for ``current``
          (including self-transitions, backward transitions, and any attempt
          to leave a terminal state).

    Examples
    --------
    >>> validate_transition("RUNNING", "COMPLETED")   # OK — returns None
    >>> validate_transition("COMPLETED", "RUNNING")   # raises InvalidTaskTransition
    >>> validate_transition("ghost", "RUNNING")       # raises InvalidTaskTransition
    """
    # Convert raw strings to enum members.  TaskState(value) raises ValueError
    # for any string that is not a declared member; we re-raise as our domain
    # exception so callers only need to handle one exception type.
    try:
        current_state = TaskState(current)
        target_state  = TaskState(target)
    except ValueError as exc:
        raise InvalidTaskTransition(f"Unknown task state: {exc}") from exc

    # Check the transition table.  Terminal states have empty sets so any
    # outbound transition from a terminal state is caught here, including
    # self-transitions (COMPLETED → COMPLETED).
    if target_state not in ALLOWED_TRANSITIONS[current_state]:
        raise InvalidTaskTransition(
            f"Transition not allowed: {current_state.value} -> {target_state.value}"
        )
