"""Vortex banner art for the stock iPhone app: the archive's PNGs, packed into the game's own banner CPK.

`serve_event_gate` (ffbe_player.py) names each Vortex tile's art after the archive's banners
(`event_<area>.png`, `event_art.json`), and those PNGs ship loose in `en/sd/area/`. `GateScene` loads a tile
image through the CRI file loader, which only searches mounted CPKs, and never downloads a loose file. On
Android, `source/exvius/menu_assets.js` hooks the texture reader and hands it the loose PNG. The iPhone has
no hook, so the Event tab drew empty frames and the Enhance tab crashed (iOS crash report 2026-11-05:
SIGSEGV on a null texture right after laying out "Chamber of Experience", art `event_226.png`).

This module rebuilds the English Vortex banner pack `en/sd/area/spdungeon1.cpk` (resource 6108101) with
every original file plus the archive's PNGs, under a new version, so the phone downloads and mounts it:

- the CPK keeps the original's layout: masked `@UTF` header and TOC, file names in the TOC sorted
  case-insensitively (upper case), `FileOffset` relative to the TOC, 8-byte file alignment, no CRCs;
- `ios_tables.py` raises the pack's English version (`86SWOBTb` in `F_RESOURCE_VERSION_MST_LOCALIZE`) and
  its English size (`MLOSu5E0` in `F_RESOURCE_CHECKSUM_MST`);
- the built pack is cached in the server root (`ios-cache/`), keyed on its contents.
"""
from __future__ import annotations

import glob
import hashlib
import json
import os
import re
import struct
import threading

PACK = "spdungeon1.cpk"
RESOURCE_ID = "6108101"
VERSION_FIELD = "86SWOBTb"     # English file version in F_RESOURCE_VERSION_MST_LOCALIZE
SIZE_FIELD = "MLOSu5E0"        # English file size in F_RESOURCE_CHECKSUM_MST
_HERE = os.path.dirname(os.path.abspath(__file__))
_LOCK = threading.Lock()
_CACHE: dict = {}
BUILDER = "2"                  # change to rebuild every cached pack (2: header FileSize/TotalDataSize set)


def enabled() -> bool:
    return os.environ.get("EXVIUS_IOS_VORTEX_ART", "1") == "1"


# --- CRI @UTF ------------------------------------------------------------------------------------------

def _mask(data: bytes) -> bytes:
    """CRI's @UTF XOR stream. Symmetric: masks a plain table and unmasks a masked one."""
    out, m = bytearray(len(data)), 0x655F
    for i, c in enumerate(data):
        out[i] = c ^ (m & 0xFF)
        m = (m * 0x4115) & 0xFFFFFFFF
    return bytes(out)


def _plain(data: bytes) -> bytes:
    return data if data[:4] == b"@UTF" else _mask(data)


_SIZES = {0: 1, 1: 1, 2: 2, 3: 2, 4: 4, 5: 4, 6: 8, 7: 8, 8: 4, 0xA: 4, 0xB: 8}
_FMT = {0: ">B", 1: ">b", 2: ">H", 3: ">h", 4: ">I", 5: ">i", 6: ">Q", 7: ">q", 8: ">f", 0xA: ">I", 0xB: ">II"}


def _cells(utf: bytes):
    """Columns and row cells of a plain @UTF table: ([(name, storage, type)], [{name: (abs offset, value)}])."""
    b = 8
    rows_off, str_off, _data_off, _name_off = struct.unpack_from(">HIII", utf, b + 2)
    ncols, row_len, nrows = struct.unpack_from(">HHI", utf, b + 16)

    def cstr(o):
        p = b + str_off + o
        return utf[p:utf.index(b"\0", p)].decode("utf-8")
    cols, p = [], b + 24
    for _ in range(ncols):
        flags = utf[p]
        name = cstr(struct.unpack_from(">I", utf, p + 1)[0])
        p += 5
        storage, typ = flags & 0xF0, flags & 0x0F
        const = None
        if storage == 0x30:
            const = struct.unpack_from(_FMT[typ], utf, p)
            p += _SIZES[typ]
        cols.append((name, storage, typ, const))
    rows = []
    for r in range(nrows):
        q = b + rows_off + r * row_len
        row = {}
        for name, storage, typ, _ in cols:
            if storage == 0x50:
                value = struct.unpack_from(_FMT[typ], utf, q)
                if typ == 0xA:
                    value = cstr(value[0])
                elif typ != 0xB:
                    value = value[0]
                row[name] = (q, value)
                q += _SIZES[typ]
        rows.append(row)
    return cols, rows


def _toc_table(entries) -> bytes:
    """A plain `CpkTocInfo` @UTF table in the original's column layout."""
    pool = bytearray(b"<NULL>\0")
    offsets = {}

    def string(s):
        if s not in offsets:
            offsets[s] = len(pool)
            pool.extend(s.encode("utf-8") + b"\0")
        return offsets[s]
    table_name = string("CpkTocInfo")
    empty = len(pool)
    pool.extend(b"\0")
    columns = [("DirName", 0x3A, struct.pack(">I", empty)), ("FileName", 0x5A, b""),
               ("FileSize", 0x54, b""), ("ExtractSize", 0x54, b""), ("FileOffset", 0x56, b""),
               ("ID", 0x54, b""), ("UserString", 0x3A, struct.pack(">I", 0))]
    schema = bytearray()
    for name, flags, const in columns:
        schema += bytes([flags]) + struct.pack(">I", string(name)) + const
    rows = bytearray()
    for e in entries:
        rows += struct.pack(">IIIQI", string(e["name"]), e["size"], e["extract"], e["offset"], e["id"])
    rows_off = 24 + len(schema)
    str_off = rows_off + len(rows)
    body_len = str_off + len(pool)
    body_len += -body_len % 8
    data_off = body_len
    body = bytearray(struct.pack(">HHIIIHHI", 0, rows_off, str_off, data_off, table_name, len(columns), 24,
                                 len(entries)))
    body += schema + rows + pool
    body += b"\0" * (body_len - len(body))
    return b"@UTF" + struct.pack(">I", len(body)) + bytes(body)


# --- the pack ------------------------------------------------------------------------------------------

def art_names() -> list[str]:
    """Every image the server names on a Vortex tile, page or raid menu."""
    names = set()
    try:
        with open(os.path.join(_HERE, "event_art.json"), encoding="utf-8") as fh:
            art = json.load(fh)
        for section in ("events", "dungeons"):
            for row in art.get(section, {}).values():
                if isinstance(row, dict) and row.get("filename"):
                    names.add(row["filename"])
    except (OSError, ValueError):
        pass
    try:
        import event_archive
        names.update(event_archive.added_art_names())   # events added by event_history.json
    except Exception:  # noqa: BLE001 -- the archive's own art still packs
        pass
    try:
        with open(os.path.join(_HERE, "raid_archive.json"), encoding="utf-8") as fh:
            for event in json.load(fh).get("events", []):
                if event.get("menu_background"):
                    names.add(event["menu_background"])
    except (OSError, ValueError):
        pass
    return sorted(n for n in names if re.fullmatch(r"[A-Za-z0-9_.\-]+\.(?:png|jpe?g)", n))


def source_pack(*roots) -> str | None:
    for root in roots:
        if root:
            hits = glob.glob(os.path.join(root, "en", "sd", "area", f"Ver*_{PACK}"))
            if os.environ.get("FFBE_ANDROID_EMBEDDED") == "1":
                # Exact original from data-010.zip, never an earlier build.
                hits = [p for p in hits if os.path.basename(p) == "Ver461_spdungeon1.cpk"]
            if hits:
                return max(hits, key=lambda p: int(re.search(r"Ver(\d+)_", os.path.basename(p)).group(1)))
    return None


def _loose(name, *roots):
    for root in roots:
        if root:
            path = os.path.join(root, "en", "sd", "area", name)
            if os.path.isfile(path):
                return path
    return None


def plan(*roots):
    """(source pack, [(name, path)] to add, signature) or None when there is nothing to do."""
    if not enabled():
        return None
    src = source_pack(*roots)
    if not src:
        return None
    adds = [(n, p) for n in art_names() for p in [_loose(n, *roots)] if p]
    if not adds:
        return None
    digest = hashlib.sha256()
    digest.update(f"{BUILDER}|{os.path.basename(src)}|{os.path.getsize(src)}".encode())
    for name, path in adds:
        digest.update(f"|{name}:{os.path.getsize(path)}".encode())
    return src, adds, digest.hexdigest()[:16]


def bump(*roots) -> int:
    """Added to the pack's English version. 0 when the pack is not rebuilt."""
    p = plan(*roots)
    return 1000 + int(p[2], 16) % 1000 if p else 0


def build(src: str, adds, out_path: str) -> dict:
    """Write the rebuilt pack to `out_path`. Returns {"files", "added", "size"}."""
    with open(src, "rb") as fh:
        head16 = fh.read(16)
        if head16[:4] != b"CPK ":
            raise ValueError("not a CPK")
        hsize = struct.unpack_from("<Q", head16, 8)[0]
        header = _plain(fh.read(hsize))
        _, hrows = _cells(header)
        h = {k: v[1] for k, v in hrows[0].items()}
        toc_off, content_off, content_size = h["TocOffset"], h["ContentOffset"], h["ContentSize"]
        fh.seek(toc_off)
        toc_head = fh.read(16)
        if toc_head[:4] != b"TOC ":
            raise ValueError("no TOC")
        toc = _plain(fh.read(struct.unpack_from("<Q", toc_head, 8)[0]))
        _, trows = _cells(toc)
        entries = [{k: v[1] for k, v in row.items()} for row in trows]
        if any(e.get("DirName") for e in entries):
            raise ValueError("pack has directories; not supported")
        have = {e["FileName"].upper() for e in entries}
        new_files = [(n, p) for n, p in adds if n.upper() not in have]
        # Layout: header at 0, TOC at the same offset, content right after the TOC (2 KiB aligned).
        out_entries = [{"name": e["FileName"], "size": e["FileSize"], "extract": e["ExtractSize"],
                        "offset": e["FileOffset"], "id": e["ID"]} for e in entries]
        next_id = max((e["ID"] for e in entries), default=-1) + 1
        tail = content_size
        for name, path in new_files:
            tail += -tail % 8
            size = os.path.getsize(path)
            out_entries.append({"name": name, "size": size, "extract": size, "offset": tail, "id": next_id,
                                "path": path})
            next_id += 1
            tail += size
        out_entries.sort(key=lambda e: e["name"].upper())
        toc_table = _toc_table(out_entries)
        new_content_off = toc_off + 16 + len(toc_table)
        new_content_off += -new_content_off % 2048
        shift = new_content_off - content_off
        for e in out_entries:
            e["offset"] += content_off - toc_off if "path" in e else 0   # appended: relative to old content
            e["offset"] += shift
        toc_table = _toc_table(out_entries)       # same length, final offsets
        # Header: same table, new numbers, patched in place.
        header = bytearray(header)
        sum_file = sum(e["size"] for e in out_entries)
        sum_extract = sum(e["extract"] for e in out_entries)
        values = {"ContentOffset": new_content_off, "ContentSize": tail, "TotalDataSize": tail,
                  "TocSize": 16 + len(toc_table),
                  "Files": len(out_entries), "EnabledPackedSize": 2 * sum_extract,
                  "EnabledDataSize": sum_file + sum_extract}
        cols = {c[0]: c for c in _cells(bytes(header))[0]}
        for name, value in values.items():
            if name in hrows[0]:
                at = hrows[0][name][0]
                struct.pack_into(_FMT[cols[name][2]], header, at, value)
        tmp = out_path + ".tmp"
        os.makedirs(os.path.dirname(out_path), exist_ok=True)
        with open(tmp, "wb") as out:
            out.write(head16)
            out.write(_mask(bytes(header)))
            pad = toc_off - out.tell()
            if pad < 0:
                raise ValueError("header larger than the original's")
            out.write(b"\0" * (pad - 6) + b"(c)CRI" if pad >= 6 else b"\0" * pad)
            out.write(b"TOC " + struct.pack("<IQ", 0, len(toc_table)))
            out.write(_mask(toc_table))
            out.write(b"\0" * (new_content_off - out.tell()))
            fh.seek(content_off)
            remaining = content_size
            while remaining:
                chunk = fh.read(min(remaining, 1 << 22))
                if not chunk:
                    break   # ContentSize counts the last file's alignment padding past the end of the file
                out.write(chunk)
                remaining -= len(chunk)
            if remaining > 8:
                raise ValueError("truncated source pack")
            out.write(b"\0" * remaining)
            for e in sorted((e for e in out_entries if "path" in e), key=lambda e: e["offset"]):
                out.write(b"\0" * (toc_off + e["offset"] - out.tell()))
                with open(e["path"], "rb") as png:
                    out.write(png.read())
            # The header's FileSize is the whole pack's size; the CRI loader refuses a pack whose size
            # disagrees (story_text.py's first build: "a loading error has occurred", 2026-11-07).
            if "FileSize" in hrows[0]:
                struct.pack_into(_FMT[cols["FileSize"][2]], header, hrows[0]["FileSize"][0], out.tell())
                out.seek(16)
                out.write(_mask(bytes(header)))
        os.replace(tmp, out_path)
    return {"files": len(out_entries), "added": len(new_files), "size": os.path.getsize(out_path)}


def built_pack(cache_dir: str, *roots) -> tuple[str, int, int] | None:
    """(path, version, size) of the rebuilt pack, building it once. None when not rebuilt."""
    p = plan(*roots)
    if not p:
        return None
    src, adds, signature = p
    base = int(re.search(r"Ver(\d+)_", os.path.basename(src)).group(1))
    path = os.path.join(cache_dir, f"{PACK[:-4]}-{signature}.cpk")
    with _LOCK:
        if not os.path.isfile(path):
            info = build(src, adds, path)
            for old in glob.glob(os.path.join(cache_dir, f"{PACK[:-4]}-*.cpk")):
                if old != path:
                    os.remove(old)   # packs built under an older setting
            print(f"[ios-art] built {os.path.basename(path)}: {info['files']} files, {info['added']} archive "
                  f"banners added, {info['size']} bytes", flush=True)
    # RC1 Android erroneously compounded resource versions each launch.
    # Use a new stable generation greater than any earlier test version.
    generation = 10000 if os.environ.get("FFBE_ANDROID_EMBEDDED") == "1" else 1000
    return path, base + generation + int(signature, 16) % 1000, os.path.getsize(path)


_PATH = re.compile(r"(^|/)en/sd/area/Ver(\d+)_" + re.escape(PACK) + r"$")


def wants(rel: str) -> bool:
    return enabled() and bool(_PATH.search(rel))


def cache_dir() -> str:
    root = os.environ.get("FFBE_SERVER_ROOT") or os.environ.get("FFBE_DATA") or _HERE
    return os.path.join(root, "ios-cache")
