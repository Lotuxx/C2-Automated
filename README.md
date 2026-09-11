# C2-AUTOMATED

**Automated Command & Control system — annual project retake**

> ⚠️ **Educational / laboratory project**
>
> This project is developed for educational purposes in an isolated and controlled laboratory environment. It is intended to demonstrate C2 architecture, asynchronous agent management, task execution, communication, and security mechanisms.

---

## Overview

C2-AUTOMATED is a modular Command & Control system composed of:

- a **C2 server**, responsible for managing agents, sessions, tasks, results, communication, and storage;
- an **agent**, responsible for communicating with the C2 server, receiving tasks, executing supported operations, and returning results;
- an **operator interface**, initially provided through a CLI, with TUI and Web interfaces considered as future extensions.

The system is designed around a clear separation between the **application logic**, **communication protocol**, **network transport**, **execution**, and **storage** layers.

The core architectural principle is:

> **The C2 server manages agents and tasks; the agent performs the tasks and returns the results.**

---

## Objectives

The project aims to implement a C2 system capable of:

- managing multiple agents simultaneously;
- maintaining agent and session state;
- communicating asynchronously with agents;
- creating and tracking tasks through a defined lifecycle;
- receiving and associating execution results with their corresponding tasks;
- transferring files between the C2 server and agents;
- protecting C2-Agent communication through TLS;
- verifying transferred-file integrity;
- maintaining structured persistent data;
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
- operator interaction;
- protocol handling;
- network transport;
- persistent storage;
- application logging.

### Agent

The agent is responsible for endpoint-side operations.

Its architecture separates:

- agent core and state;
- beacon/communication scheduling;
- protocol handling;
- network transport;
- task execution;
- command implementations;
- platform-specific functionality;
- local file storage.

### Communication

The mandatory communication channel is:

```text
C2 Server
    │
    │ TCP/TLS
    ▼
  Agent(s)
```

The protocol is kept separate from the transport layer so that the logical messages exchanged between the C2 and agents do not depend directly on the underlying network mechanism.

### File Transfer

File transfers are handled separately from ordinary task results.

The system is designed to support:

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

File integrity is intended to be verified using a cryptographic hash after reconstruction.

---

## Architecture

The system is divided into two main programs:

```text
                         ┌──────────────────┐
                         │     OPERATOR     │
                         └────────┬─────────┘
                                  │
                       ┌──────────┼──────────┐
                       ▼          ▼          ▼
                      CLI        TUI        Web
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
              └───────────┬───────────┘
                          │
                       TCP/TLS
                          │
             ┌────────────┼────────────┐
             ▼            ▼            ▼
          Agent A       Agent B      Agent C
```

The architecture is designed around three main extensibility axes:

| Area | Current implementation | Possible extension |
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

---

## Security

Security is considered at both the communication and application levels.

### Communication security

C2-Agent communication uses TLS to protect data in transit.

This includes:

- task messages;
- results;
- status/beacon communication;
- file transfers.

### File integrity

Transferred files are intended to be verified after reconstruction using a cryptographic hash.

### Input validation

Messages received by the system must be validated according to the communication protocol before being processed by application logic.

### Controlled file storage

Both the C2 server and agent use dedicated file-storage areas for transferred and temporary files.

Application-level encryption of individual files at rest is **not part of the mandatory MVP**. TLS is used for confidentiality during transmission, while additional at-rest encryption may be considered separately as a future defense-in-depth feature.

See [`SECURITY.md`](SECURITY.md) for the detailed security model.

---

## Task Model

Tasks are handled asynchronously and follow a defined lifecycle.

The current conceptual model is:

```text
PENDING
   │
   ▼
 SENT
   │
   ▼
RUNNING
   │
   ├──────────────► FAILED
   │
   ▼
COMPLETED
```

A task is associated with an agent and can later be associated with its execution result.

This model allows the server to manage multiple agents and independent tasks without relying on a single blocking request/response exchange.

---

## Supported Operations

The agent architecture currently accounts for the following logical command categories:

- `SHELL`
- `SYSINFO`
- `FILES`
- `PERSISTENCE`
- `SELF_DESTRUCT`

Linux is the primary target platform. Platform-specific implementations are kept separate so that Windows support can be added later without spreading operating-system-specific logic throughout the entire agent.

The exact command set and implementation details may evolve during development.

---

## Storage

Structured application data is intended to be persisted separately from file contents.

Conceptually:

```text
Structured data
      │
      ▼
Database storage
      │
      ▼
SQLite
```

while actual transferred files are stored in dedicated file-storage areas.

This separation allows the application to keep transfer metadata, task state, agent information, and results distinct from the actual file bytes.

---

## Development Status

The project is currently in the **architecture and design phase**.

Current priorities are:

1. finalize the architecture;
2. define the interfaces and contracts between components;
3. define the C2-Agent communication protocol;
4. define the main domain objects;
5. implement the MVP;
6. add testing and security validation;
7. consider bonus extensions once the mandatory functionality is stable.

The architecture should be treated as the current design baseline. Significant changes to component responsibilities or major interactions should be documented in [`DECISIONS.md`](DECISIONS.md).

---

## Documentation

| Document | Purpose |
|---|---|
| [`ARCHITECTURE.md`](ARCHITECTURE.md) | Global system and component architecture |
| [`SECURITY.md`](SECURITY.md) | Security properties, controls, and assumptions |
| [`DECISIONS.md`](DECISIONS.md) | Important architectural and technical decisions |
| [`CONTRIBUTING.md`](CONTRIBUTING.md) | Development workflow and repository conventions |
| [`docs/`](docs/) | Detailed documentation for specific subsystems |

Detailed documents will be added as individual subsystems become sufficiently defined to justify their own specifications.

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

## Educational Scope

This project is intended to be developed and demonstrated exclusively within an authorized laboratory environment.

The implementation and testing should remain limited to systems for which explicit authorization exists.

---

## License

This project is developed as an academic project.

License terms will be defined if the project is later distributed outside the academic context.
