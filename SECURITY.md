# Security

## 1. Purpose

This document describes the security principles and security boundaries of the C2-AUTOMATED project.

The objective is to ensure that the system is designed and implemented with appropriate protections for:

- communication between the C2 server and agents;
- agent identity and authentication;
- message validation and routing;
- session and communication-state management;
- task and result handling;
- synchronization and state reconciliation;
- file transfers;
- local file storage;
- persistent data;
- configuration and secrets;
- logging and error handling;
- resource usage and availability.

The project is intended for an **authorized and isolated laboratory environment** for educational purposes.

This document defines the project's **security principles and baseline controls**. Detailed threats and risks are maintained in [`docs/threat-model.md`](docs/threat-model.md), while concrete countermeasures are maintained in [`docs/countermeasures.md`](docs/countermeasures.md).

---

# 2. Security Scope

The security model covers the following components:

```text
Operator
    │
    ▼
Operator Interface
    │
    ▼
C2 Core
    │
    ├── Agent Manager
    ├── Session Manager
    ├── Task Manager
    ├── Result Manager
    ├── File Manager
    ├── Message Router
    └── Synchronization Manager
    │
    ├── Protocol
    ├── Transport
    ├── Database Storage
    ├── File Storage
    └── Logging / Events
    │
    ▼
Protected Network Transport
    │
    ▼
Agent
    │
    ├── Core
    ├── Beacon
    ├── Protocol
    ├── Transport
    ├── Executor
    ├── Commands
    ├── Platform
    └── File Storage
```

Security controls should be applied at the appropriate boundary rather than relying on a single protection mechanism.

The main security properties are:

- confidentiality;
- integrity;
- authenticity;
- authorization;
- availability;
- accountability and traceability.

---

# 3. Security Principles

## 3.1 Defense in Depth

The system should not rely on a single security control.

Examples include:

- TLS for communication confidentiality and transport protection;
- protocol validation for structured input;
- explicit agent authentication;
- session and context validation;
- file integrity verification;
- controlled file-storage locations;
- separation of application responsibilities;
- centralized logging;
- explicit configuration management;
- resource and timeout limits.

A successful security control at one layer must not be treated as proof that all other layers are trustworthy.

---

## 3.2 Separation of Responsibilities

Security-sensitive responsibilities are separated between components.

For example:

```text
Protocol
    │
    └── parses and validates message structure

Message Router
    │
    └── routes validated messages to the appropriate subsystem

Transport
    │
    └── protects network communication

Core
    │
    └── handles application logic and state

Synchronization Manager
    │
    └── reconciles Agent and C2 state

Storage
    │
    └── persists structured data or file contents

File Manager
    │
    └── manages file-transfer lifecycle

Executor
    │
    └── dispatches validated operations

Commands
    │
    └── implement individual operations
```

A component should not bypass the boundaries of another component without a defined architectural reason.

---

## 3.3 Least Privilege

Components should operate with only the permissions required for their intended role.

In particular:

- the C2 server should only access the directories and resources required by the application;
- the agent should use its defined file workspace for transfer-related storage;
- commands should not automatically assume unrestricted privileges;
- administrative privileges should only be used where required by the laboratory scenario;
- storage and configuration files should use appropriate filesystem permissions.

The project should avoid requiring unnecessary privileges merely for convenience.

---

## 3.4 Input Is Untrusted by Default

Data received from another component must not automatically be considered trustworthy.

This applies to:

- registration data;
- beacon messages;
- task messages;
- task status messages;
- results;
- synchronization data;
- file-transfer metadata;
- file chunks;
- error messages.

This principle applies even when communication occurs through TLS.

Successful transport-layer protection does not replace application-level validation.

---

## 3.5 Fail Safely

Security-relevant failures should produce a controlled outcome rather than silently bypassing validation or security boundaries.

Examples include:

- invalid protocol messages;
- failed authentication;
- invalid task parameters;
- unexpected session state;
- failed integrity verification;
- invalid file paths;
- synchronization inconsistencies;
- storage failures.

A failure should not automatically be interpreted as proof of a different state.

For example:

```text
Communication loss
      ≠
Task failure
      ≠
Agent termination
```

---

## 3.6 Explicit State and Context

Security-sensitive operations must be evaluated against the relevant context.

The project distinguishes:

```text
Agent identity
      ≠
Session
      ≠
Agent health
      ≠
Agent communication state
      ≠
Task state
```

This prevents a state observed in one domain from being incorrectly interpreted as a state in another.

---

# 4. Communication Security

## 4.1 TLS

The mandatory communication mechanism for the MVP is **TCP/TLS**.

```text
C2 Server
    │
    │ TLS
    ▼
  Agent
```

TLS protects communication while it is travelling over the network.

This applies to:

- registration;
- synchronization;
- task messages;
- task status;
- results;
- beacon communication;
- liveness communication;
- file transfers;
- error messages.

TLS provides transport protection but does not by itself define the identity or authorization model of the application.

---

## 4.2 Protocol and Transport Are Separate

The architecture deliberately separates:

> **Protocol — what is exchanged**

from:

> **Transport — how it is transmitted**

This allows communication security to remain associated with the transport layer without coupling application logic directly to sockets or a specific network implementation.

The use of TLS does not remove the need for:

- message validation;
- message correlation;
- state validation;
- authentication;
- authorization.

---

## 4.3 TLS Configuration

The final implementation should use an appropriate TLS configuration rather than relying on insecure defaults.

The implementation should document:

- the TLS version/configuration selected;
- certificate handling;
- certificate verification behaviour;
- trust configuration;
- failure behaviour when verification fails;
- development versus laboratory certificate handling.

These details should be finalized during implementation and testing.

The project must not assume that encryption alone proves that the remote endpoint is authorized.

---

# 5. Agent Identity and Authentication

Agent identification and authentication are separate security concepts.

```text
agent_id
   │
   └── identifies an application-level Agent

authentication
   │
   └── establishes whether that Agent is trusted
```

An `agent_id` must therefore **not** be treated as sufficient proof of identity.

The registration flow currently establishes:

```text
New connection
    │
    ▼
New Session
    │
    ▼
Transport established
    │
    ▼
Session = CONNECTED
    │
    ▼
REGISTER
    │
    ▼
Agent identified
    │
    ▼
Authentication / registration validation
    │
    ▼
REGISTER_ACK
```

The exact Agent authentication mechanism remains an open security decision and must be defined before the corresponding feature is considered complete.

The authentication mechanism must be associated with the correct Agent and Session context.

Relevant design decision:

- `PRO-001` — exact Agent authentication model.

---

# 6. Protocol Security

The protocol layer contains:

```text
protocol/
├── messages.py
├── serializer.py
└── validator.py
```

Security-relevant responsibilities include:

- validating message structure;
- validating required fields;
- validating message types;
- validating identifiers;
- validating permitted values;
- rejecting malformed messages;
- avoiding ambiguous message interpretation;
- preventing invalid data from reaching business logic;
- validating message context where required.

The intended flow is:

```text
Network Input
     │
     ▼
Transport
     │
     ▼
Protocol Parsing
     │
     ▼
Validation
     │
     ▼
Message Router
     │
     ▼
Application Logic
```

Invalid messages should be rejected before reaching sensitive application logic.

---

# 7. Message Integrity, Correlation and Routing

Protocol messages should contain sufficient metadata to associate requests, responses, agents, sessions, tasks, results, and transfers correctly.

The architecture currently considers metadata such as:

```text
version
message_id
agent_id
type
timestamp
payload
```

Additional identifiers may be required depending on the message type, such as:

```text
session_id
task_id
result_id
transfer_id
```

The exact protocol contract is defined separately in the protocol specification.

Identifiers should be used to ensure that:

- a result is associated with the correct task;
- a task is associated with the correct Agent;
- communication is associated with the correct Session;
- file-transfer messages are associated with the correct transfer;
- duplicate messages can be detected;
- unexpected messages can be rejected;
- messages cannot be silently associated with another context.

---

## 7.1 Message Router

The Message Router provides a controlled routing boundary between validated protocol messages and application subsystems.

Conceptually:

```text
Validated Message
       │
       ▼
Message Router
       │
       ├── Task Manager
       ├── Result Manager
       ├── File Manager
       ├── Session Manager
       └── Synchronization Manager
```

Routing must be based on validated message type and context.

The router must not bypass protocol validation or silently reinterpret a message as another message type.

---

# 8. Session and Communication Security

A Session represents one communication episode between an Agent and the C2.

The Session lifecycle is:

```text
CONNECTING
     │
     ▼
CONNECTED
     │
     ├──► DISCONNECTED
     │
     └──► CLOSED
```

A new connection creates a **new Session**.

A historical Session must not be silently reopened.

For example:

```text
Agent A001
 ├── S041
 ├── S042 = DISCONNECTED
 └── S043 = CONNECTED
```

The Agent identity remains persistent while Sessions represent individual communication episodes.

---

## 8.1 Session and Agent Communication State

Session state must not be confused with Agent communication state.

Agent communication uses:

```text
CONNECTING
CONNECTED
DEGRADED
OFFLINE_WAIT
SYNCHRONIZING
```

For example:

```text
Session = CONNECTED
Agent communication = SYNCHRONIZING
```

is a valid combination.

This distinction prevents synchronization or communication conditions from incorrectly modifying the underlying Session lifecycle.

---

## 8.2 Health and Communication Loss

Agent health is represented separately:

```text
UNKNOWN
ALIVE
LIKELY_UNREACHABLE
TERMINATED
```

Communication loss alone must not automatically imply:

```text
Agent = TERMINATED
```

Similarly:

```text
Communication loss
      ≠
Task failure
```

Task recovery must use the defined Task recovery and synchronization mechanisms.

---

# 9. Registration and Synchronization Security

Registration and synchronization are security-sensitive because they establish or reconcile application state.

The canonical flow is:

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
REGISTER_ACK
    │
    ▼
Agent communication = SYNCHRONIZING
    │
    ▼
SYNC_STATE
    │
    ▼
Reconciliation
    │
    ▼
SYNC_STATE_RESPONSE
    │
    ▼
SYNC_COMPLETE
    │
    ▼
Agent communication = CONNECTED
```

`REGISTER` identifies the Agent over an already-established Session. It does not itself establish the Session.

`REGISTER_ACK` confirms registration and communicates the new Session identifier. It does not cause the Session transition from `CONNECTING` to `CONNECTED`.

---

## 9.1 Synchronization Security

Synchronization data must not automatically override C2 state.

The Synchronization Manager must validate:

- Agent identity;
- Session context;
- task identifiers;
- task states;
- result identifiers;
- known versus unknown tasks;
- known versus unknown results;
- duplicate information;
- consistency of reported state.

The reconciliation process must preserve historical Sessions.

An Agent reconnecting must therefore create a new Session rather than modifying the historical Session.

---

# 10. Task Security

Tasks represent requested operations that are sent to Agents.

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
   ├──────────► FAILED
   │
   ├──────────► TIMEOUT
   │
   ├──────────► CANCELLED
   │
   ▼
COMPLETED
```

`UNKNOWN` is not a persistent Task state. It is a recovery/reporting condition when the current execution state cannot be established.

Tasks should be validated before being dispatched.

The Agent should not execute arbitrary malformed task structures.

---

## 10.1 Task and Result Separation

A Task and its Result are separate concepts.

```text
Task
 │
 └── may produce → Result
```

A missing Result does not automatically prove that a Task failed.

Likewise, a Result must not be associated with a Task solely because it arrived from the same Agent.

Correlation identifiers and validation must be used.

---

## 10.2 Task Execution Boundary

The execution path should remain separated:

```text
Received Task
     │
     ▼
Protocol Validation
     │
     ▼
Task Validation
     │
     ▼
Executor
     │
     ▼
Command Handler
     │
     ▼
Execution
```

This provides a clear boundary between communication and endpoint execution.

---

# 11. Agent Execution Security

The Agent separates:

```text
Executor
    ↓
Commands
    ↓
Platform
```

The Executor is responsible for dispatching an operation, while individual Commands implement specific functionality.

Platform-specific code remains isolated to reduce unintended effects on common Agent logic.

Commands should:

- validate their expected parameters;
- handle execution errors safely;
- avoid exposing sensitive information unnecessarily;
- return structured results rather than mixing execution logic with communication logic;
- operate with only the privileges required for the laboratory scenario.

Sensitive command categories such as `PERSISTENCE` and `SELF_DESTRUCT` require explicit scope and validation before implementation.

The exact behaviour of these commands remains subject to the project decisions.

---

# 12. File Transfer Security

File transfers are treated as a separate application concern.

The architecture supports structured transfers using:

```text
FILE_START
FILE_CHUNK
FILE_END
```

A transfer can therefore be processed incrementally rather than requiring the complete file to remain in memory.

A Transfer is distinct from:

```text
Agent
Session
Task
Result
```

A transfer may optionally be associated with a Task but has its own identifier:

```text
transfer_id
```

---

## 12.1 Encryption in Transit

File data is transferred through the protected TLS transport.

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

Therefore, separate application-level encryption of every file is not required for the mandatory MVP solely to protect data while travelling between the C2 server and the Agent.

This does **not** provide encryption at rest.

---

## 12.2 File Integrity

File integrity is handled independently from transport confidentiality.

The intended mechanism is a cryptographic hash, such as SHA-256.

```text
Original File
     │
     ▼
  SHA-256
     │
     ▼
   Transfer
     │
     ▼
Reconstructed File
     │
     ▼
  SHA-256
     │
     ▼
  Comparison
```

A mismatch should cause the transfer to be treated as invalid or corrupted.

This provides an application-level integrity check over the reconstructed file.

---

## 12.3 Chunk Handling

File chunks should be handled incrementally.

Conceptually:

```text
chunk
  ↓
validate
  ↓
write
  ↓
next chunk
```

The implementation should define behaviour for:

- missing chunks;
- unexpected chunks;
- duplicate chunks;
- incomplete transfers;
- interrupted transfers;
- invalid transfer identifiers;
- excessive transfer sizes;
- failed integrity verification.

Communication failure must not automatically be interpreted as proof that the transfer is corrupted or completed.

---

# 13. File Storage Security

The actual file contents are separated from the storage implementation.

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

The project uses dedicated workspaces:

```text
data/
└── files/
    ├── uploads/
    ├── downloads/
    └── temporary/
```

The same conceptual separation exists on the Agent.

The transfer subsystem should not treat arbitrary filesystem paths as its storage mechanism.

---

## 13.1 Temporary Files

Temporary files are used while transfers are being processed or reconstructed.

A temporary artifact should only become a final file after the transfer has successfully completed the required validation steps.

Conceptually:

```text
Incoming Data
     │
     ▼
Temporary File
     │
     ▼
Completion
     │
     ▼
Integrity Verification
     │
     ├── failure → reject/remove
     │
     └── success → final file
```

Temporary data should be cleaned up when it is no longer required.

---

## 13.2 Path Handling

File paths received from external input should not be trusted blindly.

The implementation should validate file names and paths before using them for local storage.

The transfer subsystem should prevent externally supplied paths from escaping the intended file-storage workspace.

Path validation must account for:

- absolute paths;
- relative paths;
- parent-directory traversal;
- platform-specific path representations;
- invalid or unexpected file names.

The exact implementation belongs to the File Storage / File Transfer implementation.

---

# 14. Storage Security

Structured information is persisted separately from file contents.

The current architecture uses:

```text
storage/
├── database/
└── files/
```

The database may contain information associated with:

```text
agents
sessions
tasks
results
file transfers
events
```

The filesystem contains the actual transferred data.

This separation reduces coupling between application metadata and file contents.

Database access should remain behind the defined storage interface.

File contents should remain behind the File Storage interface.

---

# 15. Secrets and Configuration

Security-sensitive configuration must not be hard-coded throughout the source code.

Configuration is centralized under:

```text
config/
```

Sensitive values should not be committed to the repository.

Examples include:

- private keys;
- credentials;
- authentication secrets;
- development certificates containing private material;
- environment-specific secrets.

The repository should use appropriate mechanisms such as environment variables or ignored local configuration files where required.

Public configuration and secret material should remain clearly separated.

---

## 15.1 Secret Handling

Secrets should:

- have restricted filesystem permissions;
- not be included in logs;
- not be embedded in protocol messages unless explicitly required;
- not be committed to version control;
- not be exposed through debugging output.

The exact credential and key-management model remains dependent on the final authentication and TLS decisions.

---

# 16. Logging and Security Events

Logging is centralized under:

```text
logging/
```

Relevant security and operational events may include:

```text
agent registration
authentication result
session establishment
session disconnection
session closure
agent communication-state changes
task creation
task acknowledgement
task state changes
result reception
synchronization
file transfer start
file transfer completion
file integrity failure
protocol validation failure
routing failure
transport errors
storage errors
```

Logs should provide enough information for troubleshooting and auditing without unnecessarily exposing sensitive data.

Sensitive values, credentials, authentication material, cryptographic secrets, private keys, and unnecessary file contents must not be written to logs.

Logging should preserve sufficient identifiers to correlate events where appropriate:

```text
agent_id
session_id
task_id
result_id
transfer_id
event_id
```

---

# 17. Error Handling

Errors should be handled explicitly rather than silently ignored.

Security-relevant failures include:

- invalid messages;
- failed authentication;
- invalid task parameters;
- failed TLS communication;
- invalid session context;
- malformed synchronization data;
- malformed file-transfer metadata;
- incomplete transfers;
- integrity-check failures;
- storage failures;
- unexpected Agent or Session state;
- invalid message routing.

The system should fail in a controlled manner and avoid exposing unnecessary internal information to remote components.

An error must not silently cause an unrelated state transition.

---

# 18. Data Protection at Rest

TLS protects information while it is travelling between the C2 server and the Agent.

This does not automatically encrypt files stored on disk.

Application-level encryption of stored files is therefore considered a separate security property.

For the mandatory MVP:

```text
Encryption in transit
    → TLS

File integrity
    → cryptographic hash

Encryption at rest
    → not mandatory for MVP
```

Encryption at rest may be considered later as a defense-in-depth feature if its key-management requirements can be implemented and tested appropriately.

At minimum, access to local databases, files, logs, configuration and cryptographic material should be restricted through appropriate filesystem permissions and deployment practices.

---

# 19. Resource and Availability Security

The system should protect itself against excessive resource consumption.

Relevant resources include:

- network connections;
- concurrent sessions;
- task queues;
- message sizes;
- file sizes;
- temporary storage;
- database storage;
- task execution time;
- file-transfer duration.

The implementation should define appropriate:

- size limits;
- queue limits;
- timeouts;
- cleanup policies;
- concurrency limits where necessary.

Resource exhaustion should not result in uncontrolled application failure.

---

# 20. Security Boundaries

The main security boundaries are:

```text
                 OPERATOR
                    │
                    ▼
             Operator Interface
                    │
                    ▼
               C2 Core
                    │
        ┌───────────┼────────────┐
        ▼           ▼            ▼
     Protocol    Storage    Synchronization
        │
        ▼
  Message Router
        │
        ▼
  TLS Transport
        │
        ▼
      Agent
        │
   ┌────┴──────────────┐
   ▼                   ▼
Executor          File Handling
   │                   │
   ▼                   ▼
Commands           File Storage
   │
   ▼
Platform
```

Each boundary should validate or constrain the data crossing it as appropriate.

In particular:

```text
Network
   ↓
Transport protection
   ↓
Protocol validation
   ↓
Message routing
   ↓
Application state validation
   ↓
Execution / storage
```

No single layer should assume that previous layers have made all security decisions.

---

# 21. Laboratory Scope

C2-AUTOMATED is an academic project and must be used only in an authorized laboratory environment.

Testing should be restricted to:

- systems owned or explicitly authorized for testing;
- isolated laboratory networks or controlled environments;
- test agents created specifically for the project.

The project should not be used against systems or networks without explicit authorization.

This scope is a security requirement rather than merely a deployment recommendation.

---

# 22. Security Testing

Security testing should verify at least the following categories.

### Transport

- TLS connection succeeds with the intended configuration;
- invalid or unacceptable TLS configurations are rejected;
- certificate verification behaves as designed;
- communication failures are handled correctly;
- unauthorized connection attempts are rejected according to the authentication model.

### Authentication and Identity

- unknown Agents cannot authenticate successfully;
- invalid authentication material is rejected;
- Agent identity is not accepted solely because an `agent_id` was supplied;
- authentication is correctly associated with the Agent and Session.

### Protocol

- malformed messages are rejected;
- missing required fields are rejected;
- invalid message types are rejected;
- invalid identifiers are rejected;
- invalid message contexts are rejected;
- duplicate or unexpected messages are handled safely.

### Routing

- messages are routed to the correct subsystem;
- invalid routing contexts are rejected;
- a message cannot be silently interpreted as another message type.

### Sessions

- new connections create new Sessions;
- disconnected Sessions are not silently reopened;
- Session and Agent identity remain correctly associated;
- invalid Session contexts are rejected.

### Synchronization

- synchronization data is validated;
- unknown tasks do not silently become authoritative C2 tasks;
- duplicate results are handled correctly;
- historical Sessions remain unchanged;
- reconciliation does not create inconsistent Task or Result state.

### Tasks

- invalid task parameters are rejected;
- authoritative Task state transitions remain consistent;
- `WAITING_ACK` is handled separately from `TIMEOUT`;
- unexpected Results cannot be incorrectly associated with another Task;
- communication loss does not automatically mark a Task as failed;
- duplicate execution is appropriately controlled.

### Agent Execution

- malformed operations do not reach unsafe execution paths;
- command parameters are validated;
- Executor and Command boundaries remain enforced;
- unnecessary privileges are not required.

### Files

- incomplete transfers are handled safely;
- invalid chunks are rejected;
- duplicate/unexpected chunks are handled correctly;
- integrity failures are detected;
- temporary files are cleaned up appropriately;
- storage paths remain within the intended workspace;
- excessive transfer sizes are controlled.

### Storage

- application data is stored through the defined interfaces;
- database and file-storage responsibilities remain separated;
- sensitive configuration is not committed;
- filesystem permissions are appropriate;
- logs do not expose secrets.

### Availability

- resource limits behave as expected;
- excessive message or file sizes are rejected;
- timeouts work correctly;
- temporary resources are cleaned up;
- communication failures do not leave uncontrolled resources behind.

---

# 23. Security Status

The following security principles are part of the current architectural baseline:

- TCP/TLS-protected C2-Agent communication;
- separation between protocol and transport;
- protocol validation before application processing;
- explicit separation of Agent identity and Session identity;
- explicit Session lifecycle;
- explicit Agent health and communication states;
- controlled message routing;
- explicit synchronization boundary;
- controlled file-storage workspaces;
- incremental file-transfer handling;
- file integrity verification;
- separation of metadata and file contents;
- centralized logging;
- centralized configuration;
- explicit security boundaries;
- least-privilege principles;
- authorized laboratory-only use.

The following areas require detailed implementation decisions and testing:

- exact Agent authentication mechanism;
- exact TLS configuration;
- certificate lifecycle and trust model;
- exact protocol serialization and validation rules;
- replay protection;
- detailed authorization model;
- synchronization conflict-resolution rules;
- detailed path-validation implementation;
- file-transfer recovery and resumability;
- resource limits;
- protection of local stored data;
- detailed failure and recovery behaviour;
- exact `PERSISTENCE` behaviour;
- exact `SELF_DESTRUCT` behaviour.

These unresolved items should be tracked in [`DECISIONS.md`](DECISIONS.md) when they represent significant architectural or security decisions.

---

# 24. Relationship with Other Security Documentation

The project deliberately separates security documentation by purpose.

| Document | Purpose |
|---|---|
| `SECURITY.md` | Security principles, boundaries and baseline security requirements |
| `docs/threat-model.md` | Threat catalogue, risk analysis, risk ownership and security requirements derived from threats |
| `docs/countermeasures.md` | Concrete security controls and their implementation status |
| `docs/kill-chain-analysis.md` | Mapping of relevant capabilities to the Cyber Kill Chain |
| `docs/testing-strategy.md` | Testing strategy, including security validation |
| `DECISIONS.md` | Significant architectural and security decisions |

The intended relationship is:

```text
SECURITY.md
     │
     ├── defines principles
     │
     ▼
Threat Model
     │
     ├── identifies risks
     │
     ▼
Countermeasures
     │
     ├── defines controls
     │
     ▼
Implementation
     │
     ▼
Testing Strategy
     │
     ▼
Validated Security Controls
```

These documents should complement each other rather than duplicate the same detailed material.

---

# 25. Summary

The main security principle of C2-AUTOMATED is:

> **Do not treat communication, input, execution requests, synchronization data, or stored data as trusted merely because they originate from another component of the system.**

The architecture therefore establishes distinct security boundaries around:

- operator interaction;
- C2 application logic;
- protocol validation;
- message routing;
- authentication and identity;
- Session management;
- synchronization;
- network transport;
- persistent storage;
- file handling;
- Agent execution.

Security must be applied as a layered system:

```text
Identity / Authentication
          ↓
Secure Transport
          ↓
Protocol Validation
          ↓
Message Correlation / Routing
          ↓
State and Context Validation
          ↓
Application Logic
          ↓
Controlled Execution / Storage
          ↓
Logging / Traceability
          ↓
Testing / Validation
```

The system is intended exclusively for an **authorized laboratory environment**, and all security decisions must remain consistent with that scope.

Security requirements should evolve together with the architecture. Significant changes should be reflected in the threat model, countermeasures, testing strategy, and `DECISIONS.md` as appropriate.
