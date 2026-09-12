# Requirements Mapping

> **Status: Work in Progress**
>
> This document maps the project requirements to the current architecture,
> planned implementation areas, documentation, and validation strategy.
>
> The mapping is intentionally maintained throughout development. As
> implementation decisions are finalized, the relevant entries should be
> updated.

---

# 1. Purpose

The purpose of this document is to maintain traceability between:

```text id="2x35yt"
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
- a defined validation approach.

The document also distinguishes mandatory requirements from optional
extensions.

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

---

# 3. Global Project Requirements

The project is based on a C2 server / agent architecture.

The major expected capabilities are:

```text id="n5pmpb"
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
Documentation
Security analysis
```

The exact mapping below should evolve as the implementation progresses.

---

# 4. Core Functional Requirements

## 4.1 C2 Server

**Requirement:** Provide a functional C2 server.

**Status:** Required / Planned

### Architecture

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

### Implementation

```text
c2_server/
```

Main entry point:

```text
c2_server/main.py
```

### Validation

The server must be able to start successfully and provide the functionality
required by the implemented MVP.

---

## 4.2 Agent

**Requirement:** Provide a deployable agent.

**Status:** Required / Planned

### Architecture

```text
Agent
├── Core
├── Beacon
├── Protocol
├── Transport
├── Executor
├── Commands
├── Platform
└── File Storage
```

### Implementation

```text
agent/
```

### Validation

The agent must be able to:

- start in the supported laboratory environment;
- establish communication with the C2;
- receive supported tasks;
- execute supported operations;
- return results.

---

# 5. Multi-Agent Management

**Requirement:** The C2 server must support multiple agents
simultaneously.

**Status:** Required / Planned

### Architecture

Primary components:

```text
c2_server/core/agent_manager.py
c2_server/core/session_manager.py
```

The architecture distinguishes agent identity from communication sessions.

Conceptually:

```text id="x8us1n"
C2 Server
   │
   ├── Agent A001
   │      ├── Session S01
   │      └── Session S02
   │
   ├── Agent A002
   │      └── Session S03
   │
   └── Agent A003
          └── Session S04
```

### Implementation

```text
c2_server/core/agent_manager.py
c2_server/core/session_manager.py
```

### Validation

Test scenarios should verify:

- multiple agents can coexist;
- agents remain distinguishable;
- sessions remain associated with the correct agents;
- tasks are dispatched to the correct agents;
- one agent does not incorrectly affect another.

---

# 6. Asynchronous Communication

**Requirement:** Support asynchronous communication and multi-agent operation.

**Status:** Required / Planned

### Architecture

The communication architecture is separated into:

```text
Protocol
   ↓
Transport
```

while task scheduling remains independent from the transport mechanism.

The conceptual model is:

```text id="ur2asy"
Agent A001 → independent activity
Agent A002 → independent activity
Agent A003 → independent activity
```

### Implementation

Primary areas:

```text
c2_server/core/session_manager.py
c2_server/core/task_manager.py
c2_server/transport/
agent/beacon/
agent/transport/
```

### Validation

Tests should verify that:

- multiple agents can communicate concurrently;
- one active task does not block unrelated agent activity;
- independent task queues remain correctly associated with agents;
- communication failures affecting one session do not incorrectly terminate
  unrelated sessions.

The exact concurrency model remains an open implementation decision.

---

# 7. Agent Registration and Beaconing

**Requirement:** The agent must establish communication with the C2 and
participate in the periodic communication cycle.

**Status:** Required / Planned

### Architecture

```text
Agent
  ↓
Beacon
  ↓
Protocol
  ↓
Transport
  ↓
C2
```

### Implementation

Primary areas:

```text
agent/beacon/
agent/protocol/
agent/transport/
c2_server/core/agent_manager.py
c2_server/core/session_manager.py
```

### Validation

Tests should verify:

- agent registration;
- correct identity association;
- beacon communication;
- session creation;
- session state updates;
- reconnection behaviour once defined.

---

# 8. Task Management

**Requirement:** The system must support a task-based execution model.

**Status:** Required / Planned

### Architecture

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
```

### Implementation

Primary areas:

```text
c2_server/core/task_manager.py
agent/executor/
agent/commands/
```

### Validation

The task lifecycle must be tested.

Current conceptual states:

```text
PENDING
   ↓
 SENT
   ↓
RUNNING
   ├──► FAILED
   ↓
COMPLETED
```

Detailed lifecycle behaviour is documented in
[`task-lifecycle.md`](task-lifecycle.md).

---

# 9. Command Execution

**Requirement:** The agent must execute supported commands.

**Status:** Required / Planned

### Architecture

```text
TASK
  ↓
Executor
  ↓
Command Handler
  ↓
Platform-specific Implementation
  ↓
Execution
  ↓
Result
```

### Current Command Categories

```text id="2beva9"
SHELL
SYSINFO
FILES
PERSISTENCE
SELF_DESTRUCT
```

### Implementation

```text
agent/executor/
agent/commands/
agent/platform/
```

### Validation

Tests should verify:

- valid commands are dispatched correctly;
- invalid commands are rejected;
- command parameters are validated;
- execution failures generate controlled results;
- platform-specific implementations remain isolated.

---

# 10. Result Handling

**Requirement:** Results from agents must be returned to and managed by the
C2 server.

**Status:** Required / Planned

### Architecture

```text
Agent
   ↓
Result
   ↓
Protocol
   ↓
Transport
   ↓
C2 Protocol
   ↓
Result Manager
   ↓
Storage / Interface
```

### Implementation

Primary area:

```text
c2_server/core/result_manager.py
```

### Validation

Tests should verify:

- correct result reception;
- correct association with the originating task;
- correct association with the agent;
- result persistence;
- handling of malformed or unexpected results.

---

# 11. File Transfer

**Requirement:** Support file transfer between the C2 server and agents.

**Status:** Required / Planned

### Architecture

File transfer is treated separately from ordinary task results.

Current conceptual protocol:

```text
FILE_START
     ↓
FILE_CHUNK
     ↓
...
     ↓
FILE_END
```

### Implementation

Primary areas:

```text
c2_server/core/file_manager.py
c2_server/storage/files/
c2_server/data/files/

agent/commands/
agent/storage/files/
agent/data/files/
```

### Validation

Testing should include:

- C2 → Agent transfer;
- Agent → C2 transfer;
- multi-chunk files;
- interrupted transfers;
- invalid transfer metadata;
- integrity verification;
- temporary-file handling;
- cleanup of failed transfers.

Detailed design is documented in [`file-transfer.md`](file-transfer.md).

---

# 12. File Integrity

**Requirement / Security Property:** Transferred files should be verifiable
after reconstruction.

**Status:** Planned

### Architecture

```text
Original File
     ↓
Cryptographic Hash
     ↓
Transfer
     ↓
Reconstructed File
     ↓
Cryptographic Hash
     ↓
Comparison
```

### Current Design

A hash such as SHA-256 is currently intended for file-integrity verification.

### Implementation

The exact implementation location remains to be finalized between the file
manager, protocol layer, and storage/transfer components.

### Validation

Tests should verify:

```text
Matching hash
    → valid transfer

Mismatching hash
    → invalid transfer
```

---

# 13. Secure Communication

**Requirement / Security Property:** Protect C2-Agent communication in transit.

**Status:** Required / Planned

### Architecture

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

### Implementation

Primary area:

```text
c2_server/transport/
agent/transport/
```

### Validation

Tests should verify:

- successful TLS communication;
- intended TLS configuration;
- certificate verification behaviour once finalized;
- handling of TLS failures.

Detailed requirements are documented in [`SECURITY.md`](../SECURITY.md).

---

# 14. Protocol

**Requirement:** Define a structured communication protocol between the C2
server and agents.

**Status:** Required / Planned

### Current Message Types

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

### Implementation

```text
c2_server/protocol/
agent/protocol/
```

### Validation

Tests should verify:

- valid messages;
- invalid messages;
- serialization/deserialization;
- required fields;
- message identifiers;
- protocol version handling once defined.

Detailed protocol design is documented in [`protocol.md`](protocol.md).

---

# 15. Linux Support

**Requirement:** Support Linux agents.

**Status:** Required / Planned

### Architecture

```text
Agent
  ↓
Platform Abstraction
  ↓
Linux
```

### Implementation

```text
agent/platform/
agent/commands/
```

### Validation

The complete MVP agent must be tested in the intended Linux laboratory
environment.

---

# 16. Windows Support

**Requirement:** Windows support.

**Status:** Bonus

### Architecture

```text
Platform Abstraction
     ├── Linux
     └── Windows
```

### Implementation

Platform-specific code should remain isolated so that Windows support can be
added without redesigning the common agent architecture.

### Validation

Windows support requires a dedicated test environment before being considered
validated.

---

# 17. Operator Interface

**Requirement:** Provide an operator interface.

**Status:** Required / Planned

### MVP

The initial interface is:

```text
CLI
```

### Architecture

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

### Implementation

```text
c2_server/interface/
```

### Validation

Tests and manual validation should verify that the operator can:

- view agents;
- select an agent;
- create tasks;
- inspect task state;
- inspect returned results;
- initiate supported file-transfer operations.

The exact CLI command set remains to be finalized.

---

# 18. Additional Transport Support

**Requirement:** Additional transports beyond TCP/TLS.

**Status:** Bonus / Future Extension

Current conceptual architecture:

```text
Transport Interface
     ├── TCP/TLS
     ├── HTTP
     └── DNS
```

TCP/TLS is the MVP.

HTTP and DNS are not considered implemented or validated unless explicitly
added later.

---

# 19. Persistence

**Requirement:** Maintain relevant structured application state.

**Status:** Required / Planned

### Architecture

```text
Application
    ↓
Database Interface
    ↓
SQLite
```

Potential entities include:

```text
agents
sessions
tasks
results
file transfers
events
```

### Implementation

```text
c2_server/storage/database/
```

### Validation

Tests should verify persistence and retrieval of finalized entities and
state.

The exact schema remains a work in progress.

---

# 20. File Storage

**Requirement:** Store transferred files separately from structured metadata.

**Status:** Required / Planned

### Architecture

```text
File Manager
      ↓
File Storage Interface
      ↓
Filesystem
      ↓
data/files/
```

### Implementation

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

### Validation

Tests should verify:

- correct storage location;
- controlled paths;
- file creation and retrieval;
- temporary-file handling;
- cleanup behaviour.

---

# 21. Security and Countermeasures

**Requirement:** Identify threats and implement appropriate countermeasures.

**Status:** Required / Planned

Current security controls include:

```text
TLS
Protocol validation
File integrity verification
Controlled file storage
Path validation
Secret protection
Centralized logging
```

Detailed security requirements are maintained in
[`SECURITY.md`](../SECURITY.md).

Threat analysis and countermeasure mapping are documented separately in:

```text
threat-model.md
kill-chain-analysis.md
countermeasures.md
```

These documents are currently being developed.

---

# 22. Required Project Documentation

The project documentation must cover at least the following areas:

| Documentation area | Repository location | Status |
|---|---|---|
| Protocol | `docs/protocol.md` | Work in Progress |
| Architecture | `ARCHITECTURE.md` | Work in Progress |
| Network architecture | `docs/network-architecture.md` | To be developed |
| Task lifecycle | `docs/task-lifecycle.md` | Work in Progress |
| File transfer | `docs/file-transfer.md` | Work in Progress |
| Data model | `docs/data-model.md` | Work in Progress |
| Kill Chain analysis | `docs/kill-chain-analysis.md` | To be developed |
| Countermeasures | `docs/countermeasures.md` | To be developed |
| Threat model | `docs/threat-model.md` | To be developed |
| Testing strategy | `docs/testing-strategy.md` | Work in Progress |

Additional project documentation is maintained in the repository root:

```text
README.md
SECURITY.md
DECISIONS.md
CONTRIBUTING.md
```

---

# 23. Bonus Features

The following features are currently considered extensions rather than
mandatory MVP requirements:

| Feature | Current status |
|---|---|
| TUI interface | Bonus / Future |
| Web interface | Bonus / Future |
| HTTP transport | Bonus / Future |
| DNS transport | Bonus / Future |
| Windows agent | Bonus / Future |
| Additional security features | To be evaluated |

Bonus features should only be prioritized once the mandatory functionality is
stable and validated.

---

# 24. Requirement → Test Traceability

The final project should maintain a direct relationship between important
requirements and their validation.

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

```text
Multi-agent support
    ↓
AgentManager + SessionManager
    ↓
Implementation
    ↓
Multi-agent integration test
```

```text
File transfer
    ↓
FileManager + File Storage + Protocol
    ↓
Implementation
    ↓
Bidirectional file-transfer test
```

```text
Secure communication
    ↓
Transport / TCP-TLS
    ↓
Implementation
    ↓
TLS communication test
```

---

# 25. Validation Status

A requirement should not be considered complete merely because code exists.

The preferred progression is:

```text
Planned
   ↓
Implemented
   ↓
Tested
   ↓
Validated
```

A requirement is considered **Validated** only when the intended behaviour
has been demonstrated through appropriate testing or project validation.

---

# 26. Open Requirements and Design Questions

Some requirements depend on design decisions that are not yet finalized.

These include:

- exact agent authentication mechanism;
- exact protocol schema;
- exact session lifecycle;
- exact task timeout/retry behaviour;
- exact file-transfer state machine;
- exact database schema;
- exact asynchronous implementation;
- exact `SELF_DESTRUCT` interpretation;
- exact CLI command set.

Unresolved design questions should not be represented as implemented
requirements.

Significant decisions should be recorded in
[`DECISIONS.md`](../DECISIONS.md).

---

# 27. Maintenance Rule

This document must be updated when:

- a requirement is clarified;
- a requirement is implemented;
- a requirement is validated;
- an architectural component changes;
- a bonus feature is added;
- a test demonstrates successful validation.

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

so that the final project can clearly demonstrate how each requirement was
addressed.
