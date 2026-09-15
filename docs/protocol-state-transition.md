# Protocol-State Transition Specification

> **Status: Work in Progress**
>
> This document defines how protocol messages interact with the logical state
> machines of C2-AUTOMATED.
>
> `protocol.md` defines the messages themselves.  
> `state-machines.md` defines the authoritative states and valid state
> transitions.  
> This document connects the two by specifying which protocol events may cause
> or confirm those transitions.
>
> **This document is authoritative for the relationship between protocol
> messages and logical state transitions, but does not define new states.**

---

# 1. Purpose

A protocol message and a state transition are not equivalent.

A message represents communication:

```text
TASK
TASK_ACK
RESULT
PING
PONG
```

A state transition represents a change in the domain:

```text
WAITING_ACK → QUEUED
RUNNING     → COMPLETED
CONNECTED   → DISCONNECTED
```

The general processing model is:

```text
Protocol Message
       ↓
Validation
       ↓
Message Handler
       ↓
Domain Event / Evidence
       ↓
State Transition
       ↓
Persisted Domain State
```

A received message MUST therefore be interpreted according to its semantic
meaning rather than automatically mapped to a state change.

---

# 2. Authorities and Responsibilities

| Document | Authority |
|---|---|
| `protocol.md` | Message vocabulary and message semantics |
| `state-machines.md` | States and valid logical state transitions |
| `protocol-state-machines.md` | Relationship between protocol messages and state transitions |
| `reconnection-and-synchronization.md` | Reconnection and synchronization procedures |
| `task-lifecycle.md` | Detailed Task execution and recovery behavior |
| `file-transfer.md` | File-transfer lifecycle and transfer behavior |
| `data-model.md` | Entities, relationships, and persistence model |

This document MUST NOT redefine states established by `state-machines.md`.

---

# 3. Transition Conventions

### Causes

The message can directly cause the transition when its preconditions are
satisfied.

### Confirms

The message provides evidence that a state has been reached or that a
condition exists.

### Triggers handling

The message initiates processing, but the resulting state depends on
additional domain logic.

### No transition

Receiving the message does not itself change the referenced state.

A message MUST NOT cause a transition prohibited by `state-machines.md`.

---

# 4. Session Transitions

The Session state machine is:

```text
CONNECTING
    │
    │ transport connection established
    ▼
CONNECTED
    │
    ├── connection lost ───────→ DISCONNECTED
    │
    └── orderly termination ───→ CLOSED
```

The Session lifecycle concerns the **underlying connection episode**.

It is therefore distinct from Agent registration and synchronization.

A Session may be:

```text
Session = CONNECTED
Agent communication = SYNCHRONIZING
```

This is a valid state combination.

---

## 4.1 Session Message Mapping

| Message / Event | Role | Condition | Session effect |
|---|---|---|---|
| New connection | Causes | C2 accepts a new connection episode | Creates new Session in `CONNECTING` |
| Transport establishment | Causes | TCP/TLS or equivalent transport successfully established | `CONNECTING → CONNECTED` |
| `REGISTER` | Triggers handling | Received over the connected Session | Does not change Session state |
| `REGISTER_ACK` | Confirms | Registration accepted | Confirms registration over the already `CONNECTED` Session |
| `BEACON` | Confirms | Valid message received | Confirms active communication |
| `BEACON_ACK` | Confirms | Valid acknowledgement exchanged | Confirms successful communication |
| `PING` | Triggers handling | Sent over active communication | No direct Session transition |
| `PONG` | Confirms | Valid response received | Confirms communication reachability |
| Connection loss | Causes | Active connection disappears | `CONNECTED → DISCONNECTED` |
| Orderly termination | Causes | Session explicitly terminated | `CONNECTED → CLOSED` |

`REGISTER` MUST NOT be treated as the event that changes:

```text
CONNECTING → CONNECTED
```

That transition belongs to the underlying connection establishment.

---

## 4.2 New Session Rule

A new connection always creates a new Session.

The correct conceptual sequence is:

```text
New connection
      ↓
New Session
      ↓
CONNECTING
      ↓
transport established
      ↓
CONNECTED
      ↓
REGISTER
      ↓
Agent communication = SYNCHRONIZING
```

The `REGISTER` message identifies the Agent and begins the registration and
synchronization process.

It does not reopen an old Session.

`previous_session_id`, when present, is historical context only.

---

# 5. Agent Health Transitions

The Agent health states are:

```text
UNKNOWN
ALIVE
LIKELY_UNREACHABLE
TERMINATED
```

## 5.1 Message Mapping

| Message / Event | Role | Agent health effect |
|---|---|---|
| `REGISTER` | Causes/confirms | `UNKNOWN → ALIVE` when valid |
| `BEACON` | Confirms | Confirms current communication |
| `PONG` | Confirms | Confirms current reachability |
| `TASK_ACK` | Confirms | Provides communication evidence |
| `RESULT` | Confirms | Provides communication evidence |
| `TASK_STATUS` | Confirms | Provides communication evidence |
| Liveness threshold | Causes | `ALIVE → LIKELY_UNREACHABLE` |
| Valid communication while unreachable | Causes | `LIKELY_UNREACHABLE → ALIVE` |
| Confirmed termination | Causes | `ALIVE/LIKELY_UNREACHABLE → TERMINATED` |

Communication loss alone MUST NOT cause `TERMINATED`.

---

# 6. Agent Activity Transitions

The Agent activity states are:

```text
IDLE
BUSY
```

`RUNNING` remains a Task state.

| Message / Event | Effect |
|---|---|
| Task accepted and execution starts | May cause `IDLE → BUSY` |
| `TASK_ACK` | Confirms acceptance; does not necessarily imply `BUSY` |
| `TASK_STATUS = RUNNING` | Provides evidence of `BUSY` |
| `RESULT` completing active work | May cause `BUSY → IDLE` if no active Task remains |
| `BEACON` | Reports activity |
| Queued Task only | No direct activity transition |

---

# 7. Agent Communication Transitions

The Agent communication states are:

```text
CONNECTING
SYNCHRONIZING
CONNECTED
DEGRADED
OFFLINE_WAIT
```

The relevant mapping is:

| Event / Message | Effect |
|---|---|
| Connection attempt begins | `CONNECTING` |
| Transport established | `CONNECTING → SYNCHRONIZING` |
| `REGISTER` | Registration processing during `SYNCHRONIZING` |
| `REGISTER_ACK` | Confirms registration |
| `SYNC_STATE` | Synchronization processing |
| `SYNC_STATE_RESPONSE` | Reconciliation processing |
| `SYNC_COMPLETE` | `SYNCHRONIZING → CONNECTED` |
| Communication degradation | `CONNECTED → DEGRADED` |
| Recovery | `DEGRADED → CONNECTED` |
| Recovery exhausted | `DEGRADED → OFFLINE_WAIT` |
| Reconnection attempt | `OFFLINE_WAIT → CONNECTING` |

The important distinction is:

```text
Session CONNECTED
        ≠
Agent communication CONNECTED
```

A Session becomes `CONNECTED` when the underlying transport is established.

Agent communication becomes `CONNECTED` only after synchronization completes.

---

# 8. Task Transitions

The authoritative Task states are:

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

## 8.1 `TASK`

```text
PENDING
   │
   │ TASK dispatched
   ▼
WAITING_ACK
```

`TASK` MUST NOT directly cause:

```text
PENDING → RUNNING
```

Transmission does not prove execution.

---

## 8.2 `TASK_ACK`

```text
WAITING_ACK
      │
      │ TASK_ACK
      ▼
QUEUED
```

`TASK_ACK` means acceptance, not execution or completion.

---

## 8.3 `TASK_STATUS`

`TASK_STATUS` provides execution-state evidence.

Possible reports include:

```text
QUEUED
RUNNING
COMPLETED
FAILED
UNKNOWN
```

`UNKNOWN` is a recovery/reporting condition and is not a persistent Task
state.

A reported state MUST be reconciled with existing C2 state before applying a
transition.

---

## 8.4 `RESULT`

A successful Result may provide evidence for:

```text
RUNNING → COMPLETED
```

An execution failure may provide evidence for:

```text
RUNNING → FAILED
```

A Result for an unknown Task MUST NOT implicitly create a Task.

---

## 8.5 Timeout

An acknowledgement deadline does not directly mean:

```text
WAITING_ACK → TIMEOUT
```

Instead:

```text
ACK deadline exceeded
        ↓
recovery
        ↓
state established?
        ↓
final timeout only if policy requires it
```

---

## 8.6 Cancellation

An explicit cancellation accepted by the Agent may produce:

```text
Applicable state → CANCELLED
```

Sending a cancellation request does not itself prove that a running Task has
stopped.

---

## 8.7 Communication Failure

Communication loss does not directly alter Task execution state.

For example:

```text
RUNNING + connection loss → RUNNING
```

remains valid.

---

# 9. Result Transitions

No independent authoritative Result state machine is defined here.

The essential distinction is:

```text
Task execution state
        ≠
Result delivery state
```

A Result may be retained on the Agent before being transmitted.

A missing Result MUST NOT automatically cause Task failure.

---

# 10. Liveness Message Transitions

## `BEACON`

A valid Beacon confirms current communication and updates liveness
information.

It does not directly change Task state.

## `BEACON_ACK`

Confirms successful processing of the Beacon.

It is not a Task acknowledgement.

## `PING` / `PONG`

A valid `PONG` confirms communication reachability.

It does not prove Task completion or Result delivery.

---

# 11. Synchronization Message Transitions

Synchronization occurs after the Session has already become `CONNECTED`.

The Agent communication state progresses through:

```text
CONNECTING
      │
      │ transport established
      ▼
SYNCHRONIZING
      │
      │ REGISTER / synchronization
      ▼
CONNECTED
```

The Session state during this process is already:

```text
CONNECTED
```

The relevant protocol messages are:

```text
REGISTER
REGISTER_ACK
SYNC_STATE
SYNC_STATE_RESPONSE
SYNC_COMPLETE
```

## 11.1 `REGISTER`

`REGISTER` identifies the Agent over the newly established Session.

It does not create or reopen the Session.

## 11.2 `REGISTER_ACK`

`REGISTER_ACK` confirms registration and provides the new Session identity.

It does not transition the Session from `CONNECTING` to `CONNECTED`; that has
already occurred at transport establishment.

It supports the Agent communication transition into synchronization.

## 11.3 `SYNC_STATE`

Provides retained Agent state as synchronization evidence.

It does not itself change Task state.

## 11.4 `SYNC_STATE_RESPONSE`

Communicates C2 reconciliation decisions and required updates.

All resulting Task transitions remain subject to `state-machines.md`.

## 11.5 `SYNC_COMPLETE`

Marks completion of synchronization:

```text
SYNCHRONIZING → CONNECTED
```

Normal Agent communication may then resume.

---

# 12. File Transfer Transitions

The authoritative File Transfer states are:

```text
PENDING
TRANSFERRING
COMPLETED
FAILED
CANCELLED
```

## 12.1 `FILE_START`

```text
PENDING → TRANSFERRING
```

## 12.2 `FILE_CHUNK`

A valid chunk keeps the transfer in:

```text
TRANSFERRING
```

## 12.3 `FILE_END`

After completeness and integrity validation:

```text
TRANSFERRING → COMPLETED
```

Failure or cancellation may produce the corresponding terminal state.

---

# 13. Error Message Transitions

`ERROR` has no universal state transition.

Its effect depends on context:

```text
Protocol error
    → message rejection

Task error
    → Task may become FAILED

Transfer error
    → Transfer may become FAILED

Communication error
    → may contribute to communication/session recovery
```

---

# 14. Cross-Message Correlation Rules

## Task

Use `task_id` to correlate:

```text
TASK
TASK_ACK
TASK_STATUS_QUERY
TASK_STATUS
RESULT
```

## Result

Use `result_id` and the associated `task_id`.

Duplicate `result_id` values MUST NOT create duplicate Results.

## Session

Use `session_id` to identify the communication episode.

An old Session MUST NOT be reactivated by receiving a message.

## File Transfer

Use `transfer_id` across:

```text
FILE_START
FILE_CHUNK
FILE_END
```

---

# 15. Duplicate and Replay Protection

The protocol distinguishes:

```text
message_id
task_id
result_id
transfer_id
session_id
```

Duplicate protocol delivery MUST NOT create duplicate logical entities or
invalid state transitions.

---

# 16. Invalid Protocol-to-State Transitions

| Situation | Invalid transition |
|---|---|
| Transport established | Session `CONNECTING → CONNECTED` is valid; `REGISTER` is not required for this transition |
| `REGISTER` received | Session `CONNECTING → CONNECTED` solely because of `REGISTER` |
| Old Session receives communication | `DISCONNECTED → CONNECTED` |
| Old Session receives communication | `CLOSED → CONNECTED` |
| Connection loss | Task `RUNNING → FAILED` solely from communication loss |
| Connection loss | Agent `ALIVE → TERMINATED` solely from communication loss |
| `TASK` transmitted | `PENDING → RUNNING` |
| `TASK_ACK` received | `WAITING_ACK → COMPLETED` |
| `PONG` received | Task → `COMPLETED` |
| Missing Result | Task → `FAILED` without execution evidence |
| Duplicate Task message | Create second logical Task |
| Duplicate Result | Create second logical Result |
| Unknown Result Task | Create implicit Task |
| `SYNC_COMPLETE` | Automatically execute every queued Task without normal Task rules |

---

# 17. State Evidence vs State Commands

## Commands

```text
TASK
TASK_STATUS_QUERY
PING
```

## Acknowledgements

```text
TASK_ACK
BEACON_ACK
REGISTER_ACK
```

## Reports

```text
TASK_STATUS
RESULT
BEACON
SYNC_STATE
```

## Synchronization

```text
SYNC_STATE
SYNC_STATE_RESPONSE
SYNC_COMPLETE
```

An acknowledgement does not necessarily mean completion.

A report provides evidence but does not necessarily command a transition.

---

# 18. Illustrative Transition Scenarios

The following diagrams are **illustrative only**.

They do not redefine the normative state machines.

## 18.1 New Connection and Synchronization

```text
Transport
    │
    │ connection established
    ▼
Session = CONNECTED
    │
    │ REGISTER
    ▼
Agent communication = SYNCHRONIZING
    │
    │ SYNC_STATE / reconciliation
    ▼
SYNC_COMPLETE
    │
    ▼
Agent communication = CONNECTED
```

This is the canonical distinction between Session connectivity and
communication readiness.

---

## 18.2 Normal Task Execution

```text
C2                         Agent

 │                           │
 │──── TASK T001 ─────────► │
 │◄─── TASK_ACK T001 ────── │
 │                           │
 │      Task = QUEUED        │
 │                           │
 │      execution starts     │
 │                           │
 │      Task = RUNNING       │
 │                           │
 │◄──── RESULT R001 ──────── │
 │                           │
 │      Task = COMPLETED     │
```

---

## 18.3 Running Task During Communication Loss

```text
Task = RUNNING
       │
       │ connection lost
       ▼
Task = RUNNING

Agent continues execution
       │
       ▼
Result retained

New Session
       │
       ▼
Synchronization
       │
       ▼
RESULT transmitted
```

The communication interruption does not itself change the Task state.

---

# 19. Implementation Guidance

Protocol handlers should follow:

```text
receive message
      ↓
deserialize
      ↓
validate
      ↓
identify message type
      ↓
resolve referenced entities
      ↓
verify preconditions
      ↓
apply permitted state transition
      ↓
persist state
      ↓
emit Event / response
```

A handler MUST NOT directly modify unrelated domain state merely because
information is present in a message.

For example, `PONG` must not mark a Task as completed.

Similarly, `RESULT` should update the corresponding Task/Result state while
Session communication evidence is handled separately.

---

# 20. Relationship to Other Documents

| Document | Responsibility |
|---|---|
| `protocol.md` | Message definitions and fields |
| `state-machines.md` | Authoritative states and transitions |
| `protocol-state-machines.md` | Protocol-to-state mapping |
| `reconnection-and-synchronization.md` | Reconnection and reconciliation |
| `task-lifecycle.md` | Task execution and recovery |
| `file-transfer.md` | File Transfer lifecycle |
| `data-model.md` | Entity identity and relationships |

Scenario diagrams in this document are illustrative and MUST NOT redefine
the normative state machines.

---

# 21. Open Questions

The following remain implementation decisions:

- exact handling of conflicting `TASK_STATUS` reports;
- exact behavior when a Result arrives before Task synchronization;
- acknowledgement/retry timing;
- synchronization conflict resolution;
- Beacon acknowledgement correlation;
- Result verification details;
- cancellation semantics;
- duplicate-retention duration;
- replay protection;
- error-to-state mapping.

Final decisions should be recorded in `DECISIONS.md`.
