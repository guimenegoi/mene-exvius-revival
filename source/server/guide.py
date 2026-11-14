"""The Guide (Library) check-offs: units, items, equipment, materia, Vision Cards and monsters (GitHub issue #4,
2026-11-11: "units, items, recipes, monsters etc. aren't checked off in the Guide").

The client keeps one bitmap per section (`UserDictionaryBase`, the same MSB-first hex string as the recipe book,
`PlayerState.recipe_book_rows`), filled from these reply groups (GL9 `GameResponseFactory::createResponseData`):

  section       group      field      bit index (`getItemIndex`)
  units         VpWnB21X   KJv6V7G9   F_UNIT_MST.QLfe23bu            (UnitMst +0x124)
  items         6RQhbe8m   KJv6V7G9   F_ITEM_MST.QLfe23bu            (ItemMst +0x5c)
  equipment     m4Bk5ex3   KJv6V7G9   F_EQUIP_ITEM_MST.QLfe23bu      (EquipItemMst +0x5c)
  materia       wiTU2Hy1   KJv6V7G9   F_MATERIA_MST.QLfe23bu         (MateriaMst +0x5c)
  vision cards  ap9do2GX   KJv6V7G9   F_VISION_CARD_MST.QLfe23bu     (VisionCardMst +0x144)
  monsters      aRhHK1S9   KJv6V7G9 seen, z41pMJvC Libra, 4yk1JQBs knockdown counts (comma list, one per
                           F_MONSTER_DICTIONARY_MST.QLfe23bu, `UserMonsterDictionary::getKnockdownCount`)
  recipes       ZrDPm3j5   eAM5B1qt   F_RECIPE_BOOK_MST.gJf3zp8a     (already served; the recipe book itself)

The server never sent the first six, so the Guide stayed empty. `rows(player)` sends them with every user-state
reply (PlayerState.groups): the save's register (`data["guide"]`) plus what is held now, read-only. The pipeline
step `register` (every reply) writes what is held now into the register, so a section only grows:
  * units: every form in the roster, and the lower forms of its family (same F_UNIT_MST.woghJa61, lower rarity):
    a 5★ Rain registers his 3★ and 4★ forms, as awakening went through them;
  * items, equipment, materia: what the bag, the equipment list and the materia list hold, including bag rows
    left at 0 (items once held and used up), equipped gear and materia;
  * Vision Cards: owned cards;
  * monsters: from battles fought from now on (`record_battle`, MissionEnd): the result's encountered monsters
    (`nar74pDu`), knockdowns (`f6M1cJgk`, `monster:count`) and Libra scans (`Dq4V7FtU`), mapped to dictionary ids
    through the battle's own monster rows (`wbet57nF` xqartN26 -> V9j8wJcC, kept on the attempt at load).
What the save never kept: units sold, fused or used as material, and items sold or used up without a 0 row, aren't
recoverable; monsters from battles before this change aren't either. EXVIUS_GUIDE=0 turns the Guide groups off.
"""
from __future__ import annotations

import os
from functools import lru_cache

SECTIONS = {   # section -> (group, master table, id field)
    "units": ("VpWnB21X", "F_UNIT_MST.ndjson", "3HriTp6B"),
    "items": ("6RQhbe8m", "F_ITEM_MST.ndjson", "tL6G9egd"),
    "equipment": ("m4Bk5ex3", "F_EQUIP_ITEM_MST.ndjson", "J1YX9kmM"),
    "materia": ("wiTU2Hy1", "F_MATERIA_MST.ndjson", "H5jBL0Vf"),
    "vision_cards": ("ap9do2GX", "F_VISION_CARD_MST.ndjson", "5giCMUd2"),
}
MONSTERS = ("aRhHK1S9", "F_MONSTER_DICTIONARY_MST.ndjson", "V9j8wJcC")
INDEX = "QLfe23bu"


def enabled() -> bool:
    return os.environ.get("EXVIUS_GUIDE", "1").strip() not in ("0", "off", "false", "no")


@lru_cache(maxsize=None)
def _index(table: str, key: str) -> dict:
    """id -> dictionary bit index (> 0) for one master table."""
    from player_state import _load_ndjson
    out = {}
    for row in _load_ndjson(table).get("__rows__", []):
        try:
            index = int(row.get(INDEX))
        except (TypeError, ValueError):
            continue
        if index > 0:
            out[str(row.get(key))] = index
    return out


def bitmap(indices) -> str:
    """The client's MSB-first hex bitmap (UserDictionaryBase::isRegistered tests bit 3 - index % 4)."""
    indices = [i for i in indices if i > 0]
    if not indices:
        return ""
    digits = [0] * (max(indices) // 4 + 1)
    for i in indices:
        digits[i // 4] |= 1 << (3 - i % 4)
    return "".join(format(n, "x") for n in digits)


@lru_cache(maxsize=1)
def _families() -> tuple[dict, dict]:
    """(unit id -> family key, family key -> [(rank, unit id)]). rank = (rarity, Neo Vision step): a 7-star unit,
    its Neo Vision form (`5Mgpv8hJ` 1) and its NV+ form (2) share the family and the rarity 7."""
    from player_state import _load_ndjson
    of, members = {}, {}
    for row in _load_ndjson("F_UNIT_MST.ndjson").get("__rows__", []):
        uid = str(row.get("3HriTp6B"))
        base = str(row.get("woghJa61") or uid)
        try:
            rank = (int(row.get("9fW0TePj") or 0), int(row.get("5Mgpv8hJ") or 0))
        except ValueError:
            rank = (0, 0)
        of[uid] = base
        members.setdefault(base, []).append((rank, uid))
    return of, members


def _register(player) -> dict:
    reg = player.data.setdefault("guide", {})
    for name in (*SECTIONS, "libra"):
        reg.setdefault(name, [])
    reg.setdefault("monsters", {})
    return reg


def _held(player) -> dict:
    """Ids held now (or once, for bag rows left at 0), per section."""
    out = {name: set() for name in SECTIONS}
    of, members = _families()
    for unit in player.data.get("roster", []):
        uid = str(unit.get("master_id"))
        out["units"].add(uid)
        forms = members.get(of.get(uid, uid), [])
        rank = next((r for r, form in forms if form == uid), (0, 0))
        for r, form in forms:
            if r < rank:
                out["units"].add(form)          # lower forms the unit was awakened through
        gear = unit.get("equipment") if isinstance(unit.get("equipment"), dict) else {}
        for item in gear.values():                  # equipped gear: slot -> item id ('0' = empty)
            if str(item or "0") != "0":
                out["equipment"].add(str(item))
        for mat in unit.get("materia") if isinstance(unit.get("materia"), list) else []:
            if str(mat or "0") != "0":
                out["materia"].add(str(mat))
    for it in player._items():
        kind = str(it.get("item_type"))
        if kind == "20":
            out["items"].add(str(it.get("item_id")))
        elif kind == "21":
            out["equipment"].add(str(it.get("item_id")))
        elif kind == "22":
            out["materia"].add(str(it.get("item_id")))
    for row in player.equip_item_rows():
        out["equipment"].add(str(row.get("J1YX9kmM")))
    for row in player.materia_rows():
        out["materia"].add(str(row.get("H5jBL0Vf")))
    for card in player.data.get("vision_cards", []):
        out["vision_cards"].add(str(card.get("vc_id") or card.get("id") or ""))
    return out


def register_holdings(player) -> bool:
    """Add what the save holds now to the register. True when anything was new."""
    reg = _register(player)
    changed = False
    for name, ids in _held(player).items():
        known = set(reg[name])
        new = sorted(i for i in ids if i and i not in known and i in _index(SECTIONS[name][1], SECTIONS[name][2]))
        if new:
            reg[name].extend(new)
            changed = True
    if changed:
        player.dirty = True
    return changed


def rows(player) -> dict:
    """The Guide reply groups for this save ({} when off)."""
    if not enabled() or player is None:
        return {}
    # Read-only: the register plus what is held now (a refused action must leave the save as it was);
    # `register` (a pipeline step) writes the new entries into the save.
    reg = player.data.get("guide") or {}
    held = _held(player)
    out = {}
    for name, (group, table, key) in SECTIONS.items():
        index = _index(table, key)
        ids = set(reg.get(name, [])) | held[name]
        hexed = bitmap(index[i] for i in ids if i in index)
        if hexed:
            out[group] = [{"KJv6V7G9": hexed}]
    monsters = reg.get("monsters") or {}
    if monsters or reg.get("libra"):
        index = _index(MONSTERS[1], MONSTERS[2])
        # Only up to the last registered monster: getKnockdownCount reads 0 past the end of the list.
        counts = [0] * (max((index[d] for d in monsters if d in index), default=0) + 1)
        for did, n in monsters.items():
            if did in index:
                counts[index[did]] = int(n)
        out[MONSTERS[0]] = [{"KJv6V7G9": bitmap(index[d] for d in monsters if d in index),
                             "z41pMJvC": bitmap(index[d] for d in reg.get("libra", []) if d in index),
                             "4yk1JQBs": ",".join(map(str, counts))}]
    return out


def monster_map(spec) -> dict:
    """Monster id -> dictionary id from a battle bundle's monster rows (`wbet57nF`)."""
    out = {}
    for row in (spec or {}).get("wbet57nF") or []:
        if isinstance(row, dict) and row.get("xqartN26") and row.get("V9j8wJcC"):
            out[str(row["xqartN26"])] = str(row["V9j8wJcC"])
    return out


def record_battle(spec, plaintext):
    """Pipeline step (MissionEnd): register the battle's monsters, once per loaded attempt."""
    import json
    from ffbe_config import RESULT_TAG
    from ffbe_state import State
    player = State.player
    if (not enabled() or player is None or player.mode == "frozen" or not isinstance(spec, dict)
            or RESULT_TAG not in spec or not plaintext):
        return spec
    try:
        req = json.JSONDecoder().raw_decode(plaintext)[0]
        result = (req.get("09HRWXDf") or [{}])[0]
    except Exception:  # noqa: BLE001
        return spec
    if not isinstance(result, dict):
        return spec
    attempt = player.data.get("exvius_repeat", {}).get("attempt", {})
    reg = _register(player)
    mark = [attempt.get("mid"), attempt.get("sequence")]
    if reg.get("last_battle") == mark:
        return spec
    known = attempt.get("guide_monsters") or {}
    index = _index(MONSTERS[1], MONSTERS[2])

    def dict_id(raw):
        raw = str(raw).strip()
        return known.get(raw) or (raw if raw in index else None)
    seen = {d for d in (dict_id(x) for x in str(result.get("nar74pDu") or "").split(",") if x) if d}
    knocked = {}
    for entry in str(result.get("f6M1cJgk") or "").split(","):
        parts = entry.split(":")
        if len(parts) >= 2 and parts[-1].strip().isdigit():
            d = dict_id(parts[0])
            if d:
                knocked[d] = knocked.get(d, 0) + int(parts[-1])
    libra = {d for d in (dict_id(x) for x in str(result.get("Dq4V7FtU") or "").split(",") if x) if d}
    if not (seen or knocked or libra):
        return spec
    monsters = reg["monsters"]
    for d in seen | set(knocked):
        monsters[d] = int(monsters.get(d, 0)) + knocked.get(d, 0)
    reg["libra"].extend(sorted(d for d in libra if d not in reg["libra"]))
    reg["last_battle"] = mark
    player.dirty = True
    State.state_dirty = True
    return spec


def register(spec, reply_id=None):
    """Pipeline step (every reply): keep what the save holds now in the Guide register."""
    from ffbe_state import State
    player = State.player
    if enabled() and player is not None and player.mode != "frozen" and register_holdings(player):
        State.state_dirty = True
    return spec
