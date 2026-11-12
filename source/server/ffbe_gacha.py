#!/usr/bin/env python3
"""ffbe_gacha.py — the GACHA axis: the authored banner layer, the pool/cost grammar, and the server-authoritative pull.

It is the largest module by line count and the one most likely to be edited by someone new, because the
banner data is JSON and inviting. The rule that keeps it honest: **the rates are ours.** They were
transmitted, never shipped, so nothing in this module is recovered data unless the docstring says so --
`gacha_community_rates.md` is the source for the community-sourced halves and every authored default is
labelled at its definition.

Extracted 2026-09-26 from `capture_server.py` (docs/SERVER_REFACTOR_PLAN.md, Phase 3, last seam).
"""
from __future__ import annotations

import copy, json, os, re

from ffbe_config import *          # noqa: F401,F403 -- constants; the table has no behaviour
import ffbe_state as st           # the REBOUND runtime state; see ffbe_state's docstring
from ffbe_state import State, _note
from player_state import COST_KINDS, cost_numeric_kind
from data_paths import TEXT_DIR


__all__ = [
    "GACHA_PLAYER_REFRESH_GROUPS",
    "all_banners",
    "authored_banners",
    "banner_art_index",
    "area_art_index",
    "button_art_index",
    "campaign_selection",
    "catalogue_banners",
    "community_banners",
    "gacha_button_base",
    "gacha_field_units",
    "gacha_groups",
    "gacha_offer_for",
    "gacha_only_ids",
    "gacha_secondary_detail_id",
    "gacha_tutorial_award",
    "serve_gacha",
    "serve_gacha_info",
    "standard_banners",
    "unit_name",
]

_BANNER_ART_INDEX: dict = {}
def banner_art_index() -> dict:
    """basename -> extracted file, built once (the banner CPK trees are small)."""
    if not _BANNER_ART_INDEX:
        for root in BANNER_ART_ROOTS:
            for dirpath, _dirs, files in os.walk(root):
                for fn in files:
                    _BANNER_ART_INDEX.setdefault(fn, os.path.join(dirpath, fn))
    return _BANNER_ART_INDEX
_AREA_ART_INDEX: dict = {}
def area_art_index() -> dict:
    """basename -> extracted file for the AREA art (the gate/list tile art family).

    A separate index from the banners on purpose: the two live in different CPK trees, so a name collision
    between them would be a coincidence rather than a meaning. Built once (2681 PNGs).
    """
    if not _AREA_ART_INDEX:
        for root in AREA_ART_ROOTS:
            for dirpath, _dirs, files in os.walk(root):
                for fn in files:
                    _AREA_ART_INDEX.setdefault(fn, os.path.join(dirpath, fn))
    return _AREA_ART_INDEX
_BUTTON_ART_INDEX: dict = {}
def button_art_index() -> dict:
    if not _BUTTON_ART_INDEX:
        for root in BUTTON_ART_ROOTS:
            for dirpath, _dirs, files in os.walk(root):
                for fn in files:
                    _BUTTON_ART_INDEX.setdefault(fn, os.path.join(dirpath, fn))
    return _BUTTON_ART_INDEX
def _btn_exists(base: str) -> bool:
    idx = button_art_index()
    return f"{base}_1.png" in idx or f"{base}_ticket_1.png" in idx
def _ticket_group_of(cost: dict):
    """The `F_TICKET_MST` group (`zF6QIY2r`) holding the cost item (`89EvGKHx` type, `tL6G9egd` id), or None."""
    from player_state import _load_ndjson
    kind = '23' if str(cost.get('kind')) == 'important' else '20'
    rows = _load_ndjson('F_TICKET_MST.ndjson')
    rows = rows.get('__rows__') or list(rows.values())
    for row in rows:
        if (isinstance(row, dict) and str(row.get('89EvGKHx')) == kind
                and str(row.get('tL6G9egd')) == str(cost.get('item_id')) and row.get('zF6QIY2r')):
            return int(row['zF6QIY2r'])
    return None


def _primary_cost(banner: dict) -> dict:
    """The banner's FIRST cost entry as a dict (for a class check). `cost` may be a LIST (multi-entry)."""
    cost = banner.get("cost")
    if isinstance(cost, list):
        cost = cost[0] if cost else {}
    return cost if isinstance(cost, dict) else {}
def gacha_button_base(banner: dict) -> str:
    """`img_btn` base: `gacha_btn_n` for the friend-point summon, else `gacha_btn_r` (see the note above)."""
    kind = str(_primary_cost(banner).get("kind") or "")
    return "gacha_btn_n" if kind == "friend_point" else "gacha_btn_r"
_UNIT_NAMES: dict = {}
def unit_name(master_id) -> str:
    """The English display name of a unit master id (shipped `F_TEXT_UNITS_NAME`), "" if unknown."""
    if not _UNIT_NAMES:
        path = os.path.join(TEXT_DIR, "F_TEXT_UNITS_NAME.ndjson")
        try:
            with open(path, encoding="utf-8") as fh:
                for ln in fh:
                    ln = ln.strip()
                    if not ln:
                        continue
                    r = json.loads(ln)
                    m = re.match(r"MST_UNIT_NAME_(\d+)$", str(r.get("key", "")))
                    if m:
                        v = r.get("v")
                        _UNIT_NAMES[m.group(1)] = v[0] if isinstance(v, list) and v else str(v)
        except (OSError, ValueError):
            pass
    return _UNIT_NAMES.get(str(master_id), "")
_GACHA_TEXT_IDS: set = set()
def missing_gacha_names(banners: list) -> dict:
    """`{id: name}` for the banners whose `MST_GACHA_NAME_<id>` the shipped text table (`F_TEXT_GACHA`) lacks
    -- the detail header otherwise prints the raw key. The summon hook answers `TextManager::getText` with these."""
    if not _GACHA_TEXT_IDS:
        try:
            with open(os.path.join(TEXT_DIR, "F_TEXT_GACHA.ndjson"), encoding="utf-8") as fh:
                for ln in fh:
                    m = re.search(r'"MST_GACHA_NAME_(\d+)"', ln)
                    if m:
                        _GACHA_TEXT_IDS.add(m.group(1))
        except OSError:
            pass
    return {str(b["id"]): str(b.get("name") or "Summon") for b in banners
            if str(b["id"]) not in _GACHA_TEXT_IDS or b.get('name_override')}
def gacha_field_units(banner: dict) -> list:
    """The unit ids the PAY detail scene poses on its field (`GachaDetailMst.t6aQ1voV`). The community rows
    carry the wiki's featured `unit_ids`; otherwise the pool's `featured` units. Empty -> no composite
    (`gacha_pay_field_research.md`: an empty `t6aQ1voV` suppresses the unit poses AND the monster).

    **ONE unit only.** `BUW0I4JL` carries one motion segment per unit and opcode `0` queues that unit's CG
    (cgs type 1); with several units the scene queues several CGs and cycles through them on screen — the
    live "flipping fast" plus a per-unit loading screen. One unit -> one pose, one load."""
    ids = [str(u) for u in (banner.get('preview_units') or
                            ((banner.get("community") or {}).get("unit_ids")) or [])]
    if not ids:
        pool = banner.get("pool")
        if isinstance(pool, dict):
            for t in pool.get("tiers") or []:
                ids += [str(u) for u in (t.get("featured") or [])]
            if not ids:
                # General ticket/reward banners have no featured rate boost,
                # but their real reward units can still populate the preview.
                for tier in pool.get('tiers') or []:
                    units = tier.get('units')
                    if isinstance(units, list):
                        ids += [str(unit) for unit in units if str(unit).isdigit()]
        elif isinstance(pool, list):
            ids += [str(row['unit_id']) for row in pool if row.get('unit_id')]
    if not ids and banner.get('selection'):
        # A select summon has no pool; pose the first unit its list offers so the pay scene draws its field.
        from player_state import _load_ndjson
        rows = _load_ndjson('F_GACHA_SELECT_UNIT_MST.ndjson')
        rows = rows.get('__rows__') or list(rows.values())
        ids += [str(r['3HriTp6B']) for r in rows[:1] if isinstance(r, dict) and r.get('3HriTp6B')]
    return ids[:1]
_CAMPAIGN_DOC = None          # lazily loaded `gacha_campaigns.json`
_CAMPAIGN_LOGGED = [False]    # the selection is announced once, not on every reply
_ONLY_LOGGED = [False]        # ditto for the single-banner mode
_STANDARD_DOC = None          # lazily loaded `gacha_standard.json`
_STANDARD_LOGGED = [False]    # the merge is announced once, not on every reply
def gacha_tutorial_award():
    """The authored forced-opening award `(unitId, granted_rarity)` from `server/gacha_authored.json`.

    AUTHORED, never recovered: the tutorial request carries no banner, so the client cannot be choosing it
    (schema §3.8 / shop_gacha_scope.md §4). The id is a real `F_UNIT_MST` id so the unit renders.
    """
    try:
        with open(GACHA_AUTHORED, encoding="utf-8") as fh:
            award = json.load(fh).get("tutorial_award") or {}
        return award.get("unitId"), award.get("granted_rarity")
    except (OSError, ValueError):
        return None, None
def _banner_doc(path: str, *, offset: int = 0, limit: int = 0, note: str) -> list:
    """The `banners` list from one gacha doc, sliced by `offset`/`limit`; [] and a note when unreadable."""
    try:
        with open(path, encoding="utf-8") as fh:
            bs = [b for b in (json.load(fh).get("banners") or [])
                  if isinstance(b, dict) and b.get("id")]
    except (OSError, ValueError) as exc:  # noqa: BLE001 - a bad doc must not kill the reply
        _note(f"gacha: {path} unreadable ({exc!r}) -- {note}")
        return []
    bs = bs[offset:]
    return bs[:limit] if limit else bs
def authored_banners() -> list:
    """The AUTHORED banners from `gacha_authored.json`. Never a shipped/recovered table -- the gacha content
    was transmitted, not shipped (docs/notes/gacha_reconstruction.md SS0)."""
    return _banner_doc(GACHA_AUTHORED, note="no banner can be served")
def catalogue_banners() -> list:
    """Documented Global campaigns assigned to the 273 retained shipped IDs.
    Anonymous assignments are recorded in catalogue_replacement. Off with `GACHA_CATALOGUE=0`; sliced by
    `GACHA_CATALOGUE_OFFSET`/`GACHA_CATALOGUE_LIMIT` (the rotation window)."""
    if not GACHA_CATALOGUE_ON:
        return []
    return _banner_doc(GACHA_CATALOGUE, offset=GACHA_CATALOGUE_OFFSET, limit=GACHA_CATALOGUE_LIMIT,
                       note="serving the authored set only")
def community_banners() -> list:
    """Global calendar names, dates, units and art, with recorded rate sources.
    Off with `GACHA_COMMUNITY=0`, sliced by `GACHA_COMMUNITY_LIMIT`."""
    if not GACHA_COMMUNITY_ON:
        return []
    return _banner_doc(GACHA_COMMUNITY, limit=GACHA_COMMUNITY_LIMIT, note="no community calendar")
def named_banners() -> list:
    """The NAMED banners: one per unused real Global banner image (`gacha_named.json`). Off with `GACHA_NAMED=0`."""
    if not GACHA_NAMED_ON:
        return []
    return _banner_doc(GACHA_NAMED, note="no named banners")
def deal_banners() -> list:
    """The DEAL banners (`gacha_deals.json`): step-ups, once-per-player 10+1s, free dailies and the other
    Global deal families, each on its real release date. Off with `GACHA_DEALS=0`."""
    if not GACHA_DEALS_ON:
        return []
    return _banner_doc(GACHA_DEALS, note="no deal banners")
def raid_banners() -> list:
    """The RAID summons (`gacha_raids.json`): each Global raid's coin-paid Raid Summon or Box Summon, on the raid's
    run date. Off with `GACHA_RAIDS=0`."""
    if not GACHA_RAIDS_ON or not os.path.exists(GACHA_RAIDS):
        return []
    return _banner_doc(GACHA_RAIDS, note="no raid summons")
def standard_banners() -> list:
    """The STANDARD families (SW-75) from `gacha_standard.json` -- the static, never-campaign-tied FREE-tab
    summons. Authored (`source: standard-authored`); the ids/titles are shipped. Off unless `GACHA_STANDARD=1`."""
    if not GACHA_STANDARD_ON:
        return []
    global _STANDARD_DOC
    if _STANDARD_DOC is None:
        try:
            with open(GACHA_STANDARD_FILE, encoding="utf-8") as fh:
                _STANDARD_DOC = json.load(fh)
        except (OSError, ValueError) as exc:  # noqa: BLE001 - a bad standard file must not kill the reply
            _note(f"gacha standard: {GACHA_STANDARD_FILE} unreadable ({exc!r}) -- serving none")
            _STANDARD_DOC = {}
    return [b for b in (_STANDARD_DOC.get("banners") or [])
            if isinstance(b, dict) and b.get("id") and b.get("serve", True)]
def campaign_selection() -> tuple | None:
    """`(standard_ids, allowed_ids, label)` for the active campaign, or None when serving everything.
    A campaign is a SELECTION -- the standard set plus one community release month. The key comes from
    `GACHA_CAMPAIGN`, or from the campaign file's own `default` when that env var is UNSET (so a reset cannot
    lose it); `all`/`off`/`0` explicitly disables the filter."""
    global _CAMPAIGN_DOC
    key = str(st.GACHA_CAMPAIGN or "").strip()
    if key.lower() in GACHA_CAMPAIGN_OFF:
        return None
    if _CAMPAIGN_DOC is None:
        try:
            with open(GACHA_CAMPAIGN_FILE, encoding="utf-8") as fh:
                _CAMPAIGN_DOC = json.load(fh)
        except (OSError, ValueError) as exc:  # noqa: BLE001 - a bad campaign file must not kill the reply
            _note(f"gacha campaign: {GACHA_CAMPAIGN_FILE} unreadable ({exc!r}) -- serving EVERYTHING")
            _CAMPAIGN_DOC = {}
    doc = _CAMPAIGN_DOC or {}
    if not key:
        key = str(doc.get("default") or "")     # the file's default, not "everything"
        if not key:
            return None
    camp = (doc.get("campaigns") or {}).get(key)
    if not camp:
        known = sorted((doc.get("campaigns") or {}))
        _note(f"gacha campaign: no campaign {key!r} ({len(known)} known: "
              f"{', '.join(known[:8])}...) -- serving EVERYTHING")
        return None
    std = {str(e["id"]) for e in (doc.get("standard") or []) if isinstance(e, dict) and e.get("id")}
    ids = std | {str(e["id"]) for e in (camp.get("banners") or [])
                 if isinstance(e, dict) and e.get("id")}
    return std, ids, str(camp.get("label") or key)
def gacha_only_ids() -> set:
    """The ids `GACHA_ONLY` (or `server/gacha_only.txt`) restricts the served set to; empty = no restriction."""
    raw = str(GACHA_ONLY or "").strip()
    if raw.lower() in GACHA_CAMPAIGN_OFF:
        return set()
    if not raw:
        try:
            with open(GACHA_ONLY_FILE, encoding="utf-8") as fh:
                raw = " ".join(fh.read().split())
        except OSError:
            return set()
    return {t for t in (s.strip() for s in raw.replace(",", " ").split()) if t}
def all_banners() -> list:
    """Catalogue + community + authored; the authored (curated FOCUSED SET) OVERRIDES by id so its exact
    art/cost/pool is kept. Ids never collide (generated/catalogue 1-8xxxxx, community 9xxxxxx, curated low).
    `GACHA_CAMPAIGN` slices the result to standard + one campaign period (see `campaign_selection`);
    `GACHA_STANDARD=1` then merges the STANDARD families (`standard_banners()`) on top of that slice."""
    by_id: dict[str, dict] = {}
    for b in catalogue_banners():
        by_id[str(b["id"])] = b
    for b in community_banners():
        by_id[str(b["id"])] = b
    for b in named_banners():
        by_id[str(b["id"])] = b
    for b in authored_banners():
        by_id[str(b["id"])] = b
    for b in deal_banners():
        by_id[str(b["id"])] = b
    for b in raid_banners():
        by_id[str(b["id"])] = b
    # Global's banners from 2023-08 to the end, rebuilt, and the real dates of the ones we had lumped (late_banners.py).
    import late_banners
    for b in late_banners.banners():
        by_id[str(b["id"])] = b
    late_banners.apply(by_id)
    # Archive identity merging shows a replacement and its calendar alias once.
    # Keep both IDs resolvable for requests already issued by an older client.
    only = gacha_only_ids()
    if only:
        kept = {k: v for k, v in by_id.items() if k in only}
        missing = sorted(only - set(kept))
        if not _ONLY_LOGGED[0]:
            _ONLY_LOGGED[0] = True
            _note(f"gacha ONLY: serving {len(kept)} of {len(by_id)} banner(s) "
                  f"({', '.join(sorted(kept))})" + (f" -- UNKNOWN ids: {', '.join(missing)}" if missing else ""))
        return list(kept.values())
    sel = campaign_selection()
    if sel:
        std, ids, label = sel
        kept = {k: v for k, v in by_id.items() if k in ids}
        if not _CAMPAIGN_LOGGED[0]:
            _CAMPAIGN_LOGGED[0] = True
            _note(f"gacha campaign {st.GACHA_CAMPAIGN or '(file default)'!r} "
                  f"({label}): serving {len(kept)} banner(s) "
                  f"= {len(std)} standard + {len(set(kept) - std)} campaign, of {len(by_id)} available")
        result = list(kept.values())
    else:
        result = list(by_id.values())
    # The STANDARD families are evergreen: merged ON TOP of (never filtered by) the campaign slice.
    std_banners = standard_banners()
    if std_banners:
        have = {str(b["id"]) for b in result}
        added = [b for b in std_banners if str(b["id"]) not in have]
        if added and not _STANDARD_LOGGED[0]:
            _STANDARD_LOGGED[0] = True
            fams = _STANDARD_DOC.get("_meta", {}).get("families") if _STANDARD_DOC else []
            _note(f"gacha standard: serving {len(added)} standard banner(s) "
                  f"({len(std_banners)} available, {len(fams)} families) on top of {len(result)}")
        result = result + added
    from banner_deals import apply as with_printed_deals   # bonuses printed on the art (banner_deals.py)
    return [with_printed_deals(with_global_buttons(b)) for b in result]
_GOLD_MAX = 11
def _gold_button(cost: dict, draws) -> str:
    """The client's own Global summon button (`gacha_btns_gold_*`, 204x96, label baked in, price drawn in its
    bar) for one cost entry: `Summon`/`N Summons` for Lapis, `Summon Free` for a free pull, and the gold
    button for a ticket (the client appends `_ticket` -> `Ticket Summon`). Friend point keeps `gacha_btn_n`."""
    kind = str((cost or {}).get("kind") or "free")
    if kind == "friend_point":
        return "gacha_btn_n"
    if kind == "free":
        return "gacha_btns_gold_free_1"
    if kind == "lapis":
        n = int(draws or 1)
        base = f"gacha_btns_gold_{n}"
        return base if 1 <= n <= _GOLD_MAX else "gacha_btn_r_multi"
    if kind in ("item", "important"):
        if cost.get('is_coin'):
            return 'gacha_btns_gold_1'
        # The original large ticket button keeps its one-line caption clear
        # of the native cost icon. The small two-line version overlaps it.
        return "gacha_btn_r_ticket"
    return "gacha_btns_gold_1"
def _step_button(cost: dict, draws) -> str:
    """The step-up scene (`GachaDetailScene`, layout 2) places the price for the big 304x136 buttons, so its
    rows wear the big Global family: `gacha_btn_r` (Summon), `gacha_btn_r_<N>times` (2-7), `gacha_btn_r_multi`
    (11 Summons), `gacha_btn_r_free`. The small gold art there draws the price below-right of its bar."""
    kind = str((cost or {}).get("kind") or "free")
    if kind == "free":
        return "gacha_btn_r_free"
    n = int(draws or 1)
    if kind == "lapis" and 2 <= n <= 7:
        return f"gacha_btn_r_{n}times"
    if kind == "lapis" and n == 11:
        return "gacha_btn_r_multi"
    return "gacha_btn_r"
def with_global_buttons(b: dict) -> dict:
    """Point every cost of a banner at the matching Global button. The big `gacha_btn_r` art the client gets
    otherwise draws the price on top of its baked "Summon" caption with an empty bar (phone, 2026-10-24).
    A single-pull Lapis banner also gets the retail second button: 11 Summons for 5000 Lapis (the Global
    10+1 price) unless it is `single_only` (the once-a-day 1/2 price summon). Authored button names are kept."""
    if str(b.get("type")) == "friend":
        return b
    b = dict(b)
    steps = b.get("steps")
    if steps:
        b["steps"] = [dict(st_, img_btn=st_.get("img_btn") or _step_button(st_.get("cost") or {}, st_.get("draws", 1)))
                      for st_ in steps]
        return b
    cost = _primary_cost(b)
    if not cost and not b.get("cost"):
        return b
    draws = b.get("draws", 1)
    # Rare tickets are group 10020 (items 50/70/80), not the legacy EX
    # tickets in group 10010. Publish the same group the purchase uses so
    # the native ticket button counts and spends the player's actual items.
    if (b.get('type') == 'normal' and cost.get('kind') == 'lapis'
            and int(cost.get('amount') or 0) == 500 and int(draws or 1) == 1
            and not b.get('single_only') and not b.get('daily_limit')
            and not b.get('purchase_limit')
            and b.get('ticket_group_id') in (None, 10010, '10010')):
        b['ticket_group_id'] = 10020
    # A select summon (GachaMst type 6, e.g. 9200030 5★ Select Summon) opens its unit list only when the
    # ticket it costs is in the detail row's ticket group: GachaDetailScene::touchEnded (0x213f9cc, type 6 ->
    # 0x213fbf4) asks TicketMstList::getMstObject(detail, type, id) (0x1c632fc), which searches only the
    # tickets of group detail+0x88 (`RZ6z12Dt`). With no group the tap silently did nothing (2026-11-10).
    if (str(b.get('type')) == 'select' and not b.get('ticket_group_id')
            and str(cost.get('kind')) in ('important', 'item') and cost.get('item_id')):
        group = _ticket_group_of(cost)
        if group:
            b['ticket_group_id'] = group
    if str(cost.get('kind')) in ('lapis', 'free'):
        b['img_btn_primary'] = _gold_button(cost, draws)
    else:
        b.setdefault("img_btn_primary", _gold_button(cost, draws))
    secondary = b.get('secondary_offer')
    if isinstance(secondary, dict) and str((secondary.get('cost') or {}).get('kind')) in ('lapis', 'free'):
        # The pay scene's price geometry belongs to the compact Global family.
        # Retained campaign records sometimes name the large step-up button.
        b['secondary_offer'] = dict(secondary, img_btn=_gold_button(secondary['cost'], secondary.get('draws', 1)))
    if (str(cost.get("kind")) == "lapis" and int(draws or 1) == 1 and not b.get("secondary_offer")
            and not b.get("single_only")
            and not isinstance(b.get("cost"), list)):
        b["secondary_offer"] = {"cost": {"kind": "lapis", "amount": GACHA_MULTI_LAPIS}, "draws": 11,
                                "exe_count": 1, "img_btn": "gacha_btns_gold_11"}
        if b.get("provenance") == "community":
            # The community art promises "a guaranteed 5★/NV unit with every 11 summon".
            b["secondary_offer"]["guarantee"] = {"rarity": 5}
    return b
def _gacha_cost_string(cost, draws: int = 1, item_id: int = 0) -> str:
    """`GachaDetailMst.costInfo` (0GgK6ytT) = `entry ("," entry)*`, each `kind:itemId:useCost:exeCount`
    (`parseCostInfo` 0x1cec090; `getUseCostValue` reads field[2], `getExeCount` field[3] --
    `gacha_banner_types.md` SS4). `draws` is a legacy name for exeCount, the PURCHASE count.
    GL9 multiplies the displayed cost by it. Pass 1 for a fixed multi-unit offer or step;
    banner.draws / step.draws separately controls how many units the server awards.
    Friend point = kind 51 -- `isFriendGacha` 0x1cecb24 is exactly that test. Empty string = no cost.

    `cost` may be a DICT (one entry) or a LIST of dicts (the `isCostInfoMulti` form) -- the PAY detail scene
    builds its buttons from the entries (`GachaPayDetailScene::setBtnLayout` 0x2157b94 reads `GACHA_MULTI` + the
    left/right prices + `_ticket`), so a single/double/ticket banner needs an entry per offer. An entry's own
    `draws` overrides the row's purchase count. A fixed 11-unit offer is `50:0:5000:1`."""
    entries = cost if isinstance(cost, list) else [cost or {}]
    out: list = []
    for e in entries:
        e = e if isinstance(e, dict) else {}
        kind = str(e.get("kind", "free"))
        if kind not in COST_KINDS:
            _note(f"gacha cost: unknown kind {kind!r} -- entry dropped (known: {sorted(COST_KINDS)})")
            continue
        num = cost_numeric_kind(kind)
        if num == 0:
            continue
        d = int(e.get("draws", draws))
        out.append(f"{num}:{int(e.get('item_id', item_id) or 0)}:{int(e.get('amount', 0))}:{d}")
    return ",".join(out)
def _gacha_art(art: dict, key: str) -> str:
    """The art filename for `key` in the preferred locale. `art` may carry a `key_en` English override;
    `GACHA_LANG=en` (default) prefers it when present, else falls back to `key` (the JP/`common_lang` file).
    All FOCUSED-SET banners are currently `region: jp`, so this is a no-op until EN art is added."""
    if GACHA_LANG == "en" and art.get(key + "_en"):
        return str(art[key + "_en"])
    return str(art.get(key, ""))
def gacha_secondary_detail_id(b: dict) -> str:
    """The detail id of a banner's SECOND (`exeType=2`) row. Distinct from the primary `nqzG3b2v` -- the client
    keys the rows by it, and `GachaExeRequest.nqzG3b2v` names the row the player TAPPED, so it is also how the
    roll resolves which offer to charge."""
    sec = b.get("secondary_offer") or {}
    return str(sec.get("detail_id") or (str(int(b["id"]) * 10 + 9)
                                         if str(b["id"]).isdigit() else str(b["id"]) + "2"))
def gacha_offer_for(banner: dict, detail_id: str):
    """The offer the tapped detail row means, or None for the primary row (whose cost/draws are the banner's
    own). `docs/notes/gacha_multi_button.md` SS9: the rows are `exeType`-partitioned, so the requested
    `nqzG3b2v` is the row selector."""
    if not detail_id or GACHA_MULTI_BTN == "0":
        return None
    sec = banner.get("secondary_offer")
    if isinstance(sec, dict) and sec and gacha_secondary_detail_id(banner) == str(detail_id):
        return sec
    return None
def _gacha_detail_row(b, art, detail_id, cost, draws, exe_type=None, img_btn=None) -> dict:
    """One `GachaDetailMst` row. `RZ6z12Dt` (ticketGroupId, +0x88) is emitted only for a ticket-only banner
    (empty cost + ticketGroupId>0 -> `isTicketOnlyGacha` true -> `TicketOnlyGachaDetailScene`);
    `LFoU0M3v` (gachaPanelId) only when the banner declares a panel. Step-ups get one row per step, with a
    detail id following the shipped convention `gachaId*10 + step`.

    `exe_type` overrides the banner's own `exe_type` (1 primary / 2 secondary, `ijEey5f7` +0x68) so ONE banner
    can emit several rows of different kinds. That field is the ONLY lever on the summon-button COUNT:    `GachaDetailScene::setLayout` (0x2140934) calls `setSingleButtonLayout` and `setMultiButtonLayout`
    UNCONDITIONALLY (both behind the `scene+0x6a0` suppression flag), and each self-gates on the presence of its
    OWN row -- `setSingleButtonLayout` (0x213cf3c) on `+0x5f0` (the `exeType==1` row), `setMultiButtonLayout`
    (0x213d3a4, gate at 0x213d3c8) on `+0x5f8` (the `exeType==2` row). `setGachaData` (0x213ca64) fills those
    two slots from `GachaDetailMstList::getListWithExeType(id, 1)` / `(id, 2)`. So a 1-row banner gets the
    standard single (+ticket) button and a 2-row banner gets the three-button layout.
    Evidence: `docs/notes/gacha_multi_button.md`."""
    det = {"X1IuZnj2": str(b["id"]), "nqzG3b2v": str(detail_id),
           "G4L0YIB2": str(b.get("name", "")),
           "ijEey5f7": str(GACHA_EXE_TYPE.get(str(exe_type or b.get("exe_type", "primary")), 1)),
           "0GgK6ytT": _gacha_cost_string(cost, draws,
                                          (cost.get("item_id", 0) if isinstance(cost, dict) else 0)),
           "4yT7FUqj": _gacha_banner_detail_string(_gacha_art(art, "detail_banner")),
           "XFLm4Mx6": img_btn or gacha_button_base(b)}
    # The BGM rides the DETAIL row (`9ZCEWn0z`/`wM9AfX6I` = +0x120/+0x124), which `getBgmMapResourceId` reads
    # FIRST (detail -> pay detail -> Mst+0x94). EMITTED ONLY WHEN AUTHORED -- see the `GACHA_BGM_RES_ID` block
    # above for why the default is "play nothing special and keep the home track". Emitted WITHOUT a version
    # still works (the resource is local); `GachaEntryScene::checkDownloadGachaBgm(id, ver)` is the only reader
    # of the version, and it is a CDN download check.
    bgm = str(b.get("bgm", "") or GACHA_BGM_RES_ID)
    if bgm and bgm != "0":
        det["9ZCEWn0z"] = bgm
        ver = str(b.get("bgm_version", "") or GACHA_BGM_RES_VERSION)
        if ver:
            det["wM9AfX6I"] = ver
    if b.get("ticket_group_id") and str(exe_type or b.get("exe_type", "primary")) != "secondary":
        det["RZ6z12Dt"] = str(b["ticket_group_id"])
    if b.get("panel_id"):
        det["LFoU0M3v"] = str(b["panel_id"])
    # A once-a-day offer: `1ovyP04j` is the row's exeLimit (+0x90, "<max>:<period>").
    # GachaDetailMst::getRemainingGachaLimit = max - today's UserGachaInfo termExeCnt for this gacha+detail
    # (UserGachaInfoList::getObjectToday), so the client shows the offer as used once it is spent.
    if (b.get("daily_limit") or b.get('weekly_limit')) and str(exe_type or b.get("exe_type", "primary")) != "secondary":
        det["1ovyP04j"] = f"{int(b.get('weekly_limit') or b['daily_limit'])}:1"
    elif b.get('lap_limit') and b.get('steps'):
        det['1ovyP04j'] = f"{int(b['lap_limit'])}:0"
    elif b.get('purchase_limit'):
        det['1ovyP04j'] = f"{int(b['purchase_limit'])}:0"
    if b.get('boxes'):
        det['h6Tg0oGd'] = str(b['box_id'])
    # The PAY detail scene's FIELD composite (`gacha_pay_field_rect`): the poses come from
    # `GachaDetailMst.t6aQ1voV` (`0:<unitId>`,...), the display names from `Rw4fS2m1` (`0:<name>`,...), and the
    # per-unit motion from `BUW0I4JL` (one `@`-segment per unit; opcode `0` = pose the unit). An EMPTY
    # `t6aQ1voV` makes `GachaPayDetailScene::setNewUILayout` (0x214a17c) return early -> no units AND no monster.
    # `gacha_pay_field_research.md`; bg/monster fall back to 100022 (Earth Shrine) / 3110010 (Ochu).
    units = gacha_field_units(b)
    if units and str(b.get("type")) != "friend":
        det["t6aQ1voV"] = ",".join(f"{i}:{u}" for i, u in enumerate(units))
        names = [f"{i}:{unit_name(u)}" for i, u in enumerate(units) if unit_name(u)]
        if names:
            det["Rw4fS2m1"] = ",".join(names)
        det["BUW0I4JL"] = "@".join("1,5" for _ in units)   # opcode 1 = NV/brave-shift, 5 = the LB/skill pair
    return det
def _gacha_banner_detail_string(banner: str) -> str:
    """`GachaDetailMst.bannerInfo` (`4yT7FUqj`, +0xc0): the `index:file` form `parseSetBannerInfo` requires.

    `GachaDetailScene::parseSetBannerInfo` `0x21433cc` reads `[mst+0xc0]` (`add x1, x2, #0xc0` at `0x21433f8`),
    splits on `,` then `:`, and `cmp x8, #0x30` at `0x21434ac` (= 2 x 24-byte `std::string`) DROPS any entry
    that is not exactly two fields; an accepted entry becomes `GachaBannerInfo{int @+0x0, string @+0x8}`.

    **This is NOT the field that draws the entry screen's `gacha_banner` slot.** It feeds a separate
    (virtual/address-taken) `getBannerInfoList` consumer (`0x2143a70`). The entry slot is fed by the
    *schedule* row -- see `_gacha_schedule_banner_string`. The earlier live run with `0:<file>` here was
    inconclusive about the entry slot for exactly that reason; the field is still kept in the 2-field form the
    parser demands. Evidence: `docs/notes/gacha_banner_draw_path.md` S4a/S4d.
    """
    return f"0:{banner}" if banner else ""
def _gacha_schedule_banner_string(banner: str, detail: str = "", extras=(), pad: bool = True) -> str:
    """`GachaScheduleMst.bannerInfo` (`4yT7FUqj`): the MIXED form the two screens need, and they are TWO
    different SLOTS (confirmed 2026-09-21):
      * the **LIST** entry reads the **bare** field `+0x60` -- `GachaTopScene::setListLayout` (`0x2120880`
        `getBannerInfo()`, then `0x21208cc` `getBannerPath(true, 0 /*main*/)` + the bare name + `createBanner`).
        A 1-field BARE entry fills it. That slot is WIDE (a `bnr_*_rotation_*` 600x120 file).
      * the **DETAIL** carousel reads the `vector<std::string>` at `+0x78` -- `GachaDetailScene::setBannerLayout`
        (`0x2138e54`), fetched from the `sub` dir (`getBannerPath(true, 1)`). A **2-field `index:file`** entry
        pushes the *string* into that vector. That slot is 640x392.

    One comma entry cannot satisfy both, so serve `"<list_bare>,0:<detail_file>"`. Previously we sent ONE file
    for both, so the wide list slot got the tall detail art.
    Evidence: `docs/notes/gacha_banner_draw_path.md` S0/S4d/S8.

    `pad`: the detail art goes to `GachaPayDetailScene` (3.5:1 frame, padded by banner_fit). False for
    banners that open the base `GachaDetailScene` (friend-point and other layout-0 summons), whose
    frame is 640x392 like the art.
    """
    name = banner or GACHA_DEFAULT_BANNER_ART
    from banner_fit import fit_name   # a fresh name for padded detail art (banner_fit.py)
    detail = fit_name(detail or name, pad)
    extra = "".join(f",{i}:{fit_name(f, pad)}" for i, f in enumerate(extras or (), 1))
    return f"{name},0:{detail}{extra}"
def _gacha_target_info(entry: dict) -> str:
    """`GachaPanelGroupMst.targetInfo` (7iJpH5zZ) = `TargetType:TargetID:TargetNum:TargetRate:TargetLv`
    (`setAnalyzeTargetInfo` 0x1ceb934 stores into +0x68/6c/70/74/78)."""
    rate = int(round(float(entry.get("rate", 0)) * GACHA_RATE_SCALE))
    return (f"{GACHA_TARGET_TYPE.get('unit', 10)}:{entry.get('unit_id')}:"
            f"{int(entry.get('num', 1))}:{rate}:{int(entry.get('lv', 1))}")
def gacha_type_code(b: dict) -> int:
    """`GachaMst.type` (`sx4kyW0i`, +0x8c). The summon screen files each banner on a tab by it; the
    offline archive moves event, free and ticket summons to their original tabs (`gacha_archive.wire_type`)."""
    code = GACHA_TYPE_CODE.get(str(b.get("type", "normal")), 0)
    if os.environ.get('EXVIUS_SUMMON_ARCHIVE') == '1':
        from gacha_archive import wire_type
        code = wire_type(b, code)
    return code
# Every banner stays available (Elv, 2026-10-24): it is served from its REAL original start date, where
# the data has one (the community calendar's `release`, a named banner's `release`), and never ends.
SERVED_END = "2099-12-31 23:59:59"


def _served_start(b, window):
    release = (b.get("community") or {}).get("release") or b.get("release")
    try:
        year, month, day = ([int(part) for part in str(release).split("-")[:3]] + [1, 1])[:3]  # "2024-07" = 1 July
        return "%04d-%02d-%02d 00:00:00" % (year, month, day)
    except (TypeError, ValueError):
        return str(window.get("from", ""))


def gacha_groups(banners: list) -> dict:
    """The five banner-layer reply groups + the player's per-banner state, from the authored banners.
    One `GachaPanelGroupMst` row PER POOL ENTRY (that row's `targetInfo` is the pool + rate)."""
    mst, detail, sched, panel, pgroup = [], [], [], [], []
    for configured in banners:
        b = configured
        if b.get('boxes'):
            from gacha_box import detail_id, box_id
            b = dict(b, detail_id=detail_id(State.player, b), box_id=box_id(State.player, b))
        art = b.get("art") or {}
        schedule_art = art  # Keep every step image in the native carousel/download catalogue.
        steps = b.get("steps") or []
        step_index = State.player.gacha_step(b) if steps and State.player else 0
        if steps:
            images = [art.get('detail_banner')] + list(art.get('detail_extra') or [])
            art = dict(art, detail_banner=images[min(step_index, len(images) - 1)], detail_extra=[])
        sd = b.get("schedule") or {}
        window = sd.get("window") or {}
        has_panel = bool(b.get("panel_id"))
        row = {"X1IuZnj2": str(b["id"]),
               "sx4kyW0i": str(gacha_type_code(b)),
               "XFLm4Mx6": gacha_button_base(b),
               "g38Pjk10": str(art.get("anime_file") or GACHA_DEFAULT_ANIME_FILE),
               "JDFMe3A7": str(art.get("anime_name") or GACHA_DEFAULT_ANIME_NAME),
               # GachaMst.displayType (+0x50) enables the original Drop Rates button.
               "8s9wNSpd": "1",
               "2RtVPS3b": "0"}
        # `7xBNR2MH` = `GachaMst.setGachaLayout` (+0x9c). `GachaMst::isPayGacha()` (0x1cea448) is exactly
        # `layout == 1`, and `GachaUtil::changeSummonSecondScene` (0x1a5314c branches on PLT `isPayGacha`)
        # routes on it: **1 -> `GachaPayDetailScene`** (the GOLD lapis/ticket buttons), else the base
        # `GachaDetailScene` (the BLUE friend button). So a pay banner MUST send 1 or it wears the friend
        # button; a step-up sends 2 (0x1cea458). An authored `gacha_layout` still wins.
        layout = b.get("gacha_layout")
        if layout is None:
            kind = str(_primary_cost(b).get("kind") or "")
            if str(b.get("type")) == "step":
                layout = 2
            elif kind not in ("free", "friend_point"):
                layout = 1                       # lapis / ticket / gil -> the pay detail scene
        if layout:
            row["7xBNR2MH"] = str(layout)
        mst.append(row)
        if steps:
            # GL9 selects the first primary detail row. The server publishes
            # the current step and replaces it after a successful pull.
            step = steps[step_index]
            sid = str(int(b["id"]) * 10 + step_index + 1)
            # One purchase of this step. GL9 multiplies useCost by exeCount
            # (clamped by affordability); the server's step.draws is the award count.
            detail.append(_gacha_detail_row(b, art, sid, step.get("cost"), 1,
                                            img_btn=step.get("img_btn")))
        else:
            swap = GACHA_MULTI_BTN == "swap"      # see the constant's comment: an exeType probe, not a feature
            # exeCount (costInfo [3]) stays 1: `GachaPayDetailScene::initialize` (0x2147344) drops a row whose
            # max play count is not 1 unless the player can pay for it more than once, and `setLayout` then
            # dereferences the missing row (crash, phone 2026-10-24). The units drawn come from `draws`.
            detail.append(_gacha_detail_row(b, art, b.get("detail_id", ""),
                                            b.get("cost"), 1,
                                            exe_type=("secondary" if swap else None),
                                            img_btn=b.get("img_btn_primary")))
            # A SECOND row (`exeType = 2`) is what produces the archive's three summon buttons (single /
            # 11-summons / ticket) -- see `_gacha_detail_row`'s docstring and `gacha_multi_button.md`. Opt-in
            # per banner via `secondary_offer`, because the shape is only PROVEN readable, not yet live-run.
            sec = b.get("secondary_offer")
            if GACHA_MULTI_BTN != "0" and isinstance(sec, dict) and sec:
                detail.append(_gacha_detail_row(b, art, gacha_secondary_detail_id(b),
                                                sec.get("cost") or b.get("cost"),
                                                # `exe_count` is the costInfo ENTRY [3] (the client's
                                                # `getExeCount()`/`getMaxPlayCount()`), which is NOT the same
                                                # thing as `draws` (the units we grant). Keep it 1: with
                                                # exeCount != 1 the pay multi button prints
                                                # `useCost * min(have/useCost, exeCount)` AND renders the
                                                # `GACHA_MULTI` "Nx Summon" caption -- neither is retail. The
                                                # "11" is the button art; the 11 units come from `draws`.
                                                # `docs/notes/gacha_multi_button.md` SS15.
                                                sec.get("exe_count", sec.get("draws", 11)),
                                                exe_type=("primary" if swap else "secondary"),
                                                img_btn=sec.get("img_btn")))
        sched.append({"X1IuZnj2": str(b["id"]),
                      "Z0EN6jSh": str(sd.get("disp_order", 1)),
                      "w2A76noc": str(sd.get("banner_type", 0)),
                      "4yT7FUqj": _gacha_schedule_banner_string(_gacha_art(schedule_art, "banner"),
                                                                 _gacha_art(schedule_art, "detail_banner"),
                                                                 schedule_art.get("detail_extra") or (),
                                                                 pad=str(layout or "0") in ("1", "2")),
                      "VjJQ51uG": _served_start(b, window),
                      "m8ivD4NX": SERVED_END,
                      "N2PkD9sy": _served_start(b, window)})
        if not has_panel:
            continue
        panel.append({"LFoU0M3v": str(b.get("panel_id", "")), "X1IuZnj2": str(b["id"]),
                      "vFqVXP19": str(b.get("panel_group_id", ""))})
        pool_rows = b.get("pool") if isinstance(b.get("pool"), list) else []
        for i, entry in enumerate(pool_rows):
            pgroup.append({"vFqVXP19": str(b.get("panel_group_id", "")),
                           "q4m8aKr0": str(b.get("detail_id", "")),
                           "7iJpH5zZ": _gacha_target_info(entry),
                           "Z0EN6jSh": str(i)})
    out = {GACHA_MST_TAG: mst, GACHA_DETAIL_TAG: detail, GACHA_SCHEDULE_TAG: sched,
           GACHA_PANEL_TAG: panel, GACHA_PANEL_GROUP_TAG: pgroup}
    for banner in banners:
        if banner.get('boxes'):
            from gacha_box import groups
            for tag, rows in groups(State.player, banner).items():
                out.setdefault(tag, []).extend(rows)
    return out
def serve_gacha_info(spec, reply_id: str):
    """Attach the authored banner layer to the reply that opens the gacha screen.

    `GachaEntryScene::initConnect` (0x211d7ac) sends `GachaEntryRequest` after `runDownloadMstAndRes(true)`,
    so the reply to that request is where the client expects the list; `GachaInfoRequest` (from
    `GachaDetailScene::updateGachaInfoRequest` 0x213ccf8) is the detail-scene refresh. A reply with neither
    id is left byte-for-byte alone. `spec` may be None (no keyed reply) -- the groups alone are a valid body.
    """
    if reply_id not in GACHA_INFO_REPLIES:
        return spec
    banners = all_banners()
    if not banners:
        return spec
    if os.environ.get('EXVIUS_SUMMON_ARCHIVE') == '1':
        from gacha_archive import visible_banners
        banners = visible_banners(State.player, banners)
    out = dict(spec) if isinstance(spec, dict) else {}
    out.update(gacha_groups(banners))
    out[GACHA_USER_INFO_TAG] = State.player.gacha_user_rows(banners) if State.player else []
    out[GACHA_STEP_INFO_TAG] = State.player.gacha_step_rows(banners) if State.player else []
    _note(f"gacha: served {len(banners)} authored banner(s) on reply {reply_id}")
    return out
def _request_gacha(plaintext: str | None) -> dict:
    """The client's OWN `5yLD4dYI` request node (banner id / detail id / ticket / repeat count).

    `raw_decode`, NOT `json.loads`: the client's manual PKCS#7 pad leaves trailing pad bytes (the pad
    VALUE varies with length), so `json.loads` raises "Extra data" -- same reason `mission_id_from` uses
    raw_decode. A partial parse is harmless here: no node means the tutorial/forced-summon path.
    """
    if not plaintext:
        return {}
    try:
        body = json.JSONDecoder().raw_decode(plaintext)[0]
    except Exception:  # noqa: BLE001
        return {}
    rows = body.get(GACHA_TAG) if isinstance(body, dict) else None
    return rows[0] if isinstance(rows, list) and rows and isinstance(rows[0], dict) else {}
def _award_str(a):
    """One `UJz5QED2` entry: `<type>:<unitId>:<userUnitId>:<lv>`.

    `GachaResultScene::initialize` (`0x217b008`-`0x217b01c`) splits each entry on `:` and calls
    `UserUnitInfoList::getObjectWithUserUnitID(field[2])`; a 2-field `10:<unitId>` reads field[2] out of
    bounds and SIGSEGVs (SW-78, `docs/notes/gacha_multi_button.md` SS17). Field[3] is the fallback lv
    (`UnitDataUtil::createMaxStatusUnitInfoForConvertUnit` `0x217b0a0`). The instance id comes from the
    `grant_unit` that `roll_gacha`/`tutorial_gacha` already performed -- no second source.
    """
    base = f"10:{a['unit_id']}"
    if a.get("instance_id") is None:
        return base
    return f"{base}:{a['instance_id']}:{int(a.get('level') or 1)}"
GACHA_PLAYER_REFRESH_GROUPS = (
    "B71MekS8",  # UserUnitInfoResponse — full roster
    "TJ9eL80N",  # UnitEquipResponse — full per-unit equipment
    "5Eb0Rig6",  # UserPartyDeckInfoResponse — full normal party list
    "8PEB5o7G",  # UserActualInfoResponse — active normal party id
    "49rQB3fP", "gP9TW2Bf", "1S8P2u9f",  # beast deck / owned espers / pieces
)
GACHA_OPTIONAL_REFRESH_GROUPS = ("4hPYneL3",)
VC_EFFECT_PATTERN_BASE = 38    # F_GACHA_EFFECT_PATTERN_MST 39..44 = Vision Card rarity 1..6   # UserVisionCardInfoResponse: an NV's Vision Card
def _gacha_player_refresh(out: dict) -> None:
    """Push the complete player-object projection after a real award.

    A gacha result tells the client which unit was awarded, but the roster, equipment and party
    singletons are separate response objects. Without these groups, a successful award can leave the
    result screen's unit object ahead of the lists used by the party editor. This is served data only;
    it does not patch or alter the client.
    """
    if State.player is None:
        return
    groups = State.player.groups()
    for tag in GACHA_PLAYER_REFRESH_GROUPS:
        out[tag] = groups[tag]
    for tag in GACHA_OPTIONAL_REFRESH_GROUPS:
        if groups.get(tag):
            out[tag] = groups[tag]
def serve_gacha(spec, plaintext: str | None = None, reply_id=None):
    """Make a summon real: roll an AUTHORED banner and GRANT the result into the roster.

    Two paths. (1) A request naming an authored banner (`X1IuZnj2`) rolls that banner's pool at its rates,
    spends its cost (`PlayerState.roll_gacha`), and serves the drawn units. (2) A bare/zero request is the
    forced tutorial summon -- one authored award (SW-61). The award is `UJz5QED2` = `<type>:<id>` with type
    10 = unit; `zoU5J3Kq` is the effect pattern, which the client does NOT validate (`shop_gacha_scope.md`
    SS6) -- but an ABSENT pattern is the `GACHA_EFFECT_ERROR` popup, so it is always set on a real result.
    Each `UJz5QED2` entry is `<type>:<unitId>:<userUnitId>:<lv>` (`_award_str`), not `<type>:<id>`.
    """
    if reply_id is not None and str(reply_id) != '9fVIioy1':
        return spec
    if not isinstance(spec, dict) or GACHA_TAG not in spec:
        return spec
    req = _request_gacha(plaintext)
    banner = next((b for b in all_banners() if str(b["id"]) == str(req.get("X1IuZnj2"))), None)
    out = copy.deepcopy(spec)
    def decline():
        # Never return the authored tutorial award for a transaction that failed.
        out[GACHA_TAG] = [{"X1IuZnj2": str(req.get("X1IuZnj2") or "0"),
                           "nqzG3b2v": str(req.get("nqzG3b2v") or "0"),
                           "zJ1A6HXm": "0", "2RtVPS3b": "0", "UJz5QED2": "",
                           "zoU5J3Kq": "1", "oY0vAuE9": "0"}]
        if State.player:
            out.update(State.player.currency_groups())
            # The server's own per-banner counts, so a refused once-a-day pull isn't shown as "Already
            # Summoned" (it wasn't counted: roll_gacha records the day only after a pull succeeds).
            try:
                banners = all_banners()
                if os.environ.get('EXVIUS_SUMMON_ARCHIVE') == '1':
                    from gacha_archive import visible_banners
                    banners = visible_banners(State.player, banners)
                out[GACHA_USER_INFO_TAG] = State.player.gacha_user_rows(banners)
            except Exception as exc:  # noqa: BLE001 -- the decline itself must still go out
                _note(f"gacha: counts not refreshed on a declined pull ({exc!r})")
        return out
    if banner is not None:
        # The CLIENT's request tokens (verified live 2026-09-21, `out/requests/*`, GachaExeRequest):
        #   `2RtVPS3b` = the REPEAT COUNT (1 for a single, 10 for a 10x)  -- NOT the ticket id
        #   `zJ1A6HXm` = the TICKET ID the player chose (12 = F_TICKET_MST item 180, the 5-star EX ticket)
        # Reading `zJ1A6HXm` as the repeat count made a 1x ticket pull try to spend 12 tickets and refuse.
        # NOTE the RESPONSE class (`GachaExeResponse`) uses the opposite token semantics (2RtVPS3b =
        # `setTicketId`, zJ1A6HXm = `setRepeatCnt`; shop_gacha_scope.md S6), so the node below follows THAT.
        repeats = int(req.get("2RtVPS3b") or 0) or 1
        ticket_id = req.get("zJ1A6HXm")
        # WHICH ROW was tapped: the client names it in `nqzG3b2v` (the detail row id), because the button row is
        # `exeType`-partitioned. The 11-summons button sends repeats=1 -- the count lives in that row's own
        # `exeCount` -- so without this the pull would charge the primary offer (`gacha_multi_button.md` SS9).
        req_detail = str(req.get("nqzG3b2v") or "")
        offer = gacha_offer_for(banner, req_detail)
        _note(f"gacha: pull banner {banner['id']} row={req_detail or '?'} "
              f"({'secondary offer' if offer else 'primary'}) repeats={repeats} ticket={ticket_id}")
        if State.player and banner.get('boxes'):
            from gacha_box import roll
            res = roll(State.player, banner, req_detail, repeats)
        else:
            res = State.player.roll_gacha(banner, repeats, ticket_id, offer=offer) if State.player else None
        if not res:
            _note(f"gacha: banner {banner['id']} pull x{repeats} (ticket {ticket_id}) refused "
                  f"(cost/affordability, or frozen); no award")
            return decline()
        from ffbe_player import score_quest_action
        from player_state import ticket_by_id, unit_mst
        conditions = [str(banner['id'])]
        if (banner.get('cost') or {}).get('kind') == 'friend_point':
            # The original Rookie quest describes condition 51 as a Friend Point summon.
            conditions.append('51')
        ticket = ticket_by_id(res.get('ticket_id'))
        if ticket:
            conditions.append(f'{ticket[0]}#{ticket[1]}')
        score_quest_action('5', res['count'], tuple(conditions))
        State.player.record_archive({'TOTAL_NV_UNIT_GET_CNT': sum(
            (unit_mst(award['unit_id']) or {}).get('9fW0TePj') == '7' for award in res['awards'])})
        detail_id = res["detail_id"]
        if offer is not None and req_detail:
            detail_id = req_detail                            # echo the row the player tapped
        _note(f"gacha: awarded {len(res['awards'])} draw(s) banner {banner['id']} row={detail_id} "
              f"({'secondary offer' if offer else 'primary'}) -- the count above is what the CLIENT asked for")
        if banner.get("steps"):   # the step's own detail row (gachaId*10 + step)
            detail_id = str(int(banner["id"]) * 10 + res["step"] + 1)
        node = {"X1IuZnj2": res["banner_id"], "nqzG3b2v": detail_id,
                "zJ1A6HXm": str(res["repeats"]),                 # GachaExeResponse: setRepeatCnt
                "2RtVPS3b": str(res.get("ticket_id") or 0),       # GachaExeResponse: setTicketId
                "UJz5QED2": ",".join(_award_str(a) for a in res["awards"]),
                "zoU5J3Kq": str(res["pattern_id"] or 1),
                # possibleCnt (UserGachaResult+0x24, `getPossibleCnt` 0x1ddf980). It GATES the multi/box
                # path: judgeExe errors at 0x21321b0 and onSceneVisible switches state when it is 0. Serve
                # the realised pull count (>0); see notes/response_field_map.md / gaps triage 2026-09-23.
                "oY0vAuE9": str(max(1, res['count']))}
        if banner.get('reward_pool'):
            node['yV45kbjw'] = '1'
        # The native result reader splits units from other rewards by kind.
        # GachaResultItemScene shows the latter after the unit result screen.
        item_bonuses = res.get('reward_awards', []) + [
            r for r in res.get('bonus_awards', []) if r['kind'] != 10]
        if item_bonuses:
            node['UJz5QED2'] = ','.join(filter(None, [node['UJz5QED2'],
                __import__('exvius_rewards').reward_text(item_bonuses)]))
        # The Vision Card of each NV pulled, in pull order: "27:<card id>:<owned card key>" (comma list).
        # UnitGetScene::touchEnded shows it after the NV (UserGachaResult::getNVResultData(true) keeps the
        # type-27 entries; the key resolves in UserVisionCardInfoList, served below in 4hPYneL3).
        if res.get("nv_cards"):
            node["eb2ANT1m"] = ",".join(f"27:{c['vc_id']}:{c['user_vc_id']}" for c in res["nv_cards"])
            # ...and its card animation, "<owned card key>:<GachaEffectPatternMst id>" in the same order
            # (UserGachaResult::getVCEffectPatternId / getVCUserId read 8schfem9). The Vision Card patterns
            # are 39-44: group 200009, one per card rarity 1-6, blocks gacha_vision_card_n1_c*.
            node["8schfem9"] = ",".join(f"{c['user_vc_id']}:{VC_EFFECT_PATTERN_BASE + c['rarity']}"
                                        for c in res["nv_cards"])
        out[GACHA_TAG] = [node]
        # Refresh the balances / held-ticket count alongside the result, so the client's currency display
        # updates without a separate user-state request (the result reply carries no LhVz6aD2).
        if State.player:
            out.update(State.player.currency_groups())
            if res.get('bonus_awards') or res.get('reward_awards'):
                out.update(State.player.groups())
            _gacha_player_refresh(out)
            # The detail scene returns straight from the result screen. Refresh
            # its step state in this reply, without requiring a new GachaEntry.
            if banner.get('steps') or banner.get('boxes'):
                banners = all_banners()
                if os.environ.get('EXVIUS_SUMMON_ARCHIVE') == '1':
                    from gacha_archive import visible_banners
                    banners = visible_banners(State.player, banners)
                refreshed = gacha_groups(banners)
                out[GACHA_DETAIL_TAG] = refreshed[GACHA_DETAIL_TAG]
                out[GACHA_SCHEDULE_TAG] = refreshed[GACHA_SCHEDULE_TAG]
                out[GACHA_STEP_INFO_TAG] = State.player.gacha_step_rows(banners)
                out[GACHA_USER_INFO_TAG] = State.player.gacha_user_rows(banners)
                for tag in ('z79fCYip', '05GvszcZ'):
                    if tag in refreshed:
                        out[tag] = refreshed[tag]
        step_note = f" step {res['step'] + 1}" if banner.get("steps") else ""
        print(f"    gacha: BANNER {res['banner_id']}{step_note} x{res['repeats']} -> {node['UJz5QED2']} "
              f"(pattern {node['zoU5J3Kq']}, ticket {res.get('ticket_id')}, "
              f"roster {len(State.player.data['roster'])}, stepNow {State.player.gacha_step(banner) + 1})",
              flush=True)
        return out
    if req.get("X1IuZnj2") not in (None, "", 0, "0"):
        _note('gacha: unknown requested banner; no award')
        return decline()
    master_id, rarity = gacha_tutorial_award()
    res = State.player.tutorial_gacha(master_id, rarity)
    rows = spec.get(GACHA_TAG)
    node = dict(rows[0]) if isinstance(rows, list) and rows and isinstance(rows[0], dict) else {}
    node["3HriTp6B"] = res["unit_id"]
    node["UJz5QED2"] = _award_str(res)
    node["zoU5J3Kq"] = str(res["pattern_id"])
    node["oY0vAuE9"] = "1"        # possibleCnt: >0 so the multi/box path is not errored (see above)
    out[GACHA_TAG] = [node]
    _gacha_player_refresh(out)
    print(f"    gacha: awarded {res['unit_id']} (granted rarity {res['granted_rarity']}, pattern "
          f"{res['pattern_id']}) -> roster now {len(State.player.data['roster'])} unit(s)", flush=True)
    return out
