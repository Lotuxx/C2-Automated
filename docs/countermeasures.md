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
Implementation
   ↓
Verification / test
```

The document focuses on protections that are relevant to the architecture and implementation of C2-AUTOMATED.

It does not claim that every threat is completely eliminated. Some risks are reduced through technical controls, while others remain accepted, partially addressed, open, or outside the project scope.

The countermeasures described here are intended to remain consistent with:

- `ARCHITECTURE.md`
- `DECISIONS.md`
- `docs/data-model.md`
- `docs/state-machines.md`
- `docs/protocol.md`
- `docs/protocol-state-transition.md`
- `docs/reconnection-and-synchronization.md`
- `docs/task-lifecycle.md`
- `docs/file-transfer.md`
- `docs/network-architecture.md`
- `docs/testing-strategy.md`
- `docs/requirements-mapping.md`

---

# 2. Relationship with Other Documents

The security documentation is organised as follows:

```text
Architecture
     │
     ▼
Threat Model
     │
     ▼
Security Requirements
     │
     ▼
Countermeasures
     │
     ▼
Implementation
     │
     ▼
Testing
```

| Document | Purpose |
|---|---|
| `ARCHITECTURE.md` | Defines system structure and component boundaries. |
| `DECISIONS.md` | Records accepted architectural and project decisions. |
| `docs/threat-model.md` | Identifies threats and their priorities. |
| `docs/countermeasures.md` | Defines the corresponding protections. |
| `docs/state-machines.md` | Defines authoritative system state machines. |
| `docs/protocol.md` | Defines protocol messages and their structure. |
| `docs/task-lifecycle.md` | Defines task lifecycle and recovery behaviour. |
| `docs/file-transfer.md` | Defines file-transfer behaviour and security properties. |
| `docs/network-architecture.md` | Defines network boundaries and transport architecture. |
| `docs/testing-strategy.md` | Defines how protections are verified. |
| `docs/requirements-mapping.md` | Tracks requirements through implementation and validation. |

Security documentation must describe the actual project design rather than presenting future capabilities as already implemented.

---

# 3. Security Objectives

The countermeasures are designed around the following objectives:

1. Protect communications between the C2 server and agents.
2. Treat all received protocol data as untrusted input.
3. Prevent malformed or unsupported protocol messages from reaching business logic.
4. Preserve the integrity of task, result, and transfer relationships.
5. Prevent uncontrolled filesystem access.
6. Keep command execution behind explicit validation and execution boundaries.
7. Protect persisted project data and avoid unnecessary sensitive-data storage.
8. Provide sufficient logging for security-relevant events.
9. Prevent uncontrolled lifecycle operations.
10. Maintain clear security boundaries between major components.
11. Preserve state consistency across disconnections and reconnections.
12. Restrict the system to explicitly authorized laboratory environments.

---

# 4. Countermeasure Status

The following status values are used in this document.

| Status | Meaning |
|---|---|
| **Planned** | Countermeasure is part of the design but is not yet implemented. |
| **Partially addressed** | Some protection exists, but the complete control is not yet implemented or verified. |
| **Implemented** | Countermeasure is implemented in the project. |
| **Validated** | Countermeasure has been implemented and verified through testing. |
| **Accepted** | The remaining risk is consciously accepted within the project scope. |
| **Open** | The required behaviour or security mechanism has not yet been sufficiently defined. |
| **Out of scope** | The risk or control is not addressed by this project. |

Implementation and validation status should ultimately be synchronized with `docs/requirements-mapping.md`.

---

# 5. Countermeasure Matrix

| ID | Threat / Security area | Countermeasure | Status |
|---|---|---|---|
| `CM-001` | Network interception | Use TLS for C2 communication. | Planned |
| `CM-002` | Weak transport configuration | Centralize and validate TLS configuration. | Planned |
| `CM-003` | Malformed protocol messages | Validate message structure before processing. | Planned |
| `CM-004` | Unsupported protocol messages | Explicitly validate message types and protocol versions. | Planned |
| `CM-005` | Message/task confusion | Use explicit correlation identifiers. | Planned |
| `CM-006` | Invalid task data | Validate task fields and command parameters before execution. | Planned |
| `CM-007` | Unsafe command execution | Keep command dispatch behind the Executor and explicit command layer. | Planned |
| `CM-008` | Uncontrolled filesystem access | Restrict file operations to controlled project workspaces. | Planned |
| `CM-009` | Path traversal | Normalize and validate paths before filesystem operations. | Planned |
| `CM-010` | File integrity errors | Use transfer metadata and cryptographic integrity verification. | Planned |
| `CM-011` | Large-file resource exhaustion | Process transfers incrementally rather than loading complete files into memory. | Planned |
| `CM-012` | Temporary-file leakage | Use dedicated temporary storage and clean up incomplete transfers. | Planned |
| `CM-013` | Database integrity / access problems | Access persistent data through the storage abstraction and controlled database operations. | Planned |
| `CM-014` | Sensitive data exposure in logs | Avoid logging secrets and unnecessary sensitive values. | Planned |
| `CM-015` | Operational traceability | Log security-relevant connection, task, result, transfer, and error events. | Planned |
| `CM-016` | Configuration/secrets exposure | Centralize configuration and keep secrets outside source code. | Planned |
| `CM-017` | Persistence abuse | Restrict `PERSISTENCE` to explicitly defined laboratory behaviour. | Open |
| `CM-018` | Uncontrolled self-destruction | Bound `SELF_DESTRUCT` to an explicitly defined and controlled scope. | Open |
| `CM-019` | Multi-agent state confusion | Keep Agent identity separate from communication Session state. | Planned |
| `CM-020` | Asynchronous task inconsistency | Persist task state and maintain explicit Task/Result relationships. | Planned |
| `CM-021` | Security regression | Maintain security-focused unit, integration, and end-to-end tests. | Planned |
| `CM-022` | Unauthorized deployment | Restrict project use to explicitly authorized laboratory environments. | Accepted / scope control |
| `CM-023` | Agent identity / authentication uncertainty | Define and implement the mechanism used to establish trust in an Agent connection. | Open |

---

# 6. Communication Security

## 6.1 TLS

The mandatory MVP communication mechanism is TCP/TLS.

TLS protects communications in transit between the C2 server and the Agent.

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

This addresses risks associated with interception and modification of network traffic.

### Countermeasure

`CM-001`

The transport implementation must use TLS rather than transmitting application data directly over unencrypted TCP.

File-transfer traffic uses the same protected transport. A separate application-level encryption mechanism for files is not mandatory for the MVP.

### Verification

Tests should verify that:

- the transport establishes a TLS connection;
- the secure endpoint does not accept unintended plaintext communication;
- TLS configuration or certificate errors are handled correctly;
- communication does not silently downgrade to plaintext;
- file-transfer messages are transmitted through the protected transport.

---

## 6.2 TLS Configuration

TLS configuration must be centralized rather than duplicated across individual components.

### Countermeasure

`CM-002`

The configuration layer should define the parameters required by the transport implementation.

Security-sensitive configuration must not be scattered throughout application code.

### Verification

Tests should verify that:

- invalid TLS configuration is rejected;
- missing mandatory configuration is handled safely;
- certificates and private material are not accidentally logged;
- transport configuration is loaded consistently.

The exact certificate and authentication model remains an implementation decision tracked separately.

---

# 7. Protocol Security

## 7.1 Message Validation

All messages received from an Agent must be treated as untrusted input.

The transport layer only establishes communication. It does not establish that a received message is valid.

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
- payload structure;
- values within permitted ranges;
- message-specific constraints.

Malformed input must not be allowed to reach command execution or state-management logic.

---

## 7.2 Explicit Message Types

The protocol uses explicit message types such as:

```text
REGISTER
REGISTER_ACK
BEACON
BEACON_ACK
TASK
TASK_ACK
TASK_STATUS
TASK_STATUS_QUERY
RESULT
PING
PONG
SYNC_STATE
SYNC_STATE_RESPONSE
SYNC_COMPLETE
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
- invalid protocol version;
- malformed payload;
- unexpected message in a given protocol context.

The expected behaviour is controlled rejection rather than unintended execution.

---

## 7.3 Message and Task Correlation

Asynchronous communication requires explicit identifiers so that responses cannot be accidentally associated with the wrong operation.

Relevant identifiers include:

```text
agent_id
session_id
task_id
result_id
transfer_id
message_id
```

These identifiers have different responsibilities and must not be substituted for one another.

### Countermeasure

`CM-005`

Examples:

```text
Task
  └── task_id
       └── Result
            └── result_id

File Transfer
  └── transfer_id

Communication episode
  └── session_id

Logical endpoint identity
  └── agent_id
```

### Verification

Tests should verify that:

- a Result references the correct Task;
- a Task belongs to the correct Agent;
- a transfer message references the correct Transfer;
- messages received through one Session cannot accidentally modify another Agent's state;
- duplicate identifiers are handled according to protocol rules.

---

# 8. Agent Identity and Authentication

The architecture distinguishes:

```text
Agent identity
      ≠
Communication Session
```

An Agent may reconnect and therefore create a new Session without becoming a new logical Agent.

However, persistent Agent identity does not by itself constitute a complete authentication mechanism.

### Countermeasure

`CM-023`

The exact mechanism by which the C2 establishes trust in an Agent remains an open security decision.

The project must distinguish between:

```text
Identification
    =
"Which Agent claims to be communicating?"

Authentication
    =
"Why should the C2 trust that claim?"
```

This distinction is important because `REGISTER` currently identifies an Agent over an already-established transport connection.

The final authentication mechanism must be explicitly defined before the security model can be considered complete.

### Verification

Tests should eventually cover:

- valid Agent registration;
- invalid or incomplete identity data;
- duplicate or conflicting identity claims;
- rejected authentication material where applicable;
- reconnection using an established Agent identity.

---

# 9. Task and Command Execution Security

## 9.1 Validation Before Execution

Tasks received from the C2 must not be passed directly to an uncontrolled operating-system command interpreter.

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
 ↓
Result
```

### Countermeasures

`CM-006`, `CM-007`

The Executor is the boundary between the Task model and endpoint command execution.

Command-specific implementations remain behind the command layer.

### Verification

Tests should verify that:

- unsupported commands are rejected;
- missing parameters are rejected;
- invalid parameter types are rejected;
- malformed Tasks never reach command execution;
- execution errors become controlled Results;
- command handlers cannot bypass Task validation.

---

## 9.2 Explicit Command Separation

The supported command categories are explicitly separated:

```text
SHELL
SYSINFO
FILES
PERSISTENCE
SELF_DESTRUCT
```

The project does not rely on one unrestricted handler containing every operation.

This separation allows each capability to have:

- its own validation;
- its own implementation;
- its own platform handling;
- its own security tests.

The exact implementation of `PERSISTENCE` and `SELF_DESTRUCT` remains open and is therefore subject to additional security constraints described below.

---

# 10. File Handling Security

## 10.1 Controlled File Workspaces

File operations are restricted to dedicated project-controlled directories.

The C2 and Agent use controlled file areas such as:

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

This reduces the risk that a transfer or file operation accidentally targets an arbitrary filesystem location.

The storage interface provides the boundary between logical file operations and physical filesystem access.

---

## 10.2 Path Validation

Agent- or operator-provided paths must not be trusted directly.

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

## 10.3 File Transfer Integrity

File transfers use explicit transfer identifiers and metadata.

A cryptographic hash such as SHA-256 may be used to verify the integrity of a reconstructed file.

### Countermeasure

`CM-010`

Conceptually:

```text
Original file
     │
     ▼
Cryptographic hash
     │
     ▼
FILE_START
     │
     ▼
FILE_CHUNK
     │
     ▼
...
     │
     ▼
FILE_END
     │
     ▼
Reconstructed file
     │
     ▼
Hash verification
     │
 ┌───┴────┐
 │        │
match   mismatch
 │        │
 ▼        ▼
valid    reject
```

This provides a distinction between:

```text
TLS
→ confidentiality and transport-level integrity

File hash
→ end-to-end integrity verification of the transferred artifact
```

Application-level encryption of the stored file is not mandatory for the MVP.

---

## 10.4 Incremental Processing

Files must not need to exist as complete in-memory objects during transfer.

The transfer mechanism processes data incrementally:

```text
chunk
  ↓
write/process
  ↓
chunk
  ↓
write/process
  ↓
chunk
  ↓
...
```

### Countermeasure

`CM-011`

This reduces memory pressure and makes the file-transfer subsystem more suitable for larger files.

### Verification

Tests should include files of different sizes and verify that:

- transfers complete correctly;
- chunks are processed according to the transfer contract;
- incomplete transfers remain incomplete;
- large transfers do not require loading the entire file into memory.

The exact chunk sizing, ordering, and resumability rules remain implementation details defined by `docs/file-transfer.md`.

---

## 10.5 Temporary Storage

Incomplete or reconstructed files remain in temporary storage until the transfer has successfully completed its validation process.

Only after successful completion should the data be promoted to its final location.

### Countermeasure

`CM-012`

This prevents partially received data from being treated as a completed artifact.

Temporary transfer data should also be cleaned up when a transfer is definitively abandoned or fails according to the transfer lifecycle.

---

# 11. Persistence and Storage Security

## 11.1 Database Abstraction

SQLite is the selected MVP persistence backend.

Application components should access persistent data through the storage abstraction rather than embedding database operations throughout the system.

### Countermeasure

`CM-013`

The intended structure is:

```text
Core
 │
 ▼
Database Interface
 │
 ▼
SQLite
```

This provides a clear boundary for:

- database access;
- transaction handling;
- persistence errors;
- future backend replacement;
- storage-related testing.

---

## 11.2 Persistent Metadata

Persistent information should be limited to information required by the project, such as:

- Agents;
- Sessions;
- Tasks;
- Results;
- File-transfer metadata;
- relevant Events.

The project should avoid storing sensitive information unnecessarily.

The database stores structured metadata, while transferred file contents remain in the filesystem storage layer.

---

## 11.3 C2 Record and Agent Recovery State

The C2 maintains the authoritative historical server-side record required by the project.

The Agent maintains lightweight state necessary for recovery and synchronization.

```text
C2
└── persistent historical record

Agent
└── lightweight recovery state
```

This separation reduces the need for the Agent to maintain a complete copy of server-side history.

It also supports reconciliation after temporary communication loss.

---

# 12. Logging and Traceability

## 12.1 Centralized Logging

Security-relevant events should be logged consistently.

Examples include:

```text
Agent registration
Session establishment
Session disconnection
Session closure
Beacon / acknowledgement
Task creation
Task dispatch
Task acknowledgement
Task execution
Task failure
Result reception
File-transfer events
Protocol validation failure
Transport error
Synchronization events
```

### Countermeasure

`CM-015`

Logging is kept separate from core business logic.

Where appropriate, security-relevant events should also be represented through the project's Event model so that operational history remains distinguishable from raw protocol Messages.

---

## 12.2 Sensitive Information

Logs should not contain:

- credentials;
- private keys;
- secrets;
- unnecessary file contents;
- unnecessary sensitive configuration values.

### Countermeasure

`CM-014`

The objective is to make logs useful for debugging, traceability, and security analysis without creating a secondary source of sensitive-data exposure.

---

# 13. Configuration and Secret Management

Configuration is centralized rather than distributed throughout individual modules.

Secrets must not be hard-coded into source files or committed to the repository.

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

Repository and configuration tests should verify that:

- test secrets are not accidentally committed;
- mandatory security configuration is detected when missing;
- secrets are not printed through normal logging;
- environment-specific values are not embedded in reusable source code.

Local certificates, private keys, databases, logs, and generated transfer files should remain outside source-controlled project files where appropriate.

---

# 14. Agent and Session Security

The architecture distinguishes between:

```text
Agent
 └── persistent logical identity

Session
 └── individual communication episode
```

For example:

```text
Agent A001
   │
   ├── S041
   │
   ├── S042 = DISCONNECTED
   │
   └── S043 = CONNECTED
```

A disconnected Session is not reopened. A new connection creates a new Session.

### Countermeasure

`CM-019`

This prevents state confusion between:

- persistent Agent identity;
- communication history;
- current communication state;
- Task ownership.

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

while preserving the same Agent identity.

They should also verify that an old Session is never incorrectly transitioned back to `CONNECTED`.

---

# 15. Asynchronous Task Security

The project supports asynchronous task handling.

Tasks may remain pending while an Agent is unavailable, and communication loss does not automatically prove that a Task has failed.

The authoritative Task states are:

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
   ↓
COMPLETED / FAILED
```

### Countermeasure

`CM-020`

The C2 maintains the persistent Task lifecycle record, while the Agent provides execution evidence that can be reconciled after communication loss.

This reduces the risk of:

- accidental task duplication;
- incorrect Result association;
- loss of task state after temporary disconnection;
- treating missing communication as proof of execution failure.

### Verification

Tests should simulate:

- Agent unavailable before dispatch;
- missing Task acknowledgement;
- Agent disconnect during execution;
- delayed Result;
- Agent reconnection;
- task recovery;
- multiple pending Tasks;
- multiple Agents executing Tasks simultaneously;
- duplicate Task or Result messages.

---

# 16. Task Recovery and `UNKNOWN`

`UNKNOWN` is not a persistent Task state.

It represents a recovery or reporting condition where the current execution state cannot yet be established reliably.

For example:

```text
C2
 │
 │ Task RUNNING
 ▼
Communication lost
 │
 ▼
Execution state uncertain
 │
 ▼
Recovery / reconciliation
```

The C2 must avoid assuming:

```text
No response
    =
Task failed
```

or:

```text
No response
    =
Task stopped
```

### Security relevance

This prevents incorrect recovery decisions from causing:

- duplicate execution;
- incorrect state transitions;
- incorrect Results;
- inconsistent multi-Agent state.

This behaviour is verified through the task lifecycle and synchronization tests.

---

# 17. Persistence Capability Security

`PERSISTENCE` is a required capability, but its exact implementation scope remains open.

### Countermeasure

`CM-017`

Before implementation is considered complete, the project must explicitly define:

- supported persistence mechanism;
- required permissions;
- installation behaviour;
- removal behaviour;
- platform-specific differences;
- cleanup responsibilities;
- laboratory restrictions.

The implementation must remain within the project's authorized laboratory scope.

The architecture must not interpret the `PERSISTENCE` command as permission to introduce arbitrary persistence mechanisms without a defined project requirement and corresponding security review.

---

# 18. Self-Destruct Capability Security

`SELF_DESTRUCT` is a required capability whose exact behaviour remains open.

This is tracked through `PRO-007` in `DECISIONS.md`.

### Countermeasure

`CM-018`

The final implementation must define a bounded lifecycle operation rather than unrestricted deletion.

The possible conceptual scopes are:

```text
A. Process termination only

B. Process termination
   + temporary cleanup

C. Process termination
   + project workspace cleanup

D. Full project Agent removal
   + associated project cleanup
```

One scope must be explicitly selected before the feature is considered fully defined.

### Security requirement

The behaviour must be:

- explicit;
- bounded;
- predictable;
- testable;
- restricted to intended project resources.

The implementation must not provide unrestricted deletion of arbitrary host resources.

---

# 19. Laboratory Scope as a Security Control

C2-AUTOMATED is an academic project intended for authorized laboratory use.

Development, deployment, and testing must remain restricted to systems and environments for which explicit authorization exists.

### Countermeasure

`CM-022`

The authorization boundary is part of the project's risk-control model.

Testing should therefore be performed using:

```text
Owned systems
      or
Explicitly authorized laboratory systems
      or
Isolated virtual machines
      or
Institution-provided exercises
```

This does not replace technical controls.

It limits the intended operational environment in which the project is developed and evaluated.

The project must not be presented as a system intended for deployment against third-party environments.

---

# 20. Security Testing

Countermeasures are not considered reliable merely because corresponding code exists.

They must be verified through testing.

The testing strategy therefore links directly to this countermeasure catalogue.

### Example traceability

| Countermeasure | Main test area |
|---|---|
| `CM-001` TLS | Transport / integration tests |
| `CM-002` TLS configuration | Transport / configuration tests |
| `CM-003` Protocol validation | Protocol unit tests |
| `CM-004` Message types | Protocol validation tests |
| `CM-005` Correlation | Protocol / integration tests |
| `CM-006` Task validation | Task / command tests |
| `CM-007` Executor boundary | Agent execution tests |
| `CM-008` Controlled file workspace | File-storage tests |
| `CM-009` Path validation | Security-focused filesystem tests |
| `CM-010` File integrity | File-transfer integration tests |
| `CM-011` Chunking | File-transfer tests |
| `CM-012` Temporary storage | File-transfer failure tests |
| `CM-013` Database abstraction | Storage tests |
| `CM-014` Sensitive logging | Logging tests |
| `CM-015` Security events | Logging / event tests |
| `CM-016` Secret separation | Configuration / repository checks |
| `CM-017` Persistence | Command/security tests |
| `CM-018` Self-destruct | Lifecycle/security tests |
| `CM-019` Agent/session separation | Session integration tests |
| `CM-020` Async task handling | Task / synchronization tests |
| `CM-021` Security regression | Full security test suite |
| `CM-022` Laboratory scope | Deployment / project-process control |
| `CM-023` Agent authentication | Registration / transport security tests |

Detailed test organisation remains defined in `docs/testing-strategy.md`.

---

# 21. Countermeasure Priorities

Security controls should be implemented according to risk and dependency.

## Priority 1 — Fundamental protections

These should exist before relying on the system for normal operation:

```text
TLS
Protocol validation
Task validation
Controlled file paths
Secure file-transfer handling
Basic logging
Configuration / secret separation
```

## Priority 2 — State and reliability protections

These support reliable and secure asynchronous operation:

```text
Task correlation
Agent/session separation
Explicit task lifecycle
Synchronization and recovery
Temporary-file handling
Integrity verification
Multi-agent state isolation
```

## Priority 3 — Open capability-specific controls

These depend on the final design of:

```text
Agent authentication
PERSISTENCE
SELF_DESTRUCT
```

Their countermeasures cannot be considered complete until the underlying behaviour has been explicitly defined.

---

# 22. Security Residual Risk

Security controls reduce risk but do not eliminate it completely.

Examples of residual risk include:

- compromise of the host running the C2 server;
- compromise of a laboratory endpoint;
- incorrect configuration;
- implementation bugs;
- weaknesses in underlying operating systems or libraries;
- compromise of credentials or authentication material if introduced;
- misuse of a legitimate project capability by an authorized operator;
- risks associated with capabilities whose exact implementation remains open.

These residual risks should be documented rather than implicitly considered solved.

---

# 23. Traceability Summary

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
    └── CM-023
          │
          ▼
Implementation
          │
          ▼
Testing
```

This creates a consistent link between:

```text
identified risk
      ↓
security requirement
      ↓
protection
      ↓
implementation
      ↓
verification
```

The exact threat and requirement identifiers must remain synchronized with `docs/threat-model.md` and `docs/requirements-mapping.md`.

---

# 24. Final Security Position

C2-AUTOMATED should not be considered secure simply because it uses TLS or because the architecture is modular.

Security depends on the combination of:

```text
Secure transport
        +
Protocol validation
        +
Explicit identity / authentication model
        +
Controlled task execution
        +
Controlled filesystem access
        +
File integrity verification
        +
Persistent-state protection
        +
Logging and traceability
        +
State reconciliation
        +
Testing
        +
Explicit laboratory scope
```

Security is therefore treated as a property of the **complete system**, rather than a feature provided by a single component.

The most important principle is:

> **Every capability that introduces a new attack surface must have a corresponding security control and a means of verification.**
