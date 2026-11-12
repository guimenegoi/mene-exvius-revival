"""How long each banner and event ran on Global, for the historic replay (2026-11-12).

With EXVIUS_REPLAY_FULL_RUNS=1 (default) a banner or event is on offer in every real week whose slice of history
overlaps its Global run (start <= slice end, end >= slice start), so a long banner stays up for several weeks and
a short one that crosses a slice boundary shows twice. 0 = the old rule: shown only in the week its start date
falls in (banners), or beside a set released near its start (events).

Run dates:
  * banners: release = the banner's own date (`community.release`/`release`, corrected by
    content/late_banners.json `existing`); end = `community.until`/`until`, else content/banner_runs.json `runs`,
    else that file's `default_days` for the banner's kind (research/BANNER_RUNS.md);
  * events: content/event_runs.json `runs` (start/end per run, from the wiki's Event Period lines), else the
    run's start plus that file's default length (research/EVENT_RUNS.md).
"""
from __future__ import annotations

import json
import os
from datetime import date, timedelta
from functools import lru_cache

_HERE = os.path.dirname(os.path.abspath(__file__))
FALLBACK_DAYS = {"featured": 14, "deal": 14, "step-up": 14, "box": 14, "ticket": 14, "select": 14}
EVENT_FALLBACK_DAYS = 14
END_OF_SERVICE = date(2024, 10, 30)
# Features Global kept open once released, new stages added on later dates (my reading of the wiki, 2026-11-12,
# research/EVENT_RUNS.md): open from their first run to the end of service rather than 14 days per update.
OPEN_ENDED = {"1199": "Advent of Purgatory", "9961": "Advent of Purgatory Rush", "402": "Short Stories",
              "1899": "Twelve Types Takedown", "1044": "Daily Fragment Challenge"}


def enabled() -> bool:
    return os.environ.get("EXVIUS_REPLAY_FULL_RUNS", "1").strip().lower() not in ("0", "off", "false", "no")


@lru_cache(maxsize=None)
def _doc(name: str) -> dict:
    try:
        with open(os.path.join(_HERE, "content", name), encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return {}


def _day(text) -> date | None:
    try:
        parts = [int(p) for p in str(text).split("-")] + [1, 1]
        return date(*parts[:3])
    except (TypeError, ValueError):
        return None


def banner_run(banner: dict) -> tuple[date, date] | None:
    """(first day, last day) of a banner's Global run, or None when it has no date."""
    import gacha_rotation
    community = banner.get("community") or {}
    start = _day(community.get("release") or banner.get("release"))
    if start is None:
        return None
    end = _day(community.get("until") or banner.get("until"))
    if end is None:
        row = (_doc("banner_runs.json").get("runs") or {}).get(str(banner.get("id"))) or {}
        end = _day(row.get("until"))
    if end is None:
        kind = gacha_rotation._kind(banner)
        days = (_doc("banner_runs.json").get("default_days") or {}).get(kind) or FALLBACK_DAYS.get(kind, 14)
        end = start + timedelta(days=int(days) - 1)
    return start, max(start, end)


def event_runs(row: dict) -> list[tuple[date, date]]:
    """[(first day, last day)] of an event's Global runs: content/event_runs.json, else each start (its release
    and event_history.json reruns) plus the default length."""
    doc = _doc("event_runs.json")
    area = str(row.get("area"))
    known = (doc.get("runs") or {}).get(area) or []
    bad = {_day(text) for text in (doc.get("bad_starts") or {}).get(area) or []}   # archive dates the wiki disproves
    out = []
    for run in known:
        start, end = _day(run.get("start")), _day(run.get("end"))
        if start:
            out.append((start, max(start, end or start)))
    starts = []
    for text in row.get("runs") or [row.get("release")]:
        start = _day(text)
        if start and start not in bad and not any(abs((start - s).days) <= 3 for s, _e in out):
            starts.append(start)
    defaults = doc.get("default_days") or {}
    days = int(defaults.get(str(row.get("kind") or "")) or defaults.get("all") or EVENT_FALLBACK_DAYS)
    out += [(s, s + timedelta(days=days - 1)) for s in starts]
    out.sort()
    if area in OPEN_ENDED and out:
        return [(out[0][0], END_OF_SERVICE)]
    return out


def overlaps(run: tuple[date, date], begin: date, end: date) -> bool:
    """A run against a slice of history [begin, end) (end exclusive, as replay.window gives it)."""
    return run[0] < end and run[1] >= begin
