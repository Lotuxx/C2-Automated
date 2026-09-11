# Security

## 1. Purpose

This document describes the security principles and security boundaries of the C2-AUTOMATED project.

The objective is to ensure that the system is designed and implemented with appropriate protections for:

- communication between the C2 server and agents;
- message validation;
- task and result handling;
- file transfers;
- local file storage;
- persistent data;
- configuration and secrets;
- logging and error handling.

The project is intended for an **authorized and isolated laboratory environment** for educational purposes.

---

# 2. Security Scope

The security model covers the following components:

```text
Operator
    │
    ▼
C2 Interface
    │
    ▼
C2 Core
    │
    ├── Task Management
    ├── Result Management
    ├── Agent / Session Management
    └── File Management
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
    ├── Command Execution
    ├── Platform-specific Operations
    └── Local File Handling
```

Security controls should be applied at the appropriate boundary rather than relying on a single protection mechanism.

---

# 3. Security Principles

## 3.1 Defense in Depth

The system should not rely on a single security control.

Examples include:

- TLS for communication confidentiality;
- protocol validation for structured input;
- file integrity verification;
- controlled file-storage locations;
- separation of application responsibilities;
- centralized logging;
- explicit configuration management.

---

## 3.2 Separation of Responsibilities

Security-sensitive responsibilities are separated between components.

For example:

```text
Protocol
    │
    └── validates message structure

Transport
    │
    └── protects network communication

Core
    │
    └── handles application logic

Storage
    │
    └── persists data

File Manager
    │
    └── manages file-transfer lifecycle
```

A component should not bypass the boundaries of another component without a defined reason.

---

## 3.3 Least Privilege

Components should operate with only the permissions required for their intended role.

In particular:

- the server should only access the directories and resources required by the application;
- the agent should use its defined file workspace for transfer-related storage;
- commands should not automatically assume unrestricted privileges;
- administrative privileges should only be used where required by the laboratory scenario.

---

## 3.4 Input Is Untrusted by Default

Data received through the network must not automatically be considered trustworthy.

This applies to:

- registration data;
- beacon messages;
- task messages;
- results;
- file-transfer metadata;
- file chunks;
- error messages.

Successful transport-layer authentication or encryption does not replace application-level validation.

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

- task messages;
- results;
- agent status and beacon communication;
- file transfers.

---

## 4.2 Protocol and Transport Are Separate

The architecture deliberately separates:

> **Protocol — what is exchanged**

from:

> **Transport — how it is transmitted**

This allows communication security to remain associated with the transport layer without coupling application logic directly to sockets or a specific network implementation.

The use of TLS does not remove the need for message validation.

---

## 4.3 TLS Configuration

The final implementation should use an appropriate TLS configuration rather than relying on insecure defaults.

The implementation should document:

- the TLS version/configuration selected;
- certificate handling;
- certificate verification behaviour;
- trust configuration;
- failure behaviour when verification fails.

These details should be finalized during implementation and testing.

---

# 5. Protocol Security

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
- rejecting malformed messages;
- avoiding ambiguous message interpretation;
- preventing invalid data from reaching business logic.

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
Application Logic
```

Invalid messages should be rejected before reaching sensitive application logic.

---

# 6. Message Integrity and Correlation

Protocol messages should contain sufficient metadata to associate requests, responses, agents, and transfers correctly.

The architecture currently considers metadata such as:

```text
version
message_id
agent_id
type
timestamp
payload
```

The exact protocol contract will be defined in the protocol specification.

Where applicable, identifiers should be used to ensure that:

- a result is associated with the correct task;
- a task is associated with the correct agent;
- file-transfer messages are associated with the correct transfer;
- duplicate or unexpected messages can be detected.

---

# 7. Task Security

Tasks represent requested operations that are sent to agents.

The conceptual task lifecycle is:

```text
PENDING
   │
   ▼
 SENT
   │
   ▼
RUNNING
   │
   ├──────────► FAILED
   │
   ▼
COMPLETED
```

Tasks should be validated before being dispatched.

The agent should not execute arbitrary malformed task structures.

The execution path should remain separated:

```text
Received Task
     │
     ▼
Protocol Validation
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

# 8. Agent Execution Security

The agent separates:

```text
Executor
    ↓
Commands
    ↓
Platform
```

The Executor is responsible for dispatching an operation, while individual commands implement specific functionality.

Platform-specific code remains isolated to reduce unintended effects on common agent logic.

Commands should:

- validate their expected parameters;
- handle execution errors safely;
- avoid exposing sensitive information unnecessarily;
- return structured results rather than mixing execution logic with communication logic.

---

# 9. File Transfer Security

File transfers are treated as a separate application concern.

The architecture supports structured transfers using messages such as:

```text
FILE_START
FILE_CHUNK
FILE_END
```

A transfer can therefore be processed incrementally rather than requiring the complete file to remain in memory.

---

## 9.1 Encryption in Transit

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

Therefore, separate application-level encryption of every file is not required for the mandatory MVP solely to protect data while travelling between the C2 server and the agent.

---

## 9.2 File Integrity

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

## 9.3 Chunk Handling

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

This avoids requiring the entire file to be loaded into memory.

The final implementation should also define behaviour for:

- missing chunks;
- unexpected chunks;
- duplicate chunks;
- incomplete transfers;
- interrupted transfers;
- invalid transfer identifiers;
- failed integrity verification.

---

# 10. File Storage Security

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

The same conceptual separation exists on the agent.

The transfer subsystem should not treat arbitrary filesystem paths as its storage mechanism.

---

## 10.1 Temporary Files

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

## 10.2 Path Handling

File paths received from external input should not be trusted blindly.

The implementation should validate file names and paths before using them for local storage.

The transfer subsystem should prevent externally supplied paths from escaping the intended file-storage workspace.

---

# 11. Storage Security

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

---

# 12. Secrets and Configuration

Security-sensitive configuration must not be hard-coded throughout the source code.

Configuration is centralized under:

```text
config/
```

Sensitive values should not be committed to the repository.

Examples include:

- private keys;
- credentials;
- secrets;
- development certificates containing private material;
- environment-specific configuration.

The repository should use appropriate mechanisms such as environment variables or ignored local configuration files where required.

Public configuration and secret material should remain clearly separated.

---

# 13. Logging and Security Events

Logging is centralized under:

```text
logging/
```

Relevant security and operational events may include:

```text
agent registration
session establishment
session termination
task creation
task dispatch
task failure
result reception
file transfer start
file transfer completion
file integrity failure
protocol validation failure
transport errors
```

Logs should provide enough information for troubleshooting and auditing without unnecessarily exposing sensitive data.

Sensitive values, credentials, cryptographic secrets, and private key material must not be written to logs.

---

# 14. Error Handling

Errors should be handled explicitly rather than silently ignored.

Security-relevant failures include:

- invalid messages;
- invalid task parameters;
- failed TLS communication;
- malformed file-transfer metadata;
- incomplete transfers;
- integrity-check failures;
- storage failures;
- unexpected agent/session state.

The system should fail in a controlled manner and avoid exposing unnecessary internal information to remote components.

---

# 15. Data Protection at Rest

TLS protects information while it is travelling between the C2 server and the agent.

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

---

# 16. Security Boundaries

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
         ┌──────────┴──────────┐
         ▼                     ▼
      Storage              Protocol
                               │
                               ▼
                         TLS Transport
                               │
                               ▼
                             Agent
                               │
                     ┌─────────┴─────────┐
                     ▼                   ▼
                  Executor           File Handling
                     │                   │
                     ▼                   ▼
                 Commands           File Storage
```

Each boundary should validate or constrain the data crossing it as appropriate.

---

# 17. Laboratory Scope

C2-AUTOMATED is an academic project and must be used only in an authorized laboratory environment.

Testing should be restricted to:

- systems owned or explicitly authorized for testing;
- isolated laboratory networks or controlled environments;
- test agents created specifically for the project.

The project should not be used against systems or networks without explicit authorization.

---

# 18. Security Testing

Security testing should verify at least the following categories:

### Transport

- TLS connection succeeds with the intended configuration;
- invalid or unacceptable TLS configurations are rejected;
- communication failures are handled correctly.

### Protocol

- malformed messages are rejected;
- missing required fields are rejected;
- invalid message types are rejected;
- invalid identifiers are rejected.

### Tasks

- invalid task parameters are rejected;
- task state transitions remain consistent;
- unexpected results cannot be incorrectly associated with another task.

### Files

- incomplete transfers are rejected or cleaned up;
- invalid chunks are handled safely;
- integrity failures are detected;
- temporary files are cleaned up appropriately;
- storage paths remain within the intended workspace.

### Storage

- application data is stored through the defined interfaces;
- sensitive configuration is not committed;
- logs do not expose secrets.

---

# 19. Security Status

The following security principles are part of the current architectural baseline:

- TLS-protected C2-Agent communication;
- protocol validation before application processing;
- separation between protocol and transport;
- controlled file-storage workspaces;
- incremental file-transfer handling;
- file integrity verification;
- separation of metadata and file contents;
- centralized logging;
- centralized configuration;
- explicit security boundaries;
- authorized laboratory-only use.

The following areas require detailed implementation decisions and testing:

- exact TLS configuration;
- certificate lifecycle and trust model;
- exact protocol validation rules;
- authentication/identity mechanisms;
- protection of local stored data;
- detailed path-validation implementation;
- detailed failure and recovery behaviour.

Security requirements should evolve together with the architecture and should be recorded in [`DECISIONS.md`](DECISIONS.md) when they represent significant design choices.
