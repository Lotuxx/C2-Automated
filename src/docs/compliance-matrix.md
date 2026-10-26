# Requirements Compliance Matrix — PA-C2

## Academic requirements

| Requirement | Status | Evidence |
|---|---|---|
| Clean client/server architecture | ✅ Implemented & verified | Separate server/ and agent/ packages, shared/ protocol layer |
| Multiple connected agents & sessions | ✅ Implemented & verified | Gate7 G1-G2: 2 agents, 2 sessions live |
| Linux-compatible agent | ✅ Implemented & verified | Tested on Linux/WSL2 throughout |
| Asynchronous communication | ✅ Implemented & verified | asyncio throughout; execute_allowed in to_thread (v7) |
| Encrypted TLS communication | ✅ Implemented & verified | TLS 1.2+ mandatory, untrusted CA test |
| Documented protocol | ✅ Implemented & verified | docs/protocol.md, shared/protocol.py with docstrings |
| Centralized task dispatch | ✅ Implemented & verified | dispatch_task(), TASK/ACK/STATUS/RESULT flow |
| Task result collection | ✅ Implemented & verified | results table, list_results(), CLI result command |
| Shell command functionality | ✅ Implemented & verified | shell: pwd/whoami/uname, allowlist enforced |
| File upload | ✅ Implemented & verified | 128 KiB tested live (Gate7 G7) |
| File download | ✅ Implemented & verified | Gate7 G8: SHA-256 verified |
| System information collection | ✅ Implemented & verified | sysinfo: OS/CPU/memory/network/env/uptime JSON |
| Agent persistence lifecycle | ✅ Implemented & verified | systemd/launchd/Task Scheduler via agent/persistence.py |
| Agent self-removal lifecycle | ✅ Implemented & verified | self_remove deletes installed files (manifest-verified) |
| Usable operator interface | ✅ Implemented & verified | Rich CLI: tables, colours, ping RTT, JSON pretty-print |
| Configurable beacon interval | ✅ Implemented & verified | --beacon-interval, --beacon-jitter flags |
| Authorized isolated lab | ✅ By design | 127.0.0.1 default, lab_dir sandbox, no arbitrary paths |
| Architecture diagrams | ✅ Updated | docs/architecture.md v7 |
| Network diagrams | ✅ Updated | docs/architecture.md — ASCII network diagram |
| Kill-chain analysis | ✅ Updated | docs/kill-chain-and-countermeasures.md |
| Defensive countermeasures | ✅ Updated | docs/kill-chain-and-countermeasures.md |
| **Automation/orchestration** | ✅ Implemented & verified | AutomationManager, playbooks, CLI commands, 33 tests |

## Extended features (beyond minimum requirements)

| Feature | Status | Notes |
|---|---|---|
| mTLS mutual authentication | ✅ Complete | --agent-ca, CN enforced, 7 tests |
| Task execution timeout watchdog | ✅ Complete | asyncio Task, timeout_task() atomic |
| Durable interruption journal | ✅ Complete | task_interruptions SQLite table |
| Auto-replay read-only tasks | ✅ Complete | reserve_replay atomic, 6 tests |
| Orphan reservation cleanup (v7) | ✅ Complete | clear_orphaned_replay_reservations() on restart |
| Shellcode execution | ✅ Complete | sandboxed binary execution, magic header detection |
| OS startup persistence | ✅ Complete | systemd + launchd + Task Scheduler |
| Rate limiting | ✅ Complete | 60 msg/s per connection |
| Cross-platform network enumeration | ✅ Complete | ip/ifconfig/ioctl/gethostbyname cascade |

## Known limitations (documented design decisions)

| Limitation | Reason |
|---|---|
| Exact-once task delivery | Would require distributed log; safe replay for read-only only |
| Windows live testing | Requires Windows hardware; code paths covered by unit tests |
| Transfer resume | Interrupted uploads/downloads must be re-issued |
| Agent-side durable result store | No local DB on agent; server handles reconciliation |
| mTLS requires manual cert generation | OpenSSL CLI required; documented in README |
