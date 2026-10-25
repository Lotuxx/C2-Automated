"""
server/main.py — Asynchronous TLS C2 server for the lab MVP.

Role in the architecture
------------------------
This is the central coordinator of the project.  It performs three
independent but concurrent responsibilities:

1. Network layer (handle_client / _tracked_handle_client)
   Accepts TLS connections from agents.  One coroutine per connected agent
   runs a ``while True`` message-dispatch loop, routing each incoming message
   type to the appropriate handler logic and writing replies.

2. Persistence layer delegation
   Every meaningful event (agent registration, task status change, result
   receipt) is immediately persisted by calling the Database methods in
   server/storage/database.py.  No state is held only in memory.

3. Operator CLI (cli)
   An interactive command-line loop runs as a parallel asyncio Task.
   The operator types commands to list agents, dispatch tasks, and inspect
   results.  When the operator types ``quit``, the CLI task exits, triggering
   a clean shutdown of the server and all agent connections.

Communication protocol
----------------------
All messages use the JSON-lines framing defined in shared/protocol.py.
TLS 1.2+ is mandatory; self-signed certificates are supported for the lab
(agent uses the server cert as its CA trust anchor).

Startup
-------
    python -m server.main [--host H] [--port P] [--cert C] [--key K]
                          [--db D] [--log-file F]

    Defaults: 127.0.0.1:9443, certs/server.crt / certs/server.key,
              data/c2.sqlite3, logs to stderr.

Message flow (normal task lifecycle)
-------------------------------------
    operator      server                                agent
    ─────────     ──────                                ─────
    task echo hi  dispatch_task()
                  INSERT tasks (PENDING)
                  write TASK ──────────────────────────► recv TASK
                  UPDATE tasks (WAITING_ACK)               write TASK_ACK
                  recv TASK_ACK ◄──────────────────────
                  UPDATE tasks (QUEUED)                    write TASK_STATUS RUNNING
                  recv TASK_STATUS ◄───────────────────
                  UPDATE tasks (RUNNING)                   execute_allowed()
                                                           write RESULT COMPLETED
                  recv RESULT ◄────────────────────────
                  complete_task_with_result()
                    UPDATE tasks (COMPLETED)
                    INSERT results
    result abc123 list_results()
                  print output
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import ssl
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

try:
    import rich as _rich_check  # noqa: F401 — availability check only
except ImportError as _rich_missing:  # pragma: no cover
    raise SystemExit(
        "The 'rich' library is required for the server CLI.\n"
        "Install it with:  pip install rich\n"
        "Or:               pip install -r requirements.txt"
    ) from _rich_missing

from server.storage.database import Database, TaskNotFoundError
from server.task_manager import InvalidTaskTransition
from shared.protocol import make_message, read_message, write_message, ProtocolError
from shared.lab_transfer import read_lab_file, write_lab_file, validate_name
from shared.mtls import build_server_context, extract_agent_id_from_cert

# Module-level logger; the root logger is configured in run().
LOG = logging.getLogger("c2")

# Maximum number of protocol messages accepted from one connection within a
# single one-second window.  Legitimate agents send a handful of messages per
# second (REGISTER, SYNC_STATE, BEACON every 30 s, occasional TASK_ACK/RESULT).
# 60 per second is generous enough for any real workload while stopping a flood.
MAX_MESSAGES_PER_SECOND = 60

# Default wall-clock deadline for a dispatched task, in seconds.
# If no RESULT arrives within this window the server marks the task TIMEOUT and
# removes the per-task tracking coroutine.  The agent continues running; the
# operator may use `ping` to verify liveness and re-dispatch if needed.
# This default can be overridden per dispatch_task() call or via --task-timeout.
DEFAULT_TASK_TIMEOUT = 60.0


# ── Logging helper ────────────────────────────────────────────────────────────

class _PromptAwareHandler(logging.StreamHandler):
    """A logging handler that keeps the interactive ``c2>`` prompt readable.

    Problem
    -------
    The CLI loop prints ``c2> `` (no newline) and then blocks in
    ``asyncio.to_thread(input, ...)`` waiting for the operator to type.
    Meanwhile the event loop keeps running and server handlers may call
    LOG.info().  The standard StreamHandler writes the log line directly to
    stderr, which is the same terminal, inserting text after the half-printed
    prompt and making output unreadable.

    Solution
    --------
    Before emitting each log record, write ``\\r\\033[K`` to the terminal.
    ``\\r`` moves the cursor to column 0 without advancing the line.
    ``\\033[K`` (ANSI "Erase to End of Line") clears everything from the
    cursor to the right margin, including the ``c2> `` fragment.  The log
    line is then written on a clean line.  Afterwards, ``c2> `` is reprinted
    so the operator's partial input is visible again.

    This technique requires no locks or thread synchronisation because the
    Python GIL ensures that the write sequence is not interrupted by another
    Python thread between the ``\\r\\033[K`` and the prompt redraw.

    Fallback
    --------
    When the stream is not a TTY (redirected to a file, piped, or running in
    CI), ``isatty()`` returns False and the handler behaves identically to a
    plain StreamHandler — no escape codes, no prompt redraw.
    """

    PROMPT = "c2> "

    def emit(self, record: logging.LogRecord) -> None:
        """Write one log record to the stream, with prompt management.

        Parameters
        ----------
        record : logging.LogRecord
            The log record produced by a LOG.info() / LOG.warning() call.
        """
        try:
            stream = self.stream
            if getattr(stream, "isatty", lambda: False)():
                # Erase the partial "c2> " fragment before writing the log line.
                stream.write("\r\033[K")
            super().emit(record)
            if getattr(stream, "isatty", lambda: False)():
                # Redraw the prompt so the operator sees where to type.
                stream.write(self.PROMPT)
                stream.flush()
        except Exception:
            self.handleError(record)


# ── Server class ──────────────────────────────────────────────────────────────

class C2Server:
    """Asynchronous TLS C2 server with an interactive operator CLI.

    One instance is created per ``run()`` invocation and shared between the
    listening socket, all agent connection handlers, and the CLI loop.

    Attributes
    ----------
    db : Database
        Shared database instance used by all coroutines.
    connections : dict[str, asyncio.StreamWriter]
        Maps full agent UUID → the StreamWriter for that agent's active TLS
        connection.  Updated under ``connection_lock`` to avoid race conditions
        between the REGISTER handler and the disconnect cleanup.
    _handler_tasks : set[asyncio.Task]
        Set of asyncio Tasks currently running ``handle_client``.  Used by
        ``shutdown()`` to cancel all in-flight handlers when the operator quits.
    connection_lock : asyncio.Lock
        Guards reads and writes to ``connections`` to prevent concurrent
        modification between the message loop and the shutdown path.
    """

    def __init__(self, db: Database, *, upload_dir="data/server_files",
                 download_dir="data/server_downloads",
                 task_timeout: float = DEFAULT_TASK_TIMEOUT,
                 mtls_enabled: bool = False):
        """Initialise the C2 server with its database and configuration.

        Parameters
        ----------
        db : Database
            Shared persistence layer; must be already initialised.
        upload_dir : str or Path
            Server-side directory of pre-approved files to push to agents.
        download_dir : str or Path
            Server-side destination for files retrieved from agents.
        task_timeout : float
            Wall-clock deadline in seconds for each dispatched task.
            Tasks that produce no RESULT within this window are marked TIMEOUT.
        mtls_enabled : bool
            When True, agent identity is taken from the TLS client certificate
            CN rather than the self-declared REGISTER payload.
        """
        self.db = db
        self.upload_dir = Path(upload_dir)
        self.download_dir = Path(download_dir)
        # When True, the server requires a client certificate on every connection
        # and derives the authoritative agent_id from the certificate's CN field.
        # The self-declared agent_id in the REGISTER payload is ignored.
        self.mtls_enabled = mtls_enabled
        # Wall-clock deadline for each dispatched task (seconds).
        # When a task has been in a non-terminal state for longer than this,
        # the server marks it TIMEOUT and stops tracking it.
        self.task_timeout = task_timeout
        # Full UUID → StreamWriter for every currently-connected agent.
        self.connections: dict[str, asyncio.StreamWriter] = {}
        # asyncio Tasks running handle_client, tracked for clean shutdown.
        self._handler_tasks: set[asyncio.Task] = set()
        # task_id → asyncio.Task running the per-task timeout watchdog.
        # Entries are removed when the task reaches a terminal state (via
        # _cancel_task_watchdog) or when the watchdog fires on its own.
        self._active_task_timeouts: dict[str, asyncio.Task] = {}
        # Protects self.connections from concurrent read/write access.
        self.connection_lock = asyncio.Lock()
        # While a newly registered TLS session synchronizes, refuse task dispatch.
        # Keys are agent IDs; fake test connections inserted directly stay usable.
        self.pending_sync: set[str] = set()
        # Correlate explicit liveness checks to the response on the same TLS session.
        self.pending_pings: dict[str, tuple[str, asyncio.StreamWriter, asyncio.Future]] = {}
        self.recovery_lock = asyncio.Lock()  # prevent duplicate retry dispatch in one server
        # Injected by tests to capture CLI output; None means cli() creates its own Console.
        self._test_console = None

    # ── Task timeout watchdog ─────────────────────────────────────────────────

    def _start_task_watchdog(self, task_id: str) -> None:
        """Schedule a coroutine that marks a task TIMEOUT if it does not complete in time.

        Called immediately after dispatch_task() writes the TASK message.  A
        separate asyncio Task sleeps for ``self.task_timeout`` seconds and then
        transitions the task to TIMEOUT if it is still in a non-terminal state.

        The watchdog is cancelled (via _cancel_task_watchdog) as soon as the
        server receives a terminal RESULT for the task, so normal completions
        carry zero overhead beyond the Task creation cost.

        If the watchdog fires it:
        1. Transitions the task to TIMEOUT via ``update_task_status``.
        2. Records an interruption entry in ``task_interruptions``.
        3. Removes itself from ``_active_task_timeouts``.
        The agent is NOT disconnected; the session remains usable for future tasks.
        """
        async def _watchdog(tid: str) -> None:
            """Sleep for the task deadline; mark TIMEOUT if the task is still running.

            Cancelled immediately when _cancel_task_watchdog() is called,
            which happens as soon as a RESULT arrives for this task.
            """
            try:
                await asyncio.sleep(self.task_timeout)
                # Sleep elapsed — the task has not reached a terminal state yet.
                # Use interrupt_task() which atomically records the pre-TIMEOUT
                # state and advances the task in one transaction.  If the task
                # completed between the sleep and here, interrupt_task returns
                # False (already terminal) and we skip the log.
                try:
                    # timeout_task transitions to TIMEOUT and records the interruption
                    # in one atomic transaction.  Returns False if the task already
                    # reached a terminal state (normal completion raced the watchdog).
                    advanced = await self.db.timeout_task(tid)
                    if advanced:
                        LOG.warning(
                            "task_timeout: task_id=%s exceeded %.1fs deadline — marked TIMEOUT",
                            tid, self.task_timeout,
                        )
                    else:
                        LOG.debug(
                            "task_timeout watchdog: task_id=%s already terminal — skipped",
                            tid,
                        )
                except Exception as exc:
                    LOG.debug("task_timeout watchdog error: %s for task_id=%s", exc, tid)
            except asyncio.CancelledError:
                # Normal path: RESULT arrived before the deadline.
                pass
            finally:
                self._active_task_timeouts.pop(tid, None)

        wdog = asyncio.create_task(_watchdog(task_id))
        self._active_task_timeouts[task_id] = wdog

    def _cancel_task_watchdog(self, task_id: str) -> None:
        """Cancel the timeout watchdog for a task that has reached a terminal state.

        Called from the RESULT handler (and from disconnect cleanup) so that
        tasks which complete normally or fail cleanly do not also get marked
        TIMEOUT after their natural conclusion.
        """
        wdog = self._active_task_timeouts.pop(task_id, None)
        if wdog is not None and not wdog.done():
            wdog.cancel()

    # ── Connection tracking ───────────────────────────────────────────────────

    async def _tracked_handle_client(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        """Entry point passed to asyncio.start_server; wraps handle_client.

        Registers the current asyncio Task in ``_handler_tasks`` before
        delegating to ``handle_client``, and removes it on exit.  This
        tracking is what allows ``shutdown()`` to cancel all live connections.

        Parameters
        ----------
        reader, writer
            Standard asyncio stream pair for the new TLS connection.
        """
        task = asyncio.current_task()
        if task:
            self._handler_tasks.add(task)
        try:
            await self.handle_client(reader, writer)
        finally:
            if task:
                self._handler_tasks.discard(task)

    async def shutdown(self) -> None:
        """Gracefully close all agent connections and wait for handlers to finish.

        Called by ``run()`` after the CLI loop exits (operator typed ``quit``).
        The sequence is:

        1. Close every StreamWriter in ``connections`` — this sends a TCP FIN
           to the agent, which causes its ``read_message`` to raise
           IncompleteReadError and exit cleanly.
        2. Cancel every running handler Task — handles the case where a
           handler is blocked waiting for a new message from an agent whose
           writer was just closed (the OS may not deliver the FIN immediately).
        3. ``asyncio.gather`` waits for all tasks to finish their ``finally``
           blocks (which persist disconnect state to the database).
        """
        # Step 1: close all writers to signal agents that the server is shutting down.
        async with self.connection_lock:
            writers = list(self.connections.values())
        for w in writers:
            try:
                w.close()
            except Exception:
                pass  # ignore errors on already-closed writers

        # Step 2: cancel handlers that may still be blocked on read_message.
        for task in list(self._handler_tasks):
            task.cancel()

        # Step 3: wait for all handlers to run their finally blocks.
        if self._handler_tasks:
            await asyncio.gather(*self._handler_tasks, return_exceptions=True)

    # ── Connection handler ────────────────────────────────────────────────────

    async def handle_client(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        """Handle the entire lifecycle of one agent's TLS connection.

        This coroutine is the core of the server.  It runs a ``while True``
        loop that reads messages one at a time and dispatches them by type.
        The loop exits on clean disconnect (IncompleteReadError), cancellation
        (CancelledError from shutdown), or an unrecoverable error.

        Session state machine (internal to this method)
        ------------------------------------------------
        Connection accepted → create_session(CONNECTED)
            REGISTER received → upsert_agent, set agent_id local variable
                message loop begins; REGISTER required before any other message
                PING / BEACON / TASK_ACK / TASK_STATUS / RESULT / SYNC_STATE ...
            connection ends (any reason) → disconnect cleanup, close_session

        Error handling
        --------------
        IncompleteReadError / ConnectionError
            Normal disconnect.  Suppressed silently; cleanup still runs.
        CancelledError
            Triggered by shutdown().  Treated as normal disconnect.
        ProtocolError
            Malformed message from the agent.  Logged as WARNING; connection
            is closed (the agent is misbehaving at the protocol level).
        Exception (catch-all)
            Unexpected server-side bug.  Logged as ERROR with full traceback.

        Parameters
        ----------
        reader : asyncio.StreamReader
            Incoming data stream from the TLS-wrapped TCP connection.
        writer : asyncio.StreamWriter
            Outgoing data stream to the agent.
        """
        session_id = str(uuid.uuid4())
        agent_id = None  # set after a valid REGISTER message is received
        peer = writer.get_extra_info("peername")
        LOG.info("connection opened peer=%s session=%s", peer, session_id)

        # ── mTLS: extract the authoritative agent_id from the client certificate ──
        # When mTLS is enabled the TLS handshake has already verified that the
        # peer holds the private key for a certificate signed by the agent CA.
        # We read the CN field now and will enforce it against the REGISTER payload
        # so that a misbehaving client cannot claim a different agent identity.
        cert_agent_id: str | None = None
        if self.mtls_enabled:
            try:
                cert_agent_id = extract_agent_id_from_cert(writer)
                if cert_agent_id is None:
                    # The TLS layer required a cert (CERT_REQUIRED is set) so this
                    # should not happen, but be defensive.
                    raise ValueError("no client certificate presented")
                LOG.info("mTLS: peer=%s identified by cert CN=%s", peer, cert_agent_id)
            except ValueError as exc:
                LOG.warning("mTLS: rejected peer=%s — %s", peer, exc)
                return  # triggers finally; no session record written yet

        try:
            # Record the session immediately so even un-REGISTERED connections
            # are visible in the sessions table for audit purposes.
            await self.db.create_session(session_id, None, "CONNECTED")

            # Per-connection rate limiter: count messages received within each
            # one-second window.  Using asyncio.get_event_loop().time() (monotonic)
            # keeps this independent of system-clock adjustments.
            _rate_window_start: float = asyncio.get_event_loop().time()
            _rate_count: int = 0

            while True:
                msg = await read_message(reader)
                mtype = msg["type"]

                # ── Rate limiting ──────────────────────────────────────────────
                now_t = asyncio.get_event_loop().time()
                if now_t - _rate_window_start >= 1.0:
                    # Start a fresh one-second window
                    _rate_window_start = now_t
                    _rate_count = 0
                _rate_count += 1
                if _rate_count > MAX_MESSAGES_PER_SECOND:
                    LOG.warning(
                        "rate limit exceeded peer=%s session=%s (%d msgs/s) — closing",
                        peer, session_id, _rate_count,
                    )
                    try:
                        await write_message(writer, make_message(
                            "ERROR",
                            agent_id=agent_id,
                            session_id=session_id,
                            payload={"error": "rate limit exceeded — connection closed"},
                        ))
                    except Exception:
                        pass
                    return  # triggers the finally block cleanly

                # ── REGISTER ──────────────────────────────────────────────────
                if mtype == "REGISTER":
                    # An already-registered connection must not be allowed to
                    # change its identity mid-session.  Permitting a second
                    # REGISTER would let a client claim a different agent_id,
                    # displace the legitimate agent from self.connections, place
                    # the session back into pending_sync, and block all task
                    # dispatch to the original agent.  Reject and keep looping
                    # so the legitimate client is not dropped.
                    if agent_id is not None:
                        LOG.warning(
                            "re-registration attempt ignored agent=%s session=%s",
                            agent_id, session_id,
                        )
                        await write_message(writer, make_message(
                            "ERROR", agent_id=agent_id, session_id=session_id,
                            payload={"error": "already registered on this session"},
                        ))
                        continue
                    payload = msg["payload"]
                    claimed_id = payload.get("agent_id")
                    # Reject malformed or oversized agent IDs to avoid
                    # polluting the database with garbage primary keys.
                    if not isinstance(claimed_id, str) or not claimed_id or len(claimed_id) > 128:
                        await write_message(writer, make_message("ERROR",
                                            payload={"error": "invalid agent_id"}))
                        continue
                    # mTLS: when a client certificate is present, its CN is the
                    # authoritative identity.  Reject mismatches so that a client
                    # cannot forge a different agent_id even if it holds a valid cert.
                    if cert_agent_id is not None and claimed_id != cert_agent_id:
                        LOG.warning(
                            "mTLS: REGISTER agent_id=%s does not match cert CN=%s — rejected peer=%s",
                            claimed_id, cert_agent_id, peer,
                        )
                        await write_message(writer, make_message("ERROR",
                                            payload={
                                                "error": (
                                                    f"agent_id {claimed_id!r} does not match "
                                                    f"certificate CN {cert_agent_id!r}"
                                                )
                                            }))
                        continue
                    agent_id = claimed_id
                    # Upsert the agent record (creates on first connect, updates
                    # hostname/platform/last_seen on reconnect).
                    await self.db.upsert_agent(
                        agent_id,
                        payload.get("hostname", "unknown"),
                        payload.get("platform", "unknown"),
                    )
                    await self.db.set_session_agent(session_id, agent_id)
                    async with self.connection_lock:
                        # Replace any stale writer from a previous session with
                        # the same agent_id.  The old writer is closed below so
                        # the previous session terminates cleanly.
                        old = self.connections.get(agent_id)
                        self.connections[agent_id] = writer
                        self.pending_sync.add(agent_id)
                    if old and old is not writer:
                        old.close()
                    await write_message(writer, make_message(
                        "REGISTER_ACK", agent_id=agent_id, session_id=session_id,
                        payload={"registered": True, "session_id": session_id},
                    ))
                    LOG.info("registered agent=%s session=%s", agent_id, session_id)

                # ── Pre-registration guard ────────────────────────────────────
                elif not agent_id:
                    # All message types other than REGISTER require a registered
                    # agent_id.  Reject with ERROR and continue the loop so the
                    # agent has a chance to send REGISTER.
                    await write_message(writer, make_message("ERROR",
                                        payload={"error": "REGISTER required"}))

                # ── PING ──────────────────────────────────────────────────────
                elif mtype == "PING":
                    # Liveness probe; reply with PONG and the message_id of the
                    # PING so the agent can correlate request and response.
                    await write_message(writer, make_message(
                        "PONG", agent_id=agent_id, session_id=session_id,
                        payload={"reply_to": msg["message_id"]},
                    ))

                # ── PONG ──────────────────────────────────────────────────────
                elif mtype == "PONG":
                    reply_to = msg["payload"].get("reply_to")
                    entry = self.pending_pings.get(reply_to)
                    if entry and entry[0] == agent_id and entry[1] is writer:
                        if not entry[2].done():
                            entry[2].set_result(True)
                    else:
                        LOG.warning("unmatched PONG from agent=%s", agent_id)

                # ── BEACON ────────────────────────────────────────────────────
                elif mtype == "BEACON":
                    # Periodic heartbeat from the agent.  Refresh last_seen so
                    # the operator can tell whether the agent is still alive.
                    await self.db.touch_agent(agent_id)
                    await write_message(writer, make_message(
                        "BEACON_ACK", agent_id=agent_id, session_id=session_id,
                        payload={},
                    ))

                # ── TASK_ACK ─────────────────────────────────────────────────
                elif mtype == "TASK_ACK":
                    # The agent has received the TASK message and is about to
                    # queue it for execution.  Transition: WAITING_ACK → QUEUED.
                    task_id = msg["payload"].get("task_id")
                    if task_id:
                        task = await self.db.get_task(task_id)
                        if task is None or task["agent_id"] != agent_id:
                            LOG.warning("TASK_ACK for unknown/foreign task=%s", task_id)
                            continue
                        try:
                            await self.db.update_task_status(task_id, "QUEUED")
                        except TaskNotFoundError:
                            # Unknown task_id — log and continue; do not kill the session.
                            LOG.warning("TASK_ACK for unknown task task_id=%s agent=%s",
                                        task_id, agent_id)
                        except InvalidTaskTransition as exc:
                            # Duplicate ACK or out-of-order message — ignore.
                            LOG.warning("TASK_ACK rejected task_id=%s agent=%s: %s",
                                        task_id, agent_id, exc)

                # ── TASK_STATUS ───────────────────────────────────────────────
                elif mtype == "TASK_STATUS":
                    task_id = msg["payload"].get("task_id")
                    status  = msg["payload"].get("status")
                    # The agent should only send RUNNING here (COMPLETED and
                    # FAILED arrive via RESULT), but COMPLETED and FAILED are
                    # also accepted to be tolerant of future agent versions.
                    if task_id and status in {"RUNNING"}:
                        task = await self.db.get_task(task_id)
                        if task is None or task["agent_id"] != agent_id:
                            LOG.warning("TASK_STATUS for unknown/foreign task=%s", task_id)
                            continue
                        try:
                            await self.db.update_task_status(task_id, status)
                        except TaskNotFoundError:
                            LOG.warning("TASK_STATUS for unknown task task_id=%s agent=%s",
                                        task_id, agent_id)
                        except InvalidTaskTransition as exc:
                            # Duplicate status update — log and continue.
                            LOG.warning("TASK_STATUS rejected task_id=%s status=%s agent=%s: %s",
                                        task_id, status, agent_id, exc)

                # ── RESULT ────────────────────────────────────────────────────
                elif mtype == "RESULT":
                    p = msg["payload"]
                    task_id = p.get("task_id")
                    if not task_id:
                        LOG.warning("RESULT without task_id rejected agent=%s", agent_id)
                        continue
                    task = await self.db.get_task(task_id)
                    # Never let one agent close another agent's task.
                    if task is None or task["agent_id"] != agent_id:
                        LOG.warning("RESULT for unknown/foreign task=%s agent=%s", task_id, agent_id)
                        continue
                    result_status = p.get("status", "COMPLETED")
                    result_id = p.get("result_id", str(uuid.uuid4()))
                    output = p.get("output", "")
                    downloaded = None
                    if task["command"] == "upload" and result_status == "COMPLETED":
                        try:
                            import json as _json
                            confirmation = _json.loads(output)
                            original = _json.loads(task["parameters_json"])
                            if (confirmation.get("operation") != "upload" or
                                    any(confirmation.get(field) != original.get(field)
                                        for field in ("name", "sha256", "bytes"))):
                                raise ValueError("agent receipt differs from sent file")
                        except (ValueError, TypeError, AttributeError) as exc:
                            result_status = "FAILED"
                            output = f"upload confirmation rejected: {exc}"
                    if task["command"] == "download" and result_status == "COMPLETED":
                        try:
                            import json as _json
                            data = _json.loads(output)
                            parameters = _json.loads(task["parameters_json"])
                            if data.get("name") != parameters.get("name"):
                                raise ValueError("returned filename does not match task")
                            downloaded = write_lab_file(self.download_dir, data)
                            output = _json.dumps({"operation": "download", **downloaded})
                        except (ValueError, TypeError, OSError) as exc:
                            result_status = "FAILED"
                            output = f"download rejected: {exc}"
                    try:
                        await self.db.complete_task_with_result(
                            task_id, result_status, result_id, agent_id, output,
                        )
                        # Task reached a terminal state — cancel the timeout watchdog
                        # so it does not also mark this task TIMEOUT after the fact.
                        self._cancel_task_watchdog(task_id)
                        LOG.info("result received task=%s status=%s", task_id, result_status)
                    except (TaskNotFoundError, InvalidTaskTransition) as exc:
                        LOG.warning("RESULT rejected task_id=%s status=%s agent=%s: %s",
                                    task_id, result_status, agent_id, exc)
                        # Avoid retaining a file for a rejected/duplicate result.
                        if downloaded is not None:
                            (self.download_dir / downloaded["name"]).unlink(missing_ok=True)

                # ── SYNC_STATE ────────────────────────────────────────────────
                elif mtype == "SYNC_STATE":
                    p = msg["payload"]
                    # Log what the agent reported so the operator can see whether
                    # the agent believes there are pending tasks from before a disconnect.
                    LOG.info(
                        "sync_state agent=%s pending_tasks=%s pending_results=%s",
                        agent_id,
                        p.get("pending_task_ids"),
                        p.get("pending_result_ids"),
                    )
                    # Reconciliation: the agent does not retain task state between
                    # sessions.  Any task that was WAITING_ACK or QUEUED when the
                    # agent last disconnected will never be executed, so we cancel
                    # them here to move them to a clean terminal state.
                    # The operator is expected to re-dispatch them from the CLI.
                    stuck = await self.db.get_stuck_tasks(agent_id)
                    for t in stuck:
                        try:
                            await self.db.interrupt_task(t["task_id"], "sync_reconnect")
                            LOG.warning(
                                "reconcile: cancelled stuck task task_id=%s"
                                " (was %s) — re-dispatch manually if needed",
                                t["task_id"], t["status"],
                            )
                        except (TaskNotFoundError, InvalidTaskTransition) as exc:
                            LOG.warning(
                                "reconcile: could not cancel task_id=%s: %s",
                                t["task_id"], exc,
                            )
                    # Acknowledge the sync and signal the session is ready.
                    await write_message(writer, make_message(
                        "SYNC_STATE_RESPONSE", agent_id=agent_id, session_id=session_id,
                        payload={"accepted": True},
                    ))
                    await write_message(writer, make_message(
                        "SYNC_COMPLETE", agent_id=agent_id, session_id=session_id,
                        payload={},
                    ))
                    async with self.connection_lock:
                        if self.connections.get(agent_id) is writer:
                            self.pending_sync.discard(agent_id)
                            await self.db.mark_session_active(session_id)

                    # ── Automatic replay of safe read-only tasks ───────────────
                    # After synchronization is complete, re-dispatch any read-only
                    # tasks (echo, get_info, restricted shell) that were interrupted
                    # with UNKNOWN_OUTCOME and have not yet been manually retried.
                    # File transfers and lifecycle commands are NEVER auto-replayed
                    # because they may have completed before the connection dropped.
                    #
                    # Race protection: reserve_replay() atomically claims the retry
                    # slot before dispatch so two concurrent SYNC_STATE events (e.g.
                    # two rapid reconnects) cannot both dispatch the same replacement.
                    replayable = await self.db.get_auto_replayable_interruptions(agent_id)
                    for interrupted in replayable:
                        orig_id = interrupted["task_id"]
                        placeholder = f"__pending_{uuid.uuid4().hex}"
                        claimed = await self.db.reserve_replay(orig_id, placeholder)
                        if not claimed:
                            # Another coroutine already claimed this slot.
                            LOG.debug("auto-replay: slot already claimed for task_id=%s", orig_id)
                            continue
                        try:
                            import json as _json
                            params = _json.loads(interrupted["parameters_json"])
                            new_id = await self.dispatch_task(
                                agent_id, interrupted["command"], params
                            )
                            # Replace placeholder with the real new task ID.
                            await self.db.mark_retried(orig_id, new_id)
                            LOG.info(
                                "auto-replay: task_id=%s cmd=%s replayed as %s",
                                orig_id[:8], interrupted["command"], new_id[:8],
                            )
                        except Exception as exc:
                            # Dispatch failed — release the slot so a future
                            # reconnect or manual retry can still attempt it.
                            await self.db.cancel_replay_reservation(orig_id, placeholder)
                            LOG.warning(
                                "auto-replay: could not replay task_id=%s: %s",
                                orig_id, exc,
                            )

                # ── Unknown message type ───────────────────────────────────────
                else:
                    await write_message(writer, make_message(
                        "ERROR", agent_id=agent_id, session_id=session_id,
                        payload={"error": f"unsupported message type: {mtype}"},
                    ))

        except (asyncio.IncompleteReadError, ConnectionError, asyncio.CancelledError):
            # Normal disconnect paths — no log needed; cleanup runs in finally.
            pass
        except ProtocolError as exc:
            # The agent sent something that violates the wire format.
            LOG.warning("protocol error peer=%s: %s", peer, exc)
        except Exception:
            # Unexpected server bug — log the full traceback.
            LOG.exception("client handler failed peer=%s", peer)
        finally:
            # ── Disconnect cleanup ─────────────────────────────────────────────
            # Always runs, regardless of whether the loop exited cleanly or with
            # an error.  Order matters: remove the connection first, then clean up
            # tasks, then close the session record.
            if agent_id:
                async with self.connection_lock:
                    # An older session must never alter the active replacement.
                    was_current = self.connections.get(agent_id) is writer
                    if was_current:
                        self.connections.pop(agent_id, None)
                        self.pending_sync.discard(agent_id)

                for message_id, (owner, sender, future) in list(self.pending_pings.items()):
                    if sender is writer:
                        self.pending_pings.pop(message_id, None)
                        if not future.done():
                            future.set_result(False)

                if was_current:
                    try:
                        # Any task that was RUNNING when the agent disconnected will
                        # never deliver a RESULT.  Mark them FAILED immediately so
                        # they do not sit in a permanent non-terminal state.
                        running = await self.db.get_running_tasks(agent_id)
                        for t in running:
                            try:
                                self._cancel_task_watchdog(t["task_id"])
                                await self.db.interrupt_task(t["task_id"], "connection_lost")
                                LOG.warning(
                                    "disconnect: task_id=%s marked FAILED"
                                    " (agent %s disconnected during execution)",
                                    t["task_id"], agent_id,
                                )
                            except (TaskNotFoundError, InvalidTaskTransition) as exc:
                                LOG.warning(
                                    "disconnect: could not mark task_id=%s FAILED: %s",
                                    t["task_id"], exc,
                                )

                        # Any task still in WAITING_ACK or QUEUED was never started.
                        # Cancel them so the operator knows to re-dispatch them.
                        stuck = await self.db.get_stuck_tasks(agent_id)
                        for t in stuck:
                            try:
                                self._cancel_task_watchdog(t["task_id"])
                                await self.db.interrupt_task(t["task_id"], "connection_lost")
                                LOG.warning(
                                    "disconnect: task_id=%s cancelled (was %s,"
                                    " agent %s disconnected before execution)",
                                    t["task_id"], t["status"], agent_id,
                                )
                            except (TaskNotFoundError, InvalidTaskTransition) as exc:
                                LOG.warning(
                                    "disconnect: could not cancel task_id=%s: %s",
                                    t["task_id"], exc,
                                )
                    except Exception:
                        LOG.exception(
                            "disconnect: error cleaning up tasks for agent=%s", agent_id
                        )
                else:
                    LOG.info("old session %s superseded; no task cleanup", session_id)

            await self.db.close_session(session_id, "DISCONNECTED")
            writer.close()
            try:
                await writer.wait_closed()
            except Exception:
                pass
            LOG.info("connection closed session=%s", session_id)

    async def ping_agent(self, agent_id: str, *, timeout: float = 3.0) -> bool:
        """Confirm round-trip liveness on the active TLS session."""
        writer = self.connections.get(agent_id)
        if writer is None or writer.is_closing() or agent_id in self.pending_sync:
            raise RuntimeError("Agent does not have a ready connection")
        message = make_message("PING", agent_id=agent_id)
        message_id = message["message_id"]
        future = asyncio.get_running_loop().create_future()
        self.pending_pings[message_id] = (agent_id, writer, future)
        try:
            await write_message(writer, message)
            return bool(await asyncio.wait_for(future, timeout))
        finally:
            self.pending_pings.pop(message_id, None)

    # ── Task dispatch ─────────────────────────────────────────────────────────

    async def dispatch_task(
        self, agent_id: str, command: str, parameters: dict
    ) -> str:
        """Create a task record and send the TASK message to the agent.

        Called by the CLI ``task`` command.  The sequence is:

        1. Verify the agent has an active connection.
        2. Insert a PENDING task record in the database.
        3. Advance to WAITING_ACK before writing, so an immediate ACK cannot
           race the state transition.
        4. Write the TASK message to the agent's stream; cancel if writing fails.

        The task transitions from PENDING to WAITING_ACK (not directly to
        QUEUED) because there is a window between writing the message and the
        agent acknowledging it.  If the agent disconnects in that window, the
        task stays in WAITING_ACK and is cancelled during reconciliation on
        the next reconnect.

        Parameters
        ----------
        agent_id : str
            Full UUID of the target agent (must be in self.connections).
        command : str
            Command name; must be in the agent's allowlist (``execute_allowed``).
        parameters : dict
            Command-specific parameters (e.g. ``{"text": "hello"}`` for echo).

        Returns
        -------
        str
            The new task's UUID, for display to the operator.

        Raises
        ------
        RuntimeError
            If ``agent_id`` is not currently connected or its writer is closing.
        """
        writer = self.connections.get(agent_id)
        if not writer or writer.is_closing():
            raise RuntimeError("Agent is not connected.")
        if agent_id in self.pending_sync:
            raise RuntimeError("Agent is registered but synchronization is not complete yet.")
        task_id = str(uuid.uuid4())
        await self.db.create_task(task_id, agent_id, command, parameters, "PENDING")
        msg = make_message("TASK", agent_id=agent_id, payload={
            "task_id":    task_id,
            "command":    command,
            "parameters": parameters,
        })
        # Set WAITING_ACK before writing to avoid racing the inbound TASK_ACK.
        await self.db.update_task_status(task_id, "WAITING_ACK")
        try:
            await write_message(writer, msg)
        except (OSError, ConnectionError, ssl.SSLError, ProtocolError):
            # The agent may or may not have received partial bytes. The task
            # is never replayed automatically; explicitly mark it cancelled.
            await self.db.interrupt_task(task_id, "dispatch_write_failed")
            raise
        # Start the timeout watchdog AFTER the write succeeds so the deadline
        # begins from the moment the message entered the OS send buffer.
        self._start_task_watchdog(task_id)
        return task_id

    async def retry_interrupted_readonly(self, task_id: str) -> str:
        """Manual, one-shot retry for demonstrably read-only tasks only.

        No automatic replay, particularly not for file transfers or lifecycle
        actions: the earlier operation may have completed before the drop.
        """
        async with self.recovery_lock:
            return await self._retry_interrupted_readonly_locked(task_id)

    async def _retry_interrupted_readonly_locked(self, task_id: str) -> str:
        """Inner implementation of retry_interrupted_readonly, called under recovery_lock.

        Validates the interrupted task is eligible for retry (read-only command,
        not already retried, agent connected), dispatches a new task, and links
        the two tasks in task_interruptions.retry_task_id.
        """
        import json as _json
        previous = await self.db.get_interruption(task_id)
        if not previous:
            raise ValueError("task has no recorded interruption")
        if previous["retry_task_id"]:
            raise ValueError("interrupted task was already retried")
        if previous["command"] not in {"echo", "get_info", "shell"}:
            raise ValueError("only read-only tasks can be retried; reissue file transfers manually")
        params = _json.loads(previous["parameters_json"])
        if previous["command"] == "shell" and params.get("command") not in {"pwd", "whoami", "uname"}:
            raise ValueError("retry rejected: shell command not allowlisted")
        new_id = await self.dispatch_task(previous["agent_id"], previous["command"], params)
        linked = await self.db.mark_retried(task_id, new_id)
        if not linked:
            LOG.warning("retry tracking conflict original=%s retry=%s", task_id, new_id)
            raise RuntimeError("retry lineage could not be recorded")
        return new_id

    # ── CLI formatting helpers ────────────────────────────────────────────────

    @staticmethod
    def _short(uuid_str: str | None, n: int = 8) -> str:
        """Return the first ``n`` characters of a UUID for compact display.

        Full UUIDs are 36 characters and hard to scan in a table.  Eight
        characters are sufficient to identify an agent or task in a lab
        environment with a small number of concurrent connections.

        Returns ``'—'`` for None values (e.g. a session with no agent yet).
        """
        return (uuid_str or "—")[:n]

    @staticmethod
    def _ts(iso: str | None) -> str:
        """Extract the HH:MM:SS portion of an ISO-8601 UTC timestamp.

        The date part is omitted because in a lab session all events
        typically occur on the same day.  The time alone is enough for
        the operator to sequence events.

        Examples
        --------
        ``"2024-10-24T10:23:45.123456+00:00"``  →  ``"10:23:45"``
        ``None``  →  ``"—"``
        """
        if not iso:
            return "—"
        try:
            return iso[11:19]  # characters 11–18 of ISO-8601 are always HH:MM:SS
        except Exception:
            return iso

    @staticmethod
    def _platform_short(p: str | None) -> str:
        """Truncate a ``platform.platform()`` string to the first two segments.

        Example: ``"Linux-6.1.0-21-amd64-x86_64-with-glibc2.36"``
                 → ``"Linux-6.1"``

        Avoids long platform strings overflowing the CLI table columns.
        """
        if not p:
            return "—"
        parts = p.split("-")
        return "-".join(parts[:2]) if len(parts) > 2 else p

    # ── CLI ─────────────────────────────────────────────────────────────────────

    async def cli(self) -> None:
        """Rich interactive operator CLI.

        Runs as an asyncio Task alongside the TLS server.  Uses
        ``asyncio.to_thread(input, ...)`` so blocking input() does not stall
        the event loop.  All output goes through a Rich Console so tables,
        colours, and panels render correctly.  The _PromptAwareHandler erases
        the prompt before writing log lines and redraws it after.
        """
        from rich.console import Console
        from rich.table import Table
        from rich.panel import Panel
        from rich.text import Text
        from rich import box as rbox
        import json as _json

        # Use an injected console (tests can set self._test_console for capture)
        # or create a real terminal console for production.
        con: Console = self._test_console or Console(highlight=False)

        # ── Visual helpers ────────────────────────────────────────────────────

        STATUS_COLOUR = {
            "PENDING":     "grey50",
            "WAITING_ACK": "yellow",
            "QUEUED":      "cyan",
            "RUNNING":     "blue",
            "COMPLETED":   "green",
            "FAILED":      "red",
            "TIMEOUT":     "dark_orange",
            "CANCELLED":   "magenta",
            "DISCONNECTED":"grey50",
            "CONNECTED":   "cyan",
            "ACTIVE":      "green",
        }

        def coloured_status(s: str | None) -> str:
            """Return a Rich markup string that colours a status value."""
            s = s or "—"
            colour = STATUS_COLOUR.get(s, "white")
            return f"[{colour}]{s}[/{colour}]"

        def header_panel(text: str) -> Panel:
            """Return a bold blue bordered panel used as a section header."""
            return Panel(Text(text, style="bold white", justify="center"),
                         style="bold blue", box=rbox.HEAVY, expand=False)

        # ── Banner ────────────────────────────────────────────────────────────
        banner = Panel(
            Text.from_markup(
                "[bold red]C2-MVP[/bold red]  [dim]─[/dim]  "
                "[bold]Authorized lab use only[/bold]\n"
                "[dim]Type [bold white]help[/bold white] to list commands  "
                "│  [bold white]quit[/bold white] to exit cleanly[/dim]"
            ),
            box=rbox.DOUBLE_EDGE,
            border_style="blue",
            expand=False,
        )
        con.print(banner)
        con.print()

        # ── Tabular formatters ────────────────────────────────────────────────

        async def show_agents():
            """Render the registered agents table with live connection status."""
            rows = await self.db.list_agents()
            if not rows:
                con.print("[yellow]No agents registered yet.[/yellow]")
                return
            t = Table(title="Registered Agents", box=rbox.ROUNDED,
                      border_style="blue", show_lines=True, expand=False)
            t.add_column("ID prefix",    style="bold cyan",  no_wrap=True)
            t.add_column("Hostname",     style="white",      no_wrap=True)
            t.add_column("Platform",     style="dim",        no_wrap=True, max_width=22)
            t.add_column("Last seen",    style="dim",        no_wrap=True)
            t.add_column("Connected",    no_wrap=True)
            async with self.connection_lock:
                connected = set(self.connections.keys())
            for row in rows:
                aid = row["agent_id"]
                is_conn = aid in connected
                conn_str = "[green]●  yes[/green]" if is_conn else "[red]○  no[/red]"
                t.add_row(
                    self._short(aid),
                    row["hostname"],
                    self._platform_short(row["platform"]),
                    self._ts(row["last_seen"]),
                    conn_str,
                )
            con.print(t)

        async def show_sessions():
            """Render all TLS sessions (active and historical) as a table."""
            rows = await self.db.list_sessions()
            if not rows:
                con.print("[yellow]No sessions yet.[/yellow]")
                return
            t = Table(title="TLS Sessions", box=rbox.ROUNDED,
                      border_style="blue", show_lines=True, expand=False)
            t.add_column("Session ID",   style="bold cyan",  no_wrap=True)
            t.add_column("Agent",        style="white",      no_wrap=True)
            t.add_column("State",        no_wrap=True)
            t.add_column("Started",      style="dim",        no_wrap=True)
            t.add_column("Ended",        style="dim",        no_wrap=True)
            for row in rows:
                t.add_row(
                    self._short(row["session_id"]),
                    self._short(row["agent_id"]),
                    coloured_status(row["state"]),
                    self._ts(row["started_at"]),
                    self._ts(row["ended_at"]) if row["ended_at"] else "[dim]active[/dim]",
                )
            con.print(t)

        async def show_tasks(filter_cmd: str | None = None):
            """Render the tasks table, optionally filtered to a single command name."""
            rows = await self.db.list_tasks()
            if filter_cmd:
                rows = [r for r in rows if r["command"] == filter_cmd]
            if not rows:
                con.print("[yellow]No tasks found.[/yellow]")
                return
            t = Table(title="Tasks", box=rbox.ROUNDED,
                      border_style="blue", show_lines=True, expand=False)
            t.add_column("Task ID",   style="bold cyan",  no_wrap=True)
            t.add_column("Agent",     style="white",      no_wrap=True)
            t.add_column("Command",   style="bold",       no_wrap=True)
            t.add_column("Status",    no_wrap=True)
            t.add_column("Updated",   style="dim",        no_wrap=True)
            for row in rows:
                t.add_row(
                    self._short(row["task_id"]),
                    self._short(row["agent_id"]),
                    row["command"],
                    coloured_status(row["status"]),
                    self._ts(row["updated_at"]),
                )
            con.print(t)

        async def show_interrupted():
            """Render the interrupted tasks ledger as a yellow-bordered table."""
            rows = await self.db.list_interruptions()
            if not rows:
                con.print("[yellow]No interrupted tasks.[/yellow]")
                return
            t = Table(title="Interrupted Tasks", box=rbox.ROUNDED,
                      border_style="yellow", show_lines=True, expand=False)
            t.add_column("Task ID",       style="bold cyan",  no_wrap=True)
            t.add_column("Agent",         style="white",      no_wrap=True)
            t.add_column("Command",       style="bold",       no_wrap=True)
            t.add_column("Was",           style="yellow",     no_wrap=True)
            t.add_column("Outcome",       style="dim",        no_wrap=True)
            t.add_column("Reason",        style="dim",        no_wrap=True)
            t.add_column("Retry",         style="green",      no_wrap=True)
            for row in rows:
                retry = (self._short(row["retry_task_id"])
                         if row.get("retry_task_id") and not row["retry_task_id"].startswith("__pending_")
                         else "[dim]—[/dim]")
                t.add_row(
                    self._short(row["task_id"]),
                    self._short(row["agent_id"]),
                    row["command"],
                    row["previous_status"],
                    row["outcome"],
                    row["reason"],
                    retry,
                )
            con.print(t)

        async def show_result(prefix: str):
            """Render the full result panel for a task identified by a UUID prefix.

            JSON output (sysinfo, shellcode, download confirmation) is
            automatically pretty-printed as a key-value grid.  If no result
            row exists but an interruption record does, the interruption details
            are shown instead with a retry hint.
            """
            all_tasks = await self.db.list_tasks()
            matches = [t for t in all_tasks if t["task_id"].startswith(prefix)]
            if not matches:
                con.print(f"[red]No task with ID starting with {prefix!r}[/red]")
                return
            if len(matches) > 1:
                con.print(f"[yellow]Ambiguous prefix [bold]{prefix!r}[/bold] — {len(matches)} matches:[/yellow]")
                for m in matches:
                    con.print(f"  [cyan]{m['task_id']}[/cyan]  [{STATUS_COLOUR.get(m['status'],'white')}]{m['status']}[/{STATUS_COLOUR.get(m['status'],'white')}]")
                return
            task = matches[0]
            results = await self.db.list_results(task["task_id"])

            # Task header
            meta = Table.grid(padding=(0, 2))
            meta.add_column(style="bold dim", no_wrap=True)
            meta.add_column(style="white")
            meta.add_row("task_id",  task["task_id"])
            meta.add_row("agent",    self._short(task["agent_id"]))
            meta.add_row("command",  task["command"])
            if task["command"] == "upload":
                try:
                    d = _json.loads(task["parameters_json"])
                    meta.add_row("file", f"{d.get('name')}  ({d.get('bytes', '?')} bytes)")
                except Exception:
                    meta.add_row("params", task["parameters_json"])
            else:
                meta.add_row("params",   task["parameters_json"])
            meta.add_row("status",   coloured_status(task["status"]))
            meta.add_row("updated",  task["updated_at"])
            con.print(Panel(meta, title="[bold]Task[/bold]", border_style="blue", box=rbox.ROUNDED))

            if not results:
                interruption = await self.db.get_interruption(task["task_id"])
                if interruption:
                    idata = Table.grid(padding=(0, 2))
                    idata.add_column(style="bold dim")
                    idata.add_column(style="white")
                    idata.add_row("reason",   interruption["reason"])
                    idata.add_row("was",      interruption["previous_status"])
                    idata.add_row("outcome",  interruption["outcome"])
                    idata.add_row("recorded", interruption["interrupted_at"])
                    rtid = interruption.get("retry_task_id")
                    if rtid and not rtid.startswith("__pending_"):
                        idata.add_row("retried", rtid)
                    else:
                        idata.add_row("hint",
                            f"[dim]retry {task['task_id'][:8]}[/dim]  (read-only tasks only)")
                    con.print(Panel(idata, title="[bold yellow]Interruption record[/bold yellow]",
                                    border_style="yellow", box=rbox.ROUNDED))
                else:
                    con.print(Panel("[dim]No result stored yet.[/dim]",
                                    border_style="dim", box=rbox.ROUNDED))
            else:
                for r in results:
                    raw = r["output"]
                    # Pretty-print JSON output (sysinfo, shellcode, download confirmation)
                    try:
                        parsed = _json.loads(raw)
                        if isinstance(parsed, dict):
                            g = Table.grid(padding=(0, 2))
                            g.add_column(style="bold dim", no_wrap=True)
                            g.add_column(style="white", overflow="fold")
                            for k, v in parsed.items():
                                if isinstance(v, dict):
                                    g.add_row(k, _json.dumps(v, ensure_ascii=False))
                                else:
                                    g.add_row(k, str(v))
                            con.print(Panel(g, title="[bold green]Result[/bold green]",
                                            border_style="green", box=rbox.ROUNDED))
                        else:
                            con.print(Panel(str(parsed), title="[bold green]Result[/bold green]",
                                            border_style="green", box=rbox.ROUNDED))
                    except (_json.JSONDecodeError, TypeError):
                        con.print(Panel(raw, title="[bold green]Result[/bold green]",
                                        border_style="green", box=rbox.ROUNDED))
                    con.print(f"[dim]stored: {r['created_at']}[/dim]")

        # ── Help panel ────────────────────────────────────────────────────────

        def show_help():
            """Render the full command reference table."""
            t = Table(title="Available Commands", box=rbox.ROUNDED,
                      border_style="blue", show_lines=True, expand=False,
                      title_style="bold white")
            t.add_column("Command",     style="bold cyan",   no_wrap=True)
            t.add_column("Description", style="white")
            t.add_column("Example",     style="dim italic",  no_wrap=False)
            t.add_row("agents",
                      "List all known agents with connection status",
                      "agents")
            t.add_row("sessions",
                      "List all TLS sessions (active and historical)",
                      "sessions")
            t.add_row("tasks [cmd]",
                      "List all tasks; optionally filter by command name",
                      "tasks  /  tasks echo")
            t.add_row("interrupted",
                      "List tasks whose outcome is uncertain after a disconnect",
                      "interrupted")
            t.add_row("result <prefix>",
                      "Show full result for a task (short ID prefix accepted)",
                      "result a1b2c3d4")
            t.add_row("retry <prefix>",
                      "Re-dispatch a read-only interrupted task (once only)",
                      "retry a1b2c3d4")
            t.add_row("─── Task dispatch ───",  "", "")
            t.add_row("task <agent> echo <text>",
                      "Send an echo payload to the agent",
                      "task ab get_info")
            t.add_row("task <agent> get_info",
                      "Compact one-line agent identification",
                      "task ab get_info")
            t.add_row("task <agent> sysinfo",
                      "Deep system inventory (OS, CPU, memory, network, env)",
                      "task ab sysinfo")
            t.add_row("task <agent> shell <cmd>",
                      "Read-only shell: pwd | whoami | uname",
                      "task ab shell whoami")
            t.add_row("task <agent> shellcode <binary> [args]",
                      "Execute a pre-built binary from the agent lab directory",
                      "task ab shellcode hello_world")
            t.add_row("task <agent> upload <filename>",
                      "Send a file from server lab dir to agent lab dir",
                      "task ab upload payload.bin")
            t.add_row("task <agent> download <filename>",
                      "Retrieve a file from agent lab dir to server downloads",
                      "task ab download result.txt")
            t.add_row("task <agent> persist [args]",
                      "Install user-scope OS startup entry (systemd/launchd/schtasks)",
                      "task ab persist --server 127.0.0.1")
            t.add_row("task <agent> unpersist",
                      "Remove the OS startup entry",
                      "task ab unpersist")
            t.add_row("task <agent> self_remove",
                      "Gracefully stop agent and remove its installed files",
                      "task ab self_remove")
            t.add_row("─── Management ───",  "", "")
            t.add_row("ping <agent>",
                      "Send PING and measure round-trip latency",
                      "ping ab")
            t.add_row("disconnect <agent>",
                      "Drop the TLS session (agent will reconnect automatically)",
                      "disconnect ab")
            t.add_row("lab <subcommand>",
                      "Local-only simulations (never sent to agents): init, upload, beacon…",
                      "lab help")
            t.add_row("quit / exit",
                      "Gracefully shut down the server and disconnect all agents",
                      "quit")
            con.print(t)
            con.print(
                "[dim]Agent and task IDs accept any unique prefix. "
                "Short IDs (8 chars) are shown in table views.[/dim]"
            )

        # ── Command loop ──────────────────────────────────────────────────────

        while True:
            try:
                line = await asyncio.to_thread(input, "\n[c2]> ")
            except (EOFError, KeyboardInterrupt):
                break
            parts = line.strip().split()
            if not parts:
                continue
            cmd = parts[0].lower()
            con.print()  # visual breathing room after input

            # ── help ──────────────────────────────────────────────────────────
            if cmd == "help":
                show_help()

            # ── agents ────────────────────────────────────────────────────────
            elif cmd == "agents":
                await show_agents()

            # ── sessions ──────────────────────────────────────────────────────
            elif cmd == "sessions":
                await show_sessions()

            # ── tasks [command_filter] ─────────────────────────────────────────
            elif cmd == "tasks":
                filter_cmd = parts[1] if len(parts) >= 2 else None
                await show_tasks(filter_cmd)

            # ── interrupted ───────────────────────────────────────────────────
            elif cmd == "interrupted":
                await show_interrupted()

            # ── result <prefix> ───────────────────────────────────────────────
            elif cmd == "result" and len(parts) >= 2:
                await show_result(parts[1])

            # ── retry <prefix> ────────────────────────────────────────────────
            elif cmd == "retry" and len(parts) == 2:
                rows = await self.db.list_interruptions()
                matches = [r for r in rows if r["task_id"].startswith(parts[1])]
                if len(matches) != 1:
                    con.print(f"[red]No unique interrupted task matches {parts[1]!r}[/red]")
                else:
                    try:
                        new_id = await self.retry_interrupted_readonly(matches[0]["task_id"])
                        con.print(
                            f"[green]✓[/green] Read-only retry dispatched: "
                            f"[cyan]{new_id[:8]}[/cyan]  "
                            f"[dim](original: {matches[0]['task_id'][:8]})[/dim]"
                        )
                    except (ValueError, RuntimeError, OSError, ConnectionError) as exc:
                        con.print(f"[red]Retry refused:[/red] {exc}")

            # ── ping <prefix> ─────────────────────────────────────────────────
            elif cmd == "ping" and len(parts) == 2:
                async with self.connection_lock:
                    matches = [aid for aid in self.connections if aid.startswith(parts[1])]
                if len(matches) != 1:
                    con.print(f"[red]No unique connected agent matches {parts[1]!r}[/red]")
                else:
                    import time as _time
                    try:
                        t0 = _time.monotonic()
                        healthy = await self.ping_agent(matches[0])
                        rtt = (_time.monotonic() - t0) * 1000
                        if healthy:
                            con.print(
                                f"[green]PONG[/green] from [cyan]{matches[0][:8]}[/cyan]  "
                                f"[dim]rtt={rtt:.1f} ms[/dim]"
                            )
                        else:
                            con.print("[yellow]Agent disconnected during ping[/yellow]")
                    except (RuntimeError, OSError, asyncio.TimeoutError) as exc:
                        con.print(f"[red]Ping failed:[/red] {exc}")

            # ── disconnect <prefix> ───────────────────────────────────────────
            elif cmd == "disconnect" and len(parts) == 2:
                typed_id = parts[1]
                async with self.connection_lock:
                    matches = [(aid, w) for aid, w in self.connections.items()
                               if aid.startswith(typed_id)]
                if not matches:
                    con.print(f"[red]No connected agent with ID starting with {typed_id!r}[/red]")
                elif len(matches) > 1:
                    con.print(f"[yellow]Ambiguous prefix[/yellow] {typed_id!r}; provide a longer ID")
                else:
                    aid, w = matches[0]
                    w.close()
                    con.print(
                        f"[green]✓[/green] Closed TLS session for agent [cyan]{aid[:8]}[/cyan]  "
                        f"[dim](agent may reconnect automatically)[/dim]"
                    )

            # ── lab <subcommand> ──────────────────────────────────────────────
            elif cmd == "lab":
                from lab_demo.cli import run_lab_command
                run_lab_command(parts[1:])

            # ── task <agent> <command> [args] ─────────────────────────────────
            elif cmd == "task" and len(parts) >= 3:
                typed_id = parts[1]
                command  = parts[2]

                # Parse parameters
                if command in {"get_info", "sysinfo", "self_remove", "unpersist"} and len(parts) == 3:
                    params: dict = {}
                elif command == "echo" and len(parts) >= 4:
                    params = {"text": line.strip().split(None, 3)[3]}
                elif command == "shell" and len(parts) == 4 and parts[3] in {"pwd", "whoami", "uname"}:
                    params = {"command": parts[3]}
                elif command == "shellcode" and len(parts) >= 4:
                    # task <agent> shellcode <binary> [arg1 arg2 ...]
                    params = {"name": parts[3], "args": parts[4:]}
                elif command == "upload" and len(parts) == 4:
                    try:
                        params = read_lab_file(self.upload_dir, parts[3])
                    except ValueError as exc:
                        con.print(f"[red]Upload rejected:[/red] {exc}")
                        continue
                elif command == "download" and len(parts) == 4:
                    try:
                        params = {"name": validate_name(parts[3])}
                    except ValueError as exc:
                        con.print(f"[red]Download rejected:[/red] {exc}")
                        continue
                elif command == "persist" and len(parts) >= 3:
                    extra = parts[3:] if len(parts) > 3 else []
                    params = {"agent_args": extra}
                else:
                    con.print(
                        "[yellow]Usage:[/yellow] task <agent> "
                        "[bold]echo[/bold] <text>  │  "
                        "[bold]get_info[/bold]  │  "
                        "[bold]sysinfo[/bold]  │  "
                        "[bold]shell[/bold] <pwd|whoami|uname>  │  "
                        "[bold]shellcode[/bold] <binary> [args]  │  "
                        "[bold]upload[/bold] <file>  │  "
                        "[bold]download[/bold] <file>  │  "
                        "[bold]persist[/bold] [startup-args]  │  "
                        "[bold]unpersist[/bold]  │  "
                        "[bold]self_remove[/bold]"
                    )
                    continue

                # Resolve agent_id prefix
                async with self.connection_lock:
                    connected_ids = list(self.connections.keys())
                matches = [aid for aid in connected_ids if aid.startswith(typed_id)]
                if len(matches) == 0:
                    con.print(f"[red]No connected agent with ID starting with {typed_id!r}[/red]")
                    continue
                if len(matches) > 1:
                    con.print(f"[yellow]Ambiguous prefix[/yellow] {typed_id!r} — matches:")
                    for aid in matches:
                        con.print(f"  [cyan]{aid}[/cyan]")
                    continue

                agent_id = matches[0]
                try:
                    task_id = await self.dispatch_task(agent_id, command, params)
                    con.print(
                        f"[green]✓[/green] Task dispatched: [cyan]{task_id[:8]}[/cyan]  "
                        f"[dim]→ agent [cyan]{agent_id[:8]}[/cyan]  "
                        f"command=[bold]{command}[/bold]  "
                        f"(view with: result {task_id[:8]})[/dim]"
                    )
                except Exception as exc:
                    con.print(f"[red]Dispatch failed:[/red] {exc}")

            # ── quit / exit ───────────────────────────────────────────────────
            elif cmd in {"quit", "exit"}:
                con.print("[bold yellow]Shutting down — closing all agent connections…[/bold yellow]")
                break

            else:
                con.print(
                    f"[red]Unknown command:[/red] [bold]{cmd}[/bold]  "
                    "[dim](type [bold white]help[/bold white] for available commands)[/dim]"
                )

# ── Server startup ────────────────────────────────────────────────────────────

async def run(args) -> None:
    """Configure logging, initialise TLS and the database, then start the server.

    Lifecycle
    ---------
    1. Configure the root logger with either a file handler (``--log-file``)
       or a ``_PromptAwareHandler`` that writes to stderr without disrupting
       the CLI prompt.
    2. Verify that the TLS certificate and key files exist.
    3. Build the TLS context (server-side, TLS 1.2+).
    4. Open the database and create tables if needed.
    5. Start the TCP server with ``_tracked_handle_client`` as the callback.
    6. Launch the CLI loop as a parallel asyncio Task.
    7. ``async with server`` keeps the server running until the CLI Task exits.
    8. On CLI exit: ``shutdown()`` closes all agents, then the listening socket
       is closed, and the database is flushed and closed.

    Parameters
    ----------
    args : argparse.Namespace
        Parsed CLI arguments from ``main()``.
    """
    # ── Logging setup ─────────────────────────────────────────────────────────
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
    log_file = getattr(args, "log_file", None) or None
    root = logging.getLogger()
    # Clear any handlers that were attached by basicConfig calls inside
    # imported modules; we install exactly one handler to avoid duplicate lines.
    root.handlers.clear()
    if log_file:
        # File mode: logs go to the file; stderr stays clean for the prompt.
        handler: logging.Handler = logging.FileHandler(log_file)
    else:
        # Terminal mode: use the prompt-aware handler so log lines do not
        # corrupt the operator's partially-typed input.
        handler = _PromptAwareHandler(sys.stderr)
    handler.setFormatter(fmt)
    root.setLevel(logging.INFO)
    root.addHandler(handler)

    # ── TLS context ───────────────────────────────────────────────────────────
    cert, key = Path(args.cert), Path(args.key)
    if not cert.is_file() or not key.is_file():
        raise SystemExit(
            "TLS certificate/key not found.\n"
            "Generate a development certificate with:\n"
            "  openssl req -x509 -newkey rsa:2048 -days 365 -nodes \\\n"
            "    -keyout certs/server.key -out certs/server.crt \\\n"
            "    -subj '/CN=127.0.0.1' -addext 'subjectAltName=IP:127.0.0.1'\n"
            "For mTLS, also run: python -m shared.mtls generate-lab-certs"
        )
    agent_ca = Path(args.agent_ca) if getattr(args, "agent_ca", None) else None
    if agent_ca is not None and not agent_ca.is_file():
        raise SystemExit(f"Agent CA certificate not found: {agent_ca}")
    # build_server_context enables CERT_REQUIRED when agent_ca is supplied (mTLS)
    # and falls back to server-auth-only mode otherwise (backward-compatible).
    context = build_server_context(cert, key, agent_ca=agent_ca)
    if agent_ca:
        LOG.info("mTLS enabled: agent certificates verified against %s", agent_ca)
    else:
        LOG.info(
            "mTLS disabled: agent identity is self-declared. "
            "Use --agent-ca certs/agent-ca.crt to enable mutual authentication."
        )

    # ── Database and server ───────────────────────────────────────────────────
    db = Database(args.db)
    await db.initialize()
    interrupted = await db.reconcile_process_restart()
    if interrupted:
        LOG.warning("startup recovery: %d unfinished tasks recorded; no automatic replay", interrupted)
    upload_dir = Path(getattr(args, "upload_dir", "data/server_files"))
    download_dir = Path(getattr(args, "download_dir", "data/server_downloads"))
    upload_dir.mkdir(parents=True, exist_ok=True)
    download_dir.mkdir(parents=True, exist_ok=True)
    task_timeout = float(getattr(args, "task_timeout", DEFAULT_TASK_TIMEOUT))
    app = C2Server(db, upload_dir=upload_dir, download_dir=download_dir,
                   task_timeout=task_timeout, mtls_enabled=agent_ca is not None)

    # _tracked_handle_client wraps handle_client to register tasks in
    # app._handler_tasks, enabling clean shutdown via app.shutdown().
    server = await asyncio.start_server(
        app._tracked_handle_client, args.host, args.port, ssl=context
    )
    LOG.info("listening on %s:%s (TLS)", args.host, args.port)

    # Run the CLI loop as a parallel task; the server keeps accepting
    # connections until cli() returns (operator typed 'quit').
    cli_task = asyncio.create_task(app.cli())
    async with server:
        await cli_task
        # 'quit' was typed: gracefully close all agent connections so they
        # see a clean EOF rather than a sudden TCP RST.
        await app.shutdown()
        server.close()
        await server.wait_closed()

    await db.close()


def main() -> None:
    """Entry point for ``python -m server.main``.

    Parses command-line arguments and delegates to the async ``run()``
    coroutine via ``asyncio.run()``.
    """
    parser = argparse.ArgumentParser(description="Lab-only C2 server MVP")
    parser.add_argument("--host", default="127.0.0.1",
                        help="Listening address (default: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=9443,
                        help="Listening port (default: 9443)")
    parser.add_argument("--cert", default="certs/server.crt",
                        help="TLS certificate file (PEM)")
    parser.add_argument("--key",  default="certs/server.key",
                        help="TLS private key file (PEM)")
    parser.add_argument("--db",   default="data/c2.sqlite3",
                        help="SQLite database path (default: data/c2.sqlite3)")
    parser.add_argument(
        "--log-file", default=None, metavar="PATH",
        help=(
            "Write server logs to FILE instead of stderr. "
            "Recommended when running interactively to prevent log lines "
            "from disrupting the c2> prompt."
        ),
    )
    parser.add_argument("--upload-dir", default="data/server_files",
                        help="Server-side approved files to send to agents")
    parser.add_argument("--download-dir", default="data/server_downloads",
                        help="Server-side destination for retrieved lab files")
    parser.add_argument(
        "--agent-ca", default=None, metavar="PATH",
        help=(
            "CA certificate (PEM) used to verify agent client certificates. "
            "When set, mutual TLS (mTLS) is enabled: every connecting agent must "
            "present a certificate signed by this CA. The certificate CN becomes "
            "the authoritative agent_id. "
            "Generate with: python -m shared.mtls generate-lab-certs"
        ),
    )
    parser.add_argument(
        "--task-timeout", type=float, default=DEFAULT_TASK_TIMEOUT,
        metavar="SECONDS",
        help=(
            f"Wall-clock deadline for each dispatched task in seconds "
            f"(default: {DEFAULT_TASK_TIMEOUT:.0f}). Tasks with no RESULT "
            f"within this window are marked TIMEOUT."
        ),
    )
    args = parser.parse_args()
    if not (1.0 <= args.task_timeout <= 3600.0):
        parser.error("--task-timeout must be between 1 and 3600 seconds")
    asyncio.run(run(args))


if __name__ == "__main__":
    main()
