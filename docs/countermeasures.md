# Countermeasures

## 1. Purpose

This document defines the security countermeasures associated with the risks identified in `docs/threat-model.md`.

Its purpose is to connect:

```text
Threat
   ↓
Security requirement
   ↓
Countermeasure
   ↓
Verification / test
```

The document focuses on the protections that are relevant to the architecture and implementation of C2-AUTOMATED.

It does not claim that every threat is completely eliminated. Some risks are reduced through technical controls, while others remain accepted, partially addressed, or outside the project scope.

---

## 2. Relationship with Other Documents

The security documentation is organised as follows:

```text
ARCHITECTURE.md
        │
        ▼
Threat model
        │
        ▼
Security requirements
        │
        ▼
Countermeasures
        │
        ▼
Testing
```

The main references are:

| Document | Purpose |
|---|---|
| `ARCHITECTURE.md` | Defines system structure and component boundaries. |
| `SECURITY.md` | Defines general security principles and security boundaries. |
| `DECISIONS.md` | Records accepted architectural and project decisions. |
| `docs/threat-model.md` | Identifies threats and their priorities. |
| `docs/countermeasures.md` | Defines the corresponding protections. |
| `docs/testing-strategy.md` | Defines how those protections are verified. |
| `docs/requirements-mapping.md` | Tracks requirements through implementation and validation. |

---

## 3. Security Objectives

The countermeasures are designed around the following objectives:

1. Protect communications between the C2 server and agents.
2. Prevent malformed or unexpected protocol messages from being accepted blindly.
3. Preserve the integrity of task and result handling.
4. Prevent uncontrolled filesystem access.
5. Limit the impact of endpoint command execution.
6. Protect persisted project data.
7. Provide sufficient logging for security-relevant events.
8. Prevent accidental or uncontrolled lifecycle operations.
9. Maintain clear security boundaries between the major components.

---

## 4. Countermeasure Status

The following status values are used in this document.

| Status | Meaning |
|---|---|
| **Planned** | Countermeasure is part of the design but is not yet implemented. |
| **Partially addressed** | Some protection exists, but the complete control is not yet implemented or verified. |
| **Implemented** | Countermeasure is implemented in the project. |
| **Validated** | Countermeasure has been implemented and verified through testing. |
| **Accepted** | The remaining risk is consciously accepted within the project scope. |
| **Out of scope** | The risk or control is not addressed by this project. |

Implementation and validation status should ultimately be synchronized with `docs/requirements-mapping.md`.

---

# 5. Countermeasure Matrix

| ID | Threat / Security area | Countermeasure | Status |
|---|---|---|---|
| `CM-001` | Network interception | Use TLS for C2 communication. | Planned / implementation-tracked |
| `CM-002` | Weak transport configuration | Centralize and validate TLS configuration. | Planned |
| `CM-003` | Malformed protocol messages | Validate message structure before processing. | Planned |
| `CM-004` | Unsupported protocol messages | Explicitly validate message types and protocol versions. | Planned |
| `CM-005` | Message/task confusion | Use explicit correlation identifiers. | Planned |
| `CM-006` | Unauthorized or invalid task data | Validate task fields and command parameters before execution. | Planned |
| `CM-007` | Unsafe command execution | Keep command dispatch behind the executor layer. | Planned |
| `CM-008` | Uncontrolled filesystem access | Restrict file operations to controlled project workspaces. | Planned |
| `CM-009` | Path traversal | Validate and normalize file paths before filesystem operations. | Planned |
| `CM-010` | File integrity errors | Use transfer metadata and integrity verification. | Planned |
| `CM-011` | Large-file resource exhaustion | Process transfers incrementally rather than loading complete files into memory. | Planned |
| `CM-012` | Temporary-file leakage | Use dedicated temporary storage and clean up incomplete transfers. | Planned |
| `CM-013` | Database integrity problems | Access SQLite through the storage abstraction. | Planned |
| `CM-014` | Sensitive data exposure in logs | Avoid logging secrets and unnecessary sensitive values. | Planned |
| `CM-015` | Operational traceability | Log security-relevant connection, task, result, and error events. | Planned |
| `CM-016` | Configuration/secrets exposure | Keep secrets outside source code and centralize configuration. | Planned |
| `CM-017` | Persistence abuse | Restrict `PERSISTENCE` to the explicitly defined laboratory behaviour. | Open |
| `CM-018` | Uncontrolled self-destruction | Bound `SELF_DESTRUCT` to an explicitly defined and controlled scope. | Open |
| `CM-019` | Multi-agent state confusion | Keep agent identity separate from communication session state. | Planned |
| `CM-020` | Asynchronous task inconsistency | Persist task states and maintain explicit task/result relationships. | Planned |
| `CM-021` | Security regression | Maintain security-focused unit, integration, and end-to-end tests. | Planned |
| `CM-022` | Unauthorized deployment | Restrict project use to explicitly authorized laboratory environments. | Accepted / scope control |

---

# 6. Communication Security

## 6.1 TLS

The mandatory communication mechanism is TCP/TLS.

TLS is used to protect communications in transit between the C2 server and the agent.

```text
C2 Server
    │
    │ encrypted transport
    ▼
   TLS
    │
    ▼
  Agent
```

This addresses risks associated with interception or modification of network traffic.

### Countermeasure

`CM-001`

The transport implementation must use TLS rather than transmitting application data directly over unencrypted TCP.

### Verification

Tests should verify that:

- the transport establishes a TLS connection;
- plaintext communication is not accepted by the configured secure endpoint;
- certificate or TLS configuration errors are handled correctly;
- communication failures do not silently downgrade to plaintext.

---

## 6.2 Protocol and Transport Separation

The application protocol is deliberately separated from the transport layer.

This means that the logical message structure does not depend directly on socket implementation details.

```text
Protocol
    │
    ▼
Transport
    │
    ▼
Network
```

This separation also prevents protocol validation from being bypassed simply because a different transport is introduced later.

### Countermeasures

`CM-002`, `CM-003`, `CM-004`

### Verification

Tests should validate the protocol independently from the transport implementation.

---

# 7. Protocol Security

## 7.1 Message Validation

All messages received from an agent must be treated as untrusted input.

The transport layer does not establish that a message is valid.

Messages must therefore be validated before reaching business logic.

```text
Incoming message
       │
       ▼
Deserializer
       │
       ▼
Validator
       │
   valid?
   /    \
 yes     no
 │       │
 ▼       ▼
Core    ERROR
```

### Countermeasure

`CM-003`

Validation should include, where applicable:

- protocol version;
- message type;
- required fields;
- field types;
- identifier format;
- timestamp or sequencing constraints;
- payload structure.

---

## 7.2 Explicit Message Types

The protocol uses explicit message types such as:

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

Unsupported message types must not be silently interpreted as another operation.

### Countermeasure

`CM-004`

### Verification

Tests should include:

- unknown message type;
- missing required fields;
- incorrect field type;
- invalid version;
- malformed payload.

The expected behaviour is rejection with an appropriate error rather than execution.

---

## 7.3 Message and Task Correlation

Tasks, results, and file transfers require explicit identifiers so that asynchronous communication does not cause responses to be associated with the wrong operation.

### Countermeasure

`CM-005`

Relevant identifiers include conceptual:

```text
agent_id
session_id
task_id
result_id
transfer_id
message_id
```

The exact persistence model is defined separately in the data model and protocol documentation.

### Verification

Tests should verify that:

- a result references the correct task;
- a task belongs to the correct agent;
- a file-transfer message belongs to the correct transfer;
- unrelated agents cannot accidentally share task state.

---

# 8. Task and Command Execution Security

## 8.1 Validation Before Execution

Tasks received from the C2 must not be passed directly to an operating-system command interpreter.

The intended flow is:

```text
TASK
 ↓
Protocol validation
 ↓
Task handling
 ↓
Executor
 ↓
Command implementation
 ↓
Execution
```

### Countermeasures

`CM-006`, `CM-007`

The executor is the boundary between the task model and endpoint execution.

### Verification

Tests should verify:

- unsupported commands are rejected;
- missing parameters are rejected;
- invalid parameter types are rejected;
- malformed tasks never reach command execution;
- execution errors are returned as controlled results.

---

## 8.2 Command Separation

Supported operations remain explicit:

```text
SHELL
SYSINFO
FILES
PERSISTENCE
SELF_DESTRUCT
```

The project does not use a single uncontrolled handler containing every operation.

This separation makes command-specific validation and testing possible.

---

# 9. File Handling Security

## 9.1 Controlled File Workspaces

File operations are restricted to dedicated project-controlled directories.

The server and agent use:

```text
data/
└── files/
    ├── uploads/
    ├── downloads/
    └── temporary/
```

The logical `FileManager` remains separate from the physical filesystem implementation.

### Countermeasure

`CM-008`

This reduces the risk that a file operation accidentally targets arbitrary filesystem locations.

---

## 9.2 Path Validation

User- or agent-provided paths must not be trusted directly.

Path handling should:

1. normalize the supplied path;
2. resolve the resulting path;
3. verify that it remains inside the allowed workspace;
4. reject paths escaping the workspace.

### Countermeasure

`CM-009`

Conceptually:

```text
Requested path
      ↓
Normalize
      ↓
Resolve
      ↓
Allowed workspace?
   /          \
 yes           no
  │             │
  ▼             ▼
Allow         Reject
```

### Verification

Tests should cover:

- normal relative paths;
- absolute paths;
- parent traversal such as `../`;
- nested traversal;
- symbolic-link edge cases where relevant;
- paths outside the controlled workspace.

---

## 9.3 Integrity Verification

File transfers should include enough metadata to verify that the received file corresponds to the intended transfer.

A cryptographic hash such as SHA-256 can be used as an integrity value.

### Countermeasure

`CM-010`

The transfer model is:

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
Integrity verification
     ↓
Promotion to final location
```

---

## 9.4 Incremental Processing

Files should not be loaded entirely into memory for transfer.

The project instead uses incremental chunks.

### Countermeasure

`CM-011`

This reduces memory pressure for larger files.

### Verification

Tests should include files of different sizes and verify that:

- transfers complete correctly;
- chunk order is handled correctly;
- incomplete transfers remain temporary;
- transfer state survives expected communication interruptions.

---

## 9.5 Temporary Storage

Incomplete or reconstructed files should remain in the temporary workspace until the transfer has been successfully validated.

Only after successful completion should the data be promoted to its final location.

### Countermeasure

`CM-012`

This prevents partially received files from being treated as complete.

---

# 10. Persistence and Storage Security

## 10.1 Database Abstraction

SQLite is the selected MVP persistence backend.

Application components should access the database through the storage abstraction rather than embedding SQL logic throughout the system.

### Countermeasure

`CM-013`

The intended structure is:

```text
Core
 │
 ▼
Storage Interface
 │
 ▼
SQLite
```

### Benefits

This reduces coupling and creates a clear location for future storage-related security controls.

---

## 10.2 Persistent Metadata

Persisted information should be limited to information required by the project, such as:

- agents;
- sessions;
- tasks;
- results;
- relevant transfer metadata.

The project should avoid storing sensitive information unnecessarily.

---

# 11. Logging and Traceability

## 11.1 Centralized Logging

Security-relevant events should be logged consistently.

Examples include:

```text
agent connection
agent disconnection
task creation
task dispatch
task failure
result reception
file transfer failure
protocol validation failure
transport error
```

### Countermeasure

`CM-015`

Logging is kept separate from core business logic.

---

## 11.2 Sensitive Information

Logs should not contain:

- credentials;
- private keys;
- secrets;
- unnecessary file contents;
- sensitive configuration values.

### Countermeasure

`CM-014`

The goal is to make logs useful for debugging and audit without creating a secondary source of sensitive-data exposure.

---

# 12. Configuration and Secret Management

Configuration is centralized rather than distributed throughout individual modules.

Secrets should not be hard-coded into source files or committed to the repository.

### Countermeasure

`CM-016`

The expected configuration model separates:

```text
Application configuration
        +
Secrets
        +
Environment-specific values
```

from source code.

### Verification

Repository checks should verify that:

- test secrets are not committed accidentally;
- configuration loading fails safely when mandatory secrets are missing;
- secrets are not printed through normal logs.

---

# 13. Agent and Session Security

The architecture distinguishes between:

```text
Agent identity
      ≠
Communication session
```

An agent may reconnect and therefore create a new session without becoming a completely new logical agent.

### Countermeasure

`CM-019`

This prevents state confusion between:

- persistent agent identity;
- current communication state;
- task ownership.

### Verification

Tests should cover:

```text
Agent A001
   ↓
Session S001
   ↓
disconnect
   ↓
Session S002
```

while preserving the same agent identity.

---

# 14. Asynchronous Task Security

Because the project supports asynchronous task handling, tasks may remain pending while an agent is unavailable.

The task lifecycle is explicitly tracked:

```text
PENDING
   ↓
SENT
   ↓
RUNNING
   ↓
COMPLETED
```

with a failure path:

```text
RUNNING
   ↓
FAILED
```

### Countermeasure

`CM-020`

The server must retain enough task metadata to prevent:

- accidental task duplication;
- result association with the wrong task;
- loss of task state after temporary disconnection.

### Verification

Tests should simulate:

- offline agent;
- reconnecting agent;
- multiple pending tasks;
- delayed result;
- failed execution;
- multiple agents executing tasks simultaneously.

---

# 15. Persistence Security

`PERSISTENCE` is a required capability but its exact implementation scope remains open.

### Countermeasure

`CM-017`

Before implementation is considered complete, the following must be explicitly defined:

- supported persistence mechanism;
- required permissions;
- installation behaviour;
- removal behaviour;
- platform-specific differences;
- cleanup responsibilities.

The implementation must remain within the project's authorized laboratory scope.

The architecture must not treat “persistence” as permission to introduce arbitrary persistence mechanisms without a defined project requirement.

---

# 16. Self-Destruct Security

`SELF_DESTRUCT` is also a required capability whose exact behaviour is currently open.

This is tracked through `PRO-006`.

### Countermeasure

`CM-018`

The final implementation must define a bounded lifecycle operation rather than unrestricted deletion.

Possible scopes previously identified are:

```text
A. Process termination only

B. Process termination
   + temporary cleanup

C. Process termination
   + project workspace cleanup

D. Full agent removal
   + persistence cleanup
```

One scope must be selected before implementation is considered fully defined.

### Security requirement

The behaviour should be:

- explicit;
- bounded;
- predictable;
- testable;
- restricted to the intended project resources.

---

# 17. Laboratory Scope as a Security Control

C2-AUTOMATED is intended for authorized laboratory use.

The project must not be presented as a system intended for deployment against third-party environments.

### Countermeasure

`CM-022`

The authorization boundary itself is part of the project's risk control model.

Testing should therefore be performed using:

```text
Owned systems
      or
Authorized laboratory systems
      or
Isolated virtual machines
      or
Institution-provided exercises
```

This does not replace technical controls, but it limits the operational environment in which the project is intended to be used.

---

# 18. Security Testing

Countermeasures are not considered reliable merely because the corresponding code exists.

They must be tested.

The testing strategy is therefore linked directly to the countermeasure catalogue.

### Example traceability

| Countermeasure | Main test area |
|---|---|
| `CM-001` TLS | Transport / integration tests |
| `CM-003` Protocol validation | Protocol unit tests |
| `CM-005` Correlation | Protocol / integration tests |
| `CM-008` Controlled file workspace | File-storage tests |
| `CM-009` Path validation | Security-focused filesystem tests |
| `CM-010` Integrity | File-transfer integration tests |
| `CM-011` Chunking | File-transfer tests |
| `CM-015` Logging | Logging tests |
| `CM-019` Agent/session separation | Session integration tests |
| `CM-020` Async task handling | Multi-agent integration tests |
| `CM-017` Persistence | Command/security tests |
| `CM-018` Self-destruct | Lifecycle/security tests |

Detailed test organisation remains defined in `docs/testing-strategy.md`.

---

# 19. Countermeasure Priorities

The security controls should be implemented according to risk and dependency.

## Priority 1 — Fundamental protections

These should exist before relying on the system for normal operation:

```text
TLS
Protocol validation
Task validation
Controlled file paths
Secure file transfer handling
Basic logging
Configuration/secret separation
```

## Priority 2 — Robustness protections

These support reliable operation:

```text
Task correlation
Agent/session separation
Asynchronous state management
Temporary-file handling
Integrity verification
Multi-agent isolation
```

## Priority 3 — Open capability-specific controls

These depend on the final design of:

```text
PERSISTENCE
SELF_DESTRUCT
```

Their countermeasures cannot be considered complete until the underlying behaviour has been explicitly defined.

---

# 20. Security Residual Risk

Security controls reduce risk but do not eliminate it completely.

Examples of residual risk include:

- compromise of the host running the C2 server;
- compromise of the laboratory endpoint;
- incorrect configuration;
- implementation bugs;
- weaknesses in underlying operating systems or libraries;
- abuse of a legitimate project capability by an authorized operator.

These residual risks should be documented rather than implicitly considered solved.

---

# 21. Traceability Summary

The intended security traceability chain is:

```text
Threat Model
    │
    ├── TM-001
    ├── TM-002
    ├── ...
    └── TM-023
          │
          ▼
Security Requirements
    │
    ├── SR-001
    ├── SR-002
    ├── ...
    └── SR-012
          │
          ▼
Countermeasures
    │
    ├── CM-001
    ├── CM-002
    ├── ...
    └── CM-022
          │
          ▼
Implementation
          │
          ▼
Testing
```

This creates a consistent link between the identified risk, the intended protection, and its validation.

---

# 22. Final Security Position

C2-AUTOMATED should not be considered secure simply because it uses TLS or because the architecture is modular.

Security depends on the combination of:

```text
Secure transport
        +
Protocol validation
        +
Controlled task execution
        +
Controlled filesystem access
        +
Integrity verification
        +
Persistent-state protection
        +
Logging
        +
Testing
        +
Explicit laboratory scope
```

The project therefore treats security as a property of the **complete system**, rather than a feature provided by a single component.

The most important principle is:

> **Every capability that introduces a new attack surface must have a corresponding security control and a means of verification.**
