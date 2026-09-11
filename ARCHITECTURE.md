# Architecture

## 1. Purpose

This document defines the architecture of the **C2-AUTOMATED** project.

It describes:

- the global organization of the system;
- the responsibilities of the C2 server and the agent;
- the boundaries between major components;
- the communication architecture;
- the task and result flows;
- the file-transfer architecture;
- the storage model;
- the security boundaries;
- the main extensibility points.

The goal is to maintain a modular architecture in which major components can evolve independently without requiring a redesign of the entire system.

---

# 2. Global Architecture

The system is composed of three main elements:

- **Operator Interface** — provides the human operator with access to the C2.
- **C2 Server** — coordinates agents, sessions, tasks, results, communication, and server-side storage.
- **Agent** — runs on the endpoint, communicates with the C2 server, executes supported tasks, and returns results.

The fundamental architectural principle is:

> **The C2 server manages agents and tasks; the agent executes tasks and returns results.**

## 2.1 High-Level Architecture

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
                               TCP/TLS (MVP)
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

The server is designed to coordinate multiple agents simultaneously. Each agent independently maintains its own execution, platform-specific functionality, and local file storage.

---

# 3. Architectural Principles

The system follows several principles that guide the implementation.

## 3.1 Separation of Responsibilities

Operator interfaces, application logic, protocol handling, transport, persistence, and endpoint execution are kept separate.

This prevents one component from becoming responsible for unrelated concerns.

## 3.2 Protocol / Transport Separation

The system distinguishes:

> **Protocol = what is exchanged**

from:

> **Transport = how it is transmitted**

The same logical message should not need to be redesigned simply because the underlying transport changes.

## 3.3 Beacon / Transport Separation

On the agent:

> **Beacon = when the agent communicates**

> **Transport = how the communication is performed**

The beacon therefore remains independent from the underlying network implementation.

## 3.4 Multi-Agent Operation

The server is designed to maintain several independent agent sessions and tasks simultaneously rather than relying on one blocking request/response exchange.

## 3.5 Storage Abstraction

Application logic should depend on storage interfaces rather than directly depending on a specific database or filesystem implementation.

## 3.6 Platform Abstraction

The agent separates common logic from platform-specific functionality so that Linux and future Windows support can coexist without spreading operating-system-specific logic throughout the entire agent.

---

# 4. C2 Server Architecture

The C2 server uses a modular monolithic structure.

```text
c2_server/
│
├── main.py
│
├── interface/
│   ├── cli/
│   ├── tui/
│   └── web/
│
├── core/
│   ├── c2.py
│   ├── agent_manager.py
│   ├── session_manager.py
│   ├── task_manager.py
│   ├── result_manager.py
│   └── file_manager.py
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
│   ├── database/
│   │   ├── interface.py
│   │   ├── sqlite.py
│   │   └── models.py
│   │
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
├── logging/
├── config/
└── tests/
```

---

## 4.1 `main.py`

`main.py` is the entry point of the C2 server.

Its role is to initialize and assemble the application components.

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

`main.py` should remain an initialization layer rather than becoming a container for the main C2 business logic.

---

## 4.2 Interface Layer

Location:

```text
interface/
├── cli/
├── tui/
└── web/
```

The interface layer provides operator-facing interfaces.

The initial MVP uses a CLI. TUI and Web interfaces are treated as extensions.

All interfaces should interact with the same C2 core rather than implementing independent versions of the C2 logic.

Conceptually:

```text
Operator
   │
   ▼
CLI / TUI / Web
   │
   ▼
C2 Core
```

The interface layer should not directly manage sockets, TLS, database queries, or endpoint execution.

---

# 5. C2 Core

Location:

```text
core/
├── c2.py
├── agent_manager.py
├── session_manager.py
├── task_manager.py
├── result_manager.py
└── file_manager.py
```

The core contains the main application logic of the C2 server.

## 5.1 `c2.py`

`c2.py` acts as the main orchestration component.

It coordinates the major server-side managers without taking over their individual responsibilities.

Conceptually:

```text
                         C2
                          │
          ┌───────────────┼───────────────┐
          ▼               ▼               ▼
    Agent Manager    Task Manager    Result Manager
          │
          ├── Session Manager
          └── File Manager
```

The C2 core provides the main application-level boundary used by the operator interfaces.

---

## 5.2 `agent_manager.py`

The Agent Manager manages the logical representation of known agents.

It can maintain information such as:

```text
agent_id
hostname
OS
architecture
address
status
last_seen
transport
```

Its responsibility is to manage the **agent identity and logical state**.

It does not:

- execute commands;
- directly manage sockets;
- render the operator interface;
- scatter SQL queries throughout the application.

---

## 5.3 `session_manager.py`

The Session Manager handles communication-session state.

An **agent** represents a persistent identity.

A **session** represents a communication instance associated with that agent.

Conceptually:

```text
Agent A001
    │
    └── Session S42
          ├── connection state
          ├── transport
          ├── last communication
          └── communication state
```

This distinction allows an agent to disconnect and reconnect while retaining its identity.

```text
connect
   ↓
communicate
   ↓
disconnect
   ↓
reconnect
   ↓
new session
```

The exact session state machine remains part of the detailed implementation design.

---

## 5.4 `task_manager.py`

The Task Manager creates and tracks tasks sent to agents.

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

The Task Manager allows the C2 to track multiple independent tasks without coupling task management directly to the network transport.

---

## 5.5 Task Queue and Asynchronous Operation

The server should not directly couple an operator command to a single blocking socket operation.

Instead:

```text
Operator
   │
   ▼
Interface
   │
   ▼
Task Manager
   │
   ▼
Task = PENDING
   │
   ▼
Communication
   │
   ▼
Agent
```

This provides the foundation for asynchronous multi-agent operation.

Conceptually:

```text
TASK QUEUE

A001 → [T004, T005]
A002 → [T006]
A003 → []
```

Several agents can therefore have independent tasks at the same time.

---

## 5.6 `result_manager.py`

The Result Manager handles results returned by agents.

Conceptually:

```text
Agent
   │
   │ RESULT
   ▼
Result Manager
   │
   ├── identify task
   ├── associate result with agent
   ├── persist result
   └── expose result to operator
```

A result is conceptually associated with:

```text
result_id
task_id
agent_id
status
timestamp
data
```

This creates traceability between:

```text
Agent
   │
   └── Task
        │
        └── Result
```

---

## 5.7 `file_manager.py`

The File Manager handles the **logical lifecycle of file transfers**.

It is responsible for transfer-related concepts such as:

- transfer state;
- association with tasks;
- transfer completion;
- file reconstruction;
- integrity verification.

It does not itself represent the physical storage mechanism.

The separation is:

```text
              File Manager
                    │
          ┌─────────┴─────────┐
          ▼                   ▼
   Transfer metadata     File Storage
          │                   │
          ▼                   ▼
      Database           Filesystem
```

---

# 6. Protocol Architecture

Location:

```text
protocol/
├── messages.py
├── serializer.py
└── validator.py
```

The protocol defines the logical language exchanged between the server and agents.

## 6.1 Message Types

The architecture currently accounts for messages such as:

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

A message may contain common metadata such as:

```text
version
message_id
agent_id
type
timestamp
payload
```

The exact protocol contract will be defined separately before implementation is finalized.

---

## 6.2 `messages.py`

Defines the supported message structures and message types.

---

## 6.3 `serializer.py`

Converts internal protocol representations into a transmissible representation and reconstructs received messages.

---

## 6.4 `validator.py`

Validates incoming and outgoing messages against the defined protocol rules.

This keeps message validation separate from the C2 business logic.

---

# 7. Transport Architecture

Location:

```text
transport/
├── interface.py
└── tcp_tls.py
```

The transport layer is responsible for network communication.

## 7.1 Transport Interface

`interface.py` defines the abstraction used by the application for communication.

The higher application layers should not depend directly on sockets or a specific transport implementation.

## 7.2 TCP/TLS

`tcp_tls.py` provides the mandatory MVP transport implementation.

The current extension model is:

```text
Transport Interface
       │
       ├── TCP/TLS     ← MVP
       ├── HTTP        ← possible extension
       └── DNS         ← possible extension
```

These additional transports are not part of the mandatory implementation.

---

# 8. Storage Architecture

Storage is divided into structured persistent data and physical file storage.

```text
storage/
├── database/
└── files/
```

This follows the principle:

> **Database = structured metadata**

> **File storage = actual file contents**

---

## 8.1 Database Storage

Location:

```text
storage/database/
├── interface.py
├── sqlite.py
└── models.py
```

The database stores structured application information such as:

```text
agents
sessions
tasks
results
file transfers
events
```

### `interface.py`

Defines the storage abstraction used by the application.

### `sqlite.py`

Provides the SQLite implementation.

### `models.py`

Defines the persistence-layer data models.

The C2 core should interact with the storage abstraction rather than directly embedding database queries throughout application logic.

---

## 8.2 File Storage

Location:

```text
storage/files/
├── interface.py
└── filesystem.py
```

This layer handles the persistence of actual file data.

### `interface.py`

Defines the file-storage abstraction.

### `filesystem.py`

Provides the filesystem implementation.

The File Manager uses this abstraction rather than being responsible for the physical storage implementation itself.

---

# 9. Server File Organization

Actual file data is stored separately from the storage implementation:

```text
data/
└── files/
    ├── uploads/
    ├── downloads/
    └── temporary/
```

These directories represent the server-side file workspace.

```text
uploads/
    Files received by the server.

downloads/
    Files prepared for or retrieved for transfer to an agent.

temporary/
    Temporary workspace used while processing transfers.
```

The conceptual relationship is:

```text
File Manager
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

File transfers should be handled incrementally so that large files do not need to be loaded entirely into memory.

---

# 10. Agent Architecture

The agent follows the same principle of separation of concerns while adding components specific to endpoint execution.

```text
agent/
│
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

## 10.1 Core

The agent core contains the central agent logic, identity, and internal state.

Conceptually, it can maintain information such as:

```text
agent_id
hostname
OS
architecture
configuration
state
```

---

## 10.2 Beacon

The Beacon component manages **when** the agent communicates.

It handles concepts such as:

```text
interval
jitter
retry
```

The beacon remains separate from the transport implementation.

```text
Beacon
  │
  │ determines when communication occurs
  ▼
Transport
  │
  │ determines how communication occurs
  ▼
Network
```

---

## 10.3 Protocol

The agent implements the same logical protocol as the C2 server.

Its role is to interpret and generate protocol messages according to the shared communication contract.

---

## 10.4 Transport

The agent-side transport manages network communication with the C2 server.

The implementation remains independent from the logical protocol.

---

## 10.5 Executor

The Executor receives tasks and dispatches them to the appropriate command implementation.

The conceptual flow is:

```text
TASK
  ↓
Executor
  ↓
Command Handler
  ↓
Execution
  ↓
Result
```

This separates task dispatching from the actual implementation of individual commands.

---

## 10.6 Commands

The command layer contains the operations that the agent can perform.

The current architecture accounts for:

```text
SHELL
SYSINFO
FILES
PERSISTENCE
SELF_DESTRUCT
```

The logical operation can remain consistent while the underlying implementation differs by operating system.

---

## 10.7 Platform

The platform layer isolates operating-system-specific functionality.

The intended structure is:

```text
Common Agent Logic
        │
        ▼
Platform Abstraction
      ┌─┴─┐
      ▼   ▼
    Linux Windows
```

Linux is the primary target. Windows is considered a bonus extension.

This separation reduces platform-specific logic leaking into the rest of the agent.

---

# 11. Agent-Side File Architecture

The agent maintains its own controlled file-storage workspace.

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

The separation is:

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

The agent therefore has a dedicated local workspace for files involved in transfers rather than directly using arbitrary locations as its transfer storage.

---

# 12. Communication Architecture

Communication is divided into logical layers:

```text
Application Logic
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
Application Logic
```

On the C2 server:

```text
Core
  ↓
Protocol
  ↓
Transport
```

On the agent:

```text
Core / Beacon / Executor
          ↓
       Protocol
          ↓
       Transport
```

This separation prevents the application logic from becoming directly coupled to the network implementation.

---

# 13. Main System Flows

## 13.1 Agent Registration and Session Establishment

At a high level:

```text
Agent
  │
  │ connection / registration
  ▼
C2 Transport
  │
  ▼
Protocol
  │
  ▼
Validation
  │
  ▼
Agent Manager / Session Manager
  │
  ▼
Persistent State
```

The exact registration exchange will be defined by the protocol specification.

---

## 13.2 Task Execution

The general flow is:

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

The result follows the reverse direction:

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
Result Manager
    │
    ▼
Interface
    │
    ▼
Operator
```

---

## 13.3 File Transfer

File transfers use the protocol and transport layers while keeping file-management and storage responsibilities separate.

A conceptual transfer is:

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

The receiving side can process chunks incrementally:

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

This allows large files to be transferred without requiring the complete file to remain in memory.

---

# 14. File Transfer Architecture

## 14.1 C2 to Agent

Conceptually:

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

## 14.2 Agent to C2

Conceptually:

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

The exact direction associated with `uploads/` and `downloads/` is defined by the transfer operation rather than by the transport layer itself.

---

# 15. File Confidentiality and Integrity

The architecture distinguishes **encryption in transit** from **encryption at rest**.

## 15.1 Encryption in Transit

TCP/TLS is the mandatory communication mechanism for the MVP.

File transfers use the same protected transport.

Conceptually:

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

## 15.2 Encryption at Rest

Application-level encryption of individual files is not part of the mandatory MVP.

It may be considered later as a defense-in-depth feature, but it introduces additional key-management and testing requirements.

## 15.3 File Integrity

Transferred files are intended to be verified after reconstruction using a cryptographic hash.

Conceptually:

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

A matching hash indicates that the reconstructed file corresponds to the expected transferred content.

---

# 16. Component Boundaries

The primary server-side dependency direction is:

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

Persistence is abstracted:

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

The agent follows a similar communication boundary:

```text
Agent Core / Beacon / Executor
              ↓
           Protocol
              ↓
           Transport
```

while execution remains separated:

```text
Agent
 ├── Executor
 │     ↓
 │   Commands
 │
 └── Platform
```

These boundaries are intended to reduce coupling and keep individual components easier to understand, test, and replace.

---

# 17. Security Boundaries

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
Command / Execution Boundary
        │
        ▼
Local File Handling
```

Important principles include:

- messages must be validated before being processed by application logic;
- transport protection does not replace protocol validation;
- data received from an agent should not automatically be considered trusted;
- commands should pass through the agent's command and execution layers;
- file transfers should remain within the defined file-management and storage boundaries.

Detailed security controls and mitigations are documented in [`SECURITY.md`](SECURITY.md).

---

# 18. Extensibility

The architecture deliberately provides several extension points.

## 18.1 Operator Interfaces

```text
Interface
 ├── CLI
 ├── TUI
 └── Web
```

Additional interfaces can reuse the same C2 core.

## 18.2 Transport

```text
Transport Interface
 ├── TCP/TLS
 ├── HTTP       ← extension
 └── DNS        ← extension
```

Additional transports should not require redesigning the task and agent-management logic.

## 18.3 Database

```text
Database Interface
        │
        └── SQLite
```

A different database backend could be introduced without changing the core business logic throughout the application.

## 18.4 File Storage

```text
File Storage Interface
        │
        └── Filesystem
```

The storage implementation can therefore evolve independently from file-transfer logic.

## 18.5 Agent Platform

```text
Platform Interface
       ├── Linux
       └── Windows ← extension
```

The command layer can also evolve while keeping the executor independent from individual command implementations.

---

# 19. Repository Mapping

The architecture maps to the implementation as follows.

## C2 Server

| Architectural Component | Implementation |
|---|---|
| Entry point | `c2_server/main.py` |
| Operator interface | `c2_server/interface/` |
| C2 core | `c2_server/core/` |
| Protocol | `c2_server/protocol/` |
| Transport | `c2_server/transport/` |
| Database storage | `c2_server/storage/database/` |
| File storage | `c2_server/storage/files/` |
| File data | `c2_server/data/files/` |
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

# 20. Current Architectural Status

This document represents the current architectural baseline of the project.

The following areas are established at the architectural level:

- C2 server / agent separation;
- multi-agent server model;
- modular separation of interface, core, protocol, transport, and storage;
- asynchronous task/result model;
- agent/session distinction;
- protocol/transport separation;
- beacon/transport separation;
- controlled file storage on both sides;
- file-management / file-storage separation;
- TLS for protected communication;
- file integrity verification;
- Linux as the primary agent platform;
- extensibility for additional interfaces, transports, storage backends, and Windows support.

The following areas still require detailed design before or during implementation:

- exact C2/agent interfaces;
- exact protocol message schema;
- exact session lifecycle;
- exact database schema;
- detailed asynchronous implementation;
- exact command contracts;
- detailed error-handling behaviour.

Major changes to component responsibilities, dependencies, or system interactions should be recorded in [`DECISIONS.md`](DECISIONS.md) and reflected in this document.
