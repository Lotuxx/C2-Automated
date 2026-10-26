# Independent audit handoff — v5 (26 octobre 2026)

The project implements a fully async TLS C2 server and agent in Python.
All features listed below are verified by automated tests (`295 passed, 7 skipped`
over real loopback TLS where applicable) **and** by a live in-process integration
run performed during the v5 audit session.

## Feature matrix — implemented and tested

| Feature | Status | Evidence |
|---|---|---|
| TLS 1.2+ async server/agent | ✅ Real | `build_server_context`, `TLSv1_2`, untrusted-CA rejection test |
| Multi-agent simultaneous sessions | ✅ Real | 2 agents, 2 sessions, isolated workspaces — verified live |
| Task lifecycle (ACK → states → result) | ✅ Real | 51 state-machine tests + 12 DB integration tests |
| `echo`, `get_info` | ✅ Real | 7 agent command tests |
| `sysinfo` (deep OS/CPU/memory/network/env) | ✅ Real | JSON result, 8 tests, verified live |
| `shell` (read-only: pwd/whoami/uname) | ✅ Real | allowlist enforced, metacharacter rejection tested |
| `shellcode` (sandboxed binary execution) | ✅ Real | lab_dir sandbox, ELF/Mach-O/PE mismatch detection, timeout, 7 tests |
| BEACON periodic heartbeat | ✅ Real | `heartbeat_loop`, jitter, TLS loopback test |
| PING/PONG with RTT | ✅ Real | `ping_agent()`, message_id correlation, CLI RTT display |
| Upload / download via TLS | ✅ Real | SHA-256, O_EXCL, 128 KiB limit — verified live (upload+download) |
| Reconnection + reconciliation | ✅ Real | bounded reconnect, stuck tasks cancelled, TLS loopback test |
| Durable interruption journal (SQLite) | ✅ Real | `task_interruptions` table, 5 tests |
| Restart recovery (`reconcile_process_restart`) | ✅ Real | RUNNING→FAILED across DB close/reopen |
| Task execution timeout (watchdog) | ✅ Real | `timeout_task()` atomic, `--task-timeout`, race-safe, 6 tests |
| Automatic replay of read-only tasks | ✅ Real | `reserve_replay` atomic, `get_auto_replayable_interruptions`, 6 tests |
| Manual read-only retry | ✅ Real | `retry_interrupted_readonly`, one-shot linkage |
| **`self_remove` with real file deletion** | ✅ Real | Deletes installed files via manifest verifier when run from `pa-agent-lab-*`; graceful skip from source tree; 4 tests |
| **OS startup persistence** | ✅ Real | `agent/persistence.py`: systemd (Linux), launchd (macOS), Task Scheduler (Windows); `persist`/`unpersist` CLI; 7 tests |
| **Mutual TLS (mTLS)** | ✅ Real | `shared/mtls.py`, `--agent-ca`, CN enforced in REGISTER, 7 tests |
| Local install/uninstall | ✅ Real | `local_install.py`, manifest verifier, 10 tests |
| Rate limiting (60 msg/s per connection) | ✅ Real | `MAX_MESSAGES_PER_SECOND`, 2 tests |
| Re-registration blocked | ✅ Real | guard `agent_id is not None`, 5 tests |
| Interactive Rich CLI | ✅ Real | coloured tables, panels, ping RTT, JSON pretty-print, `_test_console` injection |
| `lab` local simulations | ✅ Local only | clearly separated from real commands, never dispatched to agents |
| Exact-once distributed execution | ❌ Not implemented | deliberate — would require distributed log; documented |
| Windows platform validation | ⚠️ Partial | `platform_compat.py`, ELF/Mach-O/PE detection; full live test pending |

## What `self_remove` does (corrected)

`task <agent> self_remove` now behaves in two modes:

- **From an installed copy** (`pa-agent-lab-*` directory with manifest):
  the agent performs a dry-run safety check via `local_install.uninstall(execute=False)`,
  then if all checks pass deletes the installed Python files (`execute=True`).
  Result message: `"Agent decommissioned: … installation deleted (N files: …)"`.

- **From the project source tree** (no matching directory name or no manifest):
  only the runtime marker (`runtime-state-*.json`) is deleted.
  Result message: `"Agent stopping: … Installed files were NOT deleted (source-tree run)"`.

In both cases: the TLS session closes, the process exits, and the agent does not reconnect.
Transferred files (`data/agent_files/`) are **never** deleted by `self_remove`.

## Known remaining limitations

- **Exact-once delivery**: a task interrupted mid-execution may have run partially.
  Read-only tasks are auto-replayed on reconnect; file transfers and lifecycle commands
  are not (documented design decision).
- **Windows full validation**: `platform_compat.py` maps shell commands cross-platform
  and ELF/Mach-O/PE mismatches are detected and reported; end-to-end live test on native
  Windows hardware pending.
- **Transfer resume**: interrupted uploads/downloads must be re-issued from scratch.
- **`sysinfo` on macOS**: uses `ifconfig -a` (Method 2) since `ip` is not available.
  Verified to parse correctly; not live-tested on hardware.

## Test run summary (v5)

```
python -m pytest tests/ -q --tb=no
295 passed, 7 skipped, 114 subtests passed
```

Skipped tests are platform-conditional (macOS/Windows paths running on Linux CI).
All 295 passing tests exercise real logic; no tests are skipped for missing features.

## Dependencies

```
pip install -r requirements.txt   # installs rich>=13.0.0 (CLI only)
```

Python 3.10+ required; 3.12 recommended.
