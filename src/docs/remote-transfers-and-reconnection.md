# Remote file transfers and reconnection — tested laboratory implementation

## Important scope

The `task <agent> upload ...` and `task <agent> download ...` commands are **real agent-side operations carried over the TLS C2 connection**, unlike `lab upload` / `lab download` which remain separate, server-local simulations. Both endpoints use explicitly configured, local **lab directories**. These commands cannot specify arbitrary filesystem paths.

### Transfer paths

| Direction | Source | Destination |
|---|---|---|
| `task <agent> upload sample.txt` | Server `--upload-dir` (default `data/server_files`) | Agent `--lab-dir` (default `data/agent_files`) |
| `task <agent> download sample.txt` | Agent `--lab-dir` | Server `--download-dir` (default `data/server_downloads`) |

Rules: simple ASCII filenames (1–64 characters, no directories or path traversal), no symlinks, regular files only, max **128 KiB**, SHA-256 integrity check, no overwriting existing destination files, and restrictive `0600` permissions on newly received files where supported. Binary files are sent as Base64 inside the existing JSON-lines `TASK` / `RESULT` messages over TLS. This is a small-file teaching demonstration, **not** a general-purpose file transfer service or streaming protocol.

### Agent reconnect after an established connection closes

The process retains its **same `agent_id`** across reconnections; the server assigns a **new `session_id`** for each new TLS connection. The agent runs REGISTER → REGISTER_ACK → SYNC_STATE → SYNC_COMPLETE again, then resumes periodic check-ins and newly dispatched tasks. Connection attempts use bounded exponential delays.

Example:

```bash
python -m agent.main --agent-id agent-lab-a \
    --beacon-interval 10 --beacon-jitter 2 \
    --reconnect-sessions 8 --reconnect-attempts 6 \
    --reconnect-max-delay 8
```

`--reconnect-sessions` is the maximum number of *new* sessions after the initial established session (default 8). `--reconnect-attempts` is the number of TLS dial attempts in each reconnection window (default 6); the initial startup still makes up to 10 attempts. Reconnect is not invisible: logging records each session. Setting `--reconnect-sessions 0` disables reconnect after establishment.

**Task semantics:** this agent does not persist tasks/results across process restarts or connection losses and does not replay unknown tasks. On disconnect, server-side in-flight work is marked failed or cancelled, depending on state. The operator can review the status and dispatch a new task manually. An operation might have completed on the agent just before disconnect without its RESULT reaching the server; manual re-dispatch must account for that ambiguity. A superseded old connection is prevented from deleting the replacement's connection entry or cancelling new-session tasks.

### Test procedure

1. Generate the development TLS certificate as described in `README.md`.
2. Start the server from the project root: `python -m server.main`.
3. In a second terminal, start the agent: `python -m agent.main --beacon-interval 10 --reconnect-sessions 8`.
4. Prepare the server-side source file: `mkdir -p data/server_files && printf 'transfer demo\n' > data/server_files/sample.txt`.
5. In `c2>` run `agents` to discover the agent prefix, then `task <prefix> upload sample.txt`, `tasks`, and `result <task-prefix>`.
6. Run `task <prefix> download sample.txt`, verify `data/server_downloads/sample.txt` exists, and compare `sha256sum` across the directories.
7. To test reconnection **without terminating the agent**, enter `disconnect <prefix>` at the server's `c2>` prompt. The server closes that one TLS session; the agent automatically establishes a new session. Run `sessions` and `agents`, observe the unchanged agent ID with a new session ID, and dispatch `task <prefix> echo after-reconnect`. Alternatively, stop and restart the server within the configured retry window.

Automated integration test: `python -m unittest tests.test_remote_transfer_reconnect -v`. It generates a temporary local TLS certificate, uses a real loopback TLS socket, transfers a file in both directions, closes an established connection, verifies the new session, and runs an additional task after reconnection. Temporary certificate and test files are automatically cleaned up. Requires `openssl` in PATH.

### Remaining limitations

- TLS authenticates the **server** to the agent, but this design does not provide independently verified **agent identity** (agent IDs are self-declared). Do not use on an untrusted network.
- Data is small and encoded entirely inside one JSON message; there are no resumable/chunked transfers.
- The server's SQL task record retains upload parameters, including Base64 content; only use non-sensitive disposable test files.
- A missing reconnect-side task replay journal means *at-most-once manual re-dispatch*, not exact-once execution guarantees.
- The application has no rate limits, role-based access control, message authentication beyond its TLS session, or production hardening.
- OS startup persistence is implemented via `agent/persistence.py` (`persist`/`unpersist` CLI tasks, systemd/launchd/Task Scheduler). Agent self-removal is implemented: `self_remove` deletes installed files from a `pa-agent-lab-*` copy (manifest-verified). The `lab persist` and `lab self_destruct` commands remain local simulations and never touch a connected agent.

## Mise à jour du 25/10/2026 — contrôles supplémentaires

Voir `docs/audit-handoff.md` pour la matrice de conformité complète v5 et `docs/durable-recovery-and-decommission.md` pour le comportement détaillé de `self_remove` (suppression réelle des fichiers installés depuis v3), du journal d'interruptions SQLite, du watchdog de timeout, et du replay automatique des tâches lecture-seule. La persistance OS est désormais implémentée (systemd / launchd / Task Scheduler) via `agent/persistence.py`.
