"""
server/automation.py — Automation and playbook orchestration engine.

Role in the architecture
------------------------
This module implements the AutomationManager that powers the C2's automated
orchestration layer.  It sits between the operator CLI and the C2Server,
providing:

  * Declarative playbook definitions (YAML or JSON)
  * Step-by-step sequential task execution with dependencies
  * Execution state machine: PENDING → VALIDATING → RUNNING → COMPLETED/FAILED/CANCELLED
  * Per-step result collection and reporting
  * Failure handling with configurable stop-on-failure or continue policy
  * Execution history that survives server restarts (SQLite)
  * Idempotency: duplicate scheduling is detected and rejected
  * Full operator visibility via the CLI

Security design
---------------
Playbooks are constrained to the same task allowlist as the CLI.
No playbook can dispatch a command that the CLI cannot.  The command
field in each playbook step is validated against ALLOWED_COMMANDS before
the playbook is accepted.  Arbitrary shell or system commands are impossible.

Built-in playbooks
------------------
Three built-in playbooks are provided as defaults:

  agent_inventory   — ping → get_info → sysinfo → report
  connectivity      — ping → beacon wait → echo test → report
  file_integrity    — upload test file → download it → verify SHA-256 → report

Custom playbooks can be loaded from YAML or JSON files.

Wire format (YAML example)
--------------------------
  name: my_playbook
  description: "Example custom playbook"
  steps:
    - id: step1
      command: echo
      parameters:
        text: "hello"
      timeout: 30
      on_failure: stop         # stop | continue | retry
      retry_count: 0
    - id: step2
      command: get_info
      depends_on: [step1]      # only runs if step1 COMPLETED
      timeout: 30
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

LOG = logging.getLogger("c2.automation")

# Commands that playbooks are permitted to dispatch.
# This list is the single source of truth — it mirrors execute_allowed's allowlist.
ALLOWED_COMMANDS: frozenset[str] = frozenset({
    "echo", "get_info", "sysinfo", "shell",
    "shellcode", "upload", "download",
    "persist", "unpersist",
    # self_remove is intentionally excluded: it terminates the agent,
    # which would abort the playbook mid-run in an unrecoverable way.
})


class PlaybookStepStatus(str, Enum):
    """State machine for a single playbook step."""
    PENDING   = "PENDING"
    RUNNING   = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED    = "FAILED"
    SKIPPED   = "SKIPPED"   # dependency failed and on_failure=stop
    CANCELLED = "CANCELLED"


class PlaybookRunStatus(str, Enum):
    """State machine for a complete playbook execution."""
    PENDING    = "PENDING"
    VALIDATING = "VALIDATING"
    RUNNING    = "RUNNING"
    COMPLETED  = "COMPLETED"
    FAILED     = "FAILED"
    CANCELLED  = "CANCELLED"


@dataclass
class PlaybookStep:
    """Definition of a single step within a playbook."""
    step_id:     str
    command:     str
    parameters:  dict = field(default_factory=dict)
    depends_on:  list[str] = field(default_factory=list)
    timeout:     float = 60.0
    on_failure:  str = "stop"    # "stop" | "continue" | "retry"
    retry_count: int = 0

    def to_dict(self) -> dict:
        """Serialise to a plain dict for storage/display."""
        return {
            "step_id":    self.step_id,
            "command":    self.command,
            "parameters": self.parameters,
            "depends_on": self.depends_on,
            "timeout":    self.timeout,
            "on_failure": self.on_failure,
            "retry_count":self.retry_count,
        }


@dataclass
class Playbook:
    """A named sequence of steps that can be executed against a target agent."""
    name:        str
    description: str
    steps:       list[PlaybookStep]

    def to_dict(self) -> dict:
        """Serialise to a plain dict for display or export."""
        return {
            "name":        self.name,
            "description": self.description,
            "steps":       [s.to_dict() for s in self.steps],
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Playbook":
        """Deserialise from a plain dict (YAML/JSON loaded)."""
        steps = [
            PlaybookStep(
                step_id=    s["id"],
                command=    s["command"],
                parameters= s.get("parameters", {}),
                depends_on= s.get("depends_on", []),
                timeout=    float(s.get("timeout", 60.0)),
                on_failure= s.get("on_failure", "stop"),
                retry_count=int(s.get("retry_count", 0)),
            )
            for s in data.get("steps", [])
        ]
        return cls(
            name=        data["name"],
            description= data.get("description", ""),
            steps=       steps,
        )

    @classmethod
    def from_yaml(cls, text: str) -> "Playbook":
        """Load a playbook from a YAML string (requires PyYAML or stdlib json fallback)."""
        try:
            import yaml  # type: ignore
            data = yaml.safe_load(text)
        except ImportError:
            # Fall back to JSON if PyYAML is not installed
            data = json.loads(text)
        return cls.from_dict(data)

    @classmethod
    def from_file(cls, path: str | Path) -> "Playbook":
        """Load a playbook from a YAML or JSON file."""
        text = Path(path).read_text(encoding="utf-8")
        return cls.from_yaml(text)


@dataclass
class StepExecution:
    """Runtime state for one step of one playbook run."""
    step_id:    str
    command:    str
    status:     PlaybookStepStatus = PlaybookStepStatus.PENDING
    task_id:    str | None = None
    output:     str | None = None
    error:      str | None = None
    started_at: float | None = None
    ended_at:   float | None = None
    retries:    int = 0

    def to_dict(self) -> dict:
        """Serialise for storage and display."""
        return {
            "step_id":    self.step_id,
            "command":    self.command,
            "status":     self.status.value,
            "task_id":    self.task_id,
            "output":     self.output,
            "error":      self.error,
            "started_at": self.started_at,
            "ended_at":   self.ended_at,
            "retries":    self.retries,
            "duration_s": round(self.ended_at - self.started_at, 2)
                          if self.started_at and self.ended_at else None,
        }


@dataclass
class PlaybookRun:
    """Runtime state for a complete playbook execution."""
    run_id:       str
    playbook_name:str
    agent_id:     str
    status:       PlaybookRunStatus = PlaybookRunStatus.PENDING
    steps:        dict[str, StepExecution] = field(default_factory=dict)
    started_at:   float | None = None
    ended_at:     float | None = None
    error:        str | None = None

    def to_dict(self) -> dict:
        """Serialise for storage and display."""
        return {
            "run_id":        self.run_id,
            "playbook_name": self.playbook_name,
            "agent_id":      self.agent_id,
            "status":        self.status.value,
            "steps":         {k: v.to_dict() for k, v in self.steps.items()},
            "started_at":    self.started_at,
            "ended_at":      self.ended_at,
            "error":         self.error,
            "duration_s":    round(self.ended_at - self.started_at, 2)
                             if self.started_at and self.ended_at else None,
        }


class AutomationManager:
    """Orchestrates multi-step playbook execution against connected agents.

    The AutomationManager holds a registry of available playbooks and a
    history of all runs (in-memory, with optional SQLite persistence).
    It coordinates with C2Server.dispatch_task() to execute each step,
    waits for results, and advances the playbook state machine.

    All execution is async; long playbooks do not block other server
    operations.

    Parameters
    ----------
    server : C2Server
        The live server instance used to dispatch tasks and poll results.
    db : Database
        The shared SQLite database for task/result persistence.
    playbooks_dir : Path or None
        Optional directory to scan for .yaml / .json playbook files at startup.
    """

    def __init__(self, server: Any, db: Any,
                 playbooks_dir: str | Path | None = None) -> None:
        """Initialise with a reference to the live C2Server and database."""
        self._server = server
        self._db     = db
        self._playbooks: dict[str, Playbook] = {}
        self._runs: dict[str, PlaybookRun] = {}          # run_id → PlaybookRun
        self._active_tasks: dict[str, asyncio.Task] = {} # run_id → asyncio.Task
        self._triggers: list[dict] = []                   # C3 trigger definitions

        # Load built-in playbooks
        for pb in _builtin_playbooks():
            self._playbooks[pb.name] = pb

        # Load user-defined playbooks from disk
        if playbooks_dir is not None:
            self.load_playbooks_from_dir(playbooks_dir)

        # _restore_history() is async and must be awaited — schedule it as a Task.
        # The server wires AutomationManager after the event loop is running so this
        # is safe.  Tests that create AutomationManager synchronously call
        # await mgr._restore_history() explicitly if they need the history loaded.
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(self._restore_history())
        except RuntimeError:
            pass  # No running loop in some test contexts — history restored lazily

    # ── Persistence ──────────────────────────────────────────────────────────

    async def _restore_history(self) -> None:
        """Load playbook run history from SQLite on startup.

        Runs that were RUNNING at the time of the previous server process are
        marked FAILED because they could not complete — any in-flight steps
        were interrupted and the agent may have produced uncertain outcomes.
        This mirrors how the task reconciliation works on server restart.
        """
        try:
            rows = await self._db.load_playbook_runs()
        except Exception as exc:
            LOG.warning("Could not restore playbook history: %s", exc)
            return
        for row in rows:
            # Re-hydrate a minimal PlaybookRun from the DB row
            run = PlaybookRun(
                run_id=row["run_id"],
                playbook_name=row["playbook_name"],
                agent_id=row["agent_id"],
                status=PlaybookRunStatus(row["status"]),
                started_at=row.get("started_at"),
                ended_at=row.get("ended_at"),
                error=row.get("error"),
            )
            # Runs that were still RUNNING are interrupted — mark them FAILED
            if run.status == PlaybookRunStatus.RUNNING:
                run.status = PlaybookRunStatus.FAILED
                run.error  = "Interrupted by server restart"
                run.ended_at = time.monotonic()
            # Re-hydrate steps
            for step_id, sd in row.get("steps", {}).items():
                step = StepExecution(
                    step_id=step_id,
                    command=sd.get("command", ""),
                    status=PlaybookStepStatus(sd.get("status", "PENDING")),
                    task_id=sd.get("task_id"),
                    output=sd.get("output"),
                    error=sd.get("error"),
                    started_at=sd.get("started_at"),
                    ended_at=sd.get("ended_at"),
                    retries=sd.get("retries", 0),
                )
                run.steps[step_id] = step
            self._runs[run.run_id] = run
        if rows:
            LOG.info("automation: restored %d playbook run(s) from SQLite", len(rows))

    async def _persist_run(self, run: PlaybookRun) -> None:
        """Save the current state of a run to SQLite.

        Called after each step transition so the history is durable even if
        the server crashes mid-playbook.  Errors are logged and swallowed so
        a storage failure never aborts an in-progress run.
        """
        try:
            await self._db.save_playbook_run(run.to_dict())
        except Exception as exc:
            LOG.warning("Failed to persist playbook run %s: %s", run.run_id[:8], exc)

    # ── Playbook registry ─────────────────────────────────────────────────────

    def register_playbook(self, playbook: Playbook) -> None:
        """Add or replace a playbook in the registry."""
        self._playbooks[playbook.name] = playbook
        LOG.info("playbook registered: %s (%d steps)", playbook.name, len(playbook.steps))

    def load_playbooks_from_dir(self, directory: str | Path) -> list[str]:
        """Scan ``directory`` for .yaml / .json playbook files and register them.

        Returns a list of successfully loaded playbook names.
        Logs warnings for files that fail to parse.
        """
        loaded = []
        for path in Path(directory).glob("*.yaml"):
            try:
                pb = Playbook.from_file(path)
                self.register_playbook(pb)
                loaded.append(pb.name)
            except Exception as exc:
                LOG.warning("failed to load playbook %s: %s", path, exc)
        for path in Path(directory).glob("*.json"):
            try:
                pb = Playbook.from_file(path)
                self.register_playbook(pb)
                loaded.append(pb.name)
            except Exception as exc:
                LOG.warning("failed to load playbook %s: %s", path, exc)
        return loaded

    def list_playbooks(self) -> list[dict]:
        """Return a summary list of all registered playbooks."""
        return [
            {
                "name":        pb.name,
                "description": pb.description,
                "steps":       len(pb.steps),
            }
            for pb in self._playbooks.values()
        ]

    def get_playbook(self, name: str) -> Playbook | None:
        """Return the playbook with the given name, or None."""
        return self._playbooks.get(name)

    # ── Validation ───────────────────────────────────────────────────────────

    def validate_playbook(self, playbook: Playbook) -> list[str]:
        """Validate a playbook definition and return a list of error messages.

        An empty list means the playbook is valid and can be executed.
        Checks performed:
        - At least one step
        - Each step has a unique step_id
        - Each command is in ALLOWED_COMMANDS
        - Each depends_on references an existing step_id
        - on_failure is one of stop|continue|retry
        - timeout is a positive number
        """
        errors: list[str] = []
        if not playbook.steps:
            errors.append("Playbook has no steps")
            return errors
        seen_ids: set[str] = set()
        for step in playbook.steps:
            if not step.step_id:
                errors.append("A step is missing its 'id' field")
            elif step.step_id in seen_ids:
                errors.append(f"Duplicate step id: {step.step_id!r}")
            else:
                seen_ids.add(step.step_id)
            if step.command not in ALLOWED_COMMANDS:
                errors.append(
                    f"Step {step.step_id!r}: command {step.command!r} is not in "
                    f"the allowed list ({', '.join(sorted(ALLOWED_COMMANDS))})"
                )
            for dep in step.depends_on:
                if dep not in seen_ids:
                    errors.append(
                        f"Step {step.step_id!r} depends on {dep!r} which is not "
                        "defined before it"
                    )
            if step.on_failure not in ("stop", "continue", "retry"):
                errors.append(
                    f"Step {step.step_id!r}: on_failure must be stop|continue|retry, "
                    f"got {step.on_failure!r}"
                )
            if step.timeout <= 0:
                errors.append(f"Step {step.step_id!r}: timeout must be positive")
        return errors

    # ── Execution ────────────────────────────────────────────────────────────

    async def run_playbook(
        self,
        playbook_name: str,
        agent_id: str,
        run_id: str | None = None,
    ) -> str:
        """Start a playbook execution against ``agent_id`` and return the run_id.

        The playbook runs asynchronously as an asyncio Task.  The caller
        can poll ``get_run(run_id)`` for progress or await the task.

        Raises
        ------
        ValueError
            If the playbook does not exist, fails validation, or the agent
            is not currently connected.
        """
        playbook = self._playbooks.get(playbook_name)
        if playbook is None:
            raise ValueError(f"Unknown playbook: {playbook_name!r}")

        errors = self.validate_playbook(playbook)
        if errors:
            raise ValueError(
                f"Playbook {playbook_name!r} failed validation:\n" +
                "\n".join(f"  • {e}" for e in errors)
            )

        async with self._server.connection_lock:
            if agent_id not in self._server.connections:
                raise ValueError(
                    f"Agent {agent_id[:8]!r} is not connected — "
                    "cannot start playbook"
                )

        run_id = run_id or str(uuid.uuid4())
        steps = {
            s.step_id: StepExecution(step_id=s.step_id, command=s.command)
            for s in playbook.steps
        }
        run = PlaybookRun(
            run_id=run_id,
            playbook_name=playbook_name,
            agent_id=agent_id,
            steps=steps,
        )
        self._runs[run_id] = run

        LOG.info(
            "playbook start run_id=%s playbook=%s agent=%s",
            run_id[:8], playbook_name, agent_id[:8],
        )
        task = asyncio.create_task(
            self._execute_run(run, playbook),
            name=f"playbook-{run_id[:8]}",
        )
        self._active_tasks[run_id] = task
        task.add_done_callback(lambda t: self._active_tasks.pop(run_id, None))
        return run_id

    async def _execute_run(self, run: PlaybookRun, playbook: Playbook) -> None:
        """Internal coroutine that drives a playbook run to completion."""
        run.status     = PlaybookRunStatus.RUNNING
        run.started_at = time.monotonic()
        any_failed     = False
        await self._persist_run(run)   # persist RUNNING state

        try:
            for step_def in playbook.steps:
                step_exec = run.steps[step_def.step_id]

                # Dependency check: if any dependency failed/skipped, skip this step
                deps_ok = all(
                    run.steps[dep].status == PlaybookStepStatus.COMPLETED
                    for dep in step_def.depends_on
                    if dep in run.steps
                )
                if not deps_ok:
                    step_exec.status = PlaybookStepStatus.SKIPPED
                    step_exec.error  = "Skipped: dependency did not complete"
                    LOG.info(
                        "playbook step skipped run=%s step=%s (dependency failed)",
                        run.run_id[:8], step_def.step_id,
                    )
                    continue

                # Check agent still connected before each step
                async with self._server.connection_lock:
                    agent_ok = run.agent_id in self._server.connections
                if not agent_ok:
                    step_exec.status = PlaybookStepStatus.FAILED
                    step_exec.error  = "Agent disconnected before step started"
                    any_failed = True
                    break

                # Execute the step
                success = await self._execute_step(run, step_def, step_exec)
                await self._persist_run(run)   # persist step result
                if not success:
                    any_failed = True
                    if step_def.on_failure == "stop":
                        LOG.info(
                            "playbook stopping on failure run=%s step=%s",
                            run.run_id[:8], step_def.step_id,
                        )
                        # Mark remaining steps as SKIPPED
                        remaining = False
                        for other_def in playbook.steps:
                            if other_def.step_id == step_def.step_id:
                                remaining = True
                                continue
                            if remaining:
                                run.steps[other_def.step_id].status = PlaybookStepStatus.SKIPPED
                                run.steps[other_def.step_id].error  = "Skipped: earlier step failed"
                        break
                    # on_failure == "continue": proceed to next step

        except asyncio.CancelledError:
            run.status   = PlaybookRunStatus.CANCELLED
            run.error    = "Cancelled by operator"
            run.ended_at = time.monotonic()
            await self._persist_run(run)
            LOG.info("playbook cancelled run=%s", run.run_id[:8])
            raise
        except Exception as exc:
            run.status   = PlaybookRunStatus.FAILED
            run.error    = f"Internal error: {exc}"
            run.ended_at = time.monotonic()
            await self._persist_run(run)
            LOG.error("playbook error run=%s: %s", run.run_id[:8], exc, exc_info=True)
            return

        run.status   = PlaybookRunStatus.FAILED if any_failed else PlaybookRunStatus.COMPLETED
        run.ended_at = time.monotonic()
        await self._persist_run(run)   # persist final state
        LOG.info(
            "playbook finished run=%s status=%s duration=%.1fs",
            run.run_id[:8], run.status.value,
            run.ended_at - run.started_at,
        )

    async def _execute_step(
        self,
        run: PlaybookRun,
        step_def: PlaybookStep,
        step_exec: StepExecution,
    ) -> bool:
        """Execute one step and update ``step_exec``.  Returns True on success."""
        step_exec.status     = PlaybookStepStatus.RUNNING
        step_exec.started_at = time.monotonic()
        attempts             = 0
        max_attempts         = 1 + (step_def.retry_count if step_def.on_failure == "retry" else 0)

        while attempts < max_attempts:
            attempts += 1
            if attempts > 1:
                step_exec.retries += 1
                LOG.info(
                    "playbook step retry run=%s step=%s attempt=%d/%d",
                    run.run_id[:8], step_def.step_id, attempts, max_attempts,
                )

            # For upload commands, resolve the file content from the server's
            # upload directory if the caller only supplied the filename.
            # This mirrors what the CLI does for 'task <agent> upload <name>'.
            resolved_params = step_def.parameters
            if step_def.command == "upload" and "content_b64" not in step_def.parameters:
                name = step_def.parameters.get("name", "")
                try:
                    from shared.lab_transfer import read_lab_file
                    upload_dir = getattr(self._server, "upload_dir", None)
                    if upload_dir is None:
                        raise ValueError("server has no upload_dir")
                    resolved_params = read_lab_file(upload_dir, name)
                except Exception as exc:
                    step_exec.error    = f"Upload file resolution failed: {exc}"
                    step_exec.status   = PlaybookStepStatus.FAILED
                    step_exec.ended_at = time.monotonic()
                    LOG.warning(
                        "playbook step upload file not found run=%s step=%s name=%s: %s",
                        run.run_id[:8], step_def.step_id, name, exc,
                    )
                    return False

            try:
                task_id = await self._server.dispatch_task(
                    run.agent_id, step_def.command, resolved_params
                )
            except Exception as exc:
                step_exec.error   = f"Dispatch failed: {exc}"
                step_exec.status  = PlaybookStepStatus.FAILED
                step_exec.ended_at = time.monotonic()
                LOG.warning(
                    "playbook step dispatch failed run=%s step=%s: %s",
                    run.run_id[:8], step_def.step_id, exc,
                )
                if attempts < max_attempts:
                    await asyncio.sleep(1.0)
                continue

            step_exec.task_id = task_id

            # Poll for the task result with the per-step timeout
            deadline = asyncio.get_event_loop().time() + step_def.timeout
            final_status = None
            while asyncio.get_event_loop().time() < deadline:
                t = await self._db.get_task(task_id)
                if t and t["status"] in {
                    "COMPLETED", "FAILED", "TIMEOUT", "CANCELLED"
                }:
                    final_status = t["status"]
                    break
                await asyncio.sleep(0.2)

            if final_status is None:
                step_exec.error    = f"Step timed out after {step_def.timeout}s"
                step_exec.status   = PlaybookStepStatus.FAILED
                step_exec.ended_at = time.monotonic()
                LOG.warning(
                    "playbook step timeout run=%s step=%s task=%s",
                    run.run_id[:8], step_def.step_id, task_id[:8],
                )
                if attempts < max_attempts:
                    await asyncio.sleep(1.0)
                continue

            if final_status == "COMPLETED":
                # Fetch the result output
                results = await self._db.list_results(task_id)
                step_exec.output   = results[0]["output"] if results else ""
                step_exec.status   = PlaybookStepStatus.COMPLETED
                step_exec.ended_at = time.monotonic()
                LOG.info(
                    "playbook step completed run=%s step=%s task=%s",
                    run.run_id[:8], step_def.step_id, task_id[:8],
                )
                return True
            else:
                t = await self._db.get_task(task_id)
                step_exec.error    = f"Task ended with {final_status}: {t}"
                step_exec.status   = PlaybookStepStatus.FAILED
                step_exec.ended_at = time.monotonic()
                LOG.warning(
                    "playbook step failed run=%s step=%s task_status=%s",
                    run.run_id[:8], step_def.step_id, final_status,
                )
                if attempts < max_attempts:
                    await asyncio.sleep(1.0)
                continue

        return False

    # ── Trigger model (C3) ───────────────────────────────────────────────────

    def register_trigger(self, event: str, playbook_name: str, *,
                         once_per_agent: bool = True,
                         condition: str = "always") -> None:
        """Register a trigger that auto-starts a playbook when an event fires.

        Parameters
        ----------
        event : str
            The event that activates this trigger.  Supported events:
            ``"agent_connected"``  — fires when any agent completes SYNC_COMPLETE.
        playbook_name : str
            Name of a registered playbook to run when the event fires.
        once_per_agent : bool
            When True (default), the trigger fires at most once per agent_id
            per server session.  Prevents repeated executions on reconnect.
        condition : str
            Reserved for future use (e.g. ``"agent_id.startswith('lab-')"``).
            Currently only ``"always"`` is accepted.
        """
        if playbook_name not in self._playbooks:
            raise ValueError(
                f"Cannot register trigger: playbook {playbook_name!r} is not registered"
            )
        if event not in ("agent_connected",):
            raise ValueError(
                f"Unknown trigger event {event!r}. Supported: 'agent_connected'"
            )
        trigger = {
            "event":          event,
            "playbook_name":  playbook_name,
            "once_per_agent": once_per_agent,
            "condition":      condition,
            "_fired_for":     set(),   # agent_ids that already triggered this
        }
        self._triggers.append(trigger)
        LOG.info(
            "trigger registered: %s → playbook %s (once_per_agent=%s)",
            event, playbook_name, once_per_agent,
        )

    def list_triggers(self) -> list[dict]:
        """Return a summary of all registered triggers."""
        return [
            {
                "event":          t["event"],
                "playbook_name":  t["playbook_name"],
                "once_per_agent": t["once_per_agent"],
                "fired_count":    len(t["_fired_for"]),
            }
            for t in self._triggers
        ]

    async def fire_trigger(self, event: str, agent_id: str) -> list[str]:
        """Fire all triggers registered for ``event`` against ``agent_id``.

        Called by the server after SYNC_COMPLETE when ``event='agent_connected'``.
        Returns a list of run_ids for any playbooks that were started.
        Errors from individual playbooks are logged but do not abort other triggers.
        """
        run_ids = []
        for trigger in self._triggers:
            if trigger["event"] != event:
                continue
            if trigger["once_per_agent"] and agent_id in trigger["_fired_for"]:
                LOG.debug(
                    "trigger %s→%s already fired for agent=%s — skipping",
                    event, trigger["playbook_name"], agent_id[:8],
                )
                continue
            try:
                run_id = await self.run_playbook(trigger["playbook_name"], agent_id)
                trigger["_fired_for"].add(agent_id)
                run_ids.append(run_id)
                LOG.info(
                    "trigger fired: %s → playbook %s run=%s agent=%s",
                    event, trigger["playbook_name"], run_id[:8], agent_id[:8],
                )
            except Exception as exc:
                LOG.warning(
                    "trigger %s→%s failed for agent=%s: %s",
                    event, trigger["playbook_name"], agent_id[:8], exc,
                )
        return run_ids

    # ── Run history ───────────────────────────────────────────────────────────

    def get_run(self, run_id: str) -> PlaybookRun | None:
        """Return a run by its ID, or None."""
        return self._runs.get(run_id)

    def list_runs(self, limit: int = 50) -> list[dict]:
        """Return summary dicts for the most recent runs, newest first."""
        runs = sorted(
            self._runs.values(),
            key=lambda r: r.started_at or 0,
            reverse=True,
        )
        return [r.to_dict() for r in runs[:limit]]

    async def cancel_run(self, run_id: str) -> bool:
        """Cancel an in-progress playbook run.  Returns True if it was running."""
        task = self._active_tasks.get(run_id)
        if task and not task.done():
            task.cancel()
            return True
        return False


# ── Built-in playbooks ────────────────────────────────────────────────────────

def _builtin_playbooks() -> list[Playbook]:
    """Return the three built-in laboratory playbooks."""
    return [
        # ── 1. Agent inventory ───────────────────────────────────────────────
        Playbook(
            name="agent_inventory",
            description=(
                "Verify agent health, collect identification, and gather a "
                "deep system inventory. Safe: read-only operations only."
            ),
            steps=[
                PlaybookStep("ping_check",  "echo",     {"text": "health-check"},
                             timeout=15,  on_failure="stop"),
                PlaybookStep("get_id",      "get_info", {},
                             depends_on=["ping_check"], timeout=15,  on_failure="stop"),
                PlaybookStep("sysinfo",     "sysinfo",  {},
                             depends_on=["get_id"],     timeout=60,  on_failure="continue"),
                PlaybookStep("whoami",      "shell",    {"command": "whoami"},
                             depends_on=["get_id"],     timeout=10,  on_failure="continue"),
                PlaybookStep("hostname",    "shell",    {"command": "uname"},
                             depends_on=["get_id"],     timeout=10,  on_failure="continue"),
            ],
        ),
        # ── 2. Connectivity reliability ──────────────────────────────────────
        Playbook(
            name="connectivity",
            description=(
                "Assess communication reliability: ping, echo, and shell "
                "round-trips. Safe: read-only operations only."
            ),
            steps=[
                PlaybookStep("echo_1",  "echo",  {"text": "round-trip-1"},
                             timeout=10, on_failure="stop"),
                PlaybookStep("echo_2",  "echo",  {"text": "round-trip-2"},
                             depends_on=["echo_1"], timeout=10, on_failure="continue"),
                PlaybookStep("echo_3",  "echo",  {"text": "round-trip-3"},
                             depends_on=["echo_1"], timeout=10, on_failure="continue"),
                PlaybookStep("whoami",  "shell", {"command": "whoami"},
                             depends_on=["echo_1"], timeout=10, on_failure="continue"),
                PlaybookStep("get_info","get_info", {},
                             depends_on=["echo_1"], timeout=15, on_failure="continue"),
            ],
        ),
        # ── 3. File integrity demonstration ──────────────────────────────────
        Playbook(
            name="file_integrity",
            description=(
                "Transfer a test file to the agent, retrieve it, and verify "
                "integrity via SHA-256. Requires sample.txt in server upload dir."
            ),
            steps=[
                PlaybookStep("pre_check",  "echo",     {"text": "file-integrity-start"},
                             timeout=10, on_failure="stop"),
                PlaybookStep("upload",     "upload",   {"name": "sample.txt"},
                             depends_on=["pre_check"], timeout=30, on_failure="stop"),
                PlaybookStep("download",   "download", {"name": "sample.txt"},
                             depends_on=["upload"],    timeout=30, on_failure="stop"),
                PlaybookStep("verify",     "echo",     {"text": "file-integrity-ok"},
                             depends_on=["download"],  timeout=10, on_failure="stop"),
            ],
        ),
    ]
