# Data Model

> **Status: Work in Progress**
>
> This document describes the current conceptual data model of
> C2-AUTOMATED. Entity fields, relationships, persistence rules, and
> implementation details may evolve as the architecture and protocol are
> finalized.
>
> The model intentionally separates **domain entities**, **communication
> sessions**, **transport connections**, **protocol messages**, **operational
> events**, and **physical storage**.

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

A transport connection is also distinguished conceptually because it is the
actual network-level communication mechanism, but it is not treated as the
persistent identity of either an Agent or a Session.

These entities exist at the application level. Their exact representation in
Python classes, database models, protocol structures, or runtime objects may
differ.

A key architectural principle is:

```text
Agent
    → persistent endpoint identity

Session
    → one communication episode

Connection
    → actual transport connection

Task
    → logical operation requested for an Agent

Result
    → outcome produced by a Task

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
          │
          ▼
      Network
```

A message is therefore **not equivalent to the domain object it represents**.

---

# 3. Agent

An **Agent** represents the persistent identity of an endpoint running the
agent software.

The Agent identity survives across communication sessions and transport
connections.

Conceptually:

```text
Agent
├── identity
│   ├── agent_id
│   ├── hostname
│   ├── operating_system
│   ├── architecture
│   └── agent_version?
│
├── health
│   ├── agent_status
│   ├── first_seen
│   └── last_seen
│
├── communication
│   ├── communication_state
│   ├── last_beacon
│   ├── last_beacon_ack
│   ├── last_ping
│   └── last_pong
│
├── sessions
│   ├── active_session_id?
│   └── last_session_id?
│
├── activity
│   ├── activity_state
│   ├── current_task_id?
│   └── queued_task_count
│
└── history
    └── last_result_id?
```

The exact persistent schema remains to be finalized.

---

## 3.1 Agent Identity

`agent_id` uniquely identifies the Agent from the C2 server's perspective.

The identity mechanism itself has not yet been finalized.

The identity must remain independent from:

```text
session_id
message_id
task_id
```

A new communication session therefore does not create a new logical Agent.

---

## 3.2 Agent Health State

The current conceptual health model is:

```text
UNKNOWN
   │
   │ REGISTER
   ▼
 ALIVE
   │
   │ insufficient expected communication
   ▼
LIKELY_UNREACHABLE
   │
   │ communication resumes
   ▼
 ALIVE
```

An explicitly confirmed termination may instead produce:

```text
ALIVE
   │
   │ explicit termination
   ▼
TERMINATED
```

The states are interpreted as:

### `UNKNOWN`

The C2 does not yet have sufficient information to establish the current
health of the Agent.

### `ALIVE`

The C2 has recent evidence that the Agent is communicating or has recently
responded.

### `LIKELY_UNREACHABLE`

The Agent has failed to communicate within the expected conditions and is
considered likely unavailable.

This is deliberately not equivalent to confirmed process or host
termination.

### `TERMINATED`

Where supported, this represents an explicitly confirmed termination of the
Agent.

It must not be inferred solely from communication loss.

---

## 3.3 Agent Activity State

Agent health and Agent activity are distinct concepts.

The current activity model is:

```text
IDLE
BUSY
```

For example:

```text
Agent health:       ALIVE
Activity state:     BUSY
Current task:       T001
```

`RUNNING` belongs to the **Task** state machine, not the Agent activity
model.

This allows the system to represent:

```text
Agent = ALIVE
Activity = BUSY

Task T001 = RUNNING
Task T002 = QUEUED
Task T003 = QUEUED
```

---

## 3.4 Agent Communication State

The Agent has a separate communication mode describing its ability to
communicate reliably with the C2.

The current conceptual model is:

```text
CONNECTING
     │
     ▼
 CONNECTED
     │
     │ communication failure
     ▼
 DEGRADED
   /      \
recovery   repeated failure
  │             │
  ▼             ▼
CONNECTED   OFFLINE_WAIT
                │
                │ reconnect attempt
                ▼
            CONNECTING
```

A separate synchronization phase occurs after a new connection is
established:

```text
CONNECTING
    │
    ▼
SYNCHRONIZING
    │
    ▼
 CONNECTED
```

The communication state is therefore independent from:

```text
Agent health
Agent activity
Session state
Task state
```

For example:

```text
Agent health       = ALIVE
Activity           = BUSY
Communication      = DEGRADED
Session            = DISCONNECTED
Task T001          = RUNNING
```

These values are not contradictory because they represent different
dimensions of system state.

---

## 3.5 Agent Runtime Information

The Agent may maintain lightweight runtime information such as:

```text
agent_id
communication_state
last_c2_contact
last_beacon_ack

current_task_id
queued_task_ids
last_task_id

pending_result_ids

recent_task_ids
recent_message_ids
```

Recent identifiers should be bounded rather than retained indefinitely in
memory.

This state is useful for:

- task deduplication;
- message deduplication;
- task recovery;
- offline result retention;
- tracking the currently executing operation;
- responding to status queries;
- synchronization after reconnection.

The Agent should maintain only the runtime information required for
continuity and recovery. The C2 maintains the complete historical record.

---

# 4. Session

A **Session** represents one logical communication episode between a
specific Agent and the C2 through a transport.

The architectural distinction is:

```text
Agent
    → persistent identity

Session
    → one communication episode

Connection
    → actual transport connection
```

For example:

```text
Agent A001
   │
   ├── Session S041
   │      10:00 → 10:45
   │      DISCONNECTED
   │
   ├── Session S042
   │      11:10 → 12:30
   │      CLOSED
   │
   └── Session S043
          13:05 → current
          CONNECTED
```

The Agent identity survives across all of these Sessions.

---

## 4.1 Session Information

A Session may contain information such as:

```text
session_id
agent_id
session_status
transport
created_at
ended_at?
connection metadata
```

The current conceptual Session states are:

```text
CONNECTING
     │
     ▼
 CONNECTED
   /     \
  /       \
 ▼         ▼
DISCONNECTED  CLOSED
```

These states have different meanings:

### `CONNECTING`

The Session is being established.

### `CONNECTED`

The Session is actively associated with a functioning communication
connection.

### `DISCONNECTED`

The connection associated with the Session is no longer available.

The Session record remains known to the C2 and is not deleted merely because
communication was lost.

### `CLOSED`

The Session's lifecycle has been deliberately or orderly ended, such as
through explicit termination or clean application shutdown.

For a given Session, `DISCONNECTED` and `CLOSED` are terminal states.

A later reconnection creates a **new Session** instead of returning the old
Session to `CONNECTED`.

---

## 4.2 Session and Agent Relationship

Conceptually:

```text
One Agent
    │
    ├── Session S041
    ├── Session S042
    ├── Session S043
    └── ...
```

The cardinality is:

```text
Agent 1 ─── * Session
```

A Session does not replace or redefine the persistent identity of the Agent.

---

## 4.3 Session and Connection

A Session is distinct from the underlying network connection.

Conceptually:

```text
Agent
  │
  ▼
Session
  │
  ▼
TCP/TLS Connection
  │
  ▼
Network
```

For the initial implementation, one Session corresponds to one connection
episode.

When that connection disappears:

```text
S042
CONNECTED
   ↓
DISCONNECTED
```

If the Agent later establishes a new connection:

```text
new connection
      ↓
S043 created
      ↓
S043 = CONNECTED
```

The old Session is not revived.

---

## 4.4 Session and Reconnection

A new successful connection to the C2 creates a new Session.

For example:

```text
S042 = DISCONNECTED
        │
        │ new connection
        ▼
S043 = CONNECTED
```

The persistent Agent remains:

```text
A001
```

This rule applies even if the Agent reports:

```text
previous_session_id = S042
```

Such a value is historical context and does not request that S042 be reopened.

---

## 4.5 Session and Agent State

Session status and Agent health remain independent.

For example:

```text
Agent health          = ALIVE
Communication state   = OFFLINE_WAIT
Active session        = none
Last session          = S042
```

Another valid situation is:

```text
Agent health          = ALIVE
Communication state   = CONNECTED
Active session        = S043
```

A disconnected Session therefore does not imply that the Agent itself has
been terminated.

---

# 5. Liveness and Communication Information

The model distinguishes routine communication from active communication
testing.

## 5.1 Beacon

`BEACON` is the Agent's periodic check-in:

```text
Agent
  │
  │ BEACON
  ▼
 C2
  │
  │ BEACON_ACK
  ▼
Agent
```

A Beacon may carry lightweight operational information such as:

```text
activity_state
current_task_id?
queued_task_count
last_task_id?
last_result_id?
```

The exact payload remains subject to protocol specification.

The C2 may update:

```text
last_seen
last_beacon
Agent activity
current task
session activity
```

The Agent records the corresponding acknowledgement information, such as:

```text
last_beacon_ack
last_c2_contact
```

A Beacon does not create a Task.

---

## 5.2 Ping / Pong

`PING/PONG` is an active liveness mechanism:

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

Its purpose is:

> Verify that communication with the Agent succeeds at that moment.

A `PONG` is therefore evidence of immediate responsiveness.

It does **not** by itself synchronize Task or Result state.

This differs from the Beacon mechanism:

```text
BEACON / BEACON_ACK
→ normal periodic communication cycle

PING / PONG
→ active immediate connectivity test
```

---

# 6. Task

A **Task** represents one logical operation requested for a specific Agent.

A Task belongs to the Agent, not to a Session.

Conceptually:

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
├── completed_at
│
├── created_session_id?
├── last_session_id?
│
├── ack_deadline
├── execution_deadline
├── timeout_reason?
├── result_id?
└── error?
```

The detailed lifecycle is documented in
[`task-lifecycle.md`](task-lifecycle.md).

---

## 6.1 Task Ownership

A Task belongs logically to one Agent:

```text
Agent A001
   │
   ├── Task T001
   ├── Task T002
   └── Task T003
```

The relationship is:

```text
Agent 1 ─── * Task
```

A Task is **not owned by a Session**.

`created_session_id` and `last_session_id`, where retained, are historical
and communication-context metadata.

---

## 6.2 Task Can Span Sessions

A Task may be created, executed, and completed across different Sessions.

For example:

```text
T002
│
├── created during S042
├── queued during S042
├── Agent disconnected
├── remains queued during OFFLINE_WAIT
├── Agent reconnects through S043
└── executed through S043
```

Another example:

```text
T001
│
├── created during S042
├── execution starts during S042
├── communication lost
├── execution completes while offline
├── Result R001 stored locally
└── R001 transmitted during S043
```

Both are valid.

Therefore:

```text
Task identity
    ≠
Session identity
```

---

## 6.3 Task State

The current conceptual Task states are:

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
   │ TASK_STATUS(RUNNING)
   ▼
RUNNING
  /    \
 /      \
▼        ▼
COMPLETED  FAILED
```

Additional outcomes are:

```text
TIMEOUT
CANCELLED
```

The complete set is:

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

These states are independent from Agent, communication, and Session state.

---

## 6.4 `TASK_ACK`

`TASK_ACK` means:

> The Agent has received, validated, and accepted the Task for execution or
> queuing.

Therefore:

```text
WAITING_ACK
      │
      │ TASK_ACK
      ▼
   QUEUED
```

If the Agent can immediately execute the Task, it may proceed rapidly from
`QUEUED` to `RUNNING`.

The preferred explicit mechanism for notifying the C2 that execution has
actually begun is:

```text
TASK_STATUS(RUNNING)
```

---

## 6.5 Communication Uncertainty

Failure to receive a Task acknowledgement does not automatically mean that
Task execution failed.

The model distinguishes:

```text
communication failure
        ≠
task execution failure
```

For example:

```text
TASK T001
    ↓
WAITING_ACK
    ↓
ACK lost
```

The C2 must not blindly retransmit the Task because the Agent may already
have accepted it.

The recovery process is:

```text
WAITING_ACK
      │
      │ timeout
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
TASK_STATUS(...)
```

Possible results include:

```text
QUEUED
RUNNING
COMPLETED
FAILED
UNKNOWN
```

A redispatch may be considered only when the Agent confirms that the Task is
`UNKNOWN`, subject to the final retry policy.

---

# 7. Result

A **Result** represents the outcome or data produced by a Task.

Conceptually:

```text
Result
├── result_id
├── task_id
├── agent_id
├── status
├── timestamp
├── received_session_id?
└── data
```

A Result belongs logically to the Task that produced it.

```text
Agent
  │
  └── Task T001
        │
        └── Result R001
```

The relationship remains conceptually:

```text
Task 1 ─── 0..1 / *
```

depending on the final execution/result model.

---

## 7.1 Result and Session

A Result may be associated with the Session through which it is transmitted
to the C2.

For example:

```text
T001
created in S042

R001
produced while disconnected
received through S043
```

There is therefore no requirement for:

```text
Task.session_id == Result.session_id
```

The Session is communication context, not Result ownership.

---

## 7.2 Result Identification

`result_id` identifies a specific Result independently from:

```text
task_id
message_id
session_id
agent_id
```

This permits the C2 to detect a retransmitted Result without creating a
second logical Result.

---

## 7.3 Result and Task Recovery

If an Agent completes a Task while the C2 is unreachable:

```text
Task T001
      ↓
completed locally
      ↓
Result R001
      ↓
local pending-results
```

The Result is retained until communication becomes available again.

After reconnection:

```text
new Session
      ↓
synchronization
      ↓
pending Result transmitted
      ↓
C2 stores R001
```

The Result therefore survives communication interruptions.

---

## 7.4 Unmatched Results

If the C2 receives a Result referencing an unknown Task, it should not invent
a Task to satisfy the relationship.

The Result should instead be treated as:

```text
unmatched / unexpected result
```

and handled according to the final validation and logging rules.

---

# 8. Message

A **Message** represents a protocol-level communication unit exchanged
between the C2 and Agent.

A conceptual message envelope is:

```text
Message
├── protocol_version
├── message_id
├── message_type
├── agent_id
├── session_id?
├── task_id?
├── result_id?
├── transfer_id?
├── timestamp
└── payload
```

Not every field is mandatory for every message.

The exact wire representation is defined separately in
[`protocol.md`](protocol.md).

---

## 8.1 Message Identity

`message_id` identifies one specific protocol message.

It must not be confused with the logical Task or Result.

For example:

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
→ identifies logical work

message_id
→ identifies one protocol communication
```

This distinction supports tracing, deduplication, and recovery.

---

## 8.2 Cross-Session Messages

A message may concern a Task that was created or previously communicated
through another Session.

For example:

```text
Task T002
created during S042
        │
        ▼
new Session S043
        │
        ▼
TASK_ACK(T002)
```

This is valid provided that:

```text
Agent identity is valid
Session belongs to Agent
Task belongs to Agent
state transition is valid
message is not a duplicate
```

The message's `session_id` identifies **where the communication happened**,
not the Task's ownership.

---

## 8.3 Message Router

Incoming Messages are routed by the C2's **Message Router**.

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
   ├── BEACON
   │       ▼
   │   Agent / Session management
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
   ├── SYNC_STATE
   │       ▼
   │   Synchronization Manager
   │
   └── FILE_*
           ▼
       File Manager
```

The Message Router is responsible for determining where a Message should be
handled.

It does **not** own the lifecycle state of Agents, Sessions, Tasks, Results,
or File Transfers.

---

# 9. Message Correlation

The model explicitly distinguishes the main correlation identifiers:

| Identifier | Meaning |
|---|---|
| `agent_id` | identifies the Agent |
| `session_id` | identifies the communication Session |
| `task_id` | identifies the logical Task |
| `result_id` | identifies the Result |
| `transfer_id` | identifies the File Transfer |
| `message_id` | identifies the protocol Message |
| `event_id` | identifies an operational Event |

Conceptually:

```text
agent_id
→ WHO

session_id
→ WHICH communication episode

task_id
→ WHICH logical operation

result_id
→ WHICH result

transfer_id
→ WHICH file transfer

message_id
→ WHICH protocol message
```

This separation is fundamental to cross-session recovery.

---

# 10. Protocol Messages and Domain State

The conceptual relationship between protocol Messages and domain state is:

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
   → establish Agent identity
   → create new Session

REGISTER_ACK
   → communicate new Session ID to Agent

BEACON
   → update periodic liveness/activity information

BEACON_ACK
   → confirm Beacon reception

PING
   → initiate immediate liveness check

PONG
   → provide immediate communication evidence

TASK_ACK
   → WAITING_ACK → QUEUED

TASK_STATUS(RUNNING)
   → QUEUED → RUNNING

TASK_STATUS(...)
   → reconcile Task state

RESULT
   → store Result
   → update Task

SYNC_STATE
   → provide Agent-side recovery state

SYNC_STATE_RESPONSE
   → provide C2 reconciliation decisions

SYNC_COMPLETE
   → terminate synchronization phase
```

The exact routing implementation remains an implementation concern.

---

# 11. Synchronization State

Synchronization is a protocol phase associated with a **new Session**.

It does not revive a previous Session.

Conceptually:

```text
Old Session
    ↓
DISCONNECTED / CLOSED
    ↓
new connection
    ↓
NEW Session
    ↓
SYNCHRONIZING
```

The purpose is to reconcile:

```text
Agent state
    ↕
C2 state
```

after a period of communication loss.

---

## 11.1 Reconnection Sequence

For a returning Agent:

```text
Agent                                C2
────────────────────────────────────────────

new connection
────────────────────────────────────────►

REGISTER
agent_id = A001
previous_session_id = S042
────────────────────────────────────────►

                            create S043

REGISTER_ACK
session_id = S043
◄────────────────────────────────────────

SYNC_STATE
────────────────────────────────────────►

                            reconcile state

SYNC_STATE_RESPONSE
◄────────────────────────────────────────

SYNC_COMPLETE
◄────────────────────────────────────────

normal operation
```

The exact synchronization payload remains defined by the protocol
specification.

---

## 11.2 Synchronization Content

The Agent should provide only information required for recovery and
reconciliation.

Conceptually:

```text
SYNC_STATE
{
    agent_id,

    current_task_id?,
    current_task_status?,

    queued_task_ids,

    pending_result_ids,

    recent_task_ids,

    recent_message_ids,

    last_task_id?,
    last_result_id?,

    activity_state
}
```

The C2 retains the more complete historical model.

---

## 11.3 Synchronization Response

The C2's response communicates reconciliation decisions rather than blindly
replaying the database.

Conceptually:

```text
SYNC_STATE_RESPONSE
{
    task_updates,
    tasks_to_send,
    tasks_to_cancel?,
    results_needed?
}
```

The exact structure remains to be finalized.

---

## 11.4 Synchronization Does Not Mean Session Resumption

The distinction is:

```text
Session recovery
→ create a new Session

State recovery
→ synchronize and reconcile Agent/C2 state
```

For example:

```text
S042 = CLOSED
S043 = CONNECTED

T001
created during S042
completed before S043
```

There is no requirement for T001 to be recreated.

---

# 12. File Transfer

A **File Transfer** represents the logical lifecycle of a file being
transferred between the C2 and Agent.

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

The `task_id` relationship is optional because a File Transfer is not
necessarily identical to a Task.

---

## 12.1 File Transfer and Task

A Task may initiate one or more File Transfers:

```text
Task T002
   │
   ├── FileTransfer F001
   ├── FileTransfer F002
   └── ...
```

Conceptually:

```text
Task 1 ─── 0..* FileTransfer
```

when the transfer is associated with a Task.

---

## 12.2 File Transfer Correlation

Individual transfer Messages use `transfer_id`:

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

The logical File Transfer therefore remains distinct from the individual
Messages used to transport it.

---

# 13. File Transfer and Storage

A File Transfer represents the logical operation, while Storage represents
where the actual bytes are persisted.

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

This prevents the domain model from treating file metadata and file bytes as
the same object.

The implementation should process file data incrementally where appropriate,
rather than requiring an entire file to be loaded into memory.

---

# 14. Event

An **Event** represents an operational occurrence within the C2-AUTOMATED
system.

Events are distinct from protocol Messages.

Examples include:

```text
agent registration
session establishment
session disconnection
session closure
beacon reception
beacon acknowledgement
ping / pong
task creation
task dispatch
task acknowledgement
task state change
task timeout
task completion
task failure
result reception
file transfer events
synchronization events
protocol errors
communication errors
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

An Event describes something that **happened**.

A Message describes something that was **exchanged through the protocol**.

For example:

```text
TASK_ACK message
        │
        ▼
task acknowledgement event
        │
        ▼
Task state update
```

The event may be caused by the Message, but it is not the same object.

---

# 15. Entity Relationships

The current conceptual relationships are:

```text
                    ┌─────────────┐
                    │    Agent    │
                    └──────┬──────┘
                           │
               ┌───────────┼───────────┐
               │           │           │
               ▼           ▼           ▼
          ┌─────────┐ ┌─────────┐ ┌─────────────┐
          │Session  │ │  Task   │ │File Transfer│
          └─────────┘ └────┬────┘ └─────────────┘
                           │
                           ▼
                      ┌─────────┐
                      │ Result  │
                      └─────────┘
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

Event
 └── references relevant entities

Message
 └── correlates relevant entities
```

The important constraint is:

```text
Task
  → belongs to Agent

Task
  → is not owned by Session
```

---

# 16. Cardinalities

The current conceptual cardinalities are:

| Relationship | Cardinality |
|---|---|
| Agent → Session | `1 → *` |
| Agent → Task | `1 → *` |
| Agent → File Transfer | `1 → *` |
| Task → Result | `1 → 0..1 / *` |
| Task → File Transfer | `1 → 0..*` |
| Agent → Event | `1 → 0..*` |
| Session → Event | `1 → 0..*` |
| Task → Event | `1 → 0..*` |

The Task → Result cardinality remains open until the execution/result model is
fully finalized.

A Session does not have ownership cardinality over Tasks.

Tasks may reference Sessions only as communication-history metadata.

---

# 17. Identifiers

The current model distinguishes:

| Identifier | Purpose |
|---|---|
| `agent_id` | persistent Agent identity |
| `session_id` | one communication episode |
| `task_id` | one logical Task |
| `result_id` | one Result |
| `message_id` | one protocol Message |
| `transfer_id` | one File Transfer |
| `event_id` | one Event |

The exact format and generation mechanisms remain to be defined.

---

# 18. Identifier Independence

Identifiers must not be conflated.

For example:

```text
agent_id    ≠ session_id
task_id     ≠ message_id
result_id   ≠ task_id
transfer_id ≠ message_id
```

A logical Task may generate Messages across multiple Sessions:

```text
T001
 │
 ├── M100 / S042
 ├── M101 / S042
 ├── communication loss
 ├── M102 / S043
 └── M103 / S043
```

This is valid because:

```text
Task identity
    ≠
Session identity
    ≠
Message identity
```

---

# 19. Task and Result Relationship

The Task/Result relationship provides traceability between requested work and
its outcome.

```text
Task T004
    │
    └── Result R009
```

The traceability chain is:

```text
requested operation
      ↓
Task
      ↓
execution
      ↓
Result
```

A Task may be associated with the Session in which it was created and the
most recent Session through which it was communicated, without becoming
Session-owned:

```text
T004
agent_id            = A001
created_session_id  = S042
last_session_id     = S043
status              = COMPLETED
result_id           = R009
```

This allows the model to represent cross-session operations explicitly.

---

# 20. Agent, Task, Session, and Communication Independence

These concepts represent different dimensions of system state:

```text
Agent
→ "Who is the endpoint?"

Session
→ "Which communication episode is this?"

Connection
→ "Which transport connection is currently being used?"

Communication state
→ "How reliably can the Agent communicate with the C2?"

Task
→ "What logical operation exists?"

Result
→ "What outcome was produced?"
```

For example:

```text
Agent A001
health = ALIVE

Communication
state = OFFLINE_WAIT

Last Session
S042 = DISCONNECTED

Task T001
status = RUNNING
```

This is valid.

The Agent may still be executing T001 locally even though its previous
Session is no longer connected.

---

# 21. Offline Operation and Local State

Communication loss does not automatically erase Agent-side operational state.

If the Agent is executing:

```text
T001 = RUNNING
```

and C2 communication is lost:

```text
T001 → may continue
```

If T001 completes:

```text
R001 → local pending-results
```

Queued Tasks remain queued:

```text
T002 = QUEUED
T003 = QUEUED
```

The Agent does not normally start new queued work while communication is
unavailable.

After reconnection:

```text
new Session
      ↓
SYNCHRONIZING
      ↓
pending results
task state reconciliation
      ↓
SYNC_COMPLETE
      ↓
resume normal queued work
```

This preserves execution state independently from communication state.

---

# 22. Persistence Model

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

# 23. In-Memory and Persistent State

Not every piece of information needs the same lifetime.

The implementation should distinguish between **persistent**, **active**, and
**temporary** state.

## 23.1 Persistent State

Information that should survive a C2 process restart where appropriate.

Examples:

```text
Agent identity
Session history
Task history
Result history
Transfer metadata
Relevant event history
```

---

## 23.2 Active State

Information required while an operation or communication context is active.

Examples:

```text
active Session
active communication state
pending Task
running Task
queued Task
active File Transfer
synchronization state
```

---

## 23.3 Temporary State

Information that exists only while processing an operation.

Examples:

```text
partial file transfer
temporary file
intermediate reconstruction data
temporary synchronization data
```

The exact persistence policy remains an implementation decision.

---

# 24. Synchronization and Persistence

Persistence is particularly important because Tasks and Results can survive
communication interruptions and Sessions.

For example:

```text
S042
   ↓
connection lost
   ↓
T001 continues
   ↓
R001 produced locally
   ↓
S043
   ↓
synchronization
   ↓
R001 stored by C2
```

The C2 should therefore retain enough historical Task, Result, and Session
information to reconcile state after reconnection.

The C2 remains the authoritative historical record, while the Agent maintains
the smaller local state required for continuity and recovery.

---

# 25. Consistency Rules

The final implementation should preserve several basic consistency rules.

Examples include:

```text
A Task must reference a known Agent.

A Session must reference an Agent.

A File Transfer must reference its intended Agent.

A Result should reference the Task from which it originated.

A Message must have a valid message identifier.

A correlated Message must use identifiers referring to the correct entities.

A Session identifier must correspond to the Agent identified by the Message.

A Task-related Message may use a Session different from the Task's
created_session_id.

A TASK_STATUS response must refer to the requested Task.

A RESULT must not silently create an unknown Task.

A new connection must create a new Session rather than revive an old one.

A Session in DISCONNECTED or CLOSED must not return to CONNECTED.

An Agent must not be treated as TERMINATED solely because communication was
lost.
```

These rules may be enforced through application validation, persistence
constraints, or both.

---

# 26. Domain Model vs Database Model

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
serialized Message
```

These are related representations, not necessarily the same Python object.

---

# 27. Domain Model vs Runtime State

The conceptual data model does not imply that every attribute is stored
permanently.

For example:

```text
Agent
├── persistent identity
├── persistent history
└── current runtime state
```

An Agent's current Session is runtime state:

```text
A001
active_session_id = S043
```

while historical Sessions remain persistent:

```text
S042 = CLOSED
S043 = CONNECTED
```

When the Agent is disconnected:

```text
active_session_id = null
last_session_id   = S043
```

The exact runtime/database mapping remains an implementation decision.

---

# 28. Reliability-Oriented Model

The model explicitly supports asynchronous communication and uncertain
delivery.

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
 X
```

The C2 cannot conclude solely from this that T001 was not accepted.

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

Similarly, if a Result is lost:

```text
T001 = RUNNING
     ↓
RESULT lost
     ↓
new communication
     ↓
TASK_STATUS_QUERY
     ↓
TASK_STATUS(COMPLETED, R001)
```

The system should not execute T001 again merely because the Result was not
received.

---

# 29. Duplicate Handling

The model supports duplicate detection through both logical and communication
identifiers.

### Message level

`message_id` identifies an individual protocol Message.

### Task level

`task_id` identifies the logical operation.

### Result level

`result_id` identifies the logical Result.

Conceptually:

```text
same message_id
→ duplicate Message

same task_id
→ same logical Task

same result_id
→ same logical Result
```

The Agent should retain a bounded history of recently seen Task and Message
identifiers where required.

The C2 should also prevent duplicate Results from creating duplicate logical
records.

The exact retention size and deduplication algorithm remain implementation
decisions.

---

# 30. Complete Conceptual Picture

The current model can be summarized as:

```text
                            Agent
                              │
               ┌──────────────┼──────────────┐
               │              │              │
               ▼              ▼              ▼
           Sessions          Tasks       File Transfers
               │              │
               │              ▼
               │           Results
               │
               ▼
        Communication context
```

The Agent itself maintains:

```text
health
activity
communication state
current session
task runtime state
pending results
```

while the C2 maintains:

```text
Agent history
Session history
Task history
Result history
Transfer history
Event history
```

Protocol Messages connect those states across the network:

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

---

# 31. Reconnection and Synchronization Picture

The complete Session/communication relationship is:

```text
                 Agent A001
                      │
          ┌───────────┼───────────┐
          │           │           │
          ▼           ▼           ▼
       Session      Session     Session
        S041         S042        S043
          │           │           │
       CLOSED      CLOSED     CONNECTED
                                  │
                              synchronization
                                  │
                                  ▼
                             normal operation
```

The state recovery relationship is:

```text
Old Session
    │
    ▼
communication loss
    │
    ▼
Agent retains local state
    │
    ▼
new connection
    │
    ▼
new Session
    │
    ▼
SYNCHRONIZING
    │
    ├── pending Results
    ├── current Task
    ├── queued Tasks
    └── recent identifiers
    │
    ▼
reconciliation
    │
    ▼
SYNC_COMPLETE
    │
    ▼
normal operation
```

The Session itself is **not** resumed.

The Agent's state is **reconciled**.

---

# 32. Current Design Summary

The current model therefore keeps the following distinctions explicit:

```text
Identity
  → Agent

Communication episode
  → Session

Transport connection
  → TCP/TLS connection

Agent health
  → UNKNOWN / ALIVE / LIKELY_UNREACHABLE / TERMINATED

Agent activity
  → IDLE / BUSY

Agent communication mode
  → CONNECTING / CONNECTED / DEGRADED / OFFLINE_WAIT / SYNCHRONIZING

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

The principal relationship rules are:

```text
Agent owns Tasks.
Agent owns Sessions.
Task owns/produces Results.
Tasks can span Sessions.
Results can be transmitted through later Sessions.
Messages can concern Tasks created through earlier Sessions.
New connections create new Sessions.
Sessions are never revived.
State is synchronized after reconnection.
```

The principal correlation identifiers are:

```text
agent_id
session_id
task_id
result_id
transfer_id
message_id
event_id
```

The resulting model keeps **identity, communication, execution, protocol
representation, and persistence separate**, while still providing the
correlations required for asynchronous operation and recovery.

---

# 33. Open Questions

The following points remain to be finalized:

- exact fields for each entity;
- exact distinction between runtime Connection objects and persistent
  Session records;
- identifier format and generation;
- database primary keys;
- database foreign keys;
- database indexes;
- exact Task → Result cardinality;
- exact Agent health transition thresholds;
- exact communication retry policy;
- exact `OFFLINE_WAIT` reconnect interval;
- exact Beacon interval and jitter defaults;
- exact timeout values;
- exact duplicate-retention size;
- exact synchronization payload fields;
- exact synchronization conflict-resolution algorithm;
- exact Result recovery mechanism;
- exact Task cancellation behavior;
- exact authentication and registration mechanism;
- exact serialization format;
- exact File Transfer retry/resume behavior;
- event persistence and retention policy;
- synchronization between in-memory and persistent state;
- exact mapping between protocol models, domain models, and database models.

These decisions should be resolved before the final persistence model and
protocol implementation are considered stable.

Significant architectural or protocol decisions should be recorded in
[`DECISIONS.md`](../DECISIONS.md).
