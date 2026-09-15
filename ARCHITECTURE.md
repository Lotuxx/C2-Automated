# Architecture

## 1. Purpose

This document defines the high-level architecture of the **C2-AUTOMATED** project.

It describes:

- the global organization of the system;
- the responsibilities of the C2 server and the agent;
- the boundaries between major components;
- the communication architecture;
- the task and result flows;
- the file-transfer architecture;
- the storage model;
- the main security boundaries;
- the principal extensibility points.

The goal is to maintain a modular architecture in which major components can evolve independently without requiring a redesign of the entire system.

This document defines the **architectural structure** of the project. Detailed state machines, protocol semantics, data models, and network behavior are defined in their respective documents.

---

# 2. Authorized-Use Scope

**C2-AUTOMATED is an academic and laboratory project intended exclusively for authorized cybersecurity experimentation, development, testing, and demonstration.**

The C2 server and Agent are designed to operate only in environments where the operator has explicit authorization to deploy, control, monitor, and test the participating systems.

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

The architecture may contain components that model capabilities commonly associated with command-and-control infrastructure. Their inclusion in this academic project does not extend the authorized scope of use.

All implementation, testing, demonstrations, and deployment activities must remain within the authorized environment defined for the project.

Security analysis and defensive considerations should therefore be evaluated with the project treated as a **controlled laboratory system**, rather than as infrastructure intended for unauthorized operational deployment.

---

# 3. Architectural Overview

The system is composed of three principal elements:

- **Operator Interface** — provides the human operator with access to the C2;
- **C2 Server** — coordinates agents, sessions, tasks, results, communication, and server-side storage;
- **Agent** — runs on an endpoint, communicates with the C2 server, executes supported tasks, and returns results.

The fundamental architectural principle is:

> **The C2 server manages agents, sessions, tasks, and coordination; the agent executes tasks and returns execution evidence and results.**

The project follows a modular-monolithic architecture on the C2 side and a modular component architecture on the Agent side.

---

# 4. Global Architecture

## 4.1 High-Level Architecture

```text
                         ┌───────────────────────┐
                         │       OPERATOR        │
                         │      human user       │
                         └───────────┬───────────┘
                                     │
                          ┌──────────┼──────────┐
                          ▼          ▼          ▼
                         CLI        TUI        WEB
                          │
                          └──────────┬──────────┘
                                     │
                                     ▼
                         ┌───────────────────────┐
                         │      C2 SERVER        │
                         │                       │
                         │ Interface             │
                         │ Core                  │
                         │ Protocol              │
                         │ Transport             │
                         │ Storage               │
                         │ File Management       │
                         │ Logging               │
                         │ Configuration         │
                         └───────────┬───────────┘
                                     │
                                  TCP/TLS
                                     │
                    ┌────────────────┼────────────────┐
                    │                │                │
                    ▼                ▼                ▼
              ┌────────────┐   ┌────────────┐   ┌────────────┐
              │   Agent A  │   │   Agent B  │   │   Agent C  │
              │            │   │            │   │            │
              │ Core       │   │ Core       │   │ Core       │
              │ Beacon     │   │ Beacon     │   │ Beacon     │
              │ Protocol   │   │ Protocol   │   │ Protocol   │
              │ Transport  │   │ Transport  │   │ Transport  │
              │ Executor   │   │ Executor   │   │ Executor   │
              │ Commands   │   │ Commands   │   │ Commands   │
              │ Platform   │   │ Platform   │   │ Platform   │
              └────────────┘   └────────────┘   └────────────┘
```

The C2 server is designed to coordinate multiple agents concurrently.

Each Agent maintains its own:

- identity;
- communication logic;
- execution state;
- platform-specific functionality;
- local transfer workspace.

The C2 maintains the persistent server-side representation of the overall system.

---

# 5. Architectural Principles

## 5.1 Separation of Responsibilities

Operator interfaces, application logic, protocol handling, transport, persistence, and endpoint execution are kept separate.

A component should not become responsible for unrelated concerns.

For example:

```text
Interface
    ↓
C2 Core
    ↓
Protocol
    ↓
Transport
```

rather than allowing the operator interface to manipulate sockets or database records directly.

---

## 5.2 Protocol / Transport Separation

The system distinguishes:

> **Protocol = what is exchanged**

from:

> **Transport = how it is transmitted**

Logical protocol messages should remain independent from the underlying transport implementation.

This allows the transport implementation to evolve without redesigning the application-level protocol.

---

## 5.3 Beacon / Transport Separation

On the Agent:

> **Beacon = when the agent communicates**

> **Transport = how the communication is performed**

The beacon mechanism therefore does not directly depend on a particular network implementation.

---

## 5.4 Agent / Session Separation

An **Agent** represents a persistent endpoint identity.

A **Session** represents a specific communication episode associated with that Agent.

Therefore:

```text
Agent A001
 ├── Session S041
 ├── Session S042
 └── Session S043
```

A new connection creates a new Session. A previous Session is never reopened as the current communication Session.

This allows historical communication to remain associated with the Agent while new connections are represented independently.

---

## 5.5 Asynchronous Multi-Agent Operation

The C2 is designed to manage multiple agents and multiple tasks without coupling an operator action to one blocking network request.

Tasks, results, communication events, and sessions are therefore handled as independent domain objects.

---

## 5.6 Storage Abstraction

Application logic depends on storage abstractions rather than directly depending on SQLite or the filesystem.

This separates:

```text
Domain / Application Logic
            │
            ▼
      Storage Interface
         ┌──────┐
         ▼      ▼
      Database Files
```

---

## 5.7 Platform Abstraction

The Agent separates common logic from operating-system-specific functionality.

The architecture therefore allows:

```text
Common Agent Logic
        │
        ▼
Platform Abstraction
      ┌─┴─┐
      ▼   ▼
    Linux Windows
```

Linux is the primary target. Windows is an extension/bonus target.

---

# 6. C2 Server Architecture

The C2 server follows a modular-monolithic architecture.

```text
c2_server/
│
├── main.py
│
├── interface/
│   ├── cli/
│   │   ├── app.py
│   │   ├── commands.py
│   │   └── views.py
│   ├── tui/
│   └── web/
│
├── core/
│   ├── c2.py
│   ├── agent_manager.py
│   ├── session_manager.py
│   ├── task_manager.py
│   ├── result_manager.py
│   ├── file_manager.py
│   ├── message_router.py
│   └── synchronization_manager.py
│
├── protocol/
│   ├── messages.py
│   ├── serializer.py
│   └── validator.py
│
├── transport/
│   ├── interface.py
│   └── tcp_tls.py
│
├── storage/
│   ├── interface.py
│   ├── sqlite.py
│   └── models.py
│
├── logging/
│   └── logger.py
│
├── config/
│   └── settings.py
│
└── tests/
```

The server is divided into several architectural layers:

```text
Interface
    │
    ▼
Core
    │
    ├── Protocol
    │
    ├── Transport
    │
    └── Storage
```

The Core coordinates these components without absorbing their implementation responsibilities.

---

# 7. C2 Entry Point

## 7.1 `main.py`

`main.py` is the entry point of the C2 server.

Its primary responsibility is application initialization and component assembly.

Conceptually:

```text
main.py
   │
   ├── load configuration
   ├── initialize logging
   ├── initialize storage
   ├── create C2 core
   ├── create transport
   ├── connect components
   └── start operator interface
```

`main.py` should remain an initialization layer rather than becoming a container for C2 business logic.

---

# 8. Operator Interface

Location:

```text
interface/
├── cli/
├── tui/
└── web/
```

The interface layer provides operator-facing access to the C2.

The initial MVP uses a CLI.

TUI and Web interfaces are architectural extension points and should reuse the same C2 core rather than implementing independent C2 logic.

```text
Operator
   │
   ▼
CLI / TUI / Web
   │
   ▼
C2 Core
```

The interface layer should not directly:

- manage network sockets;
- perform TLS operations;
- execute endpoint commands;
- manipulate database records directly.

---

# 9. C2 Core

Location:

```text
core/
├── c2.py
├── agent_manager.py
├── session_manager.py
├── task_manager.py
├── result_manager.py
├── file_manager.py
├── message_router.py
└── synchronization_manager.py
```

The Core contains the main server-side application logic.

Its components have distinct responsibilities.

---

## 9.1 `c2.py`

`c2.py` acts as the main orchestration component.

It provides the main application-level boundary used by the operator interfaces and coordinates the other Core components.

Conceptually:

```text
                           C2
                            │
          ┌─────────────────┼──────────────────┐
          ▼                 ▼                  ▼
   Agent Manager      Task Manager      Result Manager
          │                 │                  │
          ▼                 ▼                  ▼
   Session Manager    Message Router    File Manager
                            │
                            ▼
                  Synchronization Manager
```

The exact internal call graph remains an implementation concern.

---

## 9.2 `agent_manager.py`

The Agent Manager manages the logical representation of known Agents.

It is responsible for Agent identity and Agent-level information.

Examples include:

```text
agent_id
hostname
OS
architecture
address
health
activity
last_seen
```

The Agent Manager does not:

- execute commands;
- directly manage network sockets;
- render the operator interface;
- embed database access throughout the application.

Detailed Agent state semantics are defined in `state-machines.md` and `data-model.md`.

---

## 9.3 `session_manager.py`

The Session Manager manages communication Sessions associated with Agents.

Conceptually:

```text
Agent A001
    │
    ├── S041
    ├── S042 = historical
    └── S043 = current
```

A Session represents one communication episode.

The architectural rule is:

```text
new connection
      ↓
new Session
      ↓
transport established
      ↓
Session CONNECTED
```

Registration occurs over the already established Session and does not create or reopen the Session.

Detailed Session states and transitions are defined in `state-machines.md`.

---

## 9.4 `task_manager.py`

The Task Manager creates, dispatches, tracks, and recovers Tasks.

The authoritative Task lifecycle is:

```text
PENDING
   ↓
WAITING_ACK
   ↓
QUEUED
   ↓
RUNNING
   ├───────────────┐
   ▼               ▼
COMPLETED        FAILED
   │
   ├── TIMEOUT
   └── CANCELLED
```

The complete normative state model and transition rules are defined in:

- `state-machines.md`;
- `task-lifecycle.md`;
- `protocol-state-transition.md`.

A Task belongs to an Agent and is not owned by a Session.

A Task may therefore survive a communication interruption and continue to be associated with the same Agent across multiple Sessions.

---

## 9.5 `result_manager.py`

The Result Manager processes results returned by Agents.

Conceptually:

```text
Agent
   │
   │ RESULT
   ▼
Message Router
   │
   ▼
Result Manager
   │
   ├── identify Task
   ├── validate Result
   ├── persist Result
   └── update relevant Task state
```

A Result is associated with:

```text
result_id
task_id
agent_id
status
timestamp
data
```

The Result represents execution evidence or returned data. It is therefore distinct from the Task lifecycle itself.

Detailed Result semantics are defined in `data-model.md` and `task-lifecycle.md`.

---

## 9.6 `file_manager.py`

The File Manager manages the logical lifecycle of file transfers.

Its responsibilities include:

- transfer coordination;
- transfer metadata;
- association with Tasks when applicable;
- transfer completion;
- integrity verification;
- interaction with file storage.

It does not represent the physical file-storage implementation.

The separation is:

```text
             File Manager
                  │
          ┌───────┴────────┐
          ▼                ▼
 Transfer Metadata     File Storage
          │                │
          ▼                ▼
       Database         Filesystem
```

Detailed transfer behavior is defined in `file-transfer.md`.

---

## 9.7 `message_router.py`

The Message Router is responsible for routing validated protocol messages to the appropriate Core component.

Conceptually:

```text
Transport
   │
   ▼
Protocol
   │
   ▼
Validation
   │
   ▼
Message Router
   │
   ├── Agent Manager
   ├── Session Manager
   ├── Task Manager
   ├── Result Manager
   ├── File Manager
   └── Synchronization Manager
```

This prevents protocol-receiving logic from becoming distributed across unrelated components.

The router is responsible for **dispatching messages**, not for implementing the complete business logic associated with each message.

---

## 9.8 `synchronization_manager.py`

The Synchronization Manager handles reconciliation between the C2's persistent state and the Agent's local recovery state following a new communication Session.

Conceptually:

```text
New Session
    │
    ▼
REGISTER
    │
    ▼
REGISTER_ACK
    │
    ▼
SYNC_STATE
    │
    ▼
Synchronization Manager
    │
    ├── compare known state
    ├── identify missing information
    ├── determine required updates
    └── prepare synchronization response
    │
    ▼
SYNC_STATE_RESPONSE
    │
    ▼
SYNC_COMPLETE
```

Synchronization does not create a new Agent identity and does not reopen a previous Session.

Detailed reconciliation behavior is defined in `reconnection-and-synchronization.md`.

---

# 10. Protocol Architecture

Location:

```text
protocol/
├── messages.py
├── serializer.py
└── validator.py
```

The protocol defines the logical communication language shared by the C2 and Agents.

The protocol is intentionally separated from the transport layer.

---

## 10.1 Message Types

The architecture currently accounts for message categories including:

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

### Task management

```text
TASK
TASK_ACK
TASK_STATUS_QUERY
TASK_STATUS
```

### Results and errors

```text
RESULT
ERROR
```

### File transfer

```text
FILE_START
FILE_CHUNK
FILE_END
```

The exact message contract is defined in `protocol.md`.

---

## 10.2 `messages.py`

Defines the supported protocol message structures and message types.

---

## 10.3 `serializer.py`

Converts protocol representations into the transmissible representation and reconstructs received messages.

---

## 10.4 `validator.py`

Validates messages before they reach application-level processing.

Validation is a protocol responsibility and should occur before Core components act on received data.

---

# 11. Transport Architecture

Location:

```text
transport/
├── interface.py
└── tcp_tls.py
```

The transport layer is responsible for network communication.

The application and protocol layers should not depend directly on sockets or a specific transport implementation.

---

## 11.1 Transport Interface

`interface.py` defines the abstraction used by the application for communication.

The transport interface allows the rest of the system to work with a transport without depending on its implementation details.

---

## 11.2 TCP/TLS

`tcp_tls.py` provides the mandatory MVP transport.

The current extension model is:

```text
Transport Interface
       │
       ├── TCP/TLS     ← MVP
       ├── HTTP        ← possible extension
       └── DNS         ← possible extension
```

Additional transports are not part of the mandatory MVP.

---

# 12. Communication Architecture

The communication architecture is layered:

```text
Application / Core
        │
        ▼
Protocol
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
Protocol
        │
        ▼
Application / Core
```

The principal conceptual distinction is:

```text
Beacon
  │
  │ determines when
  ▼
Transport
  │
  │ determines how
  ▼
Protocol
  │
  │ determines what
  ▼
Core
  │
  │ determines what the system does
```

The complete network architecture is defined in `network-architecture.md`.

The complete protocol behavior is defined in `protocol.md` and `protocol-state-transition.md`.

---

# 13. Registration, Session and Synchronization

A new Agent communication episode follows this architectural sequence:

```text
Agent
  │
  ▼
Establish TCP/TLS connection
  │
  ▼
New Session
  │
  ▼
Session CONNECTED
  │
  ▼
REGISTER
  │
  ▼
C2 identifies Agent
  │
  ▼
REGISTER_ACK(session_id)
  │
  ▼
Agent communication SYNCHRONIZING
  │
  ▼
SYNC_STATE
  │
  ▼
State reconciliation
  │
  ▼
SYNC_STATE_RESPONSE
  │
  ▼
SYNC_COMPLETE
  │
  ▼
Normal communication
```

The important architectural distinction is:

```text
Session state
    ≠
Agent communication state
```

For example, during synchronization:

```text
Session = CONNECTED
Agent communication = SYNCHRONIZING
```

Registration does not cause the Session to become `CONNECTED`; transport establishment does.

Detailed state semantics are defined in `state-machines.md`.

---

# 14. Storage Architecture

Storage is divided between structured persistent data and physical file data.

```text
                         Storage
                            │
                ┌───────────┴───────────┐
                ▼                       ▼
          Structured Data          File Contents
                │                       │
                ▼                       ▼
             SQLite                Filesystem
```

The principle is:

> **Database = structured metadata and persistent domain state**

> **File storage = actual file contents**

---

## 14.1 Database Storage

Location:

```text
storage/
├── interface.py
├── sqlite.py
└── models.py
```

The database stores structured information such as:

```text
agents
sessions
tasks
results
file transfers
events
```

### `interface.py`

Defines the database storage abstraction.

### `sqlite.py`

Provides the SQLite implementation.

### `models.py`

Defines persistence-layer models.

The Core should interact with the storage abstraction rather than embedding database-specific queries throughout the application.

---

## 14.2 File Storage

The file-storage abstraction handles physical file data separately from structured metadata.

The C2 architecture uses:

```text
File Manager
      │
      ▼
File Storage Interface
      │
      ▼
Filesystem Implementation
```

The exact transfer lifecycle is defined in `file-transfer.md`.

---

# 15. Server File Organization

The C2 maintains a dedicated file workspace:

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
    Files received by the C2.

downloads/
    Files prepared for transfer to an Agent.

temporary/
    Temporary transfer workspace.
```

The physical organization is an implementation detail of the file-storage layer and should not be confused with the logical transfer lifecycle.

---

# 16. Agent Architecture

The Agent follows the same separation-of-concerns principle while adding endpoint-specific components.

```text
agent/
├── core/
├── beacon/
├── protocol/
├── transport/
├── executor/
├── commands/
├── platform/
│
├── storage/
│   └── files/
│       ├── interface.py
│       └── filesystem.py
│
├── data/
│   └── files/
│       ├── uploads/
│       ├── downloads/
│       └── temporary/
│
└── tests/
```

---

## 16.1 Core

The Agent Core contains common Agent logic and internal state.

It maintains information such as:

```text
agent_id
hostname
OS
architecture
configuration
state
```

The Core does not directly implement individual commands or platform-specific operations.

---

## 16.2 Beacon

The Beacon component manages when the Agent communicates.

It handles concepts such as:

```text
interval
jitter
retry
```

The Beacon remains independent of the transport implementation.

```text
Beacon
  │
  │ determines when
  ▼
Transport
  │
  │ determines how
  ▼
Network
```

Detailed liveness and communication behavior is defined in `state-machines.md`.

---

## 16.3 Protocol

The Agent implements the same logical protocol contract as the C2.

Its responsibilities include:

- constructing protocol messages;
- parsing received messages;
- validating messages;
- passing valid messages to the appropriate Agent component.

---

## 16.4 Transport

The Agent-side transport manages communication with the C2.

The transport implementation remains independent from the logical protocol.

---

## 16.5 Executor

The Executor receives Tasks and dispatches them to the appropriate command implementation.

Conceptually:

```text
TASK
  │
  ▼
Executor
  │
  ▼
Command Handler
  │
  ▼
Execution
  │
  ▼
Result
```

The Executor therefore separates Task dispatch from the implementation of individual commands.

---

## 16.6 Commands

The command layer contains the operations supported by the Agent.

The architecture may expose operations such as:

```text
SHELL
SYSINFO
FILES
PERSISTENCE
SELF_DESTRUCT
```

The exact command set and contracts remain subject to the project requirements and implementation constraints.

Commands should remain behind the Executor boundary rather than being directly invoked by the communication layer.

---

## 16.7 Platform

The Platform layer isolates operating-system-specific functionality.

Conceptually:

```text
Common Agent Logic
        │
        ▼
Platform Abstraction
      ┌─┴─┐
      ▼   ▼
    Linux Windows
```

Linux is the primary implementation target.

Windows support is an extension/bonus objective.

---

# 17. Agent-Side File Architecture

The Agent maintains its own controlled file-storage workspace.

```text
storage/
└── files/
    ├── interface.py
    └── filesystem.py
```

Physical file data is stored under:

```text
data/
└── files/
    ├── uploads/
    ├── downloads/
    └── temporary/
```

The conceptual relationship is:

```text
Agent File Operations
        │
        ▼
File Storage Interface
        │
        ▼
Filesystem Storage
        │
        ▼
data/files/
```

File-transfer handling should remain separate from arbitrary local filesystem access.

---

# 18. Task and Result Architecture

The principal Task flow is:

```text
Operator
    │
    ▼
Interface
    │
    ▼
C2 Core
    │
    ▼
Task Manager
    │
    ▼
Protocol
    │
    ▼
Transport
    │
    ▼
Agent
    │
    ▼
Executor
    │
    ▼
Command
```

The execution result follows the reverse communication path:

```text
Command
    │
    ▼
Executor
    │
    ▼
Agent Protocol
    │
    ▼
Transport
    │
    ▼
C2 Transport
    │
    ▼
Protocol
    │
    ▼
Message Router
    │
    ▼
Result Manager
    │
    ▼
Interface
    │
    ▼
Operator
```

The Task and Result remain separate domain objects:

```text
Agent
   │
   └── Task
         │
         └── Result
```

A communication interruption does not automatically redefine the Task state.

A Task may therefore remain pending, queued, running, or otherwise recoverable while the Agent temporarily cannot communicate.

Detailed behavior is defined in `task-lifecycle.md`.

---

# 19. File Transfer Architecture

File transfers use the protocol and transport layers while keeping transfer management and physical storage separate.

The logical transfer protocol is:

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

Chunks are processed incrementally.

Conceptually:

```text
chunk
  ↓
write
  ↓
chunk
  ↓
write
  ↓
...
  ↓
reconstruct
  ↓
integrity verification
  ↓
final file
```

This avoids requiring the complete file to remain in memory.

---

## 19.1 C2 to Agent

```text
C2 File Storage
      │
      ▼
File Manager
      │
      ▼
Protocol
      │
      ▼
TLS Transport
      │
      ▼
Agent
      │
      ▼
Temporary Workspace
      │
      ▼
Integrity Verification
      │
      ▼
Agent File Storage
```

---

## 19.2 Agent to C2

```text
Agent File Storage
      │
      ▼
Agent File Handling
      │
      ▼
Protocol
      │
      ▼
TLS Transport
      │
      ▼
C2
      │
      ▼
File Manager
      │
      ▼
Temporary Workspace
      │
      ▼
Integrity Verification
      │
      ▼
C2 File Storage
```

The exact transfer state model is defined in `file-transfer.md`.

---

# 20. File Confidentiality and Integrity

The architecture distinguishes encryption in transit from encryption at rest.

## 20.1 Encryption in Transit

TCP/TLS is the mandatory MVP transport.

File transfers use the same protected transport.

```text
File
  │
  ▼
Protocol
  │
  ▼
TLS
  │
  ▼
Encrypted Network Traffic
  │
  ▼
TLS
  │
  ▼
File
```

---

## 20.2 Encryption at Rest

Application-level encryption of individual files is not part of the mandatory MVP.

It may be considered later as a defense-in-depth feature, but would introduce additional key-management and testing requirements.

---

## 20.3 File Integrity

Transferred files are verified after reconstruction using a cryptographic hash.

```text
Original File
     │
     ▼
 Hash
     │
     ▼
 Transfer
     │
     ▼
Reconstructed File
     │
     ▼
 Hash
     │
     ▼
 Compare
```

A successful comparison provides integrity evidence for the reconstructed content.

Detailed transfer integrity behavior is defined in `file-transfer.md`.

---

# 21. Component Dependency Boundaries

The primary dependency direction is:

```text
Interface
    ↓
Core
    ↓
Protocol
    ↓
Transport
    ↓
Network
```

Persistence is accessed through abstractions:

```text
Core
 ├── Database Interface
 │        ↓
 │      SQLite
 │
 └── File Storage Interface
          ↓
       Filesystem
```

The Agent follows a similar communication boundary:

```text
Agent Core / Beacon / Executor
              ↓
           Protocol
              ↓
           Transport
```

Execution remains separated:

```text
Agent
 ├── Executor
 │     ↓
 │   Commands
 │
 └── Platform
```

These boundaries are intended to reduce coupling and make components easier to test and replace.

---

# 22. Security Boundaries

The architecture contains several security-sensitive boundaries:

```text
Operator Interaction
        │
        ▼
Application Logic
        │
        ├──────► Persistent Storage
        │
        ▼
Protocol Validation
        │
        ▼
Protected Transport
        │
        ▼
Agent
        │
        ▼
Executor / Command Boundary
        │
        ▼
Local File Handling
```

Important principles include:

- messages must be validated before being processed by application logic;
- transport protection does not replace protocol validation;
- data received from an Agent should not automatically be considered trusted;
- Tasks should pass through the Agent's Executor and command layers;
- file transfers should remain within the defined file-management and storage boundaries;
- security-sensitive actions should remain observable through logging and event records.

Detailed security controls and mitigations are documented separately.

---

# 23. Extensibility

The architecture deliberately provides several extension points.

## 23.1 Operator Interfaces

```text
Interface
 ├── CLI       ← MVP
 ├── TUI       ← extension
 └── Web       ← extension
```

All interfaces reuse the same C2 Core.

---

## 23.2 Transport

```text
Transport Interface
 ├── TCP/TLS    ← MVP
 ├── HTTP       ← possible extension
 └── DNS        ← possible extension
```

Additional transports should not require redesigning the Task, Agent, or Result management logic.

---

## 23.3 Database

```text
Database Interface
        │
        └── SQLite
```

A different database backend can therefore be introduced without redesigning the Core domain logic.

---

## 23.4 File Storage

```text
File Storage Interface
        │
        └── Filesystem
```

The physical storage implementation can evolve independently from the logical file-transfer lifecycle.

---

## 23.5 Agent Platform

```text
Platform Interface
       ├── Linux       ← primary
       └── Windows     ← extension
```

The Executor and command architecture should allow platform-specific implementations without duplicating the complete Agent architecture.

---

# 24. Repository Mapping

The architecture maps to the implementation as follows.

## C2 Server

| Architectural Component | Implementation |
|---|---|
| Entry point | `c2_server/main.py` |
| Operator interface | `c2_server/interface/` |
| C2 core | `c2_server/core/` |
| Agent management | `c2_server/core/agent_manager.py` |
| Session management | `c2_server/core/session_manager.py` |
| Task management | `c2_server/core/task_manager.py` |
| Result management | `c2_server/core/result_manager.py` |
| File management | `c2_server/core/file_manager.py` |
| Message routing | `c2_server/core/message_router.py` |
| Synchronization | `c2_server/core/synchronization_manager.py` |
| Protocol | `c2_server/protocol/` |
| Transport | `c2_server/transport/` |
| Database storage | `c2_server/storage/` |
| Logging | `c2_server/logging/` |
| Configuration | `c2_server/config/` |
| Tests | `c2_server/tests/` |

## Agent

| Architectural Component | Implementation |
|---|---|
| Agent core | `agent/core/` |
| Beacon | `agent/beacon/` |
| Protocol | `agent/protocol/` |
| Transport | `agent/transport/` |
| Executor | `agent/executor/` |
| Commands | `agent/commands/` |
| Platform-specific functionality | `agent/platform/` |
| File storage | `agent/storage/files/` |
| File data | `agent/data/files/` |
| Tests | `agent/tests/` |

---

# 25. Relationship with Other Documentation

`ARCHITECTURE.md` provides the global architectural view.

It should not duplicate detailed normative definitions maintained elsewhere.

| Concern | Authoritative Document |
|---|---|
| Authorized-use scope | `ARCHITECTURE.md` |
| Global architecture | `ARCHITECTURE.md` |
| Data entities and relationships | `data-model.md` |
| Logical state machines | `state-machines.md` |
| Protocol message contract | `protocol.md` |
| Protocol/state interactions | `protocol-state-transition.md` |
| Reconnection and reconciliation | `reconnection-and-synchronization.md` |
| Task lifecycle | `task-lifecycle.md` |
| Network architecture | `network-architecture.md` |
| File transfer lifecycle | `file-transfer.md` |
| Architectural decisions | `DECISIONS.md` |
| Testing approach | `testing-strategy.md` |
| Security controls and mitigations | `countermeasures.md` / security documentation |

When a detailed document defines a domain-specific rule, this document should reference that rule rather than reproduce it.

---

# 26. Architectural Invariants

The following principles must remain true across implementations.

### Authorized Use

```text
Project
   │
   ▼
Authorized laboratory / academic environment
   │
   ├── Controlled systems
   ├── Explicitly authorized testing
   └── Academic demonstrations
```

The architecture does not authorize deployment or testing against systems outside the controlled scope.

---

### Agent and Session

```text
One Agent identity
        ↓
Many Sessions over time
```

A new connection creates a new Session.

---

### Session and Communication

```text
Transport established
        ↓
Session CONNECTED
        ↓
REGISTER
        ↓
Communication SYNCHRONIZING
        ↓
Synchronization complete
        ↓
Communication CONNECTED
```

Session state and Agent communication state are separate concepts.

---

### Task and Session

```text
Task
 │
 ├── created in one Session
 ├── may execute during another Session
 └── may be reconciled after reconnection
```

A Task is associated with an Agent, not permanently with one Session.

---

### Protocol and Transport

```text
Protocol ≠ Transport
```

The logical message contract should remain independent from the transport implementation.

---

### File Transfer and Storage

```text
Transfer Lifecycle ≠ Physical Storage
```

The File Manager manages the logical transfer while the storage layer manages the physical data.

---

### Interface and Core

```text
Operator Interface ≠ C2 Business Logic
```

CLI, TUI, and Web interfaces must use the same Core.

---

# 27. Current Architectural Status

This document represents the current architectural baseline of the project.

The following areas are established:

- authorized academic/laboratory use as the project scope;
- C2 server / Agent separation;
- modular-monolithic C2 architecture;
- multi-Agent operation;
- Agent / Session distinction;
- interface / Core / protocol / transport separation;
- protocol / transport separation;
- beacon / transport separation;
- asynchronous Task and Result model;
- explicit message routing;
- synchronization as a dedicated architectural responsibility;
- database / file-storage separation;
- controlled file workspaces;
- TCP/TLS as the MVP transport;
- file integrity verification;
- Linux as the primary Agent platform;
- extensibility for additional interfaces, transports, storage backends, and Windows support.

The following areas remain implementation-level concerns or require further detailed specification:

- exact class and function interfaces;
- exact database schema;
- concrete asynchronous/concurrency implementation;
- exact command implementations;
- detailed error-handling behavior;
- final implementation of optional interfaces and extensions.

The following areas are no longer considered undefined at the architectural level because they are specified by the corresponding documents:

- Session lifecycle;
- Agent communication states;
- Task lifecycle;
- protocol message categories;
- registration and synchronization flow;
- Agent/Session/Task/Result relationships;
- network-layer responsibilities.

Major changes to component responsibilities, dependencies, or system interactions should be recorded in `DECISIONS.md` and reflected in this document.
