"""
agent/main.py — Harmless lab agent for the C2 server.

Role in the architecture
------------------------
The agent is the remote-execution component of the lab.  It connects to the
server over TLS, registers itself, then waits in a message loop for TASK
messages dispatched by the operator from the server CLI.

Security model
--------------
The agent is intentionally restrictive.  It only executes commands that are
explicitly listed in ``execute_allowed()``.  Any command name not in that
allowlist raises a ValueError, which is caught and returned to the server as
a FAILED result.  This prevents the lab from accidentally becoming a general
remote-code-execution tool.

The agent does NOT store any task state between sessions.  On reconnect it
sends an empty SYNC_STATE (``pending_task_ids: []``), relying entirely on the
server to reconcile any tasks that were in-flight when the previous connection
dropped.

Connection resilience
---------------------
On startup the agent retries the TLS connection with bounded exponential
backoff (up to 10 attempts). After an established TLS session ends, it can
open a new session with the same in-process agent ID. It never automatically
replays an interrupted task.

Message flow (normal task lifecycle)
--------------------------------------
    server                              agent
    ──────                              ─────
    accept TLS connection
                                        send REGISTER {agent_id, hostname, platform}
    send REGISTER_ACK {session_id}
                                        send SYNC_STATE {pending: []}
    cancel any stuck tasks
    send SYNC_STATE_RESPONSE
    send SYNC_COMPLETE
                                        send BEACON {IDLE}
    send BEACON_ACK
    (operator types: task echo hello)
    send TASK {task_id, command, params}
                                        LOG "task received"
                                        send TASK_ACK {task_id}
                                        send TASK_STATUS {RUNNING}
                                        execute_allowed(command, params)
                                        LOG "task completed"
                                        send RESULT {task_id, status, output}
    complete_task_with_result()

Startup
-------
    python -m agent.main [--server HOST] [--port PORT] [--ca CA_FILE]
                         [--agent-id UUID]

    Supported tasks: echo, get_info, restricted shell, and upload/download
    strictly within a configured lab directory (max 128 KiB per file).
    No arbitrary shell execution or arbitrary filesystem paths.

    Defaults: 127.0.0.1:9443, certs/server.crt, random UUID each run.
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import platform
import ssl
import subprocess
import sys
import uuid
import random
import json
import os
import tempfile
from pathlib import Path

from shared.protocol import make_message, read_message, write_message
from shared.lab_transfer import read_lab_file, write_lab_file
from shared.mtls import build_agent_context
from shared.platform_compat import SHELL_COMMANDS, platform_summary
from agent.local_state import AgentLocalState

# Module-level logger; basicConfig is called at the top of run().
LOG = logging.getLogger("agent")


def _create_runtime_marker(lab_dir: str, agent_id: str) -> Path:
    """Create a uniquely owned *temporary* laboratory state artifact.

    Never touches the agent executable, installation directory, or other files.
    This marker provides a concrete, inspectable artifact for controlled agent
    decommissioning without implementing a remote self-erasing executable.
    """
    folder = Path(lab_dir)
    folder.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix="runtime-state-", suffix=".json", dir=folder)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump({"purpose": "temporary_lab_agent_state", "agent_id": agent_id}, handle)
    except BaseException:
        Path(name).unlink(missing_ok=True)
        raise
    return Path(name)


# ── Command execution ─────────────────────────────────────────────────────────

def execute_allowed(command: str, parameters: dict, *, lab_dir: str = "data/agent_files") -> str:
    """Execute a command only if it appears in the explicit allowlist.

    This is the agent's security boundary.  Every command name that the server
    may send must be listed here explicitly.  Commands are implemented as
    simple Python operations; no shell invocation, no file-system access
    beyond what the Python standard library provides.

    Parameters
    ----------
    command : str
        The command name from the TASK message payload (e.g. ``"echo"``).
    parameters : dict
        Command-specific parameters from the TASK message payload.

    Returns
    -------
    str
        The command's textual output, to be sent back as the RESULT payload.

    Raises
    ------
    ValueError
        If the command is not in the allowlist, or if the parameters are
        invalid for an allowlisted command.  The caller catches this and
        returns a FAILED result to the server.

    Allowlisted commands
    --------------------
    echo
        Returns the ``text`` parameter unchanged.  Validates that ``text``
        is a string of at most 2000 characters.  Useful for verifying
        end-to-end connectivity without side effects.

    get_info
        Returns a one-line summary of the host OS, kernel release, machine
        architecture, and Python version.  Read-only; no parameters needed.
    """
    if not isinstance(parameters, dict):
        raise ValueError("task parameters must be an object")

    if command == "echo":
        text = parameters.get("text")
        # Validate type and length before echoing; an oversized echo parameter
        # would produce a very large RESULT message.
        if not isinstance(text, str) or len(text) > 2000:
            raise ValueError("echo requires text of at most 2000 characters")
        return text

    if command == "get_info":
        # Compact one-liner for quick identification of the agent host.
        import socket, getpass
        return (
            f"system={platform.system()} "
            f"release={platform.release()} "
            f"machine={platform.machine()} "
            f"python={platform.python_version()} "
            f"hostname={socket.gethostname()} "
            f"user={getpass.getuser()} "
            f"pid={os.getpid()}"
        )

    if command == "sysinfo":
        """Deep system inventory — no external dependencies, stdlib only."""
        import socket, getpass, struct, json as _json

        info: dict = {}

        # ── Identity ──────────────────────────────────────────────────────────
        info["hostname"]    = socket.gethostname()
        info["user"]        = getpass.getuser()
        info["pid"]         = os.getpid()
        info["cwd"]         = os.getcwd()
        info["python"]      = platform.python_version()
        info["executable"]  = sys.executable

        # ── OS ────────────────────────────────────────────────────────────────
        info["os_system"]   = platform.system()
        info["os_release"]  = platform.release()
        info["os_version"]  = platform.version()
        info["os_machine"]  = platform.machine()
        info["os_node"]     = platform.node()

        # ── CPU ───────────────────────────────────────────────────────────────
        info["cpu_count_logical"] = os.cpu_count() or 0
        # Physical core count via /proc/cpuinfo on Linux; graceful fallback.
        try:
            with open("/proc/cpuinfo") as _f:
                cpuinfo = _f.read()
            physical = len({line.split(":")[1].strip()
                            for line in cpuinfo.splitlines()
                            if "physical id" in line}) or 1
            cores_per = max({line.split(":")[1].strip()
                             for line in cpuinfo.splitlines()
                             if "cpu cores" in line}, default="?")
            info["cpu_physical_packages"] = physical
            info["cpu_cores_per_package"] = cores_per
            model_line = next((l for l in cpuinfo.splitlines() if "model name" in l), "")
            info["cpu_model"] = model_line.split(":")[-1].strip() if model_line else "unknown"
        except (OSError, StopIteration):
            info["cpu_model"] = platform.processor() or "unknown"

        # ── Memory (Linux /proc/meminfo; fallback Windows ctypes) ─────────────
        try:
            meminfo = {}
            with open("/proc/meminfo") as _mf:
              for line in _mf:
                parts = line.split()
                if len(parts) >= 2:
                    meminfo[parts[0].rstrip(":")] = int(parts[1])
            info["mem_total_mb"]     = meminfo.get("MemTotal", 0) // 1024
            info["mem_free_mb"]      = meminfo.get("MemFree", 0) // 1024
            info["mem_available_mb"] = meminfo.get("MemAvailable", 0) // 1024
            info["swap_total_mb"]    = meminfo.get("SwapTotal", 0) // 1024
        except OSError:
            if platform.system() == "Windows":
                import ctypes
                class _MEMSTATUS(ctypes.Structure):
                    _fields_ = [("dwLength", ctypes.c_ulong),
                                 ("dwMemoryLoad", ctypes.c_ulong),
                                 ("ullTotalPhys", ctypes.c_ulonglong),
                                 ("ullAvailPhys", ctypes.c_ulonglong),
                                 ("ullTotalPageFile", ctypes.c_ulonglong),
                                 ("ullAvailPageFile", ctypes.c_ulonglong),
                                 ("ullTotalVirtual", ctypes.c_ulonglong),
                                 ("ullAvailVirtual", ctypes.c_ulonglong),
                                 ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]
                ms = _MEMSTATUS()
                ms.dwLength = ctypes.sizeof(ms)
                ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(ms))
                info["mem_total_mb"]     = ms.ullTotalPhys // (1024 * 1024)
                info["mem_available_mb"] = ms.ullAvailPhys // (1024 * 1024)

        # ── Disk ──────────────────────────────────────────────────────────────
        try:
            st = os.statvfs("/")
            info["disk_total_gb"] = round(st.f_blocks * st.f_frsize / 1e9, 1)
            info["disk_free_gb"]  = round(st.f_bfree  * st.f_frsize / 1e9, 1)
        except (AttributeError, OSError):
            pass  # Windows statvfs not available — skip

        # ── Network interfaces ────────────────────────────────────────────────
        # Four methods tried in order; first success wins.
        #
        # 1. `ip -json addr`      Linux / WSL2 — richest output, no ioctl
        # 2. `ifconfig -a`        macOS / BSD  — parsed for inet/inet6 lines
        # 3. SIOCGIFCONF ioctl    Linux/macOS  — fallback when CLI tools absent
        # 4. socket.gethostbyname all platforms — last resort
        ifaces: dict[str, list[str]] = {}
        _sys = platform.system()

        # Method 1: `ip -json addr` (Linux, WSL2, most containers)
        if not ifaces and _sys == "Linux":
            try:
                _r = subprocess.run(
                    ["ip", "-json", "addr"], capture_output=True, text=True,
                    timeout=3, check=False, shell=False,
                )
                if _r.returncode == 0:
                    import json as _jn
                    for _entry in _jn.loads(_r.stdout):
                        _name = _entry.get("ifname", "?")
                        _addrs = [
                            _a["local"]
                            for _a in _entry.get("addr_info", [])
                            if _a.get("family") in ("inet", "inet6")
                        ]
                        if _addrs:
                            ifaces[_name] = _addrs
            except Exception:
                pass

        # Method 2: `ifconfig -a` (macOS / BSD — `ip` does not exist there)
        if not ifaces and _sys == "Darwin":
            try:
                _r = subprocess.run(
                    ["ifconfig", "-a"], capture_output=True, text=True,
                    timeout=3, check=False, shell=False,
                )
                if _r.returncode == 0:
                    _cur_iface = None
                    for _line in _r.stdout.splitlines():
                        # Interface header: "en0: flags=..."
                        if _line and not _line[0].isspace():
                            _cur_iface = _line.split(":")[0]
                        elif _cur_iface:
                            _parts = _line.split()
                            # "inet 192.168.1.2 netmask ..." or "inet6 fe80::..."
                            if len(_parts) >= 2 and _parts[0] in ("inet", "inet6"):
                                _addr = _parts[1].split("%")[0]  # strip scope-id
                                ifaces.setdefault(_cur_iface, []).append(_addr)
            except Exception:
                pass

        # Method 3: SIOCGIFCONF ioctl (Linux/macOS — requires fcntl, no Windows)
        if not ifaces:
            try:
                import fcntl as _fcntl, struct as _struct
                import array as _array
                _buf = _array.array("B", b"\0" * 1024)
                with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as _s:
                    _ifc = _struct.pack("iP", _buf.buffer_info()[1] * _buf.itemsize,
                                        _buf.buffer_info()[0])
                    _fcntl.ioctl(_s.fileno(), 0x8912, _ifc)  # SIOCGIFCONF
                    _total = _struct.unpack("i", _ifc[:4])[0]
                for _i in range(0, _total, 40):
                    _nm = (
                        _buf[_i:_i+16].tobytes()
                        .rstrip(b"\x00").decode("utf-8", "replace")
                        .split("\x00")[0]
                    )
                    _addr = socket.inet_ntoa(_buf[_i+20:_i+24].tobytes())
                    if _nm:
                        ifaces.setdefault(_nm, []).append(_addr)
            except Exception:
                pass

        # Method 4: hostname resolution — universal last resort (Windows included)
        if not ifaces:
            try:
                ifaces["primary"] = [socket.gethostbyname(socket.gethostname())]
            except Exception:
                ifaces["primary"] = ["unknown"]

        info["network_interfaces"] = ifaces

        # ── Environment (safe subset) ─────────────────────────────────────────
        safe_env_keys = {"PATH", "HOME", "USER", "SHELL", "LANG", "TERM",
                         "LOGNAME", "USERNAME", "COMPUTERNAME", "USERPROFILE"}
        info["env"] = {k: os.environ.get(k, "") for k in safe_env_keys if k in os.environ}

        # ── Uptime ────────────────────────────────────────────────────────────
        try:
            with open("/proc/uptime") as _uf:
                uptime_s = float(_uf.read().split()[0])
            h, m = divmod(int(uptime_s), 3600)
            info["uptime"] = f"{h}h {m // 60}m"
        except OSError:
            info["uptime"] = "unknown"

        return _json.dumps(info, ensure_ascii=False)

    if command == "shellcode":
        """Execute a pre-built binary from the agent's lab directory.

        Educational demonstration of remote shellcode execution in a C2 lab.

        The binary MUST reside in the agent's lab_dir (same sandbox as file
        transfers).  No absolute paths, no path traversal, no shell=True.
        The file must be marked executable.  Output is capped at 4 000 chars.
        Execution timeout: 10 seconds.

        Parameters
        ----------
        name : str
            Filename of the executable in lab_dir (e.g. 'hello_world').
        args : list[str], optional
            Arguments to pass to the executable (all must be plain strings,
            no shell metacharacters interpreted).
        """
        from shared.lab_transfer import workspace_file
        import stat as _stat

        name = parameters.get("name")
        if not isinstance(name, str) or not name:
            raise ValueError("shellcode requires 'name' (filename in lab_dir)")
        extra_args = parameters.get("args", [])
        if not isinstance(extra_args, list) or any(not isinstance(a, str) for a in extra_args):
            raise ValueError("shellcode 'args' must be a list of strings")

        binary_path = workspace_file(lab_dir, name)
        if not binary_path.exists():
            raise ValueError(f"shellcode binary {name!r} not found in lab directory")
        if not binary_path.is_file():
            raise ValueError(f"{name!r} is not a regular file")
        file_stat = binary_path.stat()
        # Must be owner-executable to run
        if not (file_stat.st_mode & (_stat.S_IXUSR | _stat.S_IXGRP | _stat.S_IXOTH)):
            raise ValueError(
                f"{name!r} is not executable — run 'chmod +x {binary_path}' on the agent side"
            )

        # Read the binary magic header to detect platform mismatches BEFORE
        # attempting execution.  This produces a clear diagnostic instead of
        # cryptic OS errors (Windows: OSError 193; Linux: Exec format error).
        #
        # Magic bytes reference:
        #   \x7fELF         Linux/POSIX ELF binary
        #   \xfe\xed\xfa\xce  macOS Mach-O 32-bit (little-endian)
        #   \xfe\xed\xfa\xcf  macOS Mach-O 64-bit (little-endian)
        #   MZ (0x4D5A)    Windows PE/COFF executable
        _header = b""
        try:
            with open(binary_path, "rb") as _fh:
                _header = _fh.read(4)
        except OSError:
            pass  # unreadable — let subprocess.run report the error naturally

        _sys = platform.system()
        _is_elf   = _header[:4] == b"\x7fELF"
        _is_macho = _header[:4] in (b"\xfe\xed\xfa\xce", b"\xfe\xed\xfa\xcf",
                                    b"\xce\xfa\xed\xfe", b"\xcf\xfa\xed\xfe")
        _is_pe    = _header[:2] == b"MZ"

        if _sys == "Windows" and _is_elf:
            raise ValueError(
                f"{binary_path.name!r} is a Linux ELF binary and cannot run on Windows. "
                "Upload a .exe or .bat compiled for Windows instead."
            )
        if _sys == "Windows" and _is_macho:
            raise ValueError(
                f"{binary_path.name!r} is a macOS Mach-O binary and cannot run on Windows. "
                "Upload a .exe or .bat compiled for Windows instead."
            )
        if _sys == "Linux" and _is_macho:
            raise ValueError(
                f"{binary_path.name!r} is a macOS Mach-O binary and cannot run on Linux. "
                "Upload an ELF binary compiled for Linux instead."
            )
        if _sys == "Darwin" and _is_elf:
            raise ValueError(
                f"{binary_path.name!r} is a Linux ELF binary and cannot run on macOS. "
                "Upload a Mach-O binary compiled for macOS instead."
            )

        try:
            completed = subprocess.run(
                [str(binary_path)] + extra_args,
                capture_output=True, text=True,
                timeout=10, check=False, shell=False,
                cwd=str(binary_path.parent),  # run in the lab directory
            )
        except subprocess.TimeoutExpired:
            raise ValueError(f"shellcode execution timed out after 10 seconds")
        except OSError as exc:
            raise ValueError(f"shellcode execution failed: {exc}") from exc

        output = (completed.stdout or "") + (completed.stderr or "")
        result = {
            "returncode": completed.returncode,
            "output": output.strip()[:4000],
        }
        import json as _json
        return _json.dumps(result)

    if command == "shell":
        requested = parameters.get("command")
        # SHELL_COMMANDS is platform-aware: Linux uses pwd/whoami/uname -a;
        # Windows uses cmd builtins and whoami.  See shared/platform_compat.py.
        fixed_commands = SHELL_COMMANDS
        if not isinstance(requested, str) or requested not in fixed_commands:
            raise ValueError("shell command must be one of: pwd, whoami, uname")
        try:
            completed = subprocess.run(
                fixed_commands[requested], capture_output=True, text=True,
                timeout=3, check=False, shell=False,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise ValueError(f"read-only command failed: {exc}") from exc
        output = (completed.stdout or completed.stderr).strip()
        if completed.returncode != 0:
            raise ValueError(f"command exited {completed.returncode}: {output}")
        return output[:4000]

    if command == "self_remove":
        if parameters:
            raise ValueError("self_remove accepts no parameters")
        # Attempt to remove the installed agent files if the agent is running
        # from a recognised pa-agent-lab-* installation directory.  Uses the
        # same manifest-verified uninstall path as:
        #   python -m agent.local_install uninstall --execute
        # so no arbitrary files can be deleted.
        #
        # If the agent is running from the project source tree (not an installed
        # copy), or if the installation directory contains unrecognised files,
        # the uninstall is skipped and the agent simply stops — same as before.
        removed_files: list = []
        skip_reason = ""
        try:
            from agent.local_install import (
                uninstall, InstallationError, ALLOWED_INSTALL_ROOT, MANIFEST_NAME,
            )
            # The agent file is at agent/main.py; the install root is two levels up.
            candidate_root = Path(__file__).resolve().parent.parent
            if not ALLOWED_INSTALL_ROOT.fullmatch(candidate_root.name):
                skip_reason = f"not a pa-agent-lab-* directory ({candidate_root.name})"
            elif not (candidate_root / MANIFEST_NAME).is_file():
                skip_reason = "no installation manifest found"
            else:
                # Dry-run first — raises InstallationError on any safety failure.
                uninstall(candidate_root, execute=False)
                # All checks passed; perform the real deletion.
                removed_files = uninstall(candidate_root, execute=True)
        except ImportError:
            skip_reason = "local_install module not available"
        except Exception as exc:
            skip_reason = f"uninstall blocked: {exc}"

        if removed_files:
            summary = ", ".join(removed_files[:5])
            if len(removed_files) > 5:
                summary += f" … (+{len(removed_files) - 5} more)"
            return (
                f"Agent decommissioned: process stopping, runtime marker removed, "
                f"installation deleted ({len(removed_files)} files: {summary})."
            )
        return (
            f"Agent stopping: process will exit and runtime marker will be removed. "
            f"Installed files were NOT deleted ({skip_reason or 'source-tree run'})."
        )

    # Both transfer operations are strictly confined to this agent's lab_dir.
    # No path inputs, shell invocations, or reads outside the directory.
    if command == "upload":
        import json
        saved = write_lab_file(lab_dir, parameters)
        return json.dumps({"operation": "upload", **saved})

    if command == "download":
        import json
        if set(parameters) != {"name"}:
            raise ValueError("download requires only the lab filename")
        return json.dumps(read_lab_file(lab_dir, parameters["name"]))

    if command == "persist":
        # Install a user-scope OS startup entry so the agent survives reboots.
        # The exact arguments forwarded to the startup entry are taken from
        # parameters["agent_args"] (a list of strings); if absent, a minimal
        # default is used.  Only Linux (systemd) and Windows (Task Scheduler)
        # are supported; other platforms return a FAILED result.
        try:
            from agent.persistence import install_startup
            fwd_args = parameters.get("agent_args", [])
            if not isinstance(fwd_args, list) or any(not isinstance(a, str) for a in fwd_args):
                raise ValueError("agent_args must be a list of strings")
            result_msg = install_startup(fwd_args)
            return result_msg
        except NotImplementedError as exc:
            raise ValueError(str(exc)) from exc

    if command == "unpersist":
        # Remove the OS startup entry installed by a previous 'persist' task.
        try:
            from agent.persistence import remove_startup
            return remove_startup()
        except NotImplementedError as exc:
            raise ValueError(str(exc)) from exc

    raise ValueError(
        "unsupported command; allowed: "
        "echo, get_info, sysinfo, shell, shellcode, "
        "upload, download, self_remove, persist, unpersist"
    )


# ── Main async entry point ────────────────────────────────────────────────────

async def run(args) -> None:
    """Reconnect after established TLS disconnects with bounded attempts.

    The process keeps the same agent_id, but the server creates a new session_id
    for each TLS connection.  No in-flight task is replayed by the agent.
    """
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    agent_cert = getattr(args, "agent_cert", None)
    agent_key  = getattr(args, "agent_key", None)
    # build_agent_context wraps ssl.create_default_context and optionally loads
    # the agent's own certificate for mutual TLS.  Falls back to server-auth-only
    # mode when no agent_cert/agent_key are supplied (backward-compatible).
    context = build_agent_context(
        args.ca,
        agent_cert=agent_cert,
        agent_key=agent_key,
    )
    if agent_cert:
        LOG.info("mTLS: using agent certificate %s", agent_cert)
    agent_id = args.agent_id or str(uuid.uuid4())

    # Legacy test Namespaces omit reconnection settings and retain the former
    # one-session behavior; the interactive CLI enables bounded reconnection.
    reconnect_sessions = getattr(args, "reconnect_sessions", 0)
    reconnect_attempts = getattr(args, "reconnect_attempts", 6)
    max_delay = getattr(args, "reconnect_max_delay", 8.0)

    # A temporary, uniquely named state file is the *only* file owned by this
    # lifecycle demonstration. It is removed on graceful decommission and on
    # ordinary process exit; agent source and uploaded/downloaded lab files stay.
    lab_dir = getattr(args, "lab_dir", "data/agent_files")
    runtime_marker = _create_runtime_marker(lab_dir, agent_id)
    LOG.info("lab runtime marker created: %s", runtime_marker)
    try:
        await _connection_lifecycle(args, context, agent_id, reconnect_sessions,
                                    reconnect_attempts, max_delay)
    finally:
        runtime_marker.unlink(missing_ok=True)
        LOG.info("lab runtime marker removed: %s", runtime_marker)


async def _connection_lifecycle(args, context, agent_id,
                                reconnect_sessions, reconnect_attempts, max_delay):
    """Manage the full connection lifecycle: initial connect + bounded reconnection.

    Opens up to ``reconnect_sessions + 1`` successive TLS sessions.  The first
    session uses 10 dial attempts (to survive server cold-start); subsequent
    sessions use ``reconnect_attempts``.  Between sessions a short sleep prevents
    hammering a server that closed the connection cleanly.

    Returns when the reconnection budget is exhausted, when the agent is
    decommissioned (self_remove returned True), or when the initial connection
    fails after all attempts.
    """
    for session_number in range(reconnect_sessions + 1):
        max_attempts = 10 if session_number == 0 else reconnect_attempts
        for attempt in range(1, max_attempts + 1):
            try:
                # Must match the server's limit so readline() can handle
                # messages containing Base64-encoded 128 KiB files (~175 KiB).
                reader, writer = await asyncio.open_connection(
                    args.server, args.port, ssl=context,
                    server_hostname=args.server,
                    limit=4 * 1024 * 1024,  # 4 MiB — matches server limit
                )
                LOG.info("connected to %s:%s (attempt %d, connection %d)",
                         args.server, args.port, attempt, session_number + 1)
                break
            except (OSError, ssl.SSLError) as exc:
                if attempt == max_attempts:
                    if session_number == 0:
                        raise SystemExit(f"Agent connection failed after {attempt} attempts: {exc}")
                    LOG.error("reconnection abandoned after %d attempts: %s", attempt, exc)
                    return
                delay = min(max_delay, 0.5 * (2 ** min(attempt - 1, 8)))
                LOG.warning("connection attempt %d failed (%s) — retrying in %.1fs",
                            attempt, exc, delay)
                await asyncio.sleep(delay)

        try:
            decommissioned = await _run_session(args, reader, writer, agent_id)
            if decommissioned:
                LOG.info("agent decommissioned after final result; no automatic reconnect")
                return
        except (OSError, ConnectionError, ssl.SSLError, asyncio.IncompleteReadError) as exc:
            LOG.warning("established session interrupted: %s", exc)
        if session_number >= reconnect_sessions:
            LOG.info("agent stopped: reconnection session limit reached")
            return
        LOG.info("TLS connection ended; starting a fresh registered session")
        await asyncio.sleep(min(max_delay, 0.5))


async def _run_session(args, reader, writer, agent_id: str) -> bool:
    """Register, synchronize and run one TLS session; return True on decommission."""
    # ── Phase 1b: open durable local state store ──────────────────────────────
    # AgentLocalState persists pending_results across agent crashes so that
    # task_ids are accurately reported in SYNC_STATE on the next reconnect.
    _lab_dir_root = getattr(args, "lab_dir", "data/agent_files")
    local_state = AgentLocalState(_lab_dir_root)
    await local_state.open()
    # Restore pending results from the previous session (if agent crashed)
    _restored = await local_state.list_pending_results()
    if _restored:
        LOG.info(
            "restored %d pending result(s) from local state",
            len(_restored),
        )

    # ── Phase 2: registration ─────────────────────────────────────────────────
    # Use the provided agent-id (for deterministic test runs) or generate a
    # fresh UUID.  The UUID is not persisted; a new one is generated on each
    # invocation unless --agent-id is given.
    session_id = None  # filled in once REGISTER_ACK arrives

    # Send REGISTER immediately after the TLS handshake.  The server will not
    # process any other message type until it has seen REGISTER.
    await write_message(writer, make_message(
        "REGISTER", agent_id=agent_id,
        payload={
            "agent_id": agent_id,
            "hostname": platform.node(),       # e.g. "mybox.local"
            "platform": platform_summary(),    # platform-aware: includes WSL2 detection
        },
    ))

    # Periodic, observable heartbeat. Scheduling is intentionally independent
    # of task delivery, so a quiet connection remains visible in server logs.
    heartbeat_task = None

    async def heartbeat_loop():
        """Send a periodic BEACON every beacon_interval ± beacon_jitter seconds.

        Scheduled independently of task execution so a busy agent still sends
        heartbeats.  Cancelled in the finally block when the session ends.
        """
        while True:
            delay = args.beacon_interval + random.uniform(-args.beacon_jitter, args.beacon_jitter)
            await asyncio.sleep(delay)
            # Report the real activity state, not a hardcoded IDLE.
            # 'activity' is the dict defined in the enclosing _run_session scope.
            current_state = activity["state"]
            current_task  = activity.get("task_id")
            beacon_payload: dict = {"activity_state": current_state}
            if current_task:
                beacon_payload["running_task_id"] = current_task
            await write_message(writer, make_message(
                "BEACON", agent_id=agent_id, session_id=session_id,
                payload=beacon_payload,
            ))
            LOG.info("periodic BEACON sent session=%s state=%s", session_id, current_state)

    # ── Phase 3: message loop ─────────────────────────────────────────────────
    # Shared mutable state: heartbeat_loop reads this to report the real state.
    # States (aligned with the architectural spec):
    #   "SYNCHRONIZING" — REGISTER_ACK received, waiting for SYNC_COMPLETE
    #   "ONLINE"        — SYNC_COMPLETE received, ready for tasks (transitional)
    #   "IDLE"          — active session, no task running
    #   "BUSY"          — actively executing a task (task_id recorded)
    #   "DEGRADED"      — queue full or repeated message errors (still connected)
    # (CONNECTING and DISCONNECTED are handled in _connection_lifecycle)
    activity: dict = {"state": "SYNCHRONIZING", "task_id": None}

    # Agent-side task tracking for accurate SYNC_STATE.
    # task_id → "RUNNING" | "COMPLETED" (pending result delivery)
    # This lets the agent report genuine in-flight tasks instead of always
    # sending empty lists.  The agent does not persist this across restarts
    # (no local DB), so this only covers the current session.
    _agent_tasks: dict[str, str] = {}  # task_id → state
    # Seed from durable store so reconnect SYNC_STATE is accurate
    _pending_results: list[str] = [r["task_id"] for r in _restored]

    # ── B2: Concurrent task queue ─────────────────────────────────────────────
    # Tasks are accepted (ACK'd) immediately so the server sees QUEUED quickly,
    # but executed serially in a background worker so the message loop stays
    # free to handle PING, BEACON, and STATUS_QUERY while a task runs.
    # Capacity: up to 8 tasks queued without back-pressure; a 9th would block
    # the message loop, so we use a large-enough buffer for lab use.
    _task_queue: asyncio.Queue = asyncio.Queue(maxsize=8)
    # Shared flag set by the worker when self_remove completes so the session
    # return value is True and _connection_lifecycle skips reconnection.
    _decommission_flag: dict = {"value": False}

    async def _task_worker() -> None:
        """Background coroutine: pull tasks from _task_queue and execute them."""
        while True:
            item = await _task_queue.get()
            if item is None:
                # Sentinel: shut down the worker
                break
            p_w, task_id_w, command_w = item
            _lab_dir_w = getattr(args, "lab_dir", "data/agent_files")
            _params_w  = p_w.get("parameters", {})
            activity["state"]   = "BUSY"
            activity["task_id"] = task_id_w
            try:
                output_w = await asyncio.to_thread(
                    execute_allowed, command_w, _params_w, lab_dir=_lab_dir_w
                )
                status_w = "COMPLETED"
            except Exception as exc_w:
                output_w, status_w = str(exc_w), "FAILED"
            finally:
                activity["state"]   = "IDLE"
                activity["task_id"] = None

            LOG.info(
                "task completed task_id=%s status=%s output_len=%d",
                task_id_w, status_w, len(str(output_w)),
            )
            _agent_tasks.pop(task_id_w, None)
            _result_id_w = str(uuid.uuid4())
            _pending_results.append(task_id_w)
            # Persist before sending so a crash after send is recoverable
            await local_state.add_pending_result(
                task_id_w, _result_id_w, command_w, str(output_w), status_w
            )
            try:
                await write_message(writer, make_message(
                    "RESULT", agent_id=agent_id, session_id=session_id,
                    payload={
                        "task_id":   task_id_w,
                        "result_id": _result_id_w,
                        "status":    status_w,
                        "output":    output_w,
                    },
                ))
            except Exception as exc_send:
                LOG.warning("failed to send RESULT task_id=%s: %s", task_id_w, exc_send)
            if command_w == "self_remove" and status_w == "COMPLETED":
                LOG.info("self_remove requested: stopping agent after final result")
                _decommission_flag["value"] = True
                writer.close()
            _task_queue.task_done()

    worker_task = asyncio.create_task(_task_worker())

    try:
        while True:
            try:
                msg = await read_message(reader)
            except (asyncio.IncompleteReadError, ConnectionError, OSError):
                # The server closed the connection — normal shutdown or network
                # drop.  Log and exit the loop; the finally block cleans up.
                LOG.info("server closed the connection — session ended")
                break

            kind = msg["type"]

            # ── REGISTER_ACK ──────────────────────────────────────────────────
            if kind == "REGISTER_ACK":
                # Server confirmed our identity and assigned a session UUID.
                session_id = msg["payload"].get("session_id")
                LOG.info("registered agent=%s session=%s", agent_id, session_id)
                # Immediately send SYNC_STATE so the server can reconcile any
                # tasks that were in-flight when we last disconnected.
                # The agent tracks in-flight tasks in _agent_tasks and unACK'd results
                # are always empty; the server handles reconciliation on its side.
                # Report actual in-flight tasks.  On first connection these are
                # always empty (no prior session state).  On reconnect they
                # reflect tasks that were received and started before the drop.
                await write_message(writer, make_message(
                    "SYNC_STATE", agent_id=agent_id, session_id=session_id,
                    payload={
                        "pending_task_ids":  list(_agent_tasks.keys()),
                        "pending_result_ids": list(_pending_results),
                    },
                ))

            # ── SYNC_STATE_RESPONSE ───────────────────────────────────────────
            elif kind == "SYNC_STATE_RESPONSE":
                # Intermediate acknowledgement from the server; nothing to do.
                # The session is not yet ready — we wait for SYNC_COMPLETE.
                continue

            # ── SYNC_COMPLETE ─────────────────────────────────────────────────
            elif kind == "SYNC_COMPLETE":
                # The server has finished reconciling state and the session is
                # ready to receive tasks.  Note: the server does not perform
                # any actual reconciliation (it just cancels stuck tasks on its
                # side); the agent cannot rely on old tasks being re-delivered.
                LOG.info("session ready — SYNC_COMPLETE received, server cancelled any stuck tasks")
                activity["state"] = "ONLINE"   # transitional: SYNC_COMPLETE received
                # Send the first BEACON, then transition to IDLE
                activity["state"] = "IDLE"
                await write_message(writer, make_message(
                    "BEACON", agent_id=agent_id, session_id=session_id,
                    payload={"activity_state": "IDLE"},
                ))
                if heartbeat_task is None:
                    heartbeat_task = asyncio.create_task(heartbeat_loop())

            # ── TASK ──────────────────────────────────────────────────────────
            elif kind == "TASK":
                p       = msg["payload"]
                task_id = p.get("task_id")
                command = p.get("command", "")
                LOG.info("task received task_id=%s command=%s", task_id, command)
                _agent_tasks[task_id] = "RUNNING"

                # Step 1: acknowledge receipt immediately so the server
                # transitions from WAITING_ACK → QUEUED without delay.
                await write_message(writer, make_message(
                    "TASK_ACK", agent_id=agent_id, session_id=session_id,
                    payload={"task_id": task_id},
                ))

                # Step 2: report RUNNING now.  The worker will execute the task
                # asynchronously; we inform the server eagerly so it transitions
                # QUEUED → RUNNING and the timeout watchdog starts.
                await write_message(writer, make_message(
                    "TASK_STATUS", agent_id=agent_id, session_id=session_id,
                    payload={"task_id": task_id, "status": "RUNNING"},
                ))

                # Step 3: enqueue for the background worker.
                # The message loop continues immediately and can handle PING,
                # BEACON_ACK, STATUS_QUERY, or a second TASK while this runs.
                try:
                    _task_queue.put_nowait((p, task_id, command))
                except asyncio.QueueFull:
                    # Queue full — reject this task rather than blocking the loop.
                    activity["state"] = "DEGRADED"
                    LOG.warning(
                        "task queue full, rejecting task_id=%s command=%s",
                        task_id, command,
                    )
                    _agent_tasks.pop(task_id, None)
                    await write_message(writer, make_message(
                        "RESULT", agent_id=agent_id, session_id=session_id,
                        payload={
                            "task_id":   task_id,
                            "result_id": str(uuid.uuid4()),
                            "status":    "FAILED",
                            "output":    "Agent task queue full — retry later",
                        },
                    ))
                    # Reset to IDLE so the next task can be accepted
                    if activity["state"] == "DEGRADED":
                        activity["state"] = "IDLE"

            # ── RESULT_ACK ────────────────────────────────────────────────────
            elif kind == "RESULT_ACK":
                # The server confirmed it persisted (accepted=True) or already
                # has (accepted=False, duplicate) the result for this task.
                # Either way, we can remove the task from the pending-result list
                # so SYNC_STATE no longer reports it as pending delivery.
                acked_task = msg["payload"].get("task_id")
                if acked_task in _pending_results:
                    _pending_results.remove(acked_task)
                    # Remove from durable store — result confirmed by server
                    await local_state.remove_pending_result(acked_task)
                    if msg["payload"].get("accepted", True):
                        LOG.debug(
                            "RESULT_ACK received task_id=%s — result confirmed persisted",
                            acked_task,
                        )
                    else:
                        LOG.warning(
                            "RESULT rejected by server task_id=%s reason=%s",
                            acked_task,
                            msg["payload"].get("reason", "unknown"),
                        )

            # ── TASK_STATUS_QUERY ─────────────────────────────────────────────
            elif kind == "TASK_STATUS_QUERY":
                # Server asks the agent for the current status of a specific
                # task, typically to resolve uncertain outcomes after a
                # reconnect or a server restart.
                # The agent replies with what it currently knows:
                #   - "RUNNING"   if the task is actively executing right now
                #   - "COMPLETED" if we finished but RESULT_ACK not yet received
                #   - "UNKNOWN"   if we have no record of this task
                p_tsq    = msg["payload"]
                queried_task = p_tsq.get("task_id")
                query_id     = p_tsq.get("query_id")   # correlation ID
                if queried_task in _agent_tasks:
                    known_status = _agent_tasks[queried_task]
                elif queried_task in _pending_results:
                    known_status = "COMPLETED"
                else:
                    known_status = "UNKNOWN"
                await write_message(writer, make_message(
                    "TASK_STATUS_RESPONSE", agent_id=agent_id, session_id=session_id,
                    payload={
                        "task_id":         queried_task,
                        "agent_status":    known_status,
                        "query_id":        query_id,
                        "running_tasks":   list(_agent_tasks.keys()),
                        "pending_results": list(_pending_results),
                    },
                ))
                LOG.debug(
                    "TASK_STATUS_QUERY task_id=%s → agent_status=%s",
                    queried_task, known_status,
                )

            # ── BEACON_ACK ────────────────────────────────────────────────────
            elif kind == "BEACON_ACK":
                # Server acknowledges the heartbeat — no action needed; the
                # server's touch_agent() has already refreshed last_seen.
                pass

            # ── PING ──────────────────────────────────────────────────────────
            elif kind == "PING":
                # Liveness probe from the server; reply immediately with the
                # message_id so the server can correlate the round-trip.
                await write_message(writer, make_message(
                    "PONG", agent_id=agent_id, session_id=session_id,
                    payload={"reply_to": msg["message_id"]},
                ))

            # ── ERROR ─────────────────────────────────────────────────────────
            elif kind == "ERROR":
                # Server-sent error notification.  Log it and continue — the
                # server uses ERROR for non-fatal issues (e.g. invalid message
                # before REGISTER).  It does not close the connection.
                LOG.warning("server error: %s", msg["payload"])

            # Unhandled message types are silently ignored so that future
            # server-side additions do not break older agent versions.

    finally:
        if heartbeat_task is not None:
            heartbeat_task.cancel()
            await asyncio.gather(heartbeat_task, return_exceptions=True)
        # Stop the background task worker: send sentinel None to the queue
        # so the worker exits cleanly rather than being cancelled mid-task.
        try:
            _task_queue.put_nowait(None)
        except asyncio.QueueFull:
            pass
        worker_task.cancel()
        await asyncio.gather(worker_task, return_exceptions=True)
        # Always close the writer, even if the loop exits due to an exception.
        # wait_closed() ensures the TLS close_notify is sent before the TCP
        # connection is torn down.
        writer.close()
        try:
            await writer.wait_closed()
        except (OSError, ConnectionError, ssl.SSLError):
            pass
        # Close the local state store; leave data in place so next session can
        # restore pending results.  Only clear on self_remove or clean shutdown.
        await local_state.close()

    return _decommission_flag["value"]


# ── CLI entry point ───────────────────────────────────────────────────────────

def main() -> None:
    """Entry point for ``python -m agent.main``.

    Parses command-line arguments and delegates to the async ``run()``
    coroutine via ``asyncio.run()``.
    """
    parser = argparse.ArgumentParser(description="Harmless lab Agent")
    parser.add_argument(
        "--server", default="127.0.0.1",
        help="C2 server address (default: 127.0.0.1)",
    )
    parser.add_argument(
        "--port", type=int, default=9443,
        help="C2 server port (default: 9443)",
    )
    parser.add_argument(
        "--ca", default="certs/server.crt",
        help="CA certificate for server TLS verification (default: certs/server.crt)",
    )
    parser.add_argument(
        "--agent-cert", default=None, metavar="PATH",
        help=(
            "Agent client certificate (PEM) for mutual TLS. "
            "Required when the server is started with --agent-ca. "
            "The CN of this certificate must match --agent-id. "
            "Generate with: python -m shared.mtls generate-lab-certs"
        ),
    )
    parser.add_argument(
        "--agent-key", default=None, metavar="PATH",
        help="Agent private key (PEM) corresponding to --agent-cert.",
    )
    parser.add_argument(
        "--agent-id", default=None,
        help=(
            "Fixed agent UUID (default: random UUID generated at startup). "
            "In mTLS mode this must match the CN of --agent-cert exactly."
        ),
    )
    parser.add_argument("--beacon-interval", type=float, default=30.0,
                        help="Visible heartbeat period in seconds (1–3600)")
    parser.add_argument("--beacon-jitter", type=float, default=0.0,
                        help="Bounded timing variation in seconds (0–min(interval/2, 300))")
    parser.add_argument("--lab-dir", default="data/agent_files",
                        help="Dedicated agent-side lab files directory (created on startup)")
    parser.add_argument("--reconnect-sessions", type=int, default=8,
                        help="Maximum fresh sessions after established disconnects (0–100)")
    parser.add_argument("--reconnect-attempts", type=int, default=6,
                        help="Dial attempts after each disconnect (1–20)")
    parser.add_argument("--reconnect-max-delay", type=float, default=8.0,
                        help="Maximum retry delay in seconds (0.1–30)")
    args = parser.parse_args()
    if bool(args.agent_cert) != bool(args.agent_key):
        parser.error("--agent-cert and --agent-key must be supplied together")
    if not (1 <= args.beacon_interval <= 3600):
        parser.error("--beacon-interval must be between 1 and 3600")
    if not (0 <= args.beacon_jitter <= min(args.beacon_interval / 2, 300)):
        parser.error("--beacon-jitter is outside the permitted range")
    if not 0 <= args.reconnect_sessions <= 100:
        parser.error("--reconnect-sessions must be between 0 and 100")
    if not 1 <= args.reconnect_attempts <= 20:
        parser.error("--reconnect-attempts must be between 1 and 20")
    if not 0.1 <= args.reconnect_max_delay <= 30:
        parser.error("--reconnect-max-delay must be between 0.1 and 30")
    from pathlib import Path
    Path(args.lab_dir).mkdir(parents=True, exist_ok=True)
    try:
        asyncio.run(run(args))
    except KeyboardInterrupt:
        pass  # Ctrl-C is a normal exit; no traceback needed


if __name__ == "__main__":
    main()
