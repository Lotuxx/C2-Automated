# State Machines

> **Status: Work in Progress**
>
> This document defines the authoritative state machines for C2-AUTOMATED.
> It specifies valid states, transitions, triggers, and transition rules.
>
> The data model defines the entities and their relationships.
> This document defines how their state changes.
> The protocol defines how those state changes are communicated.

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

For example:

```text
Agent health       = ALIVE
Agent communication = OFFLINE_WAIT
Agent activity     = BUSY

Task T001          = RUNNING
Session S042       = DISCONNECTED
```

There is no contradiction in this combination.

A communication failure does not automatically determine the execution state
of a Task or the health state of an Agent.

---

# 2. State-Machine Conventions

The following notation is used:

```text
STATE_A
   │
   │ trigger
   ▼
STATE_B
```

A transition describes a change caused by an event or condition.

The following terms are normative:

- **MUST** — required behavior.
- **MUST NOT** — prohibited behavior.
- **SHOULD** — recommended behavior unless a documented reason exists not to.
- **MAY** — optional behavior.

A state machine describes **logical state**, not necessarily a single Python
enum or database column.

---

# 3. Agent State Machines

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

# 4. Agent Health State Machine

## 4.1 States

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

## 4.2 State Diagram

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
                                      │
                                      │ confirmed termination
                                      ▼
                                  TERMINATED
```

`ALIVE → TERMINATED` is possible when explicit termination information exists,
but it MUST NOT be inferred solely from communication loss.

---

## 4.3 Transitions

| Current State | Trigger | Result | Rule |
|---|---|---|---|
| `UNKNOWN` | valid `REGISTER` | `ALIVE` | Agent identity is established/revalidated |
| `ALIVE` | insufficient expected communication | `LIKELY_UNREACHABLE` | Based on configured liveness policy |
| `LIKELY_UNREACHABLE` | valid communication | `ALIVE` | Reachability is restored |
| non-terminal | confirmed termination | `TERMINATED` | Requires explicit/confirmed evidence |
| any | communication loss alone | unchanged or liveness transition | MUST NOT infer termination |

---

# 5. Agent Activity State Machine

## 5.1 States

```text
IDLE
BUSY
```

`RUNNING` is deliberately not an Agent state.

It belongs to the Task state machine.

---

## 5.2 State Diagram

```text
       Task starts
IDLE ───────────────► BUSY
 ▲                     │
 │                     │ no active work
 └─────────────────────┘
```

The exact definition of when an Agent becomes `BUSY` depends on the execution
model.

A practical interpretation is:

```text
IDLE
→ no currently executing Task

BUSY
→ at least one Task is currently executing
```

---

## 5.3 Transitions

| Current State | Trigger | Result |
|---|---|---|
| `IDLE` | Task execution starts | `BUSY` |
| `BUSY` | No active Task remains | `IDLE` |

Queued Tasks alone do not necessarily make the Agent `BUSY`.

For example:

```text
Agent = IDLE
T001 = QUEUED
T002 = QUEUED
```

is valid if neither Task is currently executing.

---

# 6. Agent Communication State Machine

Communication state describes the Agent's ability to communicate with the C2.

## 6.1 States

```text
CONNECTING
CONNECTED
DEGRADED
OFFLINE_WAIT
SYNCHRONIZING
```

### `CONNECTING`

The Agent is attempting to establish communication.

### `CONNECTED`

A valid communication Session exists and normal communication is available.

### `DEGRADED`

Communication exists or may still be recoverable, but expected communication
has failed or become unreliable.

### `OFFLINE_WAIT`

Normal communication has failed according to the recovery policy. The Agent
waits before attempting another connection.

### `SYNCHRONIZING`

A new Session has been established and state reconciliation is in progress.

---

# 7. Communication State Diagram

```text
                         successful connection
                    ┌──────────────────────────┐
                    │                          ▼
              CONNECTING ─────────────────► SYNCHRONIZING
                                                │
                                                │ reconciliation complete
                                                ▼
                                           CONNECTED
                                           │       ▲
                            communication │       │ recovery
                              degraded     │       │ succeeds
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

# 8. Communication Transitions

| Current State | Trigger | Result |
|---|---|---|
| `CONNECTING` | Connection succeeds | `SYNCHRONIZING` |
| `SYNCHRONIZING` | Reconciliation complete | `CONNECTED` |
| `CONNECTED` | Communication becomes unreliable | `DEGRADED` |
| `DEGRADED` | Communication recovers | `CONNECTED` |
| `DEGRADED` | Recovery policy exhausted | `OFFLINE_WAIT` |
| `OFFLINE_WAIT` | Reconnection attempt begins | `CONNECTING` |
| `CONNECTING` | Connection fails | `OFFLINE_WAIT` |
| `OFFLINE_WAIT` | No reconnect attempt currently active | `OFFLINE_WAIT` |

The Agent SHOULD periodically attempt reconnection from `OFFLINE_WAIT`.

It MUST NOT remain permanently silent.

---

# 9. Communication Failure Rules

Communication failure is deliberately separated from Task execution.

```text
communication failure
        │
        ├── affects communication state
        │
        ├── affects Session state
        │
        └── MAY affect Agent liveness
```

It does not automatically imply:

```text
Task → FAILED
Agent → TERMINATED
Session → revived after reconnect
```

A running Task may continue while communication is unavailable.

A queued Task normally remains queued until communication is restored and
synchronization has completed.

---

# 10. Session State Machine

A Session represents one communication episode.

## 10.1 States

```text
CONNECTING
CONNECTED
DISCONNECTED
CLOSED
```

---

## 10.2 State Diagram

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

## 10.3 Transitions

| Current State | Trigger | Result |
|---|---|---|
| `CONNECTING` | Successful registration/establishment | `CONNECTED` |
| `CONNECTED` | Connection lost | `DISCONNECTED` |
| `CONNECTED` | Orderly/explicit termination | `CLOSED` |

There is deliberately no:

```text
DISCONNECTED → CONNECTED
CLOSED → CONNECTED
```

transition.

---

# 11. New Session Rule

When communication is re-established after a Session has ended:

```text
Old Session
S042 = DISCONNECTED
        │
        │ new Connection
        ▼
New Session
S043 = CONNECTED
```

The previous Session remains part of history.

The C2 MUST create a new `session_id`.

Therefore:

```text
S042 ≠ S043
```

The Agent identity remains the same:

```text
A001
 ├── S042
 └── S043
```

Synchronization occurs through S043; it does not revive S042.

---

# 12. Task State Machine

## 12.1 States

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

Final states are:

```text
COMPLETED
FAILED
TIMEOUT
CANCELLED
```

---

# 13. Task State Diagram

```text
PENDING
   │
   │ dispatch
   ▼
WAITING_ACK
   │
   │ TASK_ACK
   ▼
QUEUED
   │
   │ execution starts
   ▼
RUNNING
  │ │
  │ │
  │ └──────── execution failure ───────► FAILED
  │
  ├──────── successful completion ─────► COMPLETED
  │
  └──────── execution timeout ─────────► TIMEOUT

QUEUED ───────── explicit cancellation ─────────► CANCELLED
```

The `WAITING_ACK` timeout is a recovery condition before finalization, rather
than immediate proof that the Task failed.

---

# 14. Task Transitions

| Current State | Trigger | Result |
|---|---|---|
| `PENDING` | Task dispatched | `WAITING_ACK` |
| `WAITING_ACK` | Valid `TASK_ACK` | `QUEUED` |
| `QUEUED` | Execution begins | `RUNNING` |
| `RUNNING` | Successful execution | `COMPLETED` |
| `RUNNING` | Execution failure | `FAILED` |
| `RUNNING` | Execution deadline exceeded and recovery exhausted | `TIMEOUT` |
| `QUEUED` | Explicit cancellation | `CANCELLED` |
| `WAITING_ACK` | ACK deadline exceeded | Recovery procedure |
| unresolved Task | `TASK_STATUS` received | Reconcile according to reported state |

---

# 15. Task Recovery State

A Task does not require additional permanent states for every recovery
condition.

For example:

```text
WAITING_ACK
    │
    │ ACK timeout
    ▼
Recovery procedure
    │
    ├── PONG
    │     │
    │     ▼
    │  TASK_STATUS_QUERY
    │
    └── communication unavailable
          │
          ▼
       await reconnection
```

The underlying Task state remains logically distinct from the communication
recovery state.

This prevents states such as:

```text
TASK_WAITING_ACK_BUT_CONNECTION_LOST
TASK_RUNNING_BUT_CONNECTION_LOST
TASK_QUEUED_BUT_SYNCHRONIZING
```

from unnecessarily becoming part of the Task state machine.

---

# 16. Communication Loss During Task Execution

## 16.1 Running Task

When:

```text
Task = RUNNING
```

and communication is lost:

```text
Task
RUNNING
   │
   │ communication loss
   ▼
RUNNING
```

The Task does not automatically become `FAILED`.

If execution completes:

```text
RUNNING
   │
   │ local completion
   ▼
COMPLETED
```

The Result is retained locally until communication resumes.

---

## 16.2 Queued Task

When:

```text
Task = QUEUED
```

and communication becomes unavailable:

```text
QUEUED
   │
   │ communication loss
   ▼
QUEUED
```

The Agent MUST NOT normally begin new queued C2-originated work while in
communication-loss recovery.

---

# 17. Task Recovery After Reconnection

After reconnection:

```text
new Session
     │
     ▼
SYNCHRONIZING
     │
     ▼
Task reconciliation
     │
     ├── Task completed remotely
     ├── Task still running
     ├── Task still queued
     ├── Task failed
     └── Task unknown
```

Examples:

### C2 says RUNNING, Agent says COMPLETED

```text
C2:    T001 = RUNNING
Agent: T001 = COMPLETED, R001 exists

             ↓

C2 reconciles
             ↓

T001 = COMPLETED
R001 persisted
```

### C2 says PENDING, Agent says UNKNOWN

The C2 may dispatch the Task again, subject to duplicate-protection rules.

### Agent reports a Task unknown to C2

The C2 MUST NOT silently create a new Task merely because the Agent reports
one.

It is treated as an anomalous or unresolved condition requiring reconciliation.

---

# 18. Result State

The Result lifecycle is intentionally simpler than the Task lifecycle.

A Result can conceptually be:

```text
PENDING
RECEIVED
VERIFIED
FAILED
```

However, the exact Result state model is still implementation-dependent.

The important distinction is between:

```text
Task execution state
```

and:

```text
Result delivery state
```

For example:

```text
Task T001 = COMPLETED

Result R001
    └── delivery = PENDING
```

is valid.

The Task is complete even though its Result has not yet reached the C2.

---

# 19. Result Delivery

The normal path is:

```text
Task execution
      │
      ▼
Result produced
      │
      ├── C2 reachable ───────► Result transmitted
      │
      └── C2 unreachable
               │
               ▼
        Result retained locally
               │
               │ reconnect
               ▼
        Result synchronized
```

A Result MUST retain its `result_id` during retransmission.

Therefore retransmission does not create a new logical Result.

---

# 20. File Transfer State Machine

The logical File Transfer lifecycle is:

```text
PENDING
   │
   │ FILE_START
   ▼
TRANSFERRING
   │
   │ FILE_END + successful verification
   ▼
COMPLETED
```

Failure may produce:

```text
FAILED
```

Cancellation may produce:

```text
CANCELLED
```

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

## 20.2 State Diagram

```text
PENDING
   │
   │ FILE_START
   ▼
TRANSFERRING
  /      \
 │        │
 │        │ FILE_END + verification
 │        ▼
 │    COMPLETED
 │
 ├── transfer failure ───► FAILED
 │
 └── explicit cancellation ─► CANCELLED
```

`FILE_CHUNK` does not create a new state.

It represents progress within `TRANSFERRING`.

---

# 21. Cross-State Constraints

The following constraints apply across the state machines.

## 21.1 Session

```text
A Session cannot be revived.
```

A new connection creates a new Session.

## 21.2 Agent

```text
Agent identity survives Session changes.
```

## 21.3 Task

```text
Tasks belong to Agents, not Sessions.
```

A Task may therefore span multiple Sessions.

## 21.4 Result

```text
Results belong to Tasks.
```

A Result may be produced during one Session and transmitted during another.

## 21.5 Communication

```text
Communication failure does not equal execution failure.
```

## 21.6 Synchronization

```text
Synchronization reconciles state.
It does not restore a previous Session.
```

## 21.7 Queued Work

```text
Queued work normally waits while communication is unavailable
and resumes only after synchronization.
```

## 21.8 Duplicate Protection

Duplicate protocol delivery MUST NOT produce:

```text
duplicate Task execution
duplicate logical Result
duplicate unsafe operation
```

---

# 22. State Consistency Examples

## 22.1 Normal Execution

```text
Agent
  Health: ALIVE
  Communication: CONNECTED
  Activity: IDLE

T001
  PENDING
    ↓
  WAITING_ACK
    ↓
  QUEUED
    ↓
  RUNNING
    ↓
  COMPLETED
```

---

## 22.2 Running Task During Communication Loss

```text
Agent
  Health: ALIVE
  Communication: CONNECTED
  Activity: BUSY

Session S042
  CONNECTED

T001
  RUNNING

        │
        │ connection lost
        ▼

Session S042
  DISCONNECTED

Agent
  Communication: OFFLINE_WAIT

T001
  RUNNING

        │
        │ local completion
        ▼

T001
  COMPLETED

R001
  retained locally
```

Later:

```text
S043
  new Session

Agent
  CONNECTING
      ↓
  SYNCHRONIZING
      ↓
  CONNECTED

R001
  transmitted
```

---

## 22.3 Queued Tasks During Outage

```text
T001 = RUNNING
T002 = QUEUED
T003 = QUEUED

communication lost

T001 = RUNNING
T002 = QUEUED
T003 = QUEUED
```

The Agent does not start:

```text
T002
T003
```

until communication recovery and synchronization allow normal operation.

---

# 23. Invalid State Transitions

The following transitions are prohibited:

```text
Session:
DISCONNECTED → CONNECTED
CLOSED       → CONNECTED

Task:
COMPLETED → RUNNING
FAILED    → RUNNING
CANCELLED → RUNNING

Agent:
communication loss → TERMINATED
                   without confirmed termination

Result:
duplicate result_id → second logical Result
```

Other transitions may also be rejected according to the final implementation
and validation rules.

---

# 24. State Persistence

State should be persisted according to the importance and lifetime of the
state.

The C2 should retain historical states for:

```text
Sessions
Tasks
Results
File Transfers
Agents
```

Runtime-only information may remain in memory where appropriate.

A restart MUST NOT require the system to reinterpret old Sessions as active.

For example:

```text
Before restart:

S042 = DISCONNECTED

After restart:

S042 = DISCONNECTED
```

If the Agent reconnects:

```text
new connection
    ↓
S043
```

not:

```text
S042 → CONNECTED
```

---

# 25. Synchronization Invariants

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

---

# 26. Relationship to Other Documents

This document should remain focused on **state machines**.

| Document | Responsibility |
|---|---|
| `data-model.md` | Entities, attributes, relationships |
| `state-machines.md` | States and state transitions |
| `protocol.md` | Protocol messages and wire-level vocabulary |
| `protocol-state-transition.md` | Message → state transition mapping |
| `reconnection-and-synchronization.md` | Recovery and reconciliation workflow |
| `task-lifecycle.md` | Detailed Task lifecycle |
| `file-transfer.md` | Detailed file-transfer behavior |
| `network-architecture.md` | Network topology and communication architecture |
| `ARCHITECTURE.md` | Overall software architecture |

The same transition should not be redefined differently in those documents.

Where a conflict exists, this document is authoritative for **logical state
definitions and valid state transitions**, while
`protocol-state-transition.md` is authoritative for the protocol mechanism
that triggers them.

---

# 27. Open Questions

The following implementation details remain to be finalized:

- exact liveness thresholds;
- exact retry counts and delays;
- Beacon interval;
- reconnect interval;
- exact Result states;
- whether Result verification requires a separate state;
- Task cancellation semantics;
- concurrent Task execution limits;
- exact synchronization conflict-resolution rules;
- persistence requirements for intermediate states;
- File Transfer resume behavior;
- timeout values;
- duplicate identifier retention period.

These decisions should be recorded in `DECISIONS.md` when finalized.
