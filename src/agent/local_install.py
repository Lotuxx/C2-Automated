"""Explicit, local-only installer/uninstaller for the disposable lab agent.

This module has no network interface and cannot be called by a C2 TASK.
It removes only its own dedicated, manifest-verified installation directory.
Data received by the agent must be kept in a separate laboratory data folder.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sys
import uuid
from pathlib import Path

PACKAGE_NAME = "pa-agent-lab"
MANIFEST_NAME = ".pa-agent-lab-install.json"
# Statically defined file list. Never accept manifest-supplied paths for deletion.
INSTALLED_FILES = (
    "agent/__init__.py",
    "agent/main.py",
    "agent/local_install.py",
    "shared/__init__.py",
    "shared/protocol.py",
    "shared/lab_transfer.py",
    "shared/mtls.py",
    "agent/persistence.py",
    "agent/local_state.py",
    "shared/platform_compat.py",
)
ALLOWED_DIRECTORIES = {"agent", "shared", "agent/__pycache__", "shared/__pycache__"}
ALLOWED_INSTALL_ROOT = re.compile(r"pa-agent-lab-[A-Za-z0-9_-]{1,48}\Z")
PY_CACHE_NAME = re.compile(r"(?P<module>[A-Za-z_][A-Za-z0-9_]*)\.cpython-\d+(?:\.opt-\d+)?\.pyc\Z")
APPROVED_CACHE_MODULES = {
    "agent/__pycache__": {"__init__", "main", "local_install", "persistence", "local_state"},
    "shared/__pycache__": {"__init__", "protocol", "lab_transfer", "mtls", "platform_compat"},
}


class InstallationError(ValueError):
    """An install/uninstall safety condition failed."""


def _validate_target(target: str | Path, *, existing: bool) -> Path:
    """Validate and resolve the installation target directory.

    Checks that the path name matches ALLOWED_INSTALL_ROOT, is not a symlink,
    and either already exists (``existing=True``) or does not yet exist
    (``existing=False``) depending on the caller's intent.

    Raises InstallationError on any violation.
    """
    raw = Path(target).expanduser().absolute()
    if not ALLOWED_INSTALL_ROOT.fullmatch(raw.name):
        raise InstallationError("installation folder name must begin with 'pa-agent-lab-'")
    if raw.is_symlink():
        raise InstallationError("installation directory must not be a symbolic link")
    if raw.parent.is_symlink():
        raise InstallationError("installation parent must not be a symbolic link")
    if existing:
        if not raw.is_dir():
            raise InstallationError("installation folder does not exist")
        # Only uninstall an installation physically at its specified location.
        if raw.resolve() != raw:
            raise InstallationError("installation folder has symlinked path components")
    else:
        if raw.exists() or raw.is_symlink():
            raise InstallationError("target must not already exist")
        if not raw.parent.is_dir():
            raise InstallationError("parent directory must already exist")
        if raw.parent.resolve() != raw.parent:
            raise InstallationError("installation parent has symlinked path components")
    return raw


def _source_root() -> Path:
    """Return the project source root (parent of the agent/ directory)."""
    return Path(__file__).resolve().parent.parent


def install(target: str | Path) -> Path:
    """Locally install a minimal working copy of the agent, no autostart."""
    root = _validate_target(target, existing=False)
    source = _source_root()
    for rel in INSTALLED_FILES:
        if not (source / rel).is_file():
            raise InstallationError(f"missing source file: {rel}")
    root.mkdir(mode=0o700)
    try:
        for rel in INSTALLED_FILES:
            dest = root / rel
            dest.parent.mkdir(exist_ok=True)
            shutil.copyfile(source / rel, dest)
            dest.chmod(0o600)
        manifest = {
            "application": PACKAGE_NAME,
            "format_version": 1,
            "installation_id": str(uuid.uuid4()),
            "target": str(root),
            "installed_files": list(INSTALLED_FILES),
            "scope": "local-user-disposable-lab",
            "autostart": False,
        }
        mpath = root / MANIFEST_NAME
        with mpath.open("x", encoding="utf-8") as handle:
            json.dump(manifest, handle, indent=2)
            handle.write("\n")
        mpath.chmod(0o600)
    except BaseException:
        # Only own files exist in a folder just created by this function.
        shutil.rmtree(root)
        raise
    return root


def _approved_paths(root: Path) -> tuple[list[Path], list[Path]]:
    """Return (files, directories) that are approved for deletion.

    Reads and validates the installation manifest, then walks the directory
    tree.  Raises InstallationError if any unknown file, directory, or
    symlink is found — the uninstall must never delete unrecognised content.
    """
    manifest_path = root / MANIFEST_NAME
    if manifest_path.is_symlink() or not manifest_path.is_file():
        raise InstallationError("installation manifest is missing or is a symlink")
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (ValueError, OSError) as exc:
        raise InstallationError("invalid installation manifest") from exc
    if (not isinstance(manifest, dict)
            or manifest.get("application") != PACKAGE_NAME
            or manifest.get("format_version") != 1
            or manifest.get("target") != str(root)
            or manifest.get("installed_files") != list(INSTALLED_FILES)):
        raise InstallationError("manifest does not match this installation")
    try:
        uuid.UUID(manifest["installation_id"])
    except (TypeError, KeyError, ValueError, AttributeError) as exc:
        raise InstallationError("invalid installation identifier") from exc

    known_files = set(INSTALLED_FILES) | {MANIFEST_NAME}
    files: list[Path] = []
    directories: list[Path] = []
    for directory, dirnames, filenames in os.walk(root, topdown=True, followlinks=False):
        folder = Path(directory)
        for name in dirnames:
            child = folder / name
            rel = child.relative_to(root).as_posix()
            if child.is_symlink() or rel not in ALLOWED_DIRECTORIES:
                raise InstallationError(f"unrecognized directory or symlink: {rel}")
            directories.append(child)
        for name in filenames:
            child = folder / name
            rel = child.relative_to(root).as_posix()
            if child.is_symlink() or not child.is_file():
                raise InstallationError(f"unexpected file type or symlink: {rel}")
            if rel not in known_files:
                parent = child.parent.relative_to(root).as_posix()
                cache_match = PY_CACHE_NAME.fullmatch(name)
                if (cache_match is None
                        or cache_match.group("module") not in APPROVED_CACHE_MODULES.get(parent, set())):
                    raise InstallationError(f"unknown file — will not delete: {rel}")
            files.append(child)
    for rel in known_files:
        if (root / rel) not in files:
            raise InstallationError(f"missing installed file: {rel}")
    return files, directories


def uninstall(target: str | Path, *, execute: bool = False) -> list[str]:
    """Preview or delete exactly the files installed by install().

    Unknown files, directories and symlinks cause a hard refusal.
    For safety this must be run from outside the installation directory.
    """
    root = _validate_target(target, existing=True)
    cwd = Path.cwd().resolve()
    if cwd == root or root in cwd.parents:
        raise InstallationError("change directory outside the installation before uninstalling")
    files, folders = _approved_paths(root)
    names = [p.relative_to(root).as_posix() for p in files]
    if not execute:
        return sorted(names)
    # Do not use a deletion helper script or a detached process. Remove files
    # only in the foreground with a local operator-initiated command.
    for file in files:
        file.unlink()
    for folder in sorted(folders, key=lambda p: len(p.parts), reverse=True):
        folder.rmdir()
    root.rmdir()
    return sorted(names)


def main(argv: list[str] | None = None) -> int:
    """Entry point for ``python -m agent.local_install install|uninstall``.

    Parses subcommands and delegates to install() or uninstall().
    Returns 0 on success, 2 on refusal.
    """
    parser = argparse.ArgumentParser(
        description="Local-only disposable lab agent installation lifecycle")
    sub = parser.add_subparsers(dest="action", required=True)
    for action in ("install", "uninstall"):
        p = sub.add_parser(action)
        p.add_argument("--target", required=True, help="absolute path to pa-agent-lab-... directory")
        if action == "uninstall":
            p.add_argument("--execute", action="store_true",
                           help="remove the verified installation after preview")
    args = parser.parse_args(argv)
    try:
        if args.action == "install":
            location = install(args.target)
            print(f"Installed disposable agent at {location}")
            print("No autostart, scheduled task, service or persistence was created.")
            print(f"Run from that directory: cd {location} && python -m agent.main ...")
        else:
            removed = uninstall(args.target, execute=args.execute)
            print("UNINSTALLED" if args.execute else "DRY RUN: would remove")
            for name in removed:
                print(f"  {name}")
            if not args.execute:
                print("Use --execute to confirm local deletion after stopping the agent.")
        return 0
    except (InstallationError, OSError) as exc:
        print(f"Refused: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
