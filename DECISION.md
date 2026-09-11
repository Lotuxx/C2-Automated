# Architecture & Technical Decisions

This document records significant architectural and technical decisions made during the development of **C2-AUTOMATED**.

The purpose is to preserve the reasoning behind important choices so that the implementation remains consistent with the intended architecture and so that future changes can be evaluated against previous decisions.

A decision may be revised later if new technical constraints or project requirements justify it. In that case, the original decision should remain documented and the new decision should supersede it.

---

## Decision Status

The following statuses are used:

- **Accepted** — decision is currently part of the project baseline.
- **Proposed** — considered but not yet finalized.
- **Superseded** — replaced by a later decision.
- **Rejected** — explicitly considered and not selected.

---

# ADR-001 — Separate C2 Server and Agent Responsibilities

**Status:** Accepted

## Context

The project requires a C2 server capable of managing multiple agents while agents are responsible for performing tasks on their respective endpoints.

A clear distinction is therefore required between central coordination and endpoint execution.

## Decision

The system is divided into two main programs:

- **C2 Server** — manages agents, sessions, tasks, results, communication, and server-side storage.
- **Agent** — communicates with the C2 server, receives tasks, executes supported operations, and returns results.

The main principle is:

> **The C2 server manages agents and tasks; the agent executes tasks and returns results.**

## Consequences

This provides a clear responsibility boundary and allows the server and agent to evolve independently.

---

# ADR-002 — Use a Modular Monolithic C2 Server

**Status:** Accepted

## Context

The project requires several distinct responsibilities, but the implementation must remain realistic for an academic project.

A distributed microservice architecture would introduce unnecessary operational and deployment complexity.

## Decision

The C2 server is implemented as a **modular monolith**.

The application remains one server-side program while separating responsibilities into:

```text
interface/
core/
protocol/
transport/
storage/
logging/
config/
```

## Consequences

The architecture remains relatively simple to deploy and test while preserving clear internal boundaries.

---

# ADR-003 — Separate Operator Interfaces from C2 Core

**Status:** Accepted

## Context

The initial interface is a CLI, but the architecture may later support a TUI or Web interface.

Duplicating C2 logic in each interface would make the system difficult to maintain.

## Decision

Operator interfaces are presentation layers over the same C2 core.

```text
CLI ────┐
TUI ────┼──► C2 Core
Web ────┘
```

The interfaces do not directly manage network communication, persistence, or agent execution.

## Consequences

A new interface can be added without redesigning the core application logic.

---

# ADR-004 — Separate Protocol from Transport

**Status:** Accepted

## Context

The system must exchange logical messages between the C2 server and agents.

The underlying communication mechanism may evolve beyond the initial TCP/TLS implementation.

## Decision

The project explicitly separates:

> **Protocol = what is exchanged**

from:

> **Transport = how it is transmitted**

Protocol handling and network transport are therefore implemented as separate layers.

## Consequences

A new transport can be introduced without redesigning the logical message model.

The application logic does not need to know whether a message arrived through a particular transport implementation.

---

# ADR-005 — Use TCP/TLS as the Mandatory MVP Transport

**Status:** Accepted

## Context

The project requires protected communication between the C2 server and agents.

A practical and clearly demonstrable secure transport is required for the MVP.

## Decision

The mandatory transport is:

```text
TCP/TLS
```

HTTP and DNS transport are considered potential future extensions rather than mandatory MVP requirements.

## Consequences

The MVP has one well-defined protected communication path while retaining the possibility of adding other transports later.

---

# ADR-006 — Separate Beacon Scheduling from Transport

**Status:** Accepted

## Context

The agent needs periodic communication behaviour, while transport describes the mechanism used for communication.

Combining the two would make the timing behaviour depend directly on a specific network implementation.

## Decision

The responsibilities are separated as follows:

> **Beacon = when the agent communicates**

> **Transport = how the communication is performed**

The Beacon component therefore controls communication timing and related behaviour, while the Transport component handles the network communication itself.

The current conceptual beacon parameters include:

```text
interval
jitter
retry
```

## Consequences

Beacon behaviour can evolve without requiring the underlying transport implementation to change.

---

# ADR-007 — Separate Agent Identity from Communication Sessions

**Status:** Accepted

## Context

An agent may disconnect and reconnect during its lifetime.

Treating every connection as a completely new agent would make persistent agent tracking difficult.

## Decision

The architecture distinguishes between:

- **Agent** — persistent identity;
- **Session** — a communication instance associated with an agent.

Conceptually:

```text
Agent A001
    │
    └── Session S42
```

An agent may therefore have multiple sessions over time.

## Consequences

The server can preserve the identity of an agent even when its current communication session ends.

This also provides a cleaner basis for multi-agent and session management.

---

# ADR-008 — Use Asynchronous Task Management

**Status:** Accepted

## Context

The server must manage multiple agents simultaneously.

A direct blocking request/response model would make the server depend on one agent completing an operation before continuing.

## Decision

Tasks are managed independently from transport operations and follow an explicit lifecycle.

The current conceptual lifecycle is:

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

The server maintains independent tasks for different agents.

## Consequences

The system can support concurrent agent activity without tying the operator interface directly to a single blocking network exchange.

---

# ADR-009 — Separate Task Management from Command Execution

**Status:** Accepted

## Context

The C2 server is responsible for creating and tracking tasks, while the agent is responsible for executing operations.

Directly coupling a server-side task to an endpoint command implementation would create unnecessary dependencies.

## Decision

The responsibilities are separated:

```text
C2
 ↓
Task Manager
 ↓
Task
 ↓
Protocol
 ↓
Agent
 ↓
Executor
 ↓
Command
```

The server manages the task lifecycle; the agent's Executor dispatches the received task to the appropriate command.

## Consequences

Task management remains independent from endpoint implementation details.

---

# ADR-010 — Separate Executor from Commands on the Agent

**Status:** Accepted

## Context

The agent must support multiple operations while keeping execution logic maintainable.

A single large command handler would tightly couple dispatching, execution, and platform-specific behaviour.

## Decision

The agent separates:

```text
Executor
    ↓
Commands
```

The Executor decides which command handler should process a task, while individual command implementations provide the actual operation.

The current logical command categories include:

```text
SHELL
SYSINFO
FILES
PERSISTENCE
SELF_DESTRUCT
```

## Consequences

New commands can be introduced without redesigning the task-dispatching mechanism.

---

# ADR-011 — Isolate Platform-Specific Agent Functionality

**Status:** Accepted

## Context

Linux is the primary target platform, while Windows is considered a bonus extension.

Placing operating-system-specific logic throughout the agent would make future platform support harder.

## Decision

Platform-specific functionality is isolated behind a platform layer.

Conceptually:

```text
Common Agent Logic
        │
        ▼
Platform Abstraction
     ┌──┴──┐
     ▼     ▼
   Linux Windows
```

Logical commands may therefore have platform-specific implementations where necessary.

## Consequences

Windows support can be added progressively without redesigning the common agent architecture.

---

# ADR-012 — Separate File Transfer Management from File Storage

**Status:** Accepted

## Context

File transfer requires more than simply sending a file as one result.

The system needs to manage transfer state, chunks, reconstruction, integrity verification, and physical storage.

## Decision

The responsibilities are separated into:

```text
File Manager
      │
      ├── transfer lifecycle
      ├── transfer state
      └── transfer completion
              │
              ▼
      File Storage Interface
              │
              ▼
          Filesystem
```

The File Manager does not own the physical storage implementation.

## Consequences

File-transfer logic can evolve independently from the filesystem implementation.

---

# ADR-013 — Separate Structured Metadata from File Contents

**Status:** Accepted

## Context

The system stores information about agents, sessions, tasks, results, and file transfers, while also needing to store the actual bytes of transferred files.

Storing both through the same mechanism would make the persistence model less clear.

## Decision

Structured information is stored in the database, while actual file contents are stored through a dedicated file-storage layer.

```text
storage/
├── database/
└── files/
```

The conceptual distinction is:

> **Database = metadata and structured application state**

> **File storage = actual file contents**

## Consequences

File contents do not need to be embedded inside the relational data model, while file-transfer metadata remains queryable.

---

# ADR-014 — Use SQLite for Structured Persistence

**Status:** Accepted

## Context

The project requires persistent server-side state but does not justify the operational complexity of a larger database deployment.

## Decision

SQLite is used as the initial database backend.

The application interacts with a storage abstraction rather than embedding SQL access throughout the core.

```text
Core
  ↓
Database Interface
  ↓
SQLite
```

## Consequences

The project obtains persistent structured storage with minimal deployment overhead while retaining the possibility of replacing the backend later.

---

# ADR-015 — Use a Storage Abstraction

**Status:** Accepted

## Context

The architecture should not make the C2 core dependent on a specific database or filesystem implementation.

## Decision

Storage responsibilities are accessed through interfaces.

```text
Application
    │
    ├── Database Interface
    │       ↓
    │     SQLite
    │
    └── File Storage Interface
            ↓
         Filesystem
```

## Consequences

Storage implementations can be replaced or extended without redesigning the application logic.

---

# ADR-016 — Use Controlled File Workspaces

**Status:** Accepted

## Context

File-transfer operations require temporary and persistent locations on both the C2 server and the agent.

Using arbitrary filesystem locations would make the transfer subsystem harder to reason about and secure.

## Decision

Both sides maintain dedicated file workspaces:

```text
data/
└── files/
    ├── uploads/
    ├── downloads/
    └── temporary/
```

Transfer-related file operations use the defined storage abstraction and workspace rather than arbitrary paths.

## Consequences

File-transfer behaviour becomes easier to test, document, and constrain.

Path validation and workspace enforcement remain implementation requirements.

---

# ADR-017 — Transfer Files Incrementally

**Status:** Accepted

## Context

A transferred file may be larger than the amount of memory that should be dedicated to a single transfer.

Loading the complete file into memory is unnecessary.

## Decision

Files are transferred incrementally using structured messages such as:

```text
FILE_START
FILE_CHUNK
FILE_CHUNK
...
FILE_END
```

Chunks are processed and persisted progressively.

## Consequences

The system can handle larger files without requiring the complete file to remain in memory.

The transfer design must also account for incomplete or invalid transfers.

---

# ADR-018 — Use TLS for Encryption in Transit

**Status:** Accepted

## Context

C2-Agent communication must be protected while travelling over the network.

## Decision

TLS is responsible for protecting network communication for the MVP.

This includes:

- task messages;
- results;
- status/beacon communication;
- file transfers.

## Consequences

Communication confidentiality and transport-level integrity are provided without requiring a separate encryption layer for each message or file.

The exact TLS configuration, certificate handling, and trust model remain implementation decisions.

---

# ADR-019 — Do Not Require Separate File Encryption for the MVP

**Status:** Accepted

## Context

File transfers require protection while travelling over the network.

An additional application-level encryption layer could provide defense in depth, but would introduce additional key-management and implementation complexity.

## Decision

Application-level encryption of individual transferred files is **not mandatory for the MVP**.

TLS is considered sufficient for protecting file contents while they are transmitted between the C2 server and agent.

Encryption at rest may be considered later as a separate feature.

## Consequences

The MVP avoids introducing unnecessary cryptographic key-management complexity while still protecting network transmission.

---

# ADR-020 — Verify File Integrity Separately

**Status:** Accepted

## Context

Confidentiality during transmission and integrity of the reconstructed file are separate security properties.

TLS protects the communication channel, but the transfer subsystem can still benefit from an explicit end-to-end file verification step.

## Decision

Transferred files should be verified after reconstruction using a cryptographic hash such as SHA-256.

Conceptually:

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

## Consequences

The transfer subsystem can detect corrupted or incomplete reconstructed files.

This is distinct from TLS:

```text
TLS
→ protects communication in transit

SHA-256
→ verifies file content integrity
```

---

# ADR-021 — Keep `main.py` as an Initialization Entry Point

**Status:** Accepted

## Context

The server requires several components to be initialized and connected together.

Putting initialization and business logic in one file would quickly make the entry point difficult to maintain.

## Decision

`main.py` acts as the application entry point and composition layer.

Its responsibilities include conceptually:

```text
load configuration
initialize logging
initialize storage
create C2 core
create transport
connect components
start operator interface
```

The main C2 business logic remains in the appropriate core components.

## Consequences

The entry point remains small and the application logic remains modular.

---

# ADR-022 — Centralize Application Logging

**Status:** Accepted

## Context

The project requires visibility into communication, task execution, errors, and system behaviour during development and demonstration.

Scattered ad-hoc logging would make troubleshooting inconsistent.

## Decision

Logging is centralized in a dedicated logging component.

Relevant events include:

```text
agent registration
session establishment
session termination
task creation
task dispatch
result reception
file transfer events
errors
```

## Consequences

Operational behaviour is easier to debug and demonstrate.

Sensitive values must not be unnecessarily exposed through logs.

---

# ADR-023 — Separate Architecture from Detailed Specifications

**Status:** Accepted

## Context

The global architecture needs to remain readable while some subsystems, such as the protocol and file-transfer mechanisms, may require much more detailed documentation.

Putting every detail into `ARCHITECTURE.md` would make the document difficult to maintain.

## Decision

`ARCHITECTURE.md` contains the global architectural model and major component responsibilities.

Detailed specifications may be placed under `docs/` when a subsystem becomes sufficiently complex.

Examples include:

```text
docs/
├── protocol.md
├── task-lifecycle.md
├── file-transfer.md
└── data-model.md
```

These documents complement the architecture rather than replacing it.

## Consequences

The architecture remains a global reference while detailed subsystem documentation can evolve independently.

---

# ADR-024 — Treat the Architecture as a Living Baseline

**Status:** Accepted

## Context

The project is being designed incrementally, and implementation may reveal constraints that require architectural changes.

## Decision

The architecture is considered a living baseline.

Changes that modify:

- component responsibilities;
- dependencies;
- major data flows;
- communication boundaries;
- storage strategy;
- security properties

should be reflected in `ARCHITECTURE.md` and, when significant, recorded in this file.

## Consequences

The repository documents not only the final implementation, but also the reasoning behind major design changes.

---

# Proposed Decisions

The following subjects have been identified but are **not yet finalized**.

## PRO-001 — Exact Agent Authentication Model

Questions to resolve:

- How does the server authenticate an agent?
- How is an agent identity established?
- Are certificates used for mutual authentication?
- How are credentials or identity material provisioned in the laboratory?

No final implementation decision has been recorded yet.

---

## PRO-002 — Exact Protocol Contract

The protocol requires a precise specification for:

- message envelope;
- message fields;
- message identifiers;
- task correlation;
- serialization format;
- validation rules;
- protocol versioning;
- error messages;
- file-transfer metadata.

The currently identified logical messages are:

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

The final contract should be documented separately once finalized.

---

## PRO-003 — Exact Session State Machine

The Agent / Session distinction has been established, but the exact session states and transitions have not yet been finalized.

This should be defined before implementing the complete session manager.

---

## PRO-004 — Detailed Database Schema

The entities currently expected include:

```text
agents
sessions
tasks
results
file_transfers
events
```

The exact relationships, fields, indexes, and lifecycle rules remain to be defined.

---

## PRO-005 — Detailed Asynchronous Implementation

The architectural requirement for asynchronous multi-agent operation is established.

The exact implementation approach, concurrency model, scheduling mechanism, and synchronization strategy remain to be finalized during implementation.

---

# Superseding Decisions

When an accepted decision is later replaced, the original ADR should not be deleted.

Instead, record the new decision and mark the older ADR as **Superseded**.

Example:

```text
ADR-005 — Use TCP/TLS
Status: Superseded by ADR-025
```

This preserves the history of the project's architectural reasoning.
