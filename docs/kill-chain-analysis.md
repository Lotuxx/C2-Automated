# Kill Chain Analysis

## 1. Purpose

This document analyses the capabilities of **C2-AUTOMATED** against the **Cyber Kill Chain** model.

The objective is not to claim that the project implements a complete attack chain. Instead, the analysis identifies:

- which project capabilities correspond to specific phases;
- which phases are only partially related to the project;
- which capabilities are outside the project scope;
- the security implications of the implemented capabilities.

C2-AUTOMATED is primarily a **Command and Control** system with selected endpoint capabilities associated with **Actions on Objectives**.

---

## 2. Authorized-Use Boundary

C2-AUTOMATED is an academic project intended for use in an **authorized laboratory environment**.

All development, deployment, demonstration, and testing must be performed only on systems and environments for which explicit authorization exists.

Examples include:

- systems owned or administered by the project user;
- dedicated laboratory machines;
- isolated virtual machines;
- private laboratory networks;
- institution-provided exercise environments.

The project is not intended for:

- third-party systems without explicit authorization;
- production systems unless they are explicitly designated and authorized for the exercise;
- public internet targets that are not part of the laboratory environment;
- systems belonging to other users or organizations without authorization.

---

## 3. Cyber Kill Chain Overview

The **Cyber Kill Chain** is commonly represented as a sequence of attack phases:

```text
Reconnaissance
      ↓
Weaponization
      ↓
Delivery
      ↓
Exploitation
      ↓
Installation
      ↓
Command & Control
      ↓
Actions on Objectives
```

The project does not attempt to implement every phase.

Its main purpose is to provide:

```text
Command & Control
        +
Selected endpoint capabilities
```

The relationship with the Kill Chain must therefore be understood as a **capability mapping**, not as a claim that the project is a complete intrusion framework.

---

## 4. Scope and Identifier Conventions

### 4.1 Scope labels

The capability classification in this document uses three scope labels:

| Scope | Meaning |
|---|---|
| **Required** | Part of the current MVP and required project delivery scope. |
| **Bonus** | Optional functionality beyond the required MVP. |
| **Future** | Architectural extension considered possible but not part of the current delivery target. |

These labels describe **project scope**, not implementation maturity.

For example, a capability marked `Required` may still be under development.

### 4.2 Definition state

Definition state is tracked separately from project scope:

| State | Meaning |
|---|---|
| **Defined** | The intended behaviour and boundaries are sufficiently established for implementation. |
| **Open** | The capability is in scope, but its exact behaviour, limits, or implementation rules still require a design decision. |

Implementation maturity is tracked separately in `docs/requirements-mapping.md`.

For example:

```text
CAP-022 PERSISTENCE
Scope: Required
Definition: Open
Implementation status: tracked separately
```

This distinction prevents an unresolved design decision from being confused with an optional capability.

### 4.3 Acronyms and identifier conventions

Several identifiers are used throughout the project documentation to maintain traceability.

| Identifier | Meaning | Purpose |
|---|---|---|
| **CAP** | **Capability** | Identifies a functional capability of C2-AUTOMATED. |
| **TM** | **Threat Model entry** | Identifies an individual threat defined in `docs/threat-model.md`. |
| **SR** | **Security Requirement** | Identifies a security requirement derived from the threat model. |
| **ADR** | **Architecture Decision Record** | Identifies an accepted architectural decision documented in `DECISIONS.md`. |
| **PRO** | **Project/Open Decision** | Identifies an unresolved project decision requiring a later design decision. |

Examples:

```text
CAP-022 → Capability 22: PERSISTENCE
TM-023  → Threat Model entry 23
SR-001  → Security Requirement 1
ADR-005 → Architecture Decision Record 5
PRO-006 → Project/Open Decision 6
```

These identifiers are **documentation references**. They are not:

- protocol message identifiers;
- database primary keys;
- task IDs;
- agent IDs;
- session IDs;
- implementation-specific identifiers.

They exist to make relationships between project documents explicit.

For example:

```text
CAP-022
   ↓
TM-010 / TM-011
   ↓
Security requirements
   ↓
Implementation
   ↓
Tests
```

---

## 5. Capability Catalogue

### 5.1 Core capabilities

| ID | Capability | Scope | Definition |
|---|---|---|---|
| `CAP-001` | Agent management | Required | Defined |
| `CAP-002` | Session management | Required | Defined |
| `CAP-003` | Multi-agent management | Required | Defined |
| `CAP-004` | Beaconing | Required | Defined |
| `CAP-005` | TCP/TLS communication | Required | Defined |
| `CAP-006` | Application protocol | Required | Defined |
| `CAP-007` | Asynchronous task queuing | Required | Defined |
| `CAP-008` | Task execution | Required | Defined |
| `CAP-009` | Result management | Required | Defined |
| `CAP-010` | File transfer | Required | Defined |
| `CAP-011` | Persistent metadata | Required | Defined |
| `CAP-012` | Controlled file storage | Required | Defined |
| `CAP-013` | Operator interface | Required | Defined |
| `CAP-014` | Linux support | Required | Defined |
| `CAP-015` | Windows support | Bonus | Defined |
| `CAP-016` | TUI interface | Future | Defined |
| `CAP-017` | Web interface | Future | Defined |
| `CAP-018` | Additional transports | Future | Defined |

### 5.2 Endpoint task capabilities

| ID | Capability | Scope | Definition |
|---|---|---|---|
| `CAP-019` | `SHELL` | Required | Defined |
| `CAP-020` | `SYSINFO` | Required | Defined |
| `CAP-021` | `FILES` | Required | Defined |
| `CAP-022` | `PERSISTENCE` | Required | Open |
| `CAP-023` | `SELF_DESTRUCT` | Required | Open |

### 5.3 Important classification notes

`CAP-022 PERSISTENCE` and `CAP-023 SELF_DESTRUCT` are both **required project capabilities**.

However, their exact behaviour is not yet completely defined.

This means:

```text
Required ≠ Fully specified
```

In particular:

- `PERSISTENCE` requires a final decision about the exact supported persistence mechanism and its boundaries.
- `SELF_DESTRUCT` requires a final decision about what is removed or terminated. This is tracked in `PRO-006`.

Neither capability should therefore be classified as `Bonus` merely because its detailed implementation is still open.

---

## 6. Kill Chain Mapping

### 6.1 Summary matrix

| Kill Chain Phase | Relationship with C2-AUTOMATED | Relevant capabilities |
|---|---|---|
| Reconnaissance | No dedicated capability | None |
| Weaponization | Out of scope | None |
| Delivery | Partial technical relationship | `CAP-005`, `CAP-006`, `CAP-010`, `CAP-012` |
| Exploitation | No dedicated capability | None |
| Installation | Partial relationship | `CAP-022` |
| Command & Control | Core project functionality | `CAP-001`–`CAP-010` |
| Actions on Objectives | Selected endpoint capabilities | `CAP-019`–`CAP-023` |

The project should not be described as implementing a complete Cyber Kill Chain.

---

## 7. Reconnaissance

### Relationship

The project does not provide a dedicated reconnaissance subsystem.

The `SYSINFO` capability should not be considered reconnaissance in the Kill Chain sense.

`SYSINFO` is an **endpoint information-collection operation** executed after an agent is already present and communicating with the C2.

### Relevant capability

None directly.

`CAP-020 SYSINFO` is related to endpoint information gathering but is not classified as a reconnaissance capability.

### Conclusion

```text
Reconnaissance
     │
     └── No dedicated C2-AUTOMATED capability
```

---

## 8. Weaponization

### Relationship

Weaponization is outside the project scope.

The project does not define a subsystem for constructing malware, exploit packages, or attack payloads as part of the Kill Chain.

### Conclusion

```text
Weaponization
     │
     └── Out of project scope
```

---

## 9. Delivery

### Relationship

C2-AUTOMATED has technical functionality that supports the movement of tasks and files between the C2 server and an agent.

Relevant capabilities include:

- `CAP-005` TCP/TLS communication;
- `CAP-006` application protocol;
- `CAP-010` file transfer;
- `CAP-012` controlled file storage.

However, this does **not** make the project a complete delivery subsystem.

The project assumes an already deployed or otherwise authorized agent participating in the laboratory environment.

Therefore:

> **File transfer is not equivalent to a complete Kill Chain Delivery capability.**

### Conclusion

```text
Delivery
   │
   ├── CAP-005
   ├── CAP-006
   ├── CAP-010
   └── CAP-012
```

The relationship is therefore **partial**.

---

## 10. Exploitation

### Relationship

The C2-AUTOMATED project does not implement an exploitation subsystem.

The agent is not designed to gain access by exploiting a vulnerability as part of its core architecture.

The project can execute commands on an endpoint where an agent is already running, but:

> **SHELL execution is not equivalent to Exploitation.**

Likewise, deployment of the agent is not itself evidence that an exploitation stage exists.

### Conclusion

```text
Exploitation
     │
     └── No dedicated capability
```

---

## 11. Installation

### Relationship

Installation has a limited relationship with the project through the `PERSISTENCE` capability.

### Relevant capability

`CAP-022 PERSISTENCE`

This capability is intended to represent controlled persistence functionality on the endpoint.

Its exact behaviour remains open and is therefore tracked separately from the broader architectural design.

The capability should not be expanded conceptually into unrestricted persistence mechanisms.

### Important distinction

```text
Agent deployment
      ≠
Persistence
```

Deploying or launching the agent does not automatically mean that the project implements a complete Installation phase.

### Conclusion

```text
Installation
     │
     └── CAP-022 PERSISTENCE
```

The relationship is **partial**.

---

## 12. Command & Control

This is the **central Kill Chain phase represented by C2-AUTOMATED**.

The architecture is specifically designed around managing agents, communication sessions, tasks, results, and file transfers.

Relevant capabilities are:

```text
CAP-001  Agent management
CAP-002  Session management
CAP-003  Multi-agent management
CAP-004  Beaconing
CAP-005  TCP/TLS
CAP-006  Application protocol
CAP-007  Asynchronous task queuing
CAP-008  Task execution
CAP-009  Result management
CAP-010  File transfer
```

The resulting model is:

```text
Operator
   │
   ▼
C2 Server
   │
   ├── Agents
   ├── Sessions
   ├── Tasks
   ├── Results
   └── Files
   │
   ▼
Agent
```

### 12.1 Agent management

`CAP-001` provides the logical management of agents.

The server maintains information such as:

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

### 12.2 Session management

`CAP-002` separates the persistent identity of an agent from an individual communication session.

```text
Agent A001
    │
    ├── Session S41
    ├── Session S42
    └── Session S43
```

The agent identity persists while communication sessions may change.

### 12.3 Multi-agent management

`CAP-003` addresses the multi-agent requirement.

The server must be able to manage multiple agents without treating the whole C2 as a single-agent connection.

### 12.4 Beaconing

`CAP-004` determines **when** the agent communicates.

This remains conceptually separate from transport:

```text
Beacon  = when to communicate
Transport = how to communicate
```

### 12.5 TCP/TLS

`CAP-005` defines the mandatory MVP communication mechanism.

TLS provides protection for communication in transit.

### 12.6 Application protocol

`CAP-006` defines what the C2 server and agent exchange.

Representative message types include:

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

### 12.7 Asynchronous task queuing

`CAP-007` provides the asynchronous model.

A task can remain pending while an agent is unavailable and be delivered during a subsequent communication opportunity.

Conceptually:

```text
Task created
     ↓
PENDING
     ↓
Agent unavailable
     ↓
Still pending
     ↓
Agent communicates
     ↓
SENT
```

### 12.8 Task execution

`CAP-008` represents the actual execution model on the agent.

The task is separated from the command implementation:

```text
Task
 ↓
Executor
 ↓
Command
 ↓
Execution
 ↓
Result
```

### 12.9 Result management

`CAP-009` represents the server-side handling of results returned by agents.

### 12.10 File transfer

`CAP-010` extends the C2 communication model to file transfers.

File transfer uses a dedicated transfer lifecycle rather than treating an entire file as an ordinary task result.

### Conclusion

```text
Command & Control
        │
        ├── CAP-001
        ├── CAP-002
        ├── CAP-003
        ├── CAP-004
        ├── CAP-005
        ├── CAP-006
        ├── CAP-007
        ├── CAP-008
        ├── CAP-009
        └── CAP-010
```

This is the **primary Kill Chain phase implemented by the project**.

---

## 13. Actions on Objectives

The project includes several endpoint capabilities that can be associated with actions performed after C2 has been established.

Relevant capabilities:

```text
CAP-019 SHELL
CAP-020 SYSINFO
CAP-021 FILES
CAP-022 PERSISTENCE
CAP-023 SELF_DESTRUCT
```

These capabilities are intentionally limited to the authorized academic laboratory scope.

### 13.1 SHELL

`CAP-019` allows the agent to execute supported shell commands.

This should not be classified as Exploitation.

The capability assumes the agent is already running.

### 13.2 SYSINFO

`CAP-020` gathers information from the endpoint.

Examples may include:

```text
hostname
operating system
architecture
```

This is endpoint information collection rather than Kill Chain Reconnaissance.

### 13.3 FILES

`CAP-021` supports controlled file operations within the project's designed file-handling boundaries.

It is associated with Actions on Objectives because it allows the operator to request file-related actions after communication with the endpoint has been established.

### 13.4 PERSISTENCE

`CAP-022` represents persistence functionality.

Its exact supported mechanism and limitations remain an open design question.

The capability is required, but its precise implementation boundaries must be defined before it is considered fully specified.

### 13.5 SELF_DESTRUCT

`CAP-023` represents a controlled endpoint lifecycle action.

Its exact scope is tracked by `PRO-006`.

Possible scopes identified during the design phase include:

```text
A. Process termination only

B. Process termination
   + temporary cleanup

C. Process termination
   + project workspace cleanup

D. Full agent removal
   + persistence cleanup
```

The project does not assume unrestricted deletion.

Therefore:

> **SELF_DESTRUCT is a controlled lifecycle capability, not unrestricted filesystem deletion.**

### Conclusion

```text
Actions on Objectives
        │
        ├── CAP-019 SHELL
        ├── CAP-020 SYSINFO
        ├── CAP-021 FILES
        ├── CAP-022 PERSISTENCE
        └── CAP-023 SELF_DESTRUCT
```

The relationship is **partial**, because the project implements only selected endpoint actions rather than every possible objective.

---

## 14. Capability-to-Threat Traceability

The capability catalogue can be connected to the project's threat model.

Examples include:

| Capability | Related threats |
|---|---|
| `CAP-004` Beaconing | `TM-022` |
| `CAP-005` TCP/TLS | `TM-001`, `TM-003` |
| `CAP-006` Application protocol | `TM-003`, `TM-004`, `TM-005` |
| `CAP-007` Asynchronous task queuing | `TM-008`, `TM-020`, `TM-021` |
| `CAP-019` SHELL | `TM-006`, `TM-007`, `TM-010` |
| `CAP-021` FILES | `TM-011`, `TM-012`, `TM-013`, `TM-014`, `TM-016` |
| `CAP-022` PERSISTENCE | `TM-010`, `TM-011` |
| `CAP-023` SELF_DESTRUCT | `TM-023` |

This allows the Kill Chain analysis to remain connected to the project's broader security documentation.

---

## 15. Important Capability Distinctions

Several capabilities can appear superficially similar to Kill Chain phases but should not be equated with them.

### File transfer ≠ complete Delivery

File transfer allows data movement between the C2 and agent.

It does not by itself implement the broader Delivery phase of an intrusion.

### SHELL ≠ Exploitation

A shell command is executed by an already-running agent.

It does not represent vulnerability exploitation.

### Agent deployment ≠ automatic persistence

An agent being launched does not automatically imply that persistence mechanisms exist.

Persistence is explicitly represented by `CAP-022`.

### SELF_DESTRUCT ≠ unrestricted deletion

The project intends `SELF_DESTRUCT` to be a controlled lifecycle operation.

Its precise boundaries remain open under `PRO-006`.

### SYSINFO ≠ Reconnaissance

`SYSINFO` gathers endpoint information after the agent is already active.

It is therefore treated as an endpoint action rather than a pre-compromise reconnaissance capability.

---

## 16. Scope Classification

The project capability ranges are intentionally separated as follows.

### Required

```text
CAP-001 – CAP-014
CAP-019 – CAP-023
```

These capabilities form the current project delivery scope.

### Bonus

```text
CAP-015
```

`CAP-015` corresponds to Windows support.

### Future

```text
CAP-016 – CAP-018
```

These represent architectural extensions:

```text
CAP-016  TUI interface
CAP-017  Web interface
CAP-018  Additional transports
```

This classification describes **scope**, not implementation maturity.

---

## 17. Relationship with Project Architecture

The Kill Chain mapping corresponds directly to the project architecture.

The main C2 architecture is:

```text
Operator
   │
   ▼
Interface
   │
   ▼
C2 Core
   │
   ├── Agent Manager
   ├── Session Manager
   ├── Task Manager
   ├── Result Manager
   └── File Manager
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
   ├── Executor
   ├── Commands
   └── Platform
```

This supports the interpretation that:

- the C2 core corresponds primarily to **Command & Control**;
- the endpoint command layer contains selected **Actions on Objectives** capabilities;
- `PERSISTENCE` creates a limited relationship with **Installation**;
- the remaining Kill Chain phases are either partially related or outside the project's scope.

---

## 18. Overall Assessment

The project should be understood as:

```text
                C2-AUTOMATED
                     │
          ┌──────────┴──────────┐
          ▼                     ▼
 Command & Control       Endpoint actions
          │                     │
   CAP-001–CAP-010       CAP-019–CAP-023
                                  │
                         selected Kill Chain
                              relationships
```

It does **not** constitute a complete implementation of the Cyber Kill Chain.

The strongest representation is:

> **C2-AUTOMATED primarily implements Command and Control, with selected endpoint capabilities associated with Actions on Objectives and a limited relationship with Installation through PERSISTENCE.**

The purpose of this mapping is therefore to demonstrate the project's position within the attack lifecycle without overstating its capabilities.
