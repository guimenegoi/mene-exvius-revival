#!/usr/bin/env python3
"""Private FFBE first-run ZIP cache server for Android laboratory validation.

Binds only 127.0.0.1:18082 in the LXC. Use SSH -L and adb reverse to route
Android loopback requests. No public HTTP endpoint; not a production installer.
All manifest pack hashes, names, sizes and order remain unchanged.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import stat
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

PORT = 18082
LOOPBACK = "127.0.0.1"


def pinned_data(manifest: Path, packs: Path, base: str) -> tuple[bytes, dict]:
    document = json.loads(manifest.read_text(encoding="utf-8"))
    rows = document.get("packs")
    if (document.get("schema") != 1 or not isinstance(rows, list)
            or len(rows) != {9: 19, 10: 20}.get(document.get("revision"))):
        raise ValueError("Expected manifest revision 9/19 or 10/20")
    if packs.is_symlink() or not packs.is_dir():
        raise ValueError("Unsafe pack directory")
    output: dict[str, tuple[Path, int]] = {}
    for record in rows:
        if not isinstance(record, dict):
            raise ValueError("Invalid pack entry")
        identity, digest, length = record.get("id"), record.get("sha256"), record.get("size")
        if (not isinstance(identity, str) or not re.fullmatch("[a-z0-9-]+", identity)
                or identity in output or not isinstance(digest, str)
                or not re.fullmatch("[a-f0-9]{64}", digest)
                or type(length) is not int or not (0 < length < 2 ** 31)):
            raise ValueError("Invalid pack metadata")
        source = packs / f"{identity}.zip"
        if source.is_symlink() or not source.is_file() or source.stat().st_size != length:
            raise ValueError("Missing, linked or incorrect pack " + identity)
        output[identity] = (source, length)
        record["url"] = base + "/packs/" + identity + ".zip"
    if "client-assets" not in output:
        raise ValueError("client-assets pack missing")
    return json.dumps(document, separators=(",", ":")).encode("utf-8"), output


def make_handler(data: bytes, packs: dict):
    class Handler(BaseHTTPRequestHandler):
        server_version = "FFBE-PrivateCacheLab/1"

        def log_message(self, fmt: str, *args) -> None:
            print("cache: " + fmt % args, flush=True)

        def do_HEAD(self):
            self.serve(False)

        def do_GET(self):
            self.serve(True)

        def serve(self, body: bool) -> None:
            parsed = urlsplit(self.path)
            if parsed.query or parsed.fragment:
                self.send_error(404)
                return
            if parsed.path == "/data/latest.json":
                self.send_response(200)
                self.send_header("Content-Length", str(len(data)))
                self.send_header("Content-Type", "application/json")
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                if body:
                    self.wfile.write(data)
                return
            match = re.fullmatch(r"/packs/([a-z0-9-]+)\.zip", parsed.path)
            if match is None or match.group(1) not in packs:
                self.send_error(404)
                return
            path, expected = packs[match.group(1)]
            try:
                descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
                info = os.fstat(descriptor)
                if not stat.S_ISREG(info.st_mode) or info.st_size != expected:
                    os.close(descriptor)
                    self.send_error(409, "Cache size changed")
                    return
            except OSError:
                self.send_error(409, "Unavailable cached pack")
                return
            try:
                header = self.headers.get("Range")
                offset = 0
                if header is not None:
                    parsed_range = re.fullmatch(r"bytes=(\d+)-", header)
                    if parsed_range is None:
                        self.send_error(400, "Only bytes=N- ranges supported")
                        return
                    offset = int(parsed_range.group(1))
                    if offset >= expected:
                        self.send_response(416)
                        self.send_header("Content-Range", f"bytes */{expected}")
                        self.send_header("Content-Length", "0")
                        self.end_headers()
                        return
                self.send_response(206 if header else 200)
                self.send_header("Content-Length", str(expected - offset))
                self.send_header("Content-Type", "application/zip")
                self.send_header("Accept-Ranges", "bytes")
                self.send_header("Cache-Control", "no-store")
                if header is not None:
                    self.send_header("Content-Range", f"bytes {offset}-{expected - 1}/{expected}")
                self.end_headers()
                if not body:
                    return
                with os.fdopen(os.dup(descriptor), "rb", buffering=0) as stream:
                    stream.seek(offset)
                    left = expected - offset
                    while left:
                        chunk = stream.read(min(1 << 20, left))
                        if not chunk:
                            raise OSError("Cached pack truncated during response")
                        self.wfile.write(chunk)
                        left -= len(chunk)
            except (BrokenPipeError, ConnectionResetError):
                return
            finally:
                os.close(descriptor)
    return Handler


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--packs", type=Path, required=True)
    parser.add_argument("--port", type=int, default=PORT)
    args = parser.parse_args()
    if args.port != PORT:
        parser.error("This lab source only supports port 18082")
    source = f"http://{LOOPBACK}:{PORT}"
    data, files = pinned_data(args.manifest, args.packs, source)
    server = ThreadingHTTPServer((LOOPBACK, PORT), make_handler(data, files))
    server.daemon_threads = True
    print(f"LAB-CACHE-READY {source} /data/latest.json {len(files)} files", flush=True)
    try:
        server.serve_forever(poll_interval=0.2)
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
