# Threat Model

## 1. Purpose

This document identifies and analyses the security threats relevant to the **C2-AUTOMATED** project.

The objective is not to describe how to exploit the system, but to determine:

- what needs to be protected;
- where trust boundaries exist;
- which components can be attacked or misused;
- what could go wrong;
- what the consequences could be;
- which security properties and controls are required.

The threat model provides the basis for the project's security analysis and is used by:

- [`../SECURITY.md`](../SECURITY.md) for global security principles;
- [`kill-chain-analysis.md`](kill-chain-analysis.md) for the Cyber Kill Chain analysis;
- [`countermeasures.md`](countermeasures.md) for the mapping between identified threats and security controls;
- [`testing-strategy.md`](testing-strategy.md) for security validation.

---

## 2. Scope

The threat model covers the main components of the project:

```text
Operator
    │
    ▼
Operator Interface
    │
    ▼
C2 Server
    ├── Core
    ├── Protocol
    ├── Transport
    ├── Database Storage
    └── File Storage
            │
            ▼
       Network Communication
            │
            ▼
          Agent
            ├── Core
            ├── Beacon
            ├── Protocol
            ├── Transport
            ├── Executor
            ├── Commands
            ├── Platform
            └── File Storage
```

The model considers threats affecting:

- confidentiality;
- integrity;
- availability;
- authenticity;
- authorization;
- accountability and traceability;
- stored data;
- transmitted data;
- task execution;
- file handling.

The project is designed for an **authorized laboratory environment**. Threats are therefore considered from both perspectives:

1. compromise or abuse of the C2 infrastructure;
2. compromise or abuse of an agent or its communication with the C2.

The model does not assume that either side of the communication is automatically trustworthy.

---

## 3. Security objectives

The main security objectives are:

### 3.1 Confidentiality

Prevent unauthorized parties from accessing:

- communications;
- stored task data;
- results;
- transferred files;
- configuration;
- credentials or cryptographic material;
- operational logs containing sensitive information.

### 3.2 Integrity

Prevent unauthorized modification of:

- protocol messages;
- task information;
- results;
- file-transfer data;
- persistent metadata;
- configuration;
- application state.

### 3.3 Authenticity

Ensure that:

- an agent can be distinguished from an unauthenticated or unknown participant;
- the C2 communicates with the intended agent;
- messages can be associated with the correct communication context.

The exact authentication model remains an open architectural point and is tracked in `DECISIONS.md`.

### 3.4 Authorization

Ensure that an authenticated participant is not automatically allowed to perform every possible operation.

Authorization considerations apply to:

- operator actions;
- task creation;
- agent management;
- file-transfer operations;
- sensitive task types;
- administrative functions.

### 3.5 Availability

Protect against conditions that could prevent legitimate operation of:

- the C2 server;
- communication sessions;
- task management;
- file transfers;
- persistent storage;
- agents.

### 3.6 Accountability

Important actions should produce sufficient logs or records to answer:

- what happened;
- when it happened;
- which agent was involved;
- which task or transfer was involved;
- whether the operation succeeded or failed.

Logging must avoid unnecessarily exposing secrets or sensitive data.

---

## 4. Assets

The following assets are considered security-relevant.

| Asset | Description | Main security properties |
|---|---|---|
| C2 server | Central application managing agents and tasks | Confidentiality, Integrity, Availability |
| Agent | Endpoint component communicating with the C2 | Integrity, Authenticity, Availability |
| Agent identity | Logical identity associated with an agent | Authenticity, Integrity |
| Session state | Communication state associated with an agent session | Integrity, Authenticity |
| Tasks | Instructions created for agents | Integrity, Authorization, Accountability |
| Results | Data returned by agents | Confidentiality, Integrity, Accountability |
| File contents | Files transferred between C2 and agents | Confidentiality, Integrity |
| File-transfer metadata | Transfer identifiers, state, size, hashes, etc. | Integrity, Accountability |
| Database | Persistent structured application data | Confidentiality, Integrity, Availability |
| File storage | Persistent and temporary file workspace | Confidentiality, Integrity, Availability |
| Protocol messages | Application-level messages exchanged between parties | Integrity, Authenticity |
| Transport channel | Network communication path | Confidentiality, Integrity, Authenticity |
| Cryptographic material | Certificates, keys, and related secrets | Confidentiality, Integrity |
| Configuration | Server and agent configuration | Confidentiality, Integrity |
| Logs | Operational and security-relevant events | Integrity, Confidentiality |
| Operator interface | Interface through which actions are requested | Authenticity, Authorization |

---

## 5. Trust boundaries

A trust boundary exists wherever data or control crosses from one security context into another.

The main boundaries are:

```text
┌─────────────────────────────────────────────────────────┐
│                    Operator Context                     │
│                                                         │
│  Operator → Operator Interface                         │
└─────────────────────────┬───────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────┐
│                    C2 Application                       │
│                                                         │
│  Interface → Core → Protocol → Transport               │
└─────────────────────────┬───────────────────────────────┘
                          │
                          │ Network / TLS Boundary
                          ▼
┌─────────────────────────────────────────────────────────┐
│                     Agent Context                       │
│                                                         │
│  Transport → Protocol → Core → Executor → Commands     │
└─────────────────────────────────────────────────────────┘
```

Additional trust boundaries exist around persistent storage:

```text
C2 Core
   │
   ├── Database Interface → Database
   │
   └── File Storage Interface → Filesystem
```

and on the agent:

```text
Agent Core
   │
   ├── Executor → Command / Platform
   │
   └── File Storage Interface → Agent Filesystem
```

The existence of a TLS connection does **not** make received application data trustworthy. Transport protection and application-level validation are separate responsibilities.

---

## 6. Attack surfaces

The primary attack surfaces are:

### 6.1 Operator interface

The operator interface is an entry point for actions affecting the C2.

Potential concerns include:

- invalid operator input;
- unauthorized actions;
- unsafe parameter handling;
- command or task parameter injection;
- accidental execution of sensitive operations;
- information disclosure through interface output.

---

### 6.2 Network transport

The transport layer exposes the C2 and agents to communication-related risks.

Potential concerns include:

- unauthorized connection attempts;
- traffic interception;
- message alteration;
- replay;
- connection exhaustion;
- malformed network data;
- session disruption.

The current architecture uses **TCP/TLS** as the MVP transport.

---

### 6.3 Application protocol

The protocol is an important security boundary because network data must be converted into structured application objects.

Potential concerns include:

- malformed messages;
- invalid message types;
- missing required fields;
- invalid identifiers;
- unexpected values;
- inconsistent state transitions;
- replayed messages;
- duplicated messages;
- oversized messages;
- ambiguous serialization.

Protocol validation must therefore occur independently of transport security.

---

### 6.4 Agent identity and registration

Registration and identity management create a security boundary between known and unknown participants.

Potential concerns include:

- impersonation;
- unauthorized registration;
- identity duplication;
- stolen or reused credentials;
- incorrect association between an agent and a session;
- stale identities.

The exact authentication model remains unresolved and is tracked separately as an architectural decision.

---

### 6.5 Task management

Tasks are security-sensitive because they represent requested actions.

Potential concerns include:

- unauthorized task creation;
- tampered task parameters;
- execution of unintended task types;
- task replay;
- duplicate execution;
- invalid state transitions;
- task/result mismatch;
- denial of service through excessive task creation.

---

### 6.6 Agent execution

The agent crosses from communication handling into endpoint execution.

Potential concerns include:

- unsafe command parameters;
- uncontrolled command execution;
- incorrect command dispatch;
- platform-specific implementation errors;
- execution under excessive privileges;
- malformed task handling;
- denial of service;
- unintended filesystem effects.

The communication layer should not execute commands directly. Tasks should pass through the executor and command layers.

---

### 6.7 File transfer

File handling introduces both content-related and filesystem-related risks.

Potential concerns include:

- malicious or malformed file metadata;
- path traversal;
- unauthorized filesystem access;
- file overwrite;
- incomplete transfers;
- corrupted chunks;
- insufficient size limits;
- temporary-file accumulation;
- transfer-state inconsistencies;
- integrity failures;
- information disclosure.

The controlled workspace model exists specifically to reduce the risk of unrestricted filesystem access.

---

### 6.8 Persistent storage

The database and file storage contain potentially sensitive operational information.

Potential concerns include:

- unauthorized access;
- unauthorized modification;
- corruption;
- accidental deletion;
- local privilege abuse;
- leakage through backups or development artifacts;
- inconsistent state between metadata and physical files.

The database and file storage are therefore treated separately even though both are persistence mechanisms.

---

### 6.9 Configuration and secrets

Configuration may contain security-sensitive information.

Potential concerns include:

- exposed credentials;
- exposed private keys;
- insecure defaults;
- accidental repository commits;
- excessive permissions;
- configuration tampering;
- inconsistent configuration between environments.

Secrets and private material must remain outside source-controlled project data.

---

### 6.10 Logging

Logs provide accountability but can themselves become a security risk.

Potential concerns include:

- logging secrets;
- logging authentication material;
- sensitive file contents;
- excessive information disclosure;
- unauthorized log modification;
- insufficient timestamps or identifiers;
- excessive logging causing storage exhaustion.

---

## 7. Threat categories

The project can be analysed using common security threat categories.

| Category | Example concern |
|---|---|
| Spoofing / Impersonation | An unauthorized participant presents itself as an existing agent |
| Tampering | A task, result, or file-transfer message is modified |
| Repudiation | An important action cannot be reliably associated with its source |
| Information Disclosure | Sensitive stored or transmitted data is exposed |
| Denial of Service | Resources are exhausted and legitimate operation is disrupted |
| Elevation of Privilege | A component performs actions beyond its intended authority |

These categories provide a structured way to classify the more specific threats below.

---

# 8. Threat catalogue

## TM-001 — Unauthorized C2 connection

**Description:**  
An unknown participant attempts to establish communication with the C2 server.

**Affected assets:**

- C2 server;
- sessions;
- agent management;
- task management.

**Security properties:** Authenticity, Availability.

**Potential impact:**

- unauthorized interaction;
- resource consumption;
- false sessions;
- manipulation attempts.

**Required considerations:**

- connection validation;
- authentication;
- session validation;
- connection limits;
- logging.

**Status:** Open pending final authentication/session design.

---

## TM-002 — Agent impersonation

**Description:**  
An unauthorized participant attempts to act as a legitimate agent.

**Affected assets:**

- agent identity;
- sessions;
- tasks;
- results.

**Security properties:** Authenticity, Integrity.

**Potential impact:**

- false agent state;
- unauthorized task interaction;
- false results;
- operational confusion.

**Required considerations:**

- strong agent authentication;
- identity validation;
- session binding;
- protection against credential reuse.

**Status:** Open.

---

## TM-003 — Message tampering

**Description:**  
A protocol message is modified between its creation and its processing.

**Affected assets:**

- tasks;
- results;
- protocol messages;
- file-transfer metadata.

**Security properties:** Integrity, Authenticity.

**Potential impact:**

- incorrect task execution;
- corrupted results;
- invalid transfer state;
- inconsistent application state.

**Required considerations:**

- TLS;
- protocol validation;
- message correlation;
- appropriate integrity/authentication mechanisms.

---

## TM-004 — Message replay

**Description:**  
A previously valid message is received again and incorrectly processed as a new message.

**Affected assets:**

- tasks;
- results;
- sessions;
- file transfers.

**Security properties:** Integrity, Authenticity.

**Potential impact:**

- duplicate task processing;
- incorrect state transitions;
- duplicate file operations;
- inconsistent state.

**Required considerations:**

- unique message identifiers;
- task identifiers;
- transfer identifiers;
- state validation;
- replay detection where appropriate.

**Status:** Design detail to be finalized in the protocol specification.

---

## TM-005 — Malformed protocol message

**Description:**  
The C2 or agent receives a syntactically valid transport payload that does not conform to the expected application protocol.

Examples include:

- missing fields;
- invalid types;
- invalid identifiers;
- unsupported message types;
- impossible state combinations.

**Affected assets:**

- protocol processing;
- application stability;
- task/session state.

**Security properties:** Integrity, Availability.

**Potential impact:**

- application errors;
- crashes;
- inconsistent state;
- denial of service.

**Required considerations:**

- schema validation;
- strict parsing;
- length limits;
- rejection of unsupported structures;
- safe error handling.

---

## TM-006 — Unauthorized task creation

**Description:**  
An unauthorized operator or compromised component creates tasks that should not be executed.

**Affected assets:**

- tasks;
- agents;
- endpoint execution.

**Security properties:** Authorization, Integrity.

**Potential impact:**

- unintended endpoint operations;
- resource consumption;
- violation of project scope.

**Required considerations:**

- operator authentication;
- authorization;
- task validation;
- controlled task types;
- audit logging.

---

## TM-007 — Task parameter manipulation

**Description:**  
Task parameters are modified or incorrectly interpreted before execution.

**Affected assets:**

- task data;
- agent execution.

**Security properties:** Integrity.

**Potential impact:**

- execution of unintended operations;
- malformed behavior;
- filesystem or process side effects.

**Required considerations:**

- protocol validation;
- parameter validation;
- command-specific validation;
- clear separation between task creation and execution.

---

## TM-008 — Duplicate task execution

**Description:**  
A task is processed more than once when it should only be executed once.

**Affected assets:**

- tasks;
- endpoint state;
- results.

**Security properties:** Integrity, Availability.

**Potential impact:**

- duplicated side effects;
- inconsistent results;
- unnecessary resource consumption.

**Required considerations:**

- unique task identifiers;
- state tracking;
- idempotency where appropriate;
- duplicate detection.

---

## TM-009 — Task/result confusion

**Description:**  
A result is incorrectly associated with the wrong task or agent.

**Affected assets:**

- task records;
- results;
- audit trail.

**Security properties:** Integrity, Accountability.

**Potential impact:**

- incorrect operator information;
- unreliable audit records;
- incorrect application state.

**Required considerations:**

- explicit task and agent identifiers;
- message correlation;
- state validation;
- persistent relationships.

---

## TM-010 — Agent-side execution abuse

**Description:**  
A task reaches the execution layer with parameters or a task type that should not be executed.

**Affected assets:**

- agent;
- endpoint;
- local files;
- processes.

**Security properties:** Integrity, Authorization, Availability.

**Potential impact:**

- unintended endpoint modifications;
- unstable agent behaviour;
- excessive resource usage;
- operations outside the intended laboratory scope.

**Required considerations:**

- task validation;
- explicit command types;
- executor boundary;
- controlled privileges;
- platform-specific validation.

---

## TM-011 — Path traversal or unauthorized file access

**Description:**  
A file operation causes access outside the controlled project workspace.

**Affected assets:**

- agent filesystem;
- C2 filesystem;
- transferred files.

**Security properties:** Confidentiality, Integrity.

**Potential impact:**

- unauthorized file access;
- overwriting unrelated files;
- disclosure of local data;
- unintended filesystem changes.

**Required considerations:**

- path validation;
- controlled file roots;
- canonicalization;
- restriction to approved workspaces.

---

## TM-012 — File-transfer corruption

**Description:**  
A transferred file is incomplete or corrupted during transmission or reconstruction.

**Affected assets:**

- file contents;
- transfer state.

**Security properties:** Integrity.

**Potential impact:**

- unusable file;
- inconsistent stored data;
- incorrect subsequent processing.

**Required considerations:**

- chunk tracking;
- transfer state;
- end-of-transfer validation;
- cryptographic hash verification;
- cleanup of incomplete transfers.

---

## TM-013 — Malicious or excessive file transfer

**Description:**  
An unexpectedly large, malformed, or otherwise resource-intensive transfer consumes excessive system resources.

**Affected assets:**

- memory;
- disk space;
- network resources;
- transfer processing.

**Security properties:** Availability.

**Potential impact:**

- disk exhaustion;
- memory pressure;
- service degradation;
- transfer failures.

**Required considerations:**

- file-size limits;
- chunk-size limits;
- resource management;
- temporary-file cleanup;
- transfer timeouts.

---

## TM-014 — Temporary-file accumulation

**Description:**  
Incomplete or failed transfers leave temporary data behind.

**Affected assets:**

- local storage;
- file workspace.

**Security properties:** Availability, Confidentiality.

**Potential impact:**

- disk exhaustion;
- exposure of partially reconstructed files;
- inconsistent storage.

**Required considerations:**

- cleanup policies;
- transfer timeout handling;
- bounded temporary storage;
- safe failure recovery.

---

## TM-015 — Persistent data corruption

**Description:**  
Database or file-storage state becomes inconsistent or corrupted.

**Affected assets:**

- database;
- file storage;
- agent/session/task records.

**Security properties:** Integrity, Availability.

**Potential impact:**

- loss of operational state;
- incorrect task history;
- unusable transferred files;
- recovery difficulties.

**Required considerations:**

- transactional database operations where appropriate;
- integrity checks;
- controlled storage interfaces;
- backup/recovery considerations.

---

## TM-016 — Storage confidentiality breach

**Description:**  
An unauthorized local user or process accesses persistent C2 or agent data.

**Affected assets:**

- database;
- transferred files;
- logs;
- configuration;
- credentials.

**Security properties:** Confidentiality.

**Potential impact:**

- disclosure of operational information;
- disclosure of transferred data;
- exposure of sensitive configuration.

**Required considerations:**

- filesystem permissions;
- restricted workspaces;
- secure configuration;
- appropriate handling of logs and local data.

---

## TM-017 — Cryptographic material exposure

**Description:**  
Private keys, credentials, certificates containing sensitive material, or other secrets become accessible to unauthorized parties.

**Affected assets:**

- cryptographic material;
- authentication mechanisms;
- transport security.

**Security properties:** Confidentiality, Authenticity.

**Potential impact:**

- impersonation;
- loss of transport trust;
- unauthorized access.

**Required considerations:**

- secrets outside source control;
- restricted filesystem permissions;
- secure configuration;
- appropriate key lifecycle management.

---

## TM-018 — Sensitive information disclosure through logs

**Description:**  
Logs contain more sensitive information than necessary.

Potential examples include:

- credentials;
- private keys;
- complete file contents;
- sensitive task parameters.

**Affected assets:**

- logs;
- credentials;
- operational data.

**Security properties:** Confidentiality.

**Potential impact:**

- secondary information disclosure;
- easier compromise of the project environment.

**Required considerations:**

- log sanitization;
- minimum necessary logging;
- explicit separation between debugging and operational logs.

---

## TM-019 — Logging manipulation or loss

**Description:**  
Security-relevant events are modified, deleted, or never recorded.

**Affected assets:**

- audit trail;
- incident analysis;
- accountability.

**Security properties:** Integrity, Accountability.

**Potential impact:**

- inability to reconstruct events;
- unreliable troubleshooting;
- reduced confidence in the system state.

**Required considerations:**

- centralized logging;
- timestamps;
- correlation identifiers;
- controlled access to logs.

---

## TM-020 — Denial of service against task management

**Description:**  
An excessive number of sessions, tasks, messages, or transfers consumes server or agent resources.

**Affected assets:**

- C2 server;
- agent;
- queues;
- database;
- network resources.

**Security properties:** Availability.

**Potential impact:**

- degraded responsiveness;
- queue exhaustion;
- storage exhaustion;
- failure to process legitimate work.

**Required considerations:**

- bounded queues;
- limits;
- timeouts;
- resource monitoring;
- cleanup mechanisms.

---

## TM-021 — Session confusion

**Description:**  
Communication belonging to one session is incorrectly associated with another session or agent identity.

**Affected assets:**

- session manager;
- agent identity;
- tasks;
- results.

**Security properties:** Integrity, Authenticity.

**Potential impact:**

- task misdelivery;
- incorrect result association;
- incorrect agent state.

**Required considerations:**

- clear distinction between agent identity and session identity;
- session identifiers;
- state validation;
- message correlation.

---

## TM-022 — Beacon abuse or unreliable communication state

**Description:**  
Beaconing or communication timing produces incorrect assumptions about agent availability.

**Affected assets:**

- agent state;
- task queue;
- session state.

**Security properties:** Availability, Integrity.

**Potential impact:**

- incorrect online/offline state;
- unnecessary retries;
- delayed tasks;
- stale information.

**Required considerations:**

- explicit session and beacon state;
- timestamps;
- timeout policies;
- controlled retry behavior.

---

## TM-023 — Unsafe `SELF_DESTRUCT` behavior

**Description:**  
The `SELF_DESTRUCT` capability performs more actions than intended or affects data outside the defined project scope.

**Affected assets:**

- agent process;
- local temporary data;
- project workspace;
- persistence.

**Security properties:** Integrity, Availability.

**Potential impact:**

- unintended deletion;
- loss of evidence or project data;
- unstable endpoint state;
- accidental destruction outside the intended scope.

The exact meaning of `SELF_DESTRUCT` is deliberately unresolved.

Possible scopes currently under consideration are:

```text
Option A
Process termination only

Option B
Process termination + temporary cleanup

Option C
Process termination + project workspace cleanup

Option D
Full agent removal / persistence cleanup
```

No option should be treated as final until the decision recorded in `DECISIONS.md` is accepted.

**Required considerations:**

- explicit scope;
- controlled paths;
- confirmation/authorization where appropriate;
- bounded cleanup;
- dedicated tests;
- clear documentation of the selected behavior.

**Status:** Open — see `PRO-006` in [`../DECISIONS.md`](../DECISIONS.md).

---

## 9. Threat prioritization

Threats should not all be treated as equally critical.

The project can use a simple qualitative assessment based on:

- **Likelihood** — how plausible the threat is in the intended environment;
- **Impact** — consequences if the threat occurs.

A simple model is:

```text
Risk = Likelihood × Impact
```

A qualitative scale can be used:

| Level | Meaning |
|---|---|
| Low | Limited consequence and/or low likelihood |
| Medium | Meaningful consequence or realistic likelihood |
| High | Significant consequence and realistic attack opportunity |
| Critical | Severe consequence combined with a credible attack opportunity |

Risk ratings should remain contextual to the academic laboratory environment.

---

## 10. Initial threat prioritization

The following initial prioritization can guide implementation and testing.

| ID | Threat | Initial priority |
|---|---|---|
| TM-001 | Unauthorized C2 connection | High |
| TM-002 | Agent impersonation | High |
| TM-003 | Message tampering | High |
| TM-004 | Message replay | Medium |
| TM-005 | Malformed protocol message | High |
| TM-006 | Unauthorized task creation | High |
| TM-007 | Task parameter manipulation | High |
| TM-008 | Duplicate task execution | Medium |
| TM-009 | Task/result confusion | Medium |
| TM-010 | Agent-side execution abuse | High |
| TM-011 | Path traversal / unauthorized file access | High |
| TM-012 | File-transfer corruption | High |
| TM-013 | Malicious / excessive file transfer | Medium |
| TM-014 | Temporary-file accumulation | Medium |
| TM-015 | Persistent data corruption | Medium |
| TM-016 | Storage confidentiality breach | High |
| TM-017 | Cryptographic material exposure | High |
| TM-018 | Sensitive information through logs | Medium |
| TM-019 | Logging manipulation or loss | Medium |
| TM-020 | Denial of service | Medium |
| TM-021 | Session confusion | High |
| TM-022 | Beacon / communication-state abuse | Medium |
| TM-023 | Unsafe `SELF_DESTRUCT` | High |

These ratings are an initial baseline and should be refined as implementation details, authentication, protocol behavior, and deployment assumptions are finalized.

---

## 11. Security boundaries and trust assumptions

The threat model relies on the following assumptions.

### 11.1 Operator environment

The operator is assumed to be authorized to use the C2.

This does not remove the need for:

- input validation;
- authorization checks;
- safe handling of sensitive operations;
- logging.

---

### 11.2 C2 host

The C2 host is assumed to be under the control of the project operator.

However, the application must not assume that every local input is trustworthy.

Examples include:

- operator-supplied parameters;
- locally stored files;
- configuration;
- persisted data.

---

### 11.3 Network

The network is considered **untrusted**.

Security must therefore not depend on the network being private or inaccessible to other parties.

The transport layer is responsible for protecting communication in transit, while the protocol layer validates application data.

---

### 11.4 Agent

The agent is treated as a security-sensitive endpoint component.

The design should not assume that every locally available resource is safe to access.

This is why:

- command execution is separated from communication;
- file storage is restricted to controlled workspaces;
- platform-specific functionality is isolated.

---

### 11.5 Storage

Persistent storage is treated as sensitive.

Access to:

- databases;
- transferred files;
- temporary data;
- logs;
- configuration;

should be restricted according to the project's security requirements.

---

## 12. Security requirements derived from the threat model

The threat analysis leads to several high-level security requirements.

### SR-001 — Secure transport

Communication between C2 and agent must use the selected secure transport mechanism.

**MVP:** TCP/TLS.

---

### SR-002 — Protocol validation

All incoming messages must be validated before being processed by application logic.

Validation must cover at least:

- message structure;
- message type;
- required fields;
- identifier formats;
- permitted values;
- expected state transitions.

---

### SR-003 — Explicit identity validation

Agents must have an explicit identity model.

The exact mechanism must be defined before authentication is considered complete.

---

### SR-004 — Session isolation

Communication state must be associated with the correct session and agent.

An agent identity and a communication session must remain conceptually distinct.

---

### SR-005 — Task integrity

Tasks must be:

- uniquely identifiable;
- associated with an agent;
- validated;
- tracked through their lifecycle;
- associated with their results.

---

### SR-006 — Controlled command execution

The agent must execute operations through the executor and command layers rather than directly from the transport layer.

---

### SR-007 — Controlled file workspace

File operations must remain within explicitly controlled project directories.

---

### SR-008 — File integrity verification

Transferred files must support integrity verification.

The current design intends to use a cryptographic hash such as SHA-256.

---

### SR-009 — Resource limits

The system should define reasonable limits for:

- messages;
- tasks;
- queues;
- file transfers;
- temporary storage;
- timeouts.

---

### SR-010 — Secure secret handling

Sensitive credentials and cryptographic material must:

- remain outside source control;
- have restricted access;
- not be unnecessarily exposed through logs or configuration output.

---

### SR-011 — Security-relevant logging

Important security and operational events should be logged sufficiently for debugging and analysis without unnecessarily exposing sensitive information.

---

### SR-012 — Bounded destructive operations

Sensitive capabilities such as `SELF_DESTRUCT` must have a clearly defined and bounded scope.

---

## 13. Relationship with the architecture

The threat model maps directly onto the architectural boundaries.

```text
Threat
  │
  ├── Operator Interface
  │      └── Input / authorization threats
  │
  ├── Core
  │      └── State / task-management threats
  │
  ├── Protocol
  │      └── Validation / message-integrity threats
  │
  ├── Transport
  │      └── Network / session threats
  │
  ├── Storage
  │      └── Data confidentiality / integrity threats
  │
  ├── File Management
  │      └── Transfer / path / integrity threats
  │
  └── Agent Execution
         └── Endpoint execution threats
```

This is one of the reasons the project maintains clear separation between:

- interface;
- core;
- protocol;
- transport;
- storage;
- execution;
- platform-specific functionality.

A security boundary that is difficult to isolate architecturally is also more difficult to test and protect.

---

## 14. Relationship with the Kill Chain analysis

The threat model identifies **what can go wrong** from a security perspective.

The Kill Chain analysis will provide a different view:

> Which project capabilities correspond to which phases of an attack lifecycle?

The two analyses should therefore not duplicate each other.

```text
Threat Model
"What threats exist?"
        │
        ▼
Kill Chain Analysis
"How do relevant capabilities map to an attack lifecycle?"
        │
        ▼
Countermeasures
"How are those risks reduced?"
```

---

## 15. Relationship with countermeasures

Each significant threat should eventually have one of three outcomes:

1. a concrete security control;
2. an explicit accepted risk;
3. a documented decision that the threat is outside project scope.

The intended relationship is:

```text
Threat
   ↓
Risk
   ↓
Countermeasure / Accepted Risk / Out of Scope
   ↓
Implementation
   ↓
Test
```

The detailed mapping will be maintained in [`countermeasures.md`](countermeasures.md).

---

## 16. Open security decisions

Several points remain open and should not be treated as finalized:

| Decision | Related threat(s) | Status |
|---|---|---|
| Exact agent authentication model | TM-001, TM-002 | Open |
| Exact protocol contract | TM-003, TM-004, TM-005 | Open |
| Session state machine | TM-021, TM-022 | Open |
| Detailed database schema | TM-009, TM-015 | Open |
| Detailed asynchronous behavior | TM-008, TM-020, TM-022 | Open |
| `SELF_DESTRUCT` scope | TM-023 | Open |

These correspond to the proposed decisions already tracked in [`../DECISIONS.md`](../DECISIONS.md).

---

## 17. Testing implications

Each important threat should result in one or more validation activities.

Examples include:

| Threat | Example validation focus |
|---|---|
| TM-001 | Unauthorized connection rejection |
| TM-002 | Agent identity validation |
| TM-003 | Message integrity and validation |
| TM-004 | Duplicate/replay handling |
| TM-005 | Malformed message rejection |
| TM-006 | Task authorization |
| TM-007 | Parameter validation |
| TM-008 | Duplicate task handling |
| TM-009 | Task/result correlation |
| TM-010 | Executor boundary validation |
| TM-011 | Workspace/path restrictions |
| TM-012 | File integrity verification |
| TM-013 | File-size/resource limits |
| TM-014 | Temporary-file cleanup |
| TM-015 | Persistent state consistency |
| TM-016 | Storage permissions |
| TM-017 | Secret handling |
| TM-018 | Log sanitization |
| TM-019 | Logging integrity/availability |
| TM-020 | Resource and queue limits |
| TM-021 | Session isolation |
| TM-022 | Beacon/session state handling |
| TM-023 | Bounded `SELF_DESTRUCT` behavior |

The detailed testing methodology belongs in [`testing-strategy.md`](testing-strategy.md).

---

## 18. Out-of-scope assumptions

The following are outside the primary scope of this academic project unless explicitly introduced later:

- protecting an enterprise-wide production infrastructure;
- guaranteeing security against a fully compromised operating system;
- eliminating all host-level vulnerabilities;
- implementing every possible transport;
- implementing every possible authentication mechanism;
- providing unrestricted endpoint management;
- reproducing the complete capabilities of a production C2 framework.

The threat model should remain proportional to the project's architecture, requirements, and laboratory context.

---

## 19. Current status

This document represents the **initial threat-model baseline**.

The structure and main threat categories are established, but the analysis will evolve as:

- the authentication model is finalized;
- the protocol contract is finalized;
- the session state machine is defined;
- file-transfer behavior is implemented;
- the network architecture is detailed;
- security controls are implemented and tested.

A threat should therefore not be considered fully addressed merely because it appears in this document.

A threat is considered addressed only when the corresponding control, accepted risk, or scope decision is documented and, where applicable, validated through testing.

---

## 20. Summary

The main security principle of the project is:

> **Do not treat communication, input, execution, or stored data as trusted merely because it comes from another component of the system.**

The architecture therefore establishes distinct security boundaries around:

- operator interaction;
- C2 application logic;
- protocol validation;
- network transport;
- persistent storage;
- file handling;
- agent execution.

The threat model provides the security baseline from which the project can proceed toward:

```text
Threat Model
      ↓
Network Architecture
      ↓
Kill Chain Analysis
      ↓
Countermeasures
      ↓
Implementation
      ↓
Security Testing
```

All future security decisions should remain consistent with this model or explicitly document why an existing assumption has changed.
