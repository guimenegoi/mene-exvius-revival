"""Authenticated panel issues short-lived one-use codes; only the phone claims credentials.

The Web Helper browser never sees the receiver token or its certificate.
Codes live in process memory, are consumed once and cannot be replayed.
"""
from __future__ import annotations
import hashlib
import hmac
import json
import secrets
import threading
import time
from pathlib import Path

ISSUER_TTL = 600
MAX_CODE_LENGTH = 32
ENDPOINT = 'https://proxmox.tailcf6a16.ts.net:18447'

class PairCodes:
    def __init__(self, credential_dir: Path):
        self.credential_dir = Path(credential_dir)
        self.lock = threading.Lock()
        self._code_hash: bytes | None = None
        self._expires = 0.0
        self._attempts = 0
        self._budget: dict[str, list[float]] = {}

    def create(self) -> str:
        code = secrets.token_hex(12).upper()
        with self.lock:
            self._code_hash = hashlib.sha256(code.encode()).digest()
            self._expires = time.monotonic() + ISSUER_TTL
            self._attempts = 0
        return code

    def claim(self, code: str, remote: str, device: str) -> dict:
        if not isinstance(code,str) or len(code) > MAX_CODE_LENGTH or not isinstance(device,str):
            raise PermissionError('Pairing refused')
        now = time.monotonic()
        with self.lock:
            recent = [x for x in self._budget.get(remote, []) if now - x < ISSUER_TTL]
            if len(recent) >= 8:
                raise PermissionError('Pairing refused')
            self._budget[remote] = recent + [now]
            self._attempts += 1
            expected = self._code_hash
            if (not expected or now > self._expires or self._attempts > 10
                    or not hmac.compare_digest(expected, hashlib.sha256(code.encode()).digest())
                    or device != 'samsung-android'):
                raise PermissionError('Pairing refused')
            # Invalidate immediately, even if a local credential file fails.
            self._code_hash = None
        root = self.credential_dir
        token_file = root / 'token'
        cert_file = root / 'cert.pem'
        for path in (token_file, cert_file):
            if path.is_symlink() or not path.is_file():
                raise ValueError('Receiver credentials unavailable')
        token = token_file.read_text('utf-8').strip()
        cert = cert_file.read_text('ascii')
        if not 32 <= len(token) <= 256 or 'BEGIN CERTIFICATE' not in cert:
            raise ValueError('Receiver credentials invalid')
        return {'endpoint': ENDPOINT, 'device': device,
                'token': token, 'ca_pem': cert}
