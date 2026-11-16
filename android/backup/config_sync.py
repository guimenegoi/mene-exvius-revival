"""Optional, conflict-safe FFBE settings synchronization over the save TLS channel.

No remote connection on startup. The already paired backup worker invokes
poll() asynchronously. Remote edits are staged, never applied mid-game.
"""
from __future__ import annotations
import hashlib
import json
import ssl
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

import config_model

INTERVAL = 120
MAX_REPLY = 8192


def _request(config: dict, ca_file: Path, path: str, *,
             method="GET", payload: bytes | None = None,
             expected: str | None = None):
    base = config["endpoint"].rstrip("/")
    if base != "https://proxmox.tailcf6a16.ts.net:18447":
        raise ValueError("Unpinned configuration endpoint")
    if not config["device"].replace("_", "").replace("-", "").isalnum():
        raise ValueError("Invalid device")
    url = base + "/v1/configs/" + config["device"]
    headers = {"Authorization": "Bearer " + config["token"]}
    if payload is not None:
        headers.update({"Content-Type": "application/json",
                        "X-Content-SHA256": hashlib.sha256(payload).hexdigest(),
                        "If-Match": expected or ""})
    request = urllib.request.Request(url, method=method,
                                     headers=headers, data=payload)
    context = ssl.create_default_context(cafile=str(ca_file))
    # HTTPS only, explicit pinned CA, no system proxy or token redirection.
    class _NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, *args):
            return None
    opener = urllib.request.build_opener(
        urllib.request.ProxyHandler({}),
        urllib.request.HTTPSHandler(context=context), _NoRedirect())
    try:
        with opener.open(request, timeout=12) as response:
            raw = response.read(MAX_REPLY + 1)
            if len(raw) > MAX_REPLY:
                raise ValueError("Oversized configuration response")
            return response.status, json.loads(raw)
    except urllib.error.HTTPError as exc:
        if exc.code not in (404, 409, 428):
            raise
        raw = exc.read(MAX_REPLY + 1)
        if len(raw) > MAX_REPLY:
            raise ValueError("Oversized error response")
        return exc.code, json.loads(raw)


def _remote_revision(document: dict, stated: str) -> str:
    clean = config_model.validate_document(document)
    value = config_model.revision(clean)
    if stated != value:
        raise ValueError("Remote document revision mismatch")
    return value


class ConfigSync:
    def __init__(self, directory: Path, connection):
        self.directory = Path(directory)
        self.connection = connection
        self.active = self.directory / "server-config.json"
        self.pending = self.directory / "staged-config.json"
        self.meta = self.directory / "config-sync.json"
        self._next_poll = 0.0
        self._lock = threading.Lock()
        self._state = "not_paired"
        self._last_error = None

    def status(self) -> dict:
        with self._lock:
            return {"state": self._state, "last_error": self._last_error,
                    "has_pending": self.pending.is_file() and not self.pending.is_symlink()}

    def poll(self) -> bool:
        if time.monotonic() < self._next_poll:
            return False
        self._next_poll = time.monotonic() + INTERVAL
        try:
            connection = self.connection()
            if connection is None:
                with self._lock:
                    self._state = "not_paired"
                return False
            config, cafile = connection
            status, response = _request(config, cafile, "", method="GET")
            if status not in (200, 404):
                raise ValueError("Unexpected config response")
            remote = None if status == 404 else config_model.validate_document(response["document"])
            remote_rev = (config_model.ZERO_REVISION if remote is None
                          else _remote_revision(remote, response["revision"]))
            local = config_model.read_private(self.active)
            pending = config_model.read_private(self.pending)
            meta = self._read_meta()
            previous = meta.get("last_remote_revision")
            local_rev = config_model.revision(local) if local else config_model.ZERO_REVISION

            if pending is not None:
                state = ("pending_restart" if remote is not None
                         and config_model.revision(pending) == remote_rev
                         else "conflict")
            elif remote_rev == local_rev:
                self._save_meta(remote_rev)
                state = "up_to_date"
            elif remote is None:
                if local is not None and previous in (None, config_model.ZERO_REVISION):
                    state = self._upload(config, cafile, local, config_model.ZERO_REVISION)
                else:
                    state = "conflict"
            elif local is None:
                config_model.write_private(self.pending, remote)
                self._save_meta(remote_rev)
                state = "pending_restart"
            elif previous == local_rev:
                # Only the server changed since the last common revision.
                config_model.write_private(self.pending, remote)
                self._save_meta(remote_rev)
                state = "pending_restart"
            elif previous == remote_rev:
                # Only the local configuration changed; safe CAS push.
                state = self._upload(config, cafile, local, remote_rev)
            else:
                # Two divergent edits or missing common ancestor; no overwrite.
                state = "conflict"
            with self._lock:
                self._state = state
                self._last_error = None
            return state in ("up_to_date", "pending_restart", "uploaded")
        except Exception as exc:
            with self._lock:
                self._state = "retry_later"
                self._last_error = type(exc).__name__
            return False

    def _read_meta(self):
        if self.meta.is_symlink():
            raise ValueError("Unsafe config sync symlink")
        if not self.meta.exists():
            return {}
        if self.meta.stat().st_mode & 0o077 or self.meta.stat().st_size > 512:
            raise ValueError("Unsafe config sync metadata")
        data = json.loads(self.meta.read_text("utf-8"))
        if not isinstance(data, dict) or set(data) != {"last_remote_revision"}:
            raise ValueError("Bad sync metadata")
        rev = data["last_remote_revision"]
        if rev != "0" and (not isinstance(rev, str)
                           or len(rev) != 64
                           or any(x not in "0123456789abcdef" for x in rev)):
            raise ValueError("Bad revision metadata")
        return data

    def _save_meta(self, revision: str):
        # Metadata is not a server settings document; retain it separate
        # from the schema validated by config_model.
        import os
        import tempfile
        self.directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        if self.directory.is_symlink() or self.meta.is_symlink():
            raise ValueError("Unsafe config sync directory")
        os.chmod(self.directory, 0o700)
        fd, name = tempfile.mkstemp(prefix=".sync-", dir=self.directory)
        try:
            with os.fdopen(fd, "wb") as out:
                os.fchmod(out.fileno(), 0o600)
                out.write(json.dumps({"last_remote_revision": revision}).encode())
                out.flush()
                os.fsync(out.fileno())
            os.replace(name, self.meta)
        finally:
            Path(name).unlink(missing_ok=True)

    def _upload(self, config: dict, cafile: Path, document: dict, previous: str):
        code, response = _request(config, cafile, "", method="PUT",
                                  payload=config_model.encode(document),
                                  expected=previous)
        if code == 409:
            return "conflict"
        if code not in (200, 201):
            raise ValueError("Unexpected settings acknowledgement")
        got = response.get("revision")
        want = config_model.revision(document)
        if got != want:
            raise ValueError("Bad configuration receipt")
        self._save_meta(want)
        return "uploaded"
