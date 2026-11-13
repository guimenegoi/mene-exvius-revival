"""Completed quest steps get their completion switches (2026-11-12, player report: completed Mitra quests were
offered again after a restart).

`exvius_actions_expedition.mission_update` saved a completed step (`exvius_map.quests[step]['4kcAD9fW'] = "2"`) and
paid the quest, but set only the switches the request carried, and the phone's completion request
(`TownUpdateRequest` `1sGiqV9T.9YPZuB2i`) carries none. Every step has its own completion switch in
F_QUEST_SUB_MST `dIPkNn61` (100100101 -> 20004002) beside its accept switch `juA0Z4m7` (20004001). The map scripts read
the completion switch (Mitra's map.bin: an event page conditioned on 20004002 being on), so with it unset the NPC
offered the quest again. mission_update now sets them; this repairs saves from before.

`repair(player)`, once per save at login (ledger `quest_switch_repair`): for every saved step marked completed ("2")
whose F_QUEST_SUB_MST row belongs to the saved quest, set its missing completion switches. Nothing else changes: no
rewards, no step states, no inventory. Active steps ("1") and unknown rows are left alone. Idempotent.
"""
from __future__ import annotations

LEDGER = "quest_switch_repair"
LOGIN_REPLIES = ("75fYdNxq", "X07iYtp5")       # the replies whose switch group the phone reads at login


def missing(player) -> list[tuple[str, str]]:
    """[(step id, switch id)] of completed steps' completion switches the save doesn't have."""
    from player_state import _load_ndjson, switch_position
    steps = _load_ndjson("F_QUEST_SUB_MST.ndjson", "7Svg2kdT")
    saved = (player.data.get("exvius_map") or {}).get("quests") or {}
    out = []
    for sid, row in saved.items():
        step = steps.get(str(sid))
        if (not isinstance(row, dict) or str(row.get("4kcAD9fW")) != "2" or not isinstance(step, dict)
                or str(step.get("Z34jU7ue")) != str(row.get("Z34jU7ue"))):
            continue
        for switch in filter(None, (s.strip() for s in str(step.get("dIPkNn61") or "").split(","))):
            pos = switch_position(switch)
            if pos and int(pos[1]) not in player.switches.get(pos[0], set()):
                out.append((str(sid), switch))
    return out


def repair(player) -> list[tuple[str, str]]:
    from player_state import switch_position
    if player is None or player.mode == "frozen" or (player.data.get(LEDGER) or {}).get("done"):
        return []
    found = missing(player)
    for _sid, switch in found:
        player.grant_switch(*switch_position(switch))
    player.data[LEDGER] = {"done": True, "set": [s for _sid, s in found]}
    player.dirty = True
    return found


def step(spec, reply_id, state):
    """Pipeline step: the login repair, before the switch group is built."""
    if str(reply_id) not in LOGIN_REPLIES or state.player is None:
        return spec
    found = repair(state.player)
    if found:
        state.state_dirty = True
        print(f"quest switches: set {len(found)} completion switch(es) for completed steps: "
              + ", ".join(f"{sid}->{sw}" for sid, sw in found), flush=True)
    return spec
