#!/usr/bin/env python3
"""Optional FFBE save backup transport (experimental, not connected to the APK).

HTTPS only in production, with CA validation and a bearer token. No save restore,
gameplay dependency or automatic run. Bounded, validated ZIP snapshots of JSON
state; never uploads original game resources, log requests or private keys.
"""
from __future__ import annotations

import argparse
import hashlib
import hmac
import io
import ipaddress
import json
import os
import re
import secrets
import ssl
import tempfile
import threading
import urllib.request
import zipfile
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

SCHEMA = 1
MAX_FILE = 8 << 20
MAX_PAYLOAD = 20 << 20
MAX_RECEIPT = 8192
MAX_FILES = 20
RETAIN = 30
FILENAME = re.compile(r"[a-zA-Z0-9_-]{1,64}\.json\Z")
DEVICE = re.compile(r"[a-zA-Z0-9_-]{1,64}\Z")


def _secure_dir(path: Path) -> Path:
    path = Path(path)
    if path.is_symlink():
        raise ValueError("Refusing symlink directory")
    path.mkdir(mode=0o700, parents=True, exist_ok=True)
    if path.is_symlink() or not path.is_dir():
        raise ValueError("Invalid private directory")
    os.chmod(path, 0o700)
    return path


def _read_state(path: Path) -> bytes:
    if path.is_symlink() or not path.is_file():
        raise ValueError("Unsafe save file")
    before = path.stat()
    if before.st_size <= 0 or before.st_size > MAX_FILE:
        raise ValueError("Save file outside allowed size")
    with path.open("rb") as stream:
        raw = stream.read(MAX_FILE + 1)
    after = path.stat()
    if (len(raw) > MAX_FILE or before.st_ino != after.st_ino
            or before.st_mtime_ns != after.st_mtime_ns or before.st_size != len(raw)):
        raise ValueError("Save was modified while reading")
    parsed = json.loads(raw)
    if not isinstance(parsed, dict):
        raise ValueError("Expected JSON object in save")
    return raw


def snapshot(state_dir: Path) -> bytes:
    """Capture an existing, atomically saved state in memory (no writes)."""
    if state_dir.is_symlink() or not state_dir.is_dir():
        raise ValueError("Unsafe or absent FFBE state directory")
    files = sorted(p for p in state_dir.iterdir() if p.is_file() or p.is_symlink())
    # Count exported JSONs, not transient atomic-write files. Still bound
    # directory scanning to prevent unbounded temporary-file accumulation.
    if len(files) > 2 * MAX_FILES:
        raise ValueError("Too many save files")
    payloads = {}
    for path in files:
        if path.name.endswith(".json.tmp") and FILENAME.fullmatch(path.name[:-4]):
            # PlayerState.save() uses <slot>.json.tmp + os.replace().
            # Ignore the in-progress write, but never silently accept symlinks.
            if path.is_symlink() or not path.is_file():
                raise ValueError("Unsafe temporary FFBE save file")
            continue
        if not FILENAME.fullmatch(path.name):
            raise ValueError("Unexpected file in FFBE state: " + path.name)
        if len(payloads) >= MAX_FILES:
            raise ValueError("Too many save files")
        payloads[path.name] = _read_state(path)
    if "campaign.json" not in payloads:
        raise ValueError("Missing active campaign.json")
    if sum(map(len, payloads.values())) > MAX_PAYLOAD:
        raise ValueError("Save exceeds backup capacity")
    document = {"schema": SCHEMA, "files": {
        name: hashlib.sha256(data).hexdigest()
        for name, data in sorted(payloads.items())
    }}
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_STORED) as zf:
        zf.writestr("manifest.json", json.dumps(document, sort_keys=True).encode())
        for name, data in sorted(payloads.items()):
            zf.writestr("state/" + name, data)
    output = buffer.getvalue()
    if len(output) > MAX_PAYLOAD:
        raise ValueError("Backup ZIP too large")
    return output


def validate(data: bytes) -> list[str]:
    """Reject traversal, symlinks, ZIP bombs, duplicate and invalid JSON."""
    if not data or len(data) > MAX_PAYLOAD:
        raise ValueError("Invalid backup payload size")
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            members = zf.infolist()
            if not 2 <= len(members) <= MAX_FILES + 1:
                raise ValueError("Invalid archive entry count")
            names = [m.filename for m in members]
            if len(names) != len(set(names)) or "manifest.json" not in names:
                raise ValueError("Duplicate or absent archive manifest")
            manifest = zf.getinfo("manifest.json")
            if manifest.file_size > 8192:
                raise ValueError("Oversized manifest")
            record = json.loads(zf.read(manifest))
            if (not isinstance(record, dict) or record.get("schema") != SCHEMA
                    or not isinstance(record.get("files"), dict)):
                raise ValueError("Invalid snapshot manifest")
            claimed = record["files"]
            if "campaign.json" not in claimed or len(claimed) != len(members) - 1:
                raise ValueError("Campaign missing or extra ZIP entries")
            total = 0
            for member in members:
                if member.compress_type != zipfile.ZIP_STORED or member.is_dir():
                    raise ValueError("Compressed or directory entry refused")
                if (member.external_attr >> 16) & 0o170000 == 0o120000:
                    raise ValueError("Symlinks forbidden")
                if member.filename == "manifest.json":
                    if member.file_size > 8192:
                        raise ValueError("Oversized manifest")
                    continue
                if not member.filename.startswith("state/"):
                    raise ValueError("Unexpected archive member")
                filename = member.filename[6:]
                if not FILENAME.fullmatch(filename) or filename not in claimed:
                    raise ValueError("Unsafe or unlisted save name")
                if member.file_size > MAX_FILE or member.file_size <= 0:
                    raise ValueError("Oversized save")
                total += member.file_size
                if total > MAX_PAYLOAD:
                    raise ValueError("Too much save data")
                raw = zf.read(member)
                if not isinstance(json.loads(raw), dict):
                    raise ValueError("Invalid save JSON type")
                digest = hashlib.sha256(raw).hexdigest()
                if not isinstance(claimed[filename], str) or not hmac.compare_digest(digest, claimed[filename]):
                    raise ValueError("Save SHA-256 mismatch")
            return sorted(claimed)
    except (zipfile.BadZipFile, UnicodeError, json.JSONDecodeError, KeyError) as exc:
        raise ValueError("Invalid backup ZIP/JSON") from exc


def store(data: bytes, root: Path, device: str, retention: int = RETAIN) -> dict:
    if not DEVICE.fullmatch(device):
        raise ValueError("Invalid device ID")
    if not 1 <= retention <= 100:
        raise ValueError("Invalid retention")
    names = validate(data)
    _secure_dir(root)
    target = _secure_dir(root / device)
    digest = hashlib.sha256(data).hexdigest()
    now = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    name = now + "-" + digest[:12] + "-" + secrets.token_hex(3) + ".zip"
    fd, tempname = tempfile.mkstemp(prefix=".pending-", dir=target)
    try:
        with os.fdopen(fd, "wb") as output:
            os.fchmod(output.fileno(), 0o600)
            output.write(data)
            output.flush()
            os.fsync(output.fileno())
        os.replace(tempname, target / name)
    finally:
        Path(tempname).unlink(missing_ok=True)
    previous = sorted(target.glob("*.zip"))
    for path in previous[:-retention]:
        if path.is_file() and not path.is_symlink():
            path.unlink()
    return {"id": name, "sha256": digest, "bytes": len(data), "files": names}


def make_handler(root: Path, token: str):
    guard = threading.Lock()
    class Handler(BaseHTTPRequestHandler):
        server_version = "FFBE-SaveBackup/1"

        def log_message(self, fmt, *args):
            # Never log authorization headers, save contents or token.
            pass

        def _json(self, status: int, body: dict):
            data = json.dumps(body, sort_keys=True).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            self.wfile.write(data)

        def _authenticated(self) -> bool:
            actual = self.headers.get("Authorization", "")
            return hmac.compare_digest(actual, "Bearer " + token)

        def do_POST(self):
            if not self._authenticated():
                return self._json(401, {"error": "unauthorized"})
            prefix = "/v1/backups/"
            device = self.path[len(prefix):] if self.path.startswith(prefix) else ""
            if not DEVICE.fullmatch(device):
                return self._json(404, {"error": "not_found"})
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if not 0 < length <= MAX_PAYLOAD:
                    raise ValueError("Invalid content length")
                if self.headers.get("Content-Type") != "application/zip":
                    raise ValueError("Invalid content type")
                digest = self.headers.get("X-Content-SHA256", "")
                if not re.fullmatch(r"[a-f0-9]{64}", digest):
                    raise ValueError("Missing SHA-256")
                data = self.rfile.read(length)
                if len(data) != length or not hmac.compare_digest(hashlib.sha256(data).hexdigest(), digest):
                    raise ValueError("Payload SHA-256 mismatch")
                with guard:
                    result = store(data, root, device)
                return self._json(201, result)
            except (ValueError, OSError) as exc:
                return self._json(400, {"error": type(exc).__name__})

        def do_GET(self):
            if not self._authenticated():
                return self._json(401, {"error": "unauthorized"})
            prefix = "/v1/backups/"
            device = self.path[len(prefix):] if self.path.startswith(prefix) else ""
            if not DEVICE.fullmatch(device):
                return self._json(404, {"error": "not_found"})
            path = root / device
            files = [] if path.is_symlink() or not path.is_dir() else [
                {"id": item.name, "bytes": item.stat().st_size}
                for item in sorted(path.glob("*.zip"), reverse=True)
                if item.is_file() and not item.is_symlink()
            ]
            return self._json(200, {"backups": files})
    return Handler


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """Never forward backup credentials or payloads to redirect targets."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def upload(state_dir: Path, url: str, token: str, cafile: Path, device: str,
           timeout: float = 8.0) -> dict:
    """Optional one-shot transfer; the caller decides when and whether to run."""
    if not url.startswith("https://") or not DEVICE.fullmatch(device):
        raise ValueError("Backup requires HTTPS and a valid device ID")
    data = snapshot(state_dir)
    request = urllib.request.Request(
        url.rstrip("/") + "/v1/backups/" + device,
        data=data, method="POST", headers={
            "Authorization": "Bearer " + token,
            "Content-Type": "application/zip",
            "X-Content-SHA256": hashlib.sha256(data).hexdigest(),
        })
    context = ssl.create_default_context(cafile=str(cafile))
    opener = urllib.request.build_opener(
        urllib.request.HTTPSHandler(context=context), _NoRedirect())
    with opener.open(request, timeout=timeout) as reply:
        if reply.status != 201:
            raise RuntimeError("Server did not accept backup")
        # A remote endpoint must not be able to exhaust client memory with
        # an unbounded acknowledgement (even over authenticated HTTPS).
        raw = reply.read(MAX_RECEIPT + 1)
        if len(raw) > MAX_RECEIPT:
            raise ValueError("Backup acknowledgement too large")
        result = json.loads(raw)
        if not isinstance(result, dict):
            raise ValueError("Invalid backup acknowledgement")
    if not hmac.compare_digest(result.get("sha256", ""), hashlib.sha256(data).hexdigest()):
        raise RuntimeError("Backup server SHA-256 acknowledgement mismatch")
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    receive = sub.add_parser("serve")
    receive.add_argument("--bind", required=True, help="explicit LAN IP, never 0.0.0.0")
    receive.add_argument("--port", type=int, default=18447)
    receive.add_argument("--store", required=True, type=Path)
    receive.add_argument("--cert", required=True, type=Path)
    receive.add_argument("--key", required=True, type=Path)
    receive.add_argument("--token-file", required=True, type=Path)
    send = sub.add_parser("push")
    send.add_argument("--state", required=True, type=Path)
    send.add_argument("--url", required=True)
    send.add_argument("--device", required=True)
    send.add_argument("--ca", required=True, type=Path)
    send.add_argument("--token-file", required=True, type=Path)
    args = parser.parse_args(argv)
    if args.command == "serve":
        host = ipaddress.ip_address(args.bind)
        if not (host.is_private or host.is_loopback) or host.is_unspecified:
            parser.error("Use an explicit private IP, not a public or wildcard address")
        if args.store.is_symlink() or args.cert.is_symlink() or args.key.is_symlink():
            parser.error("Refusing symlink service inputs")
        if not args.cert.is_file() or not args.key.is_file():
            parser.error("TLS certificate and key must be regular files")
        if args.key.stat().st_mode & 0o077:
            parser.error("TLS private key must be mode 0600")
        if (args.token_file.is_symlink() or not args.token_file.is_file()
                or args.token_file.stat().st_mode & 0o077):
            parser.error("Token file must be private (mode 0600)")
        token = args.token_file.read_text(encoding="utf-8").strip()
        if len(token) < 32:
            parser.error("Token must be at least 32 characters")
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.minimum_version = ssl.TLSVersion.TLSv1_2
        context.load_cert_chain(str(args.cert), str(args.key))
        server = ThreadingHTTPServer((args.bind, args.port), make_handler(args.store, token))
        server.socket = context.wrap_socket(server.socket, server_side=True)
        print(f"SAVE-BACKUP HTTPS READY {args.bind}:{args.port}", flush=True)
        try:
            server.serve_forever()
        finally:
            server.server_close()
        return 0
    if (args.token_file.is_symlink() or not args.token_file.is_file()
            or args.token_file.stat().st_mode & 0o077):
        parser.error("Token file must be private (mode 0600)")
    token = args.token_file.read_text(encoding="utf-8").strip()
    if len(token) < 32:
        parser.error("Token must be at least 32 characters")
    print(json.dumps(upload(args.state, args.url, token, args.ca, args.device), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
