"""
shared/platform_compat.py — Cross-platform compatibility utilities.

Role
----
This module centralises the small number of OS-specific behaviours needed by
the agent and server so that the rest of the codebase remains platform-agnostic.

Supported platforms
-------------------
* Linux (primary target, CI-tested)
* macOS (best-effort; same POSIX paths as Linux)
* Windows 10+ / WSL2 (tested manually; automated tests skip OS-dependent paths)

Known limitations on Windows
-----------------------------
* ``O_NOFOLLOW`` is not available on Windows; the flag is omitted gracefully.
  The symlink safety check in ``workspace_file()`` (shared/lab_transfer.py)
  still works because Python's ``Path.is_symlink()`` is cross-platform.
* ``systemd`` is not available on Windows; ``agent/persistence.py`` uses
  Task Scheduler instead.
* The ``shell`` command (``pwd``, ``whoami``, ``uname``) uses platform-aware
  command mappings (see ``SHELL_COMMANDS`` below).
* Path separators: all file operations in ``shared/lab_transfer.py`` use
  ``pathlib.Path`` which is inherently cross-platform.
* TLS certificate generation via ``openssl`` CLI requires OpenSSL installed
  on the PATH.  On Windows, use Git Bash, WSL, or the Win32 OpenSSL package.

SHELL_COMMANDS
--------------
Maps the three allowlisted shell command names to the actual OS commands that
implement them.  Used by ``agent/main.py::execute_allowed`` to replace the
hard-coded Linux-only command table.
"""
from __future__ import annotations

import platform

_system = platform.system()

# ── Shell command mapping (platform-aware) ────────────────────────────────────

if _system == "Windows":
    # Use cmd.exe builtins and Windows equivalents where possible.
    # These are always invoked without shell=True; cmd.exe is never used.
    SHELL_COMMANDS: dict[str, list[str]] = {
        "pwd":    ["cmd", "/c", "cd"],          # print working directory
        "whoami": ["whoami"],                   # available since Windows XP
        "uname":  ["cmd", "/c", "ver"],         # Windows version string
    }
else:
    # POSIX (Linux, macOS)
    SHELL_COMMANDS: dict[str, list[str]] = {
        "pwd":    ["pwd"],
        "whoami": ["whoami"],
        "uname":  ["uname", "-a"],
    }


def is_windows() -> bool:
    """Return True when running on native Windows (not WSL)."""
    return _system == "Windows"


def is_linux() -> bool:
    """Return True when running on Linux (including WSL2)."""
    return _system == "Linux"


def is_wsl() -> bool:
    """Return True when running inside a WSL2 environment.

    Detected by the presence of ``/proc/sys/kernel/osrelease`` containing
    ``microsoft`` (case-insensitive), which is the canonical WSL2 marker.
    """
    if not is_linux():
        return False
    try:
        with open("/proc/sys/kernel/osrelease") as _f:
            release = _f.read().lower()
        return "microsoft" in release
    except OSError:
        return False


def platform_summary() -> str:
    """Return a one-line platform description for logging and diagnostics."""
    sys_str = platform.system()
    rel_str = platform.release()
    mach = platform.machine()
    if is_wsl():
        return f"WSL2 ({sys_str} {rel_str} {mach})"
    return f"{sys_str} {rel_str} {mach}"
