# `docs/protocol.md`

```markdown
# Protocol Specification

> **Status: Work in Progress**
>
> This document describes the current protocol design between the C2 server
> and agents. Message structures and fields may evolve as implementation
> requirements are clarified.

## 1. Purpose

The protocol defines the logical messages exchanged between the C2 server
and agents.

It is intentionally separated from the transport layer:

> **Protocol = what is exchanged**

> **Transport = how it is transmitted**

The current mandatory transport is TCP/TLS.

---

## 2. Protocol Responsibilities

The protocol layer is responsible for:

- defining message types;
- defining message structure;
- serializing messages;
- deserializing received messages;
- validating message structure;
- associating messages with agents, tasks, sessions, and transfers.

The protocol does not manage sockets or implement C2 business logic.

---

## 3. Message Envelope

Messages are expected to contain common metadata allowing the receiving side
to identify and process them correctly.

The current conceptual envelope is:

```text
Message
├── version
├── message_id
├── agent_id
├── type
├── timestamp
└── payload
```

The exact field types and serialization format remain to be defined.

---

## 4. Message Types

The current architecture identifies the following logical message types:

```text
REGISTER
BEACON
TASK
RESULT
FILE_START
FILE_CHUNK
FILE_END
ERROR
```

These message types are described at a conceptual level below.

---

## 5. `REGISTER`

Used when an agent establishes its identity with the C2 server.

Conceptually, registration may provide information such as:

```text
agent_id
hostname
operating_system
architecture
agent information
```

The exact registration contract remains to be defined.

---

## 6. `BEACON`

Used for the agent's periodic communication cycle.

A beacon may communicate the agent's current state and provide an opportunity
for the server to deliver pending work.

The exact beacon contents and timing behaviour remain to be defined.

---

## 7. `TASK`

Represents a task sent by the C2 server to an agent.

Conceptually:

```text
TASK
├── task_id
├── agent_id
├── command_type
└── parameters
```

The agent should validate the task before passing it to the execution layer.

---

## 8. `RESULT`

Represents the outcome of an executed task.

Conceptually:

```text
RESULT
├── result_id
├── task_id
├── agent_id
├── status
├── timestamp
└── data
```

The C2 server uses the task identifier to associate the result with the
corresponding task.

---

## 9. File Transfer Messages

File transfers are represented separately from ordinary results.

The current conceptual sequence is:

```text
FILE_START
    ↓
FILE_CHUNK
    ↓
FILE_CHUNK
    ↓
...
    ↓
FILE_END
```

File-transfer details are documented separately in
[`file-transfer.md`](file-transfer.md).

---

## 10. `ERROR`

Represents a protocol, processing, or execution error.

The final structure should provide enough information to identify the
associated operation without unnecessarily exposing sensitive internal data.

---

## 11. Message Validation

Received messages must be validated before being passed to application logic.

Conceptually:

```text
Network Input
      ↓
Transport
      ↓
Message Deserialization
      ↓
Validation
      ↓
Application Logic
```

Validation should verify, where applicable:

- message type;
- required fields;
- field types;
- identifiers;
- message structure;
- protocol version;
- payload constraints.

Invalid messages should be rejected in a controlled manner.

---

## 12. Message Correlation

Identifiers are required to associate related operations.

The architecture currently expects relationships such as:

```text
Agent
  │
  └── Task
        │
        └── Result
```

File transfers similarly require their own transfer identity so that individual
transfer messages can be associated with the correct operation.

The exact identifier and correlation strategy remains to be finalized.

---

## 13. Versioning

The protocol contains a version field so that protocol evolution can be
handled explicitly.

Future changes to message structures should consider compatibility between
the C2 server and agent.

The exact versioning policy remains to be defined.

---

## 14. Serialization

Serialization converts internal protocol objects into their transmissible
representation.

Deserialization performs the reverse operation.

The exact serialization format has not yet been finalized.

---

## 15. Transport Independence

The logical protocol should remain independent of the underlying transport.

Conceptually:

```text
                    Protocol
                       │
             ┌─────────┴─────────┐
             ▼                   ▼
         TCP/TLS              Other
          (MVP)            transports
```

A new transport should not require redesigning the logical message model.

---

## 16. Open Questions

The following remain to be finalized:

- exact message envelope;
- serialization format;
- exact field types;
- protocol versioning policy;
- authentication / agent identity mechanism;
- error message structure;
- timeout and retry semantics;
- exact file-transfer metadata.

These questions should be resolved before the protocol implementation is
considered stable.
```

---

# `docs/task-lifecycle.md`

```markdown
# Task Lifecycle

> **Status: Work in Progress**
>
> This document describes the current conceptual task model. State
> transitions and implementation details may evolve during development.

## 1. Purpose

Tasks represent operations requested by the operator and executed by agents.

The task system separates:

- task creation;
- task scheduling;
- task delivery;
- task execution;
- result handling.

This separation is required to support multiple agents and asynchronous
operation.

---

## 2. Task Ownership

The lifecycle is divided between the C2 server and the agent.

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
          └── generate result
```

The server manages the lifecycle while the agent performs the requested
operation.

---

## 3. Task States

The current conceptual lifecycle is:

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

### `PENDING`

The task has been created but has not yet been successfully delivered to
the agent.

### `SENT`

The task has been dispatched by the C2 server.

### `RUNNING`

The agent has accepted the task and is executing the associated operation.

### `COMPLETED`

The operation finished successfully and a corresponding result can be
associated with the task.

### `FAILED`

The task could not be completed successfully.

The exact distinction between delivery failure, execution failure, timeout,
and cancellation remains to be finalized.

---

## 4. Task Structure

A task is conceptually associated with:

```text
task_id
agent_id
command_type
parameters
created_at
sent_at
completed_at
status
```

Additional fields may be introduced if required by the final implementation.

---

## 5. Task Creation

The general creation flow is:

```text
Operator
    ↓
Interface
    ↓
C2 Core
    ↓
Task Manager
    ↓
Task = PENDING
```

The interface should not directly create network messages.

The Task Manager owns the logical task lifecycle.

---

## 6. Task Dispatch

When a task is ready to be delivered:

```text
Task Manager
    ↓
Protocol
    ↓
Transport
    ↓
Agent
```

The transport layer is responsible only for communication.

The protocol layer represents the task as a protocol message.

---

## 7. Agent-Side Processing

Once received:

```text
TASK
  ↓
Protocol validation
  ↓
Executor
  ↓
Command Handler
  ↓
Execution
```

The agent should validate the received task before passing it to the
execution layer.

---

## 8. Result Handling

After execution:

```text
Command
   ↓
Executor
   ↓
Result
   ↓
Agent Protocol
   ↓
Transport
   ↓
C2 Protocol
   ↓
Result Manager
```

The C2 server associates the result with its originating task.

```text
Agent
  │
  └── Task T004
        │
        └── Result R009
```

---

## 9. Multiple Agents

The task system is designed to support independent tasks for different
agents.

Conceptually:

```text
A001 → [T004, T005]
A002 → [T006]
A003 → [T007, T008]
```

A task belonging to one agent should not block unrelated task processing for
another agent.

This is part of the asynchronous multi-agent architecture.

---

## 10. Failure Handling

The final implementation should define behaviour for situations such as:

- agent unavailable;
- communication failure;
- task timeout;
- invalid task;
- execution failure;
- malformed result;
- unexpected result;
- duplicate result.

The current architecture only establishes the principal `FAILED` state.
Detailed failure states and recovery rules remain to be finalized.

---

## 11. Task and Result Relationship

A task should have a stable identifier used to associate its result.

Conceptually:

```text
Task T004
   │
   └── Result R009
```

This provides traceability from the operator request to the resulting
execution data.

---

## 12. Open Questions

The following remain to be finalized:

- exact state machine;
- timeout semantics;
- retry behaviour;
- cancellation behaviour;
- task queue implementation;
- task prioritization;
- duplicate task handling;
- duplicate result handling;
- persistence rules for each state.
```

---

# `docs/file-transfer.md`

```markdown
# File Transfer

> **Status: Work in Progress**
>
> This document describes the current conceptual file-transfer design.
> Transfer states, metadata, storage rules, and protocol details may evolve
> during implementation.

## 1. Purpose

File transfer is treated as a dedicated application concern rather than as
an ordinary task result.

The design separates:

1. file-transfer management;
2. file storage;
3. transport protection;
4. file integrity verification.

---

## 2. Responsibilities

The main responsibilities are divided as follows:

```text
File Manager
    │
    ├── transfer lifecycle
    ├── transfer state
    ├── transfer metadata
    └── transfer completion
             │
             ▼
     File Storage Interface
             │
             ▼
        Filesystem Storage
```

The File Manager does not own the physical storage implementation.

---

## 3. Transfer Messages

The current protocol design uses:

```text
FILE_START
FILE_CHUNK
FILE_END
```

A complete transfer therefore follows conceptually:

```text
FILE_START
     ↓
FILE_CHUNK
     ↓
FILE_CHUNK
     ↓
...
     ↓
FILE_END
```

The exact fields of each message will be defined in the protocol
specification.

---

## 4. Why Chunking?

Files should be processed incrementally rather than requiring the complete
file to remain in memory.

Conceptually:

```text
chunk
  ↓
process
  ↓
write
  ↓
next chunk
  ↓
...
```

This provides a more scalable transfer mechanism for larger test files.

---

## 5. C2-Side Storage

The C2 server maintains a dedicated file workspace:

```text
data/
└── files/
    ├── uploads/
    ├── downloads/
    └── temporary/
```

Conceptually:

```text
uploads/
    Files received by the C2 server.

downloads/
    Files prepared for transfer to agents.

temporary/
    Temporary files used while processing transfers.
```

The storage implementation is separated:

```text
storage/
├── database/
└── files/
    ├── interface.py
    └── filesystem.py
```

---

## 6. Agent-Side Storage

The agent uses the same conceptual organization:

```text
data/
└── files/
    ├── uploads/
    ├── downloads/
    └── temporary/
```

with a file-storage abstraction under:

```text
storage/
└── files/
    ├── interface.py
    └── filesystem.py
```

The agent therefore maintains a controlled local workspace for transfer-related
files.

---

## 7. Upload and Download Semantics

The terms `upload` and `download` describe the direction relative to the
component performing the operation.

### Agent → C2

Conceptually:

```text
Agent File
    ↓
Agent File Handling
    ↓
Protocol
    ↓
TLS Transport
    ↓
C2 Protocol
    ↓
C2 File Manager
    ↓
Temporary File
    ↓
Integrity Verification
    ↓
C2 File Storage
```

### C2 → Agent

Conceptually:

```text
C2 File Storage
    ↓
C2 File Manager
    ↓
Protocol
    ↓
TLS Transport
    ↓
Agent Protocol
    ↓
Temporary File
    ↓
Integrity Verification
    ↓
Agent File Storage
```

---

## 8. Transfer Metadata

A transfer should have a distinct identity so that multiple simultaneous
transfers can be distinguished.

Conceptually:

```text
transfer_id
agent_id
filename
size
status
hash
created_at
completed_at
storage_path
```

The exact metadata model remains to be finalized.

---

## 9. Temporary Files

Incoming file data should first be written to a temporary workspace.

Conceptually:

```text
Incoming Chunks
      ↓
Temporary File
      ↓
Transfer Completion
      ↓
Integrity Verification
      ↓
Final File
```

If validation fails, the incomplete or invalid temporary artifact should not
be promoted to the final storage location.

Temporary files should be cleaned up when no longer required.

---

## 10. Integrity Verification

File integrity is treated separately from transport confidentiality.

The intended mechanism is a cryptographic hash such as SHA-256.

```text
Original File
     ↓
   SHA-256
     ↓
   Transfer
     ↓
Reconstructed File
     ↓
   SHA-256
     ↓
  Compare
```

A mismatch indicates that the reconstructed content does not match the
expected content.

The exact point at which the expected hash is transmitted and validated
remains part of the protocol design.

---

## 11. Encryption in Transit

File transfers use the same protected communication channel as other C2-Agent
traffic.

```text
File
  ↓
Protocol
  ↓
TLS
  ↓
Encrypted Network
  ↓
TLS
  ↓
File
```

Application-level encryption of individual files is not required for the MVP
solely to provide confidentiality during network transmission.

---

## 12. Encryption at Rest

Encryption at rest is considered separately from encryption in transit.

Current decision:

```text
Encryption in transit
    → TLS

File integrity
    → cryptographic hash

Application-level encryption at rest
    → not mandatory for MVP
```

Additional encryption at rest may be considered later as a defense-in-depth
feature.

---

## 13. Path Handling

Externally supplied file names and paths must not be trusted directly.

The implementation should ensure that transfer-related paths remain inside
the intended file-storage workspace.

Path validation is therefore part of the security requirements of the
transfer subsystem.

---

## 14. Failure Scenarios

The implementation should define behaviour for:

- interrupted transfers;
- missing chunks;
- unexpected chunks;
- duplicate chunks;
- invalid transfer identifiers;
- storage failures;
- integrity-check failures;
- invalid file metadata;
- incomplete temporary files.

The detailed transfer state machine remains to be finalized.

---

## 15. Open Questions

The following remain to be decided:

- exact transfer state machine;
- chunk numbering;
- transfer ordering guarantees;
- expected hash representation;
- resumable transfers;
- retry behaviour;
- maximum transfer size;
- temporary-file naming;
- cleanup policy;
- exact protocol fields.
```

---

# `docs/data-model.md`

```markdown
# Data Model

> **Status: Work in Progress**
>
> This document describes the current conceptual domain model. Fields,
> relationships, and persistence details may change as the implementation is
> designed.

## 1. Purpose

The system contains several central domain objects shared conceptually
between the C2 server, the agent, and the protocol.

The main objects currently identified are:

```text
Agent
Session
Task
Result
Message
File Transfer
```

The purpose of this document is to describe their conceptual relationships
before the final database schema is implemented.

---

# 2. Agent

An **Agent** represents the persistent identity of an endpoint running the
agent software.

Conceptually:

```text
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

An Agent is distinct from a Session.

---

# 3. Session

A **Session** represents a communication instance associated with an Agent.

Conceptually:

```text
Agent A001
    │
    └── Session S42
          ├── connection state
          ├── transport
          └── communication state
```

An agent may therefore have multiple sessions over time.

For example:

```text
Agent A001
    │
    ├── Session S01
    │      └── disconnected
    │
    └── Session S02
           └── active
```

The exact session lifecycle remains to be defined.

---

# 4. Task

A **Task** represents an operation requested for an Agent.

Conceptually:

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

The task lifecycle is documented in
[`task-lifecycle.md`](task-lifecycle.md).

---

# 5. Result

A **Result** represents data returned after a Task has been processed.

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

The primary relationships are:

```text
Agent
  │
  └── Task
        │
        └── Result
```

This provides traceability between an agent, its task, and the resulting data.

---

# 6. Message

A **Message** represents a protocol-level communication unit.

Conceptually:

```text
Message
├── version
├── message_id
├── agent_id
├── type
├── timestamp
└── payload
```

Messages are exchanged between the C2 server and agent.

A message may represent:

```text
REGISTER
BEACON
TASK
RESULT
FILE_START
FILE_CHUNK
FILE_END
ERROR
```

The detailed protocol is documented in [`protocol.md`](protocol.md).

---

# 7. File Transfer

A **File Transfer** represents the logical lifecycle of a file being transferred
between the C2 server and an Agent.

Conceptually:

```text
File Transfer
├── transfer_id
├── agent_id
├── filename
├── size
├── status
├── hash
├── created_at
├── completed_at
└── storage_path
```

A transfer may be associated with a Task where appropriate.

---

# 8. Relationships

The current conceptual model is:

```text
                    ┌───────────┐
                    │   Agent   │
                    └─────┬─────┘
                          │
              ┌───────────┴───────────┐
              │                       │
              ▼                       ▼
        ┌───────────┐          ┌───────────┐
        │  Session  │          │   Task    │
        └───────────┘          └─────┬─────┘
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

A more detailed model will be established once the database schema is
designed.

---

# 9. Identifiers

The architecture currently distinguishes several identifiers:

```text
agent_id
session_id
task_id
result_id
message_id
transfer_id
```

The purpose is to allow operations occurring concurrently to be associated
with the correct entity.

Identifiers should not be reused across unrelated entity types.

---

# 10. Persistence

The C2 server separates structured data from file contents.

```text
Structured Data
      ↓
Database Interface
      ↓
SQLite
```

while actual file contents use:

```text
File Data
    ↓
File Storage Interface
    ↓
Filesystem
```

Potential structured entities include:

```text
agents
sessions
tasks
results
file_transfers
events
```

The final database schema remains to be defined.

---

# 11. In-Memory vs Persistent State

Not every piece of information necessarily needs to be treated identically.

The implementation should distinguish between:

- persistent domain information;
- active communication/session state;
- temporary transfer state;
- temporary file data.

For example:

```text
Agent identity
    → persistent

Session connection state
    → potentially active/in-memory + persistent metadata

Task history
    → persistent

Temporary file reconstruction
    → filesystem workspace
```

The exact persistence policy remains to be finalized.

---

# 12. Open Questions

The following remain to be decided:

- exact fields for each entity;
- primary keys;
- relationships and foreign keys;
- session persistence strategy;
- task/result cardinality;
- file-transfer/task relationship;
- event/log persistence;
- indexes;
- retention policy;
- synchronization between in-memory state and persistent state.

These decisions should be made before the final database implementation is
considered stable.
```

I deliberately kept these as **working specifications**, not as "final truth". That matches the state of the project: we already have concrete concepts such as `REGISTER`, `BEACON`, `TASK`, `RESULT`, file-transfer messages, the task lifecycle, and the `Agent → Session / Task → Result` model, but several exact contracts were explicitly still open in the material you gave me.

One structural point I would keep: **don't move these details back into `ARCHITECTURE.md` later just because they're becoming more precise**. The architecture should stay at the system/component level; these files are precisely where the detailed specifications should mature.
