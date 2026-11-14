"""Units normal summons leave out, and sell prices for the story units (operator, 2026-11-10).

`content/summon_exclusions.json` (built by ios-server/devtools/build_summon_exclusions.py; list in
ios-server/research/SUMMON_EXCLUSIONS.md):
  * `excluded`: base units the FFBE wiki lists as story, reward, Star Quartz or Raid Summon units only.
    player_state.expand_pool leaves them out of a rarity tier that draws every base unit of its rarity; a
    banner that features one still has it, and pools that list their units are untouched.
    `EXVIUS_SUMMON_EXCLUSIONS=0` puts them back;
  * `sell_prices`: unit table row -> Gil, for the story units' rows whose sell price is 0 (the client only
    offers Sell when it is above 0), served in the client's unit table by ios_tables.py so copies players
    already own can be sold. `EXVIUS_SELL_STORY_UNITS=0` serves the table as shipped.
"""
from __future__ import annotations

import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
PATH = os.path.join(HERE, "content", "summon_exclusions.json")
_DOC: dict | None = None


def _on(name: str) -> bool:
    return str(os.environ.get(name, "1")).strip().lower() not in ("0", "off", "false", "no")


def _doc() -> dict:
    global _DOC
    if _DOC is None:
        try:
            with open(PATH, encoding="utf-8") as fh:
                _DOC = json.load(fh)
        except (OSError, ValueError) as exc:
            print(f"summon exclusions: {PATH} not loadable ({exc!r}); summons draw every base unit", flush=True)
            _DOC = {}
    return _DOC


def excluded() -> frozenset:
    """Unit ids a rarity tier's default draw leaves out (empty when switched off)."""
    if not _on("EXVIUS_SUMMON_EXCLUSIONS"):
        return frozenset()
    return frozenset(_doc().get("excluded") or {})


def limited_out() -> frozenset:
    """Limited, collaboration and seasonal units (gacha_archive.limited_unit_ids: the FFBE wiki's flag where the
    unit page was checked): on Global they came only from banners that featured them (operator, 2026-11-10), so a
    rarity tier's default draw leaves them out. Empty when EXVIUS_LIMITED_FEATURED_ONLY=0."""
    if not _on("EXVIUS_LIMITED_FEATURED_ONLY"):
        return frozenset()
    import gacha_archive
    return frozenset(gacha_archive.limited_unit_ids())


def guessed_limited() -> frozenset:
    """Listed units the wiki does not mark limited (the story units and a few rewards): the banner guess in
    gacha_archive.limited_unit_ids counts them limited, which kept them out with EXVIUS_SUMMON_EXCLUSIONS=0 too.
    They are kept out by that setting alone."""
    return frozenset(uid for uid, row in (_doc().get("excluded") or {}).items()
                     if (row or {}).get("limited") not in ("Yes", "Collaboration", "Seasonal"))


def sell_prices() -> dict:
    """Unit table row id -> sell Gil for the story units (empty when switched off)."""
    if not _on("EXVIUS_SELL_STORY_UNITS"):
        return {}
    return {str(k): int(v) for k, v in (_doc().get("sell_prices") or {}).items()}
