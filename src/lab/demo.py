
"""Run a fully local, disposable feature demonstration."""
from pathlib import Path
from tempfile import TemporaryDirectory
from .features import transfer_file, beacon_schedule, simulate_persistence, simulate_self_removal

def main():
    with TemporaryDirectory(prefix="pa-lab-demo-") as tmp:
        root = Path(tmp)
        c2, agent = root / "server_files", root / "agent_files"
        c2.mkdir()
        agent.mkdir()
        (c2 / "sample.txt").write_text("Sample data for isolated laboratory\n", encoding="utf-8")
        print("Upload:", transfer_file(c2, agent, "sample.txt"))
        print("Download:", transfer_file(agent, c2, "sample.txt"))
        print("Beacon times:", beacon_schedule(interval=10, jitter=2, count=5))
        print("Persistence simulation:", simulate_persistence(agent))
        print("Self-removal simulation:", simulate_self_removal(agent))
        print("All operations stayed inside a temporary local workspace.")

if __name__ == "__main__":
    main()
