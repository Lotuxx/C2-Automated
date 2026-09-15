# Network Architecture

## 1. Purpose

This document describes the **network architecture** of the C2-AUTOMATED project.

It focuses on:

- how the C2 and agents communicate across the network;
- the direction of connection initiation;
- the relationship between Beacon, Transport and Protocol;
- network trust boundaries;
- the selected transport;
- multi-agent communication;
- network-related security and testing considerations.

It complements:

- [`../ARCHITECTURE.md`](../ARCHITECTURE.md) for the overall software architecture;
- [`protocol.md`](protocol.md) for the application-level communication contract;
- [`state-machines.md`](state-machines.md) for authoritative state definitions and transitions;
- [`data-model.md`](data-model.md) for the domain entities and their relationships;
- [`../SECURITY.md`](../SECURITY.md) for security principles;
- [`threat-model.md`](threat-model.md) for network-related risks;
- [`countermeasures.md`](countermeasures.md) for corresponding security controls.

This document deliberately does **not** redefine the application protocol, entity model, task lifecycle, or authoritative state machines. Those subjects are defined in their respective documents.

---

# 2. Network Architecture Objectives

The network design has the following objectives:

- provide communication between one C2 server and multiple agents;
- support asynchronous operation;
- use an agent-initiated connection model;
- separate logical protocol from network transport;
- protect communications in transit;
- maintain clear network trust boundaries;
- allow multiple agents to communicate concurrently;
- keep transport implementation behind an abstraction;
- remain simple enough for the MVP and academic laboratory environment.

The MVP uses:

> **Agent-initiated TCP over TLS**

The asynchronous communication model is based on **agent-initiated communication opportunities**, coordinated by the Beacon component.

Other transport mechanisms may be considered later as extensions.

---

# 3. Global Network Topology

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

The logical relationship is:

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

The arrows represent logical communication relationships. The network connection itself is initiated by each agent according to its communication cycle.

---

# 4. Network Zones

The laboratory deployment can be viewed as three logical zones.

## 4.1 Operator Zone

The operator interacts with the C2 through an operator interface.

```text
Operator
   │
   ▼
Operator Interface
```

The initial interface is the CLI. TUI and Web interfaces remain possible future extensions.

The operator interface does not communicate directly with agents. It interacts with the C2 application core.

---

## 4.2 C2 Zone

The C2 zone contains the central server and its local resources.

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

The transport listener accepts incoming connections initiated by agents.

The MVP does not require the C2 to establish independent outbound connections to agents.

---

## 4.3 Agent Zone

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

The Beacon determines **when the agent should attempt communication**.

The Transport determines **how that communication is established and carried**.

---

# 5. Network Trust Boundaries

The architecture contains several important trust boundaries.

## 5.1 Operator ↔ C2 Application

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

The operator is assumed to be authorized, but operator input must still be validated.

The interface should not bypass the C2 core to directly manipulate transport or persistent storage.

---

## 5.2 C2 ↔ Network

The transport boundary separates trusted server-side application components from network-provided data.

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

Network input must not be considered trusted solely because it arrived through TLS.

It must pass through the appropriate protocol validation and application checks before affecting C2 state.

---

## 5.3 Network ↔ Agent

The agent receives information from an external communication channel.

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

The transport layer therefore remains separate from command execution and other local application logic.

---

## 5.4 Application ↔ Persistent Storage

The application accesses persistence through defined storage abstractions.

```text
C2 Core
   │
   ├──► Database Interface ──► SQLite
   │
   └──► File Storage Interface ──► Filesystem
```

The network layer does not directly manipulate persistent storage.

---

# 6. Asynchronous Communication Model

The MVP uses an **agent-initiated asynchronous communication model**.

The important distinction is between:

1. **who initiates a network connection**; and
2. **what information is exchanged once the connection exists**.

The agent initiates the communication opportunity:

```text
Agent
   │
   │ Beacon / communication opportunity
   ▼
Establish TCP/TLS connection
   │
   ▼
Exchange pending information
   │
   ▼
Session ends or remains available
   │
   ▼
Next communication opportunity
```

The C2 does not need to initiate a new network connection whenever it has a task for an agent.

Instead, the C2 maintains logical state independently of the current network connectivity of that agent.

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

A task can therefore remain pending while its agent is temporarily disconnected.

When the agent next communicates, the C2 can exchange the information associated with that agent.

---

# 7. Beacon, Transport and Protocol Responsibilities

These three concepts answer different questions:

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

Keeping these responsibilities separate allows communication timing, network transport, and application messages to evolve independently.

---

## 7.1 Beacon

The Beacon is responsible for:

- determining communication opportunities;
- triggering communication attempts;
- coordinating retry and communication timing policies;
- initiating the agent's communication cycle.

The Beacon does not define the structure or semantics of application messages.

---

## 7.2 Transport

The Transport is responsible for:

- establishing the network connection;
- protecting the communication channel using TLS;
- sending and receiving bytes;
- handling network-level connection errors;
- closing or maintaining the connection according to the implementation.

The Transport does not decide which task should be executed.

---

## 7.3 Protocol

The Protocol is responsible for:

- identifying messages;
- serializing and deserializing messages;
- validating message structures;
- interpreting message types;
- correlating messages with agents, sessions, tasks, results, or transfers.

The Protocol does not determine when the next Beacon communication opportunity occurs.

Detailed message semantics belong to [`protocol.md`](protocol.md).

---

# 8. Transport Architecture

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

The agent follows the same conceptual separation.

The objective is that higher-level components depend on a transport interface rather than directly on TCP/TLS implementation details.

---

## 8.1 TCP

TCP provides the underlying reliable byte-stream transport.

The application protocol operates above this byte stream.

TCP is therefore not responsible for:

- identifying application protocol messages;
- validating message fields;
- managing tasks;
- managing results;
- managing file transfers;
- interpreting command types.

Those responsibilities belong to higher layers.

---

## 8.2 TLS

TLS protects the communication channel.

Depending on the selected configuration, it is intended to provide:

- confidentiality in transit;
- integrity in transit;
- peer authentication.

TLS protects the transport channel but does not replace:

- application-level validation;
- identity handling;
- task authorization;
- protocol state validation;
- endpoint security;
- protection of locally stored data.

The exact authentication configuration remains an implementation/security decision.

---

# 9. Connection Initiation and Direction

The MVP uses an **agent-initiated connection model**.

```text
                    C2 Server
                        │
                        │
                  TCP/TLS Listener
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

The C2 therefore does not require a separate outbound connection mechanism for each agent.

This simplifies:

- network deployment;
- session handling;
- asynchronous task queuing;
- reconnection handling;
- laboratory testing.

---

# 10. Connection and Session Model

The network connection and logical Agent identity are distinct.

A new communication connection results in a **new Session** associated with an existing or newly recognized Agent.

The network-level sequence is:

```text
Agent
  │
  │ Beacon / communication opportunity
  ▼
New TCP/TLS connection
  │
  ▼
Session created
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
Agent communication = SYNCHRONIZING
  │
  ▼
State reconciliation
  │
  ▼
SYNC_COMPLETE
  │
  ▼
Agent communication = CONNECTED
```

The important distinction is:

> **Transport establishment makes the Session connected. Registration does not.**

`REGISTER` identifies the Agent and provides the information required for C2-side registration over an already established transport.

`REGISTER_ACK` confirms registration and communicates the new `session_id`. It does not perform the Session `CONNECTING → CONNECTED` transition.

The authoritative Session and communication state machines are defined in [`state-machines.md`](state-machines.md).

---

## 10.1 Reconnection

A reconnecting Agent does not reopen its previous Session.

For example:

```text
Agent A001
 ├── S041
 ├── S042 = DISCONNECTED
 └── S043 = CONNECTED
```

The conceptual sequence is:

```text
S042
  │
  ▼
Disconnected
  │
  │ new communication opportunity
  ▼
New TCP/TLS connection
  │
  ▼
S043
```

The previous Session remains historical.

The Agent identity remains the same.

This distinction supports:

- historical session tracking;
- task correlation;
- result correlation;
- last-seen information;
- synchronization after reconnection.

Detailed Session semantics belong to [`data-model.md`](data-model.md) and [`state-machines.md`](state-machines.md).

---

# 11. Registration and Synchronization Network Flow

Registration occurs over an already established transport connection.

The conceptual flow is:

```text
Agent
   │
   │ 1. Beacon / communication opportunity
   ▼
Establish TCP/TLS
   │
   ▼
Session CONNECTED
   │
   ▼
REGISTER
   │
   ▼
C2 identifies Agent
   │
   ▼
REGISTER_ACK(session_id)
   │
   ▼
Agent communication SYNCHRONIZING
   │
   ▼
SYNC_STATE
   │
   ▼
C2 reconciliation
   │
   ▼
SYNC_STATE_RESPONSE
   │
   ▼
SYNC_COMPLETE
   │
   ▼
Normal communication
```

This sequence deliberately separates:

- network connection establishment;
- Session creation;
- Agent registration;
- synchronization;
- normal application communication.

The exact messages and reconciliation rules are defined by [`protocol.md`](protocol.md) and [`reconnection-and-synchronization.md`](reconnection-and-synchronization.md).

---

# 12. Main Network Flows

## 12.1 Beacon Communication

A typical communication opportunity is:

```text
Agent
   │
   │ Beacon opportunity
   ▼
Establish TCP/TLS
   │
   ▼
Register / identify session
   │
   ▼
Synchronize if required
   │
   ▼
Exchange pending information
   │
   ├── Tasks
   ├── Results
   ├── File-transfer messages
   └── Control information
   │
   ▼
Session ends or remains available
   │
   ▼
Next communication opportunity
```

The exact message ordering is defined in [`protocol.md`](protocol.md).

---

## 12.2 Task Flow

From the network perspective:

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
   │ task associated with Agent A
   ▼
Pending Task
   │
   │ Agent A communicates
   ▼
Protocol / Transport
   │
   ▼
Agent
   │
   ▼
Task processing
```

The task does not require the Agent to be connected when the Operator creates it.

The C2 can retain the Task while the Agent is offline and exchange it during a later communication opportunity.

The authoritative Task lifecycle is defined in [`task-lifecycle.md`](task-lifecycle.md).

---

## 12.3 Result Flow

A Result travels through the same transport path:

```text
Agent
   │
   ▼
Agent Executor
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

Depending on the implementation and communication state, a Result may be transmitted during the same communication episode or during a later communication opportunity.

The Result belongs to its Task; communication timing does not change that relationship.

---

## 12.4 File Transfer Flow

File transfer uses the same network path while maintaining its own application-level lifecycle.

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

The transfer may involve multiple messages and, depending on the final implementation, may span communication episodes.

Detailed transfer semantics belong to [`file-transfer.md`](file-transfer.md).

---

# 13. Multi-Agent Communication

The C2 is designed to support multiple agents concurrently.

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

The arrows point toward the C2 because the agents initiate network connections.

The C2 must maintain the appropriate associations between:

- Agent identity;
- Session;
- Tasks;
- Results;
- File transfers.

These domain relationships are defined in [`data-model.md`](data-model.md).

---

## 13.1 Session Isolation

Messages received through one Session must not accidentally affect another Agent's state.

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

Protocol identifiers and validation rules must preserve these associations.

A network message must therefore be resolved against the appropriate Session and Agent context before it is allowed to affect application state.

---

# 14. Network Addressing

The concrete deployment environment determines the actual addresses used by the C2 and Agents.

At the architectural level, the relevant information is:

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

The laboratory deployment may use:

- local/private addressing;
- isolated virtual networks;
- host-only or equivalent laboratory networking;
- other explicitly authorized test environments.

The exact deployment topology should be documented separately once the laboratory environment is selected.

---

# 15. Ports and Endpoints

The C2 requires a network endpoint for the selected transport.

```text
C2 Server
   │
   └── TCP/TLS listener
           ▲
           │
     ┌─────┼─────┐
     │     │     │
  Agent 1 Agent 2 Agent N
```

Agents initiate connections toward this listener according to their communication cycle.

The exact port number is a deployment/configuration parameter rather than a fixed architectural requirement.

It should therefore be configured rather than hard-coded throughout the application.

---

# 16. TLS Boundary

TLS establishes a protected communication channel between the endpoints.

```text
                 TLS Protected Channel
        ╔══════════════════════════════════╗
        ║                                  ║
Agent ──╫══════════════════════════════════╫──── C2
        ║                                  ║
        ╚══════════════════════════════════╝
        Agent initiates the connection
```

The protected channel secures data **in transit**.

It does not provide:

- task authorization;
- command validation;
- filesystem authorization;
- application-level state validation;
- protection of locally stored files;
- protection of compromised endpoints.

Those responsibilities belong to the corresponding application and security layers.

---

# 17. Network Security Principles

The network architecture follows these principles.

## 17.1 The Network Is Not Trusted

Network-provided data must be treated as untrusted input.

TLS protects the communication channel but does not make application data inherently trustworthy.

---

## 17.2 TLS Does Not Replace Validation

A valid TLS connection does not imply that an application message is valid.

Received messages must still pass protocol validation and appropriate application checks.

---

## 17.3 Transport Is Independent from Protocol

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

This separation allows transport implementations to evolve without rewriting the core application logic.

---

## 17.4 Session Identity Is Distinct from Agent Identity

A network connection corresponds to a communication Session.

It does not represent the permanent identity of the Agent.

This distinction is required for reconnection and historical session tracking.

---

## 17.5 Network-Facing Components Must Be Resource-Aware

Network input can consume:

- connections;
- memory;
- CPU;
- queues;
- storage.

The implementation should therefore include appropriate:

- limits;
- timeouts;
- validation;
- cleanup mechanisms.

---

# 18. Network Architecture and Storage

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

For example, when a Result is received:

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

This prevents the transport layer from becoming coupled to persistence mechanisms.

---

# 19. Network Architecture and Logging

Network-relevant events should be observable through centralized logging.

Examples include:

- connection established;
- connection closed;
- registration accepted or rejected;
- protocol validation failure;
- Session state change;
- synchronization event;
- transfer failure;
- communication timeout;
- unexpected disconnect;
- repeated connection failures.

Logs should contain sufficient identifiers to support correlation without unnecessarily storing secrets or sensitive content.

Detailed logging responsibilities are described in [`../SECURITY.md`](../SECURITY.md).

---

# 20. Laboratory Deployment Model

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
│     ▼                    ▼            │              │
│  Agent VM 1           Agent VM 2 ─────┘              │
│                                                      │
└──────────────────────────────────────────────────────┘
```

The specific virtualization, addressing, or network isolation mechanism is a deployment decision rather than a software architecture requirement.

Testing must remain limited to systems and networks for which explicit authorization exists.

---

# 21. External Exposure

The architecture does not require the C2 to be publicly exposed to the Internet.

The preferred development and demonstration model is an isolated or controlled laboratory environment.

Any change that exposes the C2 beyond the intended laboratory environment should trigger a security review because it changes the threat model and attack surface.

---

# 22. Future Transport Extensions

The architecture keeps transport behind an interface.

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

# 23. Network Architecture versus Protocol Architecture

The two documents intentionally answer different questions.

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
| Message validation | Security boundary | Detailed |
| Task message semantics | No | Yes |
| File-transfer message semantics | No | Yes |
| Beacon semantics | Conceptual | Detailed |

This separation prevents the same technical specification from being duplicated across documents.

---

# 24. Relationship with Other Documentation

The network architecture is connected to several project documents.

```text
ARCHITECTURE.md
      │
      ▼
Network Architecture
      │
      ├────► Protocol
      ├────► State Machines
      ├────► Data Model
      ├────► Threat Model
      ├────► Security / Countermeasures
      ├────► File Transfer
      └────► Testing Strategy
```

More specifically:

- `ARCHITECTURE.md` defines the global component structure.
- `network-architecture.md` defines network topology and communication paths.
- `protocol.md` defines the application-level communication contract.
- `state-machines.md` defines authoritative logical states and transitions.
- `data-model.md` defines persistent domain entities and their relationships.
- `reconnection-and-synchronization.md` defines synchronization and recovery behavior.
- `task-lifecycle.md` defines Task lifecycle semantics.
- `file-transfer.md` defines file-transfer lifecycle and behavior.
- `threat-model.md` defines relevant risks.
- `countermeasures.md` defines corresponding controls.
- `testing-strategy.md` defines how network behavior and controls are validated.

---

# 25. Open Network Decisions

The following points remain intentionally open:

| Decision | Related area | Status |
|---|---|---|
| Exact C2 listening port | Deployment/configuration | Open |
| Exact Session lifetime | Session/transport | Open |
| Exact registration message sequence | Protocol/authentication | Open |
| Exact authentication mechanism | Identity | Open |
| Exact Beacon timing | Beaconing | Open |
| Beacon retry policy | Availability / beaconing | Open |
| Whether Sessions remain persistent or close after exchanges | Transport/session | Open |
| Connection timeout policy | Availability | Open |
| Resource limits | Availability | Open |
| Exact laboratory network topology | Deployment | Open |
| Additional transport implementations | Future extension | Open |

The **agent-initiated communication model is established for the MVP**.

The remaining Session-lifetime decision concerns whether an established TCP/TLS connection remains available for additional exchanges or is closed after a communication episode.

This does not change the distinction between:

- Agent identity;
- Session;
- transport connection;
- Agent communication state.

Significant architectural decisions should be recorded in [`../DECISIONS.md`](../DECISIONS.md).

---

# 26. Testing Implications

The network architecture creates several categories of tests.

## Connectivity

Verify that:

- the C2 transport endpoint accepts legitimate Agent connections;
- Agents can establish communication;
- invalid connections are rejected appropriately;
- disconnects are handled cleanly.

## Agent-Initiated Connection Model

Verify that:

- the Agent initiates communication according to its Beacon mechanism;
- the C2 can accept multiple Agent connections;
- the C2 does not require an outbound connection toward an Agent;
- an offline Agent can reconnect later without creating an incorrect Agent identity.

## Registration and Synchronization

Verify that:

- a new connection creates a new Session;
- transport establishment precedes `REGISTER`;
- `REGISTER` occurs over an already connected Session;
- `REGISTER_ACK` communicates the new Session identity;
- synchronization occurs before normal Agent communication when required;
- reconnection creates a new Session rather than reopening the previous one.

## Asynchronous Task Delivery

Verify that:

- a Task can remain pending while an Agent is disconnected;
- the Task is delivered when the relevant Agent communicates;
- Tasks are not lost between communication Sessions;
- Tasks remain associated with the correct Agent.

## TLS

Verify that:

- the expected TLS configuration is used;
- invalid or unsuitable connections are rejected according to the selected configuration;
- communication remains protected in transit.

## Session Handling

Verify that:

- each Session is associated with the correct Agent;
- reconnecting Agents do not create incorrect identity associations;
- disconnected Sessions are handled correctly;
- Session lifecycle behavior matches the selected implementation.

## Multi-Agent Operation

Verify that:

- multiple Agents can communicate concurrently;
- one Agent's state does not affect another's;
- Tasks and Results remain correctly associated.

## Protocol Boundary

Verify that:

- malformed network messages are rejected;
- oversized or invalid inputs are handled safely;
- protocol validation occurs before application processing.

## Resource Handling

Verify that:

- connection limits behave as expected;
- timeouts release resources;
- failed connections do not leave persistent stale state;
- repeated connection attempts cannot exhaust available resources.

The detailed testing approach belongs in [`testing-strategy.md`](testing-strategy.md).

---

# 27. Network Architecture Status

The current network architecture establishes the following baseline:

- centralized C2-to-Agent topology;
- multi-Agent communication;
- **Agent-initiated asynchronous communication**;
- Beacon-driven communication opportunities;
- TCP/TLS as the MVP transport;
- separation between Beacon, Transport and Protocol responsibilities;
- separation between Agent identity and Session;
- explicit network trust boundaries;
- controlled laboratory deployment;
- transport abstraction for future extensions;
- new Session creation on each new communication connection.

The following remain subject to detailed design:

- exact authentication;
- registration details;
- Session lifetime;
- Beacon timing and retry behavior;
- resource limits;
- deployment-specific addressing;
- exact listening port;
- any additional transports.

The network architecture should therefore be considered a **living architectural baseline**.

Any implementation change that alters a network boundary, communication path, transport, or major trust assumption should be reflected here and, where appropriate, recorded in `DECISIONS.md`.

---

# 28. Summary

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

The communication sequence is:

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
New Session
  │
  ▼
Transport established
  │
  ▼
Session CONNECTED
  │
  ▼
REGISTER
  │
  ▼
Synchronization
  │
  ▼
Normal communication
  │
  ├── Tasks
  ├── Results
  ├── File transfers
  └── Control information
  │
  ▼
Session ends or continues
  │
  ▼
Next communication opportunity
```

The central design principles are:

> **The Agent initiates the network connection.**

> **The Beacon determines when communication is attempted.**

> **The Transport determines how communication is carried.**

> **The Protocol determines what information is exchanged.**

> **Transport establishment makes a Session connected; registration does not.**

> **A new connection creates a new Session without creating a new Agent identity.**

> **The C2 can maintain logical Agent and Task state while an Agent is temporarily disconnected.**

This separation provides the network foundation for the subsequent **protocol specification**, **synchronization design**, **threat/kill-chain analysis**, **countermeasure analysis**, and **security testing**.
