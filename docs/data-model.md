# Data Model

> **Status: Work in Progress**
>
> This document describes the current conceptual data model of
> C2-AUTOMATED. Entity fields, relationships, persistence rules, and
> implementation details may evolve as the architecture and protocol are
> finalized.
>
> The model intentionally separates **domain entities**, **communication
> sessions**, **protocol messages**, **operational events**, and **physical
> storage**.

---

# 1. Purpose

C2-AUTOMATED uses several central entities to represent agents,
communication sessions, tasks, results, messages, file transfers, and
operational events.

The purpose of this document is to define the **conceptual relationships**
between these entities before the final implementation and database schema
are established.

The current primary entities are:

```text
Agent
Session
Task
Result
Message
File Transfer
Event
```

These entities exist at the application level. Their exact representation in
Python classes, database models, protocol structures, or runtime objects may
differ.

A key architectural principle is:

```text
Agent
    → persistent identity

Session
    → communication instance

Task
    → requested operation

Result
    → execution output

Message
    → protocol-level communication unit

File Transfer
    → logical file movement

Event
    → operational occurrence
```

---

# 2. Domain Overview

The current conceptual model can be summarized as:

```text
                         ┌────────────┐
                         │   Agent    │
                         └─────┬──────┘
                               │
                    ┌──────────┴──────────┐
                    │                     │
                    ▼                     ▼
              ┌───────────┐        ┌───────────┐
              │  Session  │        │    Task   │
              └───────────┘        └─────┬─────┘
                                         │
                                         ▼
                                   ┌───────────┐
                                   │  Result   │
                                   └───────────┘

                         Agent
                           │
                           ▼
                    ┌─────────────┐
                    │File Transfer│
                    └─────────────┘
```

Operational events are associated with system activity:

```text
Agent / Session / Task / Result / File Transfer
                         │
                         ▼
                       Event
```

Protocol messages transport information related to these entities:

```text
Application Entity / Event
          │
          ▼
   Protocol Message
          │
          ▼
       Transport
```

A message is therefore **not equivalent to the domain object it represents**.

---

# 3. Agent

An **Agent** represents the persistent identity of an endpoint running the
agent software.

An agent is not equivalent to a network connection. Its identity is intended
to remain stable across communication sessions.

Conceptually:

```text
Agent
├── identity
│   ├── agent_id
│   ├── hostname
│   ├── operating_system
│   └── architecture
│
├── health
│   ├── agent_status
│   ├── first_seen
│   ├── last_seen
│   ├── last_beacon
│   ├── last_ping
│   └── last_pong
│
├── session
│   ├── session_id
│   └── session_status
│
├── activity
│   ├── activity_state
│   ├── current_task_id
│   └── queued_task_count
│
└── history
    └── last_result_id
```

The exact persistent schema remains to be finalized.

## 3.1 Agent Identity

`agent_id` uniquely identifies the agent from the C2 server's perspective.

The identity mechanism itself has not yet been finalized.

The identity must remain independent from:

```text
session_id
message_id
task_id
```

A new communication session therefore does not create a new logical agent.

---

## 3.2 Agent Health State

The current conceptual health model is:

```text
UNKNOWN
   │
   ▼
 ALIVE
   │
   └──────────────┐
                  ▼
            LIKELY_DEAD
                  │
                  │ communication resumes
                  ▼
                ALIVE
```

The states are interpreted as:

### `UNKNOWN`

The C2 does not yet have sufficient information to establish the current
health of the agent.

### `ALIVE`

The C2 has recent evidence that communication with the agent is possible.

### `LIKELY_DEAD`

The agent has stopped communicating within the expected conditions and is
considered probably unavailable.

This state is deliberately probabilistic. The absence of communication does
not prove that the process or host has been terminated.

### `TERMINATED`

Where supported, this represents an explicitly confirmed termination of the
agent, for example after a controlled self-destruction operation.

It must not be inferred solely from a communication timeout.

---

## 3.3 Agent Activity State

Agent health and agent activity are distinct concepts.

The current activity model is:

```text
IDLE
BUSY
```

For example:

```text
Agent status:     ALIVE
Activity state:   BUSY
Current task:     T001
```

The value `RUNNING` belongs to the **Task** state machine, not to the Agent
activity model.

This distinction allows the system to represent situations such as:

```text
Agent = ALIVE
Activity = BUSY
Task T001 = RUNNING
Task T002 = QUEUED
Task T003 = QUEUED
```

---

## 3.4 Agent Runtime Information

The agent may maintain lightweight runtime information such as:

```text
agent_id
current_state
current_task_id
queued_task_ids
last_task_id
last_result_id
last_message_id
last_ack
last_beacon
recent_task_ids
recent_message_ids
```

Recent identifiers should be bounded rather than retained indefinitely in
memory.

This state is useful for:

- task deduplication;
- message deduplication;
- task recovery;
- tracking the currently executing operation;
- responding to status queries.

---

# 4. Session

A **Session** represents a communication instance associated with an Agent.

The architectural distinction is:

> **Agent = persistent identity**
>
> **Session = communication instance**

Conceptually:

```text
Agent A001
    │
    ├── Session S01
    │     └── DISCONNECTED
    │
    └── Session S02
          └── CONNECTED
```

An agent can therefore have multiple sessions over its lifetime.

---

## 4.1 Session Information

A session may contain information such as:

```text
session_id
agent_id
session_status
transport
created_at
last_activity
```

The current conceptual session states are:

```text
CONNECTING
     │
     ▼
 CONNECTED
     │
     ▼
DISCONNECTED
```

The exact persistence strategy remains to be finalized.

---

## 4.2 Session and Agent Relationship

Conceptually:

```text
One Agent
    │
    └── multiple Sessions over time
```

The cardinality is therefore:

```text
Agent 1 ─── * Session
```

A session should not replace or redefine the persistent identity of the
agent.

---

## 4.3 Session vs Agent Health

Session status and Agent health are deliberately independent.

For example:

```text
Agent health      = ALIVE
Session status    = DISCONNECTED
```

may occur when the agent is known to exist and communicate periodically but
does not currently have an active communication session.

Similarly, a session being connected provides evidence of communication but
does not by itself define the complete historical health state of the agent.

---

# 5. Liveness Information

The model explicitly distinguishes two mechanisms for determining
communication availability.

## 5.1 Beacon

`BEACON` is the agent's normal periodic check-in.

Conceptually:

```text
Agent
  │
  │ periodic BEACON
  ▼
 C2
```

A beacon may provide lightweight status information such as:

```text
agent activity
current task
queued task count
last task
last result
```

The exact beacon payload remains to be finalized.

The corresponding information may update:

```text
last_seen
last_beacon
agent_status
activity_state
```

---

## 5.2 Ping / Pong

`PING/PONG` is an active liveness mechanism initiated by the C2.

```text
C2
 │
 │ PING
 ▼
Agent
 │
 │ PONG
 ▼
C2
```

Conceptually:

```text
PING
    → "Can communication with this agent succeed now?"

PONG
    → "The agent received the ping and responded now."
```

A `PONG` therefore proves **immediate communication**, but does not by itself
synchronize the task state or result state.

This is different from `BEACON`:

```text
BEACON
→ passive periodic check-in

PING/PONG
→ active immediate communication check
```

Both mechanisms therefore have distinct roles in the model.

---

# 6. Task

A **Task** represents an operation requested for a specific agent.

The C2 server creates and manages tasks while the agent performs them.

Conceptually:

```text
Task
├── task_id
├── agent_id
├── command_type
├── parameters
├── status
├── created_at
├── dispatched_at
├── acknowledged_at
├── started_at
├── completed_at
├── ack_deadline
├── execution_deadline
└── error
```

The detailed task lifecycle is documented in
[`task-lifecycle.md`](task-lifecycle.md).

---

## 6.1 Task Ownership

A task belongs logically to one target agent.

```text
Agent A001
   │
   ├── Task T001
   ├── Task T002
   └── Task T003
```

Another agent has independent tasks:

```text
Agent A002
   │
   └── Task T004
```

The relationship is therefore:

```text
Agent 1 ─── * Task
```

---

## 6.2 Task State

The current conceptual task states are:

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
  /   \
 ▼     ▼
COMPLETED  FAILED
```

`TIMEOUT` and `CANCELLED` are terminal or operational outcomes supported by
the model:

```text
TIMEOUT
CANCELLED
```

The important distinction is:

```text
Task state
≠
Agent health
≠
Session status
```

---

## 6.3 `WAITING_ACK`

`WAITING_ACK` represents a task that the C2 has dispatched and for which it
is waiting for an explicit acknowledgement.

It is therefore different from:

```text
QUEUED
RUNNING
```

because the C2 has not yet established that the agent accepted the task.

---

## 6.4 `TASK_ACK`

A `TASK_ACK` indicates:

> The agent received and accepted the task.

It does not necessarily mean that execution has already started.

Therefore:

```text
TASK_ACK
   │
   ▼
QUEUED
```

is a valid transition.

For an immediately executable task:

```text
TASK_ACK
   │
   ▼
RUNNING
```

may also be valid.

---

## 6.5 Communication Uncertainty

Failure to receive an ACK does not automatically mean task execution failed.

The model explicitly distinguishes:

```text
communication failure
        ≠
task execution failure
```

For example:

```text
C2 dispatches T001
       │
       ▼
WAITING_ACK
       │
       │ ACK lost?
       ▼
communication uncertainty
```

The C2 should therefore avoid blindly dispatching the task again.

The recovery model is:

```text
WAITING_ACK
      │
      │ ACK timeout
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

The result may indicate:

```text
QUEUED
RUNNING
COMPLETED
FAILED
UNKNOWN
```

Only when the task is explicitly determined to be `UNKNOWN` may
red-dispatch be considered according to the retry policy.

---

# 7. Result

A **Result** represents the outcome or data returned after a task has been
processed.

Conceptually:

```text
Result
├── result_id
├── task_id
├── agent_id
├── status
├── timestamp
└── data
```

A result is associated with the task that produced it.

```text
Agent
  │
  └── Task T004
        │
        └── Result R009
```

The relationship is conceptually:

```text
Task 1 ─── 0..1 / *
```

depending on the final execution/result model.

The model therefore keeps the cardinality deliberately open.

---

## 7.1 Result Identification

`result_id` identifies a specific result independently from:

```text
task_id
message_id
agent_id
```

For a normal result:

```text
RESULT
├── agent_id = A001
├── task_id = T004
└── result_id = R009
```

This permits a result to be referenced later without confusing it with the
message that transported it.

---

## 7.2 Result and Task Relationship

The traceability chain is:

```text
Operator Request
      ↓
    Task
      ↓
Agent Execution
      ↓
   Result
      ↓
Operator
```

A result should therefore normally reference the task from which it
originated.

If the C2 receives a result referencing an unknown task, it should not create
a fabricated task simply to satisfy the relationship.

Such a result should instead be handled as an unmatched/orphan result and
logged appropriately.

---

# 8. Message

A **Message** represents a protocol-level unit exchanged between the C2
server and an agent.

A conceptual message envelope is:

```text
Message
├── version
├── message_id
├── agent_id
├── session_id?
├── task_id?
├── result_id?
├── transfer_id?
├── type
├── timestamp
└── payload
```

The exact wire representation is defined separately in
[`protocol.md`](protocol.md).

The message is not itself equivalent to the domain object represented inside
its payload.

For example:

```text
Task
  ↓
TASK Message
  ↓
Transport
```

and:

```text
Result
  ↓
RESULT Message
  ↓
Transport
```

---

## 8.1 Message Identity

`message_id` identifies one specific protocol message.

This is different from `task_id`.

For example, one logical task may generate:

```text
T001
 ├── M100 TASK
 ├── M101 TASK_ACK
 ├── M102 TASK_STATUS
 └── M103 RESULT
```

Therefore:

```text
task_id
→ logical operation

message_id
→ individual protocol exchange
```

This distinction is important for deduplication and recovery.

---

## 8.2 Message Router

Incoming messages are routed by the C2's **Message Router**.

Conceptually:

```text
MESSAGE
   │
   ▼
Message Router
   │
   ├── REGISTER
   │       ▼
   │   Agent Manager
   │
   ├── TASK_ACK
   │       ▼
   │   Task Manager
   │
   ├── TASK_STATUS
   │       ▼
   │   Task Manager
   │
   ├── RESULT
   │       ▼
   │   Result Manager
   │
   └── FILE_*
           ▼
       File Manager
```

The Message Router is responsible for determining where an incoming protocol
message should be handled.

It does **not** own the lifecycle state of Tasks, Results, Agents, or File
Transfers.

---

# 9. Message Correlation

The model explicitly distinguishes the main correlation identifiers:

| Identifier | Meaning |
|---|---|
| `agent_id` | WHO: identifies the agent |
| `session_id` | WHICH communication session |
| `task_id` | WHICH logical task |
| `result_id` | WHICH result |
| `transfer_id` | WHICH file transfer |
| `message_id` | WHICH protocol message |

This gives the C2 the ability to associate a received message with the
correct application object.

For example:

```text
FILE_START
agent_id    = A001
task_id     = T002
transfer_id = F001
message_id  = M010
```

followed by:

```text
FILE_CHUNK
agent_id    = A001
transfer_id = F001
message_id  = M011
```

The chunk therefore does not need to carry the entire task or transfer
definition again.

---

# 10. Protocol Messages and Domain State

The conceptual relationship between protocol messages and state changes is:

```text
Protocol Message
       │
       ▼
Message Router
       │
       ▼
Domain Manager
       │
       ▼
Domain State Update
```

Examples:

```text
REGISTER
   → Agent Manager
   → Agent identity/state update

BEACON
   → Agent Manager / Session Manager
   → liveness/activity update

TASK_ACK
   → Task Manager
   → WAITING_ACK → QUEUED or RUNNING

TASK_STATUS
   → Task Manager
   → task state synchronization

RESULT
   → Result Manager
   → Result persistence
   → Task completion update

PONG
   → Session / Agent liveness handling
   → immediate communication evidence
```

The exact routing implementation remains an implementation concern.

---

# 11. File Transfer

A **File Transfer** represents the logical lifecycle of a file being
transferred between the C2 server and an agent.

Conceptually:

```text
File Transfer
├── transfer_id
├── agent_id
├── task_id?
├── filename
├── size
├── status
├── hash
├── created_at
├── completed_at
└── storage_path
```

The `task_id` relationship is optional because not every file transfer must
necessarily be modeled as the direct output of one task.

The exact transfer relationships remain subject to the final protocol and
database design.

---

## 11.1 File Transfer and Task

A task may initiate one or more logical file transfers:

```text
Task T002
   │
   ├── FileTransfer F001
   ├── FileTransfer F002
   └── ...
```

The current conceptual relationship is therefore:

```text
Task 1 ─── 0..* FileTransfer
```

when the transfer is associated with a task.

---

## 11.2 File Transfer Correlation

The file-transfer messages use `transfer_id` to associate individual protocol
messages with the correct transfer.

Conceptually:

```text
FILE_START
transfer_id = F001
       │
       ▼
FILE_CHUNK
transfer_id = F001
sequence = 1
       │
       ▼
FILE_CHUNK
transfer_id = F001
sequence = 2
       │
       ▼
FILE_END
transfer_id = F001
```

The logical transfer therefore remains distinct from the individual messages
used to transport it.

---

# 12. File Transfer and Storage

A File Transfer represents the logical transfer operation, while storage
represents where the actual bytes are persisted.

```text
File Transfer
      │
      ├── transfer metadata
      ├── transfer state
      └── storage reference
                 │
                 ▼
          File Storage
                 │
                 ▼
             File Data
```

This distinction prevents the domain model from treating the actual file
bytes and their metadata as the same thing.

The implementation should process file data incrementally where appropriate,
rather than requiring an entire file to exist in memory.

---

# 13. Event

An **Event** represents an operational occurrence within the C2-AUTOMATED
system.

Events are distinct from protocol messages.

Examples include:

```text
agent registration
session establishment
session termination
task creation
task dispatch
task acknowledgement
task state change
task timeout
task completion
task failure
result reception
file transfer start
file transfer completion
communication error
protocol error
```

Conceptually:

```text
Event
├── event_id
├── event_type
├── timestamp
├── agent_id?
├── session_id?
├── task_id?
├── result_id?
├── transfer_id?
└── metadata
```

An event describes something that **happened**.

A message describes something that was **exchanged through the protocol**.

For example:

```text
TASK_ACK message
        │
        ▼
Task acknowledgement event
        │
        ▼
Task state update
```

The event may be generated because of the message, but it is not the same
object.

---

# 14. Entity Relationships

The current conceptual relationships are:

```text
                    ┌─────────────┐
                    │    Agent    │
                    └──────┬──────┘
                           │
                 ┌─────────┴─────────┐
                 │                   │
                 │                   │
                 ▼                   ▼
          ┌─────────────┐      ┌─────────────┐
          │   Session   │      │    Task     │
          └─────────────┘      └──────┬──────┘
                                      │
                          ┌───────────┴───────────┐
                          │                       │
                          ▼                       ▼
                   ┌─────────────┐        ┌─────────────┐
                   │   Result    │        │File Transfer│
                   └─────────────┘        └─────────────┘
```

At a high level:

```text
Agent
 ├── Sessions
 ├── Tasks
 └── File Transfers

Task
 ├── Results
 └── File Transfers

Events
 └── reference relevant entities

Messages
 └── correlate with relevant entities
```

---

# 15. Cardinalities

The current conceptual cardinalities are:

| Relationship | Cardinality |
|---|---|
| Agent → Session | `1 → *` |
| Agent → Task | `1 → *` |
| Agent → File Transfer | `1 → *` |
| Task → Result | `1 → 0..1 / *` |
| Task → File Transfer | `1 → 0..*` |
| Agent → Event | `1 → 0..*` |
| Task → Event | `1 → 0..*` |
| Session → Event | `1 → 0..*` |

The Task → Result cardinality remains intentionally open because the final
execution model may support either a single primary result or multiple
result-producing operations.

---

# 16. Identifiers

The current model distinguishes the following identifiers:

| Identifier | Purpose |
|---|---|
| `agent_id` | Identifies an agent |
| `session_id` | Identifies a communication session |
| `task_id` | Identifies a logical task |
| `result_id` | Identifies a result |
| `message_id` | Identifies a protocol message |
| `transfer_id` | Identifies a file transfer |
| `event_id` | Identifies an operational event |

These identifiers allow concurrent operations to be associated with the
correct entity.

The exact format and generation mechanism for identifiers remain to be
defined.

---

# 17. Identifier Independence

Identifiers must not be conflated.

For example:

```text
agent_id    ≠ session_id
task_id     ≠ message_id
result_id   ≠ task_id
transfer_id ≠ message_id
```

A single task can therefore have multiple associated protocol messages:

```text
T001
 ├── M100
 ├── M101
 ├── M102
 └── M103
```

Likewise, a single file transfer can produce multiple messages:

```text
F001
 ├── M200 FILE_START
 ├── M201 FILE_CHUNK
 ├── M202 FILE_CHUNK
 └── M203 FILE_END
```

This separation is essential for reliable asynchronous communication and
recovery.

---

# 18. Task and Result Relationship

The task/result relationship is one of the most important relationships in
the model.

```text
Task T004
    │
    └── Result R009
```

The `task_id` carried by a result allows the C2 server to identify the task
associated with the returned data.

The association therefore provides traceability between:

```text
requested work
      ↓
task identity
      ↓
execution
      ↓
result identity
```

A completed task may therefore be represented as:

```text
Task T004
status = COMPLETED
result_id = R009
```

When appropriate, a `TASK_STATUS` message may report the associated
`result_id` so the C2 knows that the task completed and that a result exists.

---

# 19. Agent and Session Relationship

The distinction between Agent and Session is intentional.

```text
Agent A001
    │
    ├── Session S01
    │
    ├── Session S02
    │
    └── Session S03
```

A session represents communication at a particular point in time, while the
agent represents the persistent identity.

This allows the server to retain information about an agent after a session
terminates.

---

# 20. Agent, Task, and Session Independence

The three concepts represent different dimensions of system state:

```text
Agent
→ "Who is the endpoint?"

Session
→ "How is communication established now?"

Task
→ "What operation is being performed?"
```

For example:

```text
Agent A001
health = ALIVE

Session S003
status = CONNECTED

Task T017
status = RUNNING
```

Another valid state may be:

```text
Agent A001
health = LIKELY_DEAD

Session S003
status = DISCONNECTED

Task T017
status = WAITING_ACK
```

The task does not become `FAILED` merely because the session is currently
disconnected.

This preserves the distinction between communication state and execution
state.

---

# 21. Message and Entity Relationship

Messages carry representations of application-level entities across the
communication boundary.

Conceptually:

```text
             Application
                  │
        ┌─────────┼─────────┐
        ▼         ▼         ▼
       Task     Result    File Transfer
        │         │         │
        └─────────┼─────────┘
                  ▼
              Protocol
                  │
                  ▼
               Message
                  │
                  ▼
               Transport
```

For state-oriented operations:

```text
TASK_STATUS_QUERY
        │
        ▼
Agent task state
        │
        ▼
TASK_STATUS
        │
        ▼
C2 task state
```

For liveness:

```text
PING
  │
  ▼
PONG
  │
  ▼
communication evidence
```

The protocol therefore acts as the boundary between domain state and network
communication.

---

# 22. Message Types and Domain Objects

The current protocol vocabulary maps conceptually to the domain model as
follows:

| Message | Main domain meaning |
|---|---|
| `REGISTER` | Agent identity / registration |
| `BEACON` | Agent liveness and lightweight activity information |
| `TASK` | Task dispatch |
| `TASK_ACK` | Task reception and acceptance |
| `TASK_STATUS_QUERY` | Request for a task's state |
| `TASK_STATUS` | Report of a task's state |
| `RESULT` | Result delivery |
| `PING` | Immediate liveness check |
| `PONG` | Immediate liveness response |
| `FILE_START` | File transfer initialization |
| `FILE_CHUNK` | File transfer data |
| `FILE_END` | File transfer completion |
| `ERROR` | Protocol or operational error |

This table describes conceptual mapping, not the complete wire-level
contract.

---

# 23. Persistence Model

The C2 server separates structured application state from actual file
contents.

```text
                Application State
                       │
                       ▼
               Database Interface
                       │
                       ▼
                    SQLite
```

Examples of structured data include:

```text
agents
sessions
tasks
results
file transfers
events
```

Actual file contents are persisted through the file-storage abstraction:

```text
                  File Data
                     │
                     ▼
           File Storage Interface
                     │
                     ▼
                 Filesystem
```

This separation is reflected in the server architecture.

Conceptually:

```text
storage/
├── database/
└── files/

data/
└── files/
```

The exact repository structure may evolve independently from the conceptual
model.

---

# 24. In-Memory and Persistent State

Not every piece of information needs to have the same lifetime.

The implementation should distinguish between **persistent**, **active**, and
**temporary** state.

## 24.1 Persistent State

Information that should survive a process restart where appropriate.

Examples:

```text
agent identity
task history
result history
transfer metadata
relevant event history
```

---

## 24.2 Active State

Information required while a communication session or operation is active.

Examples:

```text
active session state
pending task state
running task state
queued task state
active transfer state
```

---

## 24.3 Temporary State

Information that only exists while processing an operation.

Examples:

```text
partial file transfer
temporary file
intermediate reconstruction data
```

A transfer should not be considered complete until the required integrity and
completion conditions are satisfied.

---

# 25. Task Recovery and Persistence

Persistence is particularly important for asynchronous task handling.

For example, after a server-side restart, the implementation may need to
retain enough task information to distinguish:

```text
task created
task dispatched
task acknowledged
task running
task completed
task failed
```

The exact restart/recovery semantics remain to be finalized.

The conceptual rule is that persistent state should be sufficient to prevent
the server from treating an uncertain communication event as proof that a
task failed or should automatically be re-executed.

---

# 26. Events

The architecture anticipates operational events such as:

```text
agent registration
session establishment
session termination
beacon reception
ping / pong
task creation
task dispatch
task acknowledgement
task status change
task completion
task failure
task timeout
result reception
file transfer events
protocol errors
communication errors
```

These events may be logged and, if required, persisted.

Whether the complete event history belongs in the primary database model or
only in application logs remains an implementation decision.

---

# 27. Consistency Rules

The final implementation should preserve several basic consistency rules.

Examples include:

```text
A Task must reference a known Agent.

A Session must reference an Agent.

A Result should reference the Task from which it originated.

A File Transfer must reference its intended Agent.

A task-associated File Transfer should reference the relevant Task.

A protocol Message must have a valid message identifier.

A correlated Message must use identifiers referring to the correct domain
objects.

A file-transfer message must reference the correct transfer.

A TASK_STATUS response must refer to the requested task.

A RESULT must not silently create an unknown Task.
```

These rules may be enforced through application validation, persistence
constraints, or both.

---

# 28. Domain Model vs Database Model

The conceptual entities in this document should not automatically be treated
as one-to-one representations of database tables.

For example:

```text
Domain Entity
     │
     ▼
Persistence Model
     │
     ▼
Database
```

The final implementation may introduce database-specific fields, indexes,
constraints, timestamps, foreign keys, or normalization decisions that are
not part of the conceptual domain model.

The same applies to protocol representations.

For example:

```text
Task domain object
      │
      ▼
TASK protocol model
      │
      ▼
serialized message
```

These are related representations, not necessarily the same Python object.

---

# 29. Domain Model vs Runtime State

The conceptual data model also does not imply that every attribute is stored
permanently.

For example:

```text
Agent
├── persistent identity
├── persistent history
└── current runtime state
```

while an active communication session may exist only temporarily:

```text
Agent A001
      │
      └── Session S004
              │
              └── CONNECTED
```

The exact mapping between runtime objects and database records remains an
implementation decision.

---

# 30. Reliability-Oriented Model

The current model explicitly supports asynchronous communication and
uncertain delivery.

The important distinction is:

```text
Message delivery state
        ≠
Task execution state
```

For example:

```text
C2
 │
 │ TASK T001
 ▼
Agent
 │
 │ TASK_ACK
 X  ACK lost
```

The server may then know:

```text
No ACK received
```

but it does **not** necessarily know:

```text
Task was not received
```

Recovery therefore uses:

```text
PING
  ↓
PONG
  ↓
TASK_STATUS_QUERY
  ↓
TASK_STATUS
```

This model avoids blindly treating communication failure as execution
failure.

---

# 31. Duplicate Handling

The model supports duplicate detection through both logical and communication
identifiers.

### Message level

`message_id` identifies an individual protocol message.

### Task level

`task_id` identifies the logical operation and is therefore more important
when preventing duplicate task execution.

Conceptually:

```text
same message_id
→ duplicate communication message

same task_id
→ same logical task
```

The agent should retain a bounded history of recently seen task and message
identifiers where required.

The exact retention size and deduplication algorithm remain implementation
decisions.

---

# 32. Complete Conceptual Picture

The current model can be summarized as:

```text
                           Agent
                            │
             ┌──────────────┼──────────────┐
             │              │              │
             ▼              ▼              ▼
          Sessions         Tasks       File Transfers
                            │
                     ┌──────┴──────┐
                     │             │
                     ▼             ▼
                  Results       Transfers
```

Operationally:

```text
                         MESSAGE
                            │
                            ▼
                     Message Router
                            │
           ┌────────────────┼────────────────┐
           ▼                ▼                ▼
     Agent Manager     Task Manager    Result Manager
           │                │                │
           ▼                ▼                ▼
         Agent            Task            Result
                            │
                            ▼
                       File Manager
```

And communication itself is:

```text
Domain State
     │
     ▼
Protocol Message
     │
     ▼
Transport
     │
     ▼
Network
     │
     ▼
Transport
     │
     ▼
Protocol Message
     │
     ▼
Domain State
```

---

# 33. Current Design Summary

The current model therefore keeps the following distinctions explicit:

```text
Identity
  → Agent

Communication
  → Session

Liveness
  → Beacon / Ping / Pong

Requested operation
  → Task

Execution output
  → Result

Network representation
  → Message

File movement
  → File Transfer

Operational occurrence
  → Event

Physical persistence
  → Storage
```

The main correlation identifiers are:

```text
agent_id
session_id
task_id
result_id
transfer_id
message_id
event_id
```

The principal architectural rule is:

```text
One logical task
    ≠
one protocol message
```

Similarly:

```text
One file transfer
    ≠
one protocol message
```

This distinction is what allows C2-AUTOMATED to support multi-session,
multi-agent, asynchronous, and recoverable communication without conflating
network communication with application state.

---

# 34. Open Questions

The following points remain to be finalized:

- exact fields for each entity;
- identifier format and generation;
- primary keys;
- foreign keys;
- exact database cardinalities;
- final Task → Result cardinality;
- session persistence strategy;
- exact Beacon payload;
- exact Ping/Pong fields;
- task cancellation semantics;
- retry policy;
- timeout values;
- recent-ID retention size;
- event persistence;
- synchronization between in-memory and persistent state;
- database indexes;
- data-retention rules;
- exact database schema;
- relationship between protocol models and domain models;
- exact mapping between runtime objects and persistent records.

These decisions should be resolved before the final persistence model is
considered stable.

Significant architectural or protocol decisions should be recorded in
[`DECISIONS.md`](../DECISIONS.md).
