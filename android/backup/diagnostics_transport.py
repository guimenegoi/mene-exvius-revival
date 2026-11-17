"""Validated diagnostic event ZIP transport, isolated from FFBE save snapshots.

Only schema-constrained, low-detail technical events are accepted. This module
uses the backup HTTPS/token authentication, but a separate /v1/diagnostics
endpoint and a separate diagnostics/ tree with distinct retention.
"""
from __future__ import annotations

import hashlib
import hmac
import io
import json
import os
import re
from pathlib import Path
import secrets
import tempfile
import urllib.request
import ssl
import zipfile
from datetime import datetime, timezone

SCHEMA = 1
MAX_WIRE = 512 * 1024
MAX_EVENTS = 500
MAX_EVENT_BYTES = 256 * 1024
RETENTION = 20
EVENT_TYPES = frozenset(("startup", "request", "http_error", "python_exception", "report", "settings_update"))
LEGACY_EVENT_TYPES = EVENT_TYPES - {"settings_update"}
SUPPORTED_SCHEMAS = (sorted(LEGACY_EVENT_TYPES), sorted(EVENT_TYPES))
REQUIRED = frozenset(("README.txt", "events.jsonl", "metadata.json"))
ALLOWED_FIELDS = frozenset(("time", "event", "exception_type", "http_status"))


def validate(raw: bytes) -> dict:
    if not isinstance(raw, bytes) or not 0 < len(raw) <= MAX_WIRE:
        raise ValueError("Invalid diagnostics payload")
    try:
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            entries = archive.infolist()
            if len(entries) != 3 or {x.filename for x in entries} != REQUIRED:
                raise ValueError("Unexpected diagnostics ZIP entries")
            if any(x.is_dir() or x.file_size > MAX_EVENT_BYTES or
                   x.compress_type not in (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED)
                   or (x.external_attr >> 16) & 0o170000 == 0o120000
                   for x in entries):
                raise ValueError("Unsafe diagnostics ZIP member")
            if archive.getinfo("README.txt").file_size > 2048 or archive.getinfo("metadata.json").file_size > 4096:
                raise ValueError("Oversized diagnostics descriptions")
            info = archive.read("README.txt")
            if not info.startswith(b"FFBE Android local diagnostics.") or len(info) > 2048:
                raise ValueError("Invalid diagnostics README")
            text = archive.read("events.jsonl")
            if len(text) > MAX_EVENT_BYTES:
                raise ValueError("Oversized diagnostics events")
            meta = json.loads(archive.read("metadata.json"))
            if (not isinstance(meta, dict) or set(meta) != {"schema", "platform", "mode", "captured_event_types"}
                    or meta.get("schema") != SCHEMA
                    or meta.get("platform") != "android"
                    or meta.get("mode") != "offline-local"
                    or meta.get("captured_event_types") not in SUPPORTED_SCHEMAS):
                raise ValueError("Invalid diagnostics metadata")
            events = []
            for line in text.splitlines():
                if not line:
                    continue
                if len(events) >= MAX_EVENTS or len(line) > 512:
                    raise ValueError("Too many diagnostics events")
                item = json.loads(line)
                if not isinstance(item, dict) or not {"time", "event"} <= set(item) or not set(item) <= ALLOWED_FIELDS:
                    raise ValueError("Unsafe event fields")
                if (item["event"] not in EVENT_TYPES
                        or not isinstance(item["time"], str)
                        or not re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\+00:00", item["time"])):
                    raise ValueError("Invalid diagnostic event")
                if "exception_type" in item:
                    v = item["exception_type"]
                    if (not isinstance(v, str) or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]{0,63}", v)):
                        raise ValueError("Invalid exception name")
                if "http_status" in item and (type(item["http_status"]) is not int
                        or not 100 <= item["http_status"] <= 599):
                    raise ValueError("Invalid HTTP status")
                events.append(item)
            return {"events": len(events)}
    except (zipfile.BadZipFile, UnicodeError, json.JSONDecodeError, KeyError) as exc:
        raise ValueError("Invalid diagnostics archive") from exc


def store(data: bytes, root: Path, device: str, retention: int = RETENTION) -> dict:
    try:
        from ffbe_backup_transport import DEVICE, _secure_dir
    except ImportError:
        from lxc_backup import DEVICE, _secure_dir
    if not DEVICE.fullmatch(device) or not 1 <= retention <= 100:
        raise ValueError("Invalid diagnostics target")
    report = validate(data)
    folder = _secure_dir(Path(root) / "diagnostics")
    folder = _secure_dir(folder / device)
    digest = hashlib.sha256(data).hexdigest()
    name = (datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") +
            "-" + digest[:12] + "-" + secrets.token_hex(3) + ".zip")
    fd, temporary = tempfile.mkstemp(prefix=".pending-", dir=folder)
    try:
        with os.fdopen(fd, "wb") as dest:
            os.fchmod(dest.fileno(), 0o600)
            dest.write(data)
            dest.flush()
            os.fsync(dest.fileno())
        os.replace(temporary, folder / name)
    finally:
        Path(temporary).unlink(missing_ok=True)
    for path in sorted(folder.glob("*.zip"))[:-retention]:
        if path.is_file() and not path.is_symlink():
            path.unlink()
    return {"sha256": digest, "id": name, "bytes": len(data),
            "events": report["events"]}


def upload(data: bytes, endpoint: str, token: str, ca_file: Path,
           device: str, timeout: float = 15) -> dict:
    try:
        from ffbe_backup_transport import DEVICE, _NoRedirect, MAX_RECEIPT
    except ImportError:
        from lxc_backup import DEVICE, _NoRedirect, MAX_RECEIPT
    if not endpoint.startswith("https://") or not DEVICE.fullmatch(device):
        raise ValueError("Invalid diagnostics upload destination")
    validate(data)
    req = urllib.request.Request(
        endpoint.rstrip("/") + "/v1/diagnostics/" + device,
        data=data, method="POST",
        headers={"Authorization": "Bearer " + token,
                 "Content-Type": "application/zip",
                 "X-Content-SHA256": hashlib.sha256(data).hexdigest()})
    context = ssl.create_default_context(cafile=str(ca_file))
    opener = urllib.request.build_opener(urllib.request.HTTPSHandler(context=context),
                                        _NoRedirect())
    with opener.open(req, timeout=timeout) as result:
        if result.status != 201:
            raise ValueError("Diagnostics rejected")
        receipt = result.read(MAX_RECEIPT + 1)
        if len(receipt) > MAX_RECEIPT:
            raise ValueError("Diagnostics receipt too large")
        response = json.loads(receipt)
    if not hmac.compare_digest(response.get("sha256", ""),
                               hashlib.sha256(data).hexdigest()):
        raise ValueError("Diagnostics acknowledgement mismatch")
    return response
