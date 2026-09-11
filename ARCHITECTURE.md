# Architecture

## 1. Purpose

This document describes the architecture of the C2-AUTOMATED project.

It defines the main system components, their responsibilities, their interactions, and the separation between the C2 server and the agent.

The architecture is designed around a modular structure so that components such as the operator interface, transport layer, protocol implementation, and storage backends can evolve independently.

---

## 2. Global Architecture

The system is composed of three main elements:

- **Operator Interface** — allows the operator to interact with the C2 system.
- **C2 Server** — manages agents, sessions, tasks, results, communication, and server-side storage.
- **Agent** — runs on the target laboratory system and communicates asynchronously with the C2 server.

High-level structure:

```text
                        ┌───────────────────────┐
                        │      Operator         │
                        │   CLI / TUI / Web     │
                        └───────────┬───────────┘
                                    │
                                    ▼
                        ┌───────────────────────┐
                        │      C2 Server        │
                        │                       │
                        │ Interface             │
                        │ Core                  │
                        │ Protocol              │
                        │ Transport             │
                        │ Storage               │
                        │ File Management       │
                        └───────────┬───────────┘
                                    │
                         Network communication
                                    │
                  ┌─────────────────┼─────────────────┐
                  │                 │                 │
                  ▼                 ▼                 ▼
           ┌────────────┐    ┌────────────┐    ┌────────────┐
           │   Agent A  │    │   Agent B  │    │   Agent C  │
           │            │    │            │    │            │
           │ Core       │    │ Core       │    │ Core       │
           │ Beacon     │    │ Beacon     │    │ Beacon     │
           │ Protocol   │    │ Protocol   │    │ Protocol   │
           │ Transport  │    │ Transport  │    │ Transport  │
           │ Executor   │    │ Executor   │    │ Executor   │
           │ Commands   │    │ Commands   │    │ Commands   │
           │ Platform   │    │ Platform   │    │ Platform   │
           └────────────┘    └────────────┘    └────────────┘
```

The server is responsible for coordinating multiple agents simultaneously. Each agent maintains its own local execution and file-handling components.

---

## 3. C2 Server Architecture

The C2 server is divided into separate layers and components.

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

### 3.1 `main.py`

`main.py` is the entry point of the C2 server.

Its role is to initialize the application and assemble the required components.

It should not contain the main C2 business logic.

---

### 3.2 Interface Layer

Location:

```text
interface/
├── cli/
├── tui/
└── web/
```

The interface layer provides operator-facing interfaces.

The different interfaces should rely on the same underlying C2 core rather than implementing their own C2 logic.

This allows the CLI, TUI, and future web interface to remain presentation layers over the same backend.

---

### 3.3 Core Layer

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

The core layer contains the main application logic of the C2 server.

#### `c2.py`

Acts as the central orchestration component of the C2 server.

It coordinates the major server-side components without directly implementing every responsibility itself.

#### `agent_manager.py`

Responsible for managing known agents from the server's perspective.

It provides the higher-level management of agents independently from the low-level network transport.

#### `session_manager.py`

Responsible for maintaining the state of active or known communication sessions.

A session represents the server-side state associated with an agent connection.

#### `task_manager.py`

Responsible for creating, tracking, and managing tasks destined for agents.

It separates task management from the transport mechanism used to deliver those tasks.

#### `result_manager.py`

Responsible for receiving, processing, and managing results returned by agents.

Persistence of results is handled through the storage layer rather than being directly tied to the result manager.

#### `file_manager.py`

Responsible for the logical management of file transfers.

It coordinates file-related operations while the actual persistence of files is delegated to the file storage layer.

---

## 4. Protocol Layer

Location:

```text
protocol/
├── messages.py
├── serializer.py
└── validator.py
```

The protocol layer defines the logical format of messages exchanged between the C2 server and agents.

### `messages.py`

Defines the supported message structures and message types.

### `serializer.py`

Responsible for converting protocol messages between their internal representation and the representation used for transmission.

### `validator.py`

Responsible for validating received or generated messages against the protocol rules.

The protocol layer is independent from the underlying network transport.

---

## 5. Transport Layer

Location:

```text
transport/
├── interface.py
└── tcp_tls.py
```

The transport layer handles network communication between the C2 server and agents.

### `interface.py`

Defines the transport abstraction.

The rest of the application should depend on this interface rather than directly depending on a specific network implementation.

### `tcp_tls.py`

Provides the TCP/TLS transport implementation.

This separation allows the transport implementation to be replaced or extended without requiring changes throughout the C2 core.

---

## 6. Storage Architecture

The server separates persistent data storage into two categories:

```text
storage/
├── database/
└── files/
```

### 6.1 Database Storage

Location:

```text
storage/database/
├── interface.py
├── sqlite.py
└── models.py
```

The database layer is responsible for structured persistent data.

Examples include information associated with:

- agents
- sessions
- tasks
- results
- other metadata required by the application

#### `interface.py`

Defines the abstraction used by the application to access persistent structured data.

#### `sqlite.py`

Provides the SQLite implementation of the database interface.

#### `models.py`

Defines the data models used by the persistence layer.

---

### 6.2 File Storage

Location:

```text
storage/files/
├── interface.py
└── filesystem.py
```

The file storage layer is responsible for physically storing transferred or temporary files.

#### `interface.py`

Defines the abstraction for file persistence.

#### `filesystem.py`

Provides the filesystem-based implementation.

The storage abstraction keeps file persistence separate from the business logic responsible for managing transfers.

---

## 7. Server-Side File Organization

Location:

```text
data/
└── files/
    ├── uploads/
    ├── downloads/
    └── temporary/
```

This directory contains the server's file data.

The directories have the following roles:

```text
uploads/
    Files received by the C2 server.

downloads/
    Files prepared for or retrieved for delivery to agents.

temporary/
    Temporary workspace used during file-processing operations.
```

The distinction between **file management** and **file storage** is intentional:

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

The `file_manager.py` component handles the logical file-transfer operations, while `storage/files/filesystem.py` handles physical persistence.

---

## 8. Supporting Components

### 8.1 Logging

Location:

```text
logging/
```

The logging component provides centralized application logging.

Logging should remain separate from the C2 business logic so that operational events, errors, and debugging information can be recorded consistently.

### 8.2 Configuration

Location:

```text
config/
```

The configuration component centralizes configurable application parameters.

Configuration should not be scattered throughout individual components.

---

# 9. Agent Architecture

The agent follows the same general principle of separation of responsibilities as the C2 server, while having responsibilities specific to execution on the endpoint.

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

## 10. Agent Components

### 10.1 Core

The `core/` component contains the agent's central application logic and orchestration.

It coordinates the other agent components without directly implementing all of their responsibilities.

---

### 10.2 Beacon

The `beacon/` component manages the agent's periodic communication behaviour with the C2 server.

It is responsible for the agent's communication cycle and the handling of communication opportunities.

The exact beacon mechanism is defined by the communication design and protocol.

---

### 10.3 Protocol

The `protocol/` component contains the agent-side implementation of the communication protocol.

It is responsible for interpreting and generating messages according to the protocol shared with the C2 server.

The server and agent therefore share the same logical protocol while maintaining separate implementations appropriate to each side.

---

### 10.4 Transport

The `transport/` component handles the agent-side network communication.

It provides the agent with the mechanism required to establish and maintain communication with the C2 server.

The transport implementation remains separated from the protocol logic.

---

### 10.5 Executor

The `executor/` component is responsible for executing tasks received by the agent.

It forms the boundary between the C2 task model and the actual execution of operations on the endpoint.

---

### 10.6 Commands

The `commands/` component defines the commands or operations that the agent can execute.

Keeping commands separate from the executor allows the execution mechanism to remain distinct from the catalogue of supported operations.

---

### 10.7 Platform

The `platform/` component contains platform-specific functionality.

This layer allows operating-system-specific behaviour to remain isolated from the platform-independent parts of the agent.

This is particularly important if Windows support is added later.

---

# 11. Agent-Side File Architecture

The agent also separates file management from file persistence.

```text
storage/
└── files/
    ├── interface.py
    └── filesystem.py
```

with local file data stored under:

```text
data/
└── files/
    ├── uploads/
    ├── downloads/
    └── temporary/
```

The conceptual separation is:

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

The agent therefore has its own local file workspace rather than directly manipulating server-side storage.

---

# 12. Communication Architecture

The communication path is divided into distinct responsibilities:

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

This separation prevents application logic from becoming directly coupled to the network implementation.

---

# 13. Main System Flows

## 13.1 Agent Connection

At a high level:

```text
Agent
  │
  │ connection
  ▼
C2 Transport
  │
  ▼
Protocol validation
  │
  ▼
Agent / Session management
  │
  ▼
Persistent state
```

The exact connection and registration sequence is defined by the communication protocol.

---

## 13.2 Task Execution

The general task flow is:

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

The resulting execution output follows the reverse path:

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
Operator Interface
```

---

## 13.3 File Transfer

File transfers follow the same separation between logical file management and physical storage.

Conceptually:

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

A transfer between the C2 server and an agent is therefore handled through:

```text
Application logic
       ↓
File manager
       ↓
Protocol
       ↓
Transport
       ↓
Agent
       ↓
Agent file handling
       ↓
Agent file storage
```

The exact upload/download direction and transfer lifecycle are defined by the protocol design.

---

# 14. Component Boundaries

The architecture follows these main boundaries:

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

Persistence is kept behind storage abstractions:

```text
Core
 ├── Database Interface
 │       ↓
 │    SQLite
 │
 └── File Storage Interface
         ↓
      Filesystem
```

The same principle applies to the agent:

```text
Agent Core
    ↓
Protocol
    ↓
Transport
```

with execution and platform-specific functionality separated from communication:

```text
Agent
 ├── Executor
 │     ↓
 │   Commands
 │
 └── Platform
```

These boundaries are intended to reduce coupling and make individual components easier to test and replace.

---

# 15. Security Boundaries

The architecture separates several security-sensitive boundaries:

- operator interaction
- server-side application logic
- network transport
- protocol validation
- persistent storage
- endpoint execution
- file handling

The transport layer provides the network protection mechanism, while the protocol layer is responsible for validating structured messages.

Input received from an agent should not be considered trusted merely because it has passed through the transport layer.

Similarly, commands received from the C2 should pass through the agent's command and execution layers rather than being executed directly by the communication layer.

Detailed security controls and mitigations are documented separately from the structural architecture as they are defined.

---

# 16. Extensibility

The architecture is designed to allow components to evolve independently where practical.

Examples include:

- adding another operator interface without rewriting the C2 core;
- replacing or extending the transport implementation;
- replacing SQLite with another database backend;
- replacing filesystem storage with another storage mechanism;
- adding another platform implementation for the agent;
- extending the set of supported commands;
- extending the protocol with new message types.

The use of interfaces at transport and storage boundaries is intended to support these changes without requiring extensive modifications to the rest of the system.

---

# 17. Repository Mapping

The architecture maps to the implementation structure as follows.

### C2 Server

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

### Agent

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

# 18. Architecture Status

This document represents the current architectural baseline of the project.

Implementation details may evolve during development, but any change that modifies component responsibilities, dependencies, or major system interactions should be reflected in this document and, when appropriate, recorded in `DECISIONS.md`.
