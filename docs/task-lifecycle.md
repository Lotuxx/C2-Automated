# Task Lifecycle

> **Status: Work in Progress**
>
> This document describes the current conceptual task model used by
> C2-AUTOMATED. The lifecycle, states, and implementation details may evolve
> as the architecture and protocol are finalized.

---

## 1. Purpose

A **task** represents an operation requested by the operator and intended for
execution by a specific agent.

The task system separates:

- task creation;
- task tracking;
- task delivery;
- task execution;
- result handling.

This separation allows the C2 server to manage multiple agents and multiple
independent tasks without coupling the operator interface directly to a
single network operation.

---

## 2. Task Responsibility

The responsibility for a task is divided between the C2 server and the agent.

```text
C2 Server
    │
    ├── create task
    ├── track task
    ├── dispatch task
    └── process result
          │
          ▼
        Agent
          │
          ├── receive task
          ├── validate task
          ├── execute task
          └── return result
```

The **C2 server manages the task lifecycle**, while the **agent performs the
requested operation**.

---

# 3. Task Structure

A task is conceptually associated with the following information:

```text
Task
├── task_id
├── agent_id
├── command_type
├── parameters
├── created_at
├── sent_at
├── completed_at
└── status
```

The exact data types and additional fields remain to be defined.

### `task_id`

Unique identifier for the task.

### `agent_id`

Identifies the agent to which the task belongs.

### `command_type`

Identifies the operation that the agent is expected to perform.

### `parameters`

Contains the parameters required by the selected command.

### Timestamps

Timestamps provide information about the task lifecycle and help with
tracking and troubleshooting.

### `status`

Represents the current lifecycle state of the task.

---

# 4. Task States

The current conceptual task lifecycle is:

```text
              ┌─────────┐
              │ PENDING │
              └────┬────┘
                   │
                   ▼
                 SENT
                   │
                   ▼
                RUNNING
                /     \
               /       \
              ▼         ▼
         COMPLETED     FAILED
```

The states currently defined are:

| State | Meaning |
|---|---|
| `PENDING` | Task has been created but has not yet been successfully dispatched to the agent. |
| `SENT` | Task has been dispatched by the C2 server. |
| `RUNNING` | Agent has accepted the task and is executing the operation. |
| `COMPLETED` | The requested operation completed successfully. |
| `FAILED` | The operation could not be completed successfully. |

The exact transition conditions remain part of the implementation design.

---

# 5. `PENDING`

A task enters the `PENDING` state after it has been created by the C2 server.

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

At this stage, the task exists logically but has not yet completed its
delivery to the target agent.

A pending task may therefore remain queued until the appropriate
communication opportunity is available.

---

# 6. `SENT`

A task moves to `SENT` when the C2 server dispatches it through the
communication layer.

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

The exact definition of "sent" versus "received" remains to be finalized in
the protocol and session design.

---

# 7. `RUNNING`

The task reaches `RUNNING` when the agent has accepted the task and started
its execution.

The agent-side flow is:

```text
TASK
  │
  ▼
Protocol validation
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

The Executor is responsible for dispatching the task to the appropriate
command implementation.

---

# 8. `COMPLETED`

A task reaches `COMPLETED` when the requested operation has successfully
finished.

The agent produces a result that can be associated with the originating task.

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
C2 Result Manager
```

A successful task completion should therefore be traceable through the
corresponding result.

---

# 9. `FAILED`

A task enters `FAILED` when the requested operation cannot be completed
successfully.

Potential causes include:

- execution failure;
- communication failure;
- invalid task parameters;
- unavailable agent;
- timeout;
- other implementation-defined errors.

The current model groups these outcomes under `FAILED`.

More detailed failure states may be introduced if required later.

---

# 10. Task Queue

The C2 server must be able to manage several tasks independently.

Conceptually:

```text
TASK QUEUE

A001 → [T004, T005]
A002 → [T006]
A003 → []
```

The queue is logically associated with agents so that a task intended for one
agent is not accidentally dispatched to another.

The exact queue implementation has not yet been finalized.

---

# 11. Asynchronous Task Handling

The task system is designed around asynchronous multi-agent operation.

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
Task = PENDING
   ↓
Queue / Dispatch
   ↓
Agent
```

The C2 server remains able to manage other agents and tasks while an
individual task is being processed.

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

The exact concurrency and scheduling mechanism remains to be defined.

---

# 12. Task and Agent Relationship

Every task is intended for a specific agent.

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

The `agent_id` therefore provides an important association between the task
and the agent responsible for executing it.

---

# 13. Task and Result Relationship

A task may produce a corresponding result.

```text
Agent
   │
   └── Task T004
          │
          └── Result R009
```

The `task_id` allows the C2 server to associate the returned result with the
correct task.

This provides traceability from:

```text
Operator Request
      ↓
Task
      ↓
Agent Execution
      ↓
Result
```

The exact cardinality and persistence rules are part of the data-model
design.

---

# 14. Task / Protocol Interaction

A task is an application-level object, while the protocol defines how that
task is represented on the network.

Conceptually:

```text
Task Object
     │
     ▼
Protocol Message
     │
     ▼
Transport
     │
     ▼
Agent
```

The logical task should therefore remain independent from the network
transport.

For example, changing the transport should not require redesigning the
task lifecycle.

---

# 15. Task Validation

Tasks received by the agent must be validated before execution.

Conceptually:

```text
Received TASK
      │
      ▼
Protocol Validation
      │
      ├── invalid → reject
      │
      ▼
Executor
      │
      ▼
Command
```

Validation requirements will be specified more precisely in
[`protocol.md`](protocol.md).

Command-specific parameter validation is also expected to occur at the
appropriate command or execution boundary.

---

# 16. Failure and Recovery

The final implementation must define how the task system behaves when
something goes wrong.

Relevant situations include:

```text
Agent unavailable
Communication interrupted
Task timeout
Invalid task
Execution failure
Malformed result
Unexpected result
Duplicate result
```

The current architecture only establishes the principal `FAILED` outcome.
More detailed states or recovery mechanisms may be introduced later.

Potential future distinctions could include:

```text
FAILED
TIMEOUT
CANCELLED
REJECTED
```

These are currently **not** part of the finalized task state machine.

---

# 17. Cancellation and Retry

Cancellation and retry behaviour have not yet been finalized.

Possible future questions include:

- Can a pending task be cancelled?
- Can a sent task be cancelled before execution?
- Should failed communication automatically retry?
- How many retries are allowed?
- Should retries create a new task or reuse the same task identifier?
- What happens when the agent reconnects with tasks still pending?

These questions should be resolved before the task manager implementation is
considered complete.

---

# 18. Persistence

The task system is expected to persist relevant task information through the
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
status
timestamps
result association
```

The exact persistence rules for each lifecycle state remain to be defined.

---

# 19. Logging and Traceability

Task-related events should be logged through the centralized logging
component.

Examples include:

```text
Task created
Task dispatched
Task execution started
Task completed
Task failed
Result received
```

Logging should provide useful operational information without unnecessarily
exposing sensitive data.

---

# 20. Current Design Summary

The current task architecture can be summarized as:

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
                     ▼
                   SENT
                     │
                     ▼
               PROTOCOL / TLS
                     │
                     ▼
                   AGENT
                     │
                     ▼
                 EXECUTOR
                     │
                     ▼
                  COMMAND
                     │
                     ▼
                  RESULT
                     │
                     ▼
               RESULT MANAGER
                     │
                     ▼
               TASK COMPLETED
```

The central architectural principle is:

> **A task is a tracked application object whose lifecycle is independent from
> the underlying communication mechanism and whose execution occurs on a
> specific agent.**

---

# 21. Open Questions

The following points remain open and should be finalized during detailed
design:

- exact task state machine;
- precise `SENT` and `RUNNING` transition conditions;
- task queue implementation;
- scheduling strategy;
- timeout semantics;
- retry behaviour;
- cancellation behaviour;
- duplicate task handling;
- duplicate result handling;
- persistence rules;
- task/result cardinality;
- exact protocol representation of a task;
- synchronization between in-memory task state and persistent state.

When these questions are resolved, the relevant decisions should be recorded
in [`DECISIONS.md`](../DECISIONS.md) and the finalized behaviour reflected
in this document.
