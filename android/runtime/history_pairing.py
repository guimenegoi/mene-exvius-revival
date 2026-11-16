"""Opt-in one-time localhost pairing for the existing Revival settings sync.

No authentication credentials or save bytes are shipped inside the APK.
An authorized ADB operator supplies the private receiver token and CA only
after observing a one-use challenge on the device's restricted logcat.
"""
from __future__ import annotations

import hmac
import json
import os
import re
import secrets
import ssl
import tempfile
import time
from pathlib import Path
from urllib.parse import urlsplit

PAIR = '/__exvius/config/pair'
STATUS = '/__exvius/config/status'
ENDPOINT = 'https://proxmox.tailcf6a16.ts.net:18447'
MAX_BYTES = 8192
ATTEMPTS = 6
TTL_SECONDS = 600
DEVICE = re.compile(r'[a-zA-Z0-9_-]{1,64}\Z')


def _private_write(path: Path, contents: bytes) -> None:
    if path.is_symlink():
        raise ValueError('Unsafe pairing destination')
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    if path.parent.is_symlink():
        raise ValueError('Unsafe pairing directory')
    os.chmod(path.parent, 0o700)
    fd, tmp = tempfile.mkstemp(prefix='.pair-', dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as stream:
            os.fchmod(stream.fileno(), 0o600)
            stream.write(contents)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(tmp, path)
    finally:
        Path(tmp).unlink(missing_ok=True)


def validate(body: object) -> tuple[str, str, bytes]:
    if not isinstance(body, dict) or set(body) != {'endpoint', 'device', 'token', 'ca_pem'}:
        raise ValueError('Invalid pairing document')
    endpoint, device, token, pem = (body[x] for x in ('endpoint', 'device', 'token', 'ca_pem'))
    if not all(isinstance(x, str) for x in (endpoint, device, token, pem)):
        raise ValueError('Invalid pairing types')
    if endpoint != ENDPOINT or not DEVICE.fullmatch(device) or not 32 <= len(token) <= 256:
        raise ValueError('Untrusted receiver or credentials')
    if len(pem) > 4096 or 'BEGIN CERTIFICATE' not in pem:
        raise ValueError('Invalid receiver CA')
    ssl.PEM_cert_to_DER_cert(pem)
    return device, token, pem.encode('ascii')


class Pairing:
    def __init__(self, files: Path):
        self.directory = Path(files) / 'exvius/backup'
        self.config = self.directory / 'config.json'
        self.challenge = secrets.token_urlsafe(24)
        self.deadline = time.monotonic() + TTL_SECONDS
        self.attempts = 0
        if not self.config.is_file():
            print('FFBE-CONFIG-PAIR: ' + self.challenge, flush=True)

    def paired(self) -> bool:
        return self.config.is_file() and not self.config.is_symlink()

    def pair(self, payload: dict, code: str) -> None:
        self.attempts += 1
        if (self.paired() or self.attempts > ATTEMPTS or time.monotonic() > self.deadline
                or not isinstance(code, str) or not hmac.compare_digest(code, self.challenge)):
            raise PermissionError('Pairing refused')
        device, token, cert = validate(payload)
        cert_path = self.directory / 'receiver-ca.pem'
        token_path = self.directory / 'receiver-token.txt'
        # Persist credentials only after the challenge and strict validation.
        _private_write(cert_path, cert)
        _private_write(token_path, token.encode('utf-8'))
        _private_write(self.config, json.dumps({
            'enabled': True, 'url': ENDPOINT, 'device': device,
            'token_file': str(token_path), 'ca_file': str(cert_path),
        }, sort_keys=True).encode('utf-8'))
        self.challenge = ''
        print('FFBE-CONFIG: paired; restart required to enable synchronization', flush=True)


def wrap_handler(base, pairing: Pairing, state) -> type:
    """Preserve all normal Revival routes, intercept maintenance paths only."""
    class Handler(base):
        def _json(self, status: int, body: dict):
            data = json.dumps(body, sort_keys=True).encode('utf-8')
            self.send_response(status)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(data)))
            self.send_header('Cache-Control', 'no-store')
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):
            if self.path == STATUS:
                report = state.status() if state is not None else {'state': 'not_paired'}
                return self._json(200, {'paired': pairing.paired(), **report})
            return super().do_GET()

        def do_POST(self):
            if self.path != PAIR:
                return super().do_POST()
            try:
                if self.client_address[0] not in ('127.0.0.1', '::1'):
                    raise PermissionError('Loopback only')
                length = int(self.headers.get('Content-Length', '0'))
                if not 0 < length <= MAX_BYTES or self.headers.get_content_type() != 'application/json':
                    raise ValueError('Invalid pairing length or type')
                payload = json.loads(self.rfile.read(length))
                pairing.pair(payload, self.headers.get('X-FFBE-Pair-Code', ''))
                return self._json(201, {'paired': True, 'restart_required': True})
            except (OSError, ValueError, PermissionError, KeyError, UnicodeError, TypeError):
                return self._json(403, {'error': 'pairing refused'})

    return Handler
