"""Offline shop, crafting and enhancement actions for Global v9.

Awakenings use the shipped unit and EX masters. Service-only shop and gift
definitions live in content. Local companions reciprocate gifts once per UTC
day. Timed crafting exposes four independent slots per unlocked category.
Feature state is persisted in exvius_<feature> dictionaries; inventory/profile,
mailbox and switches retain their established PlayerState locations.
"""
from copy import deepcopy
from functools import wraps
from functools import lru_cache
from collections import Counter
from pathlib import Path
import json
import math
import random
import time

from exvius_actions import _node, _refresh, _mst, _parse_rewards, UNIT_GROUP
from ffbe_state import State, _note
from player_state import switch_position, STORAGE_CURRENCY

# AUTHORED policies, not recovered retail behavior. No randomized bonuses.
AUTHORED_CRAFT_CANCEL_REFUND = False
AUTHORED_CRAFT_RESULT_TRIPLES = True  # jsvoa0I2 = kind:id:count for plain recipes
AUTHORED_HIDDEN_REPLACE_PREDECESSOR = True  # preserve unrelated learned skills
AUTHORED_CARD_SUCCESS = 0             # verified ordinary result; no great/super RNG
AUTHORED_CARD_EXP_REMAINDER = True    # EXP is within level; total_exp is cumulative
AUTHORED_RETURN_MAIL_TITLE = "Master card returned"
AUTHORED_RETURN_MAIL_MESSAGE = "The removed master card is attached."

# Binary table 0x2f34330, not authored reward amounts.
CARD_RARITY_EXP = (0, 100, 200, 500, 1000, 1000, 3000, 5000)
PRODUCT_MASTERS = {20: ("F_ITEM_MST", "tL6G9egd"),
                   21: ("F_EQUIP_ITEM_MST", "J1YX9kmM"),
                   22: ("F_MATERIA_MST", "H5jBL0Vf"),
                   23: ("F_IMPORTANT_ITEM_MST", "2dfixko3"),
                   60: ("F_RECIPE_BOOK_MST", "staFu8U1")}


class Refused(ValueError):
    pass


def _require(ok, reason):
    if not ok:
        raise Refused(reason)


def _int(value, minimum=0):
    text = str(value)
    _require(text.isascii() and text.isdigit(), "invalid integer")
    number = int(text)
    _require(minimum <= number <= 2**63 - 1, "integer outside allowed range")
    return number


def _table(name, key=None):
    try:
        if name == "F_MEDAL_EXCHANGE_MST":
            return _fixed_medal_exchange(key)
        return _mst(name + ".ndjson", key)
    except FileNotFoundError:
        raise Refused(name + " is missing from shipped masters") from None


# Exchange rows that are wrong in the game's last table (content/medal_exchange_fixes.json). Battle at the
# Borders' store (900120, Hairpins) has 53 of its 57 rows priced in Debased Coins, The Frozen Cavern's
# currency (an event six weeks later); Global's own list of that run has every row in Hairpins (wiki "Battle
# at the Borders", King Mog). `store_currency` {store: currency} prices every row of the store in its currency.
# Every reader of the table here goes through `_table`/`_rows`; ios_tables serves the phone the same rows.
@lru_cache(maxsize=1)
def medal_exchange_fixes():
    """{exchange row id: {field: value}}."""
    path = Path(__file__).with_name('content') / 'medal_exchange_fixes.json'
    try:
        doc = json.loads(path.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return {}
    medals = _mst("F_MEDAL_EXCHANGE_MST.ndjson", "S21FT3L8")
    out = {}
    for store, currency in (doc.get('store_currency') or {}).items():
        for item in _mst("F_STORE_ITEM_MST.ndjson", None).get("__rows__", []):
            if str(item.get("Z20mNDvL")) == str(store) and str(item.get("YWF08vZS")) == "50":
                row = medals.get(str(item.get("6uIYE15X")))
                if row and str(row.get("ak2dhKm3")) != str(currency):
                    out[str(row["S21FT3L8"])] = {"ak2dhKm3": str(currency)}
    return out


@lru_cache(maxsize=None)
def _fixed_medal_exchange(key):
    table = _mst("F_MEDAL_EXCHANGE_MST.ndjson", key)
    fixes = medal_exchange_fixes()
    if not fixes:
        return table

    def fixed(row):
        return dict(row, **fixes[str(row.get("S21FT3L8"))]) if str(row.get("S21FT3L8")) in fixes else row
    if key is None:
        return {"__rows__": [fixed(row) for row in table.get("__rows__", [])]}
    return {rid: fixed(row) for rid, row in table.items()}


def _rows(name):
    return _table(name).get("__rows__", [])


def _define(name):
    row = _table("F_DEFINE_MST", "AK8Nn7ta").get(name)
    _require(row and row.get("YjIUDJ97") is not None, "missing define " + name)
    return row["YjIUDJ97"]


def _triples(text, rated=False):
    """Strict wrapper around the shared parser, never silently ignore a bad tuple."""
    if text in (None, ""):
        return []
    entries = [entry.strip() for entry in str(text).split(",")]
    text = ','.join(entries)
    if rated:
        parts = [entry.split(":") for entry in entries]
        _require(all(len(p) == 4 and p[3] == "100" for p in parts),
                 "unresolved reward probability/tuple")
        entries = [":".join(p[:3]) for p in parts]
    result = _parse_rewards(",".join(entries))
    _require(len(result) == len(entries), "invalid reward/material tuple")
    for row in result:
        _int(row["id"], 0 if row['kind'] in STORAGE_CURRENCY else 1)
        _int(row["count"], 1)
    return result


def _ids(text):
    values = str(text or "").split(",")
    _require(values and all(v.isascii() and v.isdigit() and int(v) > 0 for v in values),
             "invalid instance/master ID list")
    _require(len(values) == len(set(values)), "duplicate IDs")
    return values


def _feature(name):
    return State.player.data.get("exvius_" + name, {})


def _store(name, value):
    State.player.data["exvius_" + name] = value
    State.player.dirty = True


def _unit(iid):
    unit = next((u for u in State.player.data["roster"]
                 if str(u["instance_id"]) == str(iid)), None)
    _require(unit is not None, "unit is not owned")
    return unit


def _product(kind, iid):
    _require(kind in PRODUCT_MASTERS, "unsupported inventory kind")
    name, key = PRODUCT_MASTERS[kind]
    row = _table(name, key).get(str(iid))
    _require(row is not None, "unknown master product")
    return row


def _rewards(rows):
    for row in rows:
        kind = row["kind"]
        _require(kind in (10, 20, 21, 22, 23, 26, 27, 30, 50, 51, 60),
                 "unresolved reward ownership/projection for kind " + str(kind))
        if kind == 10:
            _require(str(row["id"]) in _table("F_UNIT_MST", "3HriTp6B"), "unknown reward unit")
        elif kind == 27:
            _require(str(row['id']) in _table('F_VISION_CARD_MST', '5giCMUd2'), 'unknown reward vision card')
        elif kind == 26:
            _require(str(row['id']) in _table('F_EMBLEM_ITEM_MST', '0w6XzofV'), 'unknown reward emblem')
        elif kind in PRODUCT_MASTERS:
            _product(kind, row["id"])
            if kind == 60:
                _require(State.player._can_credit(row), "recipe book has no native dictionary index")


def _grant(rows):
    # PlayerState has no materia projection; use its generic bag and emit rL81fVUI.
    previous = {str(unit['instance_id']) for unit in State.player.data['roster']}
    State.player._purchase = True         # bought, not earned: no Lapis multiplier (lapis_economy.py)
    try:
        State.player._grant_items([r for r in rows if r["kind"] not in (22, 26, 27)])
    finally:
        State.player._purchase = False
    for row in rows:
        if row['kind'] == 10:
            units = [unit for unit in State.player.data['roster']
                     if str(unit['instance_id']) not in previous
                     and str(unit['master_id']) == str(row['id'])][:row['count']]
            _require(len(units) == row['count'], 'reward unit grant was incomplete')
            for unit in units:
                if int(row.get('level', 1)) > 1:
                    State.player.set_unit_level(unit['instance_id'], int(row['level']))
                State.player._apply_unit_reward_metadata(unit, row)
                previous.add(str(unit['instance_id']))
        elif row["kind"] == 22:
            State.player.grant_item(22, row["id"], row["count"])
        elif row['kind'] == 26:
            State.player.grant_emblem(row['id'])
        elif row['kind'] == 27:
            cards = State.player.data.setdefault('vision_cards', [])
            for _ in range(row['count']):
                key = str(max([int(c['user_vc_id']) for c in cards] + [int(time.time() * 1000)]) + 1)
                # The level the reward names (`27:id:count:100:level`): the VC Select Ticket exchanges sell
                # their cards at level 10 (58 rows of F_MEDAL_EXCHANGE_MST); every other sold card is level 1.
                cards.append({'user_vc_id': key, 'vc_id': str(row['id']), 'level': int(row.get('level', 1)),
                              'exp': 0, 'total_exp': 0})
    if rows:
        State.player.dirty = True


def _pay(materials=(), gil=0):
    """Aggregate the entire batch before spending anything, including repeated costs."""
    totals = {}
    for row in materials:
        kind, iid = row["kind"], str(row["id"])
        _require(kind in (20, 21, 22, 23), "unsupported crafting material kind")
        totals[kind, iid] = totals.get((kind, iid), 0) + row["count"]
    _require(State.player.currencies.get("gil", 0) >= gil, "insufficient gil")
    equipment = {r['J1YX9kmM']: int(r['Qy5EvcK1']) for r in State.player.equip_item_rows()}
    worn = Counter()
    for unit in State.player.data['roster']:
        for kind, field in ((21, 'equipment'), (22, 'materia')):
            def counts(name):
                value = unit.get(name) or {}
                return Counter(str(v) for v in (value.values() if isinstance(value, dict) else value)
                               if str(v) not in ('', '0'))
            for iid, count in (counts(field) | counts('shift_' + field)).items():
                worn[kind, iid] += count
    for (kind, iid), count in totals.items():
        owned = equipment.get(iid, 0) if kind == 21 else State.player.item_count(kind, iid)
        _require(owned - worn[kind, iid] >= count, "insufficient unequipped materials")
    for (kind, iid), count in totals.items():
        if kind == 21:
            bag = State.player.data['inventory'].setdefault('equipment', [])
            row = next((r for r in bag if str(r.get('item_id')) == iid), None)
            if row is None:
                row = {'item_id': int(iid)}
                bag.append(row)
            row['count'] = equipment[iid] - count
            State.player.dirty = True
        else:
            _require(State.player.spend_item(kind, iid, count), "material debit refused")
    _require(State.player.spend_currency("gil", gil), "gil debit refused")


def _reply(spec):
    out = _refresh(spec)
    out.update(State.player.groups())
    out["rL81fVUI"] = [{"H5jBL0Vf": str(r["item_id"]), "Qy5EvcK1": str(r["count"])}
                         for r in State.player.data["inventory"]["items"]
                         if str(r["item_type"]) == "22" and r["count"] > 0]
    out['nSG9Jb1s'] = _archive_rows()
    out['3Ys8WPS6'] = State.player.emblem_rows()
    # The pipeline rebuilds B71MekS8. A later, complete mode-1 row restores flags.
    flags = _feature("sublimation").get("slots", {})
    if flags:
        delta = []
        for row in State.player._unit_rows():
            iid = row["og2GHy49"]
            if iid in flags:
                owner = row.pop("9Tbns0eI")
                row["T9Apq5fS"] = str(int(flags[iid]))
                row["9Tbns0eI"] = owner
                delta.append(row)
        out.pop("8gSkPD6b", None)
        out["8gSkPD6b"] = delta
    return out


def _archive_rows():
    """Native TrophyManager reads archive counters and persisted claim switches."""
    return State.player.archive_rows()


# Awakening handlers whose refusal must reach the phone as a message (client_message.py).
AWAKENINGS = frozenset({"unit_nv_class_up", "unit_nvp_class_up", "unit_ex_class_up"})


def _action(fn):
    @wraps(fn)
    def handle(spec, req):
        if State.player is None:
            return spec
        before, dirty = deepcopy(State.player.data), State.player.dirty
        try:
            _require(State.player.mode != "frozen", "player is frozen")
            return fn(spec, req)
        except Refused as exc:
            State.player.data, State.player.dirty = before, dirty
            _note(fn.__name__ + ": refused: " + str(exc))
            # Refresh optimistic balances, but never fabricate a success result row.
            out = _reply(spec)
            for tag in ("oh5yce1m", "6U5w20zk", "sWc7EH69", "14vWb7kX", "0T5wP98d", "0eDvu2N3",
                        "yeXn0tk1", "j0e1xIv9", "Duz1v8x9", "dnUSYLgn", "2Xi0wuGA", "Rv1YV69s"):
                out.pop(tag, None)
            if "WSH38iMI" in req:
                out["h5XGny0N"] = deepcopy(list(_feature("gift").get("receipts", {}).values()))
            if fn.__name__ in AWAKENINGS:
                # Without a result row the phone opens the awakening animation and crashes; a message stops it.
                import client_message
                client_message.set(f"The awakening couldn't be completed ({exc}). Nothing was used.")
            return out
        except Exception:
            State.player.data, State.player.dirty = before, dirty
            raise
    return handle


def _switches(out):
    from ffbe_battle import _switch_container
    out["ExQ7H1ok"] = [{"5opcUT9t": stype, "juA0Z4m7": _switch_container(out, stype)}
                         for stype in State.player.switches]
    return out


@_action
def item_sell(spec, req):
    """Settle native ItemSellRequest atomically against the projected inventory."""
    node = _node(req, "2tHu3Chy")
    _require(node is not None, "missing sale selection")
    rows = _triples(node.get("8X7LwE3r"))
    _require(rows, "empty sale selection")
    totals, price = {}, 0
    for row in rows:
        kind, iid = row["kind"], str(row["id"])
        _require(kind in (20, 21, 22), "unsupported sale kind")
        product = _product(kind, iid)
        price += _int(product.get("bz6RS3pI")) * row["count"]
        totals[kind, iid] = totals.get((kind, iid), 0) + row["count"]
    _require(_int(node.get("97h4mIQo")) == price, "sale price mismatch")
    equipment = State.player.data.get("inventory", {}).get("equipment", [])
    owned = {r["J1YX9kmM"]: int(r["Qy5EvcK1"]) for r in State.player.equip_item_rows()}
    worn, worn_materia = Counter(), Counter()
    for unit in State.player.data["roster"]:
        normal = Counter(str(iid) for iid in (unit.get('equipment') or {}).values())
        shifted = Counter(str(iid) for iid in (unit.get('shift_equipment') or {}).values())
        worn.update(normal | shifted)
        normal_materia = Counter(map(str, unit.get('materia') or []))
        shifted_materia = Counter(map(str, unit.get('shift_materia') or []))
        worn_materia.update(normal_materia | shifted_materia)
    for (kind, iid), count in totals.items():
        available = (owned.get(iid, 0) - worn.get(iid, 0) if kind == 21
                     else State.player.item_count(kind, iid) - (worn_materia[iid] if kind == 22 else 0))
        _require(available >= count, "insufficient unequipped sale inventory")
    for (kind, iid), count in totals.items():
        if kind == 21:
            row = next((r for r in equipment if str(r.get("item_id")) == iid), None)
            # The native ownership projection also includes starter equipment on units.
            # Persist the remaining total so selling spare copies preserves those wearers.
            remaining = owned[iid] - count
            if row is None:
                equipment.append({"item_id": int(iid), "count": remaining})
            else:
                row["count"] = remaining
            State.player.dirty = True
        else:
            _require(State.player.spend_item(kind, iid, count), "sale debit refused")
    State.player.add_currency("gil", price)
    print(f"item: sold {node['8X7LwE3r']} for {price} gil", flush=True)
    return _reply(spec)


@_action
def item_buy(spec, req):
    n = _node(req, "2aciVI9Y") or {}
    town = str(_int(n.get("Gh92V3Tx"), 1))
    stores = {str(r["Z20mNDvL"]) for r in _rows("F_TOWN_STORE_MST")
              if str(r["Gh92V3Tx"]) == town and str(r["kaG4xf3I"]) == "1"}
    products = {(int(r["YWF08vZS"]), str(r["6uIYE15X"]))
                for r in _rows("F_STORE_ITEM_MST") if str(r["Z20mNDvL"]) in stores}
    selected = _triples(n.get("j9NS0H15"))
    _require(0 < len(selected) <= 20, "empty/oversize purchase")
    total, books = 0, set()
    for row in selected:
        kind, iid = row["kind"], str(row["id"])
        _require((kind, iid) in products, "product is not sold in this town")
        _require(kind in (20, 21, 22, 60), "unsupported town-shop product")
        product = _product(kind, iid)
        if kind == 60:
            _require(row['count'] == 1 and iid not in books, "duplicate recipe book purchase")
            _require(not _feature('craft').get('books', {}).get(iid)
                     and State.player.item_count(60, iid) == 0, "recipe book is already owned")
            books.add(iid)
        # GameUtils::getItemBuyGil selects RecipeBookMst's gil member for kind 60.
        price_key = '7UR4J2SE' if kind == 60 else 'E61qF5Lp'
        total += _int(product.get(price_key)) * row["count"]
    _require(_int(n.get("U1uaXph4")) == total, "client gil preview does not match master price")
    _rewards(selected)
    _pay(gil=total)
    _grant(selected)
    return _reply(spec)


@_action
def strongbox_open(spec, req):
    n = _node(req, "3m6ToI0L") or {}
    store = str(_int(n.get("Z20mNDvL"), 1))
    _require(store in _table("F_TOWN_STORE_MST", "Z20mNDvL"), "unknown town store")
    boxes = _table("F_STRONGBOX_MST", "IXxi7Z8A")
    opened = deepcopy(_feature("strongbox"))
    pending, costs, rewards = [], [], []
    for bid in _ids(n.get("7NXY1JnT")):
        row = boxes.get(bid)
        _require(row is not None, "unknown strongbox")
        positions = [switch_position(row[t]) for t in ("dIPkNn61", "8aVAUgN5")]
        _require(all(positions), "strongbox switch mapping missing")
        if bid in opened or positions[0][1] in State.player.switches.get(positions[0][0], set()):
            continue
        costs.extend(_triples(row.get("wEofF38K")))
        rewards.extend(_triples(row.get("XPd8xR29"), rated=True))
        pending.append((bid, positions))
    _rewards(rewards)
    _pay(costs)
    _grant(rewards)
    for bid, positions in pending:
        for stype, bit in positions:
            State.player.grant_switch(stype, bit)
        opened[bid] = {"store": store, "switches": [list(p) for p in positions]}
    if pending:
        _store("strongbox", opened)
    return _switches(_reply(spec))


@_action
def exchange_shop(spec, req):
    n = _node(req, "V5W9ZAPx") or {}
    row = _table("F_EXCHANGE_SHOP_ITEM_MST", "wpM08VZ7").get(str(n.get("wpM08VZ7")))
    _require(row and row.get("4ubeU0nI") == "2", "unsupported exchange category/product")
    rewards = [{"kind": 20, "id": _int(row["6uIYE15X"], 1),
                "count": _int(row["Qy5EvcK1"], 1)}]
    _rewards(rewards)
    _require(State.player.spend_lapis(_int(row["8f7mxN3j"], 1)), "insufficient lapis")
    _grant(rewards)
    return _reply(spec)


@_action
def shop_exchange_list(spec, req):
    out = _reply(spec)
    out["E4r63ukD"] = list(_service_master('trust_exchange').values())
    out["ibt8aCI7"] = [{"d9gKeu0T": str(i), "0zBQbX4N": str(count)}
                        for i, count in _feature("exchange").get("counts", {}).items()]
    return out


@lru_cache(maxsize=None)
def _service_master(name):
    """Recovered service tables, which are not part of the static client masters."""
    keys = {'trust_exchange': 'd9gKeu0T', 'gifts': 'Utx8P1Qo'}
    path = Path(__file__).with_name('content') / (name + '.json')
    rows = json.loads(path.read_text(encoding='utf8'))['rows']
    return {str(row[keys[name]]): row for row in rows}


@_action
def shop_exchange_item(spec, req):
    node = _node(req, 'R0bWsV9y') or {}
    iid = str(node.get('d9gKeu0T', ''))
    product = _service_master('trust_exchange').get(iid)
    _require(product is not None, 'unknown Trust Coin product')
    quantity = _int(node.get('Qy5EvcK1'), 1)
    state = deepcopy(_feature('exchange'))
    counts = state.setdefault('counts', {})
    bought = int(counts.get(iid, 0))
    limit = int(product.get('Hp54A9JM', -1))
    _require(limit >= -1 and (limit == -1 or bought + quantity <= limit), 'Trust Coin stock exhausted')
    rewards = []
    for entry in product['7iJpH5zZ'].split(','):
        fields = entry.split(':')
        _require(len(fields) in (3, 4, 5) and (len(fields) < 4 or fields[3] == '100'),
                 'invalid Trust Coin reward')
        reward = _triples(':'.join(fields[:3]))[0]
        if len(fields) == 5:
            _require(reward['kind'] == 10, 'unexpected reward level')
            from player_state import max_level
            reward['level'] = _int(fields[4], 1)
            _require(reward['level'] <= max_level(reward['id']), 'reward level exceeds unit maximum')
        rewards.append(reward)
    for reward in rewards:
        reward['count'] *= quantity
    _rewards(rewards)
    _pay([{'kind': 23, 'id': 300, 'count': _int(product['Yc8Mm6y7'], 1) * quantity}])
    _grant(rewards)
    counts[iid] = bought + quantity
    _store('exchange', state)
    return shop_exchange_list(spec, {})


def deployed_unit_ids(player):
    party = player.data.get('party', {})
    deployed = {str(m.get('instance_id')) for mode in (party, *party.get('special', {}).values())
                for deck in mode.get('decks', []) for m in deck.get('members', [])}
    # Other offline systems retain their own instance references.
    for feature in ('expedition', 'companions', 'arena', 'dark_visions'):
        value = player.data.get('exvius_' + feature, {})
        def collect(obj):
            if isinstance(obj, dict):
                for key, child in obj.items():
                    if key in ('instance_id', 'user_unit_id', 'og2GHy49'):
                        deployed.add(str(child))
                    else:
                        collect(child)
            elif isinstance(obj, list):
                for child in obj:
                    collect(child)
        collect(value)
    return deployed


@_action
def shop_exchange_unit(spec, req):
    from player_state import unit_mst
    node = _node(req, 'gGCM0Q3h') or {}
    ids = _ids(node.get('og2GHy49'))
    player = State.player
    deployed = deployed_unit_ids(player)
    rates = {int(r['w84ixWg3']): _int(r['m7PJto98'], 1)
             for r in _rows('F_UNIT_TRANSLATE_RATE_MST') if str(r['5Fix0IX9']) == '1'}
    coins = 0
    for iid in ids:
        unit = _unit(iid)
        master = unit_mst(unit['master_id']) or {}
        _require(not int(master.get('JPW8Vs40') or 0) and master.get('Q1RJvK7r') == '1',
                 'unit is not eligible for Trust Coin conversion')
        _require(not int(unit.get('favourite') or 0) and iid not in deployed,
                 'unit is locked or assigned to a party')
        trust, _ = player._unit_trust_info(unit, 0)
        points = (list(unit.get('affinity_points') or []) + [''])[0]
        _require(trust and str(points).isdigit() and int(points) >= trust[3] > 0,
                 'Trust Coin conversion requires full trust mastery')
        root = unit_mst(master.get('woghJa61')) or master
        rarity = int(root.get('9fW0TePj') or 0)
        _require(rarity in rates, 'missing Trust Coin rarity rate')
        coins += rates[rarity]
    _require(len(player.data['roster']) > len(ids), 'cannot convert the entire roster')
    _require(len(player.drop_units(ids)) == len(ids), 'unit conversion was incomplete')
    player.grant_item(23, 300, coins)
    return _reply(spec)


@_action
def variable_store_check(spec, req):
    # GL9 EventStoreTopScene matches the base merchant, then opens za2xsDj5.
    # CommonUtils::convertToTime parses calendar dates (UTC), not Unix timestamps.
    out = _reply(spec)
    out["3VS1Bhmf"] = store_schedules()
    return out


# --- What King Mog, the Mog Minister and the summon-screen exchanges open (operator's report, 2026-11-10) ----
# The client sends VariableStoreCheckRequest when King Mog's or the Minister's counter, the summon-coin exchange
# list or the Vortex opens, and shows, per base store, the in-period row with the lowest priority
# (VariableStoreScheduleInfoList::getCurrentStoreInfo 0x1db5f14); with none, the counter's own empty base store.
# On Global both counters only ever ran the exchange of an event (wiki "Farplane", Item Exchange: King Mog and
# Mog Minister, "Event Examples / Currency / Claim Period"). The Minister's Auracite stock (900105) was
# Orbonne Monastery Vaults' exchange (wiki "Auracite Shard"), and the Star Quartz unit exchanges (7000456-58)
# came to the Shop's permanent exchanges on 2023-01-05 (Global news 2023-01-03 "Introducing Star Quartz
# Exchange Shops! Starting 1/5"). So, following the replay:
#   * a counter opens the exchange of an event in this week's Vortex whose store is that counter's
#     (F_TOWN_STORE_MST name), until the week ends; with several, the one whose run is latest;
#   * else the exchange of a currency the player holds whose event has already run, latest run first
#     (Global's claim period after an event; the Shop's exchange list applies the same rule);
#   * the summon-screen exchanges (archived_store_schedules) open while a quest that pays their currency is
#     served this week, or while the player holds it; the Star Quartz ones from replay date 2023-01-05.
# EXVIUS_EXCHANGE_SCHEDULE=0 serves the old fixed schedule (Star Quartz, Auracite, every exchange always open).
COUNTERS = {'\u30e2\u30fc\u30b0\u30ea\u738b': ('900104', 'king'),            # King Mog
            '\u30e2\u30fc\u30b0\u30ea\u5927\u81e3': ('900122', 'minister')}  # Mog Minister
STAR_QUARTZ_STORES = ('7000456', '7000457', '7000458')
STAR_QUARTZ_FROM = '2023-01-05'
ALWAYS = ('2020-01-01 00:00:00', '2099-12-31 23:59:59')


def exchange_schedule_enabled() -> bool:
    import os
    return str(os.environ.get('EXVIUS_EXCHANGE_SCHEDULE', '1')).strip().lower() not in ('0', 'off', 'false', 'no')


@lru_cache(maxsize=1)
def _event_exchanges():
    path = Path(__file__).with_name('content').joinpath('event_exchanges.json')
    return json.loads(path.read_text(encoding='utf-8')) if path.exists() else {'exchanges': []}


@lru_cache(maxsize=1)
def _area_runs():
    import event_archive
    return {str(ev['area']): sorted(str(r) for r in ev.get('runs') or [] if r)
            for ev in event_archive.document()['events']}


def _replay_week(now=None):
    """(open area -> its run that opened it, history date reached (exclusive, ISO), week start, week end,
    the quests served this week)."""
    from datetime import datetime, timezone
    import gacha_rotation
    _, start, end = gacha_rotation.week(now)
    opened, history, served = {}, (now or datetime.now(timezone.utc)).date().isoformat(), set()
    try:
        import event_archive
        import replay
        rows = event_archive.weekly_events(now=now)
        opened = {str(row['area']): str(row.get('release') or '') for row in rows}
        served = {str(m) for row in rows for m in row.get('missions') or []}
        if replay.enabled():
            history = replay.window(now)['to'].isoformat()
    except Exception as exc:  # noqa: BLE001 -- without the rotation no event is open; held currency still counts
        _note(f'exchange schedule: weekly events unavailable ({exc!r})')
    return opened, history, start, end, served


def _utc(moment):
    from datetime import timezone
    return moment.astimezone(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')


def _held() -> dict:
    player = State.player
    if player is None:
        return {}
    return {str(it.get('item_id')): int(it.get('count', 0)) for it in player._items()
            if str(it.get('item_type')) == '20' and int(it.get('count', 0) or 0) > 0}


def _counter_texts(who, currency):
    if who == 'king':
        return (f'Trade {currency} for something rare, kupo?', f'Come back with more {currency}, kupo!')
    return (f'I would gladly exchange items from my collection for {currency}, kupo!',
            f'Come back and see me once you have collected some {currency}, kupo!')


def counter_schedules(now=None, week=None):
    """King Mog's and the Mog Minister's row: this week's event exchange, else a held currency's."""
    opened, history, start, end = (week or _replay_week(now))[:4]
    held = _held()
    towns = _table('F_TOWN_STORE_MST', 'Z20mNDvL')
    best = {}
    for ex in _event_exchanges()['exchanges']:
        town = towns.get(str(ex['store'])) or {}
        if town.get('kaG4xf3I') != '5' or town.get('G4L0YIB2') not in COUNTERS:
            continue
        base, who = COUNTERS[town['G4L0YIB2']]
        live = [opened[a] for a in ex['event_areas'] if a in opened]
        if live:
            rank, period = (1, max(live)), (_utc(start), _utc(end))
        elif held.get(str(ex['currency'])):
            ran = [r for a in ex['event_areas'] for r in _area_runs().get(str(a), []) if r < history]
            if not ran:
                continue
            rank, period = (0, max(ran)), ALWAYS
        else:
            continue
        if base in best and best[base][0] >= rank:
            continue
        welcome, farewell = _counter_texts(who, ex.get('currency_name') or 'event items')
        best[base] = (rank, {'Z20mNDvL': base, 'za2xsDj5': str(ex['store']), 'w7VR6ypY': '0',
                             'VjJQ51uG': period[0], 'm8ivD4NX': period[1], 'suR36Jpm': '20:' + str(ex['currency']),
                             '89YmCAzo': welcome, '0euar5mZ': farewell})
    return [row for _, row in best.values()]


def summon_screen_schedules(now=None, week=None):
    """The summon-screen exchanges open now: their event's week, a held currency, Star Quartz from 2023-01-05."""
    opened, history, start, end, served = week or _replay_week(now)
    held = _held()
    # The quests that pay the currency, when one of them is served this week (a later run's quests are held
    # back, event_archive.only_existing_quests); else the events paying it.
    paid = {str(e['store']): e for e in _event_exchanges().get('summon_screen', [])}
    out = []
    for row in archived_store_schedules():
        store, currency = row['za2xsDj5'], row['suR36Jpm'].split(':', 1)[1]
        if store in STAR_QUARTZ_STORES:
            period = ALWAYS if history > STAR_QUARTZ_FROM else None
        elif store in paid and (served.intersection(paid[store].get('missions') or []) if 'missions' in paid[store]
                                else any(a in opened for a in paid[store]['event_areas'])):
            period = (_utc(start), _utc(end))
        else:
            period = ALWAYS if held.get(currency) else None
        if period:
            out.append(dict(row, VjJQ51uG=period[0], m8ivD4NX=period[1]))
    return out


def legacy_store_schedules():
    """The fixed schedule served before 2026-11-10 (EXVIUS_EXCHANGE_SCHEDULE=0)."""
    stores = _table("F_TOWN_STORE_MST", "Z20mNDvL")
    rows = [
        {"Z20mNDvL": base, "za2xsDj5": iid, "w7VR6ypY": "0",
         "VjJQ51uG": ALWAYS[0], "m8ivD4NX": ALWAYS[1],
         "suR36Jpm": "20:" + currency, "89YmCAzo": welcome, "0euar5mZ": farewell}
        for base, iid, currency, welcome, farewell in (
            ("900104", "7000458", "106200100", "Trade star quartz for an item?",
             "Come back and see me if you find any rare goodies, kupo."),
            ("900122", "900105", "106300100",
             "I would gladly exchange items from my collection for auracite shards, kupo!",
             "Come back and see me once you have collected some auracite shards, kupo!"))
        if stores.get(iid, {}).get("kaG4xf3I") == "5"]
    return rows + [dict(row) for row in archived_store_schedules()]


def captain_schedules():
    """A row for each store in the Moogle Guard Captain's menu (captain_menu.py), carrying its own currency.

    The store screen takes its currency (the header's icon and the one beside every price) from the opened
    store's schedule row, `suR36Jpm`: `EventStoreTopScene::updateEvent` (0x229e350) passes the row's currency to
    `StoreSceneFactory::createStoreScene`, and 0/0 when the store has none, which drew a Star Quartz-like crystal
    on the Captain's stores (operator, 2026-11-10: The Hanging Edge, priced in Trochoid Gear). King Mog's and the
    Minister's stores already had theirs through `counter_schedules`. Same list as the menu the phone has this
    session (`captain_menu.state`); empty greetings, so each store keeps its own."""
    try:
        import captain_menu
        st = captain_menu.state()
    except Exception:  # noqa: BLE001
        return []
    if st.get('sig', 'off') == 'off':
        return []
    return [{'Z20mNDvL': str(e['store']), 'za2xsDj5': str(e['store']), 'w7VR6ypY': '0',
             'VjJQ51uG': ALWAYS[0], 'm8ivD4NX': ALWAYS[1], 'suR36Jpm': '20:' + str(e['currency']),
             '89YmCAzo': '', '0euar5mZ': ''} for e in st.get('entries') or []]


def store_schedules(now=None):
    """Every store schedule row for VariableStoreCheck and the login reply."""
    if not exchange_schedule_enabled():
        rows = legacy_store_schedules()
    else:
        week = _replay_week(now)
        rows = counter_schedules(week=week) + summon_screen_schedules(week=week)
    have = {row['Z20mNDvL'] for row in rows}
    return rows + [row for row in captain_schedules() if row['Z20mNDvL'] not in have]


@lru_cache(maxsize=1)
def archived_store_schedules():
    """Open recovered exchange stock through the native store schedule format."""
    products = {}
    medals = _table('F_MEDAL_EXCHANGE_MST', 'S21FT3L8')
    for row in _rows('F_STORE_ITEM_MST'):
        if str(row.get('YWF08vZS')) == '50':
            product = medals.get(str(row.get('6uIYE15X')))
            if product:
                products.setdefault(str(row['Z20mNDvL']), product)
    result, seen = [], set()
    for row in _rows('F_GACHA_STORE_MST'):
        iid = str(row['Z20mNDvL'])
        product = products.get(iid)
        if not product or iid in seen:
            continue
        seen.add(iid)
        result.append({'Z20mNDvL': iid, 'za2xsDj5': iid, 'w7VR6ypY': '0',
                       'VjJQ51uG': '2020-01-01 00:00:00', 'm8ivD4NX': '2099-12-31 23:59:59',
                       'suR36Jpm': '20:' + str(product['ak2dhKm3']),
                       '89YmCAzo': '', '0euar5mZ': ''})
    return result


@_action
def medal_exchange(spec, req):
    n = _node(req, "2d6RAkvh") or {}
    store = str(_int(n.get("Z20mNDvL"), 1))
    _require(_table("F_TOWN_STORE_MST", "Z20mNDvL").get(store, {}).get("kaG4xf3I") == "5",
             "unknown medal merchant")
    available = {str(r["6uIYE15X"]) for r in _rows("F_STORE_ITEM_MST")
                 if r.get("Z20mNDvL") == store and r.get("YWF08vZS") == "50"}
    masters = _table("F_MEDAL_EXCHANGE_MST", "S21FT3L8")
    saved = deepcopy(_feature("medal_exchange"))
    counts = saved.setdefault("counts", {})
    # One stock with the Shop's exchange list (operator, 2026-11-10): what it sold of a row counts here too.
    from exvius_shop_catalogue import shared_medal_counts
    shared = shared_medal_counts()
    costs, rewards, seen = [], [], set()
    for entry in str(n.get("L2gHC5ta") or "").split(","):
        pair = entry.split(":")
        _require(len(pair) == 2, "invalid medal purchase")
        iid, quantity = str(_int(pair[0], 1)), _int(pair[1], 1)
        _require(iid not in seen and iid in available, "duplicate or wrong-merchant product")
        seen.add(iid)
        row = masters.get(iid)
        _require(row is not None, "missing medal product")
        mode = _int(row["kR4n5DxP"], 1)
        _require(mode in (1, 2), "unknown medal limit type")
        # GL9's parser at 0x1ca84d4: type 1 uses x0NDnEC9, type 2
        # becomes StoreExchangeItem::EXCHANGE_CNT_UNLIMITED (-1).
        bought = _int(shared.get(iid, 0))
        if mode == 1:
            _require(bought + quantity <= _int(row["x0NDnEC9"]), "medal purchase limit exceeded")
        currency = _int(row["ak2dhKm3"], 1)
        _product(20, currency)
        costs.append({"kind": 20, "id": currency, "count": _int(row["Qy5EvcK1"]) * quantity})
        from exvius_rewards import parse
        for reward in parse(row.get('7iJpH5zZ'), exchange=True):
            reward['count'] *= quantity
            rewards.append(reward)
        counts[iid] = _int(counts.get(iid, 0)) + quantity
    _require(seen and rewards, "empty medal purchase")
    _rewards(rewards)
    player = State.player
    before, dirty = deepcopy(player.data), player.dirty
    try:
        _pay(costs)
        _grant(rewards)
        _store("medal_exchange", saved)
    except Exception:
        player.data, player.dirty = before, dirty
        raise
    return _reply(spec)


def _awakening_cost(node, master):
    materials = _triples(master.get('KCk8u0am'))
    _require(_triples(node.get('KCk8u0am')) == materials, 'awakening materials do not match master')
    # Offline seasons have no active class-up discount campaign. The ordinary
    # master cost is authoritative, rather than a client-supplied debit.
    _require(str(node.get('Knra4I19', 0)) == '0', 'awakening discount campaign is not active')
    return materials, _int(master.get('7UR4J2SE', 0))


POINT_TOKENS = ('XeRVw3s2', 'jWS57HG3', 'LD4UJaf0', 'ui34MYgo', '5sNq90o6',
                '0xgsDY9E', 'VSL4Wj9z', 'y7Z5AmhC', 'h5s68EtJ', 'eu2DXK4I',
                '8RUQtk4i', '8cj19yhb', 'rjK5oB1H', '16NCtrGw')
POINT_TYPES = ('EXP', 'DOPING_LB', 'DOPING_HP', 'DOPING_MP', 'DOPING_ATK', 'DOPING_DEF',
               'DOPING_INT', 'DOPING_MND', 'MAX_LIMIT_EX_HP', 'MAX_LIMIT_EX_MP',
               'MAX_LIMIT_EX_ATK', 'MAX_LIMIT_EX_DEF', 'MAX_LIMIT_EX_INT', 'MAX_LIMIT_EX_MND')


def series_point_award(iid):
    row = _table('F_UNIT_SERIES_POWER_UP_POINT_MST', 'RvN2W9Qx').get(str(iid), {})
    kind = row.get('K5LEG0Da')
    if kind not in POINT_TYPES or not str(row.get('Yc8Mm6y7', '')).isdigit():
        return None
    return str(row['woghJa61']), POINT_TOKENS[POINT_TYPES.index(kind)], int(row['Yc8Mm6y7'])


def convert_material_units(player, ids=None):
    from player_state import unit_mix_exp, unit_mst

    if player.mode == 'frozen':
        return set()
    deployed = deployed_unit_ids(player)
    converted = set()
    points = Counter()
    gil = 0
    for unit in player.data['roster']:
        iid = str(unit['instance_id'])
        if (ids is not None and iid not in ids) or iid in deployed or unit.get('favourite'):
            continue
        master = unit_mst(unit['master_id']) or {}
        roles = set(master.get('27GkYdEu', '').split(','))
        if ids is not None and master.get('2odVXyT8') == '2' and '10' in roles:
            value = int(master.get('u18nfD7p') or 0)
            if value > 0:
                gil += value
                converted.add(iid)
            continue
        if master.get('2odVXyT8') != '1':
            continue
        credit = {}
        if '9' in roles:
            credit[POINT_TOKENS[0]] = unit_mix_exp(unit)
        elif ids is not None and roles.intersection(('12', '13')):
            values = [int(value) for value in master.get('Y2X8d5R7', '').split(',') if value.isdigit()]
            start = 8 if '13' in roles else 2
            credit.update(zip(POINT_TOKENS[start:start + 6], values))
            if '12' in roles:
                credit[POINT_TOKENS[1]] = int(master.get('1Rf2VDoI') or 0)
        if any(credit.values()):
            points.update(credit)
            converted.add(iid)
    if not converted:
        return set()
    if points:
        bank = player.data.setdefault('exvius_unit_points', {}).setdefault('banks', {}).setdefault('0', {})
        for token, amount in points.items():
            if amount:
                bank[token] = int(bank.get(token, 0)) + amount
    if gil:
        player.add_currency('gil', gil)
    player.drop_units(converted)
    _note(f'unit-exchange: credited points or gil for {len(converted)} material(s)')
    return converted


def _point_rows():
    banks = {'0': {}, **_feature('unit_points').get('banks', {})}
    return [dict({'woghJa61': str(series)}, **{token: str(bank.get(token, 0))
                 for token in POINT_TOKENS})
            for series, bank in banks.items()]


@_action
def unit_use_point(spec, req):
    from player_state import unit_mst, STAT_TOKENS, limit_burst, max_level_exp
    rows = req.get('5xfBN93i') or []
    _require(isinstance(rows, list) and 0 < len(rows) <= 2, 'invalid point-bank selection')
    state = deepcopy(_feature('unit_points'))
    banks = state.setdefault('banks', {})
    seen, target, total = set(), None, [0] * len(POINT_TOKENS)
    for node in rows:
        _require(isinstance(node, dict), 'invalid point-bank row')
        unit = _unit(str(node.get('og2GHy49', '')))
        iid = str(unit['instance_id'])
        _require(target in (None, iid), 'point rows must target the same unit')
        target = iid
        series = str(_int(node.get('woghJa61', 0)))
        master = unit_mst(unit['master_id']) or {}
        _require(series in ('0', str(master.get('woghJa61'))), 'wrong unit-series bank')
        _require(series not in seen, 'duplicate point bank')
        seen.add(series)
        bank = banks.setdefault(series, {})
        for index, token in enumerate(POINT_TOKENS):
            amount = _int(node.get(token, 0))
            _require(index != 0 or series == '0' or amount == 0, 'series bank has no unit EXP')
            balance = _int(bank.get(token, 0))
            _require(amount <= balance, 'insufficient enhancement points')
            bank[token] = balance - amount
            total[index] += amount
    _require(any(total), 'empty enhancement')
    unit = _unit(target)
    master = unit_mst(unit['master_id']) or {}
    cap = max_level_exp(unit['master_id'])
    _require(not total[0] or cap is not None and int(unit.get('total_exp', 0)) + total[0] <= cap,
             'unit EXP exceeds maximum level')
    pots = list(unit.get('stat_pots', [0] * 6))
    doors = list(unit.get('stat_doors', [0] * 6))
    for index, token in enumerate(STAT_TOKENS):
        descriptor = list(map(int, master[token].split(',')))
        pot_cap, door_cap = (descriptor + [0, 0, 0, 0])[2:4]
        doors[index] += total[index + 8]
        pots[index] += total[index + 2]
        _require(doors[index] <= door_cap and pots[index] <= pot_cap + doors[index],
                 'stat enhancement exceeds unit cap')
    if total[1]:
        lb = limit_burst(unit['master_id'])
        _require(lb is not None, 'unit has no limit burst')
        levels = sorted((int(r['7wV3QZ80']), int(r['T3Zcf40Q']))
                        for r in _rows('F_LIMITBURST_LV_MST')
                        if r['PR2HIc71'] == lb['PR2HIc71'])
        _require(levels, 'limit burst level table missing')
        level = int(unit.get('lb_level') or 1)
        exp = int(unit.get('lb_exp') or 0) + total[1]
        steps = dict(levels)
        maximum = min(levels[-1][0], int(master.get('ENwn42DV') or 1))
        while level < maximum and level + 1 in steps and exp >= steps[level + 1]:
            exp -= steps[level + 1]
            level += 1
        _require(level < maximum or exp == 0, 'limit burst EXP exceeds cap')
        unit['lb_level'], unit['lb_exp'] = level, exp
    if total[0]:
        State.player.add_unit_exp(target, total[0])
    State.player.record_archive({'TOTAL_UNIT_MIX': 1})
    unit['stat_pots'], unit['stat_doors'] = pots, doors
    _store('unit_points', state)
    out = _reply(spec)
    out['z36FApms'] = _point_rows()
    return out


def _awaken_unit(spec, req, plus):
    from player_state import unit_mst, max_level, limit_burst
    node = _node(req, '6U5w20zk') or {}
    unit = _unit(str(node.get('og2GHy49', '')))
    old = unit_mst(unit['master_id']) or {}
    step = _table('F_UNIT_CLASS_UP_MST', '3HriTp6B').get(str(unit['master_id']))
    _require(step is not None, 'unit has no further awakening')
    target = unit_mst(step['t74crqAL'])
    _require(target and int(target.get('JPW8Vs40') or 0) > 0, 'destination is not Neo Vision')
    _require(bool(int(old.get('JPW8Vs40') or 0)) == plus, 'wrong awakening type')
    if not plus:
        # No level or Super Trust requirement: Global's Version 7.0.0 (March 2022) removed both ("NV awaken units
        # without reaching 100% super trust mastery", and awakening below max level); the phone is that build.
        _require(int(old.get('9fW0TePj') or 0) == 7, 'NV awakening requires a 7-star unit')
    costs, gil = _awakening_cost(node, step)
    _pay(costs, gil)
    level = int(unit['level'])
    unit['master_id'] = str(step['t74crqAL'])
    State.player.set_unit_level(unit['instance_id'], level)
    if not plus:
        unit['nv_ex_level'] = 0
    lb = limit_burst(unit['master_id'])
    if lb:
        unit['lb_level'] = min(int(unit.get('lb_level') or 1), int((unit_mst(unit['master_id']) or {}).get('ENwn42DV') or 1))
    source_id = str(unit['instance_id'])
    unit = State.player.renew_unit_instance(source_id)
    State.player.record_archive({'TOTAL_UNIT_CLASS_UP': 1})
    State.player.dirty = True
    out = _reply(spec)
    # Both response tags use UnitClassUpResponse. Native class-up removes
    # the source ID, so its destination must have a distinct instance ID.
    out['6U5w20zk'] = [{'og2GHy49': source_id, '5u7VYNEX': str(unit['instance_id']),
                       'KCk8u0am': step.get('KCk8u0am', ''), 'WbGYcN17': '',
                       '02CI3bpE': '', 'p9Xj4Anc': '0'}]
    return out


@_action
def unit_nv_class_up(spec, req):
    return _awaken_unit(spec, req, False)


@_action
def unit_nvp_class_up(spec, req):
    return _awaken_unit(spec, req, True)


@_action
def unit_ex_class_up(spec, req):
    from player_state import unit_mst, owned_unit_stats
    from ffbe_battle import _lv_half
    node = _node(req, '14vWb7kX') or {}
    unit = _unit(str(node.get('og2GHy49', '')))
    master = unit_mst(unit['master_id']) or {}
    group = str(master.get('JPW8Vs40') or '0')
    level = int(unit.get('nv_ex_level') or 0) + 1
    _require(group != '0' and level <= 3, 'unit is not eligible for another EX awakening')
    step = next((r for r in _rows('F_NV_EX_CLASS_UP_MST')
                 if r['JPW8Vs40'] == group and int(r['f8vk4JrD']) == level), None)
    _require(step is not None, 'EX awakening master is missing')
    costs, gil = _awakening_cost(node, step)
    # Reward tuples also carry an initial level and a unit-specific trust ID.
    rewards = []
    for entry in str(step.get('dX6cor8j') or '').split(','):
        if not entry:
            continue
        fields = [field.strip() for field in entry.split(':')]
        _require(len(fields) in (3, 4, 5, 9) and (len(fields) < 4 or fields[3] == '100'),
                 'invalid EX awakening reward')
        reward = _triples(':'.join(fields[:3]))[0]
        if len(fields) >= 5:
            reward['level'] = _int(fields[4], 1)
        if len(fields) == 9:
            _require(fields[5:8] == ['0', '0', '0'] and reward['kind'] == 10,
                     'invalid EX trust reward metadata')
            target = _int(fields[8], 1)
            channel = 1 if target >= 1000000000 else 0
            target_master = unit_mst(target - channel * 1000000000)
            # A few Global units retain the JP EX series and reward target,
            # but use a different Global UnitMst ID. Their owned master has
            # the corresponding Global trust item.
            descriptor = (target_master or master).get(('9mu4boy7', 'C74EmZ1I')[channel])
            _require(descriptor and str(reward['id']).startswith(('904', '906')),
                     'missing EX trust reward target')
            reward['affinity_info'] = ['', '']
            reward['affinity_points'] = ['', '']
            reward['affinity_info'][channel] = descriptor
            reward['affinity_points'][channel] = descriptor.split(':')[3]
        rewards.append(reward)
    _rewards(rewards)
    before = _lv_half(unit['level'], unit['exp'], owned_unit_stats(unit),
                      unit.get('lb_level', 1), unit.get('lb_exp', 0))
    _pay(costs, gil)
    unit['nv_ex_level'] = level
    State.player.dirty = True
    _grant(rewards)
    after = _lv_half(unit['level'], unit['exp'], owned_unit_stats(unit),
                     unit.get('lb_level', 1), unit.get('lb_exp', 0))
    out = _reply(spec)
    out['14vWb7kX'] = [{'og2GHy49': str(unit['instance_id']),
                        'KCk8u0am': step.get('KCk8u0am', ''), 'Knra4I19': '0',
                        'Qic38SuC': str(unit['instance_id']) + '@' + before + '_' + after}]
    return out


@_action
def craft_add(spec, req):
    # The original caller is a map-script unlock, with no price parameter.
    node = _node(req, '0eDvu2N3') or {}
    _require(_int(node.get('KosY4a18'), 1) == 1, 'craft operation mismatch')
    categories = _ids(node.get('gak9Gb3N'))
    _require(set(categories) <= {'20', '21', '22'}, 'unknown crafting category')
    state = deepcopy(_feature('craft'))
    slots = state.setdefault('slots', {})
    changed = False
    for category in categories:
        # Legacy timed-crafting state supports four independent jobs per
        # category. Offline unlocks expose all four; modern CraftExe batches
        # remain independent of these legacy job slots.
        for number in range(1, 5):
            key = category + ':' + str(number)
            if key not in slots:
                slots[key] = {'recipe': 0, 'start': 0, 'end': 0, 'join_reason': 0}
                changed = True
    if changed:
        _store('craft', state)
    out = _reply(spec)
    out['gy84FjCA'] = [_slot_row({'gak9Gb3N': category, '6ukvMSg9': number}, slot)
                       for key, slot in slots.items() for category, number in [key.split(':')]]
    return out


@_action
def trophy_reward(spec, req):
    n = _node(req, "y3ubhqI0") or {}
    masters = _table("F_TROPHY_MST", "t86L4JR3")
    claims = _ids(n["m81FLCIz"]) if n.get("m81FLCIz") else []
    rows = []
    for iid in claims:
        row = masters.get(iid)
        _require(row is not None, "unknown trophy")
        _require(State.player.archive_value(row["NYb0Cri6"]) >= _int(row["nw2FXyo8"]),
                 "trophy progression below threshold")
        rows.append(row)
    tier = _int(n.get("15Y6b8Kp", 0))
    meter = _table("F_TROPHY_REWARD_MST", "15Y6b8Kp").get(str(tier)) if tier else None
    _require(not tier or meter, 'unknown meter tier')
    _require(rows or meter, "unknown meter tier" if tier else "no trophy claim")
    rewards, pending = [], []
    for row in rows:
        pos = switch_position(row["dIPkNn61"])
        _require(pos is not None, "claim switch not mapped")
        if pos[1] not in State.player.switches.get(pos[0], set()):
            rewards.extend(_triples(row["dX6cor8j"]))
            pending.append(pos)
    if meter:
        # GL9 TrophyManager::loadFiles 0x2008094 counts each eligible,
        # claimed trophy once. Grades are not weighted and points are not spent.
        maximum = _int(_define('TROPHY_MAX_GRADE'))
        count = 0
        for row in masters.values():
            pos = switch_position(row['dIPkNn61'])
            claimed = pos and (pos in pending or pos[1] in State.player.switches.get(pos[0], set()))
            if (claimed and _int(row.get('5cfi4jqE', 0)) and _int(row['XYG0uFv5']) <= maximum
                    and State.player.archive_value(row['NYb0Cri6']) >= _int(row['nw2FXyo8'])):
                count += 1
        _require(count >= _int(meter['i2Pq9NtI']), 'trophy meter below threshold')
        pos = switch_position(meter['dIPkNn61'])
        _require(pos is not None, 'meter claim switch not mapped')
        if pos[1] not in State.player.switches.get(pos[0], set()):
            rewards.extend(_triples(meter['dX6cor8j']))
            pending.append(pos)
    _rewards(rewards)
    _grant(rewards)
    for stype, bit in pending:
        State.player.grant_switch(stype, bit)
    if pending:
        claimed = {str(r['dIPkNn61']) for r in rows + ([meter] if meter else [])}
        _store("trophy", {"claimed": sorted(set(_feature("trophy").get("claimed", [])) | claimed)})
    return _switches(_reply(spec))


@_action
def vision_card_display(spec, req):
    n = _node(req, "kwK4W0Si") or {}
    iid = str(n.get("gXb32xzQ", ""))
    cards = State.player.data.get("vision_cards", [])
    _require(iid == "0" or any(str(c.get("user_vc_id")) == iid for c in cards), "card is not owned")
    State.player.data["profile"]["decorate_home_vc_id"] = iid
    feature = deepcopy(_feature("vision_card"))
    feature["display"] = iid
    _store("vision_card", feature)
    return _reply(spec)


def _card_progress(card, master):
    cap = _int(master["aU3o2D4t"], 1)
    level = _int(card.get("level", 1), 1)
    _require(level <= cap, "invalid owned card level")
    pattern = {int(r["7wV3QZ80"]): _int(r["93fnYUJG"])
               for r in _rows("F_VISION_CARD_EXP_PATTERN_MST")
               if str(r["0W7g6YXS"]) == str(master["0W7g6YXS"])}
    _require(all(l in pattern and pattern[l] > 0 for l in range(2, cap + 1)),
             "card EXP pattern incomplete")
    threshold = sum(pattern[l] for l in range(2, level + 1))
    exp = _int(card.get("exp", _int(card.get("total_exp", threshold)) - threshold))
    total = _int(card.get("total_exp", threshold + exp))
    _require(total == threshold + exp and (exp == 0 if level == cap else exp < pattern[level + 1]),
             "card EXP fields inconsistent")
    return cap, level, exp, total, pattern


@_action
def vision_card_mix(spec, req):
    n = _node(req, "oh5yce1m") or {}
    iid = str(n.get("gXb32xzQ", ""))
    ids = _ids(n.get("iUeA3z71"))
    cards = {str(c.get("user_vc_id")): c for c in State.player.data.get("vision_cards", [])}
    _require(iid in cards and iid not in ids and all(i in cards for i in ids), "invalid fusion cards")
    # Equipped/home-display cards need a separate client unequip operation first.
    equipped = {str(u.get("vision_card", "")).split("-")[-1] for u in State.player.data["roster"]}
    equipped.add(str(State.player.data["profile"].get("decorate_home_vc_id")))
    _require(not equipped.intersection(ids), "material card is equipped/displayed")
    master = _table("F_VISION_CARD_MST", "5giCMUd2")
    base = cards[iid]
    b = master.get(str(base["vc_id"]))
    _require(b is not None, "unknown base card master")
    cap, level, before_exp, _, pattern = _card_progress(base, b)
    gain, gil = 0, 0
    rate = _int(_define("DIFF_VISION_CARD_SERIES_MIX_EXP_RATE"))
    for cid in ids:
        material = cards[cid]
        m = master.get(str(material["vc_id"]))
        _require(m is not None, "unknown material card master")
        _, m_level, _, m_total, _ = _card_progress(material, m)
        rarity = _int(m["9fW0TePj"])
        value = m_total + _int(m["N85uJT1d"]) + (
            CARD_RARITY_EXP[rarity] if rarity < len(CARD_RARITY_EXP) else 0)
        if m["efb6J8AZ"] != b["efb6J8AZ"] and m["2odVXyT8"] != "1":
            value = value * rate // 1000
        gain += value
        gil += 30 * (level + m_level)
    gil = (gil + 2) // 4 if level == cap else gil
    after_exp, after_level = before_exp + gain, level
    while after_level < cap and after_exp >= pattern[after_level + 1]:
        after_level += 1
        after_exp -= pattern[after_level]
    if after_level == cap:
        after_exp = 0
    _pay(gil=gil)
    base.update(level=after_level, exp=after_exp,
                total_exp=sum(pattern[l] for l in range(2, after_level + 1)) + after_exp)
    State.player.data["vision_cards"] = [c for key, c in cards.items() if key not in ids]
    feature = deepcopy(_feature("vision_card"))
    feature["last_mix"] = {"base": iid, "consumed": ids}
    _store("vision_card", feature)
    out = _reply(spec)
    # Mode 1 preserves material objects until the client's animation removes them.
    out.pop("2Xi0wuGA", None)
    out["4hPYneL3"] = [r for r in State.player.vision_card_rows() if r["gXb32xzQ"] == iid]
    out["oh5yce1m"] = [{"gXb32xzQ": iid, "iUeA3z71": ",".join(ids), "7UR4J2SE": str(gil),
                         "B6H34Mea": str(gain), "1dT7ha9H": str(AUTHORED_CARD_SUCCESS),
                         "Wpro0aE7": f"{before_exp}:{level}_{after_exp}:{after_level}"}]
    return out


@_action
def unit_sublimation(spec, req):
    n = _node(req, "x3tm7qUF") or {}
    iid = str(n.get("og2GHy49", ""))
    _unit(iid)
    state = deepcopy(_feature("sublimation"))
    slots = state.setdefault("slots", {})
    if not slots.get(iid):
        cost = _triples(_define("VISION_CARD_SACRIFICE_ITEM_ID"))
        _require(cost, "empty slot-unlock cost")
        _pay(cost)
        slots[iid] = True
        _store("sublimation", state)
    return _reply(spec)


@_action
def sublimation_skill(spec, req):
    n = _node(req, "NcI0GgU9") or {}
    iid = str(n.get("6uIYE15X", ""))
    unit = _unit(iid)
    recipes = _table("F_SUBLIMATION_RECIPE_MST", "SJ56uhz2")
    row = recipes.get(str(n.get("SJ56uhz2")))
    _require(row is not None, "unknown sublimation recipe")
    # procClassUp sends SkillMstBase::getSkillType(), not the recipe's
    # j1z0Nxo9 category. All shipped sublimation recipes target abilities,
    # whose request type is 2 (including passive abilities).
    _require(_int(n.get("yjY4GK3X"), 1) == 2, "skill type mismatch")
    if str(row['59kRbpKz']) != '0':
        acquired = State.player.data.get('exvius_exbonus', {}).get('units', {}).get(iid, {}).get('details', {})
        bonuses = _rows('F_UNIT_EX_BONUS_MST')
        _require(any(str(b['xm7c08IS']) == '8' and str(b['xHZj7Va5']) == str(row['SJ56uhz2'])
                     and int(acquired.get(str(b['L3Nx1Jpb']), 0)) > 0 for b in bonuses),
                 'the EX-bonus enhancement limit has not been unlocked')
    master = _table("F_UNIT_MST", "3HriTp6B")[str(unit["master_id"])]
    allowed = str(row["25oxcKwN"]).split(",")
    _require(str(unit["master_id"]) in allowed or str(master["woghJa61"]) in allowed,
             "unit is not allowed for this recipe")
    state = deepcopy(_feature("sublimation"))
    skills = state.setdefault("skills", {}).setdefault(iid, {})
    before, after = str(row["hxu12ZFS"]), str(row["Q1n9iYgz"])
    root = next((r for r, current in skills.items() if str(current) == before), before)
    if str(skills.get(root, "")) == after:
        return _reply(spec)
    predecessors = {str(r["Q1n9iYgz"]): str(r["hxu12ZFS"]) for r in recipes.values()}
    _require(root in skills or before not in predecessors, "previous skill tier has not been learned")
    _require(root not in skills or str(skills[root]) == before, "skill recipe is stale")
    tier, previous = 1, before
    while previous != root and tier < 5 and previous in predecessors:
        previous = predecessors[previous]
        tier += 1
    _pay(_triples(row["HS7V6Ww1"]), _int(row["7UR4J2SE"]))
    skills[root] = after
    _store("sublimation", state)
    from ffbe_player import score_quest_action
    if previous == root:
        score_quest_action('1', param=str(tier))
    out = _reply(spec)
    out["j0e1xIv9"] = [{"og2GHy49": iid, "1MH7Na23": root, "6bHxDEL0": after}]
    return out


@_action
def hidden_skill_upgrade(spec, req):
    n = _node(req, "gK8NR3Lt") or {}
    series = str(_int(n.get("woghJa61"), 1))
    hid = str(_int(n.get("uNQgv5QM"), 1))
    units = _table("F_UNIT_MST", "3HriTp6B")
    _require(any(str(units.get(str(u["master_id"]), {}).get("woghJa61")) == series
                 for u in State.player.data["roster"]), "unit series is not owned")
    allowed = {str(r["uNQgv5QM"]) for r in _rows("F_UNIT_SERIES_HIDDEN_SKILL_MST")
               if str(r["woghJa61"]) == series}
    table = _table("F_HIDDEN_SKILL_MST", "uNQgv5QM")
    _require(hid in allowed and hid in table, "hidden skill is not allowed for this series")
    state = deepcopy(_feature("hidden_skill"))
    learned = state.setdefault(series, [])
    previous = [k for k in allowed if k in table and str(table[k]["kjK5eW55"]) == hid]
    if hid not in learned:
        _require(not previous or any(p in learned for p in previous), "previous hidden tier not learned")
        successor = str(table[hid]["kjK5eW55"])
        seen = {hid}
        while successor in table and successor not in seen:
            _require(successor not in learned, "hidden skill tier is stale")
            seen.add(successor)
            successor = str(table[successor]["kjK5eW55"])
        currency = str(_define("SKILL_POINT_ITEM")).split(":")
        _require(len(currency) == 2, "invalid EP item define")
        cost = _int(table[hid]["3V7vwrcM"])
        _pay([{"kind": _int(currency[0], 1), "id": _int(currency[1], 1), "count": cost}],
             _int(table[hid]["7UR4J2SE"]))
        if AUTHORED_HIDDEN_REPLACE_PREDECESSOR:
            learned[:] = [p for p in learned if p not in previous]
        learned.append(hid)
        _store("hidden_skill", state)
    out = _reply(spec)
    out["dnUSYLgn"] = [{"woghJa61": series, "umTJJ97w": ",".join(learned)}]
    return out


@_action
def master_card_release(spec, req):
    n = _node(req, "w7J3XBtq") or {}
    iid = str(n.get("og2GHy49", ""))
    unit = _unit(iid)
    state = deepcopy(_feature("sublimation"))
    _require(state.get("slots", {}).get(iid), "master-card slot is not unlocked")
    _require(not unit.get("vision_card"), "unequip the vision card before releasing its slot")
    rewards = _triples(_define("VISION_CARD_SACRIFICE_ITEM_ID"))
    _rewards(rewards)
    _require(State.player.spend_lapis(_int(_define("REMOVE_MASTERCARD_LAPIS"), 1)), "insufficient lapis")
    State.player.deliver_mail(AUTHORED_RETURN_MAIL_TITLE, [(r["kind"], r["id"], r["count"]) for r in rewards],
                              message=AUTHORED_RETURN_MAIL_MESSAGE)
    state["slots"][iid] = False
    _store("sublimation", state)
    out = _reply(spec)
    out["qja26wHb"] = State.player.mail_rows()
    out["t8TPs6o2"] = State.player.mail_counters()
    return out


def _recipe(n, count=1):
    rid, bid = str(_int(n.get("MpNE6gB5"), 1)), str(_int(n.get("staFu8U1"), 1))
    row = _table("F_RECIPE_MST", "MpNE6gB5").get(rid)
    book = _table("F_RECIPE_BOOK_MST", "staFu8U1").get(bid)
    _require(row and book and rid in str(book["8Qt4Ccew"]).split(","), "recipe/book mismatch")
    _require(_feature("craft").get("books", {}).get(bid), "recipe book is not owned")
    costs = _triples(row["HS7V6Ww1"])
    for cost in costs:
        cost["count"] *= count
    selected = str(n.get('XjLm3Y0r') or '').strip()
    if selected:
        ids = selected.split(',')
        _require(all(i.isascii() and i.isdigit() and int(i) > 0 for i in ids),
                 'invalid selected crafting materials')
        allowed = Counter({str(r['id']): r['count'] for r in costs if r['kind'] == 21})
        _require(not (Counter(ids) - allowed), 'selected crafting materials do not match recipe')
    result = {"kind": _int(row["gak9Gb3N"], 1), "id": _int(row["6uIYE15X"], 1),
              "count": _int(row["Qy5EvcK1"], 1) * count}
    _rewards([result])
    return row, costs, _int(row["7UR4J2SE"]) * count, result


def _craft_result(n, reward, bonuses=()):
    return {"staFu8U1": str(n["staFu8U1"]), "MpNE6gB5": str(n["MpNE6gB5"]),
            "jsvoa0I2": ":".join(str(reward[k]) for k in ("kind", "id", "count")),
            "MHNbK26X": _reward_csv(bonuses), "nM63Zvtp": ""}


def _reward_csv(rows):
    return ','.join(':'.join(str(r[k]) for k in ('kind', 'id', 'count')) for r in rows)


def _craft_byproducts(row, count=1):
    text = str(row.get('MHNbK26X') or '').strip()
    if text in ('', '0', '0,'):
        return []
    chance, separator, items = text.partition(',')
    rate = _int(chance)
    _require(separator and rate <= 100, 'invalid byproduct rate')
    rewards = _triples(items)
    _rewards(rewards)
    hits = sum(rate == 100 or random.randrange(100) < rate for _ in range(count))
    return [dict(r, count=r['count'] * hits) for r in rewards] if hits else []


def _craft_progress(row, count=1):
    key = {'20': 'TOTAL_CRAFT_ITEM', '21': 'TOTAL_CRAFT_EQUIP', '22': 'TOTAL_CRAFT_ABILITY'}[str(row['gak9Gb3N'])]
    State.player.bump_progress(key, count, what='completed crafting')


@_action
def craft_exe(spec, req):
    nodes = req.get("ayrzi0H4") or []
    _require(isinstance(nodes, list) and nodes and all(isinstance(n, dict) for n in nodes), "invalid craft batch")
    costs, gil, rewards, results, bonuses, completed = [], 0, [], [], [], []
    for n in nodes:
        count = _int(n.get("3EhUu8Xm"), 1)
        row, materials, price, reward = _recipe(n, count)
        costs.extend(materials)
        gil += price
        rewards.append(reward)
        extra = _craft_byproducts(row, count)
        bonuses.extend(extra)
        results.append(_craft_result(n, reward, extra))
        completed.append((row, count))
    _pay(costs, gil)
    _grant(rewards + bonuses)
    for row, count in completed:
        _craft_progress(row, count)
    state = deepcopy(_feature("craft"))
    state["last_results"] = results
    _store("craft", state)
    out = _reply(spec)
    out["0T5wP98d"] = results
    out["0eDvu2N3"] = [{"MHNbK26X": _reward_csv(bonuses)}]
    return out


def _slot(n, operation):
    _require(_int(n.get("KosY4a18"), 1) == operation, "craft operation mismatch")
    key = str(_int(n.get("gak9Gb3N"), 1)) + ":" + str(_int(n.get("6ukvMSg9"), 1))
    state = deepcopy(_feature("craft"))
    slot = state.get("slots", {}).get(key)
    _require(isinstance(slot, dict), "craft slot is not unlocked")
    return state, slot


def _slot_row(n, slot):
    def date(value):
        return time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime(value)) if value else ""
    return {"gak9Gb3N": str(n["gak9Gb3N"]), "6ukvMSg9": str(n["6ukvMSg9"]),
            "1J7WnqxL": str(slot.get("join_reason", 0)), "MpNE6gB5": str(slot.get("recipe", 0)),
            "f5De4ZpL": date(slot.get("start", 0)), "qpUQ7cE8": date(slot.get("end", 0)),
            "nRHg3K2h": str(_craft_charge(slot)),
            "MN1g2DBs": str(max(0, math.ceil(slot.get("end", 0) - time.time())))}


def _craft_charge(slot):
    # Local legacy timer policy. GL9 supplies this price from the server;
    # use one lapis per started three minutes and the shipped 5,000 cap.
    remaining = max(0, math.ceil(slot.get('end', 0) - time.time()))
    return min(_int(_define('CRAFT_TIME_REDUCTION_COST_LIMIT')), (remaining + 179) // 180)


@_action
def craft_start(spec, req):
    n = _node(req, "0eDvu2N3") or {}
    state, slot = _slot(n, 2)
    _require(not slot.get("recipe"), "craft slot is busy")
    row, costs, gil, reward = _recipe(n)
    _require(str(n["gak9Gb3N"]) == str(row["gak9Gb3N"]), "craft category mismatch")
    duration = _int(row["M5VLKe2F"])
    _pay(costs, gil)
    now = int(time.time())
    slot.update(recipe=str(n["MpNE6gB5"]), book=str(n["staFu8U1"]), start=now, end=now + duration)
    _store("craft", state)
    out = _reply(spec)
    out["yeXn0tk1"] = [_slot_row(n, slot)]
    return out


@_action
def craft_cancel(spec, req):
    n = _node(req, "0eDvu2N3") or {}
    state, slot = _slot(n, 4)
    _require(str(slot.get("recipe", 0)) == str(n.get("MpNE6gB5")) and slot.get("recipe"), "active recipe mismatch")
    _require(str(n.get("I5o3stxJ", 0)) in ("0", "False"), "cancellation cannot use lapis")
    slot.update(recipe=0, start=0, end=0)
    _store("craft", state)  # AUTHORED no refund and no output
    out = _reply(spec)
    out["yeXn0tk1"] = [_slot_row(n, slot)]
    return out


@_action
def craft_end(spec, req):
    n = _node(req, "0eDvu2N3") or {}
    state, slot = _slot(n, 3)
    _require(slot.get("recipe") and str(slot["recipe"]) == str(n.get("MpNE6gB5")), "active recipe mismatch")
    charge = _craft_charge(slot)
    if charge:
        _require(str(n.get('I5o3stxJ', 0)) in ('1', 'True', 'true'), 'craft is unfinished')
        _require(State.player.spend_lapis(charge), 'insufficient instant-completion lapis')
    selected = dict(n, staFu8U1=slot["book"])
    row, costs, gil, reward = _recipe(selected)
    bonuses = _craft_byproducts(row)
    _grant([reward] + bonuses)  # Cost was paid by start, never by end.
    _craft_progress(row)
    slot.update(recipe=0, start=0, end=0)
    _store("craft", state)
    out = _reply(spec)
    out["yeXn0tk1"] = [_slot_row(n, slot)]
    out["0T5wP98d"] = [_craft_result(selected, reward, bonuses)]
    out["0eDvu2N3"] = [{"MHNbK26X": _reward_csv(bonuses)}]
    return out


@_action
def gift_update(spec, req):
    n = _node(req, "WSH38iMI") or {}
    state = deepcopy(_feature("gift"))
    gifts = state.setdefault("receipts", {})
    uid = State.player.friend_id()
    sent_count = 0
    masters = _service_master('gifts')
    selected = str(n.get('Utx8P1Qo') or State.player.data['profile'].get('gift_id') or _define('INITIAL_GIFT_ID'))
    _require(selected in masters, 'unknown preferred gift')
    if n.get("2L0dxwuN"):
        from ffbe_friends import all_friends as load_friends
        friends = {str(f['friend_id']): f for f in load_friends()}
        today = time.strftime('%Y-%m-%d', time.gmtime())
        sent = state.setdefault('sent', {})
        seen = set()
        for entry in str(n["2L0dxwuN"]).split(","):
            parts = entry.split(":")
            _require(len(parts) == 2 and parts[0] in friends, "gift recipient is not an offline friend")
            friend_id, gift_id = parts
            _require(friend_id not in seen and gift_id in masters, 'duplicate recipient or unknown gift')
            seen.add(friend_id)
            # A retried send returns the same history without another delivery.
            if sent.get(friend_id) == today:
                continue
            friend = friends[friend_id]
            # UserGiftInfoResponse parses this as epoch seconds, not a date.
            stamp = str(int(time.time()))
            def receipt(key, sender, recipient, name, rank, unit, gift):
                row = masters[gift]
                kind, target, count = (int(row[k]) for k in ('YWF08vZS', '6uIYE15X', 'Qy5EvcK1'))
                # Native currency rewards are type:amount, ordinary items
                # are type:id:amount (GameUtils::convertToRewardItemInfo).
                reward = f'{kind}:{count}' if kind in STORAGE_CURRENCY else f'{kind}:{target}:{count}'
                return {'2HqjK1F7': key, 'f5LHNT4v': stamp, 'm94IYp6a': sender,
                        '9WsTg26F': str(unit['master_id']), 'AJGfV35v': name,
                        'QSf4NDq3': str(rank), 'wjX34YxG': str(unit['level']),
                        'bUfq8BJ3': recipient, 'Igd28KXq': '0',
                        'jsvoa0I2': reward,
                        'n69quiCJ': '0', 'vs48LZrt': '0'}
            # Native send history is a UserGiftInfo row with the player as sender.
            # Local companions reciprocate once per UTC day, using the preference.
            next_id = max([int(key) for key in gifts] + [int(time.time())]) + 1
            outgoing, incoming = str(next_id), str(next_id + 1)
            leader = State.player.data['roster'][0]
            gifts[outgoing] = receipt(outgoing, uid, friend_id,
                                     str(State.player.data['identity'].get('handle_name') or 'Rain'),
                                     State.player.data['rank']['level'], leader, gift_id)
            gifts[incoming] = receipt(incoming, friend_id, uid, friend['display_name'],
                                     friend['rank'], friend['unit'], selected)
            sent[friend_id] = today
            sent_count += 1
    ids = _ids(n["9wXIbKq2"]) if n.get("9wXIbKq2") else []
    rewards, pending = [], []
    for iid in ids:
        gift = gifts.get(iid)
        _require(gift and str(gift.get("bUfq8BJ3")) == uid, "gift receipt does not belong to player")
        if str(gift.get("Igd28KXq", "0")) == "0":
            reward = str(gift.get('jsvoa0I2') or '')
            parts = reward.split(':')
            if len(parts) == 2 and parts[0].isdigit() and int(parts[0]) in STORAGE_CURRENCY:
                reward = parts[0] + ':0:' + parts[1]
            rewards.extend(_triples(reward))
            pending.append(gift)
    _rewards(rewards)
    _grant(rewards)
    for gift in pending:
        gift["Igd28KXq"] = "1"
    State.player.data['profile']['gift_id'] = int(selected)
    _store('gift', state)
    State.player.record_archive({'TOTAL_GIFT_PRESENT': sent_count, 'TOTAL_GIFT_RECIEVE': len(pending)})
    if sent_count:
        from ffbe_player import _satisfied_quests, _daily_quests_for_action
        for key, qid, meta in _satisfied_quests('friend_gift'):
            State.player.bump_progress(key, sent_count, cap=meta['max'] or None,
                                       what=f'friend_gift -> {qid}')
        for key, qid, target in _daily_quests_for_action('friend_gift', State.player):
            State.player.bump_progress(key, sent_count, cap=target or None,
                                       what=f'friend_gift -> daily quest {qid}')
    out = _reply(spec)
    out["h5XGny0N"] = list(gifts.values())
    return out


def serve_feature_state(spec, reply_id=None):
    """Restore persistent service state on login and the corresponding menus."""
    if not isinstance(spec, dict) or State.player is None:
        return spec
    # The native automatic conversion screen can stall before sending its
    # request. Bank EXP when inventory is refreshed, leaving fresh summon
    # awards in the roster so their reveal can resolve the awarded instance.
    if (reply_id != '9fVIioy1' and ('LhVz6aD2' in spec or UNIT_GROUP in spec)
            and convert_material_units(State.player)):
        spec = dict(spec, z36FApms=_point_rows())
    if reply_id not in {'75fYdNxq', 'X07iYtp5', '6H1R9WID', 'u7Id4bMg',
                        '9KN5rcwj', 'syKz34cE'} and 'LhVz6aD2' not in spec:
        return spec
    out = dict(spec)
    out['nSG9Jb1s'] = _archive_rows()
    craft = deepcopy(_feature('craft'))
    release = switch_position(_define('CRAFT_RELEASE_SWITCH_ID'))
    unlocked = bool(craft.get('books')) or (release and release[1] in State.player.switches.get(release[0], set()))
    if unlocked and State.player.mode != 'frozen':
        slots = craft.setdefault('slots', {})
        changed = False
        for category in ('20', '21', '22'):
            for number in range(1, 5):
                key = category + ':' + str(number)
                if key not in slots:
                    slots[key] = {'recipe': 0, 'start': 0, 'end': 0, 'join_reason': 0}
                    changed = True
        if changed:
            _store('craft', craft)
    out['PmR4z1S7'] = list(_service_master('gifts').values())
    out['h5XGny0N'] = list(_feature('gift').get('receipts', {}).values())
    out['z36FApms'] = _point_rows()
    out['E4r63ukD'] = list(_service_master('trust_exchange').values())
    out['ibt8aCI7'] = [{'d9gKeu0T': str(i), '0zBQbX4N': str(count)}
                      for i, count in _feature('exchange').get('counts', {}).items()]
    out['gy84FjCA'] = [_slot_row({'gak9Gb3N': category, '6ukvMSg9': number}, slot)
                       for key, slot in _feature('craft').get('slots', {}).items()
                       for category, number in [key.split(':')]]
    return out


HANDLERS = {
    "sxK2HG6T": item_buy,                  # ItemBuyRequest
    "PIv7u8jU": strongbox_open,            # StrongBoxOpenRequest
    "I7fmVX3R": exchange_shop,             # ExchangeShopRequest
    "syKz34cE": shop_exchange_list,        # ShopExchangeItemListRequest
    "xD5b6PqQ": shop_exchange_item,        # ShopExchangeItemRequest
    "Vgi7j68T": shop_exchange_unit,        # ShopExchangeUnitRequest
    "LiM9Had2": medal_exchange,           # MedalExchangeRequest
    "i0woEP4B": variable_store_check,     # VariableStoreCheckRequest
    "wukWY4t2": trophy_reward,            # TrophyRewardRequest
    "5J14x3Qz": vision_card_mix,          # VisionCardMixRequest
    "TmS3EjZ8": vision_card_display,      # VisionCardDisplayRequest
    "a54L9CKY": unit_sublimation,         # UnitSublimationRequest
    "s48Qzvhd": sublimation_skill,        # SublimationSkillRequest
    "nsxUW3Y7": unit_use_point,           # UnitUsePointRequest
    "Pf5C8xjJ": unit_nv_class_up,         # UnitNvClassUpRequest
    "V8GtMQ2q": unit_nvp_class_up,        # UnitNvpClassUpRequest
    "k6NI9Tm1": unit_ex_class_up,         # UnitExClassUpRequest
    "QkN1Sp64": craft_add,               # CraftAddRequest
    "79xDN1Mw": craft_cancel,            # CraftCancelRequest
    "WIuvh09n": craft_end,               # CraftEndRequest
    "PKDhIN34": craft_exe,               # CraftExeRequest
    "Gr9zxXk5": craft_start,             # CraftStartRequest
    "qxUUaS8s": hidden_skill_upgrade,     # sgHiddenSkillUpgrade
    "23fbcXt4": master_card_release,      # MasterCardReleaseRequest
    "9KN5rcwj": gift_update,             # GiftUpdateRequest
}
