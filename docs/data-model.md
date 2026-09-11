# Data Model

> **Status: Work in Progress**
>
> This document describes the current conceptual data model of
> C2-AUTOMATED. Entity fields, relationships, persistence rules, and
> implementation details may evolve as the architecture and protocol are
> finalized.

---

# 1. Purpose

C2-AUTOMATED uses several central entities to represent agents,
communication sessions, tasks, results, messages, and file transfers.

The purpose of this document is to define the **conceptual relationships**
between these entities before the final implementation and database schema
are established.

The current primary entities are:

```text id="p0yeo1"
Agent
Session
Task
Result
Message
File Transfer
```

These entities exist at the application level. Their exact representation in
Python classes, database models, or protocol structures may differ.

---

# 2. Domain Overview

The current conceptual model can be summarized as:

```text id="0lu3mm"
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
                    File Transfer
```

Protocol messages transport information related to these entities:

```text id="drxfo4"
Application Entity
       │
       ▼
Protocol Message
       │
       ▼
Transport
```

---

# 3. Agent

An **Agent** represents the persistent identity of an endpoint running the
agent software.

An agent is not equivalent to a network connection. Its identity is intended
to remain stable across communication sessions.

Conceptually:

```text id="r9h2u3"
Agent
├── agent_id
├── hostname
├── operating_system
├── architecture
├── address
├── status
├── last_seen
└── transport
```

The exact fields remain to be finalized.

## 3.1 Agent Identity

`agent_id` uniquely identifies the agent from the C2 server's perspective.

The identity mechanism itself has not yet been finalized.

## 3.2 Agent State

The server may maintain state associated with an agent, such as:

- online/offline state;
- last communication;
- platform information;
- current transport;
- other operational metadata.

The exact state model remains to be defined.

---

# 4. Session

A **Session** represents a communication instance associated with an Agent.

The current architectural distinction is:

> **Agent = persistent identity**

> **Session = communication instance**

Conceptually:

```text id="5bu9z3"
Agent A001
    │
    ├── Session S01
    │     └── disconnected
    │
    └── Session S02
          └── active
```

An agent can therefore have multiple sessions over its lifetime.

## 4.1 Session Information

A session may contain information such as:

```text id="om4qly"
session_id
agent_id
connection state
transport
created_at
last_activity
```

The exact fields and lifecycle states remain to be finalized.

## 4.2 Session and Agent Relationship

Conceptually:

```text id="jq6a7f"
One Agent
    │
    └── multiple Sessions over time
```

A session should not replace or redefine the persistent identity of the
agent.

---

# 5. Task

A **Task** represents an operation requested for a specific agent.

The C2 server creates and manages tasks while the agent performs them.

Conceptually:

```text id="9m7p3o"
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

The detailed task lifecycle is documented in
[`task-lifecycle.md`](task-lifecycle.md).

## 5.1 Task Ownership

A task belongs logically to one target agent.

```text id="h83gkp"
Agent A001
   │
   ├── Task T001
   ├── Task T002
   └── Task T003
```

Another agent has its own independent tasks:

```text id="wsg9io"
Agent A002
   │
   └── Task T004
```

---

# 6. Result

A **Result** represents the outcome or data returned after a task has been
processed.

Conceptually:

```text id="n3cgqn"
Result
├── result_id
├── task_id
├── agent_id
├── status
├── timestamp
└── data
```

A result is associated with the task that produced it.

```text id="8r0yki"
Agent
  │
  └── Task T004
        │
        └── Result R009
```

This relationship provides traceability between the requested operation and
the returned information.

The exact result structure depends on the type of operation performed.

---

# 7. Message

A **Message** represents a protocol-level unit exchanged between the C2
server and an agent.

A conceptual message envelope is:

```text id="opba3w"
Message
├── version
├── message_id
├── agent_id
├── type
├── timestamp
└── payload
```

The message is not itself equivalent to the domain object represented inside
its payload.

For example:

```text id="q9gkq8"
Task
  ↓
TASK Message
  ↓
Transport
```

and:

```text id="ij40ft"
Result
  ↓
RESULT Message
  ↓
Transport
```

The detailed protocol is documented in
[`protocol.md`](protocol.md).

---

# 8. File Transfer

A **File Transfer** represents the logical lifecycle of a file being
transferred between the C2 server and an agent.

Conceptually:

```text id="egp7lz"
File Transfer
├── transfer_id
├── agent_id
├── task_id
├── filename
├── size
├── status
├── hash
├── created_at
├── completed_at
└── storage_path
```

Not every transfer must necessarily be associated with a task in the same
way. The exact relationship will be finalized during protocol and database
design.

The detailed transfer design is documented in
[`file-transfer.md`](file-transfer.md).

---

# 9. Entity Relationships

The current conceptual relationships are:

```text id="oaj07j"
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
                                      ▼
                               ┌─────────────┐
                               │   Result    │
                               └─────────────┘

                    Agent
                      │
                      ▼
               ┌─────────────┐
               │File Transfer│
               └─────────────┘
```

At a high level:

```text id="1e5vlz"
Agent
 ├── Sessions
 ├── Tasks
 └── File Transfers

Task
 └── Result
```

The exact cardinalities are still to be finalized.

---

# 10. Identifiers

The current model distinguishes the following identifiers:

| Identifier | Purpose |
|---|---|
| `agent_id` | Identifies an agent |
| `session_id` | Identifies a communication session |
| `task_id` | Identifies a task |
| `result_id` | Identifies a result |
| `message_id` | Identifies a protocol message |
| `transfer_id` | Identifies a file transfer |

These identifiers allow concurrent operations to be associated with the
correct entity.

The exact format and generation mechanism for identifiers remain to be
defined.

---

# 11. Task and Result Relationship

The task/result relationship is one of the most important relationships in
the model.

```text id="d5b2ur"
Task T004
    │
    └── Result R009
```

The `task_id` carried by a result allows the C2 server to identify the task
associated with the returned data.

This provides a traceable chain:

```text id="vrwq4i"
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

The exact cardinality between tasks and results remains open until the
execution/result model is finalized.

---

# 12. Agent and Session Relationship

The distinction between Agent and Session is intentional.

```text id="6f1j2q"
Agent A001
    │
    ├── Session S01
    │
    ├── Session S02
    │
    └── Session S03
```

A session represents the state of communication at a particular point in
time, while the agent represents the persistent identity.

This allows the server to retain information about an agent after a
communication session terminates.

---

# 13. Message and Entity Relationship

Messages carry representations of application-level entities across the
communication boundary.

Conceptually:

```text id="rj7xqe"
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

The protocol therefore acts as the boundary between domain objects and
network communication.

---

# 14. File Transfer and Storage

A File Transfer represents the logical transfer operation, while storage
represents where the actual bytes are persisted.

```text id="rptn34"
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

---

# 15. Persistence Model

The C2 server separates structured application state from actual file
contents.

```text id="m31dqo"
                Application State
                       │
                       ▼
               Database Interface
                       │
                       ▼
                    SQLite
```

Examples of structured data include:

```text id="9wkxwp"
agents
sessions
tasks
results
file transfers
events
```

Actual file contents are persisted through the file-storage abstraction:

```text id="dy64o8"
                  File Data
                     │
                     ▼
           File Storage Interface
                     │
                     ▼
                 Filesystem
```

This separation is reflected in the server architecture:

```text id="w7pwu4"
c2_server/
├── storage/
│   ├── database/
│   └── files/
│
└── data/
    └── files/
```

---

# 16. In-Memory and Persistent State

Not every piece of information needs to have the same lifetime.

The implementation should distinguish between:

### Persistent state

Information that should survive a process restart where appropriate.

Examples:

```text id="3u2q9y"
agent identity
task history
result history
transfer metadata
```

### Active state

Information required while a communication session or operation is active.

Examples:

```text id="1w8q9d"
active session state
pending task state
active transfer state
```

### Temporary state

Information that only exists while processing an operation.

Examples:

```text id="5h36kf"
partial file transfer
temporary file
intermediate reconstruction data
```

The exact persistence policy remains to be determined.

---

# 17. Events

The architecture also anticipates operational events such as:

```text id="z2h6b0"
agent registration
session establishment
session termination
task creation
task dispatch
task completion
task failure
result reception
file transfer events
errors
```

These events may be logged and, if required, persisted.

Whether events belong in the primary database model or only in application logs
remains an open design question.

---

# 18. Domain Model vs Database Model

The conceptual entities in this document should not automatically be treated
as one-to-one representations of database tables.

For example:

```text id="go19t5"
Domain Entity
     │
     ▼
Persistence Model
     │
     ▼
Database
```

The final implementation may introduce database-specific fields, indexes, or
relationships that are not part of the conceptual domain model.

The same applies to protocol representations.

---

# 19. Consistency Rules

The final implementation should preserve several basic consistency rules.

Examples include:

```text id="kt1qxh"
A Task must reference a known Agent.

A Result must reference the Task from which it originated.

A Session must reference an Agent.

A File Transfer must reference its intended Agent.

A protocol Message must have a valid message identifier.

A file-transfer message must reference the correct transfer.
```

The exact validation and enforcement mechanisms remain to be defined.

---

# 20. Current Design Summary

The current model can be summarized as:

```text id="ea4vth"
                           Agent
                            │
             ┌──────────────┼──────────────┐
             │              │              │
             ▼              ▼              ▼
          Sessions         Tasks       File Transfers
                            │
                            ▼
                         Results
```

Messages represent the protocol-level exchange of information concerning
these entities:

```text id="e0gh9e"
Domain Object
      ↓
Protocol Message
      ↓
Transport
      ↓
Remote Component
```

The model therefore keeps a distinction between:

```text id="7dn6u6"
Identity
  → Agent

Communication
  → Session

Requested operation
  → Task

Execution output
  → Result

Network representation
  → Message

File movement
  → File Transfer

Physical persistence
  → Storage
```

---

# 21. Open Questions

The following points remain to be finalized:

- exact fields for each entity;
- identifier format and generation;
- primary keys;
- foreign keys;
- entity cardinalities;
- session persistence strategy;
- task/result cardinality;
- file-transfer/task relationship;
- whether every result must correspond to exactly one task;
- event persistence;
- synchronization between in-memory and persistent state;
- database indexes;
- data-retention rules;
- exact database schema;
- relationship between protocol models and domain models.

These decisions should be resolved before the final persistence model is
considered stable.

Significant decisions should be recorded in
[`DECISIONS.md`](../DECISIONS.md).
