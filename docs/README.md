# Documentation

This directory contains the detailed documentation of the **C2-AUTOMATED** project.

The purpose of this documentation is not to create as many files as possible. Each document has a specific role and covers a distinct aspect of the project. The objective is to make the project easier to understand, implement, test, review, and maintain.

The documentation is organized by **subject** rather than by development phase. This allows a contributor or reviewer to directly find the information they are looking for without having to search through a single large document.

---

## Main entry points

The following documents provide the main entry points into the project:

- [Project Overview](../README.md)
- [Global Architecture](../ARCHITECTURE.md)
- [Security Baseline](../SECURITY.md)
- [Architecture Decisions](../DECISIONS.md)
- [Contribution Guidelines](../CONTRIBUTING.md)

This directory contains the more detailed technical documentation referenced by these main documents.

---

## Documentation structure

```text
docs/
├── README.md
├── protocol.md
├── task-lifecycle.md
├── file-transfer.md
├── data-model.md
├── testing-strategy.md
├── requirements-mapping.md
├── threat-model.md
├── network-architecture.md
├── kill-chain-analysis.md
└── countermeasures.md
```

Some documents are already drafted, while others will be completed as the corresponding design decisions and implementation become more precise.

---

## Quick start

This section provides the recommended reading order for someone discovering the project for the first time.

### 1. Start with the repository overview

Read [`../README.md`](../README.md) first.

It provides the project's:

- purpose;
- objectives;
- major features;
- high-level architecture;
- repository structure;
- current development status.

This should provide enough context before going into the technical documentation.

---

### 2. Understand the global architecture

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
    └── Storage
            │
            ▼
          Agent(s)
```

At this stage, focus on understanding **what each component is responsible for** rather than implementation details.

---

### 3. Understand the communication model

Read [`protocol.md`](protocol.md) to understand how the C2 and agents communicate.

Then consult [`network-architecture.md`](network-architecture.md) once it is available to understand how those communications are represented at the network level.

These provide two complementary views:

```text
Protocol
"What information is exchanged?"

Network Architecture
"Where and through which communication path is it exchanged?"
```

---

### 4. Understand the main workflows

The next recommended documents are:

[`task-lifecycle.md`](task-lifecycle.md)

Explains how a task moves through the system.

[`file-transfer.md`](file-transfer.md)

Explains how files are transferred and stored.

Together, these documents describe two of the main workflows of the project:

```text
Task
C2 → Agent → Execution → Result → C2

File Transfer
C2 / Agent → Start → Chunks → End → Integrity Check → Storage
```

---

### 5. Understand the data behind those workflows

Read [`data-model.md`](data-model.md).

This explains the entities involved in the previous workflows and how they relate:

```text
Agent
  │
  ├── Session
  │
  ├── Task
  │    └── Result
  │
  └── File Transfer
```

This provides the conceptual foundation for the persistence layer.

---

### 6. Understand security considerations

Once the architecture and workflows are understood, read [`../SECURITY.md`](../SECURITY.md).

Then consult:

- [`threat-model.md`](threat-model.md) for identified threats;
- [`kill-chain-analysis.md`](kill-chain-analysis.md) for the Kill Chain perspective;
- [`countermeasures.md`](countermeasures.md) for the controls used to mitigate identified risks.

These documents form a security-analysis chain:

```text
Architecture
     ↓
Threats
     ↓
Kill Chain Analysis
     ↓
Countermeasures
     ↓
Validation
```

---

### 7. Understand how the project is validated

Read [`testing-strategy.md`](testing-strategy.md).

This explains how the different components and workflows are tested, from individual modules through complete C2 ↔ Agent interactions.

The goal is to understand not only **what is implemented**, but also **how its correctness and security are demonstrated**.

---

### 8. Check requirement coverage

Finally, read [`requirements-mapping.md`](requirements-mapping.md).

This document connects the school requirements to:

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

### Recommended reading order

For someone who wants the shortest useful path through the documentation:

```text
1. ../README.md
        ↓
2. ../ARCHITECTURE.md
        ↓
3. protocol.md
        ↓
4. task-lifecycle.md
        ↓
5. file-transfer.md
        ↓
6. data-model.md
        ↓
7. ../SECURITY.md
        ↓
8. threat-model.md
        ↓
9. kill-chain-analysis.md
        ↓
10. countermeasures.md
        ↓
11. testing-strategy.md
        ↓
12. requirements-mapping.md
```

Not every reader needs to follow the complete sequence. The navigation table below can be used to jump directly to a particular topic.

---

## How to use this documentation

This documentation serves three main purposes:

- **Understand:** learn how the system is designed before reading the implementation.
- **Implement:** use the relevant specification when developing a component or feature.
- **Validate:** use the testing and requirements documents to verify that the implementation matches the design and project requirements.

When implementing a feature, the recommended approach is:

1. Check `ARCHITECTURE.md` to understand where the feature belongs.
2. Check the relevant detailed document in `docs/`.
3. Check `DECISIONS.md` for existing architectural decisions or open points.
4. Implement the feature.
5. Update the relevant documentation if the implementation changes the design.
6. Add or update the corresponding tests.
7. Update `requirements-mapping.md` when the feature addresses a project requirement.

Documentation should therefore be consulted throughout development, not only before the final submission.

---

## Documentation source of truth

When information appears to be related across multiple documents, each document has a defined scope.

| Subject | Primary source |
|---|---|
| Global system architecture | [`../ARCHITECTURE.md`](../ARCHITECTURE.md) |
| Architectural decisions | [`../DECISIONS.md`](../DECISIONS.md) |
| Security principles and boundaries | [`../SECURITY.md`](../SECURITY.md) |
| Protocol contract | [`protocol.md`](protocol.md) |
| Task states and lifecycle | [`task-lifecycle.md`](task-lifecycle.md) |
| File-transfer behavior | [`file-transfer.md`](file-transfer.md) |
| Domain entities and relationships | [`data-model.md`](data-model.md) |
| Network topology | [`network-architecture.md`](network-architecture.md) |
| Threats | [`threat-model.md`](threat-model.md) |
| Kill Chain analysis | [`kill-chain-analysis.md`](kill-chain-analysis.md) |
| Countermeasures | [`countermeasures.md`](countermeasures.md) |
| Testing approach | [`testing-strategy.md`](testing-strategy.md) |
| Requirement traceability | [`requirements-mapping.md`](requirements-mapping.md) |
| Development workflow | [`../CONTRIBUTING.md`](../CONTRIBUTING.md) |

Other documents may reference this information, but should not silently redefine it.

When a detailed document needs to discuss a subject owned by another document, it should preferably reference that document rather than create a second conflicting definition.

---

## Documentation map

### `protocol.md`

**Purpose:** Define how the C2 server and agents communicate at the application level.

This document covers:

- message types;
- message structure;
- common message metadata;
- serialization and deserialization;
- validation;
- message correlation;
- protocol versioning;
- registration and beacon messages;
- task and result messages;
- file-transfer messages;
- error messages.

This document answers questions such as:

> What does a message exchanged between the C2 and an agent look like?

> How does the receiver know what type of message it received?

> How are messages associated with an agent, task, or transfer?

**Look here for:** the logical communication contract between C2 and Agent.

**Status:** Work in Progress.

---

### `task-lifecycle.md`

**Purpose:** Describe how a task is created, transmitted, executed, and completed.

This document covers:

- task creation;
- task identification;
- task states;
- task queues;
- asynchronous execution;
- task/result relationships;
- task failures;
- retries and recovery concepts;
- task persistence;
- traceability and logging.

The current conceptual lifecycle is:

```text
PENDING
   ↓
 SENT
   ↓
RUNNING
   ├──→ COMPLETED
   └──→ FAILED
```

This document also provides the place for documenting special task types whose lifecycle differs from a standard command, such as the currently unresolved `SELF_DESTRUCT` behavior.

**Look here for:** everything related to the lifecycle of a task.

**Status:** Work in Progress.

---

### `file-transfer.md`

**Purpose:** Define how files are transferred between the C2 server and agents.

This document covers:

- upload and download concepts;
- transfer identifiers;
- transfer lifecycle;
- `FILE_START`, `FILE_CHUNK`, and `FILE_END`;
- chunking;
- temporary files;
- file reconstruction;
- integrity verification;
- transfer failures;
- cleanup;
- interaction with tasks;
- storage responsibilities;
- large-file handling.

The document also distinguishes between:

```text
File Transfer Management
        ↓
Logical transfer state
        ↓
File Storage
        ↓
Physical file
```

This separation prevents file-transfer logic from becoming tightly coupled to a specific storage implementation.

**Look here for:** anything concerning the movement and handling of file contents.

**Status:** Work in Progress.

---

### `data-model.md`

**Purpose:** Describe the entities and relationships that exist within the system independently of their concrete database implementation.

The document covers entities such as:

- Agent;
- Session;
- Task;
- Result;
- Message;
- File Transfer.

It explains:

- what each entity represents;
- how entities are related;
- which identifiers are used;
- what information is persistent;
- what information is temporary;
- conceptual consistency rules;
- the distinction between domain objects and database models.

For example:

```text
Agent
 ├── Sessions
 ├── Tasks
 │    └── Results
 └── File Transfers
```

**Look here for:** entities, relationships, identifiers, and persistent data concepts.

**Status:** Work in Progress.

---

### `testing-strategy.md`

**Purpose:** Define how the project will be tested and validated.

This document covers the different testing levels:

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

It also addresses testing of:

- protocol handling;
- session management;
- task management;
- result processing;
- transport;
- storage;
- file transfers;
- agent execution;
- platform-specific behavior;
- security controls;
- multi-agent operation;
- regression;
- failure handling.

The objective is to make testing part of the architecture rather than something added only after implementation.

**Look here for:** how a feature or subsystem should be validated.

**Status:** Work in Progress.

---

### `requirements-mapping.md`

**Purpose:** Provide traceability between the school requirements and the project implementation.

This document answers:

> Where is each required feature addressed?

For each requirement, it identifies where the corresponding design, implementation, and tests should be found.

Typical relationships are:

```text
Requirement
    ↓
Architecture
    ↓
Implementation
    ↓
Test
    ↓
Validation
```

It also distinguishes between statuses such as:

- Required;
- Planned;
- In Progress;
- Implemented;
- Validated;
- Bonus;
- Open.

**Look here for:** proof that a particular school requirement has been considered and where it is addressed.

**Status:** Work in Progress.

---

### `threat-model.md`

**Purpose:** Identify the security threats that are relevant to the project before selecting countermeasures.

This document is intended to analyse areas such as:

- C2 server exposure;
- agent exposure;
- communication threats;
- authentication;
- message manipulation;
- unauthorized task execution;
- session abuse;
- file-transfer abuse;
- storage exposure;
- secrets and configuration;
- logging and information leakage;
- local compromise.

It should answer:

> What can go wrong?

and:

> What assets or components are affected?

The threat model provides the foundation for the dedicated countermeasure analysis.

**Look here for:** threats, attack surfaces, affected assets, and security risks.

**Status:** Planned.

---

### `network-architecture.md`

**Purpose:** Describe the network-level architecture of the project.

This document will complement `ARCHITECTURE.md` by focusing specifically on communication paths and network relationships.

It is intended to document:

- C2 server;
- agents;
- operator interface;
- communication channels;
- transport;
- TLS boundary;
- logical network zones;
- connection direction;
- relevant trust boundaries;
- network diagrams;
- laboratory deployment assumptions.

A simplified conceptual model is:

```text
              Operator
                  │
                  ▼
          ┌───────────────┐
          │   C2 Server   │
          └───────┬───────┘
                  │
          Secure Transport
                  │
        ┌─────────┼─────────┐
        ▼         ▼         ▼
     Agent 1   Agent 2   Agent N
```

**Look here for:** network topology and communication paths.

**Status:** Planned.

---

### `kill-chain-analysis.md`

**Purpose:** Analyse the project through the Cyber Kill Chain perspective.

This document will map the relevant phases of the model to the capabilities and behaviours represented by the project.

The objective is not to claim that the project implements every phase, but to identify:

- which phases are represented;
- which capabilities support them;
- which phases are outside the project scope;
- what defensive observations or controls are relevant.

This analysis will provide a bridge between the technical architecture and the security analysis requested for the project.

**Look here for:** Kill Chain mapping and analysis of project capabilities from that perspective.

**Status:** Planned.

---

### `countermeasures.md`

**Purpose:** Document the security controls used to reduce the threats identified in the threat model and Kill Chain analysis.

This document will connect:

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

It is intended to cover controls such as:

- TLS;
- authentication;
- message validation;
- input validation;
- path validation;
- controlled file workspaces;
- file integrity verification;
- access restrictions;
- logging;
- error handling;
- secret management;
- testing and monitoring.

This document is deliberately separate from `SECURITY.md`:

- `SECURITY.md` defines the project's general security principles and boundaries.
- `countermeasures.md` will provide the more detailed threat-to-control analysis.

**Look here for:** how identified risks are mitigated.

**Status:** Planned.

---

## Where should I look?

When looking for a specific type of information, use the following guide.

| Question | Document |
|---|---|
| How do C2 and Agent exchange messages? | [`protocol.md`](protocol.md) |
| What does a protocol message contain? | [`protocol.md`](protocol.md) |
| How does a task progress? | [`task-lifecycle.md`](task-lifecycle.md) |
| How are tasks associated with results? | [`task-lifecycle.md`](task-lifecycle.md) / [`data-model.md`](data-model.md) |
| How are files transferred? | [`file-transfer.md`](file-transfer.md) |
| Where are transferred files stored? | [`file-transfer.md`](file-transfer.md) |
| What entities exist in the system? | [`data-model.md`](data-model.md) |
| How are entities related? | [`data-model.md`](data-model.md) |
| How should a feature be tested? | [`testing-strategy.md`](testing-strategy.md) |
| How is a school requirement addressed? | [`requirements-mapping.md`](requirements-mapping.md) |
| What are the project threats? | [`threat-model.md`](threat-model.md) |
| What does the network look like? | [`network-architecture.md`](network-architecture.md) |
| How does the project map to the Kill Chain? | [`kill-chain-analysis.md`](kill-chain-analysis.md) |
| How are identified threats mitigated? | [`countermeasures.md`](countermeasures.md) |

---

## Relationship between the documents

The documents are complementary rather than independent.

A typical feature can therefore be understood through several documents.

For example, file transfer can be followed through:

```text
Architecture
    ↓
How the capability fits into the system
    ↓
Protocol
    ↓
Which messages are exchanged
    ↓
File Transfer
    ↓
How the transfer itself works
    ↓
Data Model
    ↓
What information is stored
    ↓
Security / Threat Model
    ↓
What can go wrong
    ↓
Countermeasures
    ↓
How the risks are reduced
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

## When to update the documentation

Documentation should be updated when a change affects:

- architecture or module responsibilities;
- communication or protocol behavior;
- task or file-transfer workflows;
- persistent data or domain entities;
- security controls or threat assumptions;
- network topology;
- testing strategy;
- project requirements.

The documentation should be updated as part of the same change rather than reconstructed at the end of the project.

When a change represents a significant architectural choice, the corresponding decision should also be recorded in [`../DECISIONS.md`](../DECISIONS.md).

---

## Root-level documentation

Some documentation deliberately remains outside this directory because it describes the project at a broader level.

### [`../README.md`](../README.md)

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

It should remain relatively concise and direct readers here for detailed technical documentation.

---

### [`../ARCHITECTURE.md`](../ARCHITECTURE.md)

The global architectural baseline.

It describes:

- C2 and Agent architecture;
- major modules;
- responsibilities;
- boundaries;
- protocol/transport separation;
- storage architecture;
- communication flows;
- extensibility;
- repository mapping.

Detailed specifications are intentionally kept in the corresponding files under `docs/`.

---

### [`../SECURITY.md`](../SECURITY.md)

The project's global security baseline.

It defines:

- security principles;
- secure communication;
- protocol security;
- execution boundaries;
- file-transfer security;
- integrity;
- storage restrictions;
- logging;
- secrets/configuration;
- laboratory scope.

Detailed threat and countermeasure analysis will be documented separately in `threat-model.md` and `countermeasures.md`.

---

### [`../DECISIONS.md`](../DECISIONS.md)

The project's decision history.

It records important architectural choices and unresolved decisions using:

- `ADR-*` for accepted architectural decisions;
- `PRO-*` for proposed decisions that remain open.

This prevents important design choices from disappearing into discussions or undocumented implementation changes.

**Look here for:** why the architecture was designed this way.

---

### [`../CONTRIBUTING.md`](../CONTRIBUTING.md)

The project's development and contribution rules.

It describes:

- branching strategy;
- when to use `feature/`, `fix/`, `docs/`, `test/`, and `refactor/`;
- pull requests;
- validation before merge;
- documentation consistency;
- security-sensitive changes;
- repository hygiene.

**Look here for:** how changes should be made to the repository.

---

## Common terms

| Term | Meaning |
|---|---|
| **C2** | Command and Control server responsible for managing agents and tasks. |
| **Agent** | Client-side component that communicates with the C2 and executes authorized tasks. |
| **Task** | An instruction created by the C2 for an agent to process. |
| **Result** | Data returned by an agent in response to a task. |
| **Session** | A communication context between an agent and the C2. |
| **Beacon** | Agent communication mechanism used to indicate availability and exchange pending information. |
| **Transfer** | A logical file-transfer operation between the C2 and an agent. |
| **ADR** | Accepted Architecture Decision Record. |
| **PRO** | Proposed decision that has not yet been finalized. |

---

## Documentation status

Documentation is developed alongside the project rather than being postponed until the end.

Current status:

| Document | Status |
|---|---|
| `protocol.md` | Work in Progress |
| `task-lifecycle.md` | Work in Progress |
| `file-transfer.md` | Work in Progress |
| `data-model.md` | Work in Progress |
| `testing-strategy.md` | Work in Progress |
| `requirements-mapping.md` | Work in Progress |
| `threat-model.md` | Planned |
| `network-architecture.md` | Planned |
| `kill-chain-analysis.md` | Planned |
| `countermeasures.md` | Planned |

A document marked **Work in Progress** may contain intentionally unresolved design points. These should not be interpreted as finalized implementation decisions.

Architectural choices that remain open should be recorded in [`../DECISIONS.md`](../DECISIONS.md) rather than silently decided during implementation.

---

## Documentation principles

The documentation follows a few simple principles:

1. **One subject, one primary document.**  
   Information should have a clear home.

2. **Avoid unnecessary duplication.**  
   A document may reference another document instead of reproducing its content.

3. **Separate architecture from detailed specifications.**  
   High-level architecture belongs in `ARCHITECTURE.md`; detailed protocol, task, file-transfer, and testing specifications belong in `docs/`.

4. **Record important decisions.**  
   Open or significant architectural decisions belong in `DECISIONS.md`.

5. **Keep documentation synchronized with implementation.**  
   A significant architecture or behavior change should trigger the corresponding documentation update.

6. **Document uncertainty explicitly.**  
   Proposed behavior should not be presented as finalized behavior.

The goal is therefore not to have a large number of Markdown files. The goal is to make the project's design understandable and traceable from requirements to architecture, implementation, security analysis, and testing.

---

## Navigation summary

For most technical questions, the following path is sufficient:

```text
README.md
   │
   ▼
docs/README.md
   │
   ├── Architecture      → ../ARCHITECTURE.md
   ├── Protocol          → protocol.md
   ├── Tasks             → task-lifecycle.md
   ├── Files             → file-transfer.md
   ├── Data              → data-model.md
   ├── Testing           → testing-strategy.md
   ├── Requirements      → requirements-mapping.md
   ├── Threats           → threat-model.md
   ├── Network           → network-architecture.md
   ├── Kill Chain        → kill-chain-analysis.md
   └── Countermeasures   → countermeasures.md
```

This file should be the first place to look when navigating the detailed project documentation.
