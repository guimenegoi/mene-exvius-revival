"""The moogle's line for a summon that has no text of its own (2026-11-13).

The game reads two texts per summon from `F_TEXT_GACHA`, by the summon's id:

  * `MST_GACHA_EXPLAIN_LONG_<id>` (`GachaMst::getExplainLong`): the moogle's speech bubble on the 640x392 detail
    screen (`GachaDetailScene::setLayout`, `setStepUpLayout`, `createMoogleAnime`) and on the ticket-only screen;
  * `MST_GACHA_EXPLAIN_SHORT_<id>` (`GachaMst::getExplainShort`): a label, shown under a banner in the summon
    list and as the period line of the paid screen, and only when the summon has no dates to show there.

The game's own table has 1,871 long and 943 short texts ("Summon 11 and get at least four 5★ or higher units,
kupo!", "Featured Summon"). Those are never touched (ios_texts adds a text only under a key the table lacks).
But most banners here have ids of this project's own and so no text; they all got one generic line, "Summon 1
reward(s). The button shows the cost. See Drop Rates for the reward list." The paid screen never showed it. The
640x392 screen does, in the moogle's bubble (operator's screenshot of Dark Fina Revealed, 2026-11-13).

This module writes the line from what the summon really does, in the game's own wording where the game has one
for it: how many units the multi-summon gives, what it guarantees, what a step-up or a box is, how often it can
be used. Nothing is said that the banner's record doesn't say.
"""
from __future__ import annotations

WORDS = {1: "one", 2: "two", 3: "three", 4: "four", 5: "five", 6: "six", 7: "seven", 8: "eight", 9: "nine",
         10: "ten", 11: "eleven"}


def _tiers(banner: dict) -> list:
    pool = banner.get("pool")
    tiers = pool.get("tiers") if isinstance(pool, dict) else banner.get("tiers")
    return [t for t in tiers or [] if isinstance(t, dict)]


def featured(banner: dict) -> bool:
    """True when the banner raises the chance of named units."""
    return any(t.get("featured") for t in _tiers(banner)) or bool((banner.get("community") or {}).get("unit_ids"))


def guarantee_floor(banner: dict, guarantee: dict):
    """The lowest rarity a guaranteed unit can have, or None when the record doesn't settle it."""
    if guarantee.get("rarity") is not None:
        return int(guarantee["rarity"])
    if guarantee.get("pool") is None:
        return None
    try:
        from player_state import expand_pool
        own = {"pool": guarantee["pool"]}
        if banner.get("rate_source"):
            own["rate_source"] = banner["rate_source"]
        rarities = [int(row.get("rarity") or 0) for row in expand_pool(own)]
    except Exception:  # noqa: BLE001 -- say less rather than something unchecked
        return None
    return min(rarities) if rarities and min(rarities) > 0 else None


def _kind(floor: int) -> str:
    return "NV" if floor >= 7 else f"{floor}★ or higher"


def _multi(count: int, banner: dict, guarantee) -> str:
    """A multi-summon of `count` units, with what it guarantees."""
    floor = guarantee_floor(banner, guarantee) if isinstance(guarantee, dict) and guarantee else None
    if floor is None:
        return f"Summon {count} units at once"
    sure = int(guarantee.get("count", 1))
    if sure >= count:
        return f"Summon {count} units, every one {_kind(floor)}"
    if sure == 1:
        return f"Summon {count} for at least one {_kind(floor)} unit"
    return f"Summon {count} and get at least {WORDS.get(sure, str(sure))} {_kind(floor)} units"


def _limit(banner: dict) -> str:
    for key, each in (("daily_limit", "a day"), ("weekly_limit", "a week")):
        times = int(banner.get(key) or 0)
        if times:
            return f"Once {each}." if times == 1 else f"{times} times {each}."
    times = int(banner.get("purchase_limit") or 0)
    if times:
        return "Can be summoned once." if times == 1 else f"Can be summoned {times} times."
    return ""


def _cost_kind(banner: dict) -> str:
    cost = banner.get("cost")
    cost = cost[0] if isinstance(cost, list) and cost else cost
    return str((cost or {}).get("kind") or "free") if isinstance(cost, dict) or cost is None else "free"


def long_text(banner: dict) -> str:
    """The moogle's line."""
    if banner.get("selection"):
        return "Choose a unit or prism from the list, kupo!"
    steps = banner.get("steps")
    if steps:
        return f"A {len(steps)}-step summon. Each step has its own cost and contents, kupo!"
    if banner.get("boxes"):
        return "Each summon takes one reward out of the box, kupo!"
    limit = _limit(banner)
    if banner.get("reward_pool"):
        return ("You can get units, items and more, kupo! " + limit).strip()
    draws = max(1, int(banner.get("draws") or 1))
    offer = banner.get("secondary_offer") if isinstance(banner.get("secondary_offer"), dict) else {}
    free = _cost_kind(banner) == "free" and not banner.get("steps")
    if draws >= 2:
        line = _multi(draws, banner, banner.get("guarantee"))
    elif int(offer.get("draws") or 1) >= 2:
        line = _multi(int(offer["draws"]), banner, offer.get("guarantee"))
    else:
        floor = guarantee_floor(banner, banner["guarantee"]) if isinstance(banner.get("guarantee"), dict) \
            and banner.get("guarantee") else None
        if floor is not None:
            line = f"A guaranteed {_kind(floor)} unit"
        elif featured(banner):
            line = "A higher chance to summon the featured units"
        else:
            line = "Summon a unit"
    if free:
        line = "Free: " + line[0].lower() + line[1:]
    return (line + ", kupo! " + limit).strip()


def short_text(banner: dict) -> str:
    """The label (the game's own are "Featured Summon" and "Step Up Summon")."""
    if banner.get("steps"):
        return "Step Up Summon"
    if banner.get("selection"):
        return "Select Summon"
    if _cost_kind(banner) == "free":
        return "Free Summon"
    if featured(banner) and not banner.get("reward_pool") and not banner.get("boxes"):
        return "Featured Summon"
    return "Summon"
