# Requirements Mapping

> **Status: Work in Progress**
>
> This document maps the project requirements to the current architecture,
> implementation areas, documentation, and validation strategy.
>
> The mapping is intentionally maintained throughout development. As
> implementation decisions are finalized, the relevant entries should be
> updated.

---

# 1. Purpose

The purpose of this document is to maintain traceability between:

```text
Project Requirement
        ↓
Architecture
        ↓
Implementation
        ↓
Testing / Validation
```

This makes it possible to verify that each requirement has:

- an identified architectural component;
- an intended implementation location;
- a corresponding documentation reference;
- a defined validation approach.

The document also distinguishes mandatory requirements from optional extensions and open design decisions.

It is a traceability document rather than a replacement for the detailed architecture, protocol, lifecycle, security, or testing specifications.

---

# 2. Requirement Status

The following status categories are used:

| Status | Meaning |
|---|---|
| `Required` | Mandatory project requirement |
| `Planned` | Intended implementation, but not yet implemented |
| `In Progress` | Currently being implemented |
| `Implemented` | Implemented in the repository |
| `Validated` | Implemented and successfully tested |
| `Bonus` | Optional extension |
| `Open` | Requirement or implementation detail still requires clarification |
| `Accepted` | Requirement/risk is intentionally accepted within the project scope |
| `Out of Scope` | Explicitly not addressed by the project |

A requirement may have both a **project priority** and an **implementation status**.

For example:

```text
Required / Planned
Required / In Progress
Required / Validated
Bonus / Planned
```

---

# 3. Global Project Requirements

The project is based on an authorized laboratory C2 server / Agent architecture.

The major expected capabilities are:

```text
C2 Server
Agent
Multi-agent management
Asynchronous communication
Task execution
Result handling
File transfer
Secure communication
Linux support
Operator interface
Persistence
Security controls
Documentation
Testing and validation
```

The project also contains optional extensions:

```text
Windows Agent
TUI
Web interface
Additional transports
```

Mandatory functionality must be implemented and validated before bonus features are prioritized.

---

# 4. C2 Server

**Requirement:** Provide a functional C2 server capable of managing Agents and coordinating supported operations.

**Priority:** Required

**Status:** Planned

## Architecture

```text
C2 Server
├── Interface
├── Core
├── Protocol
├── Transport
├── Storage
├── File Management
├── Logging
└── Configuration
```

The C2 is structured as a modular monolith for the MVP.

Primary Core components include:

```text
AgentManager
SessionManager
TaskManager
ResultManager
FileManager
MessageRouter
SynchronizationManager
```

## Implementation

```text
c2_server/
├── main.py
├── interface/
├── core/
├── protocol/
├── transport/
├── storage/
├── data/
├── logging/
├── config/
└── tests/
```

Main entry point:

```text
c2_server/main.py
```

## Documentation

- `ARCHITECTURE.md`
- `docs/network-architecture.md`
- `docs/data-model.md`
- `DECISIONS.md`

## Validation

The C2 must:

- start successfully;
- initialize its required components;
- accept supported Agent connections;
- manage multiple Agents;
- create and manage Sessions;
- manage Tasks and Results;
- support the implemented MVP operator workflow.

---

# 5. Agent

**Requirement:** Provide a deployable Agent.

**Priority:** Required

**Status:** Planned

## Architecture

```text
Agent
├── Core
├── Beacon
├── Protocol
├── Transport
├── Executor
├── Commands
├── Platform
├── Storage
└── Tests
```

## Implementation

```text
agent/
├── core/
├── beacon/
├── protocol/
├── transport/
├── executor/
├── commands/
├── platform/
├── storage/
├── data/
└── tests/
```

## Documentation

- `ARCHITECTURE.md`
- `docs/network-architecture.md`
- `docs/data-model.md`

## Validation

The Agent must be able to:

- start in the supported laboratory environment;
- establish a communication connection with the C2;
- register itself;
- synchronize state;
- receive supported Tasks;
- execute supported operations;
- return Results;
- recover from supported communication interruptions.

---

# 6. Multi-Agent Management

**Requirement:** The C2 server must support multiple Agents simultaneously.

**Priority:** Required

**Status:** Planned

## Architecture

Primary components:

```text
c2_server/core/agent_manager.py
c2_server/core/session_manager.py
```

The architecture explicitly distinguishes persistent Agent identity from individual communication Sessions.

Conceptually:

```text
C2 Server
   │
   ├── Agent A001
   │      ├── Session S041
   │      ├── Session S042
   │      └── Session S043
   │
   ├── Agent A002
   │      └── Session S044
   │
   └── Agent A003
          └── Session S045
```

A single Agent may therefore have multiple historical Sessions.

## Implementation

```text
c2_server/core/agent_manager.py
c2_server/core/session_manager.py
```

## Documentation

- `docs/data-model.md`
- `docs/state-machines.md`
- `docs/network-architecture.md`

## Validation

Tests must verify:

- multiple Agents can coexist;
- Agents remain distinguishable;
- Sessions remain associated with the correct Agent;
- Tasks remain associated with the correct Agent;
- one Agent cannot incorrectly modify another Agent's state;
- simultaneous communication does not mix Agent state.

---

# 7. Asynchronous Communication

**Requirement:** Support asynchronous communication and independent multi-Agent operation.

**Priority:** Required

**Status:** Planned

## Architecture

The communication stack separates:

```text
Protocol
   ↓
Transport
```

while Task management remains independent from the underlying transport.

The conceptual model is:

```text
Agent A001 → independent communication / Tasks
Agent A002 → independent communication / Tasks
Agent A003 → independent communication / Tasks
```

The C2 uses explicit components for message routing and synchronization.

## Implementation

Primary areas:

```text
c2_server/core/session_manager.py
c2_server/core/task_manager.py
c2_server/core/message_router.py
c2_server/core/synchronization_manager.py

c2_server/transport/
agent/beacon/
agent/transport/
```

## Documentation

- `docs/network-architecture.md`
- `docs/state-machines.md`
- `docs/reconnection-and-synchronization.md`
- `docs/task-lifecycle.md`

## Validation

Tests should verify that:

- multiple Agents can communicate concurrently;
- one active Task does not block unrelated Agent activity;
- Task queues remain associated with the correct Agents;
- communication failure affecting one Session does not incorrectly terminate unrelated Sessions;
- multiple Agents can perform independent synchronization and Task handling.

The exact concurrency implementation remains an implementation decision.

---

# 8. Agent Registration, Session Establishment and Beaconing

**Requirement:** The Agent must establish communication with the C2, register its identity, and participate in the periodic communication cycle.

**Priority:** Required

**Status:** Planned

## Architecture

The connection lifecycle is:

```text
New connection
      ↓
New Session
      ↓
Session = CONNECTING
      ↓
Transport established
      ↓
Session = CONNECTED
      ↓
REGISTER
      ↓
Agent communication = SYNCHRONIZING
      ↓
State reconciliation
      ↓
SYNC_COMPLETE
      ↓
Agent communication = CONNECTED
```

The important distinction is:

```text
Session state
      ≠
Agent communication state
```

`REGISTER` does not establish the Session. The Session is already `CONNECTED` when registration occurs.

## Implementation

Primary areas:

```text
agent/beacon/
agent/protocol/
agent/transport/

c2_server/core/agent_manager.py
c2_server/core/session_manager.py
c2_server/core/synchronization_manager.py
```

## Documentation

- `docs/state-machines.md`
- `docs/network-architecture.md`
- `docs/reconnection-and-synchronization.md`
- `docs/protocol-state-transition.md`

## Validation

Tests should verify:

- connection establishment;
- Session creation;
- Session state transitions;
- Agent registration;
- `REGISTER_ACK`;
- assignment of the new `session_id`;
- synchronization;
- `SYNC_COMPLETE`;
- normal Beacon communication;
- reconnection using a new Session.

---

# 9. Beacon and Liveness

**Requirement:** Provide periodic Agent-to-C2 communication and a mechanism for detecting communication degradation.

**Priority:** Required

**Status:** Planned

## Architecture

Routine communication uses:

```text
BEACON
   ↓
C2
   ↓
BEACON_ACK
```

Immediate connectivity testing uses:

```text
PING
   ↓
PONG
```

These mechanisms are distinct from Task execution.

The Agent communication state machine is:

```text
CONNECTING
CONNECTED
DEGRADED
OFFLINE_WAIT
SYNCHRONIZING
```

## Implementation

```text
agent/beacon/
agent/transport/
c2_server/transport/
c2_server/core/session_manager.py
```

## Documentation

- `docs/state-machines.md`
- `docs/network-architecture.md`
- `docs/protocol.md`

## Validation

Tests should verify:

- regular Beacon transmission;
- valid acknowledgement handling;
- lost acknowledgement handling;
- transition toward `DEGRADED`;
- transition to `OFFLINE_WAIT` according to the recovery policy;
- recovery after successful communication;
- reconnection after offline operation.

Communication loss must not automatically be interpreted as Agent termination or Task failure.

---

# 10. State Management

**Requirement:** Maintain explicit and consistent lifecycle states for Agents, Sessions, Tasks, and communication.

**Priority:** Required

**Status:** Planned

## Architecture

The project uses separate state machines for:

```text
Agent health
Agent activity
Agent communication
Session
Task
File Transfer
```

Examples:

### Session

```text
CONNECTING
    ↓
CONNECTED
   /   \
  ↓     ↓
DISCONNECTED
CLOSED
```

### Task

```text
PENDING
   ↓
WAITING_ACK
   ↓
QUEUED
   ↓
RUNNING
  /    \
FAILED COMPLETED
```

Additional terminal states:

```text
TIMEOUT
CANCELLED
```

## Implementation

State definitions are implemented through the relevant domain components and persisted through the storage layer where required.

## Documentation

- `docs/state-machines.md`
- `docs/data-model.md`
- `docs/task-lifecycle.md`
- `docs/file-transfer.md`

## Validation

Tests must verify:

- valid transitions;
- invalid transitions;
- terminal-state behaviour;
- persistence of relevant states;
- separation between Session and communication states;
- correct Task recovery behaviour.

---

# 11. State Synchronization and Reconnection

**Requirement:** The Agent and C2 must be able to recover from temporary communication loss without blindly recreating or duplicating state.

**Priority:** Required

**Status:** Planned

## Architecture

Synchronization uses:

```text
REGISTER
REGISTER_ACK
SYNC_STATE
SYNC_STATE_RESPONSE
SYNC_COMPLETE
```

Canonical flow:

```text
New connection
      ↓
REGISTER
      ↓
REGISTER_ACK(session_id)
      ↓
SYNCHRONIZING
      ↓
SYNC_STATE
      ↓
C2 reconciliation
      ↓
SYNC_STATE_RESPONSE
      ↓
SYNC_COMPLETE
```

A new connection always creates a new Session.

For example:

```text
Agent A001
 ├── S041
 ├── S042 = DISCONNECTED
 └── S043 = CONNECTED
```

## Implementation

```text
c2_server/core/synchronization_manager.py
c2_server/core/session_manager.py
agent/core/
agent/protocol/
```

## Documentation

- `docs/reconnection-and-synchronization.md`
- `docs/state-machines.md`
- `docs/data-model.md`

## Validation

Tests should verify:

- Agent reconnection;
- new Session creation;
- preservation of Agent identity;
- recovery of pending Tasks;
- delayed Results;
- duplicate-message handling;
- reconciliation of Agent and C2 state;
- no reopening of historical Sessions.

---

# 12. Task Management

**Requirement:** The system must support an asynchronous task-based execution model.

**Priority:** Required

**Status:** Planned

## Architecture

```text
Operator
   ↓
Interface
   ↓
C2 Core
   ↓
Task Manager
   ↓
Protocol
   ↓
Transport
   ↓
Agent
   ↓
Executor
```

The Task Manager manages Task lifecycle state but does not directly implement endpoint command execution.

## Authoritative Task States

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

Normal lifecycle:

```text
PENDING
   ↓
WAITING_ACK
   ↓
QUEUED
   ↓
RUNNING
   ↓
COMPLETED / FAILED
```

`UNKNOWN` is not a persistent Task state. It is a recovery/reporting condition used when execution state cannot currently be established reliably.

## Implementation

```text
c2_server/core/task_manager.py
agent/executor/
```

## Documentation

- `docs/task-lifecycle.md`
- `docs/state-machines.md`
- `docs/data-model.md`

## Validation

Tests should verify:

- Task creation;
- dispatch;
- acknowledgement;
- queuing;
- execution;
- completion;
- failure;
- timeout handling;
- cancellation;
- recovery after communication loss;
- duplicate Task protection;
- correct Agent association.

---

# 13. Command Execution

**Requirement:** The Agent must execute the supported command categories.

**Priority:** Required

**Status:** Planned

## Architecture

```text
TASK
  ↓
Task handling
  ↓
Executor
  ↓
Command implementation
  ↓
Platform-specific implementation
  ↓
Execution
  ↓
RESULT
```

Current command categories:

```text
SHELL
SYSINFO
FILES
PERSISTENCE
SELF_DESTRUCT
```

## Implementation

```text
agent/executor/
agent/commands/
agent/platform/
```

## Documentation

- `ARCHITECTURE.md`
- `docs/task-lifecycle.md`
- `DECISIONS.md`

## Validation

Tests should verify:

- supported commands are dispatched correctly;
- unsupported commands are rejected;
- parameters are validated;
- malformed Tasks do not reach execution;
- execution failures produce controlled Results;
- platform-specific implementations remain isolated.

`PERSISTENCE` and `SELF_DESTRUCT` require additional security definition before their implementation can be considered complete.

---

# 14. Result Handling

**Requirement:** Results from Agents must be returned to and managed by the C2 server.

**Priority:** Required

**Status:** Planned

## Architecture

```text
Agent
   ↓
RESULT
   ↓
Protocol
   ↓
Transport
   ↓
Message Router
   ↓
Result Manager
   ↓
Storage / Interface
```

A Result belongs to a Task.

```text
Task
  │
  └── Result
```

A Result may be transmitted later than the execution itself, including after reconnection.

## Implementation

```text
c2_server/core/result_manager.py
c2_server/core/message_router.py
agent/protocol/
```

## Documentation

- `docs/data-model.md`
- `docs/task-lifecycle.md`
- `docs/protocol.md`

## Validation

Tests should verify:

- correct Result reception;
- correct Task association;
- correct Agent association;
- Result persistence;
- delayed Results;
- duplicate Results;
- unexpected/orphan Results;
- malformed Results.

An unknown Result must not silently create a fabricated Task.

---

# 15. File Transfer

**Requirement:** Support file transfer between the C2 server and Agents.

**Priority:** Required

**Status:** Planned

## Architecture

File transfer is treated as a dedicated subsystem rather than as an ordinary Task Result.

The protocol uses:

```text
FILE_START
     ↓
FILE_CHUNK
     ↓
...
     ↓
FILE_END
```

The logical Transfer is distinct from:

```text
Agent
Session
Task
Result
```

A Transfer may be associated with a Task and may conceptually span Sessions.

## Implementation

C2:

```text
c2_server/core/file_manager.py
c2_server/storage/files/
c2_server/data/files/
```

Agent:

```text
agent/storage/files/
agent/data/files/
```

Protocol:

```text
c2_server/protocol/
agent/protocol/
```

## Documentation

- `docs/file-transfer.md`
- `docs/data-model.md`
- `ARCHITECTURE.md`

## Validation

Testing should include:

- C2 → Agent transfer;
- Agent → C2 transfer;
- multi-chunk files;
- invalid transfer metadata;
- incomplete transfers;
- communication interruptions;
- integrity verification;
- temporary-file handling;
- cleanup of failed transfers;
- controlled final-file promotion.

Exact transfer recovery and resumability behaviour remains an implementation detail tracked by the file-transfer specification.

---

# 16. File Integrity

**Requirement / Security Property:** Transferred files should be verifiable after reconstruction.

**Priority:** Required security property

**Status:** Planned

## Architecture

```text
Original File
     ↓
Integrity Value
     ↓
Transfer
     ↓
Reconstructed File
     ↓
Integrity Verification
     ↓
Valid / Invalid
```

A cryptographic hash such as SHA-256 is intended for file-integrity verification.

## Implementation

The exact code location will be determined between the File Manager and file-transfer/storage components.

The integrity check belongs to the transfer lifecycle rather than to the general Task Result model.

## Documentation

- `docs/file-transfer.md`
- `docs/countermeasures.md`

## Validation

Tests should verify:

```text
Matching integrity value
    → transfer accepted

Mismatching integrity value
    → transfer rejected / marked invalid
```

---

# 17. Secure Communication

**Requirement / Security Property:** Protect C2-Agent communication in transit.

**Priority:** Required

**Status:** Planned

## Architecture

The mandatory MVP transport is:

```text
TCP/TLS
```

```text
C2 Server
    │
    │ TLS
    ▼
  Agent
```

The protocol remains independent from the transport layer.

## Implementation

```text
c2_server/transport/
agent/transport/
```

## Documentation

- `docs/network-architecture.md`
- `docs/countermeasures.md`
- `DECISIONS.md`

## Validation

Tests should verify:

- successful TLS communication;
- invalid TLS configuration handling;
- certificate/configuration behaviour once finalized;
- failure handling;
- absence of unintended plaintext downgrade.

The exact Agent authentication mechanism remains an open security decision.

---

# 18. Protocol

**Requirement:** Define a structured communication protocol between the C2 server and Agents.

**Priority:** Required

**Status:** Planned

## Current Protocol Categories

### Registration and synchronization

```text
REGISTER
REGISTER_ACK
SYNC_STATE
SYNC_STATE_RESPONSE
SYNC_COMPLETE
```

### Liveness

```text
BEACON
BEACON_ACK
PING
PONG
```

### Task and Result

```text
TASK
TASK_ACK
TASK_STATUS
TASK_STATUS_QUERY
RESULT
```

### File Transfer

```text
FILE_START
FILE_CHUNK
FILE_END
```

### Error handling

```text
ERROR
```

## Implementation

```text
c2_server/protocol/
agent/protocol/
```

Key components include:

```text
messages.py
serializer.py
validator.py
```

## Documentation

- `docs/protocol.md`
- `docs/protocol-state-transition.md`
- `docs/state-machines.md`

## Validation

Tests should verify:

- valid messages;
- invalid messages;
- serialization/deserialization;
- required fields;
- message identifiers;
- protocol version handling;
- invalid message ordering;
- correct message/state relationships.

---

# 19. Protocol Routing and Synchronization

**Requirement:** Route incoming protocol messages to the appropriate C2 subsystem and handle Agent/C2 reconciliation.

**Priority:** Required

**Status:** Planned

## Architecture

```text
Transport
   ↓
Protocol validation
   ↓
Message Router
   ├── Agent Manager
   ├── Session Manager
   ├── Task Manager
   ├── Result Manager
   ├── File Manager
   └── Synchronization Manager
```

The `MessageRouter` is responsible for dispatching valid messages to the appropriate subsystem.

The `SynchronizationManager` is responsible for synchronization/reconciliation rather than being embedded inside generic message parsing.

## Implementation

```text
c2_server/core/message_router.py
c2_server/core/synchronization_manager.py
```

## Documentation

- `ARCHITECTURE.md`
- `docs/protocol.md`
- `docs/reconnection-and-synchronization.md`

## Validation

Tests should verify:

- valid messages reach the correct subsystem;
- invalid messages are rejected before routing;
- unrelated message types are not processed by the wrong component;
- synchronization messages trigger the expected reconciliation workflow.

---

# 20. Linux Support

**Requirement:** Support Linux Agents.

**Priority:** Required

**Status:** Planned

## Architecture

```text
Agent
  ↓
Platform Abstraction
  ↓
Linux implementation
```

Platform-specific behaviour remains separated from the common Agent architecture.

## Implementation

```text
agent/platform/
agent/commands/
```

## Validation

The complete MVP Agent must be tested in the intended Linux laboratory environment.

Tests should cover the supported command categories that are implemented for Linux.

---

# 21. Windows Support

**Requirement:** Windows Agent support.

**Priority:** Bonus

**Status:** Bonus / Future

## Architecture

```text
Platform Abstraction
     ├── Linux
     └── Windows
```

Windows-specific code should remain isolated from the common Agent components.

## Implementation

```text
agent/platform/
agent/commands/
```

## Validation

Windows support requires a dedicated authorized test environment.

It should not be considered validated merely because the platform abstraction exists.

---

# 22. Operator Interface

**Requirement:** Provide an operator interface for managing the C2.

**Priority:** Required

**Status:** Planned

## MVP

The initial interface is:

```text
CLI
```

Architecture:

```text
Operator
   ↓
CLI
   ↓
C2 Core
```

Potential extensions:

```text
TUI
Web
```

These are separate interfaces over the same C2 Core rather than separate implementations of C2 business logic.

## Implementation

```text
c2_server/interface/
├── cli/
├── tui/
└── web/
```

MVP CLI:

```text
c2_server/interface/cli/
```

## Validation

The MVP interface should allow the operator to:

- view Agents;
- inspect Sessions;
- select an Agent;
- create Tasks;
- inspect Task state;
- inspect Results;
- initiate supported file-transfer operations.

The exact CLI command set remains to be finalized.

---

# 23. Persistence

**Requirement:** Maintain relevant structured application state.

**Priority:** Required

**Status:** Planned

## Architecture

```text
Application
    ↓
Database Interface
    ↓
SQLite
```

Relevant entities include:

```text
Agents
Sessions
Tasks
Results
Transfers
Events
```

The C2 maintains the persistent historical record.

The Agent maintains only the lightweight state required for recovery and synchronization.

## Implementation

```text
c2_server/storage/database/
├── interface.py
├── sqlite.py
└── models.py
```

## Documentation

- `docs/data-model.md`
- `ARCHITECTURE.md`
- `DECISIONS.md`

## Validation

Tests should verify:

- creation;
- retrieval;
- update;
- persistence across C2 restart;
- correct relationships;
- correct handling of finalized and historical Sessions;
- Task and Result persistence;
- Transfer metadata persistence;
- Event persistence where implemented.

The exact database schema remains subject to implementation.

---

# 24. File Storage

**Requirement:** Store transferred file contents separately from structured metadata.

**Priority:** Required

**Status:** Planned

## Architecture

```text
File Manager
      ↓
File Storage Interface
      ↓
Filesystem
      ↓
data/files/
```

Structured metadata belongs in the database, while file contents belong in the filesystem storage layer.

## Implementation

C2:

```text
c2_server/storage/files/
c2_server/data/files/
```

Agent:

```text
agent/storage/files/
agent/data/files/
```

## Validation

Tests should verify:

- correct storage location;
- controlled workspace boundaries;
- file creation;
- file retrieval;
- temporary-file handling;
- cleanup;
- integrity verification;
- separation from structured database metadata.

---

# 25. Logging and Event Traceability

**Requirement / Security Property:** Provide sufficient logging and event traceability for system operation and security analysis.

**Priority:** Required

**Status:** Planned

## Architecture

The project distinguishes between:

```text
Message
    ≠
Event
```

Messages represent protocol communication.

Events represent significant state or operational occurrences.

Examples:

```text
Agent registration
Session establishment
Session disconnection
Task creation
Task completion
Result reception
File-transfer event
Protocol error
Transport error
Synchronization event
```

## Implementation

```text
c2_server/logging/
```

and the Event model defined by the data model.

## Documentation

- `docs/data-model.md`
- `docs/countermeasures.md`
- `docs/testing-strategy.md`

## Validation

Tests should verify that relevant security and operational events are recorded without exposing unnecessary sensitive information.

---

# 26. Security and Countermeasures

**Requirement:** Identify project threats and implement appropriate security countermeasures.

**Priority:** Required

**Status:** Planned

Current security controls include:

```text
TLS
Protocol validation
Task validation
Controlled file storage
Path validation
File integrity verification
Secret/configuration separation
Centralized logging
State consistency controls
Authorized laboratory scope
```

Security documentation is maintained in:

```text
docs/threat-model.md
docs/countermeasures.md
docs/kill-chain-analysis.md
```

The countermeasure catalogue maps security controls to their validation strategy.

The project does not currently claim that all security controls are implemented or validated.

---

# 27. Agent Authentication

**Requirement / Security Property:** Establish how the C2 determines whether an Agent connection should be trusted.

**Priority:** Required security decision

**Status:** Open

## Current Architecture

`REGISTER` identifies the Agent over an already-established communication Session.

However:

```text
Agent identification
        ≠
Agent authentication
```

The exact authentication mechanism has not yet been finalized.

## Implementation

Tracked through the transport, registration, and protocol components once the mechanism is selected.

Potential implementation areas include:

```text
agent/transport/
agent/protocol/
c2_server/transport/
c2_server/protocol/
config/
```

## Documentation

- `DECISIONS.md`
- `docs/countermeasures.md`
- `docs/protocol.md`

## Validation

The final mechanism must define tests for:

- valid Agent authentication;
- invalid authentication;
- unknown Agent;
- conflicting Agent identity;
- reconnection;
- authentication failure handling.

This requirement must be resolved before the security model can be considered complete.

---

# 28. Additional Transport Support

**Requirement:** Additional transports beyond TCP/TLS.

**Priority:** Bonus

**Status:** Bonus / Future

The transport architecture is intentionally abstracted:

```text
Transport Interface
       ├── TCP/TLS
       ├── HTTP
       └── Other future transports
```

TCP/TLS is the MVP transport.

Additional transports must not require rewriting the protocol or core business logic.

No additional transport is considered implemented or validated until explicitly added and tested.

---

# 29. Required Project Documentation

The project documentation must cover the following areas:

| Documentation | Location | Current role |
|---|---|---|
| Architecture | `ARCHITECTURE.md` | System architecture and component boundaries |
| Decisions | `DECISIONS.md` | Architectural and technical decisions |
| Data model | `docs/data-model.md` | Domain entities and relationships |
| State machines | `docs/state-machines.md` | Authoritative lifecycle states and transitions |
| Protocol | `docs/protocol.md` | Message definitions and protocol behaviour |
| Protocol-state transitions | `docs/protocol-state-transition.md` | Mapping protocol events to state changes |
| Reconnection / synchronization | `docs/reconnection-and-synchronization.md` | Recovery and reconciliation |
| Task lifecycle | `docs/task-lifecycle.md` | Task lifecycle and recovery |
| Network architecture | `docs/network-architecture.md` | Network topology and transport boundaries |
| File transfer | `docs/file-transfer.md` | File-transfer architecture and behaviour |
| Threat model | `docs/threat-model.md` | Threat identification |
| Countermeasures | `docs/countermeasures.md` | Security protections |
| Testing strategy | `docs/testing-strategy.md` | Verification strategy |
| Requirements mapping | `docs/requirements-mapping.md` | Requirement traceability |

Additional repository documentation may include:

```text
README.md
CONTRIBUTING.md
```

Security-specific material should reference `docs/countermeasures.md` rather than an obsolete standalone `SECURITY.md`.

---

# 30. Bonus Features

The following features are currently considered extensions rather than mandatory MVP requirements:

| Feature | Priority | Current status |
|---|---|---|
| TUI interface | Bonus | Future |
| Web interface | Bonus | Future |
| HTTP transport | Bonus | Future |
| Additional transport | Bonus | Future |
| Windows Agent | Bonus | Future |
| Additional security features | Bonus | To be evaluated |

Bonus features should only be prioritized once mandatory functionality is stable and sufficiently validated.

---

# 31. Requirement → Implementation → Test Traceability

The final project should maintain a direct relationship between important requirements and their validation.

The intended model is:

```text
Requirement
    ↓
Architecture Component
    ↓
Implementation
    ↓
Test / Demonstration
```

Examples:

### Multi-Agent support

```text
Multi-Agent support
    ↓
AgentManager + SessionManager
    ↓
C2 implementation
    ↓
Multi-Agent integration test
```

### File transfer

```text
File transfer
    ↓
FileManager + File Storage + Protocol
    ↓
Implementation
    ↓
Bidirectional / multi-chunk transfer tests
```

### Secure communication

```text
Secure communication
    ↓
TCP/TLS Transport
    ↓
Implementation
    ↓
TLS communication tests
```

### State synchronization

```text
Reconnection / synchronization
    ↓
SessionManager + SynchronizationManager
    ↓
Implementation
    ↓
Disconnect / reconnect / reconciliation tests
```

### Task execution

```text
Task execution
    ↓
TaskManager + Executor + Commands
    ↓
Implementation
    ↓
Task lifecycle / execution tests
```

---

# 32. Validation Status

A requirement should not be considered complete merely because code exists.

The preferred progression is:

```text
Planned
   ↓
In Progress
   ↓
Implemented
   ↓
Tested
   ↓
Validated
```

A requirement is considered **Validated** only when the intended behaviour has been demonstrated through appropriate testing or project validation.

For requirements involving documentation, validation may also require inspection of the corresponding document and consistency with the implementation.

---

# 33. Open Requirements and Design Questions

The following areas remain open or implementation-dependent:

- exact Agent authentication mechanism;
- exact protocol serialization format;
- exact protocol error contract;
- exact database schema;
- exact asynchronous implementation;
- exact Task timeout and retry behaviour;
- exact file-transfer recovery and resumability behaviour;
- exact `PERSISTENCE` implementation;
- exact `SELF_DESTRUCT` behaviour;
- exact CLI command set;
- exact transport security configuration.

These questions are tracked through `DECISIONS.md` and the relevant detailed specification.

Open decisions must not be represented as validated requirements.

---

# 34. Maintenance Rule

This document must be updated when:

- a requirement is clarified;
- an architectural decision changes;
- an implementation area changes;
- a requirement enters implementation;
- a requirement is implemented;
- a requirement is validated;
- a bonus feature is added;
- a test demonstrates successful validation;
- a requirement is explicitly moved out of scope.

The objective is to maintain a reliable chain:

```text
Requirement
     ↓
Design
     ↓
Implementation
     ↓
Validation
```

The requirements mapping should therefore be treated as a **living project traceability document**, not as a static description written only at the end of development.
