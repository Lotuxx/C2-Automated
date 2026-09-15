# File Transfer

> **Status: Work in Progress**
>
> This document describes the current conceptual design of file transfers
> between the C2 server and agents. The transfer protocol, state handling,
> metadata, and implementation details may evolve as the architecture is
> finalized.

---

## 1. Purpose

File transfer is treated as a dedicated subsystem rather than as an ordinary
task result.

The design separates four concerns:

1. **File-transfer management** — managing the lifecycle of a transfer;
2. **File storage** — storing the actual file data;
3. **Transport protection** — protecting the data while it travels over the
   network;
4. **Integrity verification** — verifying that the reconstructed file matches
   the expected content.

The main principle is:

```text
File Transfer Management
          ↓
     File Storage
```

while network communication remains handled independently through the
protocol and transport layers.

---

# 2. Architectural Responsibilities

The file-transfer subsystem is divided into distinct responsibilities.

```text
                         File Manager
                              │
              ┌───────────────┴───────────────┐
              │                               │
              ▼                               ▼
       Transfer Management              File Storage
              │                               │
              ▼                               ▼
      Transfer metadata                 Filesystem
      Transfer state                         │
                                              ▼
                                        data/files/
```

### File Manager

The File Manager handles the logical transfer lifecycle, including:

- starting a transfer;
- tracking transfer state;
- associating a transfer with an agent and, when applicable, a task;
- handling transfer completion;
- coordinating reconstruction;
- triggering integrity verification.

### File Storage

The file-storage component is responsible for physically storing file data.

It is accessed through a storage abstraction:

```text
File Manager
     ↓
File Storage Interface
     ↓
Filesystem Storage
```

The File Manager should therefore not depend directly on filesystem-specific
implementation details.

---

# 3. File Storage Locations

Both the C2 server and the agent maintain dedicated file workspaces.

The current conceptual structure is:

```text
data/
└── files/
    ├── uploads/
    ├── downloads/
    └── temporary/
```

The purpose of each directory is:

| Directory | Purpose |
|---|---|
| `uploads/` | Files received by the component |
| `downloads/` | Files prepared for or retrieved for delivery |
| `temporary/` | Temporary workspace used during transfer processing |

The exact meaning of the `uploads/` and `downloads/` names depends on the
component and transfer direction.

The important architectural rule is that transfer-related files use the
defined workspace rather than arbitrary storage locations.

---

# 4. Storage Implementation

The storage implementation is separated from the actual data directory.

```text
storage/
└── files/
    ├── interface.py
    └── filesystem.py
```

### `interface.py`

Defines the abstraction for file persistence.

The rest of the application interacts with this abstraction instead of
depending directly on filesystem operations.

### `filesystem.py`

Provides the filesystem-based implementation.

The physical data is stored under:

```text
data/files/
```

This separation allows the storage implementation to be replaced or extended
without changing the transfer-management logic.

---

# 5. Transfer Messages

File transfers are represented using dedicated protocol messages.

The current conceptual message sequence is:

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
```

The protocol therefore distinguishes:

- transfer initialization;
- transfer data;
- transfer completion.

The exact fields of these messages are defined in
[`protocol.md`](protocol.md) once the protocol contract is finalized.

---

# 6. Transfer Identifier

Each transfer should have its own identifier.

Conceptually:

```text
transfer_id
```

This allows multiple transfers to be distinguished even when several agents
or tasks are active simultaneously.

A transfer may also be associated with:

```text
agent_id
task_id
```

where applicable.

---

# 7. Transfer Lifecycle

The current conceptual lifecycle is:

```text
             ┌──────────┐
             │ STARTING │
             └────┬─────┘
                  │
                  ▼
             TRANSFERRING
                  │
                  ▼
             RECONSTRUCTING
                  │
                  ▼
             VERIFYING
              /       \
             /         \
            ▼           ▼
        COMPLETED      FAILED
```

This is a **conceptual model**, not yet a finalized implementation state
machine.

The exact state model may instead be integrated with the task lifecycle or
defined independently.

---

# 8. Starting a Transfer

A transfer begins when the application creates a transfer operation.

Conceptually:

```text
Operator / Task
       ↓
File Manager
       ↓
Transfer Created
       ↓
FILE_START
```

The initial metadata may include:

```text
transfer_id
agent_id
filename
size
direction
expected_hash
```

The exact metadata remains to be finalized.

---

# 9. Chunked Transfer

The actual file data is transferred using chunks.

Conceptually:

```text
File
 │
 ├── Chunk 1
 ├── Chunk 2
 ├── Chunk 3
 └── ...
```

Each chunk is processed independently.

The receiving side should not need to hold the complete file in memory.

Conceptually:

```text
FILE_CHUNK
    ↓
validate
    ↓
write
    ↓
next chunk
```

This allows the transfer subsystem to handle larger files more efficiently.

The exact chunk size and chunk metadata remain to be determined.

---

# 10. Temporary Storage

Received data should initially be stored in the temporary workspace while the
transfer is still incomplete.

```text
Incoming Chunks
       ↓
Temporary File
       ↓
FILE_END
       ↓
Integrity Verification
       ↓
Final File
```

An incomplete or invalid transfer should not be treated as a completed file.

Temporary files should be removed when they are no longer required.

---

# 11. Agent to C2 Transfer

When an agent sends a file to the C2 server, the conceptual flow is:

```text
Agent File
     │
     ▼
Agent File Handling
     │
     ▼
Protocol
     │
     ▼
TLS Transport
     │
     ▼
C2 Transport
     │
     ▼
C2 Protocol
     │
     ▼
C2 File Manager
     │
     ▼
Temporary File
     │
     ▼
Integrity Verification
     │
     ▼
C2 File Storage
```

The final location is determined by the transfer operation.

Conceptually:

```text
Agent
  │
  └── file
       ↓
C2 data/files/uploads/
```

---

# 12. C2 to Agent Transfer

When the C2 server sends a file to an agent, the conceptual flow is:

```text
C2 File Storage
     │
     ▼
C2 File Manager
     │
     ▼
Protocol
     │
     ▼
TLS Transport
     │
     ▼
Agent Transport
     │
     ▼
Agent Protocol
     │
     ▼
Temporary File
     │
     ▼
Integrity Verification
     │
     ▼
Agent File Storage
```

Conceptually:

```text
C2
  │
  └── file
       ↓
Agent data/files/downloads/
```

The precise naming of the destination directories remains subject to
implementation refinement.

---

# 13. Protocol and Transport Separation

File transfers use the same architectural separation as other C2-Agent
communication.

```text
File Manager
      ↓
Protocol
      ↓
Transport
      ↓
Network
```

The protocol defines **what is transferred**.

The transport defines **how it travels**.

The file manager does not need to know the details of TCP/TLS sockets.

---

# 14. Encryption in Transit

The mandatory communication mechanism for the MVP is TCP/TLS.

File transfers use this protected transport.

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

This protects file contents while they are travelling between the C2 server
and agent.

Separate application-level file encryption is therefore not required for the
MVP solely to provide confidentiality during transmission.

See [`../SECURITY.md`](../SECURITY.md) for the broader security model.

---

# 15. File Integrity

Confidentiality and integrity are treated as separate properties.

TLS protects the communication channel, while the transfer subsystem is
intended to verify the reconstructed file.

The current design uses a cryptographic hash such as SHA-256.

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
  Compare
```

Conceptually:

```text
hash matches
    → transfer accepted

hash differs
    → transfer rejected / marked invalid
```

The exact mechanism for communicating and validating the expected hash is
still part of the protocol design.

---

# 16. Encryption at Rest

Encryption at rest is separate from encryption in transit.

The current MVP decision is:

```text
Encryption in transit
    → TLS

File integrity
    → cryptographic hash

Application-level file encryption at rest
    → not mandatory for MVP
```

Additional encryption of stored files may be considered later as a
defense-in-depth feature.

Such an extension would require an explicit key-management design.

---

# 17. Path Handling

File names and paths originating from protocol messages or other external
input must not be trusted directly.

The transfer subsystem should ensure that generated storage paths remain
inside the intended workspace.

Conceptually:

```text
External File Information
          ↓
      Validation
          ↓
Controlled Storage Path
          ↓
data/files/...
```

The implementation should prevent externally supplied paths from escaping the
defined transfer-storage directories.

---

# 18. Large Files and Memory Usage

The file-transfer mechanism should process data incrementally.

The preferred conceptual model is:

```text
read chunk
    ↓
process chunk
    ↓
write chunk
    ↓
release chunk
    ↓
read next chunk
```

rather than:

```text
read entire file
       ↓
load everything into memory
       ↓
send entire file
```

This reduces unnecessary memory usage and makes the implementation more
appropriate for larger files.

---

# 19. Failure Handling

The transfer subsystem must account for failures such as:

- interrupted connections;
- incomplete transfers;
- missing chunks;
- unexpected chunks;
- duplicate chunks;
- invalid transfer identifiers;
- invalid metadata;
- storage failures;
- integrity verification failures;
- insufficient local storage.

A failed transfer should not leave an apparently valid final file.

Temporary artifacts should be cleaned up according to the final transfer
failure policy.

---

# 20. Task Relationship

A file transfer may be associated with a task.

Conceptually:

```text
Task
  │
  └── File Transfer
        │
        ├── transfer metadata
        ├── chunks
        └── final file
```

However, file-transfer state should remain distinct from the general task
state where necessary.

For example, a task may represent the request to transfer a file, while the
associated transfer tracks the file-specific lifecycle.

The exact relationship will be finalized in the data model.

---

# 21. Current Design Summary

The current architecture can be summarized as:

```text
                    File Operation
                          │
                          ▼
                    File Manager
                          │
                          ▼
                       Protocol
                          │
                          ▼
                     TLS Transport
                          │
                          ▼
                        Network
                          │
                          ▼
                   Remote File Manager
                          │
                          ▼
                  Temporary Workspace
                          │
                          ▼
                 Integrity Verification
                          │
                          ▼
                    Final File Storage
```

The important separation is:

```text
File Manager
    → manages the transfer

Protocol
    → represents the transfer

Transport
    → transmits the transfer

File Storage
    → persists the file

Temporary Workspace
    → holds incomplete/intermediate data
```

---

# 22. Open Questions

The following subjects remain to be finalized:

- exact transfer state machine;
- exact `FILE_START` fields;
- exact `FILE_CHUNK` fields;
- exact `FILE_END` fields;
- chunk numbering;
- chunk size;
- transfer ordering guarantees;
- expected-hash representation;
- when the hash is calculated and transmitted;
- resumable transfers;
- retry behaviour;
- cleanup policy;
- maximum transfer size;
- transfer/task relationship;
- exact naming semantics of `uploads/` and `downloads/`;
- behaviour when an agent disconnects during a transfer.

These decisions should be finalized together with the protocol and data-model
design and recorded in [`DECISIONS.md`](../DECISIONS.md) when they represent
significant architectural choices.
