# Task Lifecycle

> **Status: Work in Progress**
>
> This document defines the detailed lifecycle and operational behavior of a
> Task in C2-AUTOMATED, including creation, dispatch, acknowledgement,
> queuing, execution, Result handling, failure, timeout, cancellation, and
> Task-specific recovery.
>
> The authoritative Task states and valid transitions are defined in
> `state-machines.md`.
>
> Protocol message semantics and their relationship to state transitions are
> defined in `protocol.md` and `protocol-state-transition.md`.
>
> Reconnection and cross-entity reconciliation are defined in
> `reconnection-and-synchronization.md`.

---

# 1. Purpose

A **Task** represents one logical operation requested by the operator and
intended for execution by one specific Agent.

The Task lifecycle separates:

- Task creation;
- Task tracking;
- queuing and dispatch;
- acknowledgement;
- execution;
- status reporting;
- Result handling;
- failure;
- timeout;
- cancellation;
- Task-specific recovery.

The model is designed for **asynchronous multi-Agent operation**.

A Task remains a logical domain object independently of the protocol messages
used to communicate about it.

---

# 2. Task Responsibility

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

The C2 maintains the authoritative server-side Task record.

The Agent maintains the runtime execution information required to process the
Task and recover from temporary communication loss.

Neither side should assume that its local view is always immediately
synchronized with the other side.

---

# 3. Task, Message and Result

These concepts are distinct.

```text
Task
    = logical work requested by the C2

Message
    = one protocol communication unit

Result
    = execution outcome/data produced while processing a Task
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

Identifiers have different meanings:

```text
task_id
    → logical Task identity

message_id
    → individual protocol message identity

result_id
    → logical Result identity
```

A protocol message unrelated to a Task, such as `BEACON` or `PING`, must not
create an artificial Task.

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

## 4.1 `task_id`

Unique logical identifier for the Task.

It is used to correlate:

- the Task;
- `TASK_ACK`;
- `TASK_STATUS_QUERY`;
- `TASK_STATUS`;
- `RESULT`;
- Task-related Events.

## 4.2 `agent_id`

Identifies the Agent for which the Task was created.

A Task belongs to one intended Agent.

The Task does not move to another Agent merely because communication with its
original Agent is temporarily unavailable.

## 4.3 `command_type`

Identifies the operation to perform.

The available command types are defined by the implementation.

Examples currently considered include:

```text
SHELL
SYSINFO
FILES
PERSISTENCE
SELF_DESTRUCT
```

These are command examples rather than requirements of the Task state machine.

## 4.4 `parameters`

Contains the parameters required by the selected command.

Parameters must be validated before execution.

## 4.5 Timestamps

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

## 4.6 Deadlines

Separate deadlines may be used for:

```text
ack_deadline
execution_deadline
```

This keeps acknowledgement/communication uncertainty distinct from execution
timeout.

## 4.7 `result_id`

Associates a Task with its corresponding Result where applicable.

## 4.8 `error`

Contains relevant failure information when the Task fails.

---

# 5. Authoritative Task States

The authoritative persistent Task states are:

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

Terminal states are:

```text
COMPLETED
FAILED
TIMEOUT
CANCELLED
```

`UNKNOWN` is **not** a persistent Task state.

It is a reporting/recovery condition used when the current execution state
cannot be established.

The authoritative state definitions and valid transitions are maintained in
`state-machines.md`.

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

For a Task that starts immediately after acceptance, the Agent may move through
the logical sequence:

```text
WAITING_ACK
   ↓
QUEUED
   ↓
RUNNING
```

with `QUEUED` existing only briefly.

The states describe logical lifecycle conditions; they do not impose a minimum
duration for any state.

---

# 7. Task Creation and `PENDING`

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

`PENDING` does not imply that the Agent has received the Task.

---

# 8. Dispatch and `WAITING_ACK`

When the C2 dispatches a Task, its authoritative state becomes:

```text
PENDING → WAITING_ACK
```

The meaning is:

> The C2 has sent the Task and is waiting for confirmation that the Agent
> accepted it.

Conceptually:

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

`WAITING_ACK` does not mean:

- execution has started;
- execution has succeeded;
- execution has completed;
- the Agent has necessarily accepted the Task.

`TASK_ACK` is the evidence of acceptance.

---

# 9. `TASK_ACK` and Acceptance

A valid `TASK_ACK` confirms that the Agent received and accepted the Task.

The normal lifecycle is:

```text
WAITING_ACK
      │
      │ TASK_ACK
      ▼
QUEUED
```

`TASK_ACK` means:

```text
accepted
```

It does **not** mean:

```text
running
successful
completed
```

After acceptance, the Agent may:

```text
QUEUED → RUNNING
```

when execution begins.

A duplicate `TASK_ACK` must not create another Task or repeat an already
processed logical transition.

---

# 10. `QUEUED`

`QUEUED` means that the Agent has accepted the Task but has not started
executing it.

Example:

```text
Agent A001

T001 → RUNNING
T002 → QUEUED
T003 → QUEUED
```

This allows multiple Tasks to be associated with the same Agent without
requiring simultaneous execution.

The exact scheduling and concurrency model remain implementation decisions.

A queued Task remains queued during temporary communication loss unless
separate evidence establishes another state.

---

# 11. `RUNNING`

A Task enters `RUNNING` when execution actually starts on the Agent.

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

`RUNNING` is a Task state.

It must not be confused with the Agent activity state:

```text
Agent:
    health = ALIVE
    activity = BUSY

Task:
    T001 = RUNNING
```

The Agent activity state is derived from its overall execution activity, not
from the existence of one particular Task.

---

# 12. `COMPLETED`

A Task enters `COMPLETED` when its requested operation successfully finishes.

A successful completion should normally produce a Result.

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

The Task records the lifecycle state.

The Result records the execution outcome/data.

These remain distinct even when they are transmitted together.

A Result may be retained on the Agent and transmitted later if communication
is temporarily unavailable.

---

# 13. `FAILED`

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
- invalid execution conditions discovered during processing;
- unavailable local resources;
- command-specific errors;
- other implementation-defined execution failures.

Execution failure is distinct from communication failure.

A communication failure alone MUST NOT produce:

```text
RUNNING → FAILED
```

---

# 14. `TIMEOUT`

`TIMEOUT` represents a final timeout decision made after an applicable
deadline has been exceeded and the required recovery policy has been applied.

There are two principal timeout situations.

## 14.1 Acknowledgement Deadline

When:

```text
WAITING_ACK
```

exceeds `ack_deadline`, the C2 has evidence that acknowledgement has not been
received in time.

This does **not** immediately mean:

```text
WAITING_ACK → TIMEOUT
```

Instead:

```text
WAITING_ACK
     │
     │ ack deadline exceeded
     ▼
recovery condition
     │
     ▼
attempt to establish actual Task state
```

Possible recovery evidence includes:

```text
PING / PONG
TASK_STATUS_QUERY / TASK_STATUS
reconnection
synchronization
```

Only the final timeout policy may declare:

```text
→ TIMEOUT
```

This prevents a lost `TASK_ACK` from being confused with proof that the Task
was never accepted.

## 14.2 Execution Deadline

If a Task is:

```text
RUNNING
```

and its `execution_deadline` is exceeded, the C2 may eventually declare:

```text
RUNNING → TIMEOUT
```

after applying the configured timeout policy.

This means that the expected completion condition was not observed within the
allowed time.

It does **not necessarily prove** that execution stopped at the deadline.

The Agent may still have executed the operation or may later report a Result.

---

# 15. Communication Failure vs Task Failure

This distinction is fundamental:

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

Therefore communication loss must not automatically cause:

```text
RUNNING → FAILED
```

or:

```text
RUNNING → CANCELLED
```

It should instead trigger the relevant communication recovery and, where
necessary, Task-state reconciliation.

The detailed reconnection and synchronization procedure is defined in
`reconnection-and-synchronization.md`.

---

# 16. Task Status Reporting

The Agent may report Task state through:

```text
TASK_STATUS
```

The C2 may actively request state through:

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

A status report is **evidence about the Agent's current knowledge**.

It is not automatically an instruction to change the C2's authoritative Task
state.

Possible reported states include:

```text
QUEUED
RUNNING
COMPLETED
FAILED
UNKNOWN
```

`UNKNOWN` is a recovery/reporting condition.

For example:

```text
C2:
    T001 = WAITING_ACK

Agent:
    T001 = UNKNOWN
```

The C2 must evaluate the report together with:

- the current authoritative Task state;
- the Session through which the report arrived;
- timestamps;
- previous evidence;
- synchronization information;
- applicable transition rules.

A stale or conflicting status report must not automatically reopen a Task that
has already reached a terminal state.

---

# 17. Task Recovery

Task recovery is required when the C2's knowledge of a Task becomes uncertain.

Typical causes include:

- lost `TASK_ACK`;
- lost `TASK_STATUS`;
- lost Result;
- communication interruption;
- Agent restart;
- C2 restart;
- incomplete synchronization.

The general principle is:

```text
uncertainty
    ↓
obtain evidence
    ↓
reconcile Task state
    ↓
continue / finalize / redispatch
```

Recovery does not introduce another persistent Task state.

Reconnection itself is outside this document and is defined in
`reconnection-and-synchronization.md`.

---

# 18. Missing ACK Recovery

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
     │ acknowledgement deadline exceeded
     ▼
recover communication
     │
     ▼
TASK_STATUS_QUERY(T001)
     │
     ▼
TASK_STATUS
```

The returned evidence may indicate:

```text
QUEUED
RUNNING
COMPLETED
FAILED
UNKNOWN
```

The C2 then applies the appropriate transition or recovery policy.

---

# 19. Missing Result Recovery

A Result may be produced successfully while its transmission to the C2 fails.

Example:

```text
T001
 ↓
RUNNING
 ↓
COMPLETED locally
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

The Task must not be executed again merely because its Result was not received.

This distinction is important:

```text
Task execution state
        ≠
Result delivery state
```

A Task may therefore be:

```text
COMPLETED
```

while its Result is still waiting to reach the C2.

---

# 20. `UNKNOWN` as a Recovery Condition

`UNKNOWN` is not one of the authoritative persistent Task states.

It means:

> The current execution state of the Task cannot currently be established.

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

Possible recovery actions include:

- query again;
- reconnect and synchronize;
- wait for additional evidence;
- recover a retained Result;
- evaluate whether redispatch is safe.

Redispatch must account for the possibility that the original Task was already
accepted or executed.

---

# 21. Duplicate Task Protection

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

Likewise, receiving the same logical `task_id` through another delivery must
not automatically create another logical Task.

The Agent may maintain bounded recent identifiers such as:

```text
recent_task_ids
recent_message_ids
```

The retention policy remains an implementation decision.

---

# 22. Why Blind Redispatch Is Avoided

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

# 23. Task Queue

The C2 manages Tasks independently for each Agent.

Conceptually:

```text
A001 → [T004, T005]
A002 → [T006]
A003 → []
```

The queue ensures that a Task intended for one Agent is not accidentally
dispatched to another.

On the Agent side:

```text
A001
 ├── T004 → RUNNING
 ├── T005 → QUEUED
 └── T006 → QUEUED
```

The exact scheduling policy, queue implementation, priorities, and concurrency
limits remain implementation decisions.

---

# 24. Asynchronous Multi-Agent Operation

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

# 25. Task and Agent Relationship

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

A reconnecting Agent retains the same:

```text
agent_id
```

while establishing a new Session.

---

# 26. Task and Session Relationship

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

It does not redefine the identity or lifecycle of the Task.

A new Session is not a continuation of the old Session:

```text
S041 = DISCONNECTED
S042 = CONNECTED
```

while:

```text
agent_id = A001
task_id  = T001
```

remain unchanged.

---

# 27. Task and Result Relationship

A Task may produce a Result:

```text
T001
  │
  └── R001
```

The association is established through:

```text
result.task_id = task.task_id
```

The two entities have different responsibilities:

```text
Task
    → requested operation and lifecycle

Result
    → execution outcome/data
```

A Result may become available on the Agent before the C2 receives it.

A Result may therefore be recovered after the Task has already reached
`COMPLETED`.

---

# 28. Cancellation

Cancellation is an explicit lifecycle operation.

Examples that may eventually be supported include:

```text
PENDING → CANCELLED
QUEUED  → CANCELLED
```

Cancelling a `RUNNING` Task is more complex because safe interruption depends
on the operation being executed.

The system must not assume that every command can be remotely interrupted.

A cancellation request and successful cancellation are therefore distinct
concepts:

```text
cancellation requested
        ↓
Agent evaluates whether interruption is possible
        ↓
cancellation accepted
        ↓
CANCELLED
```

The exact cancellation semantics, including whether cancellation is
best-effort or guaranteed, remain to be finalized.

---

# 29. Retry and Redispatch

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
reconnection / synchronization
```

Redispatch is a separate decision and must consider duplicate-execution risk.

A retry of communication does not necessarily imply:

```text
Task → new Task
```

and redispatch does not automatically imply creation of a new `task_id`.

The exact retry count, backoff, and redispatch policy remain open.

---

# 30. Task Validation

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

Protocol-level rules are defined in `protocol.md`.

---

# 31. Task Lifecycle and Message Routing

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

The Task Manager remains responsible for Task domain state.

This separation prevents protocol handling from becoming the owner of domain
state.

---

# 32. Persistence

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

# 33. Runtime vs Persistent State

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

# 34. Logging and Traceability

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

Logging should provide enough information to reconstruct Task behavior without
unnecessarily exposing sensitive command parameters or Result data.

---

# 35. End-to-End Normal Flow

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
              execution starts
                     ▼
                  RUNNING
                     │
              execution succeeds
                     ▼
                COMPLETED
```

A Result may be produced as part of the successful execution path:

```text
RUNNING
   │
   ├── execution
   │
   └── Result R001 produced
              │
              ▼
          COMPLETED
```

With execution failure:

```text
RUNNING
   │
   ▼
FAILED
```

With final timeout:

```text
WAITING_ACK / RUNNING
          │
          │ recovery + timeout policy
          ▼
       TIMEOUT
```

---

# 36. Task Recovery Flow

The essential recovery principle is:

```text
             communication uncertainty
                       │
                       ▼
                obtain evidence
                       │
              ┌────────┴────────┐
              │                 │
        state available     state uncertain
              │                 │
              ▼                 ▼
       reconcile state      further recovery
                                │
                                ▼
                         possible redispatch
```

A Task is not redispatched simply because a communication message was lost.

The recovery process must consider whether the Task may already have been
accepted or executed.

Detailed cross-session recovery is defined in
`reconnection-and-synchronization.md`.

---

# 37. Architectural Invariants

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
TASK_STATUS = evidence about Agent-side Task state
```

### Unknown state

```text
UNKNOWN = recovery/reporting condition
UNKNOWN ≠ persistent Task state
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

### Session continuity

```text
Reconnection creates a new Session.
Task identity survives Session changes.
```

---

# 38. Relationship to Other Documents

| Document | Responsibility |
|---|---|
| `data-model.md` | Task entity, identifiers, relationships and persistence model |
| `state-machines.md` | Authoritative Task states and state transitions |
| `protocol.md` | Task-related protocol messages and fields |
| `protocol-state-transition.md` | Mapping protocol messages and evidence to state changes |
| `reconnection-and-synchronization.md` | Reconnection, synchronization and cross-side reconciliation |
| `file-transfer.md` | File-transfer lifecycle when a Task involves file exchange |
| `testing-strategy.md` | Verification of Task lifecycle and recovery behavior |
| `DECISIONS.md` | Final architectural decisions that resolve open questions |

This document should not duplicate the full protocol specification,
reconnection workflow, or general state-machine definitions.

Its focus is the **operational lifecycle of a Task and the recovery logic
specific to Task execution**.

---

# 39. Open Questions

The following details remain to be finalized:

- exact acknowledgement deadline;
- exact execution deadline;
- final timeout policy;
- retry count and backoff;
- redispatch conditions after `UNKNOWN`;
- maximum concurrent Tasks per Agent;
- Task scheduling and prioritization;
- cancellation semantics;
- whether running Tasks can be interrupted;
- exact duplicate Task handling;
- retention period/size for recent Task and Message identifiers;
- exact `TASK_STATUS` contents;
- Result retention and recovery mechanism;
- persistence requirements for each Task state;
- in-memory/persistent state consistency;
- whether every Task transition generates an Event;
- behavior after Agent or C2 restart;
- exact policy for Tasks that remain uncertain after repeated recovery attempts;
- exact conflict-resolution policy when Agent and C2 report different Task states.

Once these decisions are finalized, the corresponding architectural choices
should be recorded in `DECISIONS.md`.
