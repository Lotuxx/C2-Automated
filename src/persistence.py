"""
agent/persistence.py — Cross-platform OS startup persistence for the lab agent.

Role
----
Installs and removes a USER-SCOPE startup entry so the agent process starts
automatically when the user logs in.  No root, sudo, or administrator
privilege is required or requested.

Supported platforms
-------------------
Linux (systemd user session)
    Unit file: ~/.config/systemd/user/pa-agent-lab.service
    Enabled with: systemctl --user enable pa-agent-lab.service
    Fallback: when systemd is unavailable (container, no D-Bus), the unit
    file is still written so it takes effect once systemd is available, and
    a clear warning is logged rather than raising an exception.

macOS (launchd per-user agent)
    Plist:    ~/Library/LaunchAgents/pa-agent-lab.plist
    Loaded with: launchctl load <plist>
    Removed with: launchctl unload <plist>; rm <plist>

Windows 10+ (Task Scheduler, current-user scope)
    Task name: PA-Agent-Lab
    Created with: schtasks /Create /SC ONLOGON /RL LIMITED
    The ProgramArguments are written via an XML task definition so that
    paths containing spaces are handled correctly without shell=True.

Other platforms
    install_startup() raises NotImplementedError.
    is_installed() returns False rather than raising.

Security design
---------------
* User scope only — no system-wide service, cron, or /etc/init.d entry.
* The started command is always exactly ``python -m agent.main`` with the
  arguments the operator supplies; no shell=True expansion, no glob.
* Unit/plist/task names are fixed constants so remove_startup() always
  finds what install_startup() created.
* Removal verifies the entry exists before deleting.
"""
from __future__ import annotations

import os
import platform
import shutil
import subprocess
import sys
import textwrap
import uuid
from pathlib import Path

# Fixed identifiers for the startup entry across all platforms.
UNIT_NAME  = "pa-agent-lab"            # systemd unit stem (Linux)
PLIST_LABEL = "com.pa-agent-lab"       # launchd label (macOS)
PLIST_NAME  = f"{PLIST_LABEL}.plist"   # filename in ~/Library/LaunchAgents/
TASK_NAME   = "PA-Agent-Lab"           # Task Scheduler name (Windows)


# ── Internal helpers ──────────────────────────────────────────────────────────

def _python() -> str:
    """Return the absolute path to the running Python interpreter."""
    return sys.executable


def _run(cmd: list[str], *, check: bool = True,
         capture: bool = True) -> subprocess.CompletedProcess:
    """Run a subprocess without shell=True; raise CalledProcessError on failure."""
    return subprocess.run(cmd, capture_output=capture, text=True,
                          check=check, shell=False)


def _working_dir() -> str:
    """Project root — the directory two levels above this file."""
    return str(Path(__file__).resolve().parent.parent)


# ── Linux / systemd ───────────────────────────────────────────────────────────

def _systemd_user_dir() -> Path:
    """Return ~/.config/systemd/user, creating it if it does not exist."""
    d = Path.home() / ".config" / "systemd" / "user"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _unit_file() -> Path:
    """Return the full path to the pa-agent-lab.service unit file."""
    return _systemd_user_dir() / f"{UNIT_NAME}.service"


def _install_linux(agent_args: list[str]) -> str:
    """Write the systemd user unit and attempt to enable it.

    When the D-Bus user session is unavailable (containers, headless servers)
    the systemctl enable step is attempted but failure is non-fatal: the unit
    file is in place and will be picked up when the user session starts.
    Returns a human-readable status string.
    """
    python = _python()
    exec_start = " ".join([python, "-m", "agent.main"] + agent_args)
    unit_content = textwrap.dedent(f"""\
        [Unit]
        Description=PA Lab C2 Agent (user-scope, disposable lab)
        After=network-online.target
        Wants=network-online.target

        [Service]
        Type=simple
        ExecStart={exec_start}
        WorkingDirectory={_working_dir()}
        Restart=on-failure
        RestartSec=5s
        StandardOutput=journal
        StandardError=journal

        [Install]
        WantedBy=default.target
    """)
    unit_path = _unit_file()
    unit_path.write_text(unit_content, encoding="utf-8")
    unit_path.chmod(0o600)

    systemctl_ok = False
    systemctl_msg = ""
    try:
        _run(["systemctl", "--user", "daemon-reload"])
        _run(["systemctl", "--user", "enable", f"{UNIT_NAME}.service"])
        systemctl_ok = True
    except (subprocess.CalledProcessError, FileNotFoundError) as exc:
        systemctl_msg = (
            f" (systemctl unavailable in this environment: {exc}; "
            f"unit file written — will activate when user session starts)"
        )

    status = "enabled" if systemctl_ok else "written (not yet enabled)"
    return (
        f"systemd user unit {status}: {unit_path}{systemctl_msg}\n"
        f"Start now:  systemctl --user start {UNIT_NAME}\n"
        f"View logs:  journalctl --user -u {UNIT_NAME} -f\n"
        f"Remove:     python -m agent.persistence remove"
    )


def _remove_linux() -> bool:
    """Disable and delete the systemd user unit. Returns True if it existed."""
    unit_path = _unit_file()
    if not unit_path.exists():
        return False
    for cmd in (
        ["systemctl", "--user", "stop",        f"{UNIT_NAME}.service"],
        ["systemctl", "--user", "disable",     f"{UNIT_NAME}.service"],
    ):
        try:
            _run(cmd, check=False)
        except FileNotFoundError:
            pass
    unit_path.unlink(missing_ok=True)
    try:
        _run(["systemctl", "--user", "daemon-reload"], check=False)
    except FileNotFoundError:
        pass
    return True


def _is_installed_linux() -> bool:
    """Return True when the systemd user unit file is present on disk."""
    return _unit_file().exists()


# ── macOS / launchd ───────────────────────────────────────────────────────────

def _launchd_dir() -> Path:
    """Return ~/Library/LaunchAgents, creating it if it does not exist."""
    d = Path.home() / "Library" / "LaunchAgents"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _plist_file() -> Path:
    """Return the full path to the pa-agent-lab launchd plist file."""
    return _launchd_dir() / PLIST_NAME


def _install_macos(agent_args: list[str]) -> str:
    """Write a launchd plist to ~/Library/LaunchAgents/ and load it.

    The plist uses a RunAtLoad key so the agent starts immediately on load
    and automatically after every login.  KeepAlive restarts it on crash.
    """
    python = _python()
    prog_args = [python, "-m", "agent.main"] + agent_args
    # Build ProgramArguments XML — one <string> per argument, no shell quoting needed.
    args_xml = "\n        ".join(f"<string>{a}</string>" for a in prog_args)
    plist_content = textwrap.dedent(f"""\
        <?xml version="1.0" encoding="UTF-8"?>
        <!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
            "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
        <plist version="1.0">
        <dict>
            <key>Label</key>
            <string>{PLIST_LABEL}</string>
            <key>ProgramArguments</key>
            <array>
                {args_xml}
            </array>
            <key>WorkingDirectory</key>
            <string>{_working_dir()}</string>
            <key>RunAtLoad</key>
            <true/>
            <key>KeepAlive</key>
            <dict>
                <key>SuccessfulExit</key>
                <false/>
            </dict>
            <key>StandardOutPath</key>
            <string>/tmp/pa-agent-lab.stdout.log</string>
            <key>StandardErrorPath</key>
            <string>/tmp/pa-agent-lab.stderr.log</string>
        </dict>
        </plist>
    """)
    plist_path = _plist_file()
    plist_path.write_text(plist_content, encoding="utf-8")
    plist_path.chmod(0o600)

    load_ok = False
    load_msg = ""
    try:
        _run(["launchctl", "load", str(plist_path)])
        load_ok = True
    except (subprocess.CalledProcessError, FileNotFoundError) as exc:
        load_msg = f" (launchctl load failed: {exc}; plist is in place)"

    return (
        f"launchd agent {'loaded and' if load_ok else 'written but not'} active: {plist_path}{load_msg}\n"
        f"View logs:  tail -f /tmp/pa-agent-lab.stdout.log\n"
        f"Remove:     python -m agent.persistence remove"
    )


def _remove_macos() -> bool:
    """Unload and delete the launchd plist. Returns True if it existed."""
    plist_path = _plist_file()
    if not plist_path.exists():
        return False
    try:
        _run(["launchctl", "unload", str(plist_path)], check=False)
    except FileNotFoundError:
        pass
    plist_path.unlink(missing_ok=True)
    return True


def _is_installed_macos() -> bool:
    """Return True when the launchd plist file is present on disk."""
    return _plist_file().exists()


# ── Windows / Task Scheduler ──────────────────────────────────────────────────

def _task_xml(agent_args: list[str]) -> str:
    """Generate a Task Scheduler XML definition.

    Using an XML file instead of /TR avoids all quoting issues with spaces
    in the Python executable path or in argument values.
    """
    python = _python()
    prog_args = [python, "-m", "agent.main"] + agent_args
    # Executable and arguments are separate in the XML so no quoting needed.
    executable = prog_args[0]
    arguments  = " ".join(prog_args[1:])
    working    = _working_dir()
    # A random GUID is required by the Task Scheduler XML schema.
    task_guid  = "{" + str(uuid.uuid4()).upper() + "}"
    return textwrap.dedent(f"""\
        <?xml version="1.0" encoding="UTF-16"?>
        <Task version="1.2"
              xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
          <RegistrationInfo>
            <Description>PA Lab C2 Agent (user-scope, disposable lab)</Description>
            <URI>\\{TASK_NAME}</URI>
          </RegistrationInfo>
          <Triggers>
            <LogonTrigger>
              <Enabled>true</Enabled>
              <UserId>{os.environ.get("USERNAME", "")}</UserId>
            </LogonTrigger>
          </Triggers>
          <Principals>
            <Principal id="Author">
              <LogonType>InteractiveToken</LogonType>
              <RunLevel>LeastPrivilege</RunLevel>
            </Principal>
          </Principals>
          <Settings>
            <MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>
            <DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>
            <StopIfGoingOnBatteries>false</StopIfGoingOnBatteries>
            <ExecutionTimeLimit>PT0S</ExecutionTimeLimit>
            <RestartOnFailure>
              <Interval>PT1M</Interval>
              <Count>10</Count>
            </RestartOnFailure>
          </Settings>
          <Actions Context="Author">
            <Exec>
              <Command>{executable}</Command>
              <Arguments>{arguments}</Arguments>
              <WorkingDirectory>{working}</WorkingDirectory>
            </Exec>
          </Actions>
        </Task>
    """)


def _install_windows(agent_args: list[str]) -> str:
    """Create a Task Scheduler task using an XML definition file.

    The XML approach avoids all /TR quoting problems with spaces in paths.
    """
    import tempfile
    xml = _task_xml(agent_args)
    # Task Scheduler requires UTF-16 LE for the /XML flag.
    with tempfile.NamedTemporaryFile(
        mode="w", encoding="utf-16-le", suffix=".xml", delete=False
    ) as f:
        f.write(xml)
        xml_path = f.name
    try:
        _run([
            "schtasks", "/Create",
            "/TN", TASK_NAME,
            "/XML", xml_path,
            "/F",   # overwrite if already exists
        ])
    finally:
        try:
            os.unlink(xml_path)
        except OSError:
            pass
    return (
        f"Task Scheduler task created: {TASK_NAME}\n"
        f"View:   schtasks /Query /TN {TASK_NAME} /V /FO LIST\n"
        f"Remove: python -m agent.persistence remove"
    )


def _remove_windows() -> bool:
    """Delete the Task Scheduler task. Returns True if it existed."""
    result = _run(["schtasks", "/Query", "/TN", TASK_NAME], check=False)
    if result.returncode != 0:
        return False
    _run(["schtasks", "/Delete", "/TN", TASK_NAME, "/F"])
    return True


def _is_installed_windows() -> bool:
    """Return True when the Task Scheduler task exists for the current user."""
    result = _run(["schtasks", "/Query", "/TN", TASK_NAME], check=False)
    return result.returncode == 0


# ── Public API ────────────────────────────────────────────────────────────────

def install_startup(agent_args: list[str] | None = None) -> str:
    """Install a user-scope OS startup entry for the lab agent.

    Parameters
    ----------
    agent_args : list[str] or None
        Extra command-line arguments passed to ``python -m agent.main``
        at startup (e.g. ``["--server", "10.0.0.1", "--ca", "certs/server.crt",
        "--agent-id", "lab-agent-01"]``).  Must not contain shell metacharacters.

    Returns
    -------
    str
        Human-readable description of what was installed and how to manage it.

    Raises
    ------
    NotImplementedError
        On platforms other than Linux, macOS, and Windows.
    OSError / subprocess.CalledProcessError
        If a required OS command fails fatally.
    """
    args = list(agent_args or [])
    system = platform.system()
    if system == "Linux":
        return _install_linux(args)
    if system == "Darwin":
        return _install_macos(args)
    if system == "Windows":
        return _install_windows(args)
    raise NotImplementedError(
        f"OS startup persistence is not implemented for {system}. "
        "Supported: Linux (systemd user unit), macOS (launchd plist), "
        "Windows (Task Scheduler logon task)."
    )


def remove_startup() -> str:
    """Remove the startup entry installed by install_startup().

    Returns
    -------
    str
        Human-readable confirmation of what was removed.

    Raises
    ------
    NotImplementedError
        On unsupported platforms.
    """
    system = platform.system()
    if system == "Linux":
        removed = _remove_linux()
        return (f"systemd unit removed: {_unit_file()}" if removed
                else "No startup unit found.")
    if system == "Darwin":
        removed = _remove_macos()
        return (f"launchd plist removed: {_plist_file()}" if removed
                else "No startup plist found.")
    if system == "Windows":
        removed = _remove_windows()
        return (f"Task Scheduler task removed: {TASK_NAME}" if removed
                else "No startup task found.")
    raise NotImplementedError(
        f"Startup removal not implemented for {system}."
    )


def is_installed() -> bool:
    """Return True if a startup entry is currently registered.

    Returns False on unsupported platforms (not True, not an exception)
    so callers can poll this without platform guards.
    """
    system = platform.system()
    if system == "Linux":
        return _is_installed_linux()
    if system == "Darwin":
        return _is_installed_macos()
    if system == "Windows":
        return _is_installed_windows()
    return False


# ── CLI entry point ───────────────────────────────────────────────────────────

def main(argv: list[str] | None = None) -> int:
    """Manage OS startup persistence from the command line.

    Usage
    -----
    python -m agent.persistence install [agent args…]
    python -m agent.persistence remove
    python -m agent.persistence status
    """
    import argparse
    parser = argparse.ArgumentParser(
        description=(
            "User-scope OS startup persistence for the lab agent. "
            "Supports Linux (systemd), macOS (launchd), Windows (Task Scheduler). "
            "No root/admin privilege required."
        )
    )
    sub = parser.add_subparsers(dest="action", required=True)
    inst = sub.add_parser("install", help="Install a startup entry")
    inst.add_argument(
        "agent_args", nargs="*",
        help="Arguments forwarded to python -m agent.main"
    )
    sub.add_parser("remove", help="Remove the startup entry")
    sub.add_parser("status", help="Check whether a startup entry is installed")

    args = parser.parse_args(argv)
    try:
        if args.action == "install":
            print(install_startup(args.agent_args))
        elif args.action == "remove":
            print(remove_startup())
        elif args.action == "status":
            installed = is_installed()
            print(f"Startup entry installed: {installed}")
            if not installed:
                print("Run 'python -m agent.persistence install' to create one.")
        return 0
    except NotImplementedError as exc:
        print(f"Not supported on this platform: {exc}", file=sys.stderr)
        return 2
    except (OSError, subprocess.CalledProcessError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
