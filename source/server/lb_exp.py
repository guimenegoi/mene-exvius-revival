"""LB EXP from cleared quests (player report, 2026-11-12: Rain used his LB twice and still needed 100 EXP for LB 2).

Global's later rule (FFBE wiki "Limit Bursts": "All participating units gain LB Exp based on energy/orb
consumption"; Altema's LB page gives the rates): on a quest clear every party unit (not the friend helper) gains
  * 100 LB EXP per stamina point the quest costs,
  * 250 per raid orb,
  * 100 per weapon-enhancement orb.
Retiring or losing gives nothing; using the LB in battle gives nothing. The level tables already use this scale
(`F_LIMITBURST_LV_MST`: a 2★ unit's LB 1 -> 2 costs 100).

The quest's cost is `F_MISSION_MST.B6kyCQ9M`, its account `CQN15Hgr`: 0 stamina (story, events, Vortex,
chambers, explorations), 1 raid orbs (Ifrit/Titan/Garuda trials, Vision of Bahamut, the FFBE raids), 2
weapon-enhancement orbs (Steel Castle Melfikya, the monthly Equipment events), 50 TFA (no rate given: nothing).
The quest's LISTED cost counts (operator, 2026-11-12: "whatever the quest or activities stam should have cost
they get in experience"), also below rank `DUNGEON_NO_COST_LV` (51), where the phone charges no stamina
(`MissionUtil::getMissionCost`): taken literally ("per stamina spent") every player under rank 51 would get no LB
EXP at all, the player in the report included; Global's text only says "based on energy/orb consumption". A quest
that costs 0 gives nothing. Arena battles aren't quests (no MissionEnd), so they give nothing.

`plan(player, mid)` -> {instance id: (lb_before, exp_before, lb_after, exp_after)} for the party, and `apply`
writes it; `ffbe_battle._credit_mission_rewards` calls both on a cleared run (once per attempt, under its
rollback) and shows the halves in `Qic38SuC`. EXVIUS_LB_EXP=0 turns it off.
"""
from __future__ import annotations

import os
from functools import lru_cache

RATES = {"0": 100, "1": 250, "2": 100}


def enabled() -> bool:
    return os.environ.get("EXVIUS_LB_EXP", "1").strip().lower() not in ("0", "off", "false", "no")


def points(player, mid) -> int:
    """LB EXP one party unit gains for clearing `mid`."""
    from player_state import _load_ndjson
    row = _load_ndjson("F_MISSION_MST.ndjson", "qo3PECw6").get(str(mid)) or {}
    kind = str(row.get("CQN15Hgr") or "0")
    try:
        cost = int(row.get("B6kyCQ9M") or 0)
    except ValueError:
        cost = 0
    if cost <= 0 or kind not in RATES:
        return 0
    return cost * RATES[kind]


@lru_cache(maxsize=None)
def _levels(lb_id: str) -> tuple:
    """((level, exp needed to reach it), ...) for one LB, ascending."""
    from player_state import _load_ndjson
    return tuple(sorted((int(r["7wV3QZ80"]), int(r["T3Zcf40Q"]))
                        for r in _load_ndjson("F_LIMITBURST_LV_MST.ndjson").get("__rows__", [])
                        if str(r.get("PR2HIc71")) == lb_id))


def advance(master_id, level: int, exp: int, gain: int) -> tuple[int, int]:
    """(level, exp) after `gain` LB EXP, walking the unit's LB level table up to its max LB level."""
    from player_state import limit_burst, unit_mst
    lb = limit_burst(master_id)
    if not lb:
        return level, exp
    levels = _levels(str(lb["PR2HIc71"]))
    if not levels:
        return level, exp
    steps = dict(levels)
    try:
        cap = int((unit_mst(master_id) or {}).get("ENwn42DV") or 1)
    except ValueError:
        cap = 1
    maximum = min(levels[-1][0], cap)
    level, exp = max(1, level), exp + gain
    while level < maximum and level + 1 in steps and exp >= steps[level + 1]:
        exp -= steps[level + 1]
        level += 1
    if level >= maximum:
        exp = 0
    return level, exp


def plan(player, mid) -> dict:
    gain = points(player, mid) if enabled() else 0
    out = {}
    if gain <= 0:
        return out
    for iid in player.party_instance_ids(mid):
        u = player.roster_row(iid)
        if u is None:
            continue
        lv, ex = int(u.get("lb_level") or 1), int(u.get("lb_exp") or 0)
        new = advance(u["master_id"], lv, ex, gain)
        if new != (lv, ex):
            out[str(iid)] = (lv, ex, new[0], new[1])
    return out


def apply(player, changes: dict) -> None:
    for iid, (_lv, _ex, lv, ex) in changes.items():
        u = player.roster_row(iid)
        if u is not None:
            u["lb_level"], u["lb_exp"] = lv, ex
    if changes:
        player.dirty = True
