# C2-AUTOMATED

**Automated Command & Control system — annual project retake**

> ⚠️ **Educational / laboratory project**
>
> This project is developed exclusively for educational purposes and authorized laboratory environments. It is intended to demonstrate C2 architecture, asynchronous agent management, task execution, communication, synchronization, file transfer, persistence, and security mechanisms.
>
> **The system must only be deployed, tested, and demonstrated on systems for which explicit authorization exists.**

---

## Overview

C2-AUTOMATED is a modular Command & Control system composed of:

- a **C2 server**, responsible for managing agents, sessions, tasks, results, communication, synchronization, and storage;
- an **agent**, responsible for communicating with the C2 server, receiving authorized tasks, executing supported operations, and returning results;
- an **operator interface**, initially provided through a CLI, with TUI and Web interfaces considered as future extensions.

The system is designed around a clear separation between:

- application logic;
- communication protocol;
- network transport;
- agent execution;
- storage;
- file transfer;
- logging and event traceability.

The core architectural principle is:

> **The C2 server coordinates agents and tasks; the agent performs authorized tasks and returns execution results.**

The project is designed as a **modular monolith** rather than a distributed microservice architecture. Internal responsibilities are separated through explicit components and interfaces so that individual subsystems can evolve without requiring a complete redesign.

---

## Objectives

The project aims to implement a C2 system capable of:

- managing multiple agents simultaneously;
- maintaining persistent agent and session information;
- communicating asynchronously with agents;
- maintaining explicit communication and liveness states;
- creating and tracking tasks through a defined lifecycle;
- recovering task state after communication interruptions;
- receiving and associating execution results with their corresponding tasks;
- synchronizing agent and C2 state after reconnection;
- transferring files between the C2 server and agents;
- protecting C2-Agent communication through TLS;
- verifying transferred-file integrity;
- maintaining structured persistent data;
- recording significant system events for traceability;
- providing a modular architecture that can be extended without redesigning the whole system.

---

## Main Features

### C2 Server

The server provides the central coordination layer for the system.

Planned responsibilities include:

- multi-agent management;
- session management;
- task management;
- result management;
- file-transfer management;
- protocol routing;
- synchronization;
- operator interaction;
- network transport;
- persistent storage;
- application logging and event recording.

The C2 maintains the persistent historical record of agents, sessions, tasks, results, transfers, and relevant events.

### Agent

The agent is responsible for endpoint-side operations.

Its architecture separates:

- agent core and state;
- beacon and communication scheduling;
- protocol handling;
- network transport;
- task execution;
- command implementations;
- platform-specific functionality;
- local file storage;
- lightweight recovery state.

Linux is the primary target platform. Windows support is considered a bonus extension.

### Communication

The mandatory communication channel is:

```text
C2 Server
    │
    │ TCP/TLS
    ▼
  Agent(s)
```

The agent initiates communication with the C2 server.

The protocol is kept separate from the transport layer so that the logical messages exchanged between the C2 and agents do not depend directly on the underlying network mechanism.

The communication model is asynchronous and supports multiple agents and independent tasks.

### Sessions and Reconnection

Agent identity and network sessions are treated as separate concepts.

An **Agent** represents the logical endpoint identity, while a **Session** represents one concrete connection episode.

A new connection always creates a new Session:

```text
Agent A001
 ├── S041
 ├── S042 = DISCONNECTED
 └── S043 = CONNECTED
```

A previous disconnected Session is never reopened.

After a new connection, the Agent and C2 perform synchronization so that pending tasks, task states, and results can be reconciled.

The high-level flow is:

```text
New connection
      │
      ▼
New Session
      │
      ▼
Session = CONNECTED
      │
      ▼
REGISTER
      │
      ▼
Communication = SYNCHRONIZING
      │
      ▼
State reconciliation
      │
      ▼
SYNC_COMPLETE
      │
      ▼
Communication = CONNECTED
```

Detailed state definitions and transition rules are documented separately.

### File Transfer

File transfers are handled separately from ordinary task results.

The system is designed to support chunked transfers:

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

Transferred files are handled through controlled storage areas rather than being kept entirely in memory.

File metadata and file contents are stored separately.

File integrity is verified after reconstruction using a cryptographic hash.

Transfer state and recovery semantics remain subject to the detailed file-transfer specification.

---

## Architecture

The system is divided into two main application components:

```text
                         ┌──────────────────┐
                         │     OPERATOR     │
                         └────────┬─────────┘
                                  │
                         ┌────────▼─────────┐
                         │   C2 INTERFACE   │
                         │       CLI        │
                         │    TUI / Web*    │
                         └────────┬─────────┘
                                  │
                       ┌──────────▼──────────┐
                       │      C2 SERVER      │
                       │                     │
                       │ Interface           │
                       │ Core                │
                       │ Protocol            │
                       │ Transport           │
                       │ Storage             │
                       │ File Management     │
                       │ Synchronization     │
                       │ Logging / Events    │
                       └──────────┬──────────┘
                                  │
                               TCP/TLS
                                  │
             ┌────────────────────┼────────────────────┐
             ▼                    ▼                    ▼
          Agent A              Agent B              Agent C
```

\* TUI and Web interfaces are future extensions.

The architecture is designed around three main extensibility axes:

| Area | Current / MVP | Possible extension |
|---|---|---|
| Operator interface | CLI | TUI / Web |
| Transport | TCP/TLS | Additional transports |
| Platform | Linux | Windows |

For a detailed description of the architecture and component responsibilities, see [`ARCHITECTURE.md`](ARCHITECTURE.md).

---

## Project Structure

The repository is organized into two main application components:

```text
C2-AUTOMATED/
│
├── README.md
├── ARCHITECTURE.md
├── SECURITY.md
├── DECISIONS.md
├── CONTRIBUTING.md
│
├── c2_server/
│   ├── main.py
│   ├── interface/
│   │   ├── cli/
│   │   ├── tui/
│   │   └── web/
│   ├── core/
│   ├── protocol/
│   ├── transport/
│   ├── storage/
│   ├── data/
│   ├── logging/
│   ├── config/
│   └── tests/
│
├── agent/
│   ├── core/
│   ├── beacon/
│   ├── protocol/
│   ├── transport/
│   ├── executor/
│   ├── commands/
│   ├── platform/
│   ├── storage/
│   ├── data/
│   └── tests/
│
└── docs/
```

The exact internal structure may evolve during implementation as responsibilities and interfaces are refined.

Major architectural changes should be documented in [`DECISIONS.md`](DECISIONS.md).

---

## Task Model

Tasks are handled asynchronously and follow an explicit lifecycle.

The authoritative task states are:

```text
PENDING
   │
   ▼
WAITING_ACK
   │
   ▼
QUEUED
   │
   ▼
RUNNING
   │
   ├──────────────► FAILED
   │
   ├──────────────► TIMEOUT
   │
   └──────────────► COMPLETED
```

Cancellation may apply to an appropriate non-terminal task state:

```text
        ┌──────────────► CANCELLED
        │
Active task state
```

The complete lifecycle is:

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

`UNKNOWN` is **not** a persistent task state. It represents a recovery or reporting condition when the current execution state cannot temporarily be established.

Communication loss does not automatically mean that a task has failed.

A task belongs to an Agent rather than to a specific Session and may therefore span multiple connection sessions.

Results are associated with Tasks and may be received later following a communication interruption.

See [`docs/task-lifecycle.md`](docs/task-lifecycle.md) for the detailed task model.

---

## Supported Operations

The agent architecture currently accounts for the following logical command categories:

- `SHELL`
- `SYSINFO`
- `FILES`
- `PERSISTENCE`
- `SELF_DESTRUCT`

These categories describe the intended command architecture; the exact command contracts and implementation remain subject to the project specifications and security decisions.

Linux is the primary target platform.

Platform-specific implementations are kept separate so that Windows support can be added later without spreading operating-system-specific logic throughout the entire agent.

---

## Protocol

The communication protocol defines the logical messages exchanged between the C2 and agents.

The current protocol includes message categories for:

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
TASK_STATUS
TASK_STATUS_QUERY
RESULT
```

### File transfer

```text
FILE_START
FILE_CHUNK
FILE_END
```

### Error handling

```text
ERROR
```

Protocol handling is separated from the network transport.

See [`docs/protocol.md`](docs/protocol.md) and [`docs/protocol-state-transition.md`](docs/protocol-state-transition.md) for the detailed protocol specification and its relationship with system state transitions.

---

## Storage

Structured application data is persisted separately from file contents.

Conceptually:

```text
Structured application data
          │
          ▼
     Storage Layer
          │
          ▼
        SQLite
```

while transferred files are stored in dedicated filesystem areas:

```text
data/
└── files/
    ├── uploads/
    ├── downloads/
    └── temporary/
```

The database is intended to contain structured information such as:

- agents;
- sessions;
- tasks;
- results;
- file-transfer metadata;
- events.

The filesystem stores the actual transferred file contents.

This separation prevents binary file data from being mixed with structured application state and allows storage implementations to remain replaceable through interfaces.

---

## Security

Security is considered at both the communication and application levels.

### Communication security

C2-Agent communication uses TLS to protect data in transit.

This includes:

- task messages;
- results;
- status and beacon communication;
- synchronization messages;
- file transfers.

TLS provides transport confidentiality and integrity, but does not by itself define the complete Agent authentication or authorization model.

### Agent identity and authentication

An `agent_id` identifies an Agent but does **not** constitute authentication by itself.

The exact Agent authentication mechanism remains an explicit security/design decision.

The registration flow therefore conceptually includes:

```text
New connection
      ↓
Session established
      ↓
REGISTER
      ↓
Identity / authentication validation
      ↓
REGISTER_ACK
      ↓
Synchronization
```

### Protocol validation

Messages received by the system must be validated according to the communication protocol before being processed by application logic.

Validation includes appropriate checks on:

- message type;
- required fields;
- field types;
- identifiers;
- correlation information;
- message size;
- command parameters;
- protocol state.

### File integrity

Transferred files are verified after reconstruction using a cryptographic hash.

### Controlled file storage

Both the C2 server and agent use dedicated file-storage areas for transferred and temporary files.

External paths must not be allowed to escape their designated storage workspaces.

### Data at rest

Application-level encryption of individual files at rest is **not part of the mandatory MVP**.

TLS protects data in transit, while filesystem permissions and controlled storage are used for local protection. Additional at-rest encryption may be considered separately as a defense-in-depth feature.

See [`SECURITY.md`](SECURITY.md), [`docs/threat-model.md`](docs/threat-model.md), and [`docs/countermeasures.md`](docs/countermeasures.md) for the detailed security documentation.

---

## Logging and Traceability

The system distinguishes between:

- **Messages**, which represent protocol communication;
- **Events**, which represent significant system occurrences.

Events may record activities such as:

- Agent registration;
- Session creation and disconnection;
- task lifecycle changes;
- result reception;
- synchronization;
- file-transfer activity;
- protocol errors;
- security-relevant events.

This provides traceability without treating every protocol message as an application event.

---

## Development Status

The project is currently in the **architecture and design phase**.

Current priorities are:

1. finalize the architecture;
2. finalize domain models and state machines;
3. define interfaces and contracts between components;
4. define the C2-Agent communication protocol;
5. implement the mandatory Linux MVP;
6. implement persistence and asynchronous task handling;
7. implement file transfer;
8. add testing and security validation;
9. stabilize the mandatory functionality;
10. consider bonus extensions such as Windows, TUI, Web, or additional transports.

The architecture should be treated as the current design baseline.

Significant changes to component responsibilities, state models, protocol behavior, or major interactions should be documented in [`DECISIONS.md`](DECISIONS.md).

---

## Documentation

| Document | Purpose |
|---|---|
| [`ARCHITECTURE.md`](ARCHITECTURE.md) | Global system and component architecture |
| [`SECURITY.md`](SECURITY.md) | Security principles, security boundaries, and security baseline |
| [`DECISIONS.md`](DECISIONS.md) | Architectural and technical decisions |
| [`CONTRIBUTING.md`](CONTRIBUTING.md) | Development workflow and repository conventions |
| [`docs/data-model.md`](docs/data-model.md) | Domain entities, relationships, and persistence model |
| [`docs/state-machines.md`](docs/state-machines.md) | Authoritative state machines |
| [`docs/protocol.md`](docs/protocol.md) | C2-Agent protocol |
| [`docs/protocol-state-transition.md`](docs/protocol-state-transition.md) | Protocol events and state transitions |
| [`docs/reconnection-and-synchronization.md`](docs/reconnection-and-synchronization.md) | Reconnection and state reconciliation |
| [`docs/task-lifecycle.md`](docs/task-lifecycle.md) | Task lifecycle and recovery |
| [`docs/network-architecture.md`](docs/network-architecture.md) | Network topology and communication architecture |
| [`docs/file-transfer.md`](docs/file-transfer.md) | File-transfer architecture and behavior |
| [`docs/testing-strategy.md`](docs/testing-strategy.md) | Testing strategy and validation |
| [`docs/threat-model.md`](docs/threat-model.md) | Threat model and security risks |
| [`docs/countermeasures.md`](docs/countermeasures.md) | Security controls and mitigations |
| [`docs/requirements-mapping.md`](docs/requirements-mapping.md) | Requirements traceability |
| [`docs/`](docs/) | Additional subsystem documentation |

See [`docs/README.md`](docs/README.md) for the complete documentation index and a guide to where each technical subject is documented.

---

## Branching Strategy

Development follows a layered branch model:

```text
feature/*
    │
    ▼
   dev
    │
    ▼
  main
```

- `feature/*` branches are used for isolated development work;
- `dev` is the integration branch;
- `main` is kept for stable and validated states.

Direct development on `main` is avoided.

See [`CONTRIBUTING.md`](CONTRIBUTING.md) for the repository workflow.

---

## Educational and Authorized-Use Scope

This project is intended to be developed, tested, and demonstrated **exclusively within authorized laboratory environments**.

The system must only be deployed or executed on:

- machines owned or controlled by the project team;
- dedicated laboratory systems;
- explicitly authorized test environments;
- systems for which appropriate permission has been obtained.

Testing against third-party systems, networks, devices, or accounts without explicit authorization is outside the scope of this project.

The project's security and architectural documentation therefore describes the system in the context of a controlled educational environment.

---

## License

This project is developed as an academic project.

License terms will be defined if the project is later distributed outside the academic context.
