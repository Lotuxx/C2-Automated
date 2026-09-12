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
- task parameter manipulation;
- accidental execution of sensitive operations;
- information disclosure through interface output.

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

### 6.4 Agent identity and registration

Registration and identity management create a security boundary between known and unknown participants.

Potential concerns include:

- impersonation;
- unauthorized registration;
- identity duplication;
- stolen or reused credentials;
- incorrect association between an agent and a session;
- stale identities.

The exact authentication model remains unresolved and is tracked separately in `DECISIONS.md`.

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

# 7. Risk matrix

The following matrix is the **single source of truth for the current threat catalogue**.

Each risk has:

- a unique identifier;
- a concrete owner;
- an affected area;
- an initial likelihood;
- an impact;
- an overall priority;
- the expected security response;
- a current status.

### Risk levels

Likelihood and impact use:

- **Low**
- **Medium**
- **High**

The initial risk level is determined qualitatively from likelihood and impact.

| ID | Threat | Affected area / asset | Likelihood | Impact | Priority | Risk owner | Primary response | Status |
|---|---|---|---|---|---|---|---|---|
| TM-001 | Unauthorized C2 connection | C2 / sessions | Medium | High | High | C2 / Transport owner | Authentication, connection validation, limits | **Open** |
| TM-002 | Agent impersonation | Agent identity / sessions | Medium | High | High | Identity / Protocol owner | Strong identity validation and session binding | **Open** |
| TM-003 | Message tampering | Protocol / tasks / results | Medium | High | High | Protocol / Transport owner | TLS, validation, message integrity | **Partially addressed** |
| TM-004 | Message replay | Protocol / tasks / results | Medium | Medium | Medium | Protocol owner | Message IDs, state validation, replay handling | **Open** |
| TM-005 | Malformed protocol message | Protocol / application stability | High | High | High | Protocol owner | Strict schema and input validation | **Planned** |
| TM-006 | Unauthorized task creation | Operator / task management | Medium | High | High | C2 / Interface owner | Authentication, authorization, task validation | **Open** |
| TM-007 | Task parameter manipulation | Tasks / endpoint execution | Medium | High | High | Task / Agent owner | Parameter validation and command-specific checks | **Planned** |
| TM-008 | Duplicate task execution | Tasks / endpoint state | Medium | Medium | Medium | Task owner | Task IDs, lifecycle state, duplicate detection | **Open** |
| TM-009 | Task/result confusion | Tasks / results | Low | Medium | Medium | Task / Result owner | Explicit correlation and persistent relationships | **Planned** |
| TM-010 | Agent-side execution abuse | Executor / endpoint | Medium | High | High | Agent / Execution owner | Executor boundary, command validation, bounded privileges | **Planned** |
| TM-011 | Path traversal / unauthorized file access | File storage / filesystem | Medium | High | High | File Transfer / Storage owner | Controlled roots, path validation, canonicalization | **Planned** |
| TM-012 | File-transfer corruption | File contents / transfers | Medium | High | High | File Transfer owner | Chunk tracking and cryptographic hash verification | **Planned** |
| TM-013 | Malicious or excessive file transfer | Disk / memory / network | Medium | Medium | Medium | File Transfer owner | Size limits, resource controls, timeouts | **Open** |
| TM-014 | Temporary-file accumulation | Temporary storage | Medium | Medium | Medium | File Storage owner | Cleanup policy and bounded temporary workspace | **Planned** |
| TM-015 | Persistent data corruption | Database / file storage | Low | High | Medium | Storage owner | Consistency controls, integrity checks, recovery strategy | **Open** |
| TM-016 | Storage confidentiality breach | Database / files / logs | Medium | High | High | Storage owner | Filesystem permissions and restricted workspaces | **Planned** |
| TM-017 | Cryptographic material exposure | Keys / credentials | Medium | High | High | Security owner | Externalized secrets, restricted permissions, key management | **Open** |
| TM-018 | Sensitive information through logs | Logs / sensitive data | Medium | Medium | Medium | Logging / Security owner | Log minimization and sanitization | **Planned** |
| TM-019 | Logging manipulation or loss | Audit trail | Low | Medium | Medium | Logging / Security owner | Controlled logging and access restrictions | **Planned** |
| TM-020 | Denial of service | C2 / queues / storage | Medium | Medium | Medium | C2 / Infrastructure owner | Resource limits, queue bounds, timeouts | **Open** |
| TM-021 | Session confusion | Sessions / tasks / results | Medium | High | High | Session / Protocol owner | Session identifiers and state validation | **Open** |
| TM-022 | Beacon / communication-state abuse | Beacon / sessions | Medium | Medium | Medium | Agent / Communication owner | Explicit state, timestamps, timeout policy | **Open** |
| TM-023 | Unsafe `SELF_DESTRUCT` behavior | Agent / local workspace | Medium | High | High | Agent / Security owner | Explicit bounded scope and dedicated validation | **Open — PRO-006** |

---

## 8. Risk ownership model

Risk ownership represents the **component or responsibility owner expected to drive the mitigation**, not necessarily the person who implements every related change.

The project currently uses the following ownership roles:

| Owner | Main responsibility |
|---|---|
| **C2 / Interface owner** | Operator interaction, authorization, C2-facing behavior |
| **C2 / Transport owner** | Server transport and network-facing controls |
| **Agent / Execution owner** | Agent executor, command handling, endpoint execution |
| **Agent / Communication owner** | Beaconing and agent communication behavior |
| **Protocol owner** | Message structure, validation, correlation, protocol rules |
| **Session owner** | Agent/session association and session lifecycle |
| **Task owner** | Task creation, state, queueing, lifecycle and correlation |
| **Result owner** | Result processing and task/result association |
| **File Transfer owner** | Logical transfer lifecycle and transfer validation |
| **Storage owner** | Database and file persistence security |
| **Logging / Security owner** | Logging controls and security-sensitive operational data |
| **Security owner** | Cross-cutting security requirements and risk review |
| **C2 / Infrastructure owner** | Server resource protection and availability |

A single implementation change may therefore involve multiple owners, but one owner remains accountable for ensuring that the risk is addressed.

---

## 9. Risk status definitions

The status column describes the current state of each risk.

| Status | Meaning |
|---|---|
| **Open** | The threat is identified but the required control or final design has not yet been established or validated. |
| **Planned** | A mitigation approach has been identified and is expected to be implemented. |
| **Partially addressed** | The architecture already provides a relevant control, but the complete mitigation is not yet implemented or validated. |
| **Mitigated** | The required control has been implemented and validated through testing. |
| **Accepted** | The remaining risk has been explicitly accepted as part of the project's scope. |
| **Out of scope** | The threat is explicitly excluded from the project's security objectives. |

A threat should **not** be marked `Mitigated` solely because a control has been designed. Evidence from implementation and testing is required.

---

## 10. Priority interpretation

The priority assigned in the matrix is intended to guide implementation order.

### High

The threat should receive explicit mitigation and testing before the affected feature is considered complete.

Typical examples include:

- authentication and identity;
- protocol validation;
- task integrity;
- endpoint execution boundaries;
- filesystem restrictions;
- cryptographic material;
- session isolation.

### Medium

The threat should be addressed as part of normal implementation and testing but may depend on the completion of higher-priority security work.

Typical examples include:

- replay handling;
- resource limits;
- temporary-file cleanup;
- logging controls;
- availability safeguards.

### Low

No currently identified threat is classified as Low in the initial matrix because the remaining risks are considered relevant to the project's core architecture.

The prioritization can be revised as the system and deployment assumptions become more precise.

---

## 11. Security requirements derived from the threat model

The risk matrix leads to the following high-level security requirements.

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

## 12. Relationship with the architecture

The risk matrix maps directly onto the architectural boundaries.

```text
Threat
  │
  ├── Operator Interface
  │      └── Input / authorization risks
  │
  ├── Core
  │      └── State / task-management risks
  │
  ├── Protocol
  │      └── Validation / message-integrity risks
  │
  ├── Transport
  │      └── Network / session risks
  │
  ├── Storage
  │      └── Data confidentiality / integrity risks
  │
  ├── File Management
  │      └── Transfer / path / integrity risks
  │
  └── Agent Execution
         └── Endpoint execution risks
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

## 13. Relationship with the Kill Chain analysis

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

## 14. Relationship with countermeasures

Each significant risk should eventually have one of three outcomes:

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

## 15. Open security decisions

Several points remain open and should not be treated as finalized:

| Decision | Related risks | Status |
|---|---|---|
| Exact agent authentication model | TM-001, TM-002 | Open |
| Exact protocol contract | TM-003, TM-004, TM-005 | Open |
| Session state machine | TM-021, TM-022 | Open |
| Detailed database schema | TM-009, TM-015 | Open |
| Detailed asynchronous behavior | TM-008, TM-020, TM-022 | Open |
| `SELF_DESTRUCT` scope | TM-023 | Open — `PRO-006` |

These correspond to the proposed decisions already tracked in [`../DECISIONS.md`](../DECISIONS.md).

---

## 16. Testing implications

The risk matrix should drive security testing.

Each High-priority risk must have explicit validation before it can be considered mitigated.

Examples include:

| Risk area | Validation focus |
|---|---|
| Authentication / identity | Unauthorized participant rejection and identity validation |
| Protocol | Malformed-message rejection and message validation |
| Task integrity | Parameter validation, state consistency, duplicate handling |
| Session management | Correct agent/session association |
| Endpoint execution | Executor boundary and command validation |
| File handling | Workspace restrictions and path validation |
| File transfer | Chunk handling and integrity verification |
| Storage | Persistence consistency and access restrictions |
| Secrets | No sensitive material in repository or inappropriate logs |
| Logging | Required events present without unnecessary sensitive data |
| Availability | Queue, timeout, size, and resource limits |
| `SELF_DESTRUCT` | Only the explicitly selected bounded behavior occurs |

The detailed testing methodology belongs in [`testing-strategy.md`](testing-strategy.md).

---

## 17. Risk review process

The threat model should be reviewed whenever a significant project change affects a security assumption.

Examples include:

- introducing a new transport;
- modifying the protocol;
- changing authentication;
- adding a new command type;
- changing file-transfer behavior;
- changing storage;
- introducing a new operator interface;
- changing the agent execution model;
- changing the network deployment model.

The review process should be:

```text
Architecture / feature change
          ↓
Existing risks reviewed
          ↓
New risks identified?
     ┌────┴────┐
    Yes        No
     │          │
     ▼          ▼
Add/update     Keep
risk matrix    current risks
     │
     ▼
Update countermeasures
     │
     ▼
Update testing requirements
```

Risk ownership should also be reassigned when component responsibilities change.

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

The main risk catalogue and ownership model are established, but the matrix will evolve as:

- the authentication model is finalized;
- the protocol contract is finalized;
- the session state machine is defined;
- file-transfer behavior is implemented;
- the network architecture is detailed;
- security controls are implemented and tested.

The matrix is therefore a **living risk register**, not a final declaration that the system is secure.

A risk is considered addressed only when the corresponding control, accepted risk, or scope decision is documented and, where applicable, validated through testing.

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
Threat Model / Risk Register
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
           ↓
Risk Review
```

All future security decisions should remain consistent with this model or explicitly document why an existing assumption has changed.
