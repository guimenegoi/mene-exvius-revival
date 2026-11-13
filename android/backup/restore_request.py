"""Single-use, app-private FFBE restore request protocol (experimental ONLY).

The on-device user interface may stage a local ZIP and exact typed confirmation
while gameplay is active. This module NEVER applies a restore then: only the
cold-start guard, before any Revival engine import, consumes the request.

No HTTP route, server API, remote trigger, cron task or automatic snapshot
selection is provided by this module.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
from pathlib import Path
from typing import Callable

try:
    from ffbe_save_restore import (
        JOURNAL, _fsync_dir, _private_file, _require_stopped, _roots,
        inspect_archive, restore_offline,
    )
    from ffbe_backup_transport import MAX_PAYLOAD
except ModuleNotFoundError as exc:
    if exc.name not in ("ffbe_save_restore", "ffbe_backup_transport"):
        raise
    from save_restore import (
        JOURNAL, _fsync_dir, _private_file, _require_stopped, _roots,
        inspect_archive, restore_offline,
    )
    from lxc_backup import MAX_PAYLOAD


QUEUE = "restore-request.json"
PROCESSING = "restore-processing.json"
SCHEMA = 1
ZIPNAME = re.compile(r"request-([a-f0-9]{64})\.zip\Z")
HEX = re.compile(r"[a-f0-9]{64}\Z")


def _safe_json(path: Path) -> dict:
    if path.is_symlink() or not path.is_file():
        raise ValueError("Invalid restore request")
    st = path.stat()
    if st.st_nlink != 1 or st.st_size > 2048 or st.st_size <= 0 or st.st_mode & 0o077:
        raise ValueError("Unsafe restore request metadata")
    doc = json.loads(path.read_text("ascii"))
    if (not isinstance(doc, dict) or set(doc) !=
            {"schema", "archive", "sha256", "confirmation"} or
            type(doc["schema"]) is not int or doc["schema"] != SCHEMA):
        raise ValueError("Invalid restore request schema")
    digest = doc["sha256"]
    filename = doc["archive"]
    if (not isinstance(digest, str) or not HEX.fullmatch(digest) or
            not isinstance(filename, str) or
            filename != "request-" + digest + ".zip" or
            not isinstance(doc["confirmation"], str) or
            not hmac.compare_digest(doc["confirmation"], "RESTAURAR " + digest[:12])):
        raise ValueError("Unconfirmed restore request")
    return doc


def _request_bytes(recovery_dir: Path, doc: dict) -> bytes:
    file = recovery_dir / doc["archive"]
    if file.is_symlink() or not file.is_file():
        raise ValueError("Unsafe restore request ZIP")
    stat = file.stat()
    if stat.st_nlink != 1 or stat.st_mode & 0o077 or not 0 < stat.st_size <= MAX_PAYLOAD:
        raise ValueError("Unsafe restore ZIP attributes")
    with file.open("rb") as stream:
        raw = stream.read(MAX_PAYLOAD + 1)
    if len(raw) != stat.st_size:
        raise ValueError("Restore ZIP changed during reading")
    inspect_archive(raw, doc["sha256"])
    return raw


def _not_pending(recovery_dir: Path) -> None:
    for name in (JOURNAL, QUEUE, PROCESSING):
        file = recovery_dir / name
        if file.exists() or file.is_symlink():
            raise RuntimeError("A save restoration is already pending")


def stage_request(data: bytes, state_dir: Path, recovery_dir: Path, *,
                  confirmation: str) -> dict:
    """Only stage a local ZIP selected and confirmed by the player.

    Staging never writes the active save. The cold-start controller must be the
    only caller of consume_request(). Android-native UI must mirror the same
    schema and 0600/0700 permissions when writing the request atomically.
    """
    if not isinstance(data, bytes):
        raise ValueError("Expected complete local ZIP bytes")
    digest = hashlib.sha256(data).hexdigest()
    plan = inspect_archive(data, digest)
    if confirmation != plan["confirmation"]:
        raise PermissionError("Explicit confirmation does not match the ZIP")
    state_dir, recovery_dir = _roots(state_dir, recovery_dir)
    # Confirm that an active, valid save exists. This does not modify the save.
    try:
        from ffbe_backup_transport import snapshot as _snapshot
    except ModuleNotFoundError as exc:
        if exc.name != 'ffbe_backup_transport':
            raise
        from lxc_backup import snapshot as _snapshot
    _snapshot(state_dir)
    _not_pending(recovery_dir)
    name = "request-" + digest + ".zip"
    target = recovery_dir / name
    if target.exists() or target.is_symlink():
        raise ValueError("Selected ZIP already staged")
    _private_file(target, data)
    doc = {"schema": SCHEMA, "archive": name, "sha256": digest,
           "confirmation": confirmation}
    _private_file(recovery_dir / QUEUE, json.dumps(doc, sort_keys=True).encode("ascii"))
    return {"sha256": digest, "bytes": len(data), "files": plan["files"],
            "queued": True}


def _discard_processed(recovery_dir: Path) -> bool:
    marker = recovery_dir / PROCESSING
    if not marker.exists() and not marker.is_symlink():
        return False
    doc = _safe_json(marker)
    # On crash, either the journal was already used to recover the prior state
    # or the restore succeeded. Do not automatically repeat a user request.
    marker.unlink()
    _fsync_dir(recovery_dir)
    zipfile = recovery_dir / doc["archive"]
    if zipfile.is_file() and not zipfile.is_symlink() and zipfile.stat().st_nlink == 1:
        zipfile.unlink()
        _fsync_dir(recovery_dir)
    return True


def consume_request(state_dir: Path, recovery_dir: Path, *,
                    game_stopped: Callable[[], bool]) -> str:
    """Consume one previously confirmed request at a cold-start gate ONLY."""
    _require_stopped(game_stopped)
    state_dir, recovery_dir = _roots(state_dir, recovery_dir)
    if (recovery_dir / JOURNAL).exists() or (recovery_dir / JOURNAL).is_symlink():
        raise RuntimeError("Interrupted restore must be recovered before a request")
    if _discard_processed(recovery_dir):
        return "interrupted_restore_request_discarded"
    request = recovery_dir / QUEUE
    if not request.exists() and not request.is_symlink():
        return "no_restore_request"
    doc = _safe_json(request)
    data = _request_bytes(recovery_dir, doc)
    _require_stopped(game_stopped)
    processing = recovery_dir / PROCESSING
    if processing.exists() or processing.is_symlink():
        raise RuntimeError("Restore request already processing")
    # Consume the request before modifying the save. If the process crashes
    # after this rename, the next startup will NOT repeat the restore.
    os.replace(request, processing)
    _fsync_dir(recovery_dir)
    receipt = restore_offline(
        data, state_dir, recovery_dir, expected_sha256=doc["sha256"],
        confirmation=doc["confirmation"], game_stopped=game_stopped,
    )
    # Only reached after the restored files were checked. If interrupted,
    # the processing marker makes the next startup discard this request.
    _discard_processed(recovery_dir)
    return "restore_applied_" + receipt["sha256"][:12]
