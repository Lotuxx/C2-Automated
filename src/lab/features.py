
"""Local-only demonstrations of C2 assignment concepts.

These functions are deliberately not callable through the network agent.
They operate solely in a temporary workspace explicitly supplied by the user.
"""
from __future__ import annotations
import hashlib
import json
import random
import shutil
from pathlib import Path

MAX_BYTES = 1024 * 1024

def _safe_file(root: Path, filename: str) -> Path:
    if not isinstance(filename, str) or not filename or filename in (".", ".."):
        raise ValueError("invalid filename")
    if Path(filename).name != filename or "/" in filename or "\\" in filename:
        raise ValueError("paths and traversal are forbidden")
    root = root.resolve()
    if not root.is_dir():
        raise ValueError("workspace directory does not exist")
    target = (root / filename).resolve()
    if target.parent != root:
        raise ValueError("file escapes workspace")
    return target

def transfer_file(source_dir: Path, destination_dir: Path, filename: str) -> dict:
    """Demonstrate upload/download using two explicit local lab directories."""
    source = _safe_file(Path(source_dir), filename)
    destination = _safe_file(Path(destination_dir), filename)
    if not source.is_file() or source.is_symlink():
        raise ValueError("source must be a regular file")
    size = source.stat().st_size
    if size > MAX_BYTES:
        raise ValueError("file exceeds 1 MiB lab limit")
    data = source.read_bytes()
    if len(data) > MAX_BYTES:
        raise ValueError("file exceeds 1 MiB lab limit")
    destination.write_bytes(data)
    return {"name": filename, "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}

def beacon_schedule(interval: float, jitter: float, count: int, seed: int = 42) -> list[float]:
    """Return observable simulated check-in times; no network traffic."""
    if not (1 <= interval <= 3600 and 0 <= jitter <= min(interval / 2, 300)):
        raise ValueError("invalid interval/jitter")
    if not 1 <= count <= 100:
        raise ValueError("invalid count")
    rng = random.Random(seed)
    now = 0.0
    times = []
    for _ in range(count):
        now += interval + rng.uniform(-jitter, jitter)
        times.append(round(now, 3))
    return times

def simulate_persistence(workspace: Path) -> Path:
    """Write a visible lifecycle *manifest*, not an OS startup entry."""
    workspace = Path(workspace).resolve()
    if not workspace.is_dir():
        raise ValueError("workspace missing")
    manifest = workspace / "lab_lifecycle.json"
    if manifest.exists() or manifest.is_symlink():
        raise ValueError("manifest already exists")
    manifest.write_text(json.dumps({
        "type": "persistence_simulation",
        "startup_registration": "SIMULATED_ONLY",
        "description": "No service, cron job, or startup entry was installed."
    }, indent=2), encoding="utf-8")
    return manifest

def simulate_self_removal(workspace: Path) -> list[str]:
    """Remove only files this demo owns; never remove an arbitrary directory."""
    workspace = Path(workspace).resolve()
    manifest = workspace / "lab_lifecycle.json"
    if manifest.is_symlink() or not manifest.is_file():
        raise ValueError("no valid lab manifest")
    info = json.loads(manifest.read_text(encoding="utf-8"))
    if info.get("type") != "persistence_simulation":
        raise ValueError("unexpected manifest")
    manifest.unlink()
    return ["lab_lifecycle.json"]
