"""Units that were summoned as a Brave Shift form become the unit itself (2026-11-13, player report).

Eight banners featured a unit's Brave Shift form beside the unit (gacha_named.json, since the first release), and
until 2026-11-12 the rebuilt late banners' Neo Vision tier drew forms too. A form in the roster can't be
awakened: it stays at its base rarity or at EX +0 for good. Pools no longer hold a form
(player_state.tiers_without_shift_forms, without_shift_forms); this puts right what was already summoned.

`repair(player)`, once per save at login (ledger `shift_form_repair`): every roster unit whose id is a form
(`player_state.unit_other_forms`: `F_UNIT_MST.I3SKJ4q0` = 1 naming another row in `JPW8Vs40`) becomes the unit a
summon should have given (`player_state.summon_unit`: the series root of the row the form names; the NV unit for
a ...17 form, the 5-star or 3-star base for a ...27 form). It keeps its place in the box and in parties (same
owned-unit id), its equipment, materia, Vision Card, trust and favourite mark. Its level is kept up to the new
unit's cap, its limit burst level up to the new unit's top LB level, and an EX level only on a Neo Vision unit;
this is what awakening does when it changes a unit's id (exvius_actions_shops._awaken_unit). Each swap is
logged and kept in the ledger. EXVIUS_SUMMON_NO_SHIFT_FORMS=0: nothing is swapped, and the ledger is not
written, so the repair still runs once the setting is back on.
"""
from __future__ import annotations

LEDGER = "shift_form_repair"
LOGIN_REPLIES = ("75fYdNxq", "X07iYtp5")       # the login replies that carry the roster


def forms_held(player) -> list:
    """[(owned-unit id, form id, the unit it becomes)] for the roster units that are a Brave Shift form."""
    from player_state import summon_unit, unit_other_forms
    forms = unit_other_forms()
    out = []
    for unit in player.data.get("roster") or []:
        master = str(unit.get("master_id"))
        if master in forms and summon_unit(master) not in forms:
            out.append((str(unit.get("instance_id")), master, summon_unit(master)))
    return out


def swap(player, unit: dict, new: str) -> None:
    """Make one roster row the unit `new`, keeping what carries over."""
    from player_state import limit_burst, need_unit_exp, unit_mst
    old = str(unit.get("master_id"))
    master = unit_mst(new) or {}
    level, exp = int(unit.get("level") or 1), int(unit.get("exp") or 0)
    unit["master_id"] = str(new)
    player.set_unit_level(unit["instance_id"], level)           # level within the cap, exp counters to match
    if int(unit.get("level") or 1) == level and 0 < exp < need_unit_exp(new, level + 1):
        unit["exp"] = exp                                         # the progress into the next level, when it fits
        unit["total_exp"] = int(unit.get("total_exp") or 0) + exp
    if limit_burst(new):
        unit["lb_level"] = max(1, min(int(unit.get("lb_level") or 1), int(master.get("ENwn42DV") or 1)))
    else:
        unit["lb_level"], unit["lb_exp"] = 0, 0
    if str(master.get("9fW0TePj")) != "7":
        unit["nv_ex_level"] = 0                                   # only a Neo Vision unit has EX levels
    if unit.get("granted_rarity") is not None:
        unit["granted_rarity"] = type(unit["granted_rarity"])(master.get("9fW0TePj") or unit["granted_rarity"])
    if str(unit.get("first_get_unit_id") or "") == old:
        unit["first_get_unit_id"] = type(unit["first_get_unit_id"])(new)


def repair(player) -> list:
    from player_state import no_shift_forms
    if (player is None or player.mode == "frozen" or not no_shift_forms()
            or (player.data.get(LEDGER) or {}).get("done")):
        return []
    found = forms_held(player)
    wanted = {instance: new for instance, _old, new in found}
    for unit in player.data.get("roster") or []:
        new = wanted.get(str(unit.get("instance_id")))
        if new:
            swap(player, unit, new)
    player.data[LEDGER] = {"done": True, "swapped": [list(row) for row in found]}
    player.dirty = True
    return found


def step(spec, reply_id, state):
    """Pipeline step: the login repair, before the roster is put in the reply."""
    if str(reply_id) not in LOGIN_REPLIES or state.player is None:
        return spec
    found = repair(state.player)
    if found:
        state.state_dirty = True
        from ffbe_gacha import unit_name
        print(f"shift forms: {len(found)} unit(s) summoned as a Brave Shift form are now the unit itself: "
              + ", ".join(f"{unit_name(old) or old} {old} -> {new} (owned unit {instance})"
                          for instance, old, new in found), flush=True)
    return spec
