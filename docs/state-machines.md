# State Machines

> **Status: Work in Progress**
>
> This document defines the authoritative state machines for C2-AUTOMATED.
> It specifies valid states, transitions, triggers, and transition rules.
>
> The data model defines the entities and their relationships.
> This document defines how their logical state changes.
> The protocol defines how those changes are communicated.
>
> **This document is authoritative for logical state definitions and valid
> state transitions.**

---

# 1. Purpose

C2-AUTOMATED contains several independent but related state machines.

The main stateful entities are:

```text
Agent
├── Health
├── Activity
└── Communication

Session

Task

Result

File Transfer
```

These state machines MUST remain conceptually independent.

For example, the following combination is valid:

```text
Agent health          = ALIVE
Agent communication   = OFFLINE_WAIT
Agent activity        = BUSY

Task T001             = RUNNING
Session S042          = DISCONNECTED
```

There is no contradiction in this combination.

A communication failure does not automatically determine the execution state
of a Task or the health state of an Agent.

---

# 2. Normative Diagram Conventions

The diagrams in this document are **normative**.

They define the authoritative states and valid logical transitions of the
system. They are not examples of particular executions.

A normative diagram:

- MUST only contain states defined by this document;
- MUST only show valid logical transitions;
- MUST NOT introduce implementation-specific states;
- MUST NOT introduce protocol messages that are not themselves the transition
  definition;
- MUST NOT be interpreted as an exhaustive description of communication
  sequences between Agent and C2.

Scenario and sequence diagrams are intentionally kept outside this document.

They belong in documents such as:

- `protocol-state-transition.md`;
- `reconnection-and-synchronization.md`;
- `task-lifecycle.md`;
- `file-transfer.md`.

For example, a diagram showing:

```text
Agent → REGISTER → C2
Agent ← REGISTER_ACK ← C2
Agent → SYNC_STATE → C2
```

is a **protocol scenario**, not a state-machine definition.

Likewise, a diagram showing a particular Agent reconnecting from one Session
to another is an **illustrative scenario**, not an alternative Session state
machine.

---

# 3. State-Machine Conventions

The following notation is used:

```text
STATE_A
   │
   │ trigger
   ▼
STATE_B
```

A transition describes a logical state change caused by an event or condition.

The following terms are normative:

- **MUST** — required behavior.
- **MUST NOT** — prohibited behavior.
- **SHOULD** — recommended behavior unless a documented reason exists not to.
- **MAY** — optional behavior.

A state machine describes **logical state**, not necessarily a single Python
enum or database column.

Recovery procedures, protocol messages, and implementation mechanisms are
described in their respective documents and MUST NOT introduce alternative
definitions of the states specified here.

---

# 4. Agent State Machines

Agent state is divided into three independent dimensions:

```text
Agent
├── Health
├── Activity
└── Communication
```

This avoids creating a large combined state machine such as:

```text
ALIVE_CONNECTED_IDLE
ALIVE_CONNECTED_BUSY
ALIVE_DEGRADED_BUSY
...
```

Such combinations would grow unnecessarily and make the model harder to
maintain.

---

# 5. Agent Health State Machine

## 5.1 States

```text
UNKNOWN
ALIVE
LIKELY_UNREACHABLE
TERMINATED
```

### `UNKNOWN`

The C2 does not yet have sufficient information to consider the Agent
reachable.

### `ALIVE`

The Agent has recently demonstrated valid communication.

### `LIKELY_UNREACHABLE`

The Agent has failed to communicate according to the configured liveness
policy, but termination has not been established.

### `TERMINATED`

The Agent is explicitly or otherwise reliably known to have terminated.

Communication loss alone MUST NOT produce this state.

---

## 5.2 Normative State Diagram

```text
                   valid REGISTER
          ┌────────────────────────────┐
          │                            ▼
      UNKNOWN ──────────────────────► ALIVE
                                      │  ▲
                                      │  │ valid communication
                         liveness     │  │ resumes
                         threshold    │  │
                                      ▼  │
                              LIKELY_UNREACHABLE
                                  │          │
                                  │          │ valid communication
                                  │          └──────────────► ALIVE
                                  │
                                  │ confirmed termination
                                  ▼
                              TERMINATED

ALIVE ───────────── confirmed termination ─────────────► TERMINATED
```

---

## 5.3 Transitions

| Current State | Trigger | Result | Rule |
|---|---|---|---|
| `UNKNOWN` | Valid `REGISTER` | `ALIVE` | Agent identity is established or revalidated |
| `ALIVE` | Insufficient expected communication | `LIKELY_UNREACHABLE` | Based on configured liveness policy |
| `LIKELY_UNREACHABLE` | Valid communication | `ALIVE` | Reachability is restored |
| `ALIVE` | Confirmed termination | `TERMINATED` | Requires explicit or confirmed evidence |
| `LIKELY_UNREACHABLE` | Confirmed termination | `TERMINATED` | Requires explicit or confirmed evidence |
| Any | Communication loss alone | Unchanged or liveness transition | MUST NOT infer termination |

---

# 6. Agent Activity State Machine

## 6.1 States

```text
IDLE
BUSY
```

`RUNNING` is deliberately not an Agent state.

It belongs to the Task state machine.

---

## 6.2 Normative State Diagram

```text
       Task starts
IDLE ───────────────► BUSY
 ▲                     │
 │                     │ no active Task remains
 └─────────────────────┘
```

---

## 6.3 Transitions

| Current State | Trigger | Result |
|---|---|---|
| `IDLE` | Task execution starts | `BUSY` |
| `BUSY` | No active Task remains | `IDLE` |

Queued Tasks alone do not necessarily make the Agent `BUSY`.

---

# 7. Agent Communication State Machine

Communication state describes the Agent's communication lifecycle with the C2.

## 7.1 States

```text
CONNECTING
SYNCHRONIZING
CONNECTED
DEGRADED
OFFLINE_WAIT
```

### `CONNECTING`

The Agent is attempting to establish communication.

### `SYNCHRONIZING`

A new Session has been established and state reconciliation is in progress.

### `CONNECTED`

Synchronization has completed and normal communication is available.

### `DEGRADED`

Communication exists or may still be recoverable, but expected communication
has failed or become unreliable.

### `OFFLINE_WAIT`

Normal communication has failed according to the recovery policy. The Agent
waits before attempting another connection.

---

# 8. Normative Communication State Diagram

```text
                    successful connection
                 ┌─────────────────────────┐
                 │                         ▼
           CONNECTING ───────────────► SYNCHRONIZING
                                           │
                                           │ reconciliation complete
                                           ▼
                                      CONNECTED
                                      │       ▲
                       communication │       │ recovery
                         unreliable   │       │ succeeds
                                      ▼       │
                                  DEGRADED ───┘
                                      │
                                      │ recovery exhausted
                                      ▼
                                 OFFLINE_WAIT
                                      │
                                      │ reconnect attempt
                                      ▼
                                 CONNECTING
```

---

# 9. Communication Transitions

| Current State | Trigger | Result |
|---|---|---|
| `CONNECTING` | Connection succeeds | `SYNCHRONIZING` |
| `SYNCHRONIZING` | Reconciliation completes | `CONNECTED` |
| `CONNECTED` | Communication becomes unreliable | `DEGRADED` |
| `DEGRADED` | Communication recovers | `CONNECTED` |
| `DEGRADED` | Recovery policy exhausted | `OFFLINE_WAIT` |
| `OFFLINE_WAIT` | Reconnection attempt begins | `CONNECTING` |
| `CONNECTING` | Connection fails | `OFFLINE_WAIT` |
| `OFFLINE_WAIT` | No reconnect attempt currently active | `OFFLINE_WAIT` |

The Agent SHOULD periodically attempt reconnection from `OFFLINE_WAIT`.

It MUST NOT remain permanently silent.

Detailed reconnection and synchronization behavior is defined in
`reconnection-and-synchronization.md`.

---

# 10. Communication Failure Rules

Communication failure is deliberately separated from Task execution.

A communication failure may affect:

- the Agent communication state;
- the Session state;
- the Agent health state through the liveness policy.

It does not automatically imply:

```text
Task → FAILED
Agent → TERMINATED
```

A running Task may continue while communication is unavailable.

A queued Task normally remains queued until communication is restored and
synchronization has completed.

---

# 11. Session State Machine

A Session represents one communication episode between an Agent and the C2.

## 11.1 States

```text
CONNECTING
CONNECTED
DISCONNECTED
CLOSED
```

---

## 11.2 Normative State Diagram

```text
CONNECTING
    │
    │ successful establishment
    ▼
CONNECTED
   /    \
  /      \
 ▼        ▼
DISCONNECTED  CLOSED
```

`DISCONNECTED` and `CLOSED` are terminal states for that Session.

---

## 11.3 Transitions

| Current State | Trigger | Result |
|---|---|---|
| `CONNECTING` | Successful establishment | `CONNECTED` |
| `CONNECTED` | Connection lost | `DISCONNECTED` |
| `CONNECTED` | Orderly or explicit termination | `CLOSED` |

There is deliberately no:

```text
DISCONNECTED → CONNECTED
CLOSED → CONNECTED
```

transition.

---

# 12. New Session Rule

The Session state machine has no transition that reopens a terminated
Session.

When communication is re-established after a Session has ended, a **new
Session** MUST be created.

Therefore:

```text
DISCONNECTED / CLOSED
        │
        │ new connection
        ▼
   NEW Session
```

The previous Session remains historical.

The C2 MUST assign a new `session_id`.

The Agent identity remains unchanged.

The detailed reconnection sequence and synchronization workflow are defined
in `reconnection-and-synchronization.md`.

---

# 13. Task State Machine

The Task state model is **authoritative and frozen**.

## 13.1 States

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

These are the only authoritative Task lifecycle states.

Terminal states are:

```text
COMPLETED
FAILED
TIMEOUT
CANCELLED
```

`UNKNOWN` is **not** a Task lifecycle state.

It is a recovery/reporting condition used when the current execution state
cannot currently be established.

---

# 14. Normative Task State Diagram

```text
                         ┌──────────────────┐
                         │     PENDING      │
                         └────────┬─────────┘
                                  │
                               dispatch
                                  │
                                  ▼
                         ┌──────────────────┐
                         │   WAITING_ACK    │
                         └────────┬─────────┘
                                  │
                              TASK_ACK
                                  │
                                  ▼
                         ┌──────────────────┐
                         │      QUEUED      │
                         └────────┬─────────┘
                                  │
                            execution starts
                                  │
                                  ▼
                         ┌──────────────────┐
                         │     RUNNING      │
                         └───────┬──────────┘
                            ┌────┴────┐
                            │         │
                         success   failure
                            │         │
                            ▼         ▼
                     ┌───────────┐ ┌──────────┐
                     │ COMPLETED │ │  FAILED  │
                     └───────────┘ └──────────┘

Applicable non-terminal state ─────────► TIMEOUT
Applicable cancellable state ──────────► CANCELLED
```

The `TIMEOUT` and `CANCELLED` transitions are intentionally represented as
conditional transitions because their applicability depends on the Task
lifecycle and the final timeout or cancellation policy.

An acknowledgement deadline MUST NOT directly produce a final `TIMEOUT`
transition without the applicable recovery process.

---

# 15. Task Transitions

| Current State | Trigger | Result |
|---|---|---|
| `PENDING` | Task dispatched | `WAITING_ACK` |
| `WAITING_ACK` | Valid `TASK_ACK` | `QUEUED` |
| `QUEUED` | Execution begins | `RUNNING` |
| `RUNNING` | Successful execution | `COMPLETED` |
| `RUNNING` | Execution failure | `FAILED` |
| Applicable non-terminal state | Final timeout declared | `TIMEOUT` |
| Applicable cancellable state | Explicit cancellation accepted | `CANCELLED` |

The following is **not** a valid direct transition:

```text
WAITING_ACK
    │
    │ ACK deadline exceeded
    ▼
TIMEOUT
```

An acknowledgement deadline first creates a recovery condition.

The system should attempt to establish whether the Task was accepted before
declaring a final timeout.

Communication loss does not itself create:

```text
RUNNING → FAILED
```

or:

```text
RUNNING → TIMEOUT
```

---

# 16. Task State Semantics

## `PENDING`

The Task exists but has not yet been dispatched.

The Agent has not necessarily received the Task.

---

## `WAITING_ACK`

The Task has been dispatched and the C2 is waiting for Agent acceptance.

`TASK_ACK` means acceptance.

It does not mean:

```text
execution started
execution succeeded
execution completed
```

---

## `QUEUED`

The Agent has accepted the Task but execution has not started.

The exact scheduling and concurrency policy remain implementation decisions.

---

## `RUNNING`

The Agent is currently executing the Task.

`RUNNING` is a Task state, not an Agent state.

---

## `COMPLETED`

The requested operation has successfully completed.

A successful Task will normally have an associated Result.

The Result may be delivered later if communication is temporarily unavailable.

---

## `FAILED`

Execution did not complete successfully.

Execution failure is distinct from communication failure.

---

## `TIMEOUT`

The system has declared that an applicable deadline has been exceeded and
the Task has reached a final timeout condition.

A timeout does not necessarily prove that Agent-side execution stopped.

The exact timeout and post-timeout policy remains an implementation decision.

---

## `CANCELLED`

The Task was explicitly cancelled and the cancellation was accepted.

Cancellation semantics depend on the execution stage and command capabilities.

In particular, cancelling a `RUNNING` Task cannot be assumed to terminate its
execution unless the Agent supports safe interruption.

---

# 17. Task Recovery and `UNKNOWN`

`UNKNOWN` is deliberately excluded from the authoritative Task state model.

It represents uncertainty about the current Task state.

Recovery should attempt to obtain evidence such as:

```text
PING / PONG
TASK_STATUS_QUERY / TASK_STATUS
reconnection
synchronization
```

The Task then returns to one of its authoritative states.

`UNKNOWN` MUST NOT be treated as equivalent to:

```text
FAILED
COMPLETED
CANCELLED
```

It MUST NOT by itself authorize redispatch.

Detailed recovery behavior is defined in `task-lifecycle.md` and
`reconnection-and-synchronization.md`.

---

# 18. Communication Loss During Task Execution

Communication and Task execution are independent.

If communication is lost while a Task is `RUNNING`, the Task's execution state
does not automatically change.

Therefore, communication loss alone MUST NOT cause:

```text
RUNNING → FAILED
RUNNING → TIMEOUT
RUNNING → CANCELLED
```

The Agent may continue executing the Task and later produce a Result.

Likewise, a `QUEUED` Task may remain `QUEUED` while communication is
unavailable.

The Agent normally does not begin new queued C2-originated work until
communication recovery and synchronization have completed.

Detailed recovery behavior is defined elsewhere.

---

# 19. Result

The Result is related to the Task state machine but has its own lifecycle
concerns.

This document does **not** define an authoritative Result state enumeration.

The important invariant is:

```text
Task execution state
        ≠
Result delivery state
```

A Task may be complete while its Result has not yet been delivered to the C2.

The absence of a received Result MUST NOT automatically change:

```text
COMPLETED → FAILED
```

Result lifecycle details belong to the Result/data model and synchronization
documents.

---

# 20. File Transfer State Machine

The logical File Transfer lifecycle is:

```text
PENDING
   │
   │ transfer starts
   ▼
TRANSFERRING
   │
   │ transfer completes and verification succeeds
   ▼
COMPLETED
```

Failure and cancellation may terminate an active transfer.

---

## 20.1 States

```text
PENDING
TRANSFERRING
COMPLETED
FAILED
CANCELLED
```

---

## 20.2 Normative State Diagram

```text
PENDING
   │
   │ transfer starts
   ▼
TRANSFERRING
  /      \
 │        │
 │        │ transfer complete
 │        │ + verification succeeds
 │        ▼
 │    COMPLETED
 │
 ├── transfer failure ───────► FAILED
 │
 └── explicit cancellation ──► CANCELLED
```

Transfer chunks represent progress within `TRANSFERRING`; they do not create
additional states.

Detailed file-transfer behavior belongs in `file-transfer.md`.

---

# 21. Cross-State Invariants

The following constraints apply across the state machines.

## 21.1 Session

A Session cannot be revived.

A new connection creates a new Session.

## 21.2 Agent

Agent identity survives Session changes.

## 21.3 Task

Tasks belong to Agents, not Sessions.

A Task may therefore span multiple Sessions.

## 21.4 Result

Results belong to Tasks.

A Result may be produced during one Session and transmitted during another.

## 21.5 Communication

```text
Communication failure ≠ execution failure
```

## 21.6 Synchronization

Synchronization reconciles state.

It does not restore a previous Session.

## 21.7 Queued Work

Queued work normally waits while communication is unavailable and resumes
only after synchronization.

## 21.8 Duplicate Protection

Duplicate protocol delivery MUST NOT produce:

```text
duplicate Task execution
duplicate logical Result
duplicate unsafe operation
```

---

# 22. Invalid State Transitions

The following transitions are prohibited.

## Session

```text
DISCONNECTED → CONNECTED
CLOSED       → CONNECTED
```

A new connection creates a new Session.

## Task

```text
COMPLETED → RUNNING
FAILED    → RUNNING
TIMEOUT   → RUNNING
CANCELLED → RUNNING
```

A terminal Task does not silently return to an active lifecycle state.

## Agent

```text
communication loss → TERMINATED
```

is prohibited without confirmed termination evidence.

## Result

Duplicate `result_id` values MUST NOT create multiple logical Results.

---

# 23. State Persistence

State should be persisted according to the importance and lifetime of the
state.

The C2 should retain historical state for:

```text
Agents
Sessions
Tasks
Results
File Transfers
```

Runtime-only information may remain in memory where appropriate.

A restart MUST NOT reinterpret historical Sessions as active.

If an Agent reconnects after a C2 restart, the connection establishes a new
Session rather than reopening a historical Session.

---

# 24. Synchronization Invariants

Synchronization MUST preserve the following invariants:

```text
1. Session identity is never reused.

2. Agent identity remains stable.

3. Task identity remains stable across Sessions.

4. Result identity remains stable across retransmissions.

5. Communication state does not overwrite execution state without evidence.

6. A locally completed Task must not be re-executed merely because the C2
   has stale information.

7. A queued Task must not start merely because communication returned;
   synchronization must first reconcile relevant state.

8. Unknown Agent Tasks must not be silently accepted as authoritative C2
   Tasks.

9. Duplicate protocol messages must not create duplicate logical entities.
```

Detailed reconciliation rules are defined in
`reconnection-and-synchronization.md`.

---

# 25. Relationship to Other Documents

| Document | Responsibility |
|---|---|
| `data-model.md` | Entities, attributes, relationships and persistence model |
| `state-machines.md` | **Authoritative states and valid logical transitions** |
| `protocol.md` | Protocol messages and wire-level vocabulary |
| `protocol-state-transition.md` | Mapping protocol messages to state transitions |
| `reconnection-and-synchronization.md` | Recovery and cross-side reconciliation |
| `task-lifecycle.md` | Detailed Task lifecycle, recovery, retry and cancellation behavior |
| `file-transfer.md` | Detailed File Transfer behavior |
| `testing-strategy.md` | Verification of state machines and transitions |
| `DECISIONS.md` | Final architectural decisions |

Other documents MUST NOT redefine a conflicting set of states.

Where a conflict exists:

- this document is authoritative for **logical state definitions and valid
  transitions**;
- `protocol.md` is authoritative for protocol message definitions;
- `protocol-state-transition.md` is authoritative for how protocol messages
  trigger state changes;
- `reconnection-and-synchronization.md` is authoritative for reconciliation
  workflow.

---

# 26. Open Questions

The following implementation details remain to be finalized:

- exact liveness thresholds;
- Beacon interval;
- reconnect interval;
- exact Result lifecycle, if a separate Result state model is required;
- Task cancellation semantics;
- whether running Tasks can be interrupted;
- concurrent Task execution limits;
- exact synchronization conflict-resolution rules;
- persistence requirements for intermediate states;
- File Transfer resume behavior;
- acknowledgement timeout;
- execution timeout;
- post-timeout handling;
- duplicate identifier retention period;
- exact scheduling and queue policy.

These decisions should be recorded in `DECISIONS.md` when finalized.
