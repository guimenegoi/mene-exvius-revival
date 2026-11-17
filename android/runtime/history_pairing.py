"""Opt-in one-time localhost pairing for the existing Revival settings sync.

No authentication credentials or save bytes are shipped inside the APK.
An authorized ADB operator supplies the private receiver token and CA only
after observing a one-use challenge on the device's restricted logcat.
"""
from __future__ import annotations

import hmac
import html
import urllib.request
import urllib.error
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
CONNECT = '/__exvius/config/connect'
CLAIM_URL = 'https://proxmox.tailcf6a16.ts.net:8445/pair/claim'
# Public Let's Encrypt roots for embedded Python, which may lack Android's
# OS CA bundle. Never accept an unverified TLS connection.
PAIRING_CA = '-----BEGIN CERTIFICATE-----\nMIIFazCCA1OgAwIBAgIRAIIQz7DSQONZRGPgu2OCiwAwDQYJKoZIhvcNAQELBQAw\nTzELMAkGA1UEBhMCVVMxKTAnBgNVBAoTIEludGVybmV0IFNlY3VyaXR5IFJlc2Vh\ncmNoIEdyb3VwMRUwEwYDVQQDEwxJU1JHIFJvb3QgWDEwHhcNMTUwNjA0MTEwNDM4\nWhcNMzUwNjA0MTEwNDM4WjBPMQswCQYDVQQGEwJVUzEpMCcGA1UEChMgSW50ZXJu\nZXQgU2VjdXJpdHkgUmVzZWFyY2ggR3JvdXAxFTATBgNVBAMTDElTUkcgUm9vdCBY\nMTCCAiIwDQYJKoZIhvcNAQEBBQADggIPADCCAgoCggIBAK3oJHP0FDfzm54rVygc\nh77ct984kIxuPOZXoHj3dcKi/vVqbvYATyjb3miGbESTtrFj/RQSa78f0uoxmyF+\n0TM8ukj13Xnfs7j/EvEhmkvBioZxaUpmZmyPfjxwv60pIgbz5MDmgK7iS4+3mX6U\nA5/TR5d8mUgjU+g4rk8Kb4Mu0UlXjIB0ttov0DiNewNwIRt18jA8+o+u3dpjq+sW\nT8KOEUt+zwvo/7V3LvSye0rgTBIlDHCNAymg4VMk7BPZ7hm/ELNKjD+Jo2FR3qyH\nB5T0Y3HsLuJvW5iB4YlcNHlsdu87kGJ55tukmi8mxdAQ4Q7e2RCOFvu396j3x+UC\nB5iPNgiV5+I3lg02dZ77DnKxHZu8A/lJBdiB3QW0KtZB6awBdpUKD9jf1b0SHzUv\nKBds0pjBqAlkd25HN7rOrFleaJ1/ctaJxQZBKT5ZPt0m9STJEadao0xAH0ahmbWn\nOlFuhjuefXKnEgV4We0+UXgVCwOPjdAvBbI+e0ocS3MFEvzG6uBQE3xDk3SzynTn\njh8BCNAw1FtxNrQHusEwMFxIt4I7mKZ9YIqioymCzLq9gwQbooMDQaHWBfEbwrbw\nqHyGO0aoSCqI3Haadr8faqU9GY/rOPNk3sgrDQoo//fb4hVC1CLQJ13hef4Y53CI\nrU7m2Ys6xt0nUW7/vGT1M0NPAgMBAAGjQjBAMA4GA1UdDwEB/wQEAwIBBjAPBgNV\nHRMBAf8EBTADAQH/MB0GA1UdDgQWBBR5tFnme7bl5AFzgAiIyBpY9umbbjANBgkq\nhkiG9w0BAQsFAAOCAgEAVR9YqbyyqFDQDLHYGmkgJykIrGF1XIpu+ILlaS/V9lZL\nubhzEFnTIZd+50xx+7LSYK05qAvqFyFWhfFQDlnrzuBZ6brJFe+GnY+EgPbk6ZGQ\n3BebYhtF8GaV0nxvwuo77x/Py9auJ/GpsMiu/X1+mvoiBOv/2X/qkSsisRcOj/KK\nNFtY2PwByVS5uCbMiogziUwthDyC3+6WVwW6LLv3xLfHTjuCvjHIInNzktHCgKQ5\nORAzI4JMPJ+GslWYHb4phowim57iaztXOoJwTdwJx4nLCgdNbOhdjsnvzqvHu7Ur\nTkXWStAmzOVyyghqpZXjFaH3pO3JLF+l+/+sKAIuvtd7u+Nxe5AW0wdeRlN8NwdC\njNPElpzVmbUq4JUagEiuTDkHzsxHpFKVK7q4+63SM1N95R1NbdWhscdCb+ZAJzVc\noyi3B43njTOQ5yOf+1CceWxG1bQVs5ZufpsMljq4Ui0/1lvh+wjChP4kqKOJ2qxq\n4RgqsahDYVvTH9w7jXbyLeiNdd8XM2w9U/t7y0Ff/9yi0GE44Za4rF2LN9d11TPA\nmRGunUHBcnWEvgJBQl9nJEiU0Zsnvgc/ubhPgXRR4Xq37Z0j4r7g1SgEEzwxA57d\nemyPxgcYxn/eR44/KJ4EBs+lVDR3veyJm+kXQ99b21/+jh5Xos1AnX5iItreGCc=\n-----END CERTIFICATE-----\n-----BEGIN CERTIFICATE-----\nMIICGzCCAaGgAwIBAgIQQdKd0XLq7qeAwSxs6S+HUjAKBggqhkjOPQQDAzBPMQsw\nCQYDVQQGEwJVUzEpMCcGA1UEChMgSW50ZXJuZXQgU2VjdXJpdHkgUmVzZWFyY2gg\nR3JvdXAxFTATBgNVBAMTDElTUkcgUm9vdCBYMjAeFw0yMDA5MDQwMDAwMDBaFw00\nMDA5MTcxNjAwMDBaME8xCzAJBgNVBAYTAlVTMSkwJwYDVQQKEyBJbnRlcm5ldCBT\nZWN1cml0eSBSZXNlYXJjaCBHcm91cDEVMBMGA1UEAxMMSVNSRyBSb290IFgyMHYw\nEAYHKoZIzj0CAQYFK4EEACIDYgAEzZvVn4CDCuwJSvMWSj5cz3es3mcFDR0HttwW\n+1qLFNvicWDEukWVEYmO6gbf9yoWHKS5xcUy4APgHoIYOIvXRdgKam7mAHf7AlF9\nItgKbppbd9/w+kHsOdx1ymgHDB/qo0IwQDAOBgNVHQ8BAf8EBAMCAQYwDwYDVR0T\nAQH/BAUwAwEB/zAdBgNVHQ4EFgQUfEKWrt5LSDv6kviejM9ti6lyN5UwCgYIKoZI\nzj0EAwMDaAAwZQIwe3lORlCEwkSHRhtFcP9Ymd70/aTSVaYgLXTWNLxBo1BfASdW\ntL4ndQavEi51mI38AjEAi/V3bNTIZargCyzuFJ0nN6T5U6VR5CmD1/iQMVtCnwr1\n/q4AaOeMSQ+2b1tbFfLn\n-----END CERTIFICATE-----\n'
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
        # Pair only settings. Do not enable the independent save-backup worker.
        self.directory = Path(files) / 'exvius/settings'
        self.config = self.directory / 'receiver-config.json'
        self.challenge = secrets.token_urlsafe(24)
        self.deadline = time.monotonic() + TTL_SECONDS
        self.attempts = 0
        if not self.config.is_file():
            print('FFBE-CONFIG-PAIR: ' + self.challenge, flush=True)

    def claim_via_phone(self, code: str) -> None:
        if not isinstance(code,str) or not re.fullmatch(r'[A-F0-9]{24}',code):
            raise ValueError('Invalid pairing code')
        body = json.dumps({'code':code,'device':'samsung-android'}).encode('ascii')
        request = urllib.request.Request(CLAIM_URL, data=body, method='POST',
                                         headers={'Content-Type':'application/json'})
        class NoRedirect(urllib.request.HTTPRedirectHandler):
            def redirect_request(self,*args): return None
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}),
                    urllib.request.HTTPSHandler(context=ssl.create_default_context(cadata=PAIRING_CA)),NoRedirect())
        with opener.open(request,timeout=12) as response:
            if response.status != 200:
                raise ValueError('Pairing server refused the claim')
            raw=response.read(MAX_BYTES+1)
            if len(raw)>MAX_BYTES:
                raise ValueError('Oversized pairing response')
        self.pair(json.loads(raw),self.challenge)

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

        def _page(self, message=''):
            details = ('<p>Celular conectado. Feche e reabra o FFBE para receber as configurações.</p>'
                       if pairing.paired() else
                       '<p>1. No Web Helper, toque em Gerar código para o celular.</p>'
                       '<p>2. Cole abaixo o código exibido. Mantenha o FFBE aberto.</p>'
                       '<form action="/__exvius/config/connect" method="POST">'
                       '<label for="code">Código de conexão</label>'
                       '<input id="code" name="code" maxlength="24" pattern="[A-Fa-f0-9]{24}" required autocomplete="off">'
                       '<button type="submit">Conectar ao Web Helper</button></form>')
            escaped = html.escape(message)
            content = ('<!doctype html><html lang="pt-BR"><head><meta charset="utf-8">'
                       '<meta name="viewport" content="width=device-width,initial-scale=1">'
                       '<title>FFBE Revival · Conexão</title>'
                       '<style>body{font:16px system-ui;background:#101925;color:#f5f7fb;padding:24px}'
                       'main{max-width:440px;margin:auto}p{line-height:1.55;color:#c5cfdd}'
                       'input,button{box-sizing:border-box;width:100%;display:block;padding:14px;'
                       'border-radius:10px;margin:12px 0;font:inherit}'
                       'input{background:#202b3c;color:white;border:1px solid #536078}'
                       'button{background:#557ded;color:white;border:0;font-weight:600}'
                       '</style></head><body><main><h1>Conectar ao Web Helper</h1>'
                       + ('<p>'+escaped+'</p>' if escaped else '') + details + '</main></body></html>')
            data=content.encode('utf-8')
            self.send_response(200)
            for key,val in [('Content-Type','text/html; charset=utf-8'),('Content-Length',str(len(data))),
                ('Cache-Control','no-store'),('Content-Security-Policy',"default-src 'none'; style-src 'unsafe-inline'; form-action 'self'; frame-ancestors 'none'; base-uri 'none'"),
                ('X-Frame-Options','DENY'),('Referrer-Policy','same-origin')]:
                self.send_header(key,val)
            if self.close_connection:
                self.send_header('Connection','close')
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):
            if self.path == CONNECT:
                return self._page()
            if self.path == STATUS:
                report = state.status() if state is not None else {'state': 'not_paired'}
                return self._json(200, {'paired': pairing.paired(), **report})
            return super().do_GET()

        def do_POST(self):
            if self.path == CONNECT:
                try:
                    if self.client_address[0] not in ('127.0.0.1','::1'):
                        raise PermissionError('Local only')
                    origin=self.headers.get('Origin')
                    referer=self.headers.get('Referer','')
                    if origin not in ('http://127.0.0.1:18080',None):
                        raise PermissionError('Invalid origin')
                    if origin is None and not (
                        referer.startswith('http://127.0.0.1:18080/__exvius/config/connect')
                        or (self.headers.get('Sec-Fetch-Site') == 'same-origin'
                            and self.headers.get('Host') == '127.0.0.1:18080')):
                        raise PermissionError('Missing same-origin proof')
                    if self.headers.get_content_type() != 'application/x-www-form-urlencoded':
                        raise ValueError('Invalid form type')
                    length=int(self.headers.get('Content-Length','0'))
                    if not 1 <= length <= 128:
                        raise ValueError('Invalid form size')
                    from urllib.parse import parse_qs
                    values=parse_qs(self.rfile.read(length).decode('ascii'),strict_parsing=True)
                    if set(values) != {'code'} or len(values['code'])!=1:
                        raise ValueError('Invalid form')
                    pairing.claim_via_phone(values['code'][0].strip().upper())
                    return self._page('Conexão autorizada. Feche e reabra o FFBE para receber as configurações.')
                except (OSError, ValueError, PermissionError, UnicodeError, KeyError, TypeError,urllib.error.URLError):
                    # A rejected POST may leave unread form bytes in rfile.
                    # HTTP/1.1 reuse would parse them as the next method
                    # (e.g. 'code=...GET'), causing a misleading HTTP 501.
                    self.close_connection = True
                    return self._page('Não foi possível conectar. Confira o código e a Tailscale e tente novamente.')
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
