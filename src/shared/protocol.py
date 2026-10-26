"""
shared/protocol.py — JSON-lines message framing for the lab C2.

Role in the architecture
------------------------
This module is the single source of truth for the wire format shared between
the server (server/main.py) and every agent (agent/main.py).  Neither side
contains its own serialisation logic; both import only from here.

Wire format
-----------
Every message is one line of UTF-8 JSON terminated by a newline character
(JSON-lines / NDJSON).  The maximum size of one message, including the
trailing newline, is MAX_MESSAGE_BYTES (1 MiB).  TLS framing is handled
by the asyncio SSL layer; this module is transport-agnostic.

Message envelope
----------------
Every message, regardless of type, carries these top-level fields:

    {
        "version":    1,               # protocol version — must be 1
        "message_id": "<uuid4>",       # unique ID for this specific message
        "type":       "<MESSAGE_TYPE>",# one of ALLOWED_TYPES
        "agent_id":   "<uuid4>|null",  # the agent this message concerns
        "session_id": "<uuid4>|null",  # the TLS session this message belongs to
        "timestamp":  "<ISO-8601>",    # UTC time the message was created
        "payload":    {}               # type-specific data (always a JSON object)
    }

Allowed message types and their direction
------------------------------------------
REGISTER            agent  → server   agent presents its identity
REGISTER_ACK        server → agent    server confirms registration
PING                either → either   liveness probe
PONG                either → either   liveness reply
BEACON              agent  → server   periodic heartbeat / idle signal
BEACON_ACK          server → agent    heartbeat acknowledgement
TASK                server → agent    server dispatches a command for execution
TASK_ACK            agent  → server   agent confirms it received the task
TASK_STATUS         agent  → server   agent reports execution progress (RUNNING)
RESULT              agent  → server   agent delivers the final task output
RESULT_ACK          server → agent   server confirms result was persisted (v7)
TASK_STATUS_QUERY   server → agent   server asks agent for a task's current status (v8)
TASK_STATUS_RESPONSE agent → server  agent replies with known status and running tasks (v8)
SYNC_STATE          agent  → server   agent reports pending IDs after reconnect
SYNC_STATE_RESPONSE server → agent    server acknowledges the sync report
SYNC_COMPLETE       server → agent    server signals the session is ready
ERROR               either → either   error notification (does not close connection)
"""

import asyncio
import json
import uuid
from datetime import datetime, timezone

# ── Constants ─────────────────────────────────────────────────────────────────

# Hard upper bound on a single serialised message (header + payload + newline).
# Prevents memory exhaustion from a large or malicious payload.
MAX_MESSAGE_BYTES = 1024 * 1024  # 1 MiB

# Exhaustive set of accepted message type strings.
# Any type not in this set is rejected by both make_message() and validate_message().
ALLOWED_TYPES = {
    "REGISTER", "REGISTER_ACK",
    "PING", "PONG",
    "BEACON", "BEACON_ACK",
    "TASK", "TASK_ACK", "TASK_STATUS", "RESULT",
    "RESULT_ACK",              # server → agent: confirms RESULT was persisted (v7)
    "TASK_STATUS_QUERY",       # server → agent: request current task status (v8)
    "TASK_STATUS_RESPONSE",    # agent → server: reply to TASK_STATUS_QUERY (v8)
    "SYNC_STATE", "SYNC_STATE_RESPONSE", "SYNC_COMPLETE",
    "ERROR",
}


# ── Exception ─────────────────────────────────────────────────────────────────

class ProtocolError(ValueError):
    """Raised when a message violates the protocol envelope rules.

    This is a ValueError subclass so callers can use a single
    ``except (ProtocolError, ValueError)`` clause when needed, though
    server/main.py catches it specifically to distinguish protocol
    violations from unexpected runtime errors.
    """


# ── Message construction ──────────────────────────────────────────────────────

def make_message(message_type, *, agent_id=None, session_id=None, payload=None):
    """Build a well-formed protocol message dictionary.

    Parameters
    ----------
    message_type : str
        One of the strings in ALLOWED_TYPES.  Raises ProtocolError if unknown.
    agent_id : str or None
        UUID of the agent this message concerns.  May be None for messages
        sent before REGISTER completes (e.g. initial ERROR replies).
    session_id : str or None
        UUID of the current TLS session.  May be None for the same reason.
    payload : dict or None
        Type-specific data.  Defaults to an empty dict so the envelope is
        always valid (validate_message requires payload to be a dict object).

    Returns
    -------
    dict
        A dictionary ready to be passed to write_message().

    Raises
    ------
    ProtocolError
        If message_type is not in ALLOWED_TYPES.
    """
    if message_type not in ALLOWED_TYPES:
        raise ProtocolError(f"unsupported message type: {message_type}")
    return {
        "version":    1,
        "message_id": str(uuid.uuid4()),   # unique per message, not per session
        "type":       message_type,
        "agent_id":   agent_id,
        "session_id": session_id,
        "timestamp":  datetime.now(timezone.utc).isoformat(),
        "payload":    payload or {},
    }


# ── Message validation ────────────────────────────────────────────────────────

def validate_message(message):
    """Validate that a parsed dict conforms to the protocol envelope.

    This function is called both when reading a message (after JSON parsing)
    and before writing one (as a final sanity check in write_message).

    Parameters
    ----------
    message : any
        The object produced by json.loads().  Must be a dict.

    Returns
    -------
    dict
        The same dict, unchanged, so callers can write ``return validate_message(msg)``.

    Raises
    ------
    ProtocolError
        On any envelope violation: wrong type, missing field, bad version,
        unknown message type, invalid message_id format, or non-dict payload.
    """
    # The envelope must be a JSON object, not an array or scalar.
    if not isinstance(message, dict):
        raise ProtocolError("message must be a JSON object")

    # All envelope fields must be present; payload-specific fields live inside payload.
    required = {"version", "message_id", "type", "timestamp", "payload"}
    if not required.issubset(message):
        raise ProtocolError("missing required envelope fields")

    # Only protocol version 1 is supported.  A future version bump here would
    # allow old and new agents to coexist during a rolling upgrade.
    if message["version"] != 1:
        raise ProtocolError("unsupported protocol version")

    # Reject unknown message types early so message handlers never see them.
    if message["type"] not in ALLOWED_TYPES:
        raise ProtocolError("unsupported message type")

    # message_id is used for logging and deduplication; it must be a short string.
    if not isinstance(message["message_id"], str) or len(message["message_id"]) > 128:
        raise ProtocolError("invalid message_id")

    # payload must always be a JSON object so handlers can safely call .get().
    if not isinstance(message["payload"], dict):
        raise ProtocolError("payload must be an object")

    return message


# ── Async I/O helpers ─────────────────────────────────────────────────────────

async def read_message(reader):
    """Read exactly one newline-terminated JSON message from an asyncio StreamReader.

    The function blocks until a complete line arrives, then validates the
    envelope before returning.  It is safe to call from multiple coroutines
    provided each coroutine has its own reader (asyncio streams are not
    thread-safe but are coroutine-safe when used with a single reader per
    connection).

    Parameters
    ----------
    reader : asyncio.StreamReader
        The read end of a TLS-wrapped TCP stream.

    Returns
    -------
    dict
        A validated message envelope.

    Raises
    ------
    asyncio.IncompleteReadError
        When the peer closes the connection before sending a complete line.
        Callers should treat this as a normal disconnect, not an error.
    ProtocolError
        When the line is too large, cannot be decoded as UTF-8, is not valid
        JSON, or fails envelope validation.
    """
    raw = await reader.readline()

    # An empty bytes object means the peer sent EOF (clean TCP close or TLS close_notify).
    if not raw:
        raise asyncio.IncompleteReadError(b"", 1)

    # Reject oversized messages before attempting to decode or parse them.
    if len(raw) > MAX_MESSAGE_BYTES:
        raise ProtocolError("message exceeds size limit")

    try:
        message = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ProtocolError("invalid JSON message") from exc

    return validate_message(message)


async def write_message(writer, message):
    """Serialise and send one message on an asyncio StreamWriter.

    The message is validated before serialisation so that programming errors
    in message construction are caught at the point of sending rather than
    silently producing malformed output on the wire.

    Parameters
    ----------
    writer : asyncio.StreamWriter
        The write end of a TLS-wrapped TCP stream.
    message : dict
        A dict built by make_message() and not modified afterwards.

    Raises
    ------
    ProtocolError
        If the message fails envelope validation or the serialised form
        exceeds MAX_MESSAGE_BYTES.
    """
    validate_message(message)

    # Compact serialisation (no extra spaces) keeps the line short.
    # ensure_ascii=False allows non-ASCII output values to pass through intact.
    raw = (
        json.dumps(message, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
        + b"\n"
    )

    if len(raw) > MAX_MESSAGE_BYTES:
        raise ProtocolError("message exceeds size limit")

    # writer.write() buffers the data; drain() flushes it to the OS send buffer.
    # On a TLS stream, drain() also performs the TLS record framing.
    writer.write(raw)
    await writer.drain()
