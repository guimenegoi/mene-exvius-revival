"""The phone's Convert to Prism / Convert to Fragments rules, and the flag that marks an NV-awakened unit (2026-11-12).

Read from libgame (GL offsets; the iPhone app is the same game build):
  * conversion row: `SacrificeMstList` (F_SACRIFICE_MST, key `woghJa61`). Fields: `jBVop84T` rarity list,
    `tL6G9egd` prism, `q1PJQ3eE` fragments, `1swM3H4T` fragments for a summoned NV.
  * Convert to Prism (`UnitClassupUtils::isEnableTransformShine` 0x19b8140): the unit's FAMILY row (F_UNIT_MST
    `woghJa61`); the unit is not NV and not 7★ (`9fW0TePj`), and some value in `jBVop84T` is <= its rarity.
  * Convert to Fragments (`isEnableTransformPiece` 0x19b7d94, row from `getSacrificeMstTransformPiece` 0x19b8094):
    an NV Shift form (`I3SKJ4q0` >= 1) reads its NV form (`JPW8Vs40`). A summoned NV ("pure", see below) reads its
    FAMILY row and pays `1swM3H4T`; every other unit reads the row of its OWN unit id and pays `q1PJQ3eE`. The row's
    `jBVop84T` must allow the unit's rarity. A regular unit whose family has a 7★ form with an NV awakening
    (F_UNIT_CLASS_UP_MST) is listed only once that awakening exists (its date; always, here).
  * both lists also need (`isEnableTransformMaterial` 0x19b7a34): FUNCTION_SP_CLASSUP on, the unit not locked in a
    party or expedition, a FAMILY row whose `jBVop84T` allows the unit's rarity.
  * "pure" NV = `UnitInfoBase::isPureNeoVision` (0x1dd3210): an NV form (`5Mgpv8hJ` 1 or 2) whose player unit does
    NOT carry the NV-awakened flag. The flag is the player unit's `k9GFaWm1` (`UserUnitInfoResponse::readParam` ->
    `setNvSublimationUnitFlg`, UnitInfoBase+0x2a1). The server never sent it, so every NV counted as summoned and an
    awakened NV (Dark Fina 100000327, Lightning 213000117) read its family row, which has no `1swM3H4T`: not listed.
  * the buttons: `SacrificeRequest` `6kvFj2Kw` rows carry `ijEey5f7` 0 (Convert to Prism, `execTransShine`) or 1
    (Convert to Fragments, `execTransPiece`); summoned NVs go through `NvSacrificeRequest` `4Ncra9DF`.

Not the server's: Trust Coin conversion drops every NV unit in the phone's own code
(`checkDispUnitTransformTrustCoin` 0x26dad74), and Gil conversion lists a unit only when its sale price
(F_UNIT_MST `u18nfD7p`, `UnitMst::canSellUnit`) is above 0, which no NV form but one has.

EXVIUS_NV_AWAKENED_FLAG=0 stops sending the flag (awakened NVs then read their family row again, as before).
"""
from __future__ import annotations

import os

NV_FLAG = "k9GFaWm1"


def flag_enabled() -> bool:
    return os.environ.get("EXVIUS_NV_AWAKENED_FLAG", "1").strip().lower() not in ("0", "off", "false", "no")


def _unit(master_id) -> dict:
    from player_state import unit_mst
    return unit_mst(master_id) or {}


def _table() -> dict:
    from player_state import _load_ndjson
    return _load_ndjson("F_SACRIFICE_MST.ndjson", "woghJa61")


def is_nv(master: dict) -> bool:
    return str(master.get("5Mgpv8hJ") or "0") in ("1", "2")


def nv_awakened(master: dict) -> bool:
    """An NV form reached by NV awakening a regular unit (or its NV Shift form): F_UNIT_MST marks exactly these
    (`k9GFaWm1` 1: the 105 F_UNIT_CLASS_UP_MST targets from a regular 7★ and their 105 shift forms)."""
    return is_nv(master) and str(master.get(NV_FLAG) or "0") == "1"


def unit_row_flag(master_id) -> str | None:
    """The `k9GFaWm1` value for a player unit row, or None to leave it out."""
    if not flag_enabled():
        return None
    return "1" if nv_awakened(_unit(master_id)) else None


def pure_nv(master: dict) -> bool:
    return is_nv(master) and not (flag_enabled() and nv_awakened(master))


def _allows(row: dict | None, rarity: int) -> bool:
    values = [int(v) for v in str((row or {}).get("jBVop84T") or "").split(",") if v.strip().lstrip("-").isdigit()]
    return any(v <= rarity for v in values)


def family_row(master: dict) -> dict | None:
    return _table().get(str(master.get("woghJa61") or ""))


def prism(master: dict) -> str | None:
    """The prism item id Convert to Prism gives for this unit form, or None when the phone doesn't list it."""
    rarity = int(master.get("9fW0TePj") or 0)
    row = family_row(master)
    if not row or rarity == 7 or is_nv(master) or not _allows(row, rarity):
        return None
    item = str(row.get("tL6G9egd") or "")
    return item if item.isdigit() and item != "0" else None


def fragments(master: dict) -> str | None:
    """The reward text Convert to Fragments gives for this unit form, or None when the phone doesn't list it."""
    rarity = int(master.get("9fW0TePj") or 0)
    if not _allows(family_row(master), rarity):        # isEnableTransformMaterial
        return None
    form = master
    if int(master.get("I3SKJ4q0") or 0) >= 1:            # an NV Shift form reads its NV form
        form = _unit(master.get("JPW8Vs40")) or master
    pure = pure_nv(master)
    row = _table().get(str(form.get("woghJa61") if pure else form.get("3HriTp6B")))
    if not row or not _allows(row, int(form.get("9fW0TePj") or rarity)):
        return None
    items = str((row.get("1swM3H4T") if pure else row.get("q1PJQ3eE")) or "")
    return items or None


def gil_listed(master: dict) -> bool:
    return int(master.get("u18nfD7p") or 0) > 0


def trust_coin_listed(master: dict) -> bool:
    """Before the trust threshold (DefineMst UNIT_TRANS_AFFINITY_COUNT) and the lock checks."""
    return not is_nv(master) and str(master.get("Q1RJvK7r") or "0") == "1"


def phone_lists(roster) -> dict:
    """Which roster units each Convert list shows, by the phone's rules (locks and trust left out)."""
    out = {"prism": [], "fragments": [], "gil": [], "trust_coin": []}
    for unit in roster:
        master = _unit(unit["master_id"])
        entry = (str(unit["instance_id"]), str(unit["master_id"]))
        if prism(master):
            out["prism"].append(entry)
        if fragments(master):
            out["fragments"].append(entry)
        if gil_listed(master):
            out["gil"].append(entry)
        if trust_coin_listed(master):
            out["trust_coin"].append(entry)
    return out
