"""Battles lower the saved item set (2026-11-12, operator: "on Global, items used in battle were gone").

The phone sends its item set (`nE7pV2wr`, one row, `jsvoa0I2` = `slot:item:count,...`, the client's own
`UserCarryItemInfoList::toJsonGroup`) in every battle-end request: MissionEnd (and its TFA and Glory forms),
MissionRetire, Parade, RM end and retire, Survival end and retire, ClsmEnd, the expedition battle end
(GL `*Request::createBody`). Until now only the item-set edit, the field-use update (`MissionSwitchUpdateRequest`)
and the RM/Parade/Survival handlers read it, so after a restart the set refilled to the last saved counts.

The rule (`apply`), the same for every one of those requests:
  * a slot keeps the smaller of its saved count and the reported count, so a count is only ever lowered;
  * a saved slot the report leaves out was used up (the phone drops an empty slot); a reported slot holding a
    different item, or a slot the saved set doesn't have, changes nothing: nothing is ever added or swapped;
  * a missing group, or one with any element that isn't three integers, changes nothing at all;
  * an empty report (no slots) while the saved set has items changes nothing: it is treated as no information,
    so a battle that really used every item in the set isn't recorded (the safe way to be wrong);
  * what a slot loses comes out of the bag too (`spend_item(20, ...)`), as the field-use update does: the item
    set is a selection from the bag (`apply_carry_edit` doesn't touch the bag), so a used Potion leaves both;
  * it compares against the CURRENT saved set, so a retried or repeated report finds nothing left to lower and
    takes nothing twice, and a Potion already taken by a field use isn't taken again at the battle's end.
No battle-end reply echoes the set back: the phone already holds what it reported (`BattlePartyItemList::
copyToCarryItem` runs before the request is built), and `nE7pV2wr` is clear-and-rebuild.
"""
from __future__ import annotations

import json

GROUP = "nE7pV2wr"
CSV = "jsvoa0I2"
BATTLE_ENDS = {
    "x5Unqg2d": "MissionEndRequest",
    "JiglLZx6": "TfaMissionEndRequest",
    "BQG1rm3y": "GloryMissionEndRequest",
    "v51PM7wj": "MissionRetireRequest",
    "4cACW7y3": "ParadeMissionEndRequest",
    "fyp10Rrc": "RmEndRequest",
    "e0R3iDm1": "RmRetireRequest",
    "3cuPF20R": "SurvivalMissionEndRequest",
    "yW35iC40": "SurvivalMissionRetireRequest",
    "3zgbapQ7": "ClsmEndRequest",
    "2pe3Xa8b": "sgExpdEndRequest",
}


def reported(req) -> dict | None:
    """{slot: (item, count)} from a request body, or None when the group is missing or unreadable."""
    rows = req.get(GROUP) if isinstance(req, dict) else None
    if isinstance(rows, dict):
        rows = [rows]
    if not isinstance(rows, list) or not rows or not isinstance(rows[0], dict) or not isinstance(rows[0].get(CSV), str):
        return None
    out = {}
    for element in filter(None, (e.strip() for e in rows[0][CSV].split(","))):
        parts = element.split(":")
        if len(parts) != 3 or not all(p.strip().lstrip("-").isdigit() for p in parts):
            return None
        slot, item, count = (int(p) for p in parts)
        if slot in out or count < 0:
            return None
        out[slot] = (item, count)
    return out


def apply(player, req) -> dict:
    """Lower the saved set to what the report shows and take the difference out of the bag. Returns
    {item: count taken}; {} when nothing changed."""
    if player is None or player.mode == "frozen":
        return {}
    report = reported(req)
    if report is None:
        return {}
    saved = player.data.setdefault("inventory", {}).setdefault("carry_items", [])
    if not report and saved:
        # An empty report while the save holds items is no information (operator, 2026-11-12): a phone that
        # lost its set would otherwise empty it. A battle that really used every item isn't recorded.
        return {}
    kept, taken = [], {}
    for row in sorted(saved, key=lambda r: int(r["disp_order"])):
        slot, item, count = int(row["disp_order"]), int(row["item_id"]), int(row["count"])
        got = report.get(slot)
        if got is not None and got[0] != item:
            new = count                                  # a different item in that slot: leave it
        else:
            new = min(count, got[1]) if got is not None else 0
        if new < count:
            taken[item] = taken.get(item, 0) + count - new
        if new > 0:
            kept.append({"disp_order": slot, "item_id": item, "count": new})
    if not taken:
        return {}
    for item, count in taken.items():
        player.spend_item(20, item, min(count, player.item_count(20, item)))
    saved[:] = kept
    player.dirty = True
    return taken


def step(spec, reply_id, plaintext, state):
    """Pipeline step: on a battle-end request, apply its item-set report. The reply is left as it is."""
    if str(reply_id) not in BATTLE_ENDS or not plaintext or state.player is None:
        return spec
    try:
        req = json.JSONDecoder().raw_decode(plaintext)[0]
    except ValueError:
        return spec
    taken = apply(state.player, req)
    if taken:
        state.state_dirty = True
        print(f"item set: {BATTLE_ENDS[str(reply_id)]} used "
              + ", ".join(f"{item}x{count}" for item, count in taken.items()), flush=True)
    return spec
