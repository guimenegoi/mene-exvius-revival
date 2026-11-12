"""Global's summon banners from 2023-08 to the end of service, rebuilt (content/late_banners.json, 2026-11-12), and
three earlier featured banners our data lacked.

`banners`: new banners (ids 9700001+), in the deal banners' shape, art downloaded by deal_art.py (`art.urls`, an
empty url draws a titled stand-in). `existing`: Global's real release/until for banners we already had on guessed
or lumped dates (the cached Global banners 92000xx, the wiki banners 9300xxx, a few a day off). `hide`: placeholder
records that weren't real Global banners. Research and sources: ios-server/research/LATE_BANNERS.md.
EXVIUS_LATE_BANNERS=0 serves the banners as before (no new ones, old dates, nothing hidden).
"""
from __future__ import annotations

import copy
import json
import os
from functools import lru_cache

_HERE = os.path.dirname(os.path.abspath(__file__))
PATH = os.path.join(_HERE, "content", "late_banners.json")


def enabled() -> bool:
    return os.environ.get("EXVIUS_LATE_BANNERS", "1").strip().lower() not in ("0", "off", "false", "no")


@lru_cache(maxsize=1)
def _doc() -> dict:
    try:
        with open(PATH, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return {}


def banners() -> list:
    """The rebuilt banners. Those whose very existence is inferred (`unconfirmed`: the 2024 NV Premium Step-Ups,
    copied from the 2023 pattern) only with EXVIUS_LATE_UNCONFIRMED=1."""
    if not enabled():
        return []
    unconfirmed = os.environ.get("EXVIUS_LATE_UNCONFIRMED", "0").strip() == "1"
    return [copy.deepcopy(b) for b in _doc().get("banners") or [] if unconfirmed or not b.get("unconfirmed")]


def apply(by_id: dict) -> None:
    """Redate the existing banners and drop the hidden placeholders, in place."""
    if not enabled():
        return
    doc = _doc()
    for bid, fix in (doc.get("existing") or {}).items():
        banner = by_id.get(str(bid))
        if banner is None:
            continue
        banner = by_id[str(bid)] = dict(banner)
        community = dict(banner.get("community") or {})
        if fix.get("release"):
            banner["release"] = community["release"] = fix["release"]
        if fix.get("until"):
            community["until"] = fix["until"]
        if fix.get("alias_ids"):   # the same Global banner under another id: hidden, still resolvable
            banner["alias_ids"] = list(dict.fromkeys([*(banner.get("alias_ids") or []), *fix["alias_ids"]]))
        if fix.get("name"):
            banner["name"] = fix["name"]          # Global's title (e.g. the FFXI Lady Shantotto/Lion banner)
        featured = [str(u) for u in fix.get("featured_units") or []]
        if featured:
            community["unit_ids"] = list(dict.fromkeys([*(community.get("unit_ids") or []), *featured]))
            pool = banner.get("pool")
            if isinstance(pool, dict) and pool.get("tiers"):
                tiers = [dict(t) for t in pool["tiers"]]
                top = max(range(len(tiers)), key=lambda i: int(tiers[i].get("rarity") or 0))
                tiers[top]["featured"] = list(dict.fromkeys([*(tiers[top].get("featured") or []), *featured]))
                banner["pool"] = dict(pool, tiers=tiers)
        banner["community"] = community
    for bid in doc.get("hide") or {}:
        by_id.pop(str(bid), None)
