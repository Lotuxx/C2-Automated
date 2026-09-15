# Authoritative Task State Model

> **Status:** FROZEN  
> **Authority:** This document defines the single authoritative state model for a `Task`. Other project documents MUST reference this model rather than redefine Task states.

## 1. Purpose

A `Task` represents one logical unit of work requested by the C2 for a specific Agent.

The Task state describes the lifecycle of that logical unit of work. It MUST remain independent from:

- the network connection or `Session`,
- the Agent health state,
- the Agent communication state,
- the delivery state of individual protocol messages.

Communication failures therefore MUST NOT be interpreted automatically as Task failures.

---

## 2. Authoritative States

A Task has exactly one of the following states:

```text
PENDING
WAITING_ACK
QUEUED
RUNNING
COMPLETED
FAILED
TIMEOUT
CANCELLED
```

### State meanings

| State | Meaning |
|---|---|
| `PENDING` | Task exists in the C2 but has not yet been dispatched to the Agent. |
| `WAITING_ACK` | Task has been sent and the C2 is waiting for the Agent to acknowledge acceptance. |
| `QUEUED` | Agent has acknowledged the Task and accepted it for execution, but execution has not started. |
| `RUNNING` | Agent is executing the Task. |
| `COMPLETED` | Task execution finished successfully and a valid Result has been associated with it. |
| `FAILED` | Task execution finished unsuccessfully. |
| `TIMEOUT` | The Task exceeded an applicable deadline and was declared timed out by the responsible component. |
| `CANCELLED` | The Task was explicitly cancelled before successful completion. |

`UNKNOWN` is **not** a persistent Task lifecycle state.

It is a **recovery/reporting condition** used when the C2 cannot currently determine the authoritative execution state of a Task.

---

## 3. Canonical Lifecycle

The normal lifecycle is:

```text
PENDING
   │
   ▼
WAITING_ACK
   │
   ▼
QUEUED
   │
   ▼
RUNNING
   │
   ├──────────────► COMPLETED
   │
   └──────────────► FAILED
```

Additional terminal outcomes are:

```text
PENDING / WAITING_ACK / QUEUED / RUNNING
                 │
                 ├────────► TIMEOUT
                 │
                 └────────► CANCELLED
```

A Task does not have to spend a meaningful amount of time in every state.

For example, an Agent may acknowledge and immediately begin execution:

```text
PENDING → WAITING_ACK → QUEUED → RUNNING → COMPLETED
```

`QUEUED` may therefore be very brief.

---

## 4. Authoritative Transitions

| Current state | Event / condition | Next state |
|---|---|---|
| `PENDING` | Task dispatched | `WAITING_ACK` |
| `WAITING_ACK` | Valid `TASK_ACK` received | `QUEUED` |
| `QUEUED` | Agent starts execution | `RUNNING` |
| `RUNNING` | Successful execution + valid Result | `COMPLETED` |
| `RUNNING` | Execution failure + valid failure Result | `FAILED` |
| Applicable active state | Execution deadline exceeded and timeout declared | `TIMEOUT` |
| Cancellable active state | Explicit cancellation accepted | `CANCELLED` |

The implementation MUST NOT invent additional lifecycle states without updating this authoritative model.

---

## 5. Communication Failure

Communication state and Task state are separate.

For example:

```text
Task:       RUNNING
Session:    DISCONNECTED
Agent:      LIKELY_UNREACHABLE
```

This is valid.

A disconnected Session MUST NOT automatically cause:

```text
RUNNING → FAILED
```

Likewise:

```text
WAITING_ACK + connection loss
```

does not prove that the Agent never received the Task.

The C2 MUST use recovery mechanisms such as:

```text
PING/PONG
      ↓
TASK_STATUS_QUERY
      ↓
TASK_STATUS
```

before deciding whether a Task should be redispatched or ultimately timed out.

---

## 6. UNKNOWN as a Recovery Condition

`UNKNOWN` is not part of the authoritative persistent lifecycle.

It represents uncertainty about the current execution state.

Example:

```text
C2:
T001 = WAITING_ACK

Connection lost

C2 cannot determine whether:
- the Agent received T001,
- T001 was queued,
- T001 started,
- T001 completed.
```

The C2 may therefore temporarily obtain:

```text
T001 → UNKNOWN
```

for recovery purposes.

The C2 should then attempt to recover the actual state:

```text
PING
  ↓
PONG
  ↓
TASK_STATUS_QUERY(T001)
  ↓
TASK_STATUS(T001, RUNNING)
  ↓
T001 = RUNNING
```

The implementation MUST NOT treat `UNKNOWN` as permission to execute the Task again.

---

## 7. Result and Task State

A `Result` represents execution evidence produced by the Agent.

The Result does not represent network delivery status.

For a successful execution:

```text
RUNNING
   │
   ▼
RESULT(status=COMPLETED)
   │
   ▼
COMPLETED
```

For an unsuccessful execution:

```text
RUNNING
   │
   ▼
RESULT(status=FAILED)
   │
   ▼
FAILED
```

If the Agent completed the Task but the Result was lost during transmission, the Task MUST NOT automatically become `FAILED`.

Example:

```text
Agent:
T001 → COMPLETED
R001 retained locally

Connection lost

C2:
T001 = RUNNING
R001 = not received
```

After reconnection, synchronization can recover `R001` and reconcile the Task to:

```text
T001 = COMPLETED
R001 = stored
```

Therefore:

> **Execution state and Result delivery state are distinct concerns.**

---

## 8. Timeout Semantics

`TIMEOUT` means that the system has declared the Task timed out according to an applicable deadline.

A timeout does **not necessarily prove that execution stopped**.

For example:

```text
C2 deadline expires
        ↓
T001 = TIMEOUT
        ↓
Agent may still be executing T001
```

The implementation should therefore distinguish:

- **C2-side Task timeout**
- **actual Agent-side execution termination**

where necessary.

A timeout MUST NOT be interpreted as proof of successful cancellation or termination of execution.

---

## 9. Cancellation

`CANCELLED` represents an explicit cancellation decision.

Cancellation semantics depend on the execution stage.

### Before execution

Cancellation is comparatively straightforward:

```text
PENDING → CANCELLED
WAITING_ACK → CANCELLED
QUEUED → CANCELLED
```

provided the cancellation is accepted and processed before execution begins.

### During execution

The behavior of:

```text
RUNNING → CANCELLED
```

depends on whether the Agent supports safe cancellation of the command.

This transition remains an implementation-level capability and MUST NOT be assumed universally.

---

## 10. Terminal States

The authoritative terminal states are:

```text
COMPLETED
FAILED
TIMEOUT
CANCELLED
```

A Task in a terminal state MUST NOT silently return to:

```text
PENDING
WAITING_ACK
QUEUED
RUNNING
```

A new execution attempt represents a new logical Task unless an explicit retry/redispatch mechanism defines otherwise.

---

## 11. Retry and Redispatch

Retry is not represented by a separate Task state.

A retry policy operates on an existing Task or creates a new logical Task according to the implementation's idempotency model.

The system MUST NOT blindly redispatch a Task merely because its acknowledgement or Result was not received.

The preferred recovery sequence is:

```text
uncertain Task state
        ↓
connectivity check
        ↓
TASK_STATUS_QUERY
        ↓
recover actual state
        ↓
retry/redispatch only when justified
```

`task_id` remains the identifier of the logical Task.

---

## 12. Relationship with Session

A Task belongs to an `Agent`, not to a `Session`.

A Task may therefore span multiple Sessions:

```text
Agent A001

Session S041
    │
    └── Task T001 dispatched

connection lost

Session S042
    │
    └── Task T001 status recovered
```

The Session records communication context.

It does not own the Task lifecycle.

---

## 13. Relationship with Agent State

Task state and Agent state are independent.

For example:

```text
Agent health:        ALIVE
Agent activity:      BUSY
Communication:       CONNECTED
Task:                RUNNING
Session:             CONNECTED
```

or:

```text
Agent health:        ALIVE
Agent activity:      BUSY
Communication:       OFFLINE_WAIT
Task:                RUNNING
Session:             DISCONNECTED
```

The second situation is valid when the Agent continues execution locally after losing communication.

---

## 14. State Invariants

The following invariants are authoritative:

1. Every Task has exactly one logical `task_id`.
2. A Task belongs to exactly one `agent_id`.
3. A Task has exactly one current lifecycle state.
4. `UNKNOWN` is a recovery condition, not a persistent lifecycle state.
5. Communication failure does not automatically mean Task failure.
6. Missing `TASK_ACK` does not prove that a Task was not received.
7. Missing `RESULT` does not prove that execution failed.
8. A Task may span multiple Sessions.
9. A Result belongs to a Task and provides execution evidence.
10. A duplicate protocol message MUST NOT create duplicate Task execution.
11. A terminal Task MUST NOT silently return to an active lifecycle state.
12. Retry/redispatch does not introduce a new lifecycle state.
13. Timeout does not necessarily prove that Agent-side execution stopped.
14. Task state is owned by the Task lifecycle logic, principally `TaskManager` on the C2.

---

## 15. Authority of Project Documents

The Task state model is defined here.

Other documents have the following responsibilities:

| Document | Responsibility |
|---|---|
| `state-machines.md` | Visual representation and cross-entity state relationships |
| `protocol.md` | Protocol messages that carry Task information |
| `protocol-state-transition.md` | Mapping between protocol messages and Task transitions |
| `task-lifecycle.md` | Detailed Task lifecycle, recovery, retry and cancellation behavior |
| `reconnection-and-synchronization.md` | Recovery of Task state across communication loss and reconnection |
| `data-model.md` | Persistent representation of Task data |
| `testing-strategy.md` | Verification of valid and invalid Task transitions |

These documents MUST NOT redefine a different set of Task states.

When a conflict exists, this Task state model is authoritative.

---

## 16. Implementation Representation

The implementation should represent the state using a finite, explicit enumeration equivalent to:

```text
PENDING
WAITING_ACK
QUEUED
RUNNING
COMPLETED
FAILED
TIMEOUT
CANCELLED
```

State changes SHOULD pass through explicit transition logic rather than arbitrary assignment.

Conceptually:

```text
Task
 │
 ├── current_state
 ├── task_id
 ├── agent_id
 ├── timestamps
 ├── result_id?
 ├── error?
 └── timeout_reason?
```

The exact programming-language representation remains an implementation detail.

---

## 17. Final Authoritative Model

```text
                    ┌──────────────┐
                    │    PENDING   │
                    └──────┬───────┘
                           │ dispatch
                           ▼
                    ┌──────────────┐
                    │ WAITING_ACK  │
                    └──────┬───────┘
                           │ TASK_ACK
                           ▼
                    ┌──────────────┐
                    │    QUEUED    │
                    └──────┬───────┘
                           │ start
                           ▼
                    ┌──────────────┐
                    │    RUNNING   │
                    └───┬──────┬───┘
                        │      │
             success   │      │ failure
                        │      │
                        ▼      ▼
                 ┌──────────┐ ┌──────────┐
                 │COMPLETED │ │  FAILED  │
                 └──────────┘ └──────────┘


        Cancellation / timeout may terminate
        an applicable active Task:

        PENDING ────────┐
        WAITING_ACK ────┤
        QUEUED ─────────┼──► CANCELLED
        RUNNING ────────┘     (if supported)

        Applicable active state
                 │
                 ▼
              TIMEOUT
```

**Authoritative Task states:**

```text
PENDING
WAITING_ACK
QUEUED
RUNNING
COMPLETED
FAILED
TIMEOUT
CANCELLED
```

**Recovery condition, not a Task state:**

```text
UNKNOWN
```
