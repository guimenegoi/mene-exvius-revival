"""The summon art pack (2026-11-13): the summon images the server used to download, draw, pad or cut while it
ran, as files that come with the game data.

Before, 1,018 summon images were made by the running server: 178 downloaded from the Internet Archive and the
wiki at every start until they arrived (deal_art.fetch), 840 drawn as titled stand-ins, and every detail image
that didn't fit its frame was padded or cut on request (banner_fit). The pack holds the finished files, so a
server with the game data installed needs no network and makes no image.

Layout, in `<data>/static/summon_art` (SUMMON_ART_PACK_ROOT; `fetch-data` puts it there):

    base/<name>   an image under the name a banner's record gives it (`late-9700003-detail.png`): what
                  deal_art.fetch used to put in `deal_art/`. The art index lists this folder first, so the
                  summon reply finds the file and reads its shape from it.
    main/<name>   a list image under the exact name the phone asks for (`x-strip1.png`: the strip cut from x).
    sub/<name>    a detail image under the exact name the phone asks for (`x-fit1.png`, `x-full1.png`), already
                  fitted to its frame. The file server sends these as they are.
    list.json     {"images": {"<folder>/<name>": {"source": ..., "from": ..., "size": [w, h], "banners": [...]}}}
                  `source`: where the picture came from (`news`, `wiki`, `jp`, `game`, `drawn`), so a better one
                  can replace it later; a made image also says `made` (`strip`, `fit`).

`EXVIUS_SUMMON_ART_PACK=0`: the pack is not read (the server downloads, draws and pads as before, when the
fetch settings allow it).
"""
from __future__ import annotations

import json
import os
import re
from functools import lru_cache

REQUEST = re.compile(r"(^|/)static_banner/gacha/(main|sub)/([^/]+\.png)$", re.IGNORECASE)


def enabled() -> bool:
    return os.environ.get("EXVIUS_SUMMON_ART_PACK", "1").strip().lower() not in ("0", "off", "false", "no")


def root() -> str:
    import data_paths
    return data_paths.SUMMON_ART_PACK_ROOT


def base_folder() -> str:
    return os.path.join(root(), "base")


@lru_cache(maxsize=1)
def listing() -> dict:
    """The pack's list, {"<folder>/<name>": {...}}; empty without a pack."""
    if not enabled():
        return {}
    try:
        with open(os.path.join(root(), "list.json"), encoding="utf-8") as fh:
            return dict(json.load(fh).get("images") or {})
    except (OSError, ValueError):
        return {}


def installed() -> bool:
    return bool(listing())


def source(name: str) -> str | None:
    """Where the pack's `base/<name>` picture came from (`drawn` for a titled stand-in), or None."""
    row = listing().get("base/" + str(name or ""))
    return str(row.get("source") or "") if row else None


def literal(rel: str) -> str | None:
    """The pack file for a summon image request, under the exact name asked for, or None."""
    m = REQUEST.search(rel or "")
    if not m or not enabled():
        return None
    path = os.path.join(root(), m.group(2).lower(), m.group(3))
    return path if os.path.isfile(path) else None
