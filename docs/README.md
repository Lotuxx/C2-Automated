# Documentation

This directory contains the detailed documentation of the **C2-AUTOMATED** project.

The purpose of this documentation is not to create as many files as possible. Each document has a specific role and covers a distinct aspect of the project. The objective is to make the project easier to understand, implement, test, review, and maintain.

The documentation is organized by **subject and responsibility** rather than by development phase. This allows a contributor or reviewer to directly find the information they are looking for without having to search through a single large document.

---

## Main entry points

The following documents provide the main entry points into the project:

- [Project Overview](../README.md)
- [Global Architecture](../ARCHITECTURE.md)
- [Security Baseline](../SECURITY.md)
- [Architecture Decisions](../DECISIONS.md)
- [Contribution Guidelines](../CONTRIBUTING.md)

This directory contains the detailed technical specifications referenced by these main documents.

---

## Documentation structure

```text
docs/
├── README.md
├── data-model.md
├── state-machines.md
├── authorative-task-state-model.md
├── protocol.md
├── protocol-state-transition.md
├── reconnection-and-synchronization.md
├── task-lifecycle.md
├── network-architecture.md
├── file-transfer.md
├── testing-strategy.md
├── threat-model.md
├── countermeasures.md
├── requirements-mapping.md
└── kill-chain-analysis.md
```

Some documents describe relatively stable design decisions, while others intentionally contain open points that will be refined during implementation.

The status of each document is listed at the end of this file.

---

# Quick Start

This section provides the recommended reading order for someone discovering the project for the first time.

## 1. Start with the repository overview

Read [`../README.md`](../README.md) first.

It provides:

- project purpose;
- objectives;
- major features;
- high-level architecture;
- repository structure;
- development status;
- links to detailed documentation.

This should provide enough context before going into the technical documentation.

---

## 2. Understand the global architecture

Next, read [`../ARCHITECTURE.md`](../ARCHITECTURE.md).

This explains how the main components fit together:

```text
Operator
    │
    ▼
C2 Server
    │
    ├── Interface
    ├── Core
    ├── Protocol
    ├── Transport
    ├── Storage
    ├── File Management
    └── Synchronization
            │
            ▼
          Agent(s)
```

At this stage, focus on understanding **what each component is responsible for** rather than implementation details.

---

## 3. Understand the domain model and state machines

Read:

- [`data-model.md`](data-model.md)
- [`state-machines.md`](state-machines.md)
- [`authorative-task-state-model.md`](authorative-task-state-model.md)

These documents establish the conceptual foundation of the system.

The data model explains entities such as:

```text
Agent
  │
  ├── Session
  ├── Task
  │    └── Result
  │
  └── File Transfer
```

The general state-machine specification defines the state machines used throughout the system.

The **Authoritative Task State Model** provides the dedicated normative definition of Task states and transitions:

```text
PENDING
    ↓
WAITING_ACK
    ↓
QUEUED
    ↓
RUNNING
    ├──→ COMPLETED
    ├──→ FAILED
    ├──→ TIMEOUT
    └──→ CANCELLED
```

The Task state model should be treated as the authoritative reference whenever another document needs to describe Task lifecycle states.

Important distinctions include:

```text
Session state
        ≠
Agent communication state
        ≠
Agent health
        ≠
Agent activity
        ≠
Task state
```

---

## 4. Understand the communication protocol

Read [`protocol.md`](protocol.md).

This defines the logical messages exchanged between the C2 and agents.

Then read [`protocol-state-transition.md`](protocol-state-transition.md).

These documents provide complementary views:

```text
protocol.md
"What information is exchanged?"

        ↓

protocol-state-transition.md
"Which protocol events affect which system states?"
```

When Task-related protocol messages are involved, consult [`authorative-task-state-model.md`](authorative-task-state-model.md) for the authoritative Task-state semantics.

---

## 5. Understand reconnection and synchronization

Read [`reconnection-and-synchronization.md`](reconnection-and-synchronization.md).

This document explains what happens when an Agent:

- connects for the first time;
- reconnects after communication loss;
- has pending tasks;
- has results that have not yet been delivered;
- has state that may differ from the C2's recorded state.

The fundamental model is:

```text
New connection
      ↓
New Session
      ↓
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

A previous disconnected Session is never reopened.

---

## 6. Understand the main workflows

The next documents describe the main operational workflows.

### Tasks

[`task-lifecycle.md`](task-lifecycle.md)

Explains how a Task is:

- created;
- acknowledged;
- queued;
- executed;
- completed;
- failed;
- timed out;
- cancelled;
- recovered.

For the exact normative Task states and transition rules, [`authorative-task-state-model.md`](authorative-task-state-model.md) is authoritative.

The two documents therefore have different roles:

| Document | Role |
|---|---|
| `authorative-task-state-model.md` | Authoritative Task states and transitions |
| `task-lifecycle.md` | Operational Task workflow, recovery, persistence, and execution behavior |

### File transfers

[`file-transfer.md`](file-transfer.md)

Explains how files are transferred independently from ordinary Task Results:

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
    ↓
Reconstruction
    ↓
Integrity verification
    ↓
Storage
```

---

## 7. Understand the network architecture

Read [`network-architecture.md`](network-architecture.md).

This document complements the logical protocol specification by describing the network-level architecture.

The distinction is:

```text
Protocol
"What is exchanged?"

Network Architecture
"Where and through which communication path?"
```

It covers:

- connection direction;
- TCP/TLS transport;
- network zones;
- trust boundaries;
- addressing;
- endpoints;
- registration;
- synchronization;
- multi-agent communication;
- laboratory deployment.

---

## 8. Understand security

Start with [`../SECURITY.md`](../SECURITY.md).

This provides the global security baseline.

Then read:

- [`threat-model.md`](threat-model.md);
- [`countermeasures.md`](countermeasures.md);
- [`kill-chain-analysis.md`](kill-chain-analysis.md).

These documents have different purposes:

```text
SECURITY.md
Security principles and boundaries
        ↓
Threat Model
What can go wrong?
        ↓
Kill Chain Analysis
How capabilities map to the analytical model
        ↓
Countermeasures
How identified risks are reduced
        ↓
Testing Strategy
How controls and behavior are validated
```

---

## 9. Understand validation and testing

Read [`testing-strategy.md`](testing-strategy.md).

This explains how the different components and workflows are tested, from individual modules through complete C2 ↔ Agent interactions.

The objective is to demonstrate not only:

> **What is implemented?**

but also:

> **Does the implementation behave according to the documented design?**

and:

> **Are the relevant security properties being validated?**

---

## 10. Check requirement coverage

Finally, read [`requirements-mapping.md`](requirements-mapping.md).

This document connects the academic project requirements to:

```text
Requirement
    ↓
Design
    ↓
Implementation
    ↓
Test
    ↓
Validation
```

It is particularly useful during project reviews and before the final submission.

---

# Recommended Reading Order

For someone who wants the most useful path through the documentation:

```text
1.  ../README.md
        ↓
2.  ../ARCHITECTURE.md
        ↓
3.  data-model.md
        ↓
4.  state-machines.md
        ↓
5.  authorative-task-state-model.md
        ↓
6.  protocol.md
        ↓
7.  protocol-state-transition.md
        ↓
8.  reconnection-and-synchronization.md
        ↓
9.  task-lifecycle.md
        ↓
10. file-transfer.md
        ↓
11. network-architecture.md
        ↓
12. ../SECURITY.md
        ↓
13. threat-model.md
        ↓
14. countermeasures.md
        ↓
15. kill-chain-analysis.md
        ↓
16. testing-strategy.md
        ↓
17. requirements-mapping.md
```

Not every reader needs to follow the complete sequence.

The navigation tables below can be used to jump directly to a particular topic.

---

# How to Use This Documentation

This documentation serves three main purposes:

- **Understand:** learn how the system is designed before reading the implementation.
- **Implement:** use the relevant specification when developing a component or feature.
- **Validate:** use the testing and requirements documents to verify that the implementation matches the design and project requirements.

When implementing a feature, the recommended approach is:

1. Check `ARCHITECTURE.md` to understand where the feature belongs.
2. Check `data-model.md` and `state-machines.md` if the feature introduces or modifies entities or states.
3. If the feature concerns Tasks, check `authorative-task-state-model.md`.
4. Check the relevant detailed specification in `docs/`.
5. Check `DECISIONS.md` for existing architectural decisions or open points.
6. Implement the feature.
7. Add or update the corresponding tests.
8. Update the relevant documentation if the implementation changes the design.
9. Update `requirements-mapping.md` when the feature addresses a project requirement.

Documentation should therefore be consulted throughout development, not only before the final submission.

---

# Documentation Source of Truth

When information appears to be related across multiple documents, each document has a defined scope.

| Subject | Primary source |
|---|---|
| Global system architecture | [`../ARCHITECTURE.md`](../ARCHITECTURE.md) |
| Architectural decisions | [`../DECISIONS.md`](../DECISIONS.md) |
| Security principles and boundaries | [`../SECURITY.md`](../SECURITY.md) |
| Domain entities and relationships | [`data-model.md`](data-model.md) |
| General state definitions and transitions | [`state-machines.md`](state-machines.md) |
| **Authoritative Task states and transitions** | [`authorative-task-state-model.md`](authorative-task-state-model.md) |
| Protocol contract | [`protocol.md`](protocol.md) |
| Protocol events and state transitions | [`protocol-state-transition.md`](protocol-state-transition.md) |
| Reconnection and synchronization | [`reconnection-and-synchronization.md`](reconnection-and-synchronization.md) |
| Task operational lifecycle | [`task-lifecycle.md`](task-lifecycle.md) |
| Network topology | [`network-architecture.md`](network-architecture.md) |
| File-transfer behavior | [`file-transfer.md`](file-transfer.md) |
| Threats | [`threat-model.md`](threat-model.md) |
| Countermeasures | [`countermeasures.md`](countermeasures.md) |
| Kill Chain analysis | [`kill-chain-analysis.md`](kill-chain-analysis.md) |
| Testing approach | [`testing-strategy.md`](testing-strategy.md) |
| Requirement traceability | [`requirements-mapping.md`](requirements-mapping.md) |
| Development workflow | [`../CONTRIBUTING.md`](../CONTRIBUTING.md) |

Other documents may reference this information, but should not silently redefine it.

When a detailed document needs to discuss a subject owned by another document, it should preferably reference that document rather than create a second conflicting definition.

---

# Documentation Map

## `data-model.md`

**Purpose:** Define the conceptual entities, relationships, identifiers, persistence concepts, and consistency rules of the system.

This document covers:

- Agent;
- Session;
- Task;
- Result;
- Message;
- File Transfer;
- Event;
- identifiers;
- relationships and cardinalities;
- persistence;
- runtime state;
- reliability and offline operation;
- consistency rules.

**Look here for:** the conceptual data model.

**Status:** Work in Progress.

---

## `state-machines.md`

**Purpose:** Define the general state machines used throughout the system.

This document covers:

- Agent communication state;
- Agent health;
- Agent activity;
- Session state;
- general Task-state relationships;
- Result-related state;
- File-transfer state;
- state-transition rules;
- invalid transitions;
- cross-state invariants;
- synchronization invariants.

Task-specific authoritative state semantics are maintained separately in [`authorative-task-state-model.md`](authorative-task-state-model.md).

Important distinctions include:

```text
Session state
        ≠
Agent communication state
        ≠
Agent health
        ≠
Agent activity
        ≠
Task state
```

**Look here for:** the system-wide state-machine relationships and cross-state invariants.

**Status:** Work in Progress.

---

## `authorative-task-state-model.md`

**Purpose:** Define the authoritative Task state model used by the project.

This document is the **normative source of truth for Task states and Task-state transitions**.

The authoritative persistent Task states are:

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

Terminal states are:

```text
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
    ↓
COMPLETED / FAILED
```

Additional transitions cover timeout and cancellation where applicable.

This document also defines important Task semantics, including:

- `TASK_ACK` meaning acceptance rather than completion;
- Task ownership by Agent rather than Session;
- Tasks spanning multiple Sessions;
- communication loss versus Task failure;
- timeout semantics;
- recovery behavior;
- `UNKNOWN` as a recovery/reporting condition rather than a persistent state;
- Result association;
- duplicate-task protection;
- invalid transitions.

**Look here for:** the exact authoritative Task state model.

**Important:** Other documents may describe Task behavior, but they should not redefine the authoritative Task states independently.

**Status:** Work in Progress.

---

## `protocol.md`

**Purpose:** Define how the C2 server and agents communicate at the application level.

This document covers:

- message types;
- message structure;
- common message metadata;
- serialization and deserialization;
- validation;
- message correlation;
- protocol versioning;
- registration;
- synchronization;
- beacon and liveness messages;
- task and result messages;
- file-transfer messages;
- error messages.

The protocol currently includes message categories such as:

```text
REGISTER
REGISTER_ACK
SYNC_STATE
SYNC_STATE_RESPONSE
SYNC_COMPLETE

BEACON
BEACON_ACK
PING
PONG

TASK
TASK_ACK
TASK_STATUS
TASK_STATUS_QUERY
RESULT

FILE_START
FILE_CHUNK
FILE_END

ERROR
```

For Task state semantics, this document defers to [`authorative-task-state-model.md`](authorative-task-state-model.md).

**Look here for:** the logical communication contract between C2 and Agent.

**Status:** Work in Progress.

---

## `protocol-state-transition.md`

**Purpose:** Define how protocol events interact with the system's state machines.

This document bridges:

```text
Protocol messages
        ↓
Protocol events
        ↓
State-machine transitions
```

It clarifies, for example, that:

```text
New connection
    ↓
New Session = CONNECTING
    ↓
Transport established
    ↓
Session = CONNECTED
    ↓
REGISTER
    ↓
Agent communication = SYNCHRONIZING
    ↓
Synchronization
    ↓
Agent communication = CONNECTED
```

In particular:

- `REGISTER` does not establish the Session;
- `REGISTER_ACK` does not cause `Session CONNECTING → CONNECTED`;
- a new connection always creates a new Session;
- Task-related transitions must remain consistent with the authoritative Task state model.

**Look here for:** the relationship between protocol events and state transitions.

**Status:** Work in Progress.

---

## `reconnection-and-synchronization.md`

**Purpose:** Define how the system recovers and reconciles state after communication interruptions.

This document covers:

- initial registration;
- reconnection;
- creation of new Sessions;
- `previous_session_id`;
- synchronization;
- pending Tasks;
- Task-state reconciliation;
- pending Results;
- duplicate protection;
- recovery after C2 restart;
- communication-state recovery.

The fundamental principle is:

> **A new connection creates a new Session; synchronization reconciles state across the new Session.**

Task reconciliation must remain consistent with [`authorative-task-state-model.md`](authorative-task-state-model.md).

**Look here for:** reconnect behavior, state recovery, and reconciliation.

**Status:** Work in Progress.

---

## `task-lifecycle.md`

**Purpose:** Describe the operational lifecycle of Tasks.

This document explains how a Task is:

- created;
- dispatched;
- acknowledged;
- queued;
- executed;
- completed;
- failed;
- timed out;
- cancelled;
- recovered.

It covers:

- task creation;
- task identification;
- task queues;
- asynchronous execution;
- acknowledgement semantics;
- task/result relationships;
- failures;
- timeouts;
- cancellation;
- recovery;
- duplicate protection;
- persistence;
- traceability;
- multi-agent operation.

The exact Task states and legal transitions are defined by [`authorative-task-state-model.md`](authorative-task-state-model.md).

The distinction is intentional:

```text
Authorative Task State Model
        ↓
"What states and transitions are valid?"

Task Lifecycle
        ↓
"How does the Task behave operationally?"
```

**Look here for:** Task workflow, recovery, persistence, and execution behavior.

**Status:** Work in Progress.

---

## `network-architecture.md`

**Purpose:** Describe the network-level architecture of the project.

This document focuses on:

- network topology;
- connection direction;
- C2 server;
- agents;
- TCP/TLS transport;
- trust boundaries;
- network zones;
- endpoints;
- addressing;
- registration;
- synchronization;
- multi-agent communication;
- laboratory deployment.

**Look here for:** network topology and communication paths.

**Status:** Work in Progress.

---

## `file-transfer.md`

**Purpose:** Define how files are transferred between the C2 server and agents.

This document covers:

- transfer identifiers;
- upload/download concepts;
- transfer lifecycle;
- `FILE_START`;
- `FILE_CHUNK`;
- `FILE_END`;
- chunking;
- temporary storage;
- reconstruction;
- integrity verification;
- transfer failures;
- cleanup;
- interaction with Tasks;
- storage responsibilities.

**Look here for:** anything concerning movement, reconstruction, verification, and storage of file contents.

**Status:** Work in Progress.

---

## `testing-strategy.md`

**Purpose:** Define how the project will be tested and validated.

This document covers:

```text
Unit
  ↓
Component
  ↓
Integration
  ↓
C2 ↔ Agent
  ↓
End-to-End
```

It includes testing of:

- state machines;
- authoritative Task states;
- registration and synchronization;
- protocol handling;
- message routing;
- sessions;
- tasks;
- results;
- transport;
- storage;
- file transfers;
- agent execution;
- platform abstraction;
- beacon/liveness;
- persistence and restart;
- security controls;
- failure and recovery;
- multi-agent operation;
- regression.

**Look here for:** how correctness, reliability, and security are validated.

**Status:** Work in Progress.

---

## `requirements-mapping.md`

**Purpose:** Provide traceability between the academic project requirements and the project design, implementation, and validation.

The document connects:

```text
Requirement
    ↓
Design
    ↓
Implementation
    ↓
Test
    ↓
Validation
```

It also distinguishes statuses such as:

- Required;
- Planned;
- In Progress;
- Implemented;
- Validated;
- Bonus;
- Open;
- Accepted;
- Out of Scope.

The authoritative Task state model is referenced when mapping Task-management requirements.

**Look here for:** where each project requirement is addressed.

**Status:** Work in Progress.

---

## `threat-model.md`

**Purpose:** Identify the security threats relevant to the project.

The threat model covers areas such as:

- C2 exposure;
- Agent impersonation;
- authentication;
- message manipulation;
- replay;
- malformed protocol messages;
- unauthorized task creation;
- duplicate task execution;
- session confusion;
- synchronization inconsistency;
- file-transfer abuse;
- storage exposure;
- secrets;
- logging;
- availability;
- unsafe command behavior.

It distinguishes:

```text
Asset
  ↓
Attack Surface
  ↓
Threat
  ↓
Risk
  ↓
Security Requirement
```

**Look here for:** what can go wrong and what is at risk.

**Status:** Work in Progress.

---

## `countermeasures.md`

**Purpose:** Document the concrete security controls used to reduce identified threats.

This document connects:

```text
Threat
  ↓
Risk
  ↓
Countermeasure
  ↓
Implementation
  ↓
Validation
```

Examples include:

- TLS;
- Agent authentication;
- message validation;
- task validation;
- executor boundaries;
- controlled file workspaces;
- path validation;
- file integrity;
- resource limits;
- logging and traceability;
- configuration and secret protection;
- persistence safeguards;
- security regression testing;
- authorized deployment.

**Look here for:** how identified risks are mitigated.

**Status:** Work in Progress.

---

## `kill-chain-analysis.md`

**Purpose:** Analyse the project through the Cyber Kill Chain perspective.

This document maps relevant project capabilities to the analytical Kill Chain model.

The objective is not to claim that the project implements every phase, but to identify:

- which phases are represented;
- which capabilities relate to those phases;
- which phases are outside project scope;
- what defensive observations or controls are relevant.

**Look here for:** Kill Chain mapping and security analysis from that perspective.

**Status:** Planned / To be finalized.

---

# Where Should I Look?

| Question | Document |
|---|---|
| What is the overall architecture? | [`../ARCHITECTURE.md`](../ARCHITECTURE.md) |
| Why was an architectural choice made? | [`../DECISIONS.md`](../DECISIONS.md) |
| What entities exist? | [`data-model.md`](data-model.md) |
| What general state machines exist? | [`state-machines.md`](state-machines.md) |
| **What are the authoritative Task states?** | [`authorative-task-state-model.md`](authorative-task-state-model.md) |
| How do C2 and Agent exchange messages? | [`protocol.md`](protocol.md) |
| How do protocol events affect state? | [`protocol-state-transition.md`](protocol-state-transition.md) |
| What happens after reconnection? | [`reconnection-and-synchronization.md`](reconnection-and-synchronization.md) |
| How does a Task behave operationally? | [`task-lifecycle.md`](task-lifecycle.md) |
| How are Tasks associated with Results? | [`task-lifecycle.md`](task-lifecycle.md) / [`data-model.md`](data-model.md) |
| How are files transferred? | [`file-transfer.md`](file-transfer.md) |
| Where are files stored? | [`file-transfer.md`](file-transfer.md) |
| What does the network look like? | [`network-architecture.md`](network-architecture.md) |
| What are the security principles? | [`../SECURITY.md`](../SECURITY.md) |
| What are the project threats? | [`threat-model.md`](threat-model.md) |
| How are threats mitigated? | [`countermeasures.md`](countermeasures.md) |
| How does the project map to the Kill Chain? | [`kill-chain-analysis.md`](kill-chain-analysis.md) |
| How should something be tested? | [`testing-strategy.md`](testing-strategy.md) |
| How is a school requirement addressed? | [`requirements-mapping.md`](requirements-mapping.md) |
| How should I contribute? | [`../CONTRIBUTING.md`](../CONTRIBUTING.md) |

---

# Relationship Between the Documents

The documents are complementary rather than independent.

A typical Task-related feature can therefore be followed through:

```text
Architecture
    ↓
Where the capability fits
    ↓
Data Model
    ↓
What entities and relationships are involved
    ↓
State Machines
    ↓
How system states interact
    ↓
Authorative Task State Model
    ↓
What Task states and transitions are authoritative
    ↓
Protocol
    ↓
Which messages are exchanged
    ↓
Protocol / State Transitions
    ↓
How messages affect state
    ↓
Task Lifecycle
    ↓
How the Task behaves operationally
    ↓
Synchronization
    ↓
How Task state is recovered across Sessions
    ↓
Security / Threat Model
    ↓
What can go wrong
    ↓
Countermeasures
    ↓
How risks are reduced
    ↓
Testing Strategy
    ↓
How the feature is validated
    ↓
Requirements Mapping
    ↓
Which project requirement it satisfies
```

This structure avoids putting the same information into multiple documents while still allowing each subject to be documented at the appropriate level.

---

# When to Update the Documentation

Documentation should be updated when a change affects:

- architecture or module responsibilities;
- communication or protocol behavior;
- state machines;
- Task states or Task transitions;
- Task or file-transfer workflows;
- persistent data or domain entities;
- synchronization or reconnection behavior;
- security controls or threat assumptions;
- network topology;
- testing strategy;
- project requirements.

Documentation should be updated as part of the same change rather than reconstructed at the end of the project.

When a change represents a significant architectural choice, the corresponding decision should also be recorded in [`../DECISIONS.md`](../DECISIONS.md).

---

# Root-Level Documentation

Some documentation deliberately remains outside this directory because it describes the project at a broader level.

## [`../README.md`](../README.md)

The main entry point to the repository.

It provides:

- project overview;
- objectives;
- major features;
- high-level architecture;
- repository structure;
- project status;
- development information;
- links to detailed documentation.

---

## [`../ARCHITECTURE.md`](../ARCHITECTURE.md)

The global architectural baseline.

It describes:

- C2 and Agent architecture;
- major modules;
- responsibilities;
- boundaries;
- protocol/transport separation;
- storage architecture;
- communication flows;
- synchronization;
- extensibility;
- repository mapping.

---

## [`../SECURITY.md`](../SECURITY.md)

The project's global security baseline.

It defines:

- security principles;
- secure communication;
- Agent identity and authentication considerations;
- protocol security;
- execution boundaries;
- file-transfer security;
- storage restrictions;
- logging;
- secrets/configuration;
- resource and availability considerations;
- authorized laboratory scope.

Detailed threat and countermeasure analysis is documented separately in `threat-model.md` and `countermeasures.md`.

---

## [`../DECISIONS.md`](../DECISIONS.md)

The project's decision history.

It records important architectural choices and unresolved decisions using:

- `ADR-*` for accepted architectural decisions;
- `PRO-*` for proposed decisions that remain open.

**Look here for:** why the architecture was designed this way and which decisions remain open.

---

## [`../CONTRIBUTING.md`](../CONTRIBUTING.md)

The project's development and contribution rules.

It describes:

- branching strategy;
- development workflow;
- pull requests;
- validation before merge;
- documentation consistency;
- security-sensitive changes;
- repository hygiene.

**Look here for:** how changes should be made to the repository.

---

# Common Terms

| Term | Meaning |
|---|---|
| **C2** | Command and Control server responsible for coordinating agents and tasks. |
| **Agent** | Endpoint-side component that communicates with the C2 and executes authorized tasks. |
| **Task** | An instruction created by the C2 for an Agent to process. |
| **Result** | Data returned by an Agent in relation to a Task. |
| **Session** | One concrete communication connection episode between an Agent and the C2. |
| **Beacon** | Agent communication mechanism used to indicate availability and exchange pending information. |
| **Transfer** | A logical file-transfer operation between the C2 and an Agent. |
| **Event** | A recorded occurrence representing a significant system activity or state change. |
| **ADR** | Accepted Architecture Decision Record. |
| **PRO** | Proposed decision that has not yet been finalized. |

---

# Documentation Status

Documentation is developed alongside the project rather than being postponed until the end.

Current status:

| Document | Status |
|---|---|
| `data-model.md` | Work in Progress |
| `state-machines.md` | Work in Progress |
| `authorative-task-state-model.md` | Work in Progress |
| `protocol.md` | Work in Progress |
| `protocol-state-transition.md` | Work in Progress |
| `reconnection-and-synchronization.md` | Work in Progress |
| `task-lifecycle.md` | Work in Progress |
| `network-architecture.md` | Work in Progress |
| `file-transfer.md` | Work in Progress |
| `testing-strategy.md` | Work in Progress |
| `threat-model.md` | Work in Progress |
| `countermeasures.md` | Work in Progress |
| `requirements-mapping.md` | Work in Progress |
| `kill-chain-analysis.md` | Planned / To be finalized |

A document marked **Work in Progress** may contain intentionally unresolved design points. These should not be interpreted as finalized implementation decisions.

Architectural choices that remain open should be recorded in [`../DECISIONS.md`](../DECISIONS.md) rather than silently decided during implementation.

---

# Documentation Principles

The documentation follows a few simple principles:

1. **One subject, one primary document.**  
   Information should have a clear home.

2. **Avoid unnecessary duplication.**  
   A document should reference another document instead of reproducing its content whenever possible.

3. **Separate architecture from detailed specifications.**  
   High-level architecture belongs in `ARCHITECTURE.md`; detailed protocol, state, Task, synchronization, file-transfer, network, and testing specifications belong in `docs/`.

4. **Record important decisions.**  
   Open or significant architectural decisions belong in `DECISIONS.md`.

5. **Keep documentation synchronized with implementation.**  
   A significant architecture or behavior change should trigger the corresponding documentation update.

6. **Document uncertainty explicitly.**  
   Proposed behavior should not be presented as finalized behavior.

7. **Maintain a clear source of truth.**  
   In particular, the authoritative Task state model should not be redefined in other documents.

The goal is therefore not to have a large number of Markdown files.

The goal is to make the project's design understandable and traceable from:

```text
Requirements
    ↓
Architecture
    ↓
Domain Model / State Machines
    ↓
Authoritative Task State Model
    ↓
Protocol / Workflows
    ↓
Implementation
    ↓
Security Analysis
    ↓
Testing
    ↓
Validation
```

---

# Navigation Summary

For most technical questions, the following map is sufficient:

```text
README.md
   │
   ▼
docs/README.md
   │
   ├── Architecture
   │      └── ../ARCHITECTURE.md
   │
   ├── Decisions
   │      └── ../DECISIONS.md
   │
   ├── Data Model
   │      └── data-model.md
   │
   ├── State Machines
   │      └── state-machines.md
   │
   ├── Authoritative Task State Model
   │      └── authorative-task-state-model.md
   │
   ├── Protocol
   │      └── protocol.md
   │
   ├── Protocol / State Transitions
   │      └── protocol-state-transition.md
   │
   ├── Reconnection / Synchronization
   │      └── reconnection-and-synchronization.md
   │
   ├── Tasks
   │      └── task-lifecycle.md
   │
   ├── Network
   │      └── network-architecture.md
   │
   ├── File Transfer
   │      └── file-transfer.md
   │
   ├── Security
   │      └── ../SECURITY.md
   │
   ├── Threat Model
   │      └── threat-model.md
   │
   ├── Countermeasures
   │      └── countermeasures.md
   │
   ├── Kill Chain
   │      └── kill-chain-analysis.md
   │
   ├── Testing
   │      └── testing-strategy.md
   │
   └── Requirements
          └── requirements-mapping.md
```

This file should be the first place to look when navigating the detailed project documentation.
