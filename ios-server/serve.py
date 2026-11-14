#!/usr/bin/env python3
"""Run the Exvius Offline game server for a stock (unmodified) game client, such as the iPhone app.

The Android build runs this same engine inside the app. Here it runs as a network server:

  * HTTPS on 443 and HTTP on 80 for the game API and its file downloads (any host name; the
    engine answers by path);
  * a small DNS responder on 53/udp that answers the game's host names (gumi.sg, exvius.com and
    their subdomains) with this machine's Tailscale address, so a Tailscale split-DNS entry can
    send the phone here and nowhere else;
  * http://<address>/ca.mobileconfig to install the root certificate on the phone.

Folders (both are volumes in docker-compose.yml):
  /srv/ffbe/data          the unpacked game data (fetch_data.py fills it)
  /srv/ffbe/server-root   saves, certificates and request logs
"""
from __future__ import annotations

import datetime
import os
import socket
import ssl
import struct
import sys
import threading
import time
from http.server import ThreadingHTTPServer
from pathlib import Path

APP = Path(__file__).resolve().parent
ENGINE = Path(os.environ.get('FFBE_ENGINE', APP / 'server'))
DATA = Path(os.environ.get('FFBE_DATA_DIR', '/srv/ffbe/data'))
ROOT = Path(os.environ.get('FFBE_SERVER_ROOT', '/srv/ffbe/server-root'))
SLOT = os.environ.get('FFBE_SAVE_SLOT', 'campaign')
DNS_SUFFIXES = tuple(s.strip().lower().strip('.') for s in
                     os.environ.get('FFBE_DNS_SUFFIXES', 'gumi.sg,exvius.com').split(',') if s.strip())
REQUEST_LOG_DAYS = float(os.environ.get('FFBE_REQUEST_LOG_DAYS', '3'))
# Size caps (2026-11-07): request records are also trimmed to this many MB, oldest first, and only the newest
# client reports (the game's uploaded logs, 2-6 MB each, one or two per launch) are kept.
REQUEST_LOG_MB = float(os.environ.get('FFBE_REQUEST_LOG_MB', '300'))
CLIENT_REPORTS_KEEP = int(os.environ.get('FFBE_CLIENT_REPORTS_KEEP', '30'))


def log(message: str) -> None:
    print('[ios-server] ' + message, flush=True)


# --------------------------------------------------------------------------------------------------
# Engine configuration: the same layout and switches the Android app uses (android_game.start and
# local_game.LocalGame), so the server behaves the way the app's built-in server does.
# --------------------------------------------------------------------------------------------------
def configure_engine() -> None:
    static, native = DATA / 'static', DATA / 'native'
    # Keep authored CDN data outside the Android client's installed resource
    # tree; the client-side files are immutable inputs, not an overlay.
    overlay = ROOT / 'overlay' if os.environ.get('FFBE_ANDROID_EMBEDDED') == '1' else native
    missing = [p for p in (static / 'mst_decoded', native / 'mst', native / 'common_lang') if not p.is_dir()]
    if missing:
        log('game data is missing: ' + ', '.join(map(str, missing)))
        log('run the data download first:  docker compose run --rm server fetch-data')
        sys.exit(2)
    for key, path in (('MST_DIR', static / 'mst_decoded'), ('TEXT_DIR', static / 'text_decoded'),
                      ('ART_ROOT', static / 'cpk_extract'), ('COMMUNITY_ART_ROOT', static / 'gacha_community/art'),
                      ('VERSION_TABLE_XML', static / 'client/shared_prefs/gamedata.xml'),
                      # The unpacked native tree is the client's own `files/` folder: serve it and use it
                      # as the overlay, exactly as the Android app does once its data is installed.
                      ('CDN_ROOT', native), ('CDN_OVERLAY', overlay)):
        os.environ[key] = str(path)
    os.environ['FFBE_DATA'] = str(ROOT)
    # The deal banners' art, downloaded once on startup (source/server/deal_art.py).
    os.environ.setdefault('DEAL_ART_ROOT', str(ROOT / 'deal_art'))
    # The summon art pack, part of the game data (source/server/art_pack.py).
    os.environ.setdefault('SUMMON_ART_PACK_ROOT', str(static / 'summon_art'))
    os.environ['OUT_REQUESTS'] = str(ROOT / 'requests')
    for key, value in (('GACHA_ONLY', 'all'), ('GACHA_CAMPAIGN', 'all'), ('EXVIUS_SUMMON_ARCHIVE', '1'),
                       ('EXVIUS_EVENT_ARCHIVE', '1'), ('GACHA_STANDARD', '1'), ('GACHA_CATALOGUE', '1'),
                       ('EXVIUS_SUMMON_ROTATION', '1'),
                       # Summons, Vortex and shops follow Global's history (source/server/replay.py).
                       ('EXVIUS_REPLAY', '1'),
                       # Home screen banners from this replay week's events (replay_notices.py).
                       ('MARQUEE_FLAG', '1'),
                       # Name padded summon detail art afresh so phones drop the squashed copy (banner_fit.py).
                       ('EXVIUS_IOS_BANNER_FIT_NAMES', '1'),
                       # A stock client keeps tables of its own; make it take this server's whole set.
                       ('EXVIUS_TABLE_VERSION_OFFSET', '200000'),  # raise it to make the phone re-download every table
                       # The game's own error log upload (server/client-reports/), off by default. 1 turns it on for
                       # troubleshooting: the game then uploads its log (tens of MB) once per launch.
                       ('EXVIUS_CLIENT_REPORTS', '0'),
                       # Serve rebuilt tables with LF line endings; the iPhone client rejects CRLF.
                       ('EXVIUS_TABLE_LF', '1'),
                       # Re-flag HCA-MX waveforms in the Android sound banks as plain HCA for the iPhone.
                       ('EXVIUS_IOS_HCA', '1'),
                       # Remove the Android banks' HCA cipher (type 1) for the iPhone. See sound_compat.py.
                       ('EXVIUS_IOS_HCA_PLAIN', '1'),
                       # No free 8th-Anniversary 10+1 ticket in the mail every day.
                       ('ANNIVERSARY_TICKET', '0'),
                       # Download the packs the first battle reads before the tutorial starts ('all' = everything).
                       ('EXVIUS_EARLY_RESOURCES', 'resources_common.cpk,resources.cpk')):
        os.environ.setdefault(key, value)
    ROOT.mkdir(parents=True, exist_ok=True)
    sys.path.insert(0, str(ENGINE))


def start_engine():
    import capture_server
    result = capture_server.main(['--data', str(ROOT), '--state', SLOT], in_process=True)
    if result != 0:
        log(f'engine initialisation failed ({result})')
        sys.exit(3)
    capture_server.State.cdn_root = str(DATA / 'native')
    capture_server.State.cdn_overlay = str(
        ROOT / 'overlay' if os.environ.get('FFBE_ANDROID_EMBEDDED') == '1'
        else DATA / 'native'
    )
    # Unit pictures for the Drop Rates and News pages, copied out of the unit packs in the background
    # (source/server/unit_art.py; EXVIUS_NOTICE_ART=0 turns it off).
    import unit_art
    unit_art.start(capture_server.State.cdn_overlay, capture_server.State.cdn_root)
    # Index the native image folders the way the Android app does.
    from ffbe_gacha import BANNER_ART_ROOTS, _BANNER_ART_INDEX
    for relative in ('homeMarquee', 'en/sd/static_banner', 'common_lang/sd/static_banner'):
        folder = str(DATA / 'native' / relative)
        if folder not in BANNER_ART_ROOTS:
            BANNER_ART_ROOTS.append(folder)
    _BANNER_ART_INDEX.clear()
    return capture_server


# --------------------------------------------------------------------------------------------------
# HTTP(S)
# --------------------------------------------------------------------------------------------------
def make_handler(capture_server, profile: bytes, ca_der: bytes):
    base = capture_server.Handler

    class Handler(base):
        def _send_static(self, body: bytes, content_type: str, filename: str) -> None:
            self.send_response(200)
            self.send_header('Content-Type', content_type)
            self.send_header('Content-Disposition', f'attachment; filename="{filename}"')
            self.send_header('Content-Length', str(len(body)))
            self.send_header('Cache-Control', 'no-store')
            self.end_headers()
            if self.command != 'HEAD':
                self.wfile.write(body)

        def do_GET(self):
            path = self.path.split('?', 1)[0]
            if path in ('/ca.mobileconfig', '/__exvius/ca.mobileconfig'):
                return self._send_static(profile, 'application/x-apple-aspen-config', 'exvius-offline.mobileconfig')
            if path in ('/ca.crt', '/__exvius/ca.crt'):
                return self._send_static(ca_der, 'application/x-x509-ca-cert', 'exvius-offline-root.crt')
            if path == '/__exvius/hello':
                # Open https://v900-lapis.gumi.sg/__exvius/hello on the phone: if this page loads with no
                # warning, DNS and the certificate are both set up correctly.
                body = (b'<!doctype html><meta name="viewport" content="width=device-width">'
                        b'<body style="font:17px -apple-system,sans-serif;padding:24px">'
                        b'<h2>Exvius Offline server</h2><p>Reachable. You can open the game.</p></body>')
                self.send_response(200)
                self.send_header('Content-Type', 'text/html; charset=utf-8')
                self.send_header('Content-Length', str(len(body)))
                self.send_header('Cache-Control', 'no-store')
                self.end_headers()
                if self.command != 'HEAD':
                    self.wfile.write(body)
                return
            return base.do_GET(self)

    return Handler


class Server(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True
    tls: ssl.SSLContext | None = None
    label = 'HTTP'

    def get_request(self):
        sock, addr = super().get_request()
        if self.tls is not None:
            # Handshake later, on the request's own thread, so one slow client cannot stall the listener.
            sock = self.tls.wrap_socket(sock, server_side=True, do_handshake_on_connect=False)
        return sock, addr

    def finish_request(self, request, client_address):
        if self.tls is not None:
            try:
                request.settimeout(30)
                request.do_handshake()
                request.settimeout(None)
            except (ssl.SSLError, OSError) as exc:
                log(f'TLS handshake failed from {client_address[0]}: {exc!r}')
                return
        super().finish_request(request, client_address)

    def handle_error(self, request, client_address):
        exc = sys.exc_info()[1]
        if isinstance(exc, (ConnectionError, ssl.SSLError, TimeoutError)):
            return  # the client went away; nothing to report
        super().handle_error(request, client_address)


def serve(port: int, handler, tls: ssl.SSLContext | None = None) -> Server:
    server = Server(('0.0.0.0', port), handler)
    server.tls = tls
    server.label = 'HTTPS' if tls else 'HTTP'
    threading.Thread(target=server.serve_forever, name=f'{server.label}-{port}', daemon=True).start()
    log(f'{server.label} listening on port {port}')
    return server


# --------------------------------------------------------------------------------------------------
# DNS: answer only the game's names, with this machine's Tailscale address.
# --------------------------------------------------------------------------------------------------
def tailscale_address() -> str | None:
    fixed = os.environ.get('FFBE_ADVERTISE_IP', '').strip()
    if fixed:
        return fixed
    # The route to Tailscale's own resolver goes out through the tailnet interface, so the socket's
    # source address is this node's Tailscale IPv4. No packet is sent.
    try:
        probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        probe.connect(('100.100.100.100', 53))
        address = probe.getsockname()[0]
        probe.close()
    except OSError:
        return None
    first, second = (int(part) for part in address.split('.')[:2])
    return address if first == 100 and 64 <= second <= 127 else None


def _question(packet: bytes):
    names, offset = [], 12
    while True:
        length = packet[offset]
        if length == 0:
            offset += 1
            break
        if length & 0xC0:
            raise ValueError('compressed question name')
        names.append(packet[offset + 1:offset + 1 + length].decode('ascii', 'replace'))
        offset += 1 + length
    qtype, qclass = struct.unpack('!HH', packet[offset:offset + 4])
    return '.'.join(names).lower(), qtype, qclass, packet[12:offset + 4]


def dns_answer(packet: bytes, address_for) -> bytes | None:
    if len(packet) < 17:
        return None
    ident, flags = struct.unpack('!HH', packet[:4])
    if flags & 0x8000:
        return None  # a response, not a query
    try:
        name, qtype, qclass, question = _question(packet)
    except (IndexError, ValueError, struct.error):
        return struct.pack('!HHHHHH', ident, 0x8001, 0, 0, 0, 0)  # FORMERR
    ours = any(name == suffix or name.endswith('.' + suffix) for suffix in DNS_SUFFIXES)
    rd = flags & 0x0100
    if not ours:
        return struct.pack('!HHHHHH', ident, 0x8005 | rd, 1, 0, 0, 0) + question  # REFUSED
    address = address_for()
    answers = b''
    if qtype in (1, 255) and qclass == 1 and address:
        answers = struct.pack('!HHHIH', 0xC00C, 1, 1, 60, 4) + socket.inet_aton(address)
    # Authoritative answer; no AAAA, so the phone connects over IPv4.
    header = struct.pack('!HHHHHH', ident, 0x8400 | rd, 1, 1 if answers else 0, 0, 0)
    return header + question + answers


def serve_dns() -> None:
    cached = {'ip': None}

    def address_for():
        if cached['ip'] is None:
            cached['ip'] = tailscale_address()
            if cached['ip']:
                log(f'DNS: answering {", ".join(DNS_SUFFIXES)} with {cached["ip"]}')
        return cached['ip']

    def loop():
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.bind(('0.0.0.0', int(os.environ.get('FFBE_DNS_PORT', '53'))))
        except OSError as exc:
            log(f'DNS responder disabled: {exc}')
            return
        log('DNS listening on port ' + os.environ.get('FFBE_DNS_PORT', '53') + '/udp')
        while True:
            try:
                packet, peer = sock.recvfrom(1500)
                reply = dns_answer(packet, address_for)
                if reply:
                    sock.sendto(reply, peer)
            except Exception as exc:  # noqa: BLE001 - one bad packet must not stop the responder
                log(f'DNS: {exc!r}')

    if address_for() is None:
        log('DNS: Tailscale address not found yet; will keep looking (set FFBE_ADVERTISE_IP to fix it)')
    threading.Thread(target=loop, name='dns', daemon=True).start()


# --------------------------------------------------------------------------------------------------
# Housekeeping
# --------------------------------------------------------------------------------------------------
def _files_oldest_first(folder: Path) -> list:
    out = []
    if folder.is_dir():
        for entry in folder.iterdir():
            try:
                if entry.is_file():
                    st = entry.stat()
                    out.append((st.st_mtime, st.st_size, entry))
            except OSError:
                pass
    return sorted(out, key=lambda row: row[0])


def _unlink(path: Path) -> bool:
    try:
        path.unlink()
        return True
    except OSError:
        return False


def prune_once() -> None:
    """Keep the server's own records bounded: request records by age (FFBE_REQUEST_LOG_DAYS) and total size
    (FFBE_REQUEST_LOG_MB), client reports by count (FFBE_CLIENT_REPORTS_KEEP). Oldest go first."""
    requests = ROOT / 'requests'
    cutoff = time.time() - REQUEST_LOG_DAYS * 86400
    rows = _files_oldest_first(requests)
    old = sum(_unlink(p) for mtime, _, p in rows if mtime < cutoff)
    rows = [row for row in rows if row[0] >= cutoff]
    total, limit, big = sum(size for _, size, _ in rows), REQUEST_LOG_MB * 1024 * 1024, 0
    for _, size, path in rows:
        if total <= limit:
            break
        if _unlink(path):
            total -= size
            big += 1
    reports = _files_oldest_first(ROOT / 'client-reports')
    extra = max(0, len(reports) - max(0, CLIENT_REPORTS_KEEP))
    gone = sum(_unlink(p) for _, _, p in reports[:extra])
    if old or big or gone:
        log(f'housekeeping: removed {old} request log(s) older than {REQUEST_LOG_DAYS:g} days, '
            f'{big} more to stay under {REQUEST_LOG_MB:g} MB, {gone} client report(s) beyond the newest '
            f'{CLIENT_REPORTS_KEEP}')


def prune_request_logs() -> None:
    """Run `prune_once` at startup and every hour."""

    def loop():
        while True:
            try:
                prune_once()
            except Exception as exc:  # noqa: BLE001 - housekeeping must never stop the server
                log(f'housekeeping failed: {exc!r}')
            time.sleep(3600)

    threading.Thread(target=loop, name='prune', daemon=True).start()


def main() -> int:
    configure_engine()
    import certs
    paths = certs.ensure(ROOT / 'certs')
    capture_server = start_engine()
    # Build the iPhone's Vortex banner pack now (a few seconds, cached in server-root/ios-cache), rather than
    # during the first login that asks for it. See source/server/ios_art.py.
    def build_art():
        import event_archive
        import ios_tables
        # Banners of the events added by event_history.json: in the game data since 2026-11-13; downloaded
        # from the wiki only when EXVIUS_EVENT_ART_FETCH=1 asks for it.
        if os.environ.get('EXVIUS_EVENT_ART_FETCH', '0') == '1':
            event_archive.fetch_added_art(log=log)
        ios_tables.art()
    threading.Thread(target=build_art, name='ios-art', daemon=True).start()

    def fetch_deal_art():
        import deal_art
        deal_art.fetch(log=log)   # the deal banners' art (gacha_deals.json), once; see source/server/deal_art.py
    threading.Thread(target=fetch_deal_art, name='deal-art', daemon=True).start()
    tls = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    tls.minimum_version = ssl.TLSVersion.TLSv1_2
    tls.load_cert_chain(paths['leaf_chain'], paths['leaf_key'])
    handler = make_handler(capture_server, paths['profile'].read_bytes(), paths['ca_der'].read_bytes())
    serve(int(os.environ.get('FFBE_HTTPS_PORT', '443')), handler, tls)
    serve(int(os.environ.get('FFBE_HTTP_PORT', '80')), handler)
    serve_dns()
    prune_request_logs()
    ip = tailscale_address()
    where = ip or '<this node\'s Tailscale IP>'
    log(f'ready. Certificate profile for the phone: http://{where}/ca.mobileconfig')
    log('leaf certificate valid until ' + paths['leaf_expires'].strftime('%Y-%m-%d'))
    from gacha_rotation import enabled, week
    if enabled():
        number, start, end = week()
        log(f'summon rotation on: week {number}, next change {end:%a %Y-%m-%d %H:%M %Z}')
    renew_at = paths['leaf_expires'] - datetime.timedelta(days=30)
    while True:
        time.sleep(3600)
        if datetime.datetime.now(datetime.timezone.utc) >= renew_at:
            log('leaf certificate is due for renewal; restarting to renew it')
            return 0  # the container restarts and certs.ensure issues a new leaf


if __name__ == '__main__':
    sys.exit(main())
