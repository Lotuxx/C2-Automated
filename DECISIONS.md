# Architecture & Technical Decisions

This document records significant architectural and technical decisions made during the development of **C2-AUTOMATED**.

The purpose is to preserve the reasoning behind important choices so that the implementation remains consistent with the intended architecture and so that future changes can be evaluated against previous decisions.

A decision may be revised later if new technical constraints or project requirements justify it. In that case, the original decision should remain documented and the new decision should supersede it.

---

# Document Conventions

## ADR — Architecture Decision Record

`ADR` stands for **Architecture Decision Record**.

An ADR documents a decision that has been accepted as part of the current architecture or technical baseline.

Each ADR records:

- **Context** — why the decision was necessary;
- **Decision** — what was chosen;
- **Consequences** — what follows from the decision.

## PRO — Proposed Decision

`PRO` stands for **Proposed Decision**.

A PRO documents a topic that still requires a decision.

It is explicitly **not** part of the finalized architecture until it is resolved and, when appropriate, converted into an ADR.

---

# Decision Status

The following statuses are used:

- **Accepted** — decision is currently part of the project baseline.
- **Proposed** — considered but not yet finalized.
- **Superseded** — replaced by a later decision.
- **Rejected** — explicitly considered and not selected.

---

# ADR-001 — Separate C2 Server and Agent Responsibilities

**Status:** Accepted

## Context

The project requires a C2 server capable of managing multiple Agents while Agents are responsible for performing tasks on their respective endpoints.

A clear distinction is therefore required between central coordination and endpoint execution.

## Decision

The system is divided into two main programs:

- **C2 Server** — manages Agents, Sessions, Tasks, Results, communication, synchronization, and server-side storage.
- **Agent** — communicates with the C2 server, receives Tasks, executes supported operations, maintains lightweight recovery state, and returns execution evidence and Results.

The main principle is:

> **The C2 server manages Agents and Tasks; the Agent executes Tasks and returns execution evidence and Results.**

## Consequences

This provides a clear responsibility boundary and allows the server and Agent to evolve independently.

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

The initial interface is a CLI, while the architecture may later support a TUI or Web interface.

Duplicating C2 logic in each interface would make the system difficult to maintain.

## Decision

Operator interfaces are presentation layers over the same C2 Core.

```text
CLI ────┐
TUI ────┼──► C2 Core
Web ────┘
```

The interfaces do not directly manage network communication, persistence, or Agent execution.

The CLI is the mandatory MVP interface. TUI and Web are extension points.

## Consequences

A new interface can be added without redesigning the Core application logic.

---

# ADR-004 — Separate Protocol from Transport

**Status:** Accepted

## Context

The system must exchange logical messages between the C2 server and Agents.

The underlying communication mechanism may evolve beyond the initial TCP/TLS implementation.

## Decision

The project explicitly separates:

> **Protocol = what is exchanged**

from:

> **Transport = how it is transmitted**

Protocol handling and network transport are therefore implemented as separate layers.

## Consequences

A new transport can be introduced without redesigning the logical message model.

The application logic does not need to know which transport implementation carried a message.

---

# ADR-005 — Use TCP/TLS as the Mandatory MVP Transport

**Status:** Accepted

## Context

The project requires protected communication between the C2 server and Agents.

A practical and clearly demonstrable secure transport is required for the MVP.

## Decision

The mandatory MVP transport is:

```text
TCP/TLS
```

HTTP and DNS transports are considered possible future extensions rather than mandatory MVP requirements.

## Consequences

The MVP has one well-defined protected communication path while retaining the possibility of adding other transports later.

---

# ADR-006 — Separate Beacon Scheduling from Transport

**Status:** Accepted

## Context

The Agent requires periodic communication behaviour, while transport describes the mechanism used for communication.

Combining the two would make communication timing depend directly on a specific network implementation.

## Decision

The responsibilities are separated as follows:

> **Beacon = when the Agent communicates**

> **Transport = how the communication is performed**

The Beacon component therefore controls communication timing and related liveness behaviour, while the Transport component handles network communication.

The current conceptual Beacon parameters include:

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

An Agent may disconnect and reconnect during its lifetime.

Treating every connection as a completely new Agent would make persistent Agent tracking difficult.

At the same time, reusing the same Session after a connection interruption would make individual communication episodes ambiguous.

## Decision

The architecture distinguishes between:

- **Agent** — persistent endpoint identity;
- **Session** — one specific communication episode associated with an Agent.

An Agent may therefore have multiple Sessions over time.

```text
Agent A001
 ├── S041
 ├── S042 = DISCONNECTED
 └── S043 = CONNECTED
```

A new connection always creates a **new Session**.

A previous Session is never reopened as the current Session.

## Consequences

The server can preserve the identity of an Agent while maintaining an accurate historical record of its communication Sessions.

Tasks and Results can also be associated with an Agent without becoming permanently tied to one communication Session.

---

# ADR-008 — Define an Explicit Session Lifecycle

**Status:** Accepted

## Context

The distinction between an Agent and a Session requires a precise Session lifecycle.

In particular, transport establishment and Agent registration are separate events and must not be conflated.

## Decision

The authoritative Session states are:

```text
CONNECTING
CONNECTED
DISCONNECTED
CLOSED
```

The principal transitions are:

```text
CONNECTING
    │
    ▼
CONNECTED
   ├──► DISCONNECTED
   └──► CLOSED
```

A new communication connection follows:

```text
New connection
      ↓
New Session
      ↓
Session CONNECTING
      ↓
Transport established
      ↓
Session CONNECTED
      ↓
REGISTER
```

`REGISTER` does **not** establish the Session.

`REGISTER_ACK` does **not** cause:

```text
CONNECTING → CONNECTED
```

because the Session has already become `CONNECTED` when transport establishment succeeds.

`REGISTER_ACK` confirms Agent registration and communicates the new Session identifier.

## Consequences

Session lifecycle semantics remain independent from Agent registration and from higher-level Agent communication state.

Detailed state semantics are authoritative in `state-machines.md`.

---

# ADR-009 — Separate Session State from Agent Communication State

**Status:** Accepted

## Context

A connected network Session does not necessarily mean that the Agent is ready for normal application-level communication.

For example, an Agent may have established a Session but still need to reconcile its local state with the C2.

## Decision

Session state and Agent communication state are modeled separately.

Agent communication states are:

```text
CONNECTING
CONNECTED
DEGRADED
OFFLINE_WAIT
SYNCHRONIZING
```

Therefore, the following combination is valid:

```text
Session = CONNECTED
Agent communication = SYNCHRONIZING
```

The normal communication sequence is:

```text
Session CONNECTED
        ↓
REGISTER
        ↓
Communication SYNCHRONIZING
        ↓
State reconciliation
        ↓
SYNC_COMPLETE
        ↓
Communication CONNECTED
```

## Consequences

Network connectivity, synchronization status, and normal application communication are no longer represented by one overloaded state.

This reduces ambiguity during reconnection and recovery.

---

# ADR-010 — Use Explicit Agent Health and Activity States

**Status:** Accepted

## Context

Agent reachability and Agent workload are different concepts.

A single state would not adequately represent situations such as an Agent being reachable but currently executing a Task.

## Decision

Agent health is represented independently using:

```text
UNKNOWN
ALIVE
LIKELY_UNREACHABLE
TERMINATED
```

Agent activity is represented independently using:

```text
IDLE
BUSY
```

`RUNNING` is therefore a Task state and is not an Agent activity state.

Communication state is also maintained separately as defined by ADR-009.

## Consequences

The system can represent combinations such as:

```text
Health = ALIVE
Activity = BUSY
Communication = CONNECTED
```

without conflating endpoint health, workload, and communication state.

---

# ADR-011 — Use Explicit Asynchronous Task Lifecycle

**Status:** Accepted

## Context

The original task model used a simplified `SENT → RUNNING → COMPLETED` representation.

As the architecture evolved, this proved insufficient to represent acceptance, queuing, recovery, cancellation, and timeout behaviour.

## Decision

Tasks use the following authoritative persistent lifecycle states:

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

The normal lifecycle is:

```text
PENDING
   ↓
WAITING_ACK
   ↓
QUEUED
   ↓
RUNNING
   ├──► COMPLETED
   └──► FAILED
```

`TIMEOUT` and `CANCELLED` are additional terminal states applicable according to their respective transition rules.

`UNKNOWN` is **not** a persistent Task state. It is a recovery or reporting condition used when the execution state cannot currently be established.

## Consequences

The Task model can represent asynchronous multi-Agent operation more accurately.

The obsolete `SENT` Task state is not part of the current architecture.

Detailed Task semantics are defined in `state-machines.md` and `task-lifecycle.md`.

---

# ADR-012 — Separate Task Management from Command Execution

**Status:** Accepted

## Context

The C2 server is responsible for creating and tracking Tasks, while the Agent is responsible for executing operations.

Directly coupling a server-side Task to an endpoint command implementation would create unnecessary dependencies.

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

The server manages the Task lifecycle.

The Agent's Executor dispatches received Tasks to the appropriate command implementation.

## Consequences

Task management remains independent from endpoint implementation details.

---

# ADR-013 — Separate Executor from Commands on the Agent

**Status:** Accepted

## Context

The Agent must support multiple operations while keeping execution logic maintainable.

A single large command handler would tightly couple dispatching, execution, and platform-specific behaviour.

## Decision

The Agent separates:

```text
Executor
    ↓
Commands
```

The Executor decides which command handler should process a Task, while individual command implementations provide the actual operation.

The current logical command categories include:

```text
SHELL
SYSINFO
FILES
PERSISTENCE
SELF_DESTRUCT
```

The exact command contracts remain implementation-level details unless separately specified.

## Consequences

New commands can be introduced without redesigning the task-dispatching mechanism.

Command capabilities remain subject to the project's authorized laboratory scope.

---

# ADR-014 — Isolate Platform-Specific Agent Functionality

**Status:** Accepted

## Context

Linux is the primary target platform, while Windows is considered a bonus extension.

Placing operating-system-specific logic throughout the Agent would make future platform support harder.

## Decision

Platform-specific functionality is isolated behind a platform layer.

```text
Common Agent Logic
        │
        ▼
Platform Abstraction
     ┌──┴──┐
     ▼     ▼
   Linux Windows
```

Linux is the primary implementation target.

Windows support is an extension/bonus objective.

## Consequences

Windows support can be added progressively without redesigning the common Agent architecture.

---

# ADR-015 — Separate File Transfer Management from File Storage

**Status:** Accepted

## Context

File transfer requires more than simply sending a file as one Result.

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

# ADR-016 — Separate Structured Metadata from File Contents

**Status:** Accepted

## Context

The system stores information about Agents, Sessions, Tasks, Results, Events, and File Transfers, while also needing to store the actual bytes of transferred files.

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

File contents do not need to be embedded inside the relational data model, while transfer metadata remains queryable.

---

# ADR-017 — Use SQLite for Structured Persistence

**Status:** Accepted

## Context

The project requires persistent server-side state but does not justify the operational complexity of a larger database deployment.

## Decision

SQLite is used as the initial database backend.

The application interacts with a storage abstraction rather than embedding SQL access throughout the Core.

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

# ADR-018 — Use a Storage Abstraction

**Status:** Accepted

## Context

The architecture should not make the C2 Core dependent on a specific database or filesystem implementation.

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

# ADR-019 — Use Controlled File Workspaces

**Status:** Accepted

## Context

File-transfer operations require temporary and persistent locations on both the C2 server and the Agent.

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

# ADR-020 — Transfer Files Incrementally

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

# ADR-021 — Use TLS for Encryption in Transit

**Status:** Accepted

## Context

C2-Agent communication must be protected while travelling over the network.

## Decision

TLS is responsible for protecting network communication for the MVP.

This includes:

- Task messages;
- Results;
- status and Beacon communication;
- synchronization messages;
- file transfers.

## Consequences

Communication confidentiality and transport-level integrity are provided without requiring a separate encryption layer for each message or file.

The exact TLS configuration, certificate handling, and trust model remain implementation decisions.

---

# ADR-022 — Do Not Require Separate File Encryption for the MVP

**Status:** Accepted

## Context

File transfers require protection while travelling over the network.

An additional application-level encryption layer could provide defense in depth, but would introduce additional key-management and implementation complexity.

## Decision

Application-level encryption of individual transferred files is **not mandatory for the MVP**.

TLS is considered sufficient for protecting file contents while they are transmitted between the C2 server and Agent.

Encryption at rest may be considered later as a separate feature.

## Consequences

The MVP avoids introducing unnecessary cryptographic key-management complexity while still protecting network transmission.

---

# ADR-023 — Verify File Integrity Separately from Transport Security

**Status:** Accepted

## Context

Confidentiality during transmission and integrity of the reconstructed file are separate security properties.

TLS protects the communication channel, while the transfer subsystem can benefit from an explicit end-to-end verification step.

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
→ verifies reconstructed file content
```

---

# ADR-024 — Use Explicit Message Routing

**Status:** Accepted

## Context

The protocol contains messages associated with different application responsibilities.

Allowing each component to independently inspect incoming messages would distribute protocol-handling logic throughout the C2 and increase coupling.

## Decision

The C2 uses a dedicated Message Router.

```text
Transport
    ↓
Protocol
    ↓
Validation
    ↓
Message Router
    ├── Agent Manager
    ├── Session Manager
    ├── Task Manager
    ├── Result Manager
    ├── File Manager
    └── Synchronization Manager
```

The Message Router is responsible for dispatching validated messages.

It does not replace the business logic of the destination component.

## Consequences

Protocol dispatch remains centralized and predictable.

Core components can focus on their domain responsibilities rather than implementing message-routing logic independently.

---

# ADR-025 — Use a Dedicated Synchronization Manager

**Status:** Accepted

## Context

An Agent may reconnect after communication loss while retaining local information about Tasks and Results.

Simply creating a new Session is insufficient to restore consistent application state.

## Decision

Synchronization and reconciliation are handled by a dedicated Synchronization Manager.

The canonical flow is:

```text
New Session
    ↓
REGISTER
    ↓
REGISTER_ACK
    ↓
Agent SYNCHRONIZING
    ↓
SYNC_STATE
    ↓
State reconciliation
    ↓
SYNC_STATE_RESPONSE
    ↓
SYNC_COMPLETE
    ↓
Normal communication
```

The Synchronization Manager compares the C2's persistent state with valid Agent recovery information and determines the required reconciliation actions.

## Consequences

Reconnection logic does not need to be distributed across Task, Result, Session, and Agent managers.

Detailed reconciliation rules are defined in `reconnection-and-synchronization.md`.

---

# ADR-026 — Separate Task State from Result Delivery State

**Status:** Accepted

## Context

A Task's execution state and the delivery of its Result are related but not identical.

For example, an Agent may complete a Task while communication is unavailable and deliver the Result during a later Session.

Treating Result delivery as identical to Task execution would therefore produce incorrect lifecycle semantics.

## Decision

The architecture treats:

```text
Task execution state
```

and:

```text
Result delivery state
```

as separate concepts.

A Result belongs to a Task and may be transmitted later than the execution event that produced it.

Communication loss does not automatically change the Task to `FAILED` or `TIMEOUT`.

## Consequences

The system can correctly represent offline execution, delayed Result delivery, and reconnection-based reconciliation.

---

# ADR-027 — Keep `main.py` as an Initialization Entry Point

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
create C2 Core
create transport
connect components
start operator interface
```

The main C2 business logic remains in the appropriate Core components.

## Consequences

The entry point remains small and the application logic remains modular.

---

# ADR-028 — Centralize Application Logging and Event Recording

**Status:** Accepted

## Context

The project requires visibility into communication, Task execution, errors, file transfers, and system behaviour during development and demonstration.

Scattered ad-hoc logging would make troubleshooting inconsistent.

The architecture also requires a distinction between operational logging and structured domain events.

## Decision

Logging is centralized in a dedicated logging component.

Relevant events may include:

```text
Agent registration
Session establishment
Session disconnection
Session closure
Beacon / Beacon acknowledgement
Task creation
Task dispatch
Task state changes
Result reception
File transfer events
Synchronization
Errors
```

Structured domain events are represented separately from protocol Messages.

Sensitive values must not be unnecessarily exposed through logs.

## Consequences

Operational behaviour is easier to debug, trace, and demonstrate while preserving a structured historical event record.

---

# ADR-029 — Separate Architecture from Detailed Specifications

**Status:** Accepted

## Context

The global architecture needs to remain readable while subsystems such as the protocol, state machines, task lifecycle, synchronization, and file transfer require significantly more detailed documentation.

Putting every detail into `ARCHITECTURE.md` would make the document difficult to maintain.

## Decision

`ARCHITECTURE.md` contains the global architectural model and major component responsibilities.

Detailed specifications are maintained in dedicated documents.

Examples include:

```text
docs/
├── data-model.md
├── state-machines.md
├── protocol.md
├── protocol-state-transition.md
├── reconnection-and-synchronization.md
├── task-lifecycle.md
├── network-architecture.md
├── file-transfer.md
└── testing-strategy.md
```

These documents complement the architecture rather than replacing it.

## Consequences

The architecture remains a global reference while detailed subsystem documentation can evolve independently.

---

# ADR-030 — Treat the Architecture as a Living Baseline

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

When a decision changes, the original ADR remains in the document and is marked **Superseded**.

## Consequences

The repository documents both the current architecture and the reasoning behind significant design changes.

---

# ADR-031 — Restrict the Project to Authorized Laboratory Use

**Status:** Accepted

## Context

The project models a C2 server and Agent architecture for an academic cybersecurity project.

Some of the modeled capabilities correspond to functionality that could be misused outside an authorized environment.

The project therefore requires an explicit scope defining where the system may be developed, tested, demonstrated, and deployed.

## Decision

**C2-AUTOMATED is an academic and laboratory project intended exclusively for authorized cybersecurity experimentation, development, testing, and demonstration.**

The intended environments include:

- isolated cybersecurity laboratories;
- virtual machines and test networks;
- systems owned or explicitly controlled by the project operator;
- authorized academic demonstrations;
- controlled security-testing environments.

The project must not be used to:

- access systems without authorization;
- deploy Agents on third-party systems without explicit permission;
- obtain unauthorized access to data or infrastructure;
- evade security controls on systems outside the authorized laboratory;
- conduct unauthorized persistence, surveillance, or remote-control operations.

The architecture may model capabilities associated with C2 infrastructure for educational purposes, but the existence of a capability in the architecture does not extend the authorized scope of the project.

## Consequences

Implementation, testing, demonstration, and deployment remain constrained to authorized environments.

Security-sensitive capabilities must be developed with controlled laboratory systems and documented testing conditions.

The authorized-use scope is also documented in `ARCHITECTURE.md`.

---

# ADR-032 — Maintain a Dedicated Data Model for Persistent Domain Entities

**Status:** Accepted

## Context

The architecture contains several persistent entities whose relationships must remain consistent across Sessions and reconnections.

The initial design left some of these relationships implicit.

## Decision

The principal persistent domain entities are:

```text
Agent
Session
Task
Result
File Transfer
Event
```

The relationships are modeled explicitly.

In particular:

```text
Agent
 ├── Sessions
 ├── Tasks
 ├── Results
 ├── File Transfers
 └── Events
```

A Task belongs to an Agent and may reference the Sessions in which it was created, dispatched, or last observed.

A Result belongs to a Task and Agent.

A File Transfer may be associated with a Task where applicable.

An Event may reference an Agent, Session, Task, Result, or File Transfer where relevant.

## Consequences

Persistent state can be represented consistently across reconnects and server restarts.

The detailed entity definitions and relationships are maintained in `data-model.md`.

---

# ADR-033 — Treat the C2 Persistent Record and Agent Recovery State as Complementary

**Status:** Accepted

## Context

The C2 maintains persistent historical state, while an Agent needs enough local information to recover after temporary communication loss.

Neither side alone can represent every recovery situation.

## Decision

The C2 maintains the authoritative **server-side historical record** of Agents, Sessions, Tasks, Results, Transfers, and Events.

The Agent maintains a lightweight **local recovery state** containing information required to report unfinished or recently observed work after reconnection.

During synchronization, valid Agent execution evidence may be used to reconcile stale C2 state.

The Agent does not silently create authoritative C2 Tasks or rewrite persistent history without reconciliation.

## Consequences

The architecture preserves server-side historical traceability while allowing Agents to recover useful execution state after communication interruptions.

Detailed reconciliation behaviour is defined in `reconnection-and-synchronization.md`.

---

# Proposed Decisions

The following subjects have been identified but are **not yet finalized**.

---

## PRO-001 — Exact Agent Authentication Model

Questions to resolve:

- How does the server authenticate an Agent?
- How is an Agent identity established?
- Are certificates used for mutual authentication?
- How are credentials or identity material provisioned in the laboratory?
- How is an unknown or invalid Agent handled?

No final implementation decision has been recorded yet.

---

## PRO-002 — Exact Transport Security Configuration

The use of TLS is accepted, but the following implementation details remain to be finalized:

- TLS version and configuration;
- certificate generation and storage;
- certificate validation;
- trust model;
- development versus demonstration certificates;
- certificate rotation requirements, if any.

These details should be finalized during implementation without changing the architectural decision to use TCP/TLS.

---

## PRO-003 — Exact Protocol Serialization Format

The logical protocol message model is established, but the concrete serialization representation remains an implementation decision.

The implementation must define:

- serialization format;
- framing;
- encoding;
- maximum message size;
- binary versus textual representation where applicable;
- serialization/deserialization errors.

The logical protocol contract remains defined in `protocol.md`.

---

## PRO-004 — Detailed Protocol Error Contract

The protocol contains an `ERROR` message, but the complete error taxonomy and error-handling contract remain to be finalized.

Questions include:

- error categories;
- error codes;
- human-readable messages;
- correlation with Messages and Tasks;
- recoverable versus non-recoverable errors;
- malformed-message handling.

---

## PRO-005 — Detailed Database Schema

The principal persistent entities are established:

```text
agents
sessions
tasks
results
file_transfers
events
```

The exact implementation details remain to be finalized:

- SQL schema;
- indexes;
- foreign keys;
- uniqueness constraints;
- migration strategy;
- timestamp representation;
- deletion/retention policy.

The conceptual data model is defined in `data-model.md`.

---

## PRO-006 — Detailed Asynchronous Implementation

The architectural requirement for asynchronous multi-Agent operation is established.

The exact implementation approach remains to be finalized during implementation.

Questions include:

- concurrency model;
- event loop versus worker model;
- Task scheduling;
- transport handling;
- synchronization scheduling;
- interaction with the CLI;
- shutdown behaviour.

The implementation must preserve the asynchronous Task and multi-Agent architecture.

---

## PRO-007 — Exact `SELF_DESTRUCT` Behaviour

**Status:** Proposed

## Context

The Agent command model currently includes a `SELF_DESTRUCT` capability.

The term may represent different levels of behaviour, ranging from process termination to cleanup of the project's controlled workspace.

Because the operation can affect the Agent's local state, its scope must be explicitly defined before implementation.

## Possible Interpretations

### Option A — Process Termination

The command causes the running Agent process to terminate.

```text
C2
 ↓
SELF_DESTRUCT
 ↓
Agent validates request
 ↓
Agent terminates
```

Under this interpretation, the Agent stops executing but does not necessarily remove its files or other local data.

---

### Option B — Process Termination + Temporary Cleanup

The command terminates the Agent and removes temporary runtime data within the project's controlled workspace.

```text
C2
 ↓
SELF_DESTRUCT
 ↓
Agent validation
 ↓
Cleanup temporary data
 ↓
Agent termination
```

The cleanup would remain limited to the project's defined temporary workspace.

---

### Option C — Process Termination + Project Workspace Cleanup

The command terminates the Agent and removes files associated with the Agent's controlled project workspace.

This could include project-specific:

```text
temporary data
transfer data
local runtime data
```

The exact cleanup scope would need to be explicitly defined.

---

### Option D — Full Agent Removal

The command would attempt to remove the Agent installation and associated project-controlled mechanisms.

This interpretation would require additional design around:

- installation locations;
- persistence mechanisms;
- cleanup ordering;
- failure handling;
- privileges;
- recovery;
- verification.

This interpretation is **not assumed by the current architecture**.

## Decision Criteria

Before selecting an implementation, the following should be considered:

- alignment with the academic project requirements;
- implementation complexity;
- safety within the laboratory environment;
- ability to test the behaviour reliably;
- interaction with persistence mechanisms;
- cleanup guarantees;
- privilege requirements;
- documentation requirements;
- demonstration value.

## Current Position

No option has been selected yet.

`SELF_DESTRUCT` should therefore remain a **defined capability but an unresolved implementation decision**.

The final interpretation should be recorded as an ADR once selected.

## Related Documentation

Once the interpretation is selected, the corresponding behaviour should be reflected in:

- `ARCHITECTURE.md`;
- `task-lifecycle.md`;
- `testing-strategy.md`;
- `kill-chain-analysis.md`, where applicable;
- `countermeasures.md`, where applicable.

---

## PRO-008 — Exact Command Contract

The architectural command categories are established, but each command still requires a precise implementation contract.

For each command, the project should define:

- command identifier;
- required parameters;
- optional parameters;
- input validation;
- supported platforms;
- execution result format;
- error conditions;
- timeout behaviour;
- authorization constraints within the laboratory;
- logging requirements.

This should be defined before the command implementation becomes extensive.

---

## PRO-009 — File Transfer Recovery Semantics

The basic file-transfer model is established:

```text
FILE_START
    ↓
FILE_CHUNK*
    ↓
FILE_END
```

The following details remain to be finalized:

- interrupted transfer recovery;
- transfer timeout;
- duplicate chunks;
- chunk ordering;
- retransmission;
- partial-file cleanup;
- maximum file size;
- hash metadata placement;
- duplicate transfer handling.

The implementation must preserve the separation between transfer state and physical file storage.

---

# Superseded Decisions

When an accepted decision is later replaced, the original ADR should not be deleted.

Instead, record the new decision and mark the older ADR as **Superseded**.

For example:

```text
ADR-005 — Use TCP/TLS
Status: Superseded by ADR-XXX
```

This preserves the history of the project's architectural reasoning.

---

# Decision History

The following earlier assumptions were replaced during the architectural refinement of the project:

| Previous assumption | Current decision |
|---|---|
| `SENT` was a Task state | Replaced by the authoritative Task lifecycle defined in ADR-011 |
| Registration established a Session | Replaced by ADR-008: transport establishment establishes the Session |
| `REGISTER_ACK` caused Session `CONNECTING → CONNECTED` | Replaced by ADR-008 |
| Session state represented Agent communication state | Replaced by ADR-009 |
| Task state was tightly coupled to one Session | Replaced by ADR-007 and ADR-011 |
| Communication loss implied Task failure | Replaced by ADR-011 and ADR-026 |
| Synchronization was distributed across components | Replaced by ADR-025 |
| Message routing was implicit | Replaced by ADR-024 |
| Protocol messages were limited to the initial simplified set | Expanded and formalized in `protocol.md` |
| Session state machine was undefined | Defined in `state-machines.md` and ADR-008 |
| Database entities were only preliminary | Persistent domain model established in ADR-032 |
| Agent recovery state was undefined | Established as complementary to C2 persistence in ADR-033 |

---

# Relationship with Other Documentation

`DECISIONS.md` records **why** major architectural choices were made.

It does not replace the normative technical specifications.

| Concern | Authoritative Document |
|---|---|
| Global architecture | `ARCHITECTURE.md` |
| Architectural decisions | `DECISIONS.md` |
| Data entities and relationships | `data-model.md` |
| Logical state machines | `state-machines.md` |
| Protocol message contract | `protocol.md` |
| Protocol/state interactions | `protocol-state-transition.md` |
| Reconnection and reconciliation | `reconnection-and-synchronization.md` |
| Task lifecycle | `task-lifecycle.md` |
| Network architecture | `network-architecture.md` |
| File transfer lifecycle | `file-transfer.md` |
| Testing approach | `testing-strategy.md` |
| Security controls and mitigations | `countermeasures.md` / security documentation |

When a detailed document defines a domain-specific rule, `DECISIONS.md` records the architectural rationale where appropriate, while the detailed document remains authoritative for the actual specification.

---

# Current Decision Baseline

The current architecture is based on the following major decisions:

```text
C2 Server / Agent separation
        ↓
Modular-monolithic C2
        ↓
Interface / Core separation
        ↓
Protocol / Transport separation
        ↓
TCP/TLS MVP transport
        ↓
Agent / Session separation
        ↓
Explicit Session lifecycle
        ↓
Separate Agent communication state
        ↓
Explicit asynchronous Task lifecycle
        ↓
Task / Result separation
        ↓
Explicit Message Router
        ↓
Dedicated Synchronization Manager
        ↓
Database / File Storage separation
        ↓
Controlled file workspaces
        ↓
TLS + explicit file integrity verification
        ↓
Platform abstraction
        ↓
Authorized laboratory-only scope
```

This baseline should be treated as the current architectural reference unless a later ADR explicitly supersedes one of these decisions.
