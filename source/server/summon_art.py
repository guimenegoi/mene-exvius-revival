"""Summon art the phone can always download (2026-11-12, player report: opening the summon screen started a data
download that failed, sent the game to the title and asked to re-download all data).

The summon screen downloads every image its banners name (`GachaScheduleMst.bannerInfo` `4yT7FUqj`: the list art
from `.../static_banner/gacha/main/`, the detail art from `.../sub/`), and a file the server answers with 404
fails the whole download. 1,018 of the names are made by the server itself: 840 drawn stand-ins and 178 web
downloads (`deal_art.fetch`, on a background thread at start, half a second apart, a failed download retried
only at the next start). The late banners (9c8b059) added most of them, so after an update the summon screen
named files that didn't exist yet for minutes, and a failed web download stayed missing until the next restart.

Now:
  * `resolve(banner, art)` (the summon reply) names only files that exist: a missing stand-in is drawn on the spot;
    a web image not downloaded yet is named `standin_<name>` (drawn now) until the real file arrives; a name no
    one can make falls back to the default summon art (`GACHA_DEFAULT_BANNER_ART`);
  * `fallback(rel)` (the file server) answers any summon art request that still misses with a drawn image, so the
    phone never gets a 404 there.
"""
from __future__ import annotations

import os
import re
import threading
from functools import lru_cache

STANDIN = "standin_"
_LOCK = threading.Lock()
SUMMON_ART = re.compile(r"(^|/)static_banner/gacha/(main|sub)/([^/]+\.png)$", re.IGNORECASE)


@lru_cache(maxsize=1)
def _targets() -> dict:
    """name -> (url, title, size) for every image the server makes (deal_art._targets)."""
    import deal_art
    return {name: (url, title, size) for name, url, title, size in deal_art._targets()}


def _index() -> dict:
    from ffbe_gacha import banner_art_index
    return banner_art_index()


def _folder() -> str:
    import data_paths
    return data_paths.DEAL_ART_ROOT


def _draw(name: str, title: str, size: tuple) -> bool:
    """Draw a titled stand-in into the deal art folder under `name`; True when the file now exists."""
    import deal_art
    folder = _folder()
    path = os.path.join(folder, name)
    with _LOCK:
        if os.path.isfile(path):
            _index().setdefault(name, path)
            return True
        try:
            os.makedirs(folder, exist_ok=True)
            data = deal_art.render(title, size)
            with open(path + ".tmp", "wb") as fh:
                fh.write(data)
            os.replace(path + ".tmp", path)
        except Exception as exc:  # noqa: BLE001 -- the caller falls back to art that exists
            print(f"SUMMON-ART could not draw {name}: {exc!r}", flush=True)
            return False
        _index()[name] = path
        _say_drawn(name)
        return True


_DRAWN = [0]


def _say_drawn(name: str) -> None:
    """A stand-in drawn while running is the last resort: the art pack carries these as files (art_pack.py).
    The first five are logged by name, then every hundredth, so a server without the pack says so plainly
    without filling its log."""
    _DRAWN[0] += 1
    if _DRAWN[0] <= 5 or _DRAWN[0] % 100 == 0:
        import art_pack
        why = ("it is not in the summon art pack" if art_pack.installed()
               else "the summon art pack is not installed: run fetch-data")
        print(f"SUMMON-ART drew a stand-in for {name} ({why}; {_DRAWN[0]} drawn since the start)", flush=True)


# Characters a summon image name may be made of when it is handed to the phone: printable ASCII that needs at
# most a space encoded in a URL. Names with spaces (`Gacha-Noctis Arrives.png`) are in replay weeks 0 and 1 and
# download on the phone. A name outside this set is sent under an ASCII alias instead (`plain_name`).
_PLAIN = re.compile(r"[A-Za-z0-9._ \-&'()+,;=@!$*~]+")


def plain_name(name: str) -> str:
    """`name`, or an ASCII alias for it when it holds anything else (2026-11-13, GitHub #6/#7).

    Twelve pack images are named `Gacha-7★-<unit>.png`. The star is three bytes in UTF-8 (E2 98 85). No phone
    had ever been handed such a name: with the replay they first show in week 29, with EXVIUS_SUMMON_ROTATION=0
    all at once, and those players' summon download never finished. What the phone sends for one isn't known
    (the iPhone's downloader is platform code); sent as raw bytes the request line didn't even parse here (see
    capture_server.Handler.parse_request). The alias keeps the readable part and adds a checksum of the real
    name, so it is the same after every restart; ffbe_gacha.banner_art_index lists every alias beside the real
    name, so the file server finds the file under either."""
    if not name or _PLAIN.fullmatch(name):
        return name
    import zlib
    stem, ext = os.path.splitext(name)
    safe = re.sub(r"-{2,}", "-", re.sub(r"[^A-Za-z0-9._ \-]+", "-", stem)).strip("-. ") or "art"
    ext = ext if re.fullmatch(r"\.[A-Za-z0-9]+", ext) else ".png"
    return f"{safe}-x{zlib.crc32(name.encode('utf-8')) & 0xffffff:06x}{ext}"


def ensure(name: str, title: str = "", size: tuple | None = None) -> str:
    """A name for `name` that the phone can download now."""
    from ffbe_config import GACHA_DEFAULT_BANNER_ART
    if not name:
        return name
    if name in _index():
        alias = plain_name(name)
        if alias != name:
            _index().setdefault(alias, _index()[name])
        return alias
    target = _targets().get(name)
    if target is not None:
        url, made_title, made_size = target
        title, size = title or made_title, size or made_size
        if not url:                                   # a drawn stand-in: draw it now
            if _draw(name, title, size):
                return name
        else:                                         # Global's art, not downloaded yet: a stand-in meanwhile
            stand = STANDIN + name
            if _draw(stand, title, size):
                return stand
    return GACHA_DEFAULT_BANNER_ART


def resolve(banner: dict, art: dict) -> dict:
    """`art` with every summon image name replaced by one that exists (see the module docstring)."""
    if os.environ.get("EXVIUS_SUMMON_ART_GUARD", "1").strip() in ("0", "off", "false", "no"):
        return art
    title = str(banner.get("name") or "")
    out = dict(art)
    detail = art.get("detail_banner")
    for key in ("banner", "banner_en", "detail_banner", "detail_banner_en"):
        if out.get(key):
            wide = key.startswith("banner") and out[key] != detail
            out[key] = ensure(str(out[key]), title, (640, 160) if wide else (640, 392))
    if art.get("detail_extra"):
        out["detail_extra"] = [ensure(str(n), title, (640, 392)) for n in art["detail_extra"]]
    return out


def fallback(rel: str, why: str = "file missing") -> tuple[bytes, str] | None:
    """(PNG bytes, how) for a summon art request the file server couldn't answer, else None. `why` goes in
    the log line (banner_fit gives its own when the file is there but too large to fit)."""
    m = SUMMON_ART.search(rel or "")
    if not m:
        return None
    import deal_art
    name = m.group(3)
    base = name[len(STANDIN):] if name.startswith(STANDIN) else name
    url, title, size = _targets().get(base, ("", "", None))
    size = size or ((640, 392) if m.group(2).lower() == "sub" else (640, 160))
    try:
        return deal_art.render(title or "Summon", size), f"summon art stand-in ({why})"
    except Exception:  # noqa: BLE001
        from ffbe_config import GACHA_DEFAULT_BANNER_ART
        path = _index().get(GACHA_DEFAULT_BANNER_ART)
        if path and os.path.isfile(path):
            with open(path, "rb") as fh:
                return fh.read(), f"default summon art ({why})"
    return None
