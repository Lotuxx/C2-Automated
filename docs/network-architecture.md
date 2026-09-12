# Network Architecture

## 1. Purpose

This document describes the **network architecture** of the C2-AUTOMATED project.

It focuses specifically on how the different system components communicate across the network, where network trust boundaries exist, and how the selected transport fits into the broader architecture.

It complements:

- [`../ARCHITECTURE.md`](../ARCHITECTURE.md) for the overall software architecture;
- [`protocol.md`](protocol.md) for the application-level communication contract;
- [`../SECURITY.md`](../SECURITY.md) for security principles;
- [`threat-model.md`](threat-model.md) for network-related risks;
- [`countermeasures.md`](countermeasures.md) for the corresponding security controls.

This document deliberately does **not** redefine the application protocol or task/file-transfer semantics. Those subjects have dedicated documentation.

---

## 2. Network architecture objectives

The network design has the following objectives:

- provide communication between the C2 server and multiple agents;
- support asynchronous operation;
- separate logical protocol from network transport;
- protect communications in transit;
- maintain clear trust boundaries;
- allow multiple agents to communicate with a single C2 server;
- permit transport extensions without redesigning the application core;
- remain simple enough for the MVP and academic laboratory environment.

The current MVP uses:

> **Agent-initiated TCP over TLS**

The asynchronous communication model is based on **agent-initiated communication opportunities**, represented by the Beacon component.

Other transport mechanisms may be considered later as extensions.

---

## 3. Global network topology

The project follows a centralized C2 model.

```text
                         ┌───────────────────────┐
                         │       Operator        │
                         │      CLI / TUI / Web  │
                         └───────────┬───────────┘
                                     │
                                     │ Local application
                                     ▼
                         ┌───────────────────────┐
                         │      C2 Server        │
                         │                       │
                         │ Interface             │
                         │ Core                  │
                         │ Protocol              │
                         │ Transport             │
                         │ Storage               │
                         └───────────┬───────────┘
                                     │
                           TCP / TLS │
                         Agent-initiated
                                     │
                  ┌──────────────────┼──────────────────┐
                  │                  │                  │
                  ▼                  ▼                  ▼
          ┌──────────────┐   ┌──────────────┐   ┌──────────────┐
          │    Agent 1   │   │    Agent 2   │   │    Agent N   │
          │              │   │              │   │              │
          │ Core         │   │ Core         │   │ Core         │
          │ Beacon       │   │ Beacon       │   │ Beacon       │
          │ Protocol     │   │ Protocol     │   │ Protocol     │
          │ Transport    │   │ Transport    │   │ Transport    │
          │ Executor     │   │ Executor     │   │ Executor     │
          └──────────────┘   └──────────────┘   └──────────────┘
```

The C2 server is the central coordination point.

Agents do not communicate directly with one another through the C2 architecture.

The intended logical relationship is:

```text
Operator
   │
   ▼
C2 Server
   │
   ├────────► Agent 1
   ├────────► Agent 2
   └────────► Agent N
```

The arrows above represent logical communication relationships. Network connections are initiated by the agents according to their communication cycle.

---

## 4. Network zones

The laboratory deployment can be viewed as three logical zones.

### 4.1 Operator zone

This is where the authorized operator interacts with the C2.

```text
Operator
   │
   ▼
Operator Interface
```

The interface may initially be a CLI, with TUI or Web interfaces considered as future extensions.

The operator interface does not directly communicate with agents.

---

### 4.2 C2 zone

This contains the central server and its local resources.

```text
┌─────────────────────────────────────────┐
│                C2 Zone                  │
│                                         │
│  Interface                              │
│      │                                  │
│      ▼                                  │
│  C2 Core                                │
│      │                                  │
│  ┌───┼─────────┐                        │
│  ▼   ▼         ▼                        │
│Protocol      Storage      Logging       │
│  │                                      │
│  ▼                                      │
│Transport                                │
└───────────────┬─────────────────────────┘
                │
                │ Network boundary
                ▼
```

The C2 zone contains:

- server application logic;
- transport listener;
- persistent database;
- server-side file storage;
- configuration;
- logging.

The transport listener waits for incoming agent connections. It does not need to establish outbound connections to individual agents for the MVP communication model.

---

### 4.3 Agent zone

Each agent runs in its own endpoint context.

```text
┌─────────────────────────────────────────┐
│              Agent Zone                 │
│                                         │
│  Beacon                                 │
│      │                                  │
│      ▼                                  │
│  Transport                              │
│      │                                  │
│      ▼                                  │
│  Protocol                               │
│      │                                  │
│      ▼                                  │
│  Agent Core                             │
│      │                                  │
│  ┌───┴──────────┐                       │
│  ▼              ▼                       │
│Executor       Other local logic         │
│  │                                      │
│  ▼                                      │
│Commands / Platform                      │
│                                         │
└─────────────────────────────────────────┘
```

The Beacon determines **when the agent should communicate**.

The Transport determines **how the communication is established**.

---

# 5. Network trust boundaries

The network architecture contains several important trust boundaries.

## 5.1 Operator ↔ C2 application

```text
Operator
   │
   │ operator input
   ▼
Interface
   │
   ▼
C2 Core
```

The operator is assumed to be authorized, but operator input should still be validated.

The interface should not bypass the C2 core to directly manipulate transport or storage.

---

## 5.2 C2 ↔ network

The C2 transport boundary separates trusted server-side application components from network-provided data.

```text
C2 Core
   │
   ▼
Protocol
   │
   ▼
Transport
   │
   ║ Network boundary
   │
   ▼
Agent
```

Data received from the network must not be considered trusted solely because it arrived through TLS.

---

## 5.3 Network ↔ agent

The agent receives information from an external communication channel.

The expected boundary is:

```text
Network
   │
   ▼
Transport
   │
   ▼
Protocol Validation
   │
   ▼
Agent Core
```

The transport layer should therefore remain separate from command execution.

---

## 5.4 Application ↔ persistent storage

The network architecture also includes local trust boundaries around persistence:

```text
C2 Core
   │
   ├──► Database Interface ──► SQLite
   │
   └──► File Storage Interface ──► Filesystem
```

The application should access storage through the defined interfaces rather than coupling business logic directly to storage mechanisms.

---

# 6. Asynchronous communication model

The C2-AUTOMATED MVP uses an **agent-initiated asynchronous communication model**.

The important concept is that the C2 does not continuously push work to agents through independently initiated network connections.

Instead:

```text
Agent
   │
   │ Beacon / communication opportunity
   ▼
Establish TCP/TLS session
   │
   ▼
Exchange pending messages
   │
   ▼
Process / acknowledge information
   │
   ▼
Session ends or remains available according to the implementation
   │
   ▼
Next beacon
```

The Beacon therefore determines **when the agent attempts communication**, while the C2 determines **what information is available for that agent when the communication occurs**.

---

## 6.1 C2-side model

The C2 maintains logical state independently of an individual network connection.

For example:

```text
Agent A
 ├── Logical identity
 ├── Pending Task 1
 ├── Pending Task 2
 └── Last known state

Agent B
 ├── Logical identity
 └── Pending Task 3
```

The C2 does not need a permanent TCP connection to represent a pending task.

Tasks can therefore remain queued while an agent is temporarily disconnected.

---

## 6.2 Agent-side model

The agent contains a Beacon component responsible for communication opportunities.

Conceptually:

```text
Agent
  │
  ▼
Beacon
  │
  │ "Time to communicate"
  ▼
Transport
  │
  ▼
C2
```

During a communication opportunity, the agent may:

- identify itself;
- report its state;
- send pending results;
- initiate or continue file transfers;
- receive pending tasks or other information.

The exact message ordering is defined in [`protocol.md`](protocol.md).

---

## 6.3 Communication is asynchronous at the application level

“Asynchronous” refers primarily to the fact that the C2 and agents do not need to be executing a single blocking operator-to-agent interaction.

For example:

```text
Operator
   │
   │ creates task
   ▼
C2 Task Queue
   │
   │ task remains pending
   │
   │          Agent is temporarily offline
   │
   │
   ▼
Agent next beacon
   │
   ▼
Task delivered
```

This allows the operator to create tasks without requiring the agent to be continuously connected at that exact moment.

---

## 6.4 Connection lifecycle

The logical connection lifecycle is:

```text
Agent
  │
  │ Wait for beacon opportunity
  ▼
Beacon triggered
  │
  ▼
TCP/TLS connection
  │
  ▼
Session established
  │
  ▼
Registration / beacon / pending exchange
  │
  ├──► Tasks
  ├──► Results
  ├──► File-transfer messages
  └──► Control information
  │
  ▼
Session termination or continued communication
  │
  ▼
Wait for next beacon
```

The exact point at which a session is terminated is an implementation detail and remains separate from the logical agent identity.

---

## 6.5 Agent identity versus session

A persistent **agent identity** and a temporary **network session** are different concepts.

```text
Agent Identity
      │
      ├── Session 1
      │
      ├── Session 2
      │
      └── Session N
```

For example, if the agent loses connectivity:

```text
Session 1
    ↓
Disconnected
    ↓
Agent remains known
    ↓
Next beacon
    ↓
Session 2
```

The C2 should therefore not treat every new network connection as the creation of a completely new agent.

This distinction is important for:

- task queues;
- result correlation;
- last-seen information;
- reconnection;
- session management.

---

# 7. Beacon, transport and protocol responsibilities

These three concepts must remain distinct.

```text
┌─────────────────────────────────────────────┐
│                  Beacon                     │
│     WHEN should communication occur?        │
└──────────────────────┬──────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────┐
│                 Transport                   │
│       HOW is communication carried?         │
│               TCP / TLS                     │
└──────────────────────┬──────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────┐
│                  Protocol                   │
│       WHAT information is exchanged?        │
└─────────────────────────────────────────────┘
```

This separation allows the communication timing, network mechanism, and application message structure to evolve independently.

---

## 7.1 Beacon

The Beacon is responsible for:

- determining communication opportunities;
- triggering communication attempts;
- interacting with retry/timeout policy;
- coordinating the agent's communication cycle.

The Beacon does **not** define the contents of the exchanged messages.

---

## 7.2 Transport

The Transport is responsible for:

- establishing the network connection;
- protecting communication using TLS;
- sending and receiving bytes;
- handling network-level connection errors;
- closing or maintaining the network connection according to the implementation.

The Transport does **not** decide which task should be executed.

---

## 7.3 Protocol

The Protocol is responsible for:

- identifying messages;
- serializing and deserializing messages;
- validating message structures;
- interpreting message types;
- correlating messages with agents, tasks, sessions, or transfers.

The Protocol does not determine when the next beacon occurs.

---

# 8. Transport architecture

The MVP transport is:

```text
Application Protocol
        │
        ▼
       TCP
        │
        ▼
       TLS
        │
        ▼
      Network
```

The transport implementation is isolated behind an abstraction.

On the C2:

```text
transport/
├── interface.py
└── tcp_tls.py
```

The same separation exists conceptually on the agent.

The objective is to ensure that the rest of the application depends on a transport interface rather than directly on TCP/TLS implementation details.

---

## 8.1 TCP

TCP provides the underlying reliable byte-stream transport.

The application protocol operates above this transport.

TCP is therefore not responsible for:

- identifying protocol messages;
- validating message fields;
- managing tasks;
- managing file transfers;
- interpreting command types.

Those responsibilities remain within higher layers.

---

## 8.2 TLS

TLS provides protection for the communication channel.

It is intended to provide:

- confidentiality in transit;
- integrity in transit;
- peer authentication according to the selected authentication configuration.

TLS therefore protects the communication channel but does not replace application-level protocol validation or authorization.

---

# 9. Connection initiation and direction

The MVP uses an **agent-initiated connection model**.

```text
                    C2 Server
                        │
                        │
                  Listening
                        │
                        ▲
                        │
              TCP/TLS connection
                        │
                        │ initiated by
                        │
                     Agent
```

The C2 waits for incoming agent connections.

The agent decides when to initiate communication according to its Beacon mechanism.

The C2 therefore does not need an outbound connection mechanism for each agent.

This model simplifies:

- the network architecture;
- session handling;
- laboratory deployment;
- asynchronous task queuing;
- reconnection handling.

It also makes the distinction between **logical task availability** and **current network connectivity** explicit.

---

# 10. Main network flows

## 10.1 Agent registration

Conceptually:

```text
Agent
   │
   │ Beacon / registration opportunity
   ▼
Beacon
   │
   ▼
Transport
   │
   │ TCP/TLS connection
   ▼
C2 Transport
   │
   ▼
Protocol Validation
   │
   ▼
Agent / Session Management
   │
   ▼
Persistent State
```

The purpose is to associate an incoming participant with an agent identity and communication session.

The exact registration message and authentication mechanism remain defined by the protocol and decision records.

---

## 10.2 Beacon communication

A typical beacon cycle is conceptually:

```text
Agent
   │
   │ 1. Beacon opportunity
   ▼
Establish TCP/TLS
   │
   ▼
Send beacon / state
   │
   ▼
C2 identifies session
   │
   ├── Pending task(s)
   ├── Pending transfer(s)
   └── Other pending information
          │
          ▼
       Exchange
          │
          ▼
    Process local work
          │
          ▼
Session ends or remains available
          │
          ▼
Wait for next beacon
```

The exact message sequence is defined by [`protocol.md`](protocol.md).

---

## 10.3 Task flow

The network perspective of task execution is:

```text
Operator
   │
   ▼
C2 Interface
   │
   ▼
C2 Core
   │
   ▼
Task Manager
   │
   │ task queued for Agent A
   ▼
Pending Task Store / Queue
   │
   │
   │ Agent A next beacon
   ▼
Agent Transport
   │
   ▼
Agent Protocol
   │
   ▼
Agent Executor
```

The key point is that the task does **not** require the agent to be currently connected at the moment the operator creates it.

The task can remain pending until a suitable communication opportunity occurs.

The execution details are documented in [`task-lifecycle.md`](task-lifecycle.md).

---

## 10.4 Result flow

Results conceptually travel through the next available communication opportunity:

```text
Agent
   │
   ▼
Executor
   │
   ▼
Agent Protocol
   │
   ▼
Transport
   │
   │ TCP/TLS
   ▼
C2 Transport
   │
   ▼
C2 Protocol
   │
   ▼
Result Manager
   │
   ▼
Persistent State
   │
   ▼
Operator Interface
```

Depending on the implementation, the result may be transmitted:

- during the communication session associated with the task; or
- during a later beacon cycle.

The exact protocol behavior is defined in [`protocol.md`](protocol.md) and [`task-lifecycle.md`](task-lifecycle.md).

---

## 10.5 File-transfer flow

A file transfer uses the same network path but has its own application-level lifecycle.

Conceptually:

```text
File Manager
     │
     ▼
Protocol
     │
     ▼
Transport
     │
     │ TCP/TLS
     ▼
Remote Transport
     │
     ▼
Remote Protocol
     │
     ▼
Remote File Handling
     │
     ▼
Remote File Storage
```

A large transfer may therefore span multiple communication exchanges depending on the final protocol and session design.

The detailed transfer lifecycle is defined in [`file-transfer.md`](file-transfer.md).

---

# 11. Multi-agent communication

The C2 is designed to support multiple agents concurrently.

The intended model is:

```text
                    C2
                     │
       ┌─────────────┼─────────────┐
       │             │             │
       ▲             ▲             ▲
       │             │             │
    Agent A       Agent B       Agent C
       │             │             │
    Session A     Session B     Session C
```

The arrows point toward the C2 because the agents initiate the network connections.

The C2 therefore needs to maintain a distinction between:

- the logical agent;
- the current session;
- tasks assigned to the agent;
- results returned by the agent.

This distinction is documented in `ARCHITECTURE.md` and `data-model.md`.

---

## 11.1 Session isolation

Messages received through one session must not accidentally affect another agent's state.

Conceptually:

```text
Session A
   │
   ├── Agent A
   ├── Tasks A
   └── Results A

Session B
   │
   ├── Agent B
   ├── Tasks B
   └── Results B
```

The protocol must provide sufficient identifiers and validation to preserve these associations.

---

# 12. Network addressing

The concrete deployment environment determines the actual addresses used by the C2 and agents.

For the architecture, the following logical information matters:

```text
C2
 ├── Network address
 ├── Listening transport endpoint
 └── TLS configuration

Agent
 ├── C2 destination
 ├── Network identity/context
 └── TLS configuration
```

The architecture intentionally does not hard-code a particular IP addressing scheme.

The laboratory deployment may therefore use:

- local/private addressing;
- isolated virtual networks;
- host-only or equivalent laboratory networking;
- other explicitly authorized test environments.

The exact deployment topology should be recorded separately when the laboratory environment is selected.

---

# 13. Ports and endpoints

The C2 requires a network endpoint for the selected transport.

At the architectural level:

```text
C2 Server
   │
   └── TCP/TLS listener
           ▲
           │
     ┌─────┼─────┐
     │     │     │
     │     │     │
  Agent 1 Agent 2 Agent N
```

The agents initiate connections toward this listener according to their beacon cycle.

The exact port number is a deployment/configuration parameter rather than a fixed architectural requirement.

It should therefore be defined through configuration rather than hard-coded throughout the application.

---

# 14. TLS boundary

TLS establishes a protected communication channel between the communicating endpoints.

```text
                 TLS Protected Channel
        ╔══════════════════════════════════╗
        ║                                  ║
Agent ──╫══════════════════════════════════╫──── C2
        ║                                  ║
        ╚══════════════════════════════════╝
        Agent initiates the connection
```

The protected channel is responsible for securing data **in transit**.

It does not provide:

- task authorization;
- command validation;
- filesystem authorization;
- application-level state validation;
- protection of locally stored files;
- protection of compromised endpoints.

These responsibilities remain with the appropriate application and security layers.

---

# 15. Network security boundaries

The network architecture should be understood together with the threat model.

The main network-related risks include:

| Risk ID | Risk | Network relevance |
|---|---|---|
| TM-001 | Unauthorized C2 connection | Incoming agent connection |
| TM-002 | Agent impersonation | Identity associated with network participant |
| TM-003 | Message tampering | Data crossing the network |
| TM-004 | Message replay | Repeated network messages |
| TM-005 | Malformed protocol message | Untrusted network input |
| TM-020 | Denial of service | Network and connection resource consumption |
| TM-021 | Session confusion | Association between network session and agent |
| TM-022 | Beacon / communication-state abuse | Agent communication timing/state |

The complete risk register is maintained in [`threat-model.md`](threat-model.md).

---

# 16. Network-level security principles

The network architecture follows these principles.

### 16.1 The network is not trusted

The architecture must remain secure even when the network itself is considered hostile.

---

### 16.2 TLS does not replace validation

A valid TLS connection does not imply that application data is valid.

Received messages must still be validated by the protocol layer.

---

### 16.3 Transport is independent from protocol

The protocol defines the information exchanged.

The transport defines how that information is carried.

```text
Protocol
   │
   ▼
Transport Interface
   │
   ▼
TCP/TLS
```

This separation allows future transport extensions without rewriting the core application logic.

---

### 16.4 Session identity is distinct from agent identity

A network connection represents a communication session.

It does not necessarily represent the permanent identity of the agent.

This distinction supports reconnection and asynchronous task queuing.

---

### 16.5 Network-facing components must be resource-aware

Network input can consume:

- connections;
- memory;
- CPU;
- queues;
- storage.

The design should therefore include appropriate:

- limits;
- timeouts;
- validation;
- cleanup mechanisms.

---

# 17. Network architecture and storage

The network layer does not directly manage persistent storage.

The expected flow is:

```text
Network
   │
   ▼
Transport
   │
   ▼
Protocol
   │
   ▼
Core / Manager
   │
   ├──► Database
   │
   └──► File Storage
```

For example, when a result is received:

```text
Network
   ↓
Transport
   ↓
Protocol Validation
   ↓
Result Manager
   ↓
Database / relevant storage
```

When a file transfer is received:

```text
Network
   ↓
Transport
   ↓
Protocol
   ↓
File Manager
   ↓
File Storage
```

This prevents the transport layer from becoming coupled to persistence.

---

# 18. Network architecture and logging

Network-relevant events should be observable through centralized logging.

Potential events include:

- connection established;
- connection closed;
- registration accepted/rejected;
- protocol validation failure;
- session state change;
- transfer failure;
- communication timeout;
- unexpected disconnect;
- repeated connection failures.

Logs should contain sufficient identifiers to support correlation without unnecessarily storing secrets or sensitive content.

Relevant logging responsibilities are described in `SECURITY.md`.

---

# 19. Laboratory deployment model

The project is intended for an **authorized laboratory environment**.

A representative topology is:

```text
                 Laboratory Network
┌──────────────────────────────────────────────────────┐
│                                                      │
│  Operator Machine                                    │
│       │                                              │
│       ▼                                              │
│  ┌───────────────┐                                   │
│  │   C2 Server   │                                   │
│  │ TCP/TLS       │◄───────────────────┐              │
│  │ listener      │                    │              │
│  └───────┬───────┘                    │              │
│          ▲                            │              │
│          │ TCP/TLS                    │              │
│          │ agent-initiated            │              │
│     ┌────┴───────────────┐            │              │
│     │                    │            │              │
│     │                    │            │              │
│     ▼                    ▼            │              │
│  Agent VM 1           Agent VM 2 ─────┘              │
│                                                      │
└──────────────────────────────────────────────────────┘
```

The specific virtualization, addressing, or network isolation mechanism is a deployment decision rather than a requirement of the software architecture.

Testing must remain limited to systems and networks for which explicit authorization exists.

---

# 20. External exposure

The architecture does not require the C2 to be publicly exposed to the Internet.

The preferred development and demonstration model is an isolated or controlled laboratory environment.

Any change that exposes the C2 beyond the intended laboratory environment should trigger a security review, because it changes the threat model and attack surface.

---

# 21. Future transport extensions

The architecture deliberately keeps transport behind an interface.

Potential future transport implementations may include alternative mechanisms, depending on project scope and requirements.

Conceptually:

```text
                 Transport Interface
                         │
           ┌─────────────┼─────────────┐
           │             │             │
           ▼             ▼             ▼
         TCP/TLS      Future A       Future B
          MVP
```

Adding a new transport should not require rewriting:

- task management;
- result management;
- file management;
- storage;
- the operator interface;
- the Beacon's logical purpose.

Any new transport would nevertheless require its own security analysis and testing.

---

# 22. Network architecture versus protocol architecture

These two documents intentionally answer different questions.

| Topic | Network Architecture | Protocol |
|---|---|---|
| Network topology | Yes | No |
| C2/Agent communication path | Yes | Partially |
| Connection initiation direction | Yes | Partially |
| TCP/TLS | Yes | No |
| Trust boundaries | Yes | Partially |
| Ports/endpoints | Yes | No |
| Message structure | No | Yes |
| Message types | No | Yes |
| Serialization | No | Yes |
| Message validation | Security boundary only | Detailed |
| Task message semantics | No | Yes |
| File-transfer message semantics | No | Yes |
| Beacon semantics | Conceptual | Detailed |

This separation avoids duplicating the same technical specification in multiple documents.

---

# 23. Relationship with other documentation

The network architecture is connected to several other project documents.

```text
ARCHITECTURE.md
      │
      ▼
Network Architecture
      │
      ├────► Protocol
      │
      ├────► Threat Model
      │
      ├────► Security
      │
      ├────► File Transfer
      │
      └────► Testing Strategy
```

More specifically:

- `ARCHITECTURE.md` defines the global component structure.
- `network-architecture.md` defines the network topology and communication paths.
- `protocol.md` defines the application-level communication contract.
- `threat-model.md` defines the relevant risks.
- `countermeasures.md` defines how those risks are mitigated.
- `testing-strategy.md` defines how the network behavior and controls are validated.

---

# 24. Open network decisions

The following points remain intentionally open:

| Decision | Related area | Status |
|---|---|---|
| Exact C2 listening port | Deployment/configuration | Open |
| Exact session lifetime | Session/transport | Open |
| Exact registration sequence | Protocol/authentication | Open |
| Exact authentication mechanism | Identity | Open |
| Exact beacon timing/state machine | Beaconing | Open |
| Whether sessions remain persistent or close after exchanges | Transport/session | Open |
| Connection timeout policy | Availability | Open |
| Retry policy | Availability / beaconing | Open |
| Resource limits | Availability | Open |
| Exact laboratory network topology | Deployment | Open |
| Additional transport implementations | Future extension | Open |

The **agent-initiated communication model itself is established for the MVP**.

The remaining decision is primarily the precise lifecycle of each TCP/TLS session: whether a session closes after each communication opportunity or remains available for additional exchanges.

These decisions should be recorded in [`../DECISIONS.md`](../DECISIONS.md) where they constitute significant architectural choices.

---

# 25. Testing implications

The network architecture creates several categories of tests.

### Connectivity

Verify that:

- the C2 transport endpoint can accept legitimate agent connections;
- agents can establish communication;
- invalid connections are rejected appropriately;
- disconnects are handled cleanly.

### Agent-initiated connection model

Verify that:

- the agent initiates communication according to its Beacon mechanism;
- the C2 can accept multiple agent connections;
- the C2 does not require an outbound connection toward an agent;
- an offline agent can reconnect later without creating an incorrect identity.

### Asynchronous task delivery

Verify that:

- a task can remain pending while an agent is disconnected;
- the task is delivered when the relevant agent communicates;
- tasks are not lost between communication sessions;
- tasks remain associated with the correct agent.

### TLS

Verify that:

- the expected TLS configuration is used;
- invalid or unsuitable connections are rejected according to the selected configuration;
- communication remains protected in transit.

### Session handling

Verify that:

- each session is associated with the correct agent;
- reconnecting agents do not create incorrect identity associations;
- disconnected sessions are cleaned up correctly;
- session lifecycle behavior matches the selected implementation.

### Multi-agent operation

Verify that:

- multiple agents can communicate concurrently;
- one agent's state does not affect another's;
- tasks and results remain correctly associated.

### Protocol boundary

Verify that:

- malformed network messages are rejected;
- oversized or invalid inputs are handled safely;
- protocol validation occurs before application processing.

### Resource handling

Verify that:

- connection limits behave as expected;
- timeouts release resources;
- failed connections do not leave persistent stale state;
- repeated connection attempts cannot exhaust available resources.

The detailed testing approach belongs in [`testing-strategy.md`](testing-strategy.md).

---

# 26. Network architecture status

The current network architecture establishes the following baseline:

- centralized C2-to-agent topology;
- multi-agent communication;
- **agent-initiated asynchronous communication**;
- Beacon-driven communication opportunities;
- TCP/TLS as the MVP transport;
- separation between protocol and transport;
- separation between agent identity and communication session;
- explicit trust boundaries;
- controlled laboratory deployment;
- transport abstraction for future extensions.

The following remain subject to detailed design:

- exact authentication;
- registration sequence;
- session state machine;
- exact session lifetime;
- beacon timing and retry behavior;
- resource limits;
- deployment-specific addressing;
- exact listening port;
- any additional transports.

The network architecture should therefore be considered a **living architectural baseline**.

Any implementation change that alters a network boundary, communication path, transport, or major trust assumption should be reflected here and, where appropriate, recorded in `DECISIONS.md`.

---

# 27. Summary

The network architecture can be summarized as:

```text
                         OPERATOR
                             │
                             ▼
                    OPERATOR INTERFACE
                             │
                             ▼
                        C2 SERVER
                             │
                      TCP/TLS Listener
                             ▲
                             │
                  Agent-initiated connection
                             │
             ┌───────────────┼───────────────┐
             │               │               │
             │               │               │
          AGENT 1         AGENT 2         AGENT N
             │               │               │
          Beacon          Beacon          Beacon
             │               │               │
          Transport       Transport       Transport
             │               │               │
          Protocol        Protocol        Protocol
             │               │               │
          Executor        Executor        Executor
```

The asynchronous model is:

```text
Agent
  │
  ▼
Beacon opportunity
  │
  ▼
TCP/TLS connection initiated
  │
  ▼
Session
  │
  ├── Registration / Beacon
  ├── Tasks
  ├── Results
  └── File-transfer data
  │
  ▼
Session ends or continues
  │
  ▼
Wait for next beacon
```

The central design principles are:

> **The agent initiates network communication.**

> **The Beacon determines when communication is attempted.**

> **The Transport determines how communication is carried.**

> **The Protocol determines what information is exchanged.**

> **The C2 can maintain logical tasks and agent state even when an agent is temporarily disconnected.**

This separation provides a clear foundation for the subsequent **Kill Chain analysis**, **countermeasure analysis**, and **security testing**.
