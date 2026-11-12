"""English text the stock iPhone app is missing, added to the localized text tables it downloads.

The Android build answers some text lookups itself: hooks in `source/exvius/summon_menu.js` replace
`TextManager::getText` results for keys the shipped tables never had. The local Shop bundles
(`MST_BUNDLE_NAME_990000xxx`), the JP special-summon tickets (`MST_ITEM_NAME_1062130x0`) and banners the
shipped `F_TEXT_GACHA` doesn't name. The iPhone app has no hooks, so it printed the raw keys (seen live
2026-11-05 in the Shop's Bundles list). This module puts the same text into the tables themselves:

- each text table is one or more lines of base64 AES-ECB, each decrypting to `KEY^text^text...` records;
  missing keys are appended as one more line, in the table's own record shape;
- the patched table gets a new version number (`Ver<N>_<token>.dat`), and the localized-text index
  (`F_LOCALIZED_TEXT_MST`) is served with that version and the patched file's MD5 and size, which is how
  the app picks text files;
- `ios_tables.py` routes the requests here and raises the index's own advertised version.

Existing records are only replaced where the Android hook replaces them too (a banner's `name_override`).
Explanations are added only for banners with none.

Also covered (2026-11-05): everything else the Android hooks fill in at run time (reconstructed EX-bonus
ability names and descriptions, monster and monster-skill names of reconstructed battles and the
Colosseum, the "Story" dungeon entry, Clash of Wills / Dark Visions area names), the SP tickets' short and
long descriptions, and the obtainable items whose English text is missing (ios_text_items.json). Those
are written only where the shipped table has no usable English text.
"""
from __future__ import annotations

import base64
import glob
import hashlib
import json
import os
import re
import zlib

INDEX = ("F_LOCALIZED_TEXT_MST", "i5QEJpua", "R8PYPnJ9")
# (file token, AES key text) per table, from the name/token/key string triplets in libgame.
TABLES = {
    "F_TEXT_BUNDLE": ("4OBhnBKu", "3VkESseA"),
    "F_TEXT_ITEM_NAME": ("VhkhtvDn", "xDkegMbe"),
    "F_TEXT_ITEM_EXPLAIN_SHORT": ("IAPS1jOu", "TZh30bbo"),
    "F_TEXT_ITEM_EXPLAIN_LONG": ("9NCIDltW", "s3fVSywt"),
    "F_TEXT_GACHA": ("ZJz5QwAy", "Ab2Kb6yJ"),
    "F_TEXT_ABILITY_NAME": ("eSB5Ry3E", "At4ghcWo"),
    "F_TEXT_ABILITY_EXPLAIN_SHORT": ("8GJBzdQV", "D9UVupRQ"),
    "F_TEXT_MONSTER_NAME": ("0xkPiwVI", "UOz3hI2k"),
    "F_TEXT_MONSTER_SKILL_NAME": ("F1z92dkt", "B41kLp2C"),
    "F_TEXT_AREA_NAME": ("4qiOcmtJ", "FhWJxFlW"),
    "F_TEXT_DUNGEON_NAME": ("AyVqkz2B", "0cqVvd61"),
    "F_TEXT_ITEM_EQUIP_NAME": ("E0NdslwL", "SGMI0nIq"),
    "F_TEXT_ITEM_EQUIP_SHORT": ("Nao9HYWk", "I0l1uc2s"),
    "F_TEXT_ITEM_EQUIP_LONG": ("CD4giPVu", "jqe9yQm0"),
    "F_TEXT_MATERIA_NAME": ("2Eg5s20D", "E5jbLGyb"),
    "F_TEXT_MATERIA_EXPLAIN_SHORT": ("8g18k8jD", "DvdwoXYQ"),
    "F_TEXT_MATERIA_EXPLAIN_LONG": ("QEbXmDTD", "3ZaDmbq1"),
    "F_TEXT_IMPORTANT_ITEM_NAME": ("TIKwbf3D", "lx4HCdrQ"),
    "F_TEXT_IMPORTANT_ITEM_EXPLAIN_SHORT": ("YBqAUJt1", "Fc6H1Udw"),
    "F_TEXT_IMPORTANT_ITEM_EXPLAIN_LONG": ("aJ4tvgSq", "iElLxksB"),
    "F_TEXT_NV_SHOP_PRODUCT_NAME": ("s5K4EzVy", "spxNTzFX"),
    "F_TEXT_NV_SHOP_PRODUCT_SHORT_DES": ("39tuQBKk", "bLUjnqGk"),
    "F_TEXT_NV_SHOP_PRODUCT_LONG_DES": ("jhDV9jT6", "uaCuMXaq"),
    "F_TEXT_DAILY_QUEST_NAME": ("FBBD8vv6", "BhDl8FWG"),
    "F_TEXT_DAILY_QUEST_DETAIL": ("gCfFcx75", "xpLyjA9A"),
    "F_TEXT_CHALLENGE_NAME": ("4bQbA2FH", "SFaS7rXZ"),     # restored challenges (reward_overrides.py)
    # Exchange stores named after the merchant opening them this week (captain_menu.merchants, 2026-11-10).
    "F_TEXT_TOWN_STORE": ("h23JuUGF", "Jovaw62m"),
    "F_TEXT_TOWN_STORE_OWNER_NAME": ("KFL34pbm", "Q9HMWNZG"),
}
# Tables whose text follows the replay week: they also take captain_menu's names revision, which only goes up.
WEEKLY = ("F_TEXT_TOWN_STORE", "F_TEXT_TOWN_STORE_OWNER_NAME")
# Per reward kind: (name table, prefix), (short table, prefix), (long table, prefix).
ITEM_TEXT = {
    "20": (("F_TEXT_ITEM_NAME", "MST_ITEM_NAME_"), ("F_TEXT_ITEM_EXPLAIN_SHORT", "MST_ITEM_SHORTDESCRIPTION_"),
           ("F_TEXT_ITEM_EXPLAIN_LONG", "MST_ITEM_LONGDESCRIPTION_")),
    "21": (("F_TEXT_ITEM_EQUIP_NAME", "MST_EQUIP_ITEM_NAME_"), ("F_TEXT_ITEM_EQUIP_SHORT", "MST_EQUIP_ITEM_SHORTDESCRIPTION_"),
           ("F_TEXT_ITEM_EQUIP_LONG", "MST_EQUIP_ITEM_LONGDESCRIPTION_")),
    "22": (("F_TEXT_MATERIA_NAME", "MST_MATERIA_NAME_"), ("F_TEXT_MATERIA_EXPLAIN_SHORT", "MST_MATERIA_SHORTDESCRIPTION_"),
           ("F_TEXT_MATERIA_EXPLAIN_LONG", "MST_MATERIA_LONGDESCRIPTION_")),
    "23": (("F_TEXT_IMPORTANT_ITEM_NAME", "MST_IMPORTANT_ITEM_NAME_"),
           ("F_TEXT_IMPORTANT_ITEM_EXPLAIN_SHORT", "MST_IMPORTANT_ITEM_SHORTDESCRIPTION_"),
           ("F_TEXT_IMPORTANT_ITEM_EXPLAIN_LONG", "MST_IMPORTANT_ITEM_LONGDESCRIPTION_")),
}
_HERE = os.path.dirname(os.path.abspath(__file__))

# The JP special summons' ticket items (F_ITEM_MST 106213030-080) have no Global English name
# (same list as summon_menu.js).
TICKET_NAMES = {
    "106213040": "SP Summon Ticket",
    "106213050": "4★/5★/NV SP Summon Ticket",
    "106213030": "5★/NV SP Summon Ticket",
    "106213060": "Bonus Summon Ticket",
    "106213070": "Boss Rush Summon Ticket",
    "106213080": "Brave Ability Box Ticket",
}

# Their short and long descriptions (the Shop's bundle details and the item list print them).
TICKET_DESCRIPTIONS = {
    "106213040": "Use for one SP Special Summon.",
    "106213050": "Use for one 4★/5★/NV SP Special Summon.",
    "106213030": "Use for one 5★/NV SP Special Summon.",
    "106213060": "Use for one Bonus Summon.",
    "106213070": "Use for one Boss Rush Event Summon.",
    "106213080": "Use for one Brave Ability Enhancement Box Summon.",
}
TICKET_LONG = " The summon appears on the Summon screen while you hold this ticket."

# Raise by one whenever the text additions change: the phone only re-downloads a table whose advertised
# version went UP, and the checksum part alone can go down. 1 = bundles/tickets/banners (2026-11-05),
# 2 = item descriptions and the Android hook texts (2026-11-05), 3 = exchange shop product names (2026-11-07),
# 4 = Bonus Present Ticket and Hill of Fortune bundles (2026-11-07), 5 = NV Unit Select exchanges (2026-11-07),
# 6 = custom daily quests' names and descriptions (2026-11-07, daily_custom.py),
# 7 = event exchanges' product names (2026-11-09, content/event_exchanges.json),
# 8 = Orbonne Monastery Vaults' exchange added to them (2026-11-10),
# 9 = the two exchange-store name tables added (2026-11-10, WEEKLY).
# 10 = Kira's ability names (content/restored_unit_text.json, 2026-11-12).
GENERATION = 10

_CACHE: dict = {}
_JAPANESE = re.compile("[\u3040-\u30ff\u3400-\u9fff]")


def _shipped(table: str) -> dict[str, str]:
    """The shipped English text of one table (decoded copy in TEXT_DIR), first column."""
    key = ("shipped", table)
    if key not in _CACHE:
        out = {}
        try:
            import data_paths
            with open(os.path.join(data_paths.TEXT_DIR, table + ".ndjson"), encoding="utf-8") as fh:
                for line in fh:
                    row = json.loads(line)
                    values = [v for v in row.get("v") or [] if v]
                    out[row["key"]] = values[0] if values else ""
        except (OSError, ValueError, ImportError):
            pass
        _CACHE[key] = out
    return _CACHE[key]


def _bad(value, key: str) -> bool:
    """No usable English text: missing, the key itself, a TFA placeholder or Japanese (same test as the
    Android hook in source/exvius/menu_assets.js)."""
    return not value or value == key or value.startswith("TFA") or bool(_JAPANESE.search(value))


def _fill(out: dict, table: str, key: str, text) -> None:
    """Add `key` only where the shipped table has no usable English text for it."""
    if not text:
        return
    if _bad(_shipped(table).get(key), key):
        out[table][key] = (_clean(text), True)


def enabled() -> bool:
    return os.environ.get("EXVIUS_IOS_TEXT", "1") == "1"


def _clean(text: str) -> str:
    return " ".join(str(text).replace("^", " ").split())


def additions() -> dict[str, dict[str, tuple[str, bool]]]:
    """`{table: {key: (text, replace_existing)}}`."""
    if "additions" in _CACHE:
        return _CACHE["additions"]
    out: dict[str, dict[str, tuple[str, bool]]] = {name: {} for name in TABLES}
    bundles = {"990000001": "2,000 Friend Points"}
    try:
        with open(os.path.join(_HERE, "global_bundles.json"), encoding="utf-8") as fh:
            for bundle in json.load(fh).get("bundles", []):
                bundles[str(bundle["id"])] = str(bundle["name"])
    except (OSError, ValueError, KeyError):
        pass
    for bid, name in bundles.items():
        out["F_TEXT_BUNDLE"]["MST_BUNDLE_NAME_" + bid] = (_clean(name), False)
        out["F_TEXT_BUNDLE"]["MST_BUNDLE_DESC_" + bid] = (_clean(name), False)
    for iid, name in TICKET_NAMES.items():
        out["F_TEXT_ITEM_NAME"]["MST_ITEM_NAME_" + iid] = (name, False)
        out["F_TEXT_ITEM_EXPLAIN_SHORT"]["MST_ITEM_SHORTDESCRIPTION_" + iid] = (TICKET_DESCRIPTIONS[iid], False)
        out["F_TEXT_ITEM_EXPLAIN_LONG"]["MST_ITEM_LONGDESCRIPTION_" + iid] = (
            TICKET_DESCRIPTIONS[iid] + TICKET_LONG, False)
    _hook_texts(out)
    _daily_quests(out)
    try:                     # the challenges restored from the wiki (2026-11-10)
        import reward_overrides
        for row in reward_overrides.added_challenges():
            out["F_TEXT_CHALLENGE_NAME"]["MST_CHALLENGE_NAME_" + str(row["V36ygRYs"])] = (_clean(row["name"]), False)
    except Exception as exc:  # noqa: BLE001 -- the other texts still go out
        print(f"[ios-texts] restored challenge names skipped ({exc})", flush=True)
    _reachable_items(out)
    _shop_products(out)
    try:
        from ffbe_gacha import all_banners, missing_gacha_names
        banners = all_banners()
        for gid, name in missing_gacha_names(banners).items():
            out["F_TEXT_GACHA"]["MST_GACHA_NAME_" + gid] = (_clean(name), True)
        for b in banners:
            gid = str(b["id"])
            text = ("Choose a unit or prism from the selection list." if b.get("selection") else
                    f"{len(b['steps'])}-step summon. Review each step's contents above." if b.get("steps") else
                    f"Summon {b.get('draws', 1)} reward(s). The button shows the cost. "
                    "See Drop Rates for the reward list.")
            out["F_TEXT_GACHA"]["MST_GACHA_EXPLAIN_LONG_" + gid] = (text, False)
            out["F_TEXT_GACHA"]["MST_GACHA_EXPLAIN_SHORT_" + gid] = (text, False)
    except Exception as exc:  # noqa: BLE001 -- bundles and tickets still get their names
        print(f"[ios-texts] banner names skipped ({exc})", flush=True)
    _CACHE["additions"] = out
    return out


def _daily_quests(out: dict) -> None:
    """Names and descriptions of the custom daily quests (daily_custom.py). The client builds both keys from
    the quest id and ignores the reply's text columns; the list row shows the description."""
    try:
        import daily_custom
        if not daily_custom.enabled():
            return
        for quest in daily_custom.quests():
            qid = str(quest["id"])
            out["F_TEXT_DAILY_QUEST_NAME"]["MST_DAILY_QUEST_NAME_" + qid] = (_clean(quest["name"]), True)
            out["F_TEXT_DAILY_QUEST_DETAIL"]["MST_DAILY_QUEST_DETAIL_" + qid] = (_clean(quest["detail"]), True)
    except Exception as exc:  # noqa: BLE001 -- the other texts still go out
        print(f"[ios-texts] daily quest texts skipped ({exc})", flush=True)


def _load(name: str):
    try:
        with open(os.path.join(_HERE, name), encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return {}


def _hook_texts(out: dict) -> None:
    """The text the Android build's hooks supply at run time (source/exvius/menu_assets.js and
    summon_menu.js), written into the tables instead."""
    # Reconstructed EX-bonus abilities: name and description.
    for aid, row in (_load("content/exbonus_text.json") or {}).items():
        if not isinstance(row, dict):
            continue
        _fill(out, "F_TEXT_ABILITY_NAME", "MST_ABILITY_NAME_" + aid, row.get("name"))
        for prefix in ("MST_ABILITY_SHORTDESCRIPTION_", "MST_ABILITY_EXPLAIN_SHORT_", "MST_ABILITY_LONGDESCRIPTION_"):
            _fill(out, "F_TEXT_ABILITY_EXPLAIN_SHORT", prefix + aid, row.get("description"))
    # Abilities of units restored with hand-written English (Kira) that the restore missed (2026-11-12).
    for aid, row in ((_load("content/restored_unit_text.json") or {}).get("abilities") or {}).items():
        _fill(out, "F_TEXT_ABILITY_NAME", "MST_ABILITY_NAME_" + aid, row.get("name"))
        _fill(out, "F_TEXT_ABILITY_EXPLAIN_SHORT", "MST_ABILITY_SHORTDESCRIPTION_" + aid, row.get("description"))
    # Monster and monster-skill names of the reconstructed battles and the Colosseum.
    battle = _load("battle_names.json") or {}
    colosseum = _load("colosseum_names.json") or {}
    for mid, name in {**colosseum, **(battle.get("monster") or {})}.items():
        _fill(out, "F_TEXT_MONSTER_NAME", "MST_MONSTER_NAME_" + str(mid), name)
    for sid, name in (battle.get("skill") or {}).items():
        _fill(out, "F_TEXT_MONSTER_SKILL_NAME", "MST_MONSTER_SKILL_NAME_" + str(sid), name)
    # The story's own dungeon list entry, and the two native event modes' area names.
    _fill(out, "F_TEXT_DUNGEON_NAME", "MST_DUNGEONS_NAME_99999", "Story")
    try:
        from event_archive import events
        for row in events():
            mode = row.get("native_mode")
            label = {"tfa": "Clash of Wills", "parade": "Dark Visions"}.get(mode)
            if label:
                out["F_TEXT_AREA_NAME"]["MST_AREA_NAME_" + str(row["area"])] = (label, True)
    except Exception as exc:  # noqa: BLE001 -- the rest still applies
        print(f"[ios-texts] event mode names skipped ({exc})", flush=True)


def _reachable_items(out: dict) -> None:
    """Items a player can receive with no English name or description (ios_text_items.json, from an
    audit of every reward, shop and bundle list in the shipped tables and this server's files): fill the
    name, and use it as the description, so item screens never print MST_..._SHORTDESCRIPTION_<id>."""
    for ref, name in (_load("ios_text_items.json").get("items") or {}).items():
        kind, _, iid = ref.partition(":")
        if kind not in ITEM_TEXT:
            continue
        (name_table, name_key), short, long = ITEM_TEXT[kind]
        _fill(out, name_table, name_key + iid, name)
        name = name or _shipped(name_table).get(name_key + iid)
        for table, prefix in (short, long):
            _fill(out, table, prefix + iid, name)


# Reward kind -> (text table, key prefix) for naming a shop product after what it gives.
REWARD_NAMES = {
    "10": ("F_TEXT_UNITS_NAME", "MST_UNIT_NAME_"),
    "20": ("F_TEXT_ITEM_NAME", "MST_ITEM_NAME_"),
    "21": ("F_TEXT_ITEM_EQUIP_NAME", "MST_EQUIP_ITEM_NAME_"),
    "22": ("F_TEXT_MATERIA_NAME", "MST_MATERIA_NAME_"),
    "23": ("F_TEXT_IMPORTANT_ITEM_NAME", "MST_IMPORTANT_ITEM_NAME_"),
    "27": ("F_TEXT_VISION_CARD_NAME", "MST_VISION_CARD_NAME_"),
    "60": ("F_TEXT_RECIPE_BOOK_NAME", "MST_RECIPEBOOK_NAME_"),
}
CURRENCY_NAMES = {"30": "Gil", "31": "Friend Points", "50": "Lapis"}


def reward_text(raw: str) -> str:
    """'Metal Gigantuar's Here!', 'Lapis x200', 'Faceted Orb Recipe, Gil x1000' for a reward string."""
    parts = []
    for entry in filter(None, str(raw or "").split(",")):
        fields = entry.split(":")
        if len(fields) < 2:
            continue
        kind, iid = fields[0], fields[1]
        count = fields[2] if len(fields) > 2 and fields[2].isdigit() else "1"
        if kind in CURRENCY_NAMES:
            name = CURRENCY_NAMES[kind]
        else:
            table, prefix = REWARD_NAMES.get(kind, (None, None))
            name = _shipped(table).get(prefix + iid) if table else None
            if _bad(name, (prefix or "") + iid):
                name = out_names().get(kind + ":" + iid)
            if not name:
                return ""
            if kind == "60":
                name += " Recipe"
        parts.append(name + (f" x{int(count):,}" if count != "1" else ""))
    return ", ".join(parts)


def out_names() -> dict:
    """Names this module adds for items the shipped tables don't name (ios_text_items.json)."""
    return {ref: name for ref, name in (_load("ios_text_items.json").get("items") or {}).items() if name}


def _shop_products(out: dict) -> None:
    """The exchange shops' products are this server's own (exvius_shop_catalogue.py: fragment, VIP, coin,
    Obnixus Drop, Xenostone and event exchanges), numbered in ranges the shipped product texts partly use for
    other products. A product whose reward has no name of its own in the list (a vision card such as the VIP
    Shop's "Metal Gigantuar's Here!") showed `MST_NVSHOP_PRODUCT_NAME_<id>` (seen 2026-11-07). Name every
    product after its rewards."""
    try:
        from exvius_shop_catalogue import _catalogue
        _, products, _ = _catalogue(None)
    except Exception as exc:  # noqa: BLE001 -- the other additions still apply
        print(f"[ios-texts] shop product names skipped ({exc})", flush=True)
        return
    for row in products:
        pid, text = str(row["jPV7Xc4N"]), reward_text(row.get("P4puB2ch"))
        if not text:
            continue
        out["F_TEXT_NV_SHOP_PRODUCT_NAME"]["MST_NVSHOP_PRODUCT_NAME_" + pid] = (_clean(text), True)
        out["F_TEXT_NV_SHOP_PRODUCT_SHORT_DES"]["MST_NVSHOP_PRODUCT_SHORT_DES_" + pid] = (_clean(text), True)
        out["F_TEXT_NV_SHOP_PRODUCT_LONG_DES"]["MST_NVSHOP_PRODUCT_LONG_DES_" + pid] = (
            _clean("Exchange for " + text + "."), True)


def bump() -> int:
    """Added to each patched text table's version and to the index's advertised version."""
    if not enabled():
        return 0
    if "bump" not in _CACHE:
        blob = json.dumps(additions(), sort_keys=True, ensure_ascii=False).encode("utf-8")
        _CACHE["bump"] = 1000 * GENERATION + zlib.crc32(blob) % 1000
    return _CACHE["bump"]


def _weekly(name: str) -> tuple[int, dict]:
    """(revision, entries) of a WEEKLY table from the last login (captain_menu.refresh)."""
    if name not in WEEKLY:
        return 0, {}
    try:
        import captain_menu
        return captain_menu.names_rev(), captain_menu.store_texts().get(name, {})
    except Exception:  # noqa: BLE001
        return 0, {}


def index_bump() -> int:
    """Added to the text index's advertised version: `bump`, plus the store names' revision."""
    if not bump():
        return 0
    return bump() + _weekly(WEEKLY[0])[0]


def _ecb(key_text: str, decrypt: bool, data: bytes) -> bytes:
    from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
    from ffbe_crypto import key16
    cipher = Cipher(algorithms.AES(key16(key_text)), modes.ECB())
    op = cipher.decryptor() if decrypt else cipher.encryptor()
    return op.update(data) + op.finalize()


def _pad(data: bytes, layers: int) -> bytes:
    for _ in range(layers):
        n = 16 - len(data) % 16
        data += bytes([n]) * n
    return data


def patch_text(raw: bytes, key_text: str, entries: dict[str, tuple[str, bool]]) -> tuple[bytes, int]:
    """A text table with `entries` applied. Returns (bytes with LF line endings, records added or changed)."""
    out, seen, changed = [], set(), 0
    columns, shape_layers = None, None
    for line in raw.decode("ascii").splitlines():
        line = line.strip()
        if not line:
            continue
        plain = _ecb(key_text, True, base64.b64decode(line))
        layers = 0
        while plain and 1 <= plain[-1] <= 16 and plain[-plain[-1]:] == bytes([plain[-1]]) * plain[-1]:
            plain = plain[:-plain[-1]]
            layers += 1
        records = plain.decode("utf-8").split("\n")
        touched = False
        for i, record in enumerate(records):
            fields = record.rstrip("\r").split("^")
            if len(fields) < 2:
                continue
            if columns is None:
                columns, shape_layers = len(fields) - 1, layers
            seen.add(fields[0])
            entry = entries.get(fields[0])
            if entry and entry[1] and any(value != entry[0] for value in fields[1:]):
                records[i] = "^".join([fields[0]] + [entry[0]] * (len(fields) - 1)) + record[len(record.rstrip("\r")):]
                touched = True
                changed += 1
        if touched:
            line = base64.b64encode(_ecb(key_text, False, _pad("\n".join(records).encode("utf-8"), layers))).decode("ascii")
        out.append(line)
    if columns is None:
        raise ValueError("no text records found")
    missing = [key for key in sorted(entries) if key not in seen]
    if missing:
        plain = "".join("^".join([key] + [entries[key][0]] * columns) + "\n" for key in missing).encode("utf-8")
        out.append(base64.b64encode(_ecb(key_text, False, _pad(plain, shape_layers))).decode("ascii"))
        changed += len(missing)
    return ("\n".join(out) + "\n").encode("ascii"), changed


def _index_source(*roots):
    for root in roots:
        if root:
            hits = glob.glob(os.path.join(root, "mst", f"Ver*_{INDEX[1]}.dat"))
            if hits:
                return max(hits, key=lambda p: int(re.search(r"Ver(\d+)_", os.path.basename(p)).group(1)))
    return None


def _index_rows(raw: bytes):
    from ffbe_crypto import cbc_decrypt, key16
    for line in raw.decode("ascii").splitlines():
        line = line.strip()
        if not line:
            continue
        plain = cbc_decrypt(key16(INDEX[2]), line)
        pad = plain[-1]
        double = 1 <= pad <= 16 and plain[-pad:] == bytes([pad]) * pad
        yield line, json.loads(plain[:-pad] if double else plain), double


def _base_versions(*roots) -> dict[str, int]:
    src = _index_source(*roots)
    if not src:
        return {}
    return {row["a4hXTIm0"]: int(row["00zAYGYS"]) for _, row, _ in _index_rows(open(src, "rb").read())
            if row.get("a4hXTIm0") in TABLES and str(row.get("00zAYGYS", "")).isdigit()}


def patched_table(name: str, *roots) -> tuple[bytes, int, int] | None:
    """(bytes, records changed, served version) of one patched text table, cached."""
    rev, weekly = _weekly(name)
    cache_key = ("table", name, bump(), rev)
    if cache_key in _CACHE:
        return _CACHE[cache_key]
    base = _base_versions(*roots).get(name)
    if base is None:
        return None
    token, key_text = TABLES[name]
    for root in roots:
        path = os.path.join(root or "", "localized_texts", "en", f"Ver{base}_{token}.dat")
        if root and os.path.isfile(path):
            data, changed = patch_text(open(path, "rb").read(), key_text, {**additions()[name], **weekly})
            _CACHE[cache_key] = (data, changed, base + bump() + rev)
            return _CACHE[cache_key]
    return None


def patched_index(raw: bytes, *roots) -> tuple[bytes, list[str]]:
    from ffbe_crypto import cbc_encrypt, key16
    out, done = [], []
    for line, row, double in _index_rows(raw):
        name = row.get("a4hXTIm0")
        if name in TABLES:
            patched = patched_table(name, *roots)
            if patched:
                data, _, version = patched
                row.update({"00zAYGYS": str(version), "zptmZGqa": hashlib.md5(data).hexdigest(),
                            "MLOSu5E0": str(len(data))})
                line = cbc_encrypt(key16(INDEX[2]), json.dumps(row, ensure_ascii=False, separators=(",", ":")).encode("utf-8"),
                                   double_pad=double)
                done.append(name)
        out.append(line)
    return ("\n".join(out) + "\n").encode("ascii"), done


_TEXT_PATH = re.compile(r"(^|/)localized_texts/en/Ver(\d+)_([A-Za-z0-9]{8})\.dat$")
_INDEX_PATH = re.compile(r"(^|/)mst/Ver\d+_" + INDEX[1] + r"\.dat$")


def wants(rel: str) -> bool:
    if not bump():
        return False
    if _INDEX_PATH.search(rel):
        return True
    m = _TEXT_PATH.search(rel)
    return bool(m) and any(m.group(3) == token for token, _ in TABLES.values())


def serve(rel: str, *roots) -> tuple[bytes | None, str | None]:
    try:
        if _INDEX_PATH.search(rel):
            src = _index_source(*roots)
            if not src:
                return None, None
            data, done = patched_index(open(src, "rb").read(), *roots)
            return data, f"{os.path.basename(src)}, text version(s) raised for {', '.join(done) or 'nothing'}"
        m = _TEXT_PATH.search(rel)
        name = next(n for n, (token, _) in TABLES.items() if token == m.group(3))
        patched = patched_table(name, *roots)
        if not patched or int(m.group(2)) != patched[2]:
            return None, None  # an older version: serve the shipped file as is
        data, changed, _ = patched
        return data, f"{name}, {changed} English text record(s) added for the iPhone"
    except Exception as exc:  # noqa: BLE001 -- fall back to the shipped file
        return None, f"iPhone text patch failed ({exc})"
