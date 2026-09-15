# Reconnection and Synchronization

> **Status:** Work in Progress  
> **Scope:** Defines how an Agent reconnects to the C2 after communication loss and how C2 and Agent reconcile their state.  
> **Related documents:** `data-model.md`, `state-machines.md`, `protocol.md`, `protocol-state-transition.md`, `task-lifecycle.md`

---

## 1. Purpose

The C2-AUTOMATED system must tolerate temporary communication loss without confusing communication failure with task failure.

An Agent may:

- lose its connection to the C2;
- reconnect later through a new communication session;
- complete a previously running Task while disconnected;
- retain Results locally until they can be transmitted;
- retain knowledge of queued or recently completed Tasks.

The C2 must therefore be able to reconstruct the Agent's current state and reconcile it with its own historical state.

The synchronization mechanism exists to:

1. establish a new Session;
2. identify the Agent;
3. exchange relevant recovery state;
4. reconcile differences;
5. recover missing Results;
6. avoid duplicate Task execution;
7. resume normal operation.

---

# 2. Core Principles

The following principles are normative.

### 2.1 A reconnection creates a new Session

A disconnected Session is never reopened.

```text
S041 CONNECTED
      │
      │ communication loss
      ▼
S041 DISCONNECTED

      │
      │ reconnect
      ▼

S042 CONNECTING
      │
      ▼
S042 CONNECTED
```

The new Session belongs to the same Agent but represents a new communication episode.

---

### 2.2 Communication state is not execution state

Communication loss does not automatically modify the state of a Task.

For example:

```text
Agent:
    T001 = RUNNING

connection lost

Agent:
    T001 = RUNNING

connection restored

Agent:
    T001 = COMPLETED
    R001 = available
```

The C2 must not interpret the connection loss itself as:

```text
RUNNING → FAILED
```

or:

```text
RUNNING → CANCELLED
```

unless an independent Task rule explicitly causes that transition.

---

### 2.3 Agent-local state is retained for recovery

The Agent must retain enough information to report what happened while disconnected.

At minimum, this includes:

- current Task;
- queued Task identifiers;
- recently processed Task identifiers;
- pending Result identifiers;
- recently processed message identifiers.

The exact persistence mechanism is an implementation detail.

---

### 2.4 Synchronization occurs before normal operation resumes

After a new connection is established, the Agent enters:

```text
SYNCHRONIZING
```

Normal queued work should not resume until synchronization has completed.

```text
REGISTER
   │
   ▼
REGISTER_ACK
   │
   ▼
SYNCHRONIZING
   │
   ▼
SYNC_STATE
   │
   ▼
RECONCILIATION
   │
   ▼
SYNC_COMPLETE
   │
   ▼
CONNECTED
```

---

# 3. Reconnection Lifecycle

The complete reconnection lifecycle is:

```text
                 communication loss
                        │
                        ▼
              ┌──────────────────┐
              │ Previous Session  │
              │   DISCONNECTED    │
              └────────┬─────────┘
                       │
                       │ reconnect
                       ▼
              ┌──────────────────┐
              │  New Session     │
              │   CONNECTING     │
              └────────┬─────────┘
                       │
                       │ REGISTER
                       ▼
              ┌──────────────────┐
              │  Session         │
              │   CONNECTED      │
              └────────┬─────────┘
                       │
                       │ registration accepted
                       ▼
              ┌──────────────────┐
              │ SYNCHRONIZING    │
              └────────┬─────────┘
                       │
                       │ state exchange
                       ▼
              ┌──────────────────┐
              │  Reconciliation  │
              └────────┬─────────┘
                       │
                       │ synchronization complete
                       ▼
              ┌──────────────────┐
              │ Normal Operation │
              │    CONNECTED     │
              └──────────────────┘
```

The Session itself remains governed by the Session state machine defined in `state-machines.md`. `SYNCHRONIZING` is an **Agent communication state**, not a Session state.

---

# 4. Registration During Reconnection

When an Agent reconnects, it sends a `REGISTER` message.

Conceptually:

```text
REGISTER {
    agent_id
    previous_session_id?
    hostname
    operating_system
    architecture
    agent_information
}
```

The `previous_session_id` is optional historical context.

It does **not** mean:

> reopen this Session.

Instead, it means:

> this Agent believes its previous communication episode was associated with this Session.

The C2 remains responsible for creating the new Session.

---

## 4.1 C2 Registration Processing

Upon receiving a valid `REGISTER`:

1. validate the message;
2. identify or create the Agent;
3. create a **new Session**;
4. associate the Session with the Agent;
5. return `REGISTER_ACK`;
6. provide the new `session_id`;
7. initiate synchronization.

Example:

```text
Agent A001

previous:
    S041 = DISCONNECTED

new connection:
    REGISTER(A001, previous_session_id=S041)

C2:
    create S042

REGISTER_ACK:
    session_id=S042

Agent:
    SYNCHRONIZING
```

The previous Session remains historical.

---

# 5. Synchronization State Machine

Synchronization is represented by the Agent communication state:

```text
CONNECTING
     │
     │ REGISTER accepted
     ▼
SYNCHRONIZING
     │
     │ state exchange
     ▼
CONNECTED
```

A synchronization failure does not create a new semantic Session.

If communication is lost during synchronization:

```text
SYNCHRONIZING
       │
       │ communication loss
       ▼
OFFLINE_WAIT
       │
       │ reconnect
       ▼
CONNECTING
       │
       ▼
new Session
       │
       ▼
SYNCHRONIZING
```

The incomplete synchronization is abandoned and performed again on the next connection.

---

# 6. Synchronization Protocol

The baseline synchronization exchange is:

```text
Agent                         C2
  │                            │
  │ REGISTER                   │
  │───────────────────────────>│
  │                            │
  │ REGISTER_ACK(session_id)   │
  │<───────────────────────────│
  │                            │
  │ SYNC_STATE                 │
  │───────────────────────────>│
  │                            │
  │ SYNC_STATE_RESPONSE        │
  │<───────────────────────────│
  │                            │
  │ SYNC_COMPLETE              │
  │<───────────────────────────│
  │                            │
  │ normal operation           │
  │<──────────────────────────>│
```

The exact transport-level framing is defined by `protocol.md`.

This document defines the **recovery semantics**, not the serialization format.

---

# 7. Agent Synchronization State

The Agent sends a `SYNC_STATE` message containing enough information for the C2 to determine what happened while communication was unavailable.

The baseline information is:

```text
agent_id

current_task_id?
current_task_status?

queued_task_ids

pending_result_ids

recent_task_ids
recent_message_ids

last_task_id?
last_result_id?

activity_state
```

This is intentionally a compact recovery summary rather than a complete database dump.

The exact fields remain implementation-level and may evolve.

---

# 8. C2 Synchronization State

The C2 already maintains its historical state for the Agent.

Relevant information includes:

- known Tasks;
- Task states;
- known Results;
- Sessions;
- last known communication;
- queued Tasks;
- cancellation state where supported;
- missing Results;
- historical Events.

The C2 uses the Agent's synchronization state to identify discrepancies.

---

# 9. Reconciliation

Reconciliation compares the two views of the Agent's state.

Conceptually:

```text
          ┌───────────────┐
          │ Agent State   │
          └───────┬───────┘
                  │
                  │
                  ▼
          ┌───────────────┐
          │ Reconciliation│
          │    Logic      │
          └───────┬───────┘
                  │
          ┌───────┴────────┐
          │                │
          ▼                ▼
   C2 needs information   Agent needs information
          │                │
          ▼                ▼
   Results / status       Tasks / updates
```

Reconciliation must be **idempotent**: repeating the synchronization exchange must not create duplicate Tasks, Results, or executions.

---

# 10. Reconciliation Rules

## 10.1 C2 knows a Task, Agent knows the Task

The systems compare their known state.

Example:

```text
C2:
    T001 = RUNNING

Agent:
    T001 = COMPLETED
    R001 = pending
```

The Agent's completion evidence must be considered.

The C2 can then update:

```text
T001 → COMPLETED
```

and request or receive:

```text
R001
```

---

## 10.2 C2 knows a Task, Agent does not

The C2 must not automatically assume that the Task was executed.

Possible causes include:

- Agent state was lost;
- Task was never received;
- local state was cleaned;
- synchronization information is incomplete.

The reconciliation policy must determine whether the Task should be:

- redispatched;
- cancelled;
- marked as requiring recovery;
- or otherwise handled.

The current architecture does not mandate automatic redispatch.

---

## 10.3 Agent knows a Task, C2 does not

The Agent must not silently create a new C2 Task record from an unknown Task.

The situation should be recorded as an inconsistency or orphaned Task reference and handled by explicit recovery logic.

This prevents an arbitrary local identifier from becoming an unverified C2 operation.

---

## 10.4 C2 expects a Result, Agent has the Result

The Agent provides the Result.

```text
C2:
    T001 = COMPLETED
    R001 = missing

Agent:
    R001 = available
```

The Result can then be transmitted and stored.

---

## 10.5 Agent has a Result, C2 has never seen it

The Result is not sufficient to invent a new Task.

The C2 should treat it as an **unmatched/orphan Result** until its relationship with a known Task can be established.

---

## 10.6 Both sides already know the Result

If the same `result_id` is already stored by the C2, retransmission must not create a second Result record.

```text
R001 received
R001 received again

→ one logical Result
```

---

# 11. Task Recovery After Reconnection

Task recovery is closely related to synchronization but remains governed by `task-lifecycle.md`.

The key cases are:

### Case A — Task completed while offline

```text
T001 = RUNNING

connection lost

Agent:
    T001 = COMPLETED
    R001 = pending

connection restored

sync

C2:
    T001 = COMPLETED
    R001 received
```

No second execution occurs.

---

### Case B — Task was queued while offline

A queued Task must not begin merely because the Agent reconnects.

The synchronization process first determines whether the Task remains valid.

After synchronization:

```text
QUEUED → RUNNING
```

may occur during normal Task processing.

---

### Case C — Task status is uncertain

Example:

```text
C2:
    T001 = RUNNING

Agent:
    T001 = UNKNOWN
```

The C2 should attempt status recovery before assuming failure.

Possible sequence:

```text
PING
  ↓
PONG
  ↓
TASK_STATUS_QUERY(T001)
  ↓
TASK_STATUS(T001)
```

The Task is only assigned a final state according to the resulting evidence and Task lifecycle rules.

---

# 12. Missing Acknowledgement Recovery

A lost `TASK_ACK` must not automatically cause the C2 to resend the Task.

Example:

```text
C2 → Agent:
    TASK T001

Agent:
    accepts T001
    sends TASK_ACK

TASK_ACK is lost

C2:
    T001 = WAITING_ACK
```

The C2 should first attempt to determine whether the Task was actually accepted.

Baseline recovery:

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

If the Agent reports:

```text
QUEUED
RUNNING
COMPLETED
FAILED
```

the C2 reconciles its Task state accordingly.

Only an explicitly permitted recovery policy may cause redispatch.

This prevents:

```text
TASK T001
   ↓
accepted by Agent
   ↓
ACK lost
   ↓
TASK resent
   ↓
T001 executed twice
```

---

# 13. Missing Result Recovery

A Result may be successfully generated but fail to reach the C2.

Example:

```text
Agent:
    T001 = COMPLETED
    R001 = stored locally

connection lost

C2:
    T001 = RUNNING
    R001 = unknown
```

After reconnection, synchronization identifies:

```text
Agent:
    R001 pending
```

The Agent retransmits the Result.

The C2 stores it using `result_id` as the logical identity.

Repeated transmission must remain idempotent.

---

# 14. Queued Tasks

Tasks queued by the C2 while an Agent is unavailable remain associated with that Agent.

They should not be considered delivered merely because they exist in the C2 database.

Conceptually:

```text
C2:
    T001 = PENDING

Agent offline

T001 remains:
    PENDING
```

After reconnection and synchronization:

```text
C2 → Agent:
    TASK T001

Agent:
    TASK_ACK

T001:
    WAITING_ACK → QUEUED
```

The exact transition depends on the dispatch implementation described in `task-lifecycle.md`.

The important invariant is:

> A queued Task must not be silently treated as executed or acknowledged before the Agent has accepted it.

---

# 15. Synchronization Response

The C2's `SYNC_STATE_RESPONSE` may contain the information required to reconcile both sides.

Baseline conceptual structure:

```text
SYNC_STATE_RESPONSE {
    task_updates
    tasks_to_send
    tasks_to_cancel?
    results_needed?
}
```

Examples:

```text
task_updates:
    T001 → COMPLETED

tasks_to_send:
    T002

results_needed:
    R001
```

The exact representation is implementation-dependent.

---

# 16. Synchronization Completion

Synchronization is complete only after the required reconciliation actions have been processed.

The C2 then sends:

```text
SYNC_COMPLETE
```

The Agent transitions from:

```text
SYNCHRONIZING
```

to:

```text
CONNECTED
```

Normal operation can resume.

Conceptually:

```text
REGISTER
   ↓
REGISTER_ACK
   ↓
SYNCHRONIZING
   ↓
SYNC_STATE
   ↓
SYNC_STATE_RESPONSE
   ↓
reconciliation
   ↓
SYNC_COMPLETE
   ↓
CONNECTED
```

---

# 17. Duplicate Protection

Synchronization can involve retransmission.

Therefore:

### Message level

`message_id` identifies one protocol message.

Receiving the same `message_id` again must not cause an unintended duplicate transition.

### Task level

`task_id` identifies one logical Task.

Receiving a Task with an already-known `task_id` must not create a second Task execution.

### Result level

`result_id` identifies one logical Result.

Receiving the same Result again must not create a duplicate Result record.

### Session level

A new connection always receives a new `session_id`.

A previous Session identifier is never reused.

---

# 18. C2 Restart

The C2 may restart while Agents are offline.

Persistent C2 state must survive the restart where the implementation supports persistence.

Historical Sessions remain historical.

Example:

```text
Before restart:

A001
 ├── S041 CLOSED
 └── S042 DISCONNECTED

C2 restarts

After Agent reconnects:

A001
 ├── S041 CLOSED
 ├── S042 DISCONNECTED
 └── S043 CONNECTED
```

The C2 does not reopen `S042`.

The new Session performs normal registration and synchronization.

---

# 19. Agent Restart

An Agent may also restart.

Where persistent local state is available, the Agent should retain enough recovery information to report:

- its persistent `agent_id`;
- previously known Tasks;
- pending Results;
- relevant deduplication identifiers.

After restart:

```text
Agent starts
    ↓
connects
    ↓
REGISTER
    ↓
new Session
    ↓
SYNCHRONIZING
    ↓
reconciliation
```

An Agent restart does not imply that every previously running Task failed.

The final Task state depends on what evidence the Agent can provide and on the Task execution model.

---

# 20. Communication Loss During Synchronization

Communication can fail before synchronization completes.

Example:

```text
REGISTER
   ↓
REGISTER_ACK
   ↓
SYNC_STATE
   ↓
connection lost
```

The incomplete synchronization must not be treated as successful.

The Agent enters its offline recovery behavior.

When it reconnects:

```text
new Session
   ↓
REGISTER
   ↓
SYNCHRONIZING
   ↓
synchronization repeated
```

Because reconciliation is idempotent, repeating the process is safe.

---

# 21. Synchronization Invariants

The following invariants must hold.

### Session invariant

```text
One connection episode → one Session
```

### Identity invariant

```text
One Agent → persistent agent_id
```

### Task invariant

```text
One logical Task → one task_id
```

### Result invariant

```text
One logical Result → one result_id
```

### Recovery invariant

```text
Communication loss ≠ Task failure
```

### Execution invariant

```text
Missing ACK ≠ permission to execute the Task again
```

### Result invariant

```text
Missing Result ≠ permission to execute the Task again
```

### Synchronization invariant

```text
Synchronization must be repeatable without
creating duplicate logical objects or executions.
```

### Session history invariant

```text
A previous Session is never reopened.
```

---

# 22. Canonical Recovery Scenario

The following scenario combines the principal mechanisms without redefining them.

```text
Agent A001
    │
    │ S041 CONNECTED
    │
    │ TASK T001
    ▼
T001 = RUNNING

    │
    │ connection lost
    ▼

S041 = DISCONNECTED

    │
    │ Agent continues execution
    ▼

T001 = COMPLETED
R001 = locally stored

    │
    │ reconnect
    ▼

S042 = CONNECTING

    │
    │ REGISTER
    ▼

REGISTER_ACK(S042)

    │
    ▼

SYNCHRONIZING

    │
    │ SYNC_STATE
    │
    │ T001 = COMPLETED
    │ R001 = pending
    ▼

C2 reconciliation

    │
    ├── T001 → COMPLETED
    │
    └── request/accept R001
             │
             ▼
          R001 stored

    │
    ▼

SYNC_COMPLETE

    │
    ▼

CONNECTED
```

The important result is that the Task is **not executed again**.

---

# 23. Failure and Recovery Matrix

| Situation | Immediate interpretation | Recovery |
|---|---|---|
| Connection lost | Communication unavailable | Session → `DISCONNECTED`; Agent enters recovery |
| ACK lost | Task acceptance uncertain | Query status before redispatch |
| Result lost | Execution result delivery uncertain | Recover Result; do not re-execute automatically |
| Agent reconnects | New communication episode | Create new Session |
| Sync interrupted | Synchronization incomplete | Repeat on next Session |
| C2 restarts | Historical state may be recovered from persistence | Reconnect and synchronize |
| Agent restarts | Local execution state may be partially retained | Register and synchronize |
| Unknown Task from Agent | Inconsistent state | Do not silently create Task |
| Unknown Result from Agent | Unmatched evidence | Do not silently create Task |
| Duplicate message | Already processed protocol event | Ignore or safely acknowledge according to message semantics |
| Duplicate Task | Same logical Task | Do not execute twice |
| Duplicate Result | Same logical Result | Do not create duplicate record |

---

# 24. Responsibilities by Component

| Component | Responsibility |
|---|---|
| `Agent` | Maintain local recovery state |
| `SessionManager` | Create and track Sessions |
| `AgentManager` | Identify and manage Agents |
| `TaskManager` | Maintain Task lifecycle and recovery |
| `ResultManager` | Store and reconcile Results |
| `SynchronizationManager` | Coordinate synchronization and reconciliation |
| `MessageRouter` | Route synchronization messages to the appropriate component |
| `Protocol` | Encode, decode and validate synchronization messages |
| `Storage` | Persist C2 recovery state |
| `Transport` | Provide communication without owning synchronization semantics |

The `SynchronizationManager` coordinates reconciliation but does not replace the domain managers responsible for Tasks, Results, Agents, or Sessions.

---

# 25. Relationship to Other Documents

| Document | Responsibility |
|---|---|
| `data-model.md` | Entities, identifiers and relationships |
| `state-machines.md` | Authoritative state definitions and transitions |
| `protocol.md` | Protocol messages and logical message format |
| `protocol-state-transition.md` | Mapping protocol messages to state changes |
| `reconnection-and-synchronization.md` | Reconnection and state reconciliation |
| `task-lifecycle.md` | Detailed Task execution and recovery |
| `file-transfer.md` | File transfer lifecycle and recovery |
| `network-architecture.md` | Network topology and communication architecture |
| `testing-strategy.md` | Verification of reconnection and synchronization behavior |

This document should not duplicate the complete Task lifecycle or protocol catalogue.

---

# 26. Open Questions

The following details remain implementation decisions:

- How much Agent state must survive an Agent process restart?
- How long should recent `task_id` and `message_id` identifiers be retained?
- What exact conflict-resolution algorithm should synchronization use?
- How should a C2-side `CANCELLED` Task interact with a locally queued or running Task?
- What should happen when local Agent state is corrupted?
- What synchronization timeout should be applied?
- Should synchronization itself use acknowledgements for each phase?
- How should large numbers of pending Results be synchronized?
- Should synchronization support pagination/batching?
- What is the exact policy for redispatching a Task whose state remains `UNKNOWN`?
- Which synchronization events should be persisted in the Event log?

These questions can be resolved during implementation without changing the core architecture defined here.
