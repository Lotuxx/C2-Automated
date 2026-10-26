# Interruption recovery, verification and agent decommission (25/10/2026)

## What is implemented

A SQLite `task_interruptions` table durably records the **previous state** (`PENDING`, `WAITING_ACK`, `QUEUED` or `RUNNING`), the **reason**, **outcome uncertainty**, an interruption timestamp and the ID of one linked manual retry. Writing the interruption and updating task status are done in **one transaction**.

When a connection drops, interrupted `RUNNING` tasks become `FAILED` and `WAITING_ACK` or `QUEUED` become `CANCELLED`, as before, but the interruption reason is now retained. During startup `reconcile_process_restart()` marks nonterminal tasks from a prior server process and closes sessions left open by that process. The startup reconciliation is idempotent. A completed task and its result are never overwritten by reconciliation.

The `interrupted` CLI command lists these persistent records. `retry <task_id_prefix>` creates a **new task with a new task ID** and permanently links it to the interrupted original, **only** for `echo`, `get_info`, and the restricted read-only `shell` operations. A second retry of the same original task is rejected. The original task and its outcome uncertainty remain visible. File transfers are **not** automatically or manually retried through this command; resend them explicitly after inspecting the lab directories. A transfer may have succeeded just before its result was lost.

**Critical limitation:** This is **durable recovery of task history, interruption bookkeeping and controlled read-only reissue**, not crash-resumable agent execution, durable agent-side output storage, distributed exactly-once delivery or automatic task replay. The running agent does not persist in-flight tasks/results between sessions. `WAITING_ACK`, `QUEUED` and `RUNNING` all have `UNKNOWN_OUTCOME` because dispatch or execution may have occurred before the link failed. `PENDING` is classified `NOT_SENT`.

## Graceful `self_remove` operation

The real agent accepts `task <agent_id_prefix> self_remove` with **no parameters**. It sends `TASK_ACK`, `TASK_STATUS RUNNING`, then a final `RESULT COMPLETED`, closes the TLS session, and exits without reconnecting.

**Behaviour depends on the execution context:**

- **Installed copy** (`pa-agent-lab-*` directory with manifest present):
  performs a dry-run safety check via `local_install.uninstall(execute=False)`,
  then deletes all installed Python files on success.
  Result: `"Agent decommissioned: … installation deleted (N files: …)"`.

- **Source tree** (directory name does not match `pa-agent-lab-*`, or no manifest):
  only the runtime marker (`runtime-state-*.json`) is deleted.
  Result: `"Agent stopping: … Installed files were NOT deleted (source-tree run)"`.

In both cases, transferred lab files (`data/agent_files/`) are **never** deleted.

The `lab self_destruct` command remains a server-local simulation that only deletes a local JSON simulation manifest — it never touches a connected agent.

Arbitrary path deletion or host wiping is never implemented; `self_remove` only touches the manifest-verified file list from `INSTALLED_FILES`.

## Testable live demonstration

1. Start server and an agent in isolated terminals. Specify `--agent-id lab-agent-a --lab-dir data/agent_a_files` for a repeatable identity and separate files.
2. At `c2>`: `agents`, `sessions`, `ping lab-agent-a`, `task lab-agent-a echo test`, `task lab-agent-a get_info`, `task lab-agent-a shell whoami`, `result <task_id>`.
3. Inspect `data/agent_a_files/runtime-state-*.json` while the agent is running. Enter `task lab-agent-a self_remove`; `result <task_id>`, then check that the agent process exits and the runtime marker disappears while other files remain.
4. For interruption/retry, reconnect an agent and deliberately disconnect during an in-flight read-only task (or reproduce state with the DB recovery tests). After an interruption, `interrupted` shows the saved evidence; `retry <original_task_id>` is available only after synchronization and only for read-only commands. Do not assume any task will be replayed automatically.
5. To test startup recovery deterministically without needing timing tricks, run `python -m unittest tests.test_durable_recovery_and_audit -v` and inspect the restart-ledger tests.

## Automated tests

`tests/test_durable_recovery_and_audit.py` verifies a persistent SQLite restart across a newly opened DB connection, preservation of completed results, atomic/idempotent interruption records, no automatic replay, single linked retry, real TLS read-only tasks and shell rejection, TLS PING/PONG, periodic beacon receipt, certificate rejection with an untrusted CA, bounded self-removal behavior and preservation of pre-existing files. The existing transfer/reconnect suite continues testing remote uploads/downloads and two isolated agents.

## Étape locale supplémentaire — désinstallation du programme installé

Le module `agent.local_install` permet d'installer une copie jetable dans un dossier réservé (`pa-agent-lab-*`) et de supprimer cette copie locale après arrêt. La commande `TASK self_remove` **déclenche désormais** cette suppression automatiquement quand l'agent détecte qu'il tourne depuis une telle copie (vérification du nom de dossier + présence du manifeste + dry-run de sécurité). La désinstallation locale manuelle reste disponible via `uninstall --execute`. Voir `docs/local-install-and-uninstall.md`.
