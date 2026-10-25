"""Explicitly sandboxed file transfer for an authorized local lab.

Remote tasks can only access basename-only files in an operator-specified
workspace.  No absolute/relative paths, symlinks, directories, or
unrestricted filesystem reads/writes are supported.
"""
from __future__ import annotations

import base64
import binascii
import hashlib
import os
import re
import stat
from pathlib import Path

MAX_TRANSFER_BYTES = 128 * 1024
NAME_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,63}\Z")


def validate_name(name: str) -> str:
    """Validate that ``name`` is a safe, basename-only filename.

    Accepts 1–64 characters matching [A-Za-z0-9][A-Za-z0-9_.-]{0,63}.
    Rejects empty strings, ".", "..", any path separator, and any string
    not matching NAME_PATTERN.  Returns ``name`` unchanged on success.

    Raises
    ------
    ValueError
        If the name fails any validation check.
    """
    if not isinstance(name, str) or not NAME_PATTERN.fullmatch(name):
        raise ValueError("filename must be 1–64 simple ASCII characters (no path separators)")
    if name in {".", ".."}:
        raise ValueError("invalid filename")
    return name


def workspace_file(directory: str | Path, name: str) -> Path:
    """Resolve ``name`` to an absolute path inside ``directory`` safely.

    Verifies that the resolved path is a direct child of the lab root
    (no traversal), that the root itself is a real directory, and that
    ``name`` is not a symlink.  The resolved path may not exist yet —
    this is normal for write operations.

    Raises
    ------
    ValueError
        On traversal, missing directory, or symlink.
    """
    validate_name(name)
    root = Path(directory).resolve()
    if not root.is_dir():
        raise ValueError("configured lab directory does not exist")
    candidate = root / name
    if candidate.is_symlink():
        raise ValueError("symlinks are forbidden in transfer workspaces")
    if candidate.resolve().parent != root:
        raise ValueError("file is outside the lab workspace")
    return candidate


def read_lab_file(directory: str | Path, name: str) -> dict:
    """Return a validated and bounded base64 message payload."""
    path = workspace_file(directory, name)  # raises if symlink via workspace_file()
    # O_NOFOLLOW prevents TOCTOU symlink substitution between workspace_file()
    # and os.open() on Linux/macOS.  On Windows O_NOFOLLOW is absent (getattr
    # returns 0) so the flag is a no-op, but the is_symlink() check inside
    # workspace_file() still guards the pre-open symlink detection.
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    try:
        fd = os.open(path, flags)
    except OSError as exc:
        raise ValueError(f"cannot read lab file: {exc}") from exc
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_size > MAX_TRANSFER_BYTES:
            raise ValueError("only regular files up to 128 KiB are allowed")
        with os.fdopen(fd, "rb", closefd=False) as handle:
            data = handle.read(MAX_TRANSFER_BYTES + 1)
        if len(data) > MAX_TRANSFER_BYTES:
            raise ValueError("transfer exceeds 128 KiB")
    finally:
        os.close(fd)
    return {
        "name": name,
        "content_b64": base64.b64encode(data).decode("ascii"),
        "sha256": hashlib.sha256(data).hexdigest(),
        "bytes": len(data),
    }


def write_lab_file(directory: str | Path, payload: dict) -> dict:
    """Validate checksum and create exactly one new file without overwriting."""
    if not isinstance(payload, dict):
        raise ValueError("file payload must be an object")
    name = validate_name(payload.get("name"))
    path = workspace_file(directory, name)
    encoded = payload.get("content_b64")
    sha = payload.get("sha256")
    if not isinstance(encoded, str) or len(encoded) > 4 * ((MAX_TRANSFER_BYTES + 2) // 3):
        raise ValueError("invalid or excessive file content")
    try:
        data = base64.b64decode(encoded, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise ValueError("invalid base64 content") from exc
    if len(data) > MAX_TRANSFER_BYTES:
        raise ValueError("transfer exceeds 128 KiB")
    if not isinstance(sha, str) or hashlib.sha256(data).hexdigest() != sha:
        raise ValueError("SHA-256 integrity verification failed")
    if payload.get("bytes") != len(data):
        raise ValueError("declared file length mismatch")
    # O_CREAT|O_EXCL ensures atomic create-or-fail (no overwrite).
    # O_NOFOLLOW prevents TOCTOU symlink substitution on Linux/macOS;
    # on Windows the flag is absent but workspace_file() already checked is_symlink().
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    try:
        fd = os.open(path, flags, 0o600)
    except OSError as exc:
        raise ValueError(f"cannot create lab file (no overwrites): {exc}") from exc
    try:
        with os.fdopen(fd, "wb", closefd=False) as handle:
            handle.write(data)
    except Exception:
        try:
            path.unlink()
        except OSError:
            pass
        raise
    finally:
        os.close(fd)
    return {"name": name, "bytes": len(data), "sha256": sha}
