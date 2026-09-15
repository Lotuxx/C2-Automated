# Task Lifecycle

> **Status: Work in Progress**
>
> This document defines the conceptual Task lifecycle used by C2-AUTOMATED,
> including creation, dispatch, acknowledgement, queuing, execution, result
> handling, failure, timeout, cancellation, and Task-specific recovery.
>
> The authoritative state definitions are shared with `state-machines.md`.
> Protocol message semantics are defined in `protocol.md` and
> `protocol-state-transition.md`. Reconnection and cross-entity
> reconciliation are defined in `reconnection-and-synchronization.md`.

---

## 1. Purpose

A **Task** represents one logical operation requested by the operator and
intended for execution by one specific Agent.

The Task system separates:

- Task creation;
- Task tracking;
- Task queuing;
- Task dispatch;
- acknowledgement;
- execution;
- status reporting;
- Result handling;
- failure;
- timeout;
- cancellation;
- Task-specific recovery.

The model is designed for **asynchronous multi-Agent operation**.

A Task remains a logical object independently of the protocol messages used to
communicate about it.

---

## 2. Task Responsibility

Responsibility is divided between the C2 and the Agent.

```text
C2 Server
    │
    ├── create Task
    ├── track Task
    ├── queue / schedule Task
    ├── dispatch Task
    ├── process TASK_ACK
    ├── recover uncertain Task state
    └── process Result
          │
          ▼
        Agent
          │
          ├── receive Task
          ├── validate Task
          ├── acknowledge Task
          ├── queue Task if necessary
          ├── execute Task
          ├── report Task status
          └── produce Result
```

The C2 maintains the server-side Task record.

The Agent maintains the runtime execution state required to process the Task
and recover from temporary communication loss.

Neither side should assume that its local view is always immediately
synchronized with the other side.

---

# 3. Task vs Message vs Result

These concepts are distinct.

```text
Task
    = logical work requested by the C2

Message
    = one protocol communication unit

Result
    = outcome/data produced while processing a Task
```

One Task may therefore generate several protocol messages:

```text
T001
 │
 ├── TASK
 ├── TASK_ACK
 ├── TASK_STATUS
 └── RESULT
```

`task_id` identifies the logical Task.

`message_id` identifies one protocol message.

`result_id` identifies one logical Result.

A protocol message that is unrelated to a Task, such as `BEACON` or `PING`,
must not create an artificial Task.

---

# 4. Task Structure

A Task is conceptually represented by:

```text
Task
├── task_id
├── agent_id
├── command_type
├── parameters
├── status
│
├── created_at
├── dispatched_at
├── acknowledged_at
├── started_at
└── completed_at
│
├── ack_deadline
├── execution_deadline
├── timeout_reason?
├── result_id?
└── error?
```

The exact types and additional fields remain implementation decisions.

### `task_id`

Unique logical identifier for the Task.

It is used to correlate:

- the Task;
- `TASK_ACK`;
- `TASK_STATUS_QUERY`;
- `TASK_STATUS`;
- `RESULT`;
- Task-related Events.

### `agent_id`

Identifies the Agent for which the Task was created.

A Task belongs to one intended Agent.

### `command_type`

Identifies the operation to perform.

The available command types are defined by the project implementation.

Examples currently considered include:

```text
SHELL
SYSINFO
FILES
PERSISTENCE
SELF_DESTRUCT
```

These are command examples rather than requirements of the Task state
machine.

### `parameters`

Contains the parameters required by the selected command.

Parameters must be validated before execution.

### Timestamps

The Task may record:

```text
created_at
dispatched_at
acknowledged_at
started_at
completed_at
```

These timestamps support lifecycle tracking, timeout handling, troubleshooting,
and logging.

### Deadlines

Separate deadlines may be used for:

```text
ack_deadline
execution_deadline
```

This allows communication uncertainty and execution timeout to remain
distinct.

### `result_id`

Associates a completed Task with its corresponding Result where applicable.

### `error`

Contains relevant failure information when the Task fails.

---

# 5. Task States

The conceptual lifecycle is:

```text
                         CREATE
                           │
                           ▼
                      ┌─────────┐
                      │ PENDING │
                      └────┬────┘
                           │
                        dispatch
                           │
                           ▼
                   ┌──────────────┐
                   │ WAITING_ACK  │
                   └──────┬───────┘
                          │
                       TASK_ACK
                          │
                          ▼
                    ┌─────────┐
                    │ QUEUED  │
                    └────┬────┘
                         │
                      starts
                         │
                         ▼
                    ┌─────────┐
                    │ RUNNING │
                    └────┬────┘
                       ┌─┴──┐
                    success failure
                       │      │
                       ▼      ▼
                 COMPLETED   FAILED
```

The conceptual states are:

| State | Meaning |
|---|---|
| `PENDING` | Task exists but has not yet been dispatched. |
| `WAITING_ACK` | Task has been dispatched and the C2 is waiting for Agent acceptance. |
| `QUEUED` | Agent has accepted the Task but has not started it. |
| `RUNNING` | Agent is executing the Task. |
| `COMPLETED` | Task completed successfully. |
| `FAILED` | Task execution did not complete successfully. |
| `TIMEOUT` | Required communication or execution response exceeded its applicable deadline. |
| `CANCELLED` | Task was explicitly cancelled, where cancellation is supported. |

`CANCELLED` and the exact cancellation semantics remain subject to final
implementation decisions.

---

# 6. Normal Lifecycle

The normal lifecycle is:

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
   │
   ├───────────────┐
   │               │
success         failure
   │               │
   ▼               ▼
COMPLETED        FAILED
```

For a Task that starts immediately after acceptance, the Agent may effectively
move through:

```text
WAITING_ACK
   ↓
RUNNING
```

without remaining in `QUEUED` for a significant amount of time.

The lifecycle therefore represents logical states rather than mandatory
minimum durations.

---

# 7. `PENDING`

A Task enters `PENDING` when it is created by the C2.

```text
Operator
   │
   ▼
Interface
   │
   ▼
Task Manager
   │
   ▼
PENDING
```

The Task exists logically but has not yet been dispatched.

A Task may remain pending because:

- the scheduler has not selected it;
- the Agent is unavailable;
- the C2 is waiting for a communication opportunity;
- another scheduling condition prevents dispatch.

A Task being `PENDING` does not imply that the Agent has received it.

---

# 8. `WAITING_ACK`

After dispatch, the Task enters:

```text
WAITING_ACK
```

This means:

> The C2 has dispatched the Task and is waiting for confirmation that the
> Agent accepted it.

It does not mean:

- the Task failed;
- execution has started;
- execution has completed.

The relevant protocol exchange is:

```text
C2
 │
 │ TASK(T001)
 ▼
Agent
 │
 │ TASK_ACK(T001)
 ▼
C2
```

The `TASK_ACK` confirms acceptance, not successful execution.

---

# 9. `QUEUED`

`QUEUED` means that the Agent has accepted the Task but has not started
executing it.

Example:

```text
Agent A001

T001 → RUNNING
T002 → QUEUED
T003 → QUEUED
```

This permits several Tasks to be associated with the same Agent without
requiring them all to execute simultaneously.

The exact scheduling and concurrency model remain implementation decisions.

---

# 10. `RUNNING`

A Task enters `RUNNING` when execution starts on the Agent.

Conceptually:

```text
TASK
  │
  ▼
validation
  │
  ▼
acceptance / queue
  │
  ▼
Executor
  │
  ▼
Command Handler
  │
  ▼
execution
```

`RUNNING` belongs to the Task.

It must not be confused with the Agent's activity state.

For example:

```text
Agent:
    health = ALIVE
    activity = BUSY

Task:
    T001 = RUNNING
```

---

# 11. `COMPLETED`

A Task enters `COMPLETED` when its requested operation successfully finishes.

A successful completion should normally be associated with a Result.

```text
Agent
  │
  ├── execute T001
  │
  └── produce R001
          │
          ▼
        C2
          │
          ▼
     T001 = COMPLETED
```

The Result provides the execution outcome/data; the Task records the lifecycle
state.

A Result may be transmitted later if communication is temporarily
unavailable.

---

# 12. `FAILED`

A Task enters `FAILED` when execution does not complete successfully.

Example:

```text
T001
 │
 ▼
RUNNING
 │
 │ execution failure
 ▼
FAILED
```

Potential causes include:

- command execution failure;
- invalid execution conditions;
- unavailable local resources;
- command-specific errors;
- other implementation-defined execution failures.

Execution failure is distinct from communication failure.

---

# 13. `TIMEOUT`

`TIMEOUT` represents failure to obtain required information within an
applicable deadline.

There are two principal timeout categories.

### 13.1 Acknowledgement timeout

```text
WAITING_ACK
     │
     │ ack_deadline exceeded
     ▼
recovery
```

An acknowledgement timeout means that the C2 did not receive confirmation in
time.

It does **not prove that the Agent never received or accepted the Task**.

Task-specific recovery should therefore be attempted before redispatch where
possible.

### 13.2 Execution timeout

```text
RUNNING
   │
   │ execution_deadline exceeded
   ▼
TIMEOUT
```

An execution timeout means that the expected completion condition was not
observed within the configured deadline.

It does not necessarily prove that execution stopped at the deadline.

The final timeout policy remains implementation-dependent.

---

# 14. Communication Failure vs Task Failure

This distinction is fundamental.

```text
Communication failure
        ≠
Task failure
```

For example:

```text
T001 = RUNNING

connection lost

T001 may remain:
    RUNNING
```

The Agent may continue executing the Task and later produce:

```text
T001 = COMPLETED
R001 = available locally
```

Therefore, communication loss must not automatically cause:

```text
RUNNING → FAILED
```

or:

```text
RUNNING → CANCELLED
```

The detailed reconnection and synchronization procedure is defined in
`reconnection-and-synchronization.md`.

---

# 15. Task Status Reporting

The Agent can report Task state through:

```text
TASK_STATUS
```

The C2 can actively request state through:

```text
TASK_STATUS_QUERY
```

Conceptually:

```text
C2
 │
 │ TASK_STATUS_QUERY(T001)
 ▼
Agent
 │
 │ TASK_STATUS(T001, RUNNING)
 ▼
C2
```

Possible reported states include:

```text
QUEUED
RUNNING
COMPLETED
FAILED
UNKNOWN
```

`UNKNOWN` is useful when the Agent cannot establish the state of a Task.

A completed status may include:

```text
result_id = R001
```

allowing the C2 to recover knowledge of the corresponding Result.

---

# 16. Task Recovery

Task recovery is required when the C2's knowledge of a Task becomes
uncertain.

Typical causes include:

- lost `TASK_ACK`;
- lost `TASK_STATUS`;
- lost Result;
- communication interruption;
- Agent restart;
- C2 restart;
- incomplete synchronization.

The general recovery principle is:

```text
uncertainty
    ↓
obtain evidence
    ↓
reconcile Task state
    ↓
continue / finalize / redispatch
```

Reconnection itself is outside this document and is defined in
`reconnection-and-synchronization.md`.

---

# 17. Missing ACK Recovery

A missing `TASK_ACK` must not automatically trigger Task redispatch.

Example:

```text
C2                              Agent

TASK T001
 ───────────────────────────────►

                                accepts T001

TASK_ACK
 ◄────────────── X lost
```

The C2 may still have:

```text
T001 = WAITING_ACK
```

After the acknowledgement deadline, the C2 should attempt to establish the
actual Task state.

A baseline recovery sequence is:

```text
WAITING_ACK
     │
     │ acknowledgement timeout
     ▼
   PING
     │
     ▼
   PONG
     │
     ▼
TASK_STATUS_QUERY(T001)
     │
     ▼
TASK_STATUS
```

The result can indicate:

```text
QUEUED
RUNNING
COMPLETED
FAILED
UNKNOWN
```

The exact liveness and retry procedure is defined across
`protocol-state-transition.md` and `reconnection-and-synchronization.md`.

---

# 18. Missing Result Recovery

A Result may be produced successfully while its transmission to the C2 fails.

Example:

```text
T001
 ↓
RUNNING
 ↓
COMPLETED
 ↓
R001 produced
 ↓
communication failure
```

The Agent should retain the pending Result when the implementation supports
offline recovery.

After communication is restored, synchronization can identify:

```text
R001 = pending
```

and recover it.

The Task must not be executed again merely because the Result was not received.

The detailed reconciliation procedure belongs to
`reconnection-and-synchronization.md`.

---

# 19. `UNKNOWN` Task State

`UNKNOWN` is a **reported/recovery state**, rather than one of the persistent
normal lifecycle states defined above.

It means:

> The Agent cannot currently establish the state of the requested Task.

For example:

```text
C2:
    T001 = WAITING_ACK

Agent:
    T001 = UNKNOWN
```

The C2 must not interpret `UNKNOWN` as equivalent to:

```text
FAILED
```

or:

```text
COMPLETED
```

Depending on the available evidence and retry policy, the C2 may:

- query again;
- reconcile after reconnection;
- wait for additional evidence;
- consider redispatch.

Redispatch must be designed to avoid duplicate execution.

---

# 20. Duplicate Task Protection

Retries and reconnection can cause the same logical Task to be encountered
more than once.

The implementation must distinguish:

```text
task_id
    → logical Task identity

message_id
    → individual protocol message identity
```

For example:

```text
TASK
message_id = M100
task_id    = T001
```

If the same protocol message is received again:

```text
M100 / T001
M100 / T001
```

the Agent must not execute the logical Task twice merely because the message
was duplicated.

Likewise, receiving the same logical `task_id` through a different message
must not automatically create another logical Task.

The Agent should maintain bounded recent identifiers such as:

```text
recent_task_ids
recent_message_ids
```

The retention policy remains an implementation decision.

---

# 21. Why Blind Redispatch Is Avoided

Consider:

```text
C2 → TASK T001
Agent → accepts T001
Agent → begins execution
Agent → TASK_ACK
          X lost
```

If the C2 assumes that the Task was never received and immediately sends it
again:

```text
C2 → TASK T001
Agent → executes T001 again
```

the same logical operation may execute twice.

Therefore:

> **Missing acknowledgement is communication uncertainty, not proof that the
> Task was not accepted.**

The C2 should recover Task state before considering redispatch.

---

# 22. Task Queue

The C2 manages Tasks independently for each Agent.

Conceptually:

```text
A001 → [T004, T005]
A002 → [T006]
A003 → []
```

The queue ensures that a Task intended for one Agent is not accidentally
dispatched to another.

On the Agent side, several accepted Tasks may also be maintained:

```text
A001
 ├── T004 → RUNNING
 ├── T005 → QUEUED
 └── T006 → QUEUED
```

The exact scheduling policy, queue implementation, priorities, and concurrency
limits remain to be defined.

---

# 23. Asynchronous Multi-Agent Operation

The Task system must not block the C2 on one Agent or one Task.

The intended model is:

```text
Operator
    │
    ▼
Create T001
    │
    ▼
C2 continues managing other work
    │
    ├── A001 → T001
    ├── A002 → T002
    └── A003 → T003
```

An individual Task may remain:

```text
WAITING_ACK
QUEUED
RUNNING
```

while unrelated Tasks continue to be managed.

The exact concurrency mechanism is an implementation concern.

---

# 24. Task and Agent Relationship

Each Task is associated with one intended Agent:

```text
Agent A001
 ├── T001
 ├── T002
 └── T003

Agent A002
 └── T004
```

The association is identified by:

```text
task.agent_id
```

A Task does not move between Agents as a consequence of reconnection.

A reconnecting Agent creates a new Session while retaining the same
`agent_id`.

---

# 25. Task and Session Relationship

A Task is **not owned by a Session**.

A Task belongs to an Agent and may span multiple Sessions.

Example:

```text
Agent A001

S041
 │
 └── T001 = RUNNING
       │
       │ communication loss
       ▼
S041 = DISCONNECTED

S042
 │
 └── T001 = COMPLETED
       │
       └── R001 recovered
```

The Session records the communication episode through which Task-related
messages were exchanged.

It does not redefine the identity of the Task.

---

# 26. Task and Result Relationship

A Task may produce a Result.

```text
T001
  │
  └── R001
```

The association is established through:

```text
result.task_id = task.task_id
```

The Result remains distinct from the Task:

```text
Task
    → lifecycle and requested operation

Result
    → execution outcome/data
```

A Result may become available after the Task has completed locally but before
the C2 receives it.

---

# 27. Cancellation

Cancellation is an explicit lifecycle operation.

Examples that may eventually be supported:

```text
PENDING  → CANCELLED
QUEUED   → CANCELLED
```

Cancelling a `RUNNING` Task is more complex because safe interruption depends
on the command being executed.

The system must not assume that every command can be remotely interrupted.

Cancellation semantics, including whether cancellation is best-effort or
guaranteed, remain to be finalized.

---

# 28. Retry and Redispatch

Retries must be distinguished from Task recreation.

```text
Communication retry
    → attempt to recover communication or Task state

Task redispatch
    → request execution of the logical Task again
```

Communication recovery can use:

```text
PING / PONG
TASK_STATUS_QUERY / TASK_STATUS
```

Redispatch is a separate decision and must consider duplicate-execution risk.

The exact retry count, backoff, and redispatch policy remain open.

---

# 29. Task Validation

Tasks received by the Agent must be validated before execution.

```text
TASK
  │
  ▼
Protocol validation
  │
  ├── invalid → reject / ERROR
  │
  ▼
Task handling
  │
  ▼
Executor
  │
  ▼
Command implementation
```

Validation is performed at appropriate layers:

- protocol validation checks message structure and required fields;
- Task handling checks Task-level constraints;
- command implementation checks command-specific parameters.

The protocol-level rules are defined in `protocol.md`.

---

# 30. Task Lifecycle and Message Routing

Task-related messages are routed through the C2 Message Router.

```text
Incoming Message
       │
       ▼
Message Router
       │
       ├── TASK_ACK
       │      ↓
       │   Task Manager
       │
       ├── TASK_STATUS
       │      ↓
       │   Task Manager
       │
       └── RESULT
              ↓
          Result Manager
              │
              ▼
          Task Manager
```

The Message Router is responsible for routing.

The Task Manager remains responsible for Task state.

This separation prevents protocol handling from becoming the owner of domain
state.

---

# 31. Persistence

Relevant Task information is persisted through the C2 storage layer.

```text
Task Manager
     │
     ▼
Database Interface
     │
     ▼
SQLite
```

Potential persistent information includes:

```text
task_id
agent_id
command_type
parameters
status
timestamps
deadlines
result_id
timeout_reason
error
```

The exact persistence policy remains to be finalized.

---

# 32. Runtime vs Persistent State

The C2 may maintain active Task information in memory while persisting the
authoritative Task record.

```text
Runtime
├── active Tasks
├── queue
├── timeout tracking
└── active execution metadata

Persistent
├── Task identity
├── lifecycle state
├── timestamps
├── Result association
└── historical information
```

The exact consistency mechanism between runtime and persistent state remains an
implementation decision.

---

# 33. Logging and Traceability

Task-related lifecycle events should be recorded through the centralized
logging/Event mechanisms.

Examples include:

```text
Task created
Task dispatched
TASK_ACK received
Task queued
Task execution started
Task status received
Task completed
Task failed
Task timeout
Task cancellation
TASK_STATUS_QUERY sent
Result received
Unmatched Result detected
Task recovery initiated
```

Logging should provide sufficient information to reconstruct Task behaviour
without unnecessarily exposing sensitive command parameters or Result data.

---

# 34. End-to-End Normal Flow

The normal lifecycle can be represented as:

```text
                  OPERATOR
                     │
                     ▼
                  INTERFACE
                     │
                     ▼
                TASK MANAGER
                     │
                     ▼
                  PENDING
                     │
                  dispatch
                     ▼
                WAITING_ACK
                     │
                  TASK_ACK
                     ▼
                  QUEUED
                     │
                  execution
                     ▼
                  RUNNING
                     │
                  RESULT
                     ▼
                 COMPLETED
```

With immediate execution:

```text
PENDING
   ↓
WAITING_ACK
   ↓
RUNNING
   ↓
COMPLETED
```

With execution failure:

```text
RUNNING
   ↓
FAILED
```

With a final timeout:

```text
WAITING_ACK / RUNNING
          ↓
       TIMEOUT
```

---

# 35. Task Recovery Flow

The essential recovery principle is:

```text
             communication uncertainty
                       │
                       ▼
                obtain evidence
                       │
              ┌────────┴────────┐
              │                 │
        status available    status unknown
              │                 │
              ▼                 ▼
       update Task state    further recovery
                                │
                                ▼
                         possible redispatch
```

A Task is not redispatched simply because a communication message was lost.

Detailed reconnection and synchronization behaviour is defined in
`reconnection-and-synchronization.md`.

---

# 36. Architectural Invariants

The following rules should remain stable.

### Task identity

```text
One logical Task → one task_id
```

### Agent ownership

```text
One Task → one intended Agent
```

### Session independence

```text
Task belongs to Agent, not Session
```

### Result association

```text
Result.task_id → corresponding Task
```

### Communication independence

```text
Communication failure ≠ execution failure
```

### Acknowledgement semantics

```text
TASK_ACK = acceptance
TASK_ACK ≠ successful completion
```

### Status semantics

```text
TASK_STATUS = evidence of current/known Task state
```

### Duplicate protection

```text
Duplicate delivery must not cause duplicate logical execution.
```

### Recovery

```text
Uncertain Task state → recover evidence before redispatch where possible.
```

### Asynchronous operation

```text
One Task waiting/running must not block unrelated Tasks or Agents.
```

---

# 37. Relationship to Other Documents

| Document | Responsibility |
|---|---|
| `data-model.md` | Task entity, identifiers, relationships and persistence model |
| `state-machines.md` | Authoritative Task states and state transitions |
| `protocol.md` | Task-related protocol messages and fields |
| `protocol-state-transition.md` | Mapping messages such as `TASK_ACK` and `TASK_STATUS` to state changes |
| `reconnection-and-synchronization.md` | Reconnection, synchronization and cross-side reconciliation |
| `file-transfer.md` | File-transfer lifecycle when a Task involves file exchange |
| `testing-strategy.md` | Verification of Task lifecycle and recovery behaviour |
| `DECISIONS.md` | Final architectural decisions that resolve current open questions |

This document should not duplicate the full protocol specification,
reconnection workflow, or general state-machine definitions.

---

# 38. Open Questions

The following details remain to be finalized:

- exact acknowledgement timeout;
- exact execution timeout;
- timeout handling policy;
- retry count and backoff;
- redispatch conditions after `UNKNOWN`;
- whether `TASK_ACK` always leads to `QUEUED` or may directly precede `RUNNING`;
- maximum concurrent Tasks per Agent;
- Task scheduling and prioritization;
- cancellation semantics;
- whether running Tasks can be interrupted;
- exact duplicate Task handling;
- retention period/size for recent Task and Message identifiers;
- exact `TASK_STATUS` contents;
- Result recovery mechanism;
- persistence requirements for each Task state;
- in-memory/persistent state consistency;
- whether every Task transition generates an Event;
- behaviour after Agent or C2 restart;
- exact policy for Tasks that remain uncertain after repeated recovery attempts.

Once these decisions are finalized, the corresponding architectural choices
should be recorded in `DECISIONS.md`.
