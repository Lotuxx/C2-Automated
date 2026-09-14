# Task Lifecycle

> **Status: Work in Progress**
>
> This document describes the current conceptual task model used by
> C2-AUTOMATED. The lifecycle, states, recovery mechanisms, and implementation
> details may evolve as the architecture and protocol are finalized.

---

## 1. Purpose

A **Task** represents an operation requested by the operator and intended for
execution by a specific agent.

The task system separates:

- task creation;
- task tracking;
- task queuing;
- task delivery;
- task acknowledgement;
- task execution;
- task status reporting;
- result handling;
- failure and timeout handling;
- task recovery.

This separation allows the C2 server to manage multiple agents and multiple
independent tasks without coupling the operator interface directly to a
single network operation.

The model is explicitly designed for **asynchronous multi-agent operation**.

---

## 2. Task Responsibility

The responsibility for a task is divided between the C2 server and the agent.

```text
C2 Server
    │
    ├── create task
    ├── track task
    ├── queue task
    ├── dispatch task
    ├── process acknowledgement
    ├── query task status when necessary
    └── process result
          │
          ▼
        Agent
          │
          ├── receive task
          ├── validate task
          ├── acknowledge task
          ├── queue task if necessary
          ├── execute task
          ├── report task status
          └── return result
```

The **C2 server manages the server-side task lifecycle**, while the
**agent is responsible for the actual processing and current runtime state of
its tasks**.

Neither side should assume that its local view of the other side's state is
always immediately synchronized.

---

## 3. Task vs Message vs Result

These concepts must remain distinct.

```text
Task
    = logical work requested by the C2

Message
    = one protocol communication unit carrying information

Result
    = outcome/data produced by an agent after processing a task
```

A single task can therefore generate several protocol messages:

```text
Task T001
    │
    ├── TASK
    ├── TASK_ACK
    ├── TASK_STATUS
    └── RESULT
```

The `task_id` identifies the logical work, while `message_id` identifies one
specific communication message.

A message such as `BEACON` does not represent a Task and must not cause the
C2 to create an artificial Task.

---

# 4. Task Structure

A Task is conceptually associated with the following information:

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
└── error
```

The exact data types and additional fields remain to be finalized.

### `task_id`

Unique logical identifier for the Task.

It is used to correlate:

- the Task;
- `TASK_ACK`;
- `TASK_STATUS_QUERY`;
- `TASK_STATUS`;
- `RESULT`;
- other task-related events.

### `agent_id`

Identifies the Agent to which the Task belongs.

A Task is always associated with one intended Agent.

### `command_type`

Identifies the operation that the Agent is expected to perform.

Examples include the project-defined commands such as:

```text
SHELL
SYSINFO
FILES
PERSISTENCE
SELF_DESTRUCT
```

### `parameters`

Contains the parameters required by the selected command.

Parameters must be validated before execution.

### Timestamps

Timestamps provide information about the Task lifecycle and support
tracking, timeout handling, troubleshooting, and logging.

The model distinguishes, where applicable:

```text
created_at
dispatched_at
acknowledged_at
started_at
completed_at
```

`dispatched_at` indicates when the C2 dispatched the Task.

`acknowledged_at` indicates when the C2 received `TASK_ACK`.

`started_at` indicates when the Agent reports that execution started.

### Deadlines

The model may include separate deadlines for:

```text
ack_deadline
execution_deadline
```

This allows communication timeout and execution timeout to be treated
separately.

### `status`

Represents the current lifecycle state of the Task.

---

# 5. Task States

The current conceptual lifecycle is:

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
                       ┌───┴────┐
                     ACK       timeout
                       │        │
                       ▼        ▼
                 ┌─────────┐  TIMEOUT
                 │ QUEUED  │
                 └────┬────┘
                      │
                agent starts
                      │
                      ▼
                 ┌─────────┐
                 │ RUNNING │
                 └────┬────┘
                    ┌─┴──┐
                    │    │
                 success failure
                    │    │
                    ▼    ▼
               COMPLETED FAILED
```

The current conceptual Task states are:

| State | Meaning |
|---|---|
| `PENDING` | Task has been created but has not yet been dispatched. |
| `WAITING_ACK` | Task has been dispatched and the C2 is waiting for the Agent to acknowledge it. |
| `QUEUED` | Agent has accepted the Task but has not started executing it yet. |
| `RUNNING` | Agent is currently executing the Task. |
| `COMPLETED` | Requested operation completed successfully. |
| `FAILED` | Requested operation was accepted or started but execution did not complete successfully. |
| `TIMEOUT` | Required communication or execution response was not received within the applicable deadline. |
| `CANCELLED` | Task was explicitly cancelled, where cancellation is supported. |

`CANCELLED` remains subject to the final cancellation design.

---

# 6. `PENDING`

A Task enters `PENDING` after it has been created by the C2 server.

```text
Operator
    │
    ▼
Interface
    │
    ▼
C2 Core
    │
    ▼
Task Manager
    │
    ▼
PENDING
```

At this stage, the Task exists logically but has not yet been dispatched.

A pending Task may remain in this state because:

- it has not yet been selected by the scheduler;
- the Agent is unavailable;
- the C2 is waiting for an appropriate communication opportunity;
- another scheduling condition prevents immediate dispatch.

---

# 7. `WAITING_ACK`

A Task enters `WAITING_ACK` after the C2 has dispatched it and is waiting for
confirmation from the Agent.

```text
Task Manager
    │
    ▼
Protocol
    │
    ▼
Transport
    │
    ▼
Agent
```

The conceptual transition is:

```text
PENDING
   │
   │ dispatch
   ▼
WAITING_ACK
```

`WAITING_ACK` means:

> The C2 has attempted to deliver the Task but does not yet have confirmation
> that the Agent accepted it.

It does **not** mean that the Task has failed.

It also does not mean that execution has completed.

---

# 8. `TASK_ACK`

The Agent responds to an accepted Task with:

```text
TASK_ACK
task_id = T001
```

The message is processed through the C2 message-routing layer:

```text
TASK_ACK(T001)
       │
       ▼
Message Router
       │
       ▼
Task Manager
       │
       ▼
Task state update
```

The acknowledgement means:

> The Agent received and accepted Task `T001`.

The acknowledgement is not itself the final execution result.

Depending on how the Agent schedules the Task, the next state may be:

```text
WAITING_ACK
      ↓
QUEUED
```

or, for an immediately executable Task:

```text
WAITING_ACK
      ↓
RUNNING
```

---

# 9. `QUEUED`

`QUEUED` represents an Agent-side state in which the Task has been accepted
but execution has not started yet.

For example:

```text
Agent A001
 ├── T001 → RUNNING
 ├── T002 → QUEUED
 └── T003 → QUEUED
```

This is useful because the project supports multiple Tasks associated with
the same Agent.

A Task may therefore follow:

```text
TASK
   ↓
TASK_ACK
   ↓
QUEUED
   ↓
RUNNING
```

However, a very fast or immediately executable Task may transition directly:

```text
TASK
   ↓
TASK_ACK
   ↓
RUNNING
```

The absence of a visibly long `QUEUED` period is therefore not an error.

---

# 10. `RUNNING`

A Task reaches `RUNNING` when the Agent reports that execution has started.

Conceptually:

```text
TASK
  │
  ▼
Protocol validation
  │
  ▼
Task acceptance / queue
  │
  ▼
Executor
  │
  ▼
Command Handler
  │
  ▼
Execution
```

The Executor is responsible for dispatching the Task to the appropriate
command implementation.

`RUNNING` belongs to the **Task**, not to the Agent.

For example:

```text
Agent A001
    agent_status = ALIVE
    activity_state = BUSY

Task T001
    status = RUNNING
```

---

# 11. `COMPLETED`

A Task reaches `COMPLETED` when the requested operation has successfully
finished.

The normal flow is:

```text
Command
   │
   ▼
Executor
   │
   ▼
Result
   │
   ▼
Agent Protocol
   │
   ▼
C2 Protocol
   │
   ▼
Result Manager
   │
   ▼
Task Manager
   │
   ▼
COMPLETED
```

A successful Task completion should therefore be traceable through its
corresponding Result.

---

# 12. `FAILED`

A Task enters `FAILED` when the Agent reports that the requested operation
could not be completed successfully.

Example:

```text
TASK T001
   ↓
TASK_ACK
   ↓
RUNNING
   ↓
RESULT
status = FAILURE
   ↓
FAILED
```

Potential causes include:

- command execution failure;
- command-specific error;
- invalid execution conditions;
- unavailable local resource;
- other implementation-defined execution failures.

Execution failure is distinct from communication timeout.

---

# 13. `TIMEOUT`

`TIMEOUT` is used when the C2 cannot obtain required communication or task
progress within the applicable deadline.

The project distinguishes timeout from execution failure.

### Acknowledgement timeout

```text
WAITING_ACK
      │
      │ no TASK_ACK
      ▼
TIMEOUT / recovery procedure
```

### Execution timeout

```text
RUNNING
   │
   │ no completion within execution deadline
   ▼
TIMEOUT
```

A timeout therefore means:

> The C2 did not obtain the expected information within the defined period.

It does **not necessarily prove that the Task never executed**.

---

# 14. Task and Agent State Are Independent

Task state must not be confused with Agent health.

For example:

```text
Agent A001
    agent_status = ALIVE
    activity_state = BUSY

Task T001
    status = RUNNING
```

Or:

```text
Agent A001
    agent_status = LIKELY_DEAD
    activity_state = UNKNOWN

Task T001
    status = RUNNING
```

The second case means that the C2 has not established the final outcome of
T001 even though communication with A001 has become uncertain.

This separation is essential to the asynchronous model.

---

# 15. Task Queue

The C2 server must be able to manage several Tasks independently.

Conceptually:

```text
TASK QUEUES

A001 → [T004, T005]
A002 → [T006]
A003 → []
```

On the Agent side, several Tasks may also be maintained:

```text
A001
 ├── T004 → RUNNING
 ├── T005 → QUEUED
 └── T006 → QUEUED
```

The queue is logically associated with Agents so that a Task intended for one
Agent is not accidentally dispatched to another.

The exact queue implementation and scheduling mechanism have not yet been
finalized.

---

# 16. Asynchronous Task Handling

The task system is explicitly designed around asynchronous multi-agent
operation.

The intended model is not:

```text
Operator
   ↓
send command
   ↓
wait for completion
   ↓
receive result
```

for every interaction.

Instead:

```text
Operator
   ↓
Create Task
   ↓
PENDING
   ↓
Queue / Dispatch
   ↓
Agent
```

The C2 server remains able to manage other Agents and Tasks while an
individual Task is being processed.

Conceptually:

```text
                 C2 SERVER
                     │
          ┌──────────┼──────────┐
          ▼          ▼          ▼
        A001       A002       A003
         │          │          │
      T001/T002     T003     T004/T005
```

One Agent's Task processing must not block unrelated Tasks belonging to other
Agents.

The exact concurrency and scheduling mechanism remains to be defined.

---

# 17. Task and Agent Relationship

Every Task is intended for a specific Agent.

```text
Agent A001
   │
   ├── Task T001
   ├── Task T002
   └── Task T003

Agent A002
   │
   └── Task T004
```

The `agent_id` therefore provides the authoritative association between the
Task and its intended Agent.

---

# 18. Task and Result Relationship

A Task may produce a corresponding Result.

```text
Agent
   │
   └── Task T004
          │
          └── Result R009
```

The `task_id` allows the C2 server to associate a returned Result with the
correct Task.

This provides traceability:

```text
Operator Request
      ↓
Task
      ↓
Agent Execution
      ↓
Result
```

A Result may arrive after an arbitrary communication delay because the
architecture is asynchronous.

The exact Task/Result cardinality and persistence rules remain part of the
data-model design.

---

# 19. Task / Protocol Interaction

A Task is an application-level object.

The protocol defines how that Task is represented during communication.

Conceptually:

```text
Task Object
     │
     ▼
TASK Message
     │
     ▼
Transport
     │
     ▼
Agent
```

The same Task may subsequently generate:

```text
TASK_ACK
TASK_STATUS
RESULT
```

The logical Task should remain independent from the transport mechanism.

Changing the transport should therefore not require redesigning the Task
lifecycle.

---

# 20. Task Status Queries

The protocol provides:

```text
TASK_STATUS_QUERY
TASK_STATUS
```

These messages are particularly useful when the C2 is uncertain about the
state of a Task.

For example:

```text
C2
 │
 │ TASK_STATUS_QUERY(T001)
 ▼
Agent
 │
 │ TASK_STATUS(T001, QUEUED)
 ▼
C2
```

Possible returned states include:

```text
QUEUED
RUNNING
COMPLETED
FAILED
UNKNOWN
```

A completed status may include the corresponding `result_id`:

```text
TASK_STATUS
├── task_id = T001
├── status = COMPLETED
└── result_id = R001
```

This allows the C2 to recover knowledge of a completed Task after losing a
Result message.

---

# 21. Task Recovery After a Missing ACK

The C2 must not blindly resend a Task when its acknowledgement is missing.

For example:

```text
TASK T001
   ↓
WAITING_ACK
   ↓
ACK timeout
```

The preferred recovery sequence is:

```text
WAITING_ACK
      │
      │ timeout
      ▼
     PING
      │
 ┌────┴─────┐
 │          │
PONG      no PONG
 │          │
 ▼          ▼
Agent      agent
reachable  unavailable / retry check
 │
 ▼
TASK_STATUS_QUERY(T001)
```

`PING/PONG` answers:

> Can the C2 communicate with the Agent right now?

`TASK_STATUS_QUERY` answers:

> What is the current state of this particular Task?

These are deliberately different questions.

---

# 22. `PING/PONG` and Task Recovery

The recovery logic is therefore:

```text
T001 = WAITING_ACK
        │
        │ ACK timeout
        ▼
      PING
       /  \
     PONG  no PONG
      │       │
      │       ▼
      │   availability issue
      │
      ▼
TASK_STATUS_QUERY(T001)
      │
      ▼
┌──────────┬─────────┬───────────┬─────────┐
│          │         │           │
QUEUED   RUNNING  COMPLETED   UNKNOWN
│          │         │           │
└──────────┴─────────┘           │
                                 ▼
                         possible re-dispatch
```

Only after the Agent reports `UNKNOWN` should re-dispatch become a possible
decision.

The exact retry policy remains to be defined.

---

# 23. Lost ACK Scenario

Example:

```text
C2                              Agent

TASK T001
 ───────────────────────────────►

                                accepts T001

TASK_ACK
 ◄────────────── X lost
```

The C2 still has:

```text
T001 = WAITING_ACK
```

After the acknowledgement deadline:

```text
C2 → PING
```

Agent:

```text
Agent → PONG
```

The C2 now knows the Agent is reachable.

It then asks:

```text
C2 → TASK_STATUS_QUERY(T001)
```

The Agent may respond:

```text
TASK_STATUS
task_id = T001
status = QUEUED
```

The C2 can therefore update its model without re-executing T001.

---

# 24. Lost Result Scenario

A Task may complete even if its result message is lost.

```text
TASK T001
   ↓
TASK_ACK
   ↓
RUNNING
   ↓
RESULT(T001)
      X lost
```

The C2 may still believe:

```text
T001 = RUNNING
```

It can recover the state through:

```text
PING
 ↓
PONG
 ↓
TASK_STATUS_QUERY(T001)
 ↓
TASK_STATUS(COMPLETED, R001)
```

The C2 now knows that the Task completed.

This prevents unnecessary re-execution.

The exact mechanism used to recover the missing Result data remains to be
defined.

---

# 25. Duplicate Task Handling

Communication retries can cause the same logical Task or Message to appear
more than once.

The implementation must therefore distinguish:

```text
task_id
    → identity of the logical Task

message_id
    → identity of one protocol Message
```

For example:

```text
TASK
message_id = M100
task_id = T001
```

If the same message is received twice:

```text
M100 TASK T001
M100 TASK T001
```

the Agent can detect that the same communication message was already
processed.

The Agent should maintain bounded recent history such as:

```text
recent_task_ids
recent_message_ids
```

This history should not grow indefinitely.

The exact retention size remains an implementation decision.

---

# 26. Why Blind Task Retransmission Is Avoided

Consider:

```text
C2 → TASK T001
Agent → accepts and executes T001
Agent → TASK_ACK
          X lost
```

If the C2 immediately sends T001 again:

```text
C2 → TASK T001
Agent → executes T001 again
```

the same logical operation may be executed twice.

Therefore:

> **A missing acknowledgement is a communication uncertainty, not proof that
> the Task was never received.**

The C2 should use liveness and task-status mechanisms before considering
redispatch.

---

# 27. Task Validation

Tasks received by the Agent must be validated before execution.

Conceptually:

```text
Received TASK
      │
      ▼
Protocol Validation
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
Command
```

Validation requirements are specified more precisely in
[`protocol.md`](protocol.md).

Command-specific parameter validation should also occur at the appropriate
command or execution boundary.

---

# 28. Message Routing and Task Lifecycle

Incoming messages do not go directly to the Task Manager without first being
classified.

The C2 uses a Message Router:

```text
Incoming Message
       │
       ▼
Message Router
       │
       ├── TASK_ACK
       │      ↓
       │   TaskManager
       │
       ├── TASK_STATUS
       │      ↓
       │   TaskManager
       │
       ├── RESULT
       │      ↓
       │   ResultManager
       │      ↓
       │   TaskManager
       │
       ├── BEACON
       │      ↓
       │   AgentManager / SessionManager
       │
       └── PONG
              ↓
          Session / health handling
```

This keeps communication routing separate from ownership of domain state.

---

# 29. Failure and Recovery

Relevant failure situations include:

```text
Agent unavailable
Communication interrupted
TASK_ACK not received
TASK_STATUS not received
Task timeout
Invalid task
Execution failure
Malformed result
Unexpected result
Unknown task
Duplicate task
Duplicate result
Lost result message
```

These cases must not all be treated as the same failure.

The most important distinction is:

```text
Communication problem
        ≠
Execution failure
```

For example:

```text
WAITING_ACK → TIMEOUT
```

does not prove that execution failed.

Whereas:

```text
RUNNING
   ↓
RESULT(FAILURE)
   ↓
FAILED
```

does.

---

# 30. Cancellation

Task cancellation is conceptually supported as a possible lifecycle operation.

For example:

```text
PENDING
   ↓
CANCELLED
```

or:

```text
QUEUED
   ↓
CANCELLED
```

Whether a running Task can be safely interrupted remains to be defined.

The project must not assume that every running operation can be remotely
terminated until this behaviour is explicitly implemented and tested.

---

# 31. Retry Behaviour

Retries are not equivalent to task recreation.

The system should distinguish:

```text
communication retry
```

from:

```text
task re-dispatch
```

A communication retry may involve checking availability:

```text
PING
   ↓
PONG
```

or querying state:

```text
TASK_STATUS_QUERY
   ↓
TASK_STATUS
```

A task re-dispatch must only be considered when the system has enough
information to avoid unnecessary duplicate execution.

The exact number of retries and retry policy remain open.

---

# 32. Persistence

The task system is expected to persist relevant Task information through the
C2 storage layer.

Conceptually:

```text
Task Manager
     │
     ▼
Database Interface
     │
     ▼
SQLite
```

Persistent task information may include:

```text
task_id
agent_id
command_type
parameters
status
timestamps
deadlines
result association
error
```

The exact persistence rules for each lifecycle state remain to be defined.

---

# 33. In-Memory and Persistent State

The C2 may maintain active Task information in memory for efficient runtime
processing while persisting the authoritative Task history.

Conceptually:

```text
Runtime Task State
      │
      ├── active queue
      ├── current status
      └── timeout tracking
      │
      ▼
Persistent Task Record
      │
      └── historical state
```

The exact synchronization strategy between in-memory and persistent state
remains to be defined.

---

# 34. Logging and Traceability

Task-related events should be logged through the centralized logging
component.

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
Task timed out
Task cancellation
TASK_STATUS_QUERY sent
Result received
Unmatched result detected
```

Logging should provide useful operational information without unnecessarily
exposing sensitive data.

---

# 35. Agent Runtime Information

The Agent should maintain enough lightweight runtime information to answer
task-related queries and detect duplicates.

Conceptually:

```text
Agent Runtime State
├── agent_id
├── current_task_id
├── queued_task_ids
├── last_task_id
├── last_result_id
├── last_message_id
├── last_ack
├── last_beacon
└── recent task/message IDs
```

The recent history should remain bounded.

The Agent does not need to retain an unlimited history in memory.

---

# 36. Relationship with Agent Health

Task recovery may depend on the Agent health state.

The Agent maintains a separate health dimension:

```text
agent_status
    UNKNOWN
    ALIVE
    LIKELY_DEAD
    TERMINATED
```

while activity is represented separately:

```text
activity_state
    IDLE
    BUSY
```

This allows situations such as:

```text
Agent A001
├── agent_status = ALIVE
├── activity_state = BUSY
└── current_task_id = T001
```

or:

```text
Agent A001
├── agent_status = LIKELY_DEAD
├── activity_state = UNKNOWN
└── current_task_id = T001
```

The Agent health model is therefore not part of the Task state machine.

---

# 37. Current End-to-End Task Flow

The current normal flow can be summarized as:

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
                     │ dispatch
                     ▼
                WAITING_ACK
                     │
                     │ TASK
                     ▼
               PROTOCOL / TLS
                     │
                     ▼
                   AGENT
                     │
                     │ TASK_ACK
                     ▼
                  QUEUED
                     │
                     │ start
                     ▼
                  RUNNING
                     │
                     │ RESULT
                     ▼
               RESULT MANAGER
                     │
                     ▼
               TASK MANAGER
                     │
                     ▼
                 COMPLETED
```

For an immediate task:

```text
PENDING
   ↓
WAITING_ACK
   ↓
RUNNING
   ↓
COMPLETED
```

For a delayed task:

```text
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

# 38. Recovery Flow

The current recovery model is:

```text
                     TASK
                       │
                       ▼
                  WAITING_ACK
                       │
                  ACK timeout
                       │
                       ▼
                     PING
                    /    \
                 PONG    no PONG
                  │          │
                  ▼          ▼
        TASK_STATUS_QUERY   availability
                  │          problem
                  ▼
       ┌──────────┼────────────┐
       │          │            │
    QUEUED     RUNNING      COMPLETED
       │          │            │
       └──────────┴────────────┘
                    │
                 continue
```

If the Agent reports:

```text
UNKNOWN
```

then re-dispatch may be considered according to the final retry policy.

---

# 39. Current Design Summary

The task architecture can be summarized as:

```text
Task
 │
 ├── created by C2
 │
 ├── PENDING
 │
 ├── WAITING_ACK
 │       │
 │       ├── timeout → recovery
 │       │
 │       └── TASK_ACK
 │
 ├── QUEUED
 │
 ├── RUNNING
 │       │
 │       ├── success → COMPLETED
 │       ├── failure → FAILED
 │       └── deadline → TIMEOUT
 │
 └── optional CANCELLED
```

The important protocol interactions are:

```text
TASK
   ↓
TASK_ACK
   ↓
TASK_STATUS
   ↓
RESULT
```

where `TASK_STATUS` may be queried when the C2 needs to recover from
communication uncertainty.

The health mechanisms are separate:

```text
BEACON
    → normal periodic check-in

PING/PONG
    → immediate liveness check
```

---

# 40. Architectural Principles

The following principles should remain stable as implementation progresses:

### Task is a logical object

A Task is not the same thing as the protocol message used to transport it.

### One Task may produce several Messages

```text
T001
 ├── TASK
 ├── TASK_ACK
 ├── TASK_STATUS
 └── RESULT
```

### Task state is independent from Agent health

```text
Task state
    ≠
Agent status
```

### Communication failure is not execution failure

```text
TIMEOUT
    ≠
FAILED
```

### Missing ACK does not imply missing execution

The C2 should query Agent/task state before blindly redispatching.

### `PING/PONG` and `BEACON` are complementary

```text
BEACON
    → periodic agent check-in

PING/PONG
    → active immediate liveness check
```

### `task_id` and `message_id` have different purposes

```text
task_id
    → logical Task identity

message_id
    → individual protocol message identity
```

### Agent history remains bounded

The Agent should retain only enough recent information for status queries and
duplicate detection.

---

# 41. Open Questions

The following points remain to be finalized:

- exact timeout durations;
- acknowledgement deadline policy;
- execution deadline policy;
- maximum number of communication retries;
- exact re-dispatch rules after `UNKNOWN`;
- whether `TASK_ACK` always leads directly to `QUEUED` or may lead directly to
  `RUNNING`;
- whether multiple Tasks may execute concurrently on a single Agent;
- task scheduling and prioritization;
- cancellation semantics;
- exact duplicate Task handling;
- exact duplicate Message handling;
- recent Task/Message history size;
- result recovery after a lost Result;
- persistence rules for each lifecycle state;
- synchronization between in-memory and persistent Task state;
- exact `TASK_STATUS` contents;
- whether every state change generates `TASK_STATUS` or only selected changes.

When these decisions are finalized, the relevant architectural or project
decisions should be recorded in [`DECISIONS.md`](../DECISIONS.md), and this
document should remain synchronized with [`protocol.md`](protocol.md),
[`data-model.md`](data-model.md), and [`testing-strategy.md`](testing-strategy.md).
