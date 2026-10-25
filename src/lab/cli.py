"""Visible, local-only demo commands in the server operator CLI."""
from __future__ import annotations
from pathlib import Path
from tempfile import gettempdir
from .features import transfer_file, beacon_schedule, simulate_persistence, simulate_self_removal

WORKSPACE = Path(gettempdir()) / "pa-c2-local-lab-demo"


def run_lab_command(args: list[str]) -> str:
    """Run local simulations; never dispatch network tasks or touch agent state."""
    command = args[0] if args else "help"
    if command == "help":
        output = ("LOCAL SIMULATION ONLY — no remote agent execution.\n"
                  "lab init | lab upload | lab download | lab beacon [interval jitter count] "
                  "| lab persist | lab self_destruct")
    else:
        server = WORKSPACE / "server_files"
        agent = WORKSPACE / "simulated_agent_files"
        try:
            if command == "init" and len(args) == 1:
                server.mkdir(parents=True, exist_ok=True)
                agent.mkdir(parents=True, exist_ok=True)
                (server / "sample.txt").write_text("C2 local demonstration sample\n", encoding="utf-8")
                output = f"Initialized LOCAL demo workspace: {WORKSPACE}"
            elif command == "upload" and len(args) == 1:
                output = f"LOCAL simulated upload: {transfer_file(server, agent, 'sample.txt')}"
            elif command == "download" and len(args) == 1:
                output = f"LOCAL simulated download: {transfer_file(agent, server, 'sample.txt')}"
            elif command == "beacon" and len(args) in (1, 4):
                interval, jitter, count = (10, 2, 5) if len(args) == 1 else (float(args[1]), float(args[2]), int(args[3]))
                output = f"LOCAL simulated check-in seconds: {beacon_schedule(interval, jitter, count)}"
            elif command == "persist" and len(args) == 1:
                output = f"LOCAL persistence MANIFEST ONLY: {simulate_persistence(agent)}"
            elif command == "self_destruct" and len(args) == 1:
                output = f"LOCAL manifest cleanup ONLY: {simulate_self_removal(agent)}"
            else:
                output = "Invalid lab command. Type 'lab help'."
        except (ValueError, OSError, TypeError) as exc:
            output = f"Local lab demo error: {exc}. Run 'lab init' first if necessary."
    print(output)
    return output
