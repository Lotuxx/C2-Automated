# Testing Strategy

> **Status: Work in Progress**
>
> This document describes the current testing strategy for C2-AUTOMATED.
> Test levels, scenarios, and tooling may evolve as the architecture and
> implementation are finalized.

---

# 1. Purpose

The purpose of this document is to define how the C2-AUTOMATED project will
be verified throughout development.

Testing should not only verify that individual functions work. It should also
verify that:

- architectural boundaries are respected;
- components communicate correctly;
- the C2 server can manage multiple agents;
- tasks can progress through their expected lifecycle;
- results are correctly associated with tasks;
- file transfers work correctly;
- communication is protected;
- malformed or unexpected input is handled safely.

The testing strategy therefore covers multiple levels, from individual
components to complete C2-Agent scenarios.

---

# 2. Testing Principles

## 2.1 Test Before Integration

A component should be tested as independently as practical before being
integrated with the rest of the system.

```text
Implementation
     ↓
Component Tests
     ↓
Integration
```

This makes failures easier to locate.

---

## 2.2 Test Architectural Boundaries

The project relies on clear boundaries between:

```text
Interface
   ↓
Core
   ↓
Protocol
   ↓
Transport
```

and:

```text
Core
   ↓
Storage Interface
   ↓
Storage Implementation
```

Tests should verify these boundaries rather than only testing internal
functions.

---

## 2.3 Test Normal and Failure Behaviour

Tests should cover both:

```text
Expected behaviour
```

and:

```text
Invalid input
Communication failure
Unexpected state
Incomplete operation
```

A component should not only work when everything goes as expected.

---

# 3. Test Levels

The current strategy uses five main levels:

```text
Unit Tests
    ↓
Component Tests
    ↓
Integration Tests
    ↓
C2 ↔ Agent Tests
    ↓
End-to-End Tests
```

Each level has a different purpose.

---

# 4. Unit Tests

Unit tests verify small pieces of functionality independently.

Examples include:

```text
Protocol message validation
Task state transitions
Identifier handling
File path validation
Hash calculation
Configuration parsing
Serialization / deserialization
```

The objective is to determine whether a small unit behaves correctly without
requiring the complete system.

---

# 5. Component Tests

Component tests verify a complete subsystem while isolating external
dependencies where appropriate.

Examples:

```text
AgentManager
SessionManager
TaskManager
ResultManager
FileManager
Protocol layer
Storage layer
Agent Executor
Command handlers
Platform abstraction
```

For example, the Task Manager should be testable without requiring a live
network connection.

Likewise, the File Manager should be testable using a controlled storage
backend.

---

# 6. Integration Tests

Integration tests verify that several components interact correctly.

Examples include:

```text
Interface → C2 Core
C2 Core → Task Manager
Task Manager → Protocol
Protocol → Transport
Core → Database Storage
File Manager → File Storage
Executor → Command Handler
```

These tests are particularly important because the system is deliberately
modular.

A component may pass all of its unit tests while still failing because its
interface with another component is incorrect.

---

# 7. C2-Agent Communication Tests

The C2 server and agent must be tested together in the laboratory environment.

The communication path is:

```text
C2 Application Logic
       ↓
C2 Protocol
       ↓
C2 Transport
       ↓
Network
       ↓
Agent Transport
       ↓
Agent Protocol
       ↓
Agent Application Logic
```

Communication tests should verify that the two sides correctly interpret the
same logical protocol.

Initial scenarios include:

- agent registration;
- beacon communication;
- task delivery;
- result delivery;
- error handling;
- file-transfer messages.

---

# 8. Multi-Agent Tests

Multi-agent operation is a core architectural requirement.

Testing must therefore include scenarios with multiple independent agents.

For example:

```text
                 C2 SERVER
                     │
          ┌──────────┼──────────┐
          ▼          ▼          ▼
        Agent A    Agent B    Agent C
          │          │          │
        Task A      Task B     Task C
```

The tests should verify that:

- agents remain logically distinguishable;
- sessions remain associated with the correct agents;
- tasks are assigned to the correct agents;
- results are associated with the correct tasks;
- activity from one agent does not incorrectly affect another agent;
- the server can process independent agent activity concurrently.

---

# 9. Session Tests

The Agent / Session distinction must be explicitly tested.

A basic scenario is:

```text
Agent A001
    │
    ▼
Session S01
    │
    ▼
disconnect
    │
    ▼
Session S02
```

Tests should verify that:

- the agent identity remains consistent;
- session state changes correctly;
- a disconnected session does not remain incorrectly active;
- a new session can be associated with the existing agent;
- session information is not accidentally assigned to another agent.

The exact session state machine remains to be finalized.

---

# 10. Task Lifecycle Tests

The current task lifecycle is:

```text
PENDING
   ↓
 SENT
   ↓
RUNNING
   ├──► FAILED
   ↓
COMPLETED
```

Tests should verify valid transitions.

Examples:

```text
PENDING → SENT
SENT → RUNNING
RUNNING → COMPLETED
RUNNING → FAILED
```

Invalid transitions should also be tested.

For example, the implementation should not allow arbitrary state changes that
break the task lifecycle.

Detailed task behaviour is documented in
[`task-lifecycle.md`](task-lifecycle.md).

---

# 11. Result Association Tests

Results must be associated with the correct task.

A basic scenario is:

```text
Agent A001
   │
   └── Task T004
          │
          └── Result R009
```

Tests should verify that:

- the correct task is identified;
- the correct agent is identified;
- the result is stored correctly;
- unrelated results cannot silently replace another task's result;
- malformed or unexpected results are rejected appropriately.

---

# 12. Protocol Tests

Protocol tests verify the logical communication contract.

The current message types include:

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

Tests should verify:

### Valid messages

Valid messages can be serialized, transmitted, deserialized, validated, and
processed correctly.

### Invalid messages

Invalid messages are rejected when they contain problems such as:

- missing required fields;
- invalid message types;
- invalid identifiers;
- malformed structures;
- unsupported protocol versions;
- invalid payloads.

The exact validation rules will be refined as the protocol specification is
finalized.

---

# 13. Serialization Tests

Serialization must preserve the information required by the protocol.

Tests should verify:

```text
Object
  ↓
Serialize
  ↓
Transmitted Representation
  ↓
Deserialize
  ↓
Equivalent Object
```

The exact serialization format is not yet finalized.

Once selected, serialization tests should cover all supported message types.

---

# 14. Transport Tests

Transport tests verify the network communication mechanism independently from
the application protocol.

For the MVP, the transport is TCP/TLS.

Tests should verify:

- successful connection establishment;
- successful message transmission;
- connection closure;
- communication failure handling;
- TLS configuration;
- certificate verification behaviour once finalized;
- rejection of unacceptable TLS conditions.

The transport should not need to understand the meaning of individual
application messages.

---

# 15. Storage Tests

Storage tests cover both structured data and file storage.

## 15.1 Database

Tests should verify operations involving:

```text
agents
sessions
tasks
results
file transfers
```

where applicable.

The tests should verify correct creation, retrieval, update, and persistence
behaviour.

## 15.2 File Storage

Tests should verify:

- file creation;
- file retrieval;
- chunk writing;
- file reconstruction;
- temporary-file handling;
- cleanup behaviour;
- invalid-path rejection.

Storage should be tested through its defined interfaces where practical.

---

# 16. File-Transfer Tests

File transfer spans several architectural components and therefore requires
dedicated testing.

The conceptual flow is:

```text
File
 ↓
File Manager
 ↓
Protocol
 ↓
TLS Transport
 ↓
Remote Protocol
 ↓
File Manager
 ↓
Temporary File
 ↓
Integrity Verification
 ↓
Final File
```

Tests should include:

### Small file

Verify complete transfer of a small test file.

### Larger file

Verify incremental transfer without requiring the entire file to remain in
memory.

### Multiple chunks

Verify reconstruction from several chunks.

### Interrupted transfer

Verify that an incomplete transfer does not become a valid final file.

### Invalid transfer

Verify that malformed transfer metadata or invalid chunks are rejected.

### Integrity failure

Modify or otherwise invalidate the expected content and verify that the
integrity check detects the mismatch.

### Cleanup

Verify that temporary artifacts are removed or handled according to the
defined failure policy.

Detailed transfer behaviour is documented in
[`file-transfer.md`](file-transfer.md).

---

# 17. Agent Execution Tests

The agent execution path is:

```text
TASK
  ↓
Protocol Validation
  ↓
Executor
  ↓
Command Handler
  ↓
Platform-specific Implementation
  ↓
Result
```

Tests should verify that:

- valid tasks reach the correct executor;
- commands receive the expected parameters;
- unsupported commands are rejected;
- invalid parameters are rejected appropriately;
- execution failures produce controlled results;
- platform-specific implementations remain separated.

---

# 18. Platform Tests

Linux is the primary target platform.

Windows support is considered an extension.

Platform-specific tests should therefore verify that:

```text
Common Logic
    ↓
Platform Abstraction
    ↓
Linux Implementation
```

works correctly.

When Windows support is implemented, corresponding tests can be added:

```text
Common Logic
    ↓
Platform Abstraction
    ├── Linux
    └── Windows
```

Platform-specific behaviour should not be tested only through the complete
system; relevant platform components should also have isolated tests.

---

# 19. Security Tests

Security testing verifies the controls described in [`SECURITY.md`](../SECURITY.md).

Initial categories include:

### Transport Security

Verify that C2-Agent communication uses the intended TLS configuration.

### Protocol Validation

Verify that malformed or invalid messages are rejected.

### Task Validation

Verify that invalid task structures and parameters are not executed.

### File Security

Verify:

- path restrictions;
- temporary-file handling;
- file-integrity verification;
- invalid transfer rejection.

### Configuration

Verify that sensitive local configuration is not accidentally exposed or
committed.

### Logging

Verify that sensitive values are not unnecessarily written to logs.

---

# 20. End-to-End Tests

End-to-end tests verify complete user scenarios.

A basic scenario is:

```text
Operator
   ↓
CLI
   ↓
C2 Core
   ↓
Task Manager
   ↓
Protocol
   ↓
TLS Transport
   ↓
Agent
   ↓
Executor
   ↓
Command
   ↓
Result
   ↓
C2
   ↓
Operator
```

Example end-to-end scenarios include:

- starting the C2 server;
- starting one or more laboratory agents;
- registering an agent;
- viewing the agent from the operator interface;
- creating a task;
- executing the task;
- receiving the result;
- storing the result;
- displaying the result to the operator.

A complete file-transfer scenario should similarly verify the complete
transfer lifecycle.

---

# 21. Regression Testing

Existing functionality should be re-tested when changes affect shared
components.

Particular attention should be given to changes involving:

```text
Protocol
Transport
Task Manager
Session Manager
Storage Interfaces
File Manager
Executor
Platform Abstraction
```

A change to a shared component can affect several other parts of the system.

---

# 22. Test Data

Testing should use controlled laboratory data.

Examples include:

```text
small text files
binary test files
files containing multiple chunks
invalid protocol messages
invalid task parameters
simulated communication failures
```

Test data should not contain unnecessary personal or sensitive information.

---

# 23. Test Environment

Testing should take place in an authorized and controlled laboratory
environment.

A typical environment may contain:

```text
┌─────────────────────┐
│      C2 Server      │
│                     │
│  C2 + Database      │
└──────────┬──────────┘
           │
        TCP/TLS
           │
     ┌─────┴─────┐
     ▼           ▼
┌─────────┐  ┌─────────┐
│ Agent A │  │ Agent B │
└─────────┘  └─────────┘
```

The final laboratory topology will be documented in
[`network-architecture.md`](network-architecture.md).

---

# 24. Test Organization

Tests should be organized so that they remain associated with the component
or subsystem they verify.

The current project structure provides dedicated test directories:

```text
c2_server/tests/
agent/tests/
```

As the implementation grows, tests may be grouped by type or component.

For example:

```text
tests/
├── unit/
├── component/
├── integration/
└── e2e/
```

The exact test-directory structure can be refined during implementation.

---

# 25. Test Results and Validation

A successful test should provide evidence that the intended behaviour works.

Where practical, tests should make it possible to answer:

```text
What was tested?
What was expected?
What actually happened?
Did the test pass?
```

For important project milestones, the validated functionality should be
recorded so that the state of the project can be reproduced and demonstrated.

---

# 26. Requirements Traceability

Testing should ultimately be connected to project requirements.

Conceptually:

```text
Requirement
    ↓
Architecture
    ↓
Implementation
    ↓
Test
```

For example:

```text
Multi-agent requirement
        ↓
AgentManager + SessionManager
        ↓
Implementation
        ↓
Multi-agent integration test
```

The detailed mapping between requirements and validation is maintained in
[`requirements-mapping.md`](requirements-mapping.md).

---

# 27. Current Testing Priorities

The initial testing priorities are:

1. protocol validation and serialization;
2. task lifecycle;
3. session and agent management;
4. C2-Agent communication;
5. file transfer and integrity;
6. multi-agent operation;
7. end-to-end scenarios;
8. security controls.

These priorities may change as implementation dependencies become clearer.

---

# 28. Open Questions

The following testing decisions remain to be finalized:

- exact testing framework and tooling;
- exact test directory organization;
- exact concurrency-testing strategy;
- network-failure simulation;
- TLS test setup;
- session reconnection scenarios;
- task timeout and retry tests;
- detailed file-transfer failure scenarios;
- test fixtures and reusable laboratory environments;
- automated end-to-end execution;
- test coverage targets.

These should be progressively resolved as implementation begins.
