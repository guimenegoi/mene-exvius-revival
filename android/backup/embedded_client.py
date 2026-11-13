"""Opt-in Android FFBE save backups. Imported only by the embedded Revival worker.

No account/save data is sent until an ADB-provisioned, private TLS+token
configuration exists. The worker is daemonized and cannot block gameplay.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import secrets
import ssl
import stat
import tempfile
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

import ffbe_backup_transport as transport

PAIR_PATH = "/__exvius/backup/pair"
STATUS_PATH = "/__exvius/backup/status"
DEVICE = re.compile(r"[A-Za-z0-9_-]{1,64}\Z")
MAX_PAIR = 8192
POLL_SECONDS = 20
BACKOFF_SECONDS = 120
PAIR_TTL = 600

def _private_dir(path: Path) -> Path:
    if path.is_symlink():
        raise ValueError("Backup directory is a symlink")
    path.mkdir(mode=0o700, parents=True, exist_ok=True)
    if path.is_symlink() or not path.is_dir():
        raise ValueError("Unsafe backup directory")
    os.chmod(path, 0o700)
    return path

def _write_private(path: Path, data: bytes) -> None:
    if path.is_symlink():
        raise ValueError("Backup configuration is a symlink")
    _private_dir(path.parent)
    fd, name = tempfile.mkstemp(prefix=".backup-staging-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as output:
            os.fchmod(output.fileno(), 0o600)
            output.write(data)
            output.flush()
            os.fsync(output.fileno())
        os.replace(name, path)
    finally:
        Path(name).unlink(missing_ok=True)

def _validated_config(value: dict) -> dict:
    if not isinstance(value, dict) or set(value) != {"endpoint", "token", "device", "ca_pem"}:
        raise ValueError("Invalid backup pairing parameters")
    endpoint, token, device, pem = (value[key] for key in ("endpoint", "token", "device", "ca_pem"))
    if not all(isinstance(x, str) for x in (endpoint, token, device, pem)):
        raise ValueError("Invalid backup pairing types")
    if not (32 <= len(token) <= 256 and DEVICE.fullmatch(device)):
        raise ValueError("Invalid device or token")
    url = urlsplit(endpoint)
    if (url.scheme != "https" or url.username or url.password or url.query or url.fragment
            or url.path not in ("", "/") or url.hostname != "proxmox.tailcf6a16.ts.net"
            or url.port != 18447):
        raise ValueError("Backup endpoint must be the pinned private Tailscale TLS service")
    if len(pem) > 4096 or "BEGIN CERTIFICATE" not in pem:
        raise ValueError("Missing or oversized pinned certificate")
    try:
        ssl.PEM_cert_to_DER_cert(pem)
    except ValueError as exc:
        raise ValueError("Invalid pinned certificate") from exc
    return {"endpoint": endpoint.rstrip("/"), "token": token, "device": device, "ca_pem": pem}

def _signature(state_dir: Path) -> tuple | None:
    if state_dir.is_symlink() or not state_dir.is_dir():
        return None
    names = []
    for path in state_dir.iterdir():
        if path.name.endswith(".json.tmp"):
            continue
        if not path.name.endswith(".json"):
            continue
        if path.is_symlink():
            raise ValueError("Unsafe save symlink")
        st = path.stat()
        if not stat.S_ISREG(st.st_mode) or st.st_nlink != 1:
            raise ValueError("Unsafe save inode")
        names.append((path.name, st.st_ino, st.st_size, st.st_mtime_ns))
    if not any(x[0] == "campaign.json" for x in names):
        return None
    return tuple(sorted(names))

class BackupCoordinator:
    def __init__(self, private_dir: Path, state_dir: Path, *, interval: float = POLL_SECONDS):
        self.private = Path(private_dir)
        self.state_dir = Path(state_dir)
        self.interval = interval
        self.config_file = self.private / "config.json"
        self.ca_file = self.private / "receiver-ca.pem"
        self.status_file = self.private / "status.json"
        self._lock = threading.Lock()
        self._wake = threading.Event()
        self._stop = threading.Event()
        self._last_signature = None
        self._next_retry = 0.0
        self._last_error = None
        self._last_receipt = None
        self._thread = None
        self._pair_nonce = secrets.token_urlsafe(24)
        self._pair_deadline = time.monotonic() + PAIR_TTL
        self._pair_attempts = 0

    def enabled(self) -> bool:
        return (self.config_file.is_file() and not self.config_file.is_symlink()
                and self.ca_file.is_file() and not self.ca_file.is_symlink())

    def start(self) -> None:
        if self._thread is not None:
            return
        self._thread = threading.Thread(target=self._loop, name="ffbe-save-backup",
                                        daemon=True)
        self._thread.start()
        if not self.enabled():
            # ADB logcat is private to shell and the app on modern Android.
            print("FFBE-BACKUP-PAIR: " + self._pair_nonce, flush=True)
        else:
            print("FFBE-BACKUP: paired; scheduled checks enabled", flush=True)

    def stop(self) -> None:
        self._stop.set()
        self._wake.set()
        if self._thread:
            self._thread.join(timeout=2)

    def pair(self, value: dict, code: str) -> None:
        with self._lock:
            self._pair_attempts += 1
            if (self.enabled() or self._pair_attempts > 6
                    or time.monotonic() > self._pair_deadline
                    or not isinstance(code, str)
                    or not hmac.compare_digest(code, self._pair_nonce)):
                raise PermissionError("Pairing unavailable or code invalid")
            parsed = _validated_config(value)
            _private_dir(self.private)
            # Only the certificate is copied into the CA file; never trust
            # system certificates or disable SSL verification as a fallback.
            _write_private(self.ca_file, parsed["ca_pem"].encode("ascii"))
            _write_private(self.config_file, json.dumps({
                k: parsed[k] for k in ("endpoint", "token", "device")
            }).encode("utf-8"))
            self._pair_nonce = ""
            self._last_signature = None
            self._next_retry = 0
        self._wake.set()
        print("FFBE-BACKUP: device paired with private TLS receiver", flush=True)

    def status(self) -> dict:
        with self._lock:
            receipt = dict(self._last_receipt) if self._last_receipt else None
            return {"configured": self.enabled(), "last_backup": receipt,
                    "last_error": self._last_error, "worker_active":
                    bool(self._thread and self._thread.is_alive())}

    def _load(self) -> dict:
        if not self.enabled():
            raise ValueError("Backup not paired")
        if self.config_file.stat().st_mode & 0o077:
            raise ValueError("Unsafe backup configuration permissions")
        if self.ca_file.stat().st_mode & 0o077:
            raise ValueError("Unsafe backup CA permissions")
        config = json.loads(self.config_file.read_text("utf-8"))
        if not isinstance(config, dict):
            raise ValueError("Invalid private config")
        config["ca_pem"] = self.ca_file.read_text("ascii")
        return _validated_config(config)

    def poll_once(self) -> bool:
        if not self.enabled():
            return False
        if time.monotonic() < self._next_retry:
            return False
        try:
            signature = _signature(self.state_dir)
            if signature is None or signature == self._last_signature:
                return False
            config = self._load()
            result = transport.upload(
                self.state_dir, config["endpoint"], config["token"],
                self.ca_file, config["device"], timeout=15)
            if result.get("files") and "campaign.json" not in result["files"]:
                raise ValueError("Active save was not accepted")
            receipt = {"sha256": result["sha256"],
                       "time": datetime.now(timezone.utc).isoformat(),
                       "files": result.get("files", [])}
            with self._lock:
                self._last_signature = signature
                self._last_receipt = receipt
                self._last_error = None
                self._next_retry = 0.0
            _write_private(self.status_file, json.dumps(receipt).encode("utf-8"))
            print("FFBE-BACKUP: private save snapshot acknowledged", flush=True)
            return True
        except Exception as exc:
            # Never disclose bearer credentials, endpoints, or save payloads.
            with self._lock:
                self._last_error = type(exc).__name__
                self._next_retry = time.monotonic() + BACKOFF_SECONDS
            print("FFBE-BACKUP: retry scheduled (" + type(exc).__name__ + ")", flush=True)
            return False

    def _loop(self) -> None:
        while not self._stop.is_set():
            self.poll_once()
            self._wake.wait(self.interval)
            self._wake.clear()

def wrap_handler(base, coordinator: BackupCoordinator):
    """Intercept only private maintenance paths; normal game routes untouched."""
    class Handler(base):
        def _backup_json(self, status: int, data: dict) -> None:
            body = json.dumps(data, sort_keys=True).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            if self.path == STATUS_PATH:
                return self._backup_json(200, coordinator.status())
            return super().do_GET()

        def do_POST(self):
            if self.path != PAIR_PATH:
                return super().do_POST()
            try:
                if self.client_address[0] not in ("127.0.0.1", "::1"):
                    raise PermissionError("Loopback-only operation")
                length = int(self.headers.get("Content-Length", "0"))
                if not 0 < length <= MAX_PAIR or self.headers.get_content_type() != "application/json":
                    raise ValueError("Invalid pairing message")
                body = json.loads(self.rfile.read(length))
                if not isinstance(body, dict):
                    raise ValueError("Invalid pairing body")
                code = self.headers.get("X-FFBE-Pair-Code", "")
                coordinator.pair(body, code)
                return self._backup_json(201, {"paired": True})
            except (ValueError, PermissionError, OSError, KeyError, UnicodeError):
                return self._backup_json(403, {"error": "pairing refused"})

    return Handler
