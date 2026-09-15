# Protocol-State Transition Specification

> **Status: Work in Progress**
>
> This document defines how protocol messages interact with the logical state
> machines of C2-AUTOMATED.
>
> `protocol.md` defines the messages themselves.  
> `state-machines.md` defines the authoritative states and valid state
> transitions.  
> This document connects the two by specifying which protocol events may cause
> or confirm those transitions.

---

## 1. Purpose

A protocol message and a state transition are not equivalent.

A message represents communication:

```text
TASK
TASK_ACK
RESULT
PING
PONG
```

A state transition represents a change in the domain:

```text
WAITING_ACK → QUEUED
RUNNING     → COMPLETED
CONNECTED   → DISCONNECTED
```

This document defines the relationship between the two.

The general flow is:

```text
Protocol Message
       ↓
Validation
       ↓
Message Handler
       ↓
Domain Event / Evidence
       ↓
State Transition
       ↓
Persisted Domain State
```

A received message must therefore be interpreted according to its semantic
meaning rather than automatically mapped to a state change.

---

## 2. Authorities and Responsibilities

The project uses the following documentation boundaries:

| Document | Authority |
|---|---|
| `protocol.md` | Message vocabulary and message semantics |
| `state-machines.md` | States and valid state transitions |
| `protocol-state-transition.md` | Relationship between protocol messages and state transitions |
| `reconnection-and-synchronization.md` | Reconnection and synchronization procedures |
| `task-lifecycle.md` | Detailed Task execution and recovery behavior |
| `file-transfer.md` | File-transfer lifecycle and transfer behavior |
| `data-model.md` | Entities, relationships, and persistence model |

This document must not redefine states already established by
`state-machines.md`.

---

## 3. Transition Conventions

The notation used throughout this document is:

```text
Message
    ↓
Condition
    ↓
State transition
```

The following terms are used:

- **Causes** — the message can directly cause the transition when its
  preconditions are satisfied.
- **Confirms** — the message provides evidence that a transition has occurred.
- **Triggers handling** — the message initiates processing, but the resulting
  state depends on additional domain logic.
- **No transition** — receiving the message does not itself change the
  referenced state.

A message MUST NOT cause a state transition that is not permitted by
`state-machines.md`.

---

# 4. Session Transitions

The Session state machine is:

```text
CONNECTING
    │
    │ successful connection / registration
    ▼
CONNECTED
    │
    ├── connection lost ───────→ DISCONNECTED
    │
    └── orderly termination ───→ CLOSED
```

`DISCONNECTED` and `CLOSED` are terminal states for a Session.

### 4.1 Session Message Mapping

| Message / Event | Condition | Session effect |
|---|---|---|
| `REGISTER` | New connection accepted | Creates a new Session in `CONNECTING`/establishment phase |
| `REGISTER_ACK` | Registration accepted | Confirms new Session as `CONNECTED` after establishment processing |
| `BEACON` | Valid message received | Confirms active communication |
| `BEACON_ACK` | Valid acknowledgement sent/received | Confirms successful communication |
| `PING` | Sent over active Session | No direct state change |
| `PONG` | Valid response received | Confirms communication reachability |
| Connection loss | Active connection disappears | `CONNECTED → DISCONNECTED` |
| Orderly termination | Explicit Session closure | `CONNECTED → CLOSED` |

The exact connection-establishment sequencing is defined in
`reconnection-and-synchronization.md`.

### 4.2 New Session Rule

A new connection always creates a new Session.

For example:

```text
S042 = DISCONNECTED

New connection
      ↓
REGISTER
      ↓
New Session S043
      ↓
REGISTER_ACK
      ↓
S043 = CONNECTED
```

The protocol MUST NOT interpret `previous_session_id` as a request to reopen
`S042`.

---

# 5. Agent Health Transitions

The Agent health state machine is:

```text
UNKNOWN
   │
   │ valid registration / communication
   ▼
ALIVE
   │
   │ liveness threshold exceeded
   ▼
LIKELY_UNREACHABLE
   │
   ├── valid communication ──→ ALIVE
   │
   └── confirmed termination → TERMINATED
```

### 5.1 Message Mapping

| Message / Event | Condition | Agent health effect |
|---|---|---|
| `REGISTER` | Valid registration received | `UNKNOWN → ALIVE` |
| `BEACON` | Valid periodic communication | Confirms/maintains `ALIVE` |
| `PONG` | Valid response to liveness check | Confirms current reachability |
| `TASK_ACK` | Valid Agent response | Confirms communication but does not independently determine health |
| `RESULT` | Valid Result received | Confirms communication |
| Liveness threshold | Expected communication repeatedly absent | `ALIVE → LIKELY_UNREACHABLE` |
| Valid communication while suspected unreachable | Any valid Agent message | `LIKELY_UNREACHABLE → ALIVE` |
| Confirmed termination | Reliable termination evidence | `→ TERMINATED` |

Communication loss alone MUST NOT transition an Agent directly to
`TERMINATED`.

---

# 6. Agent Activity Transitions

The Agent activity state machine is:

```text
IDLE
  │
  │ Task starts
  ▼
BUSY
  │
  │ no active work
  ▼
IDLE
```

Protocol messages generally provide evidence about activity rather than
directly controlling it.

| Message / Event | Effect |
|---|---|
| `TASK` accepted and execution started | May cause `IDLE → BUSY` |
| `TASK_ACK` | Confirms Task acceptance; does not necessarily imply `BUSY` |
| `TASK_STATUS` with `RUNNING` | Provides evidence of `BUSY` |
| `RESULT` completing the active Task | May cause `BUSY → IDLE` if no other active Task remains |
| `BEACON` | Reports current activity state |
| Queued Task only | Does not necessarily cause `IDLE → BUSY` |

`RUNNING` remains a Task state, not an Agent activity state.

---

# 7. Task Transitions

The Task state machine is:

```text
PENDING
   │
   │ TASK dispatched
   ▼
WAITING_ACK
   │
   │ TASK_ACK
   ▼
QUEUED
   │
   │ execution starts
   ▼
RUNNING
   ├──────────────→ COMPLETED
   ├──────────────→ FAILED
   └──────────────→ TIMEOUT

QUEUED
   │
   │ cancellation
   ▼
CANCELLED
```

The exact lifecycle is defined in `task-lifecycle.md`.

## 7.1 `TASK`

A `TASK` message is associated with a C2 Task.

Normal processing:

```text
Task = PENDING
      ↓
TASK sent
      ↓
Task = WAITING_ACK
```

The message itself does not imply execution.

The C2 MUST NOT mark the Task as `RUNNING` merely because `TASK` was
transmitted.

## 7.2 `TASK_ACK`

A valid `TASK_ACK` provides confirmation that the Agent received and accepted
the Task.

Normal transition:

```text
WAITING_ACK
      │
      │ TASK_ACK
      ▼
QUEUED
```

Depending on implementation scheduling, the Agent may begin execution
immediately after acceptance. The resulting state is then determined by the
Task lifecycle rather than by the acknowledgement message alone.

A duplicate `TASK_ACK` MUST NOT create a new logical Task or repeat the Task
transition.

## 7.3 `TASK_STATUS`

`TASK_STATUS` provides evidence of the Agent's current Task state.

Possible mappings include:

| Reported status | C2 interpretation |
|---|---|
| `QUEUED` | Confirms/updates Task knowledge to `QUEUED` when consistent |
| `RUNNING` | Confirms/updates Task knowledge to `RUNNING` |
| `COMPLETED` | Confirms Task completion |
| `FAILED` | Confirms Task failure |
| `UNKNOWN` | Agent has no known state for the referenced Task |

A `TASK_STATUS` message does not automatically justify every possible
transition.

For example:

```text
COMPLETED
   ↓
TASK_STATUS = RUNNING
```

must not normally reopen the completed Task without explicit conflict
resolution.

## 7.4 `RESULT`

A valid `RESULT` provides execution evidence for a Task.

For a successful result:

```text
RUNNING
   │
   │ RESULT
   ▼
COMPLETED
```

For an execution error:

```text
RUNNING
   │
   │ RESULT / failure information
   ▼
FAILED
```

The exact Result status semantics remain subject to the final
implementation.

A Result MUST be correlated with its `task_id` when one is supplied.

A Result for an unknown Task MUST NOT create a new Task implicitly.

## 7.5 Task Communication Failure

Communication events do not directly imply Task failure.

For example:

```text
RUNNING
   │
   │ connection lost
   ▼
RUNNING
```

The Task may continue executing locally.

Likewise:

```text
QUEUED
   │
   │ connection lost
   ▼
QUEUED
```

A queued Task does not become `FAILED` merely because communication was lost.

---

# 8. Result Transitions

The Result model distinguishes execution from delivery.

Conceptually:

```text
Task execution
      ↓
Result produced
      ↓
Result retained by Agent
      ↓
Result transmitted
      ↓
Result received by C2
```

A Result may therefore exist before the C2 receives its corresponding
protocol message.

### 8.1 `RESULT`

A received `RESULT` provides evidence that:

```text
Task → execution outcome
```

and allows the C2 to associate the Result with its Task.

The Result's exact persistence/verification states remain implementation
dependent.

### 8.2 Lost Result

A lost Result message does not imply:

```text
Task → FAILED
```

The Agent may retain the Result and transmit it during a later synchronization
or recovery process.

Detailed Result recovery is defined in
`reconnection-and-synchronization.md` and `task-lifecycle.md`.

---

# 9. Liveness Message Transitions

Liveness messages affect communication knowledge rather than Task execution.

## 9.1 `BEACON`

```text
Agent
  │
  │ BEACON
  ▼
C2
```

A valid Beacon:

- confirms that the Agent can currently communicate;
- updates liveness-related information;
- may report lightweight Agent/Task information.

It does not directly change a Task state.

## 9.2 `BEACON_ACK`

```text
BEACON
   ↓
BEACON_ACK
```

The acknowledgement confirms successful handling of the Beacon.

It does not represent Task acknowledgement.

## 9.3 `PING` / `PONG`

```text
PING
  ↓
PONG
```

A valid `PONG`:

- confirms current communication reachability;
- may restore an Agent from `LIKELY_UNREACHABLE` to `ALIVE`;
- may confirm that a Session is still communicating.

It does not:

- complete a Task;
- acknowledge a Task;
- prove a Result was delivered.

---

# 10. Synchronization Message Transitions

Synchronization messages are associated with the Agent's communication state.

The high-level sequence is:

```text
New Session
     ↓
REGISTER
     ↓
REGISTER_ACK
     ↓
SYNCHRONIZING
     ↓
SYNC_STATE
     ↓
SYNC_STATE_RESPONSE
     ↓
SYNC_COMPLETE
     ↓
CONNECTED / normal operation
```

The exact reconciliation algorithm is intentionally not defined here.

### 10.1 `SYNC_STATE`

`SYNC_STATE` provides retained Agent state to the C2.

It does not itself change a Task state merely because a Task identifier is
present.

Instead, it provides evidence that the Synchronization Manager uses to
reconcile the C2's state.

### 10.2 `SYNC_STATE_RESPONSE`

`SYNC_STATE_RESPONSE` communicates the C2's reconciliation decisions and
required updates.

Potential consequences include:

- updating stale Task information;
- requesting retained Results;
- dispatching Tasks that are still pending;
- handling cancellation information.

Each consequence must be processed according to the authoritative state
machine.

### 10.3 `SYNC_COMPLETE`

`SYNC_COMPLETE` marks the end of the synchronization phase.

It permits the Agent to leave the synchronization phase and resume normal
communication/Task processing.

Detailed synchronization behavior belongs to
`reconnection-and-synchronization.md`.

---

# 11. File Transfer Transitions

File transfers use:

```text
FILE_START
FILE_CHUNK
FILE_END
```

The transfer state machine is:

```text
PENDING
   │
   │ FILE_START
   ▼
TRANSFERRING
   │
   │ FILE_END + validation
   ▼
COMPLETED

TRANSFERRING ──failure──→ FAILED
TRANSFERRING ──cancel────→ CANCELLED
```

### 11.1 `FILE_START`

Initiates a logical transfer.

Normal transition:

```text
PENDING
   ↓
FILE_START
   ↓
TRANSFERRING
```

### 11.2 `FILE_CHUNK`

Transfers part of the file.

A valid `FILE_CHUNK` normally leaves the transfer in:

```text
TRANSFERRING
```

A chunk alone does not indicate completion.

### 11.3 `FILE_END`

Marks the end of the transmitted file data.

The transfer may transition to `COMPLETED` only after required integrity and
completeness checks succeed.

Otherwise:

```text
TRANSFERRING
      ↓
FAILED
```

Detailed transfer semantics are defined in `file-transfer.md`.

---

# 12. Error Message Transitions

An `ERROR` message reports an error but does not have one universal state
transition.

Its effect depends on what the error concerns.

Examples:

```text
Protocol error
    → reject message
    → no domain state transition

Task execution error
    → Task may become FAILED

Transfer error
    → Transfer may become FAILED

Communication error
    → may contribute to Session/liveness state changes
```

Therefore:

> `ERROR` is evidence requiring domain-specific handling, not a universal
> state transition.

---

# 13. Cross-Message Correlation Rules

Protocol messages must be correlated with the correct domain entity.

### 13.1 Task Correlation

Messages concerning a Task use `task_id`:

```text
TASK
TASK_ACK
TASK_STATUS_QUERY
TASK_STATUS
RESULT
```

A message referencing an unknown Task must not silently create one unless an
explicit protocol rule later permits this.

### 13.2 Result Correlation

`RESULT` uses `result_id` as the logical Result identifier and normally
references the originating `task_id`.

Duplicate `result_id` values must not create duplicate logical Results.

### 13.3 Session Correlation

Session-bound messages use `session_id` to identify the communication episode.

A message associated with an old Session must not silently reactivate that
Session.

### 13.4 File Transfer Correlation

File messages use `transfer_id`:

```text
FILE_START
FILE_CHUNK
FILE_END
```

All chunks belonging to one transfer must reference the same logical
`transfer_id`.

---

# 14. Duplicate and Replay Protection

The protocol distinguishes three levels of identity:

```text
message_id
    → individual communication message

task_id
    → logical unit of work

result_id
    → logical execution result
```

Consequently:

```text
duplicate message
        ≠
duplicate Task
        ≠
duplicate Result
```

Implementations MUST ensure that duplicate protocol delivery does not cause
an invalid domain transition.

Examples:

```text
TASK M100
TASK M100
```

must not cause the same logical Task to be executed twice merely because the
message was delivered twice.

Similarly:

```text
RESULT R001
RESULT R001
```

must not create two logical Results.

---

# 15. Invalid Protocol-to-State Transitions

The following mappings are explicitly invalid:

| Situation | Invalid transition |
|---|---|
| Old Session receives communication after being replaced | `DISCONNECTED → CONNECTED` |
| Connection loss | `RUNNING → FAILED` solely from communication loss |
| Connection loss | `Agent ALIVE → TERMINATED` solely from communication loss |
| `TASK` transmitted | `PENDING → RUNNING` without acceptance/execution |
| `TASK_ACK` received | `WAITING_ACK → COMPLETED` |
| `PONG` received | `Task → COMPLETED` |
| Missing `RESULT` | `Task → FAILED` without execution evidence |
| Duplicate `TASK` | Create second logical Task |
| Duplicate `RESULT` | Create second logical Result |
| Unknown Result Task | Create implicit Task |
| Queued Task during outage | `QUEUED → RUNNING` solely because time passed |
| `SYNC_COMPLETE` | Automatically execute every queued Task without normal Task rules |

These rules prevent communication events from being confused with execution
events.

---

# 16. State Evidence vs State Commands

Protocol messages can have different semantic roles.

### Command

The C2 requests an operation:

```text
TASK
TASK_STATUS_QUERY
PING
```

### Acknowledgement

The receiving side confirms reception/acceptance:

```text
TASK_ACK
BEACON_ACK
REGISTER_ACK
```

### Report

The sender provides information about current state:

```text
TASK_STATUS
RESULT
BEACON
SYNC_STATE
```

### Synchronization

The sides reconcile retained state:

```text
SYNC_STATE
SYNC_STATE_RESPONSE
SYNC_COMPLETE
```

This distinction is important because a report does not necessarily command a
state transition, and an acknowledgement does not necessarily indicate
completion.

---

# 17. Representative Transition Scenarios

These scenarios illustrate the mapping without redefining the underlying
state machines.

## 17.1 Normal Task

```text
C2
 │
 │ TASK T001
 ▼
Agent
 │
 │ TASK_ACK T001
 ▼
C2
 │
 │ Task acknowledged
 ▼
Task = QUEUED
 │
 │ execution starts
 ▼
Task = RUNNING
 │
 │ RESULT R001
 ▼
Task = COMPLETED
```

## 17.2 Lost Task Acknowledgement

```text
TASK
  ↓
WAITING_ACK
  ↓
ACK not received
  ↓
PING
  ↓
PONG
  ↓
TASK_STATUS_QUERY
  ↓
TASK_STATUS
```

The recovery procedure is defined elsewhere. The important protocol rule is
that the missing acknowledgement does not itself prove Task failure.

## 17.3 Running Task During Communication Loss

```text
Task = RUNNING
       │
       │ connection lost
       ▼
Task = RUNNING

Agent executes locally
       │
       ▼
Result retained

New Session
       │
       ▼
Synchronization
       │
       ▼
RESULT transmitted
```

The Task remains an execution concern; the communication interruption is
handled by the Session and synchronization mechanisms.

---

# 18. Implementation Guidance

Protocol handlers should follow this general pattern:

```text
receive message
      ↓
deserialize
      ↓
validate
      ↓
identify message type
      ↓
resolve referenced domain entities
      ↓
verify preconditions
      ↓
apply permitted state transition
      ↓
persist state
      ↓
emit operational Event / response
```

A handler should not directly modify unrelated domain state merely because
the information is present in a message.

For example:

```text
PONG
```

should be handled by liveness/session logic and must not directly mark a Task
as completed.

Similarly:

```text
RESULT
```

should update the corresponding Task/Result state according to its semantics,
not modify the Session state except for communication evidence handled by the
appropriate component.

---

# 19. Relationship to Other Documents

| Document | Used here for |
|---|---|
| `protocol.md` | Message definitions and fields |
| `state-machines.md` | Valid states and transitions |
| `reconnection-and-synchronization.md` | Detailed reconnect/synchronization procedure |
| `task-lifecycle.md` | Detailed Task execution and recovery |
| `file-transfer.md` | Detailed transfer lifecycle |
| `data-model.md` | Entity identity and relationships |

This document should remain focused on the **mapping between protocol events
and domain state transitions**.

---

# 20. Open Questions

The following remain implementation decisions:

- exact transition handling for conflicting `TASK_STATUS` reports;
- exact behavior when a Result arrives before its Task state is synchronized;
- retry and acknowledgement timing;
- exact synchronization conflict-resolution rules;
- whether `BEACON_ACK` carries explicit correlation information;
- exact Result verification states;
- cancellation semantics;
- duplicate-retention duration;
- replay protection beyond bounded identifier history;
- exact error-to-state mapping for each error category.

These decisions should be recorded in `DECISIONS.md` once finalized.
