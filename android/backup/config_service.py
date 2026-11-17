"""Revisioned, authenticated FFBE configuration store for the LXC receiver.

Routes are served through lxc_backup.make_handler, which authenticates Bearer
before calling this module. Configuration is kept separate from save ZIPs.
"""
from __future__ import annotations
import hashlib
import hmac
import json
import re
import threading
from pathlib import Path
import config_model

_LOCK = threading.Lock()
REV = re.compile(r"(?:0|[a-f0-9]{64})\Z")
MAX_WIRE = config_model.MAX_BYTES
HISTORY = 30

def _path(root: Path, device: str) -> Path:
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", device):
        raise ValueError("Invalid device name")
    return Path(root) / "configs" / (device + ".json")

def get(root: Path, device: str) -> dict | None:
    document = config_model.read_private(_path(root, device))
    if document is None:
        return None
    return {"revision": config_model.revision(document), "document": document}

def put(root: Path, device: str, body: bytes, expected: str) -> tuple[int, dict]:
    if not isinstance(expected, str) or not REV.fullmatch(expected):
        return 428, {"error": "revision_precondition_required"}
    try:
        proposed = config_model.parse(body)
        path = _path(root, device)
        with _LOCK:
            old = config_model.read_private(path)
            current = config_model.revision(old) if old is not None else config_model.ZERO_REVISION
            if not hmac.compare_digest(current, expected):
                return 409, {"error": "revision_conflict", "revision": current}
            new_revision = config_model.revision(proposed)
            if new_revision == current:
                return 200, {"revision": new_revision, "unchanged": True}
            if old is not None:
                history = Path(root) / "config-history" / device
                previous = history / (current + ".json")
                if config_model.read_private(previous) is None:
                    config_model.write_private(previous, old)
                records = sorted(history.glob("*.json"), key=lambda f: f.stat().st_mtime_ns)
                for stale in records[:-HISTORY]:
                    if stale.is_symlink():
                        raise ValueError("Unsafe historical configuration")
                    stale.unlink()
            config_model.write_private(path, proposed)
            return 201, {"revision": new_revision}
    except (ValueError, OSError, TypeError, KeyError) as exc:
        return 400, {"error": type(exc).__name__}

def authorize_write_headers(headers, body: bytes) -> None:
    if headers.get("Content-Type") != "application/json":
        raise ValueError("JSON content type required")
    claimed = headers.get("X-Content-SHA256", "")
    if not re.fullmatch(r"[a-f0-9]{64}", claimed):
        raise ValueError("SHA-256 required")
    if not hmac.compare_digest(claimed, hashlib.sha256(body).hexdigest()):
        raise ValueError("SHA-256 content mismatch")
