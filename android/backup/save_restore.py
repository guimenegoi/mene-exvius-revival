"""Fail-closed, offline-only FFBE save restore core (NOT wired into the APK).

Never call from the running Revival engine. An Android lifecycle controller must
guarantee exclusive access and invoke recover_pending() before starting the
engine. This module intentionally exposes no HTTP endpoint or auto-restore.
"""
from __future__ import annotations

import fcntl
import hashlib
import hmac
import io
import json
import os
import re
import secrets
import shutil
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

try:  # Android packaging uses this alias for the shared backup transport.
    import ffbe_backup_transport as backup
except ModuleNotFoundError:
    import lxc_backup as backup

SHA256 = re.compile(r"[a-f0-9]{64}\Z")
JOURNAL = "pending-restore.json"
LOCK = ".restore.lock"


def inspect_archive(data: bytes, expected_sha256: str) -> dict:
    """Verify bytes and per-file hashes before allowing a restore."""
    if not isinstance(expected_sha256, str) or not SHA256.fullmatch(expected_sha256):
        raise ValueError("Expected SHA-256 is required")
    digest = hashlib.sha256(data).hexdigest()
    if not hmac.compare_digest(expected_sha256, digest):
        raise ValueError("Archive SHA-256 mismatch")
    names = backup.validate(data)  # ZIP boundaries, manifest, JSON and hashes
    return {
        "sha256": digest,
        "files": names,
        "bytes": len(data),
        "confirmation": "RESTAURAR " + digest[:12],
    }


def _fsync_dir(path: Path) -> None:
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _private_file(path: Path, content: bytes) -> None:
    if path.is_symlink():
        raise ValueError("Refusing symlink file")
    fd, temp = tempfile.mkstemp(prefix=".restore-write-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as output:
            os.fchmod(output.fileno(), 0o600)
            output.write(content)
            output.flush()
            os.fsync(output.fileno())
        os.replace(temp, path)
        _fsync_dir(path.parent)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)


def _roots(state_dir: Path, recovery_dir: Path) -> tuple[Path, Path]:
    state_dir, recovery_dir = Path(state_dir), Path(recovery_dir)
    if (state_dir.is_symlink() or state_dir.parent.is_symlink()
            or not state_dir.is_dir()):
        raise ValueError("Unsafe state directory")
    # Same parent and filesystem: os.replace() never falls back to copying.
    if recovery_dir.parent != state_dir.parent or recovery_dir == state_dir:
        raise ValueError("Recovery must be a sibling of state")
    if recovery_dir.is_symlink():
        raise ValueError("Unsafe recovery directory")
    recovery_dir.mkdir(mode=0o700, exist_ok=True)
    if not recovery_dir.is_dir() or recovery_dir.is_symlink():
        raise ValueError("Unsafe recovery directory")
    os.chmod(recovery_dir, 0o700)
    if state_dir.stat().st_dev != recovery_dir.stat().st_dev:
        raise ValueError("Recovery and state need same filesystem")
    return state_dir, recovery_dir


def _require_stopped(callback: Callable[[], bool]) -> None:
    # This callback must be supplied by the trusted Android lifecycle; an
    # always-true lambda is appropriate only in synthetic offline tests.
    if not callable(callback) or callback() is not True:
        raise RuntimeError("Revival game must be confirmed stopped")


def _archive_files(data: bytes) -> dict[str, bytes]:
    names = backup.validate(data)
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        return {name: archive.read("state/" + name) for name in names}


def _fingerprints(state_dir: Path) -> dict[str, str]:
    # snapshot() rejects links, hardlinks, invalid JSON, unexpected JSON
    # files and partial writes. Its ZIP timestamp is not stable; hash entries.
    return {name: hashlib.sha256(raw).hexdigest()
            for name, raw in _archive_files(backup.snapshot(state_dir)).items()}


def _write_journal(path: Path, payload: dict) -> None:
    _private_file(path, json.dumps(payload, sort_keys=True).encode("ascii"))


def _load_journal(path: Path) -> dict:
    if path.is_symlink() or not path.is_file():
        raise ValueError("Invalid restore journal")
    if path.stat().st_size > 2048 or path.stat().st_mode & 0o077:
        raise ValueError("Unsafe restore journal")
    doc = json.loads(path.read_text("ascii"))
    if set(doc) != {"archive_sha256", "pre_sha256", "pre_file", "txn"}:
        raise ValueError("Unexpected restore journal fields")
    if not all(isinstance(doc[k], str) for k in doc):
        raise ValueError("Invalid restore journal fields")
    if not SHA256.fullmatch(doc["archive_sha256"]) or not SHA256.fullmatch(doc["pre_sha256"]):
        raise ValueError("Invalid restore digest")
    if not re.fullmatch(r"pre-[a-f0-9]{16}\.zip", doc["pre_file"]):
        raise ValueError("Invalid pre-restore filename")
    if not re.fullmatch(r"txn-[a-f0-9]{16}", doc["txn"]):
        raise ValueError("Invalid restore transaction")
    return doc


def _lock(recovery_dir: Path):
    path = recovery_dir / LOCK
    flags = os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW
    fd = os.open(path, flags, 0o600)
    if os.fstat(fd).st_mode & 0o077:
        os.close(fd)
        raise ValueError("Unsafe restore lock")
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BaseException:
        os.close(fd)
        raise
    return fd


def _restore_files(state_dir: Path, recovery_dir: Path,
                   files: dict[str, bytes], txn: str) -> None:
    directory = recovery_dir / txn
    if directory.is_symlink():
        raise ValueError("Unsafe restore staging")
    directory.mkdir(mode=0o700, exist_ok=True)
    stage = directory / "staged"
    if stage.is_symlink():
        raise ValueError("Unsafe restore staging")
    stage.mkdir(mode=0o700, exist_ok=True)
    for name, raw in files.items():
        _private_file(stage / name, raw)
    # Files not in the restored snapshot must not survive into the past save.
    for candidate in state_dir.iterdir():
        if backup.FILENAME.fullmatch(candidate.name):
            if (candidate.is_symlink() or not candidate.is_file()
                    or candidate.stat().st_nlink != 1):
                raise ValueError("Unsafe current save entry")
            if candidate.name not in files:
                candidate.unlink()
    for name in sorted(files):
        target = state_dir / name
        if target.is_symlink() or (target.exists() and not target.is_file()):
            raise ValueError("Unsafe restore target")
        os.replace(stage / name, target)
    _fsync_dir(state_dir)


def _recover_locked(state_dir: Path, recovery_dir: Path) -> bool:
    pending = recovery_dir / JOURNAL
    if not pending.exists() and not pending.is_symlink():
        return False
    record = _load_journal(pending)
    pre = recovery_dir / record["pre_file"]
    if pre.is_symlink() or not pre.is_file() or pre.stat().st_mode & 0o077:
        raise ValueError("Unsafe pre-restore backup")
    raw = pre.read_bytes()
    if not hmac.compare_digest(hashlib.sha256(raw).hexdigest(), record["pre_sha256"]):
        raise ValueError("Pre-restore backup digest mismatch")
    files = _archive_files(raw)
    _restore_files(state_dir, recovery_dir, files, record["txn"])
    if _fingerprints(state_dir) != {
            name: hashlib.sha256(content).hexdigest()
            for name, content in files.items()}:
        raise RuntimeError("Rollback verification failed")
    pending.unlink()
    _fsync_dir(recovery_dir)
    shutil.rmtree(recovery_dir / record["txn"])
    return True


def recover_pending(state_dir: Path, recovery_dir: Path, *,
                    game_stopped: Callable[[], bool]) -> bool:
    """Recover pre-restore state before starting gameplay after a crash.

    A trusted launcher must run this before initializing the Revival engine.
    It never restores a remote snapshot; only rolls back an interrupted one.
    """
    _require_stopped(game_stopped)
    state_dir, recovery_dir = _roots(state_dir, recovery_dir)
    fd = _lock(recovery_dir)
    try:
        _require_stopped(game_stopped)
        return _recover_locked(state_dir, recovery_dir)
    finally:
        os.close(fd)


def restore_offline(data: bytes, state_dir: Path, recovery_dir: Path, *,
                    expected_sha256: str, confirmation: str,
                    game_stopped: Callable[[], bool]) -> dict:
    """Restore a validated ZIP with a durable pre-restore checkpoint.

    No public endpoint, no implicit network calls. If an ordinary exception
    happens mid-commit, roll back immediately. If a process is killed, the
    pending journal allows recover_pending() to restore before next startup.
    """
    plan = inspect_archive(data, expected_sha256)
    if confirmation != plan["confirmation"]:
        raise PermissionError("Explicit archive confirmation required")
    _require_stopped(game_stopped)
    state_dir, recovery_dir = _roots(state_dir, recovery_dir)
    fd = _lock(recovery_dir)
    try:
        if (recovery_dir / JOURNAL).exists() or (recovery_dir / JOURNAL).is_symlink():
            raise RuntimeError("Interrupted restore must be recovered first")
        before = backup.snapshot(state_dir)
        old_fingerprints = _fingerprints(state_dir)
        desired = _archive_files(data)
        txn = "txn-" + secrets.token_hex(8)
        pre_file = "pre-" + secrets.token_hex(8) + ".zip"
        pre = recovery_dir / pre_file
        _private_file(pre, before)
        pre_sha = hashlib.sha256(before).hexdigest()
        # Persist recovery information BEFORE the first save file changes.
        journal = {
            "archive_sha256": plan["sha256"],
            "pre_sha256": pre_sha,
            "pre_file": pre_file,
            "txn": txn,
        }
        _require_stopped(game_stopped)
        if _fingerprints(state_dir) != old_fingerprints:
            raise RuntimeError("Save changed while preparing restore")
        _write_journal(recovery_dir / JOURNAL, journal)
        try:
            _restore_files(state_dir, recovery_dir, desired, txn)
            if _fingerprints(state_dir) != {
                    name: hashlib.sha256(content).hexdigest()
                    for name, content in desired.items()}:
                raise RuntimeError("Restored save verification failed")
        except Exception as exc:
            try:
                _recover_locked(state_dir, recovery_dir)
            except Exception as rollback_exc:
                raise RuntimeError(
                    "Restore failed and recovery remains pending; do not start game"
                ) from rollback_exc
            raise RuntimeError("Restore failed; previous save recovered") from exc
        (recovery_dir / JOURNAL).unlink()
        _fsync_dir(recovery_dir)
        staging = recovery_dir / txn
        if staging.exists():
            shutil.rmtree(staging)
        return {
            "sha256": plan["sha256"],
            "files": plan["files"],
            "pre_restore_file": pre_file,
            "pre_restore_sha256": pre_sha,
        }
    finally:
        os.close(fd)
