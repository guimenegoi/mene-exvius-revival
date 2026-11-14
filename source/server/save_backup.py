"""Opt-in, nonblocking FFBE Android save snapshots using the existing LXC transport.

No credentials ship in the APK. A private per-install config enables this hook;
network failures can never change the game save or the response pipeline.
"""
from __future__ import annotations

import json
import os
import threading
import time
from pathlib import Path

_LOCK = threading.Lock()
_RUNNING = False
_LAST_ATTEMPT: float | None = None
MIN_INTERVAL_SECONDS = 300


def _private_file(path: Path) -> bool:
    return (not path.is_symlink() and path.is_file()
            and path.stat().st_mode & 0o077 == 0)


def _configuration() -> tuple[str, str, str, Path, Path] | None:
    path_value = os.environ.get("FFBE_SAVE_BACKUP_CONFIG", "")
    if not path_value or os.environ.get("FFBE_ANDROID_EMBEDDED") != "1":
        return None
    config = Path(path_value)
    if not _private_file(config) or config.stat().st_size > 8192:
        raise ValueError("Backup config is not a private regular file")
    body = json.loads(config.read_text(encoding="utf-8"))
    if not isinstance(body, dict) or body.get("enabled") is not True:
        return None
    endpoint, device = body.get("url"), body.get("device")
    if not isinstance(endpoint, str) or not endpoint.startswith("https://"):
        raise ValueError("Backup endpoint must use HTTPS")
    if not isinstance(device, str):
        raise ValueError("Backup device identifier missing")
    token_file, ca_file = Path(body["token_file"]), Path(body["ca_file"])
    if not _private_file(token_file) or not ca_file.is_file() or ca_file.is_symlink():
        raise ValueError("Backup credentials invalid")
    token = token_file.read_text(encoding="utf-8").strip()
    if len(token) < 32:
        raise ValueError("Backup bearer token invalid")
    return endpoint, device, token, ca_file, token_file


def after_save(saved_path: str) -> bool:
    """Schedule one snapshot after a successful atomic save; never block on IO/network."""
    if os.environ.get("FFBE_ANDROID_EMBEDDED") != "1" or not os.environ.get("FFBE_SAVE_BACKUP_CONFIG"):
        return False
    path = Path(saved_path)
    if path.name != "campaign.json" or path.parent.name != "state":
        return False
    global _RUNNING, _LAST_ATTEMPT
    with _LOCK:
        now = time.monotonic()
        if _RUNNING or (_LAST_ATTEMPT is not None and now - _LAST_ATTEMPT < MIN_INTERVAL_SECONDS):
            return False
        _RUNNING = True
        _LAST_ATTEMPT = now
    try:
        worker = threading.Thread(target=_send, args=(path.parent,), name="FFBE-SaveBackup", daemon=True)
        worker.start()
        return True
    except Exception:
        with _LOCK:
            _RUNNING = False
        return False


def _send(state_dir: Path) -> None:
    global _RUNNING
    try:
        settings = _configuration()
        if settings is None:
            return
        endpoint, device, token, ca_file, _ = settings
        from lxc_backup import upload
        result = upload(state_dir, endpoint, token, ca_file, device)
        print("SAVE-BACKUP: confirmed SHA-256 " + str(result["sha256"]), flush=True)
    except Exception as exc:
        # Deliberately avoid printing URL, token, paths or response bodies.
        print("SAVE-BACKUP: skipped/failed (" + type(exc).__name__ + ")", flush=True)
    finally:
        with _LOCK:
            _RUNNING = False
