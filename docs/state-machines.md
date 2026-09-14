# Data Model

> **Status: Work in Progress**
>
> This document defines the current conceptual data model of C2-AUTOMATED.
> Entity fields, relationships, persistence rules, and implementation details
> may evolve as the architecture and protocol are finalized.
>
> The model separates **domain entities**, **communication Sessions**,
> **transport Connections**, **protocol Messages**, **operational Events**,
> and **physical storage**.

---

# 1. Purpose and Scope

The current primary domain entities are:

```text
Agent
Session
Task
Result
Message
File Transfer
Event
```

A transport `Connection` is also represented conceptually because it is the
actual network communication mechanism.

The main distinction is:

```text
Agent
    → persistent endpoint identity

Session
    → one communication episode

Connection
    → transport-level communication

Task
    → logical operation requested for an Agent

Result
    → outcome produced by a Task

Message
    → protocol communication unit

File Transfer
    → logical file movement

Event
    → operational occurrence
```

These are conceptual objects. Their final Python, protocol, runtime, and
database representations may differ.

---

# 2. Domain Overview

The ownership relationships are:

```text
                    ┌─────────────┐
                    │    Agent    │
                    └──────┬──────┘
                           │
               ┌───────────┼───────────┐
               │           │           │
               ▼           ▼           ▼
          ┌─────────┐ ┌─────────┐ ┌─────────────┐
          │ Session │ │  Task   │ │File Transfer│
          └─────────┘ └────┬────┘ └─────────────┘
                           │
                           ▼
                      ┌─────────┐
                      │ Result  │
                      └─────────┘
```

Messages and Events are cross-cutting:

```text
Entities
   │
   ├──► Events
   │
   └──► Messages
           │
           ▼
       Transport
```

A Message is therefore not the same object as the Task, Result, or Event it
references.

---

# 3. Agent

An **Agent** represents the persistent identity of an endpoint.

Its identity survives across Sessions and transport Connections.

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

## 3.1 Identity

`agent_id` uniquely identifies an Agent from the C2 perspective.

It is independent from:

```text
session_id
task_id
result_id
message_id
transfer_id
event_id
```

A new Session therefore does not create a new Agent.

## 3.2 Health

The current health states are:

```text
UNKNOWN
ALIVE
LIKELY_UNREACHABLE
TERMINATED
```

Normal liveness may follow:

```text
UNKNOWN
   │
   │ valid REGISTER
   ▼
ALIVE
   │
   │ insufficient expected communication
   ▼
LIKELY_UNREACHABLE
   │
   │ valid communication resumes
   ▼
ALIVE
```

`TERMINATED` is reserved for explicit or otherwise confirmed termination.
Communication loss alone must not imply termination.

## 3.3 Activity

The activity states are:

```text
IDLE
BUSY
```

`RUNNING` belongs to the Task state machine.

A valid combination is:

```text
Agent health = ALIVE
Activity     = BUSY

T001 = RUNNING
T002 = QUEUED
```

## 3.4 Communication State

The Agent communication states are:

```text
CONNECTING
CONNECTED
DEGRADED
OFFLINE_WAIT
SYNCHRONIZING
```

The general path is:

```text
CONNECTING
    │
    ▼
CONNECTED
    │
    │ communication failure
    ▼
DEGRADED
   /    \
  /      \
recovery  failure threshold reached
 │             │
 ▼             ▼
CONNECTED   OFFLINE_WAIT
                │
                │ reconnect
                ▼
            CONNECTING
                │
                ▼
          SYNCHRONIZING
                │
                ▼
            CONNECTED
```

Communication state is independent from Agent health, activity, Session
state, and Task state.

## 3.5 Runtime Information

The Agent may keep lightweight state such as:

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

Recent identifier history should be bounded.

The Agent keeps the information required for continuity and recovery; the C2
maintains the complete historical record.

---

# 4. Session

A **Session** is one logical communication episode for an Agent.

A Session is distinct from:

```text
Agent
→ persistent identity

Session
→ communication episode

Connection
→ transport connection
```

## 4.1 Session States

```text
CONNECTING
     │
     ▼
 CONNECTED
   /     \
  ▼       ▼
DISCONNECTED  CLOSED
```

| State | Meaning |
|---|---|
| `CONNECTING` | Session establishment is in progress |
| `CONNECTED` | Communication for this Session is active |
| `DISCONNECTED` | The Session's connection has been lost |
| `CLOSED` | The Session has been deliberately or orderly ended |

`DISCONNECTED` and `CLOSED` are terminal states for that Session.

The Session record remains available for history.

## 4.2 New Connection Rule

> **Every new successful transport Connection creates a new Session. A previous Session is never revived.**

Example:

```text
Agent A001
   │
   ├── S041 → CLOSED
   ├── S042 → DISCONNECTED
   └── S043 → CONNECTED
```

The transition is therefore:

```text
S042 = DISCONNECTED
        │
        │ new connection
        ▼
S043 = CONNECTED
```

never:

```text
S042 = DISCONNECTED
        │
        │ reconnect
        ▼
S042 = CONNECTED
```

A `previous_session_id` in `REGISTER` is historical context only.

## 4.3 Agent Relationship

One Agent may have many Sessions:

```text
Agent A001
   ├── S041
   ├── S042
   ├── S043
   └── ...
```

```text
Agent 1 ─── * Session
```

The C2 may maintain:

```text
active_session_id?
last_session_id
```

When no Session is active:

```text
active_session_id = null
last_session_id   = S043
```

A later connection can then create S044 without modifying S043.

---

# 5. Liveness

Liveness mechanisms are distinct from Session lifecycle.

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

A Beacon may report lightweight operational information such as:

```text
activity_state
current_task_id?
queued_task_count
last_task_id?
last_result_id?
```

The C2 may update `last_seen`, `last_beacon`, and related runtime information.

## 5.2 Ping / Pong

`PING/PONG` provides an active immediate connectivity check:

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

The distinction is:

```text
BEACON / BEACON_ACK
→ routine periodic communication

PING / PONG
→ immediate connectivity verification
```

A `PONG` does not itself reconcile Task or Result state.

---

# 6. Task

A **Task** represents one logical operation requested for an Agent.

A Task belongs to an Agent, not to a Session.

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
├── created_session_id?
├── last_session_id?
├── ack_deadline
├── execution_deadline
├── timeout_reason?
├── result_id?
└── error?
```

The detailed lifecycle is defined in
[`task-lifecycle.md`](task-lifecycle.md).

## 6.1 Task Ownership and Sessions

The relationship is:

```text
Agent 1 ─── * Task
```

`created_session_id` and `last_session_id`, where used, record communication
history only.

A Task may therefore span Sessions:

```text
T002
 │
 ├── created through S042
 ├── remains queued after S042 disconnects
 └── executed through S043
```

Another valid case is:

```text
T001
 │
 ├── RUNNING through S042
 ├── completes while disconnected
 ├── R001 retained locally
 └── R001 transmitted through S043
```

## 6.2 Task States

```text
PENDING
   │
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
  /    \
 ▼      ▼
COMPLETED  FAILED
```

Additional final states are:

```text
TIMEOUT
CANCELLED
```

Complete set:

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

## 6.3 Task Acknowledgement and Recovery

`TASK_ACK` means that the Agent has received, validated, and accepted the
Task for execution or queuing.

Therefore:

```text
WAITING_ACK
      │
      ▼
   QUEUED
```

A missing ACK does not prove Task failure.

Recovery is:

```text
ACK timeout
     ↓
   PING
     ↓
   PONG
     ↓
TASK_STATUS_QUERY
     ↓
TASK_STATUS
```

The C2 must not blindly retransmit a Task after an uncertain ACK.

Redispatch may be considered after confirmation that the Agent considers the
Task `UNKNOWN`, subject to retry and duplicate-protection rules.

---

# 7. Result

A **Result** represents data or an outcome produced by a Task.

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

A Result belongs logically to its Task.

```text
Task T001
   └── Result R001
```

The Task → Result cardinality remains `1 → 0..1 / *` until the execution
model is finalized.

## 7.1 Cross-Session Results

The Session recorded with a Result identifies the communication context in
which the Result was received.

Example:

```text
T001
 │
 ├── execution through S042
 ├── S042 disconnects
 ├── R001 produced locally
 └── R001 transmitted through S043
```

A lost Result must not cause the Task to be executed again.

The C2 can instead recover the state with:

```text
TASK_STATUS_QUERY
       ↓
TASK_STATUS(COMPLETED, R001)
```

## 7.2 Result Deduplication

`result_id` uniquely identifies the logical Result.

A retransmitted Result therefore remains the same Result and must not create a
second logical record.

An unknown referenced Task must not be silently invented; the Result should
instead be treated as unmatched/unexpected.

---

# 8. Message

A **Message** is one protocol-level communication unit.

Conceptually:

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

The exact wire format is defined in [`protocol.md`](protocol.md).

## 8.1 Identifier and Correlation

`message_id` identifies the protocol Message.

For example:

```text
T001
 ├── M100 TASK
 ├── M101 TASK_ACK
 ├── M102 TASK_STATUS
 └── M103 RESULT
```

A Message may concern a Task created through an earlier Session:

```text
T002 created through S042
        │
        ▼
S042 disconnects
        │
        ▼
S043 established
        │
        └── Message concerning T002
```

The Message's `session_id` records the communication context.

It does not redefine Task ownership.

## 8.2 Message Router

The C2's Message Router dispatches Messages to the appropriate subsystem:

```text
MESSAGE
   │
   ▼
Message Router
   │
   ├── REGISTER ───────────► Agent Manager
   ├── BEACON ─────────────► Agent / Session handling
   ├── TASK_ACK ───────────► Task Manager
   ├── TASK_STATUS ────────► Task Manager
   ├── RESULT ─────────────► Result Manager
   ├── SYNC_STATE ─────────► Synchronization Manager
   └── FILE_* ─────────────► File Manager
```

The Router does not own domain state.

---

# 9. Identifiers

The identifiers have distinct meanings:

| Identifier | Meaning |
|---|---|
| `agent_id` | persistent Agent identity |
| `session_id` | one communication Session |
| `task_id` | one logical Task |
| `result_id` | one Result |
| `transfer_id` | one File Transfer |
| `message_id` | one protocol Message |
| `event_id` | one Event |

They must not be conflated:

```text
agent_id    ≠ session_id
task_id     ≠ message_id
result_id   ≠ task_id
transfer_id ≠ message_id
```

This allows one Task to span multiple Sessions and Messages:

```text
T001
 │
 ├── M100 / S042
 ├── M101 / S042
 │
 ├── communication loss
 │
 ├── M102 / S043
 └── M103 / S043
```

---

# 10. Synchronization

Synchronization reconciles Agent and C2 state after communication recovery.

It takes place through a **new Session**.

The sequence is:

```text
new connection
      ↓
new Session
      ↓
SYNCHRONIZING
      ↓
state reconciliation
      ↓
SYNC_COMPLETE
      ↓
normal operation
```

## 10.1 Reconnection Protocol

A returning Agent may provide the previous Session for context:

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

                            reconcile

SYNC_STATE_RESPONSE
◄────────────────────────────────────────

SYNC_COMPLETE
◄────────────────────────────────────────
```

The historical Session remains unchanged:

```text
S042 = DISCONNECTED
S043 = current Session
```

## 10.2 Synchronization State

The Agent may provide:

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

The C2 may respond with:

```text
SYNC_STATE_RESPONSE
{
    task_updates,
    tasks_to_send,
    tasks_to_cancel?,
    results_needed?
}
```

Exact fields and conflict-resolution rules remain open.

Synchronization restores **operational state**; it does not restore Session
identity.

---

# 11. File Transfer

A **File Transfer** represents the logical movement of a file.

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

A Task may have zero or more associated File Transfers:

```text
Task T002
   ├── F001
   ├── F002
   └── ...
```

Transfer Messages are correlated with `transfer_id`:

```text
FILE_START
      │
      ▼
FILE_CHUNK
      │
      ▼
FILE_CHUNK
      │
      ▼
FILE_END
```

The logical Transfer remains distinct from the individual Messages carrying
its data.

---

# 12. Storage

Structured application state and file data are stored separately.

```text
                Application State
                       │
                       ▼
               Database Interface
                       │
                       ▼
                    SQLite
```

Structured data includes:

```text
agents
sessions
tasks
results
file transfers
events
```

Actual file contents use:

```text
                  File Data
                     │
                     ▼
           File Storage Interface
                     │
                     ▼
                 Filesystem
```

This separates logical file-transfer metadata from physical file data.

---

# 13. Event

An **Event** represents an operational occurrence.

Examples include:

```text
agent registration
session establishment
session disconnection
session closure
beacon reception
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

A Message describes protocol communication; an Event records what happened
operationally.

---

# 14. Entity Relationships and Cardinalities

The principal relationships are:

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
 └── correlate relevant entities
```

Current conceptual cardinalities:

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

A Session does not own Tasks.

Task references to Sessions are communication-history metadata only.

---

# 15. Persistence and Runtime State

The implementation should distinguish:

### Persistent State

```text
Agent identity
Session history
Task history
Result history
Transfer metadata
Relevant event history
```

### Active State

```text
active Session
communication state
pending/running/queued Tasks
active File Transfers
synchronization state
```

### Temporary State

```text
partial file transfer
temporary file
intermediate synchronization data
```

The conceptual entity model does not require every runtime attribute to be
persisted permanently.

For example:

```text
A001
active_session_id = S043
```

is runtime information, while historical records remain persistent:

```text
S042 = DISCONNECTED
S043 = CONNECTED
```

---

# 16. Reliability and Offline Operation

Communication state and execution state are independent.

A running Task may continue while communication is unavailable:

```text
T001 = RUNNING
communication = OFFLINE_WAIT
```

A completed Result may therefore remain locally pending:

```text
T001 → COMPLETED
R001 → pending locally
```

Queued work remains paused during communication-loss recovery.

After a new Session is established, synchronization handles pending Results
and Task reconciliation before normal queued execution resumes.

This implements the principle:

```text
communication failure
        ≠
execution failure
```

---

# 17. Consistency Rules

The implementation should preserve:

```text
A Task must reference a known Agent.

A Session must reference an Agent.

A File Transfer must reference its intended Agent.

A Result should reference the Task from which it originated.

A correlated Message must use identifiers belonging to the correct Agent.

A Task-related Message may use a different Session from the Task's
creation Session.

A RESULT must not silently create an unknown Task.

A new Connection must create a new Session.

A Session in DISCONNECTED or CLOSED must not return to CONNECTED.

Communication loss alone must not imply Agent termination.

Duplicate protocol delivery must not create duplicate logical Tasks or Results
or cause unsafe duplicate execution.
```

These rules may be enforced through application validation, persistence
constraints, or both.

---

# 18. Normative State-Transition Table

This table is the authoritative cross-entity reference.

The terms **MUST**, **MUST NOT**, and **MAY** are normative.

| Entity / Context | Current State | Trigger | Required Transition / Behavior | Resulting State |
|---|---|---|---|---|
| Session | `CONNECTING` | successful registration/session establishment | C2 MUST create a new Session for the new connection | `CONNECTED` |
| Session | `CONNECTED` | connection lost | C2 MUST retain the Session record and mark it disconnected | `DISCONNECTED` |
| Session | `CONNECTED` | orderly/explicit termination | Session MUST be finalized as deliberately ended | `CLOSED` |
| Session | `DISCONNECTED` | new connection | C2 MUST create a new Session; it MUST NOT revive the old Session | new Session `CONNECTED` |
| Session | `CLOSED` | new connection | C2 MUST create a new Session; the closed Session MUST remain closed | new Session `CONNECTED` |
| Agent health | `UNKNOWN` | valid `REGISTER` | C2 MUST recognize/create the Agent identity and mark it reachable | `ALIVE` |
| Agent health | `ALIVE` | repeated failed communication checks | C2 MAY transition the Agent to an unreachable state according to configured liveness policy | `LIKELY_UNREACHABLE` |
| Agent health | `LIKELY_UNREACHABLE` | valid communication resumes | C2 MUST update the Agent as reachable | `ALIVE` |
| Agent health | any non-terminal health state | communication loss alone | System MUST NOT infer `TERMINATED` solely from communication loss | unchanged / liveness-driven |
| Agent communication | `CONNECTING` | registration accepted | Agent enters synchronization when required | `SYNCHRONIZING` |
| Agent communication | `SYNCHRONIZING` | reconciliation completed | Agent MUST NOT resume normal queued work before synchronization completes | `CONNECTED` |
| Agent communication | `CONNECTED` | missed/lost expected response | Agent MAY retry communication and MUST NOT immediately enter offline mode | `DEGRADED` after retry/recovery policy |
| Agent communication | `DEGRADED` | communication recovery succeeds | Agent resumes normal communication | `CONNECTED` |
| Agent communication | `DEGRADED` | recovery policy exhausted | Agent MUST stop normal beaconing/new queued work and enter recovery mode | `OFFLINE_WAIT` |
| Agent communication | `OFFLINE_WAIT` | reconnect attempt succeeds | Agent MUST establish a new connection and synchronization phase | `CONNECTING` → `SYNCHRONIZING` |
| Agent communication | `OFFLINE_WAIT` | reconnect attempt fails | Agent MUST remain in recovery mode and MAY retry later | `OFFLINE_WAIT` |
| Task | `PENDING` | C2 dispatches Task | C2 MUST record dispatch and begin acknowledgement tracking | `WAITING_ACK` |
| Task | `WAITING_ACK` | valid `TASK_ACK` | C2 MUST record task acceptance | `QUEUED` |
| Task | `QUEUED` | Agent starts execution | Agent SHOULD report `TASK_STATUS(RUNNING)` and MUST update local execution state | `RUNNING` |
| Task | `RUNNING` | successful execution / valid result | C2 MUST associate and persist the Result | `COMPLETED` |
| Task | `RUNNING` | execution failure | C2 MUST distinguish execution failure from communication failure | `FAILED` |
| Task | `WAITING_ACK` | ACK timeout | C2 MUST enter recovery and MUST NOT blindly redispatch the Task | recovery / unresolved |
| Task | `RUNNING` | execution timeout | C2 MAY use status recovery before finalizing the Task as timed out | `TIMEOUT` when finalized |
| Task | `WAITING_ACK` / unresolved | `PONG` received | C2 MUST use `TASK_STATUS_QUERY` to determine the Task state rather than assuming failure | recovered state |
| Task | any recoverable state | `TASK_STATUS` received | C2 MUST reconcile its Task state with the reported valid Agent state | reported/reconciled state |
| Task | `WAITING_ACK` | `TASK_STATUS(UNKNOWN)` | C2 MAY consider redispatch subject to retry policy and duplicate protection | policy-dependent |
| Task | any non-final state | communication loss | Agent MUST NOT automatically cancel a running Task solely because communication was lost | task state preserved |
| Task | `RUNNING` during communication loss | local execution completes | Agent MUST retain the Result locally if C2 is unreachable | local completed/pending result |
| Task | `QUEUED` during communication loss | communication unavailable | Agent MUST NOT start new queued C2-originated work | `QUEUED` / paused |
| Result | locally pending | new communication available | Agent MUST retain Result identity and transmit it during recovery/synchronization | pending → synchronized |
| Result | received by C2 | duplicate `result_id` | C2 MUST NOT create a second logical Result | unchanged |
| Message | any | duplicate `message_id` | Receiver MUST detect duplicates where deduplication is applicable and MUST NOT repeat unsafe processing | unchanged |
| Task | any | duplicate `task_id` | Agent MUST use logical Task identity to prevent unintended duplicate execution | unchanged / deduplicated |
| Synchronization | `SYNCHRONIZING` | `SYNC_STATE` exchanged | C2 and Agent MUST reconcile relevant Task/Result state before normal queued execution resumes | synchronized |
| Synchronization | `SYNCHRONIZING` | pending Result known to C2 already | C2 MUST NOT create a duplicate Result solely because Agent reports it as pending | synchronized |
| Synchronization | `SYNCHRONIZING` | C2 Task unknown to Agent | C2 MAY redispatch the Task after confirming it is unknown | normal Task lifecycle |
| Synchronization | `SYNCHRONIZING` | Agent Task unknown to C2 | C2 MUST NOT silently create and execute an unknown Task solely from Agent state | unresolved/anomalous |
| Synchronization | `SYNCHRONIZING` | explicit C2 cancellation vs queued Agent Task | Where cancellation is supported, the explicit cancellation decision MAY override queued local work | `CANCELLED` |
| File Transfer | active | `FILE_CHUNK` | Receiver MUST associate the chunk with the correct `transfer_id` | transfer remains active |
| File Transfer | active | `FILE_END` | Receiver MUST finalize and verify the transfer before marking it complete | completed transfer |

### Normative cross-state rules

```text
1. A new transport Connection MUST create a new Session.

2. A Session in DISCONNECTED or CLOSED MUST NOT return to CONNECTED.

3. Agent identity MUST survive Session changes.

4. Tasks MUST belong logically to Agents, not Sessions.

5. A Task MAY be communicated through multiple Sessions.

6. A Result MAY be produced during one Session or while disconnected and
   transmitted through a later Session.

7. Communication failure MUST NOT automatically be interpreted as
   execution failure.

8. The C2 MUST NOT blindly retransmit a Task after a lost TASK_ACK.

9. A running Task MUST NOT be automatically cancelled solely because
   communication with the C2 was lost.

10. Queued Tasks MUST NOT normally begin while the Agent is in
    communication-loss recovery mode.

11. Results produced while the C2 is unreachable MUST be retained locally
    until they can be synchronized.

12. Reconnection MUST create a new Session and MUST be followed by
    synchronization before normal queued work resumes.

13. Synchronization MUST reconcile state; it MUST NOT revive the previous
    Session.

14. Identifier semantics MUST remain distinct:
    agent_id, session_id, task_id, result_id, transfer_id, message_id,
    and event_id identify different logical objects.

15. Duplicate protocol delivery MUST NOT cause duplicate logical Task,
    Result, or unsafe Task execution.
```

---

# 19. Domain Model vs Implementation

The conceptual entities do not imply one-to-one database tables or Python
objects.

A typical mapping may be:

```text
Domain Entity
     │
     ▼
Persistence / Runtime Model
     │
     ▼
Database or in-memory representation
```

Likewise:

```text
Task
  │
  ▼
TASK protocol structure
  │
  ▼
serialized Message
```

Database-specific fields, indexes, foreign keys, normalization, and runtime
objects remain implementation details.

---

# 20. Open Questions

The following remain to be finalized:

- exact fields for each entity;
- exact runtime Connection representation;
- identifier format and generation;
- database keys and indexes;
- exact Task → Result cardinality;
- Agent health thresholds;
- communication retry policy;
- `OFFLINE_WAIT` reconnect interval;
- Beacon interval and jitter;
- timeout values;
- duplicate-retention size;
- synchronization payload;
- synchronization conflict resolution;
- Result recovery mechanism;
- Task cancellation behavior;
- authentication and registration mechanism;
- serialization format;
- File Transfer retry/resume behavior;
- Event persistence and retention;
- runtime/persistent state synchronization;
- exact mapping between protocol, domain, and database models.

These decisions should be resolved before the persistence and protocol
implementations are considered stable.

Significant architectural or protocol decisions should be recorded in
[`DECISIONS.md`](../DECISIONS.md).
