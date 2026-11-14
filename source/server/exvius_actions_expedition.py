"""Offline expedition, map-quest and registered-party actions for Global v9.

Original masters define requirements, durations, rewards and trust gains.
content/expeditions.json records the offline grade, XP and random-category
policies where the retired backend supplied no recoverable definitions.
Collection, milestone claims and map deliveries use atomic inventory changes
and durable receipts. Weekly points and daily attempt limits survive reloads.
Party slots retain native strings and authoritative loadout snapshots; loading
restores owned gear, materia, cards and espers without recreating sold items.
Archive unlocks are permanent unless an explicit native duration is supplied.
Challenge reset consumes the original entitlement. Frozen saves never mutate.
"""
from copy import deepcopy
from collections import Counter
from functools import wraps
import json
import math
import re
from pathlib import Path
import secrets
import time

from exvius_actions import UNIT_GROUP, _node, _refresh, _mst, _parse_rewards
from ffbe_state import State, _note
from ffbe_battle import _switch_container
from player_state import GRANT_BAG_PROJECTED, STORAGE_CURRENCY, switch_position, unit_mst, vision_card_key

DAY_ANCHOR = 14400                       # The offline daily reset (04:00 UTC), as for attempt limits.
OFFERS_VERSION = 2                       # Saves offered under the older sequential scheme are re-dealt once.
AUTHORED_PARTY_LIMIT = 5                 # Conservative offline expedition selection limit.

QUEST = "67l03PW2"
SLOT = "b7Ay4Ju8"
SLOT_FIELDS = ("YLi31qam", "o0T4S52k", "G4L0YIB2", "2A6fYiEC", "w1JG7i9j",
               "XZ4Kh7Ic", "93Y6evuT", "80NUYFMJ", "2c8nqLrM", "xBi3L6yR",
               "r21y0YzS", "Na7YM2v4", "nQ1iAGf3")
LINE_COLUMNS = ("9neAsUui", "VcnF0Qyt", "JRpHYrcf", "xQGaV4rq", "Z9DG2ftx",
                "nnh27KwE", "xJIcglf6", "ybd0k1yF")


def _int(value, default=0):
    try:
        return int(str(value))
    except (ValueError, TypeError):
        return default


def _store(feature):
    # Read-only callers must not create an unmarked change in a fresh save.
    return State.player.data.get("exvius_" + feature, {})


def _put(feature, value):
    State.player.data["exvius_" + feature] = value
    State.player.dirty = True


def _out(spec, **groups):
    out = deepcopy(spec) if isinstance(spec, dict) else {}
    out.update(deepcopy(groups))
    return out


def _refuse(spec, reason):
    _note("expedition actions: " + reason)
    return spec


def _writable(spec):
    if State.player.mode == "frozen":
        _refuse(spec, "frozen player; action refused")
        return False
    return True


def _define(key):
    return (_mst("F_DEFINE_MST.ndjson", "AK8Nn7ta").get(key) or {}).get("YjIUDJ97")


def _quest_reply(spec):
    rows = deepcopy(list(_store("expedition").get("quests", {}).values()))
    day = (int(time.time()) - 14400) // 86400
    attempts = _store('expedition').get('daily_attempts', {})
    for row in rows:
        key = str(day) + ':' + str(row.get('Ko86047K'))
        row['mqbn4Gdm'] = str(attempts.get(key, row.get('mqbn4Gdm', '0')))
    return _out(spec, **{QUEST: rows})


def _points():
    block = _expedition_week()
    return [{"92l3W8pW": str(block.get("points", 0)), "edd6db2H": "0",
             "O82h92n5": str(block.get("reset", 0))}]


def _atomic(fn):
    @wraps(fn)
    def call(spec, req):
        from exvius_actions_shops import _action
        return _action(fn)(spec, req)
    return call


def _expedition_policy():
    return json.loads(Path(__file__).with_name('content').joinpath('expeditions.json').read_text(encoding='utf8'))


def _expedition_week():
    block = deepcopy(_store('expedition'))
    now = int(time.time())
    # Global's offline weekly cycle is anchored to Thursday 04:00 UTC.
    week = (now - 14400) // 604800
    if block.get('week') != week:
        block.update(week=week, points=0, reset=(week + 1) * 604800 + 14400, claimed=[])
    return block


def _milestones(block):
    policy = _expedition_policy()
    result = []
    for row in policy['milestones']:
        reward = row['reward']
        if row['id'] == '3' and block['week'] % 2:
            reward = policy['alternate_pot'] + ',23:110003:5'
        result.append({'k60s8T42': row['id'], 'p1H8307H': str(row['points']),
                       '3JND4wjr': ('2' if row['id'] in block.get('claimed', []) else
                                    '1' if block.get('points', 0) >= row['points'] else '0'),
                       '23tA3948': reward})
    return result


def _expedition_rewards(text):
    from exvius_actions_shops import _require, _rewards
    from exvius_rewards import parse
    result = []
    pools = _expedition_policy()['random_item_pools']
    try:
        # The original Moogle Cave has an explicit zero-count display row.
        rows = parse(','.join(e for e in str(text or '').split(',')
                              if e and len(e.split(':')) >= 3 and e.split(':')[2] != '0'))
    except ValueError as exc:
        _require(False, str(exc))
    for reward in rows:
        kind, iid, count = reward['kind'], reward['id'], reward['count']
        if kind == 20 and str(iid) in pools:
            # These native IDs are display categories, never actual inventory.
            for _ in range(count):
                result.append({'kind': 20, 'id': secrets.choice(pools[str(iid)]), 'count': 1})
            continue
        result.append(reward)
    _rewards(result)
    return result


def _reward_csv(rewards):
    return __import__('exvius_rewards').reward_text(rewards)


# --- offers --------------------------------------------------------------------------------------------
# What the list holds, as in Global (wiki "Expedition" and "Basic Information"):
# - the tutorial chain first: Relic Hunting Craze I, then II, then III (`sZ4964o7` names the next), 10 s each;
# - then EXPEDITION_MAX_AVAILABLE (3) offers dealt from the regular expeditions (`sx4kyW0i` 2: ranks D to S,
#   3 to 24 hours), replaced by the refresh button: free once a day at the daily reset, or for lapis or an
#   Ancient Coin;
# - alongside them, outside that count: the supercite expeditions of the day (`sx4kyW0i` 1; `5BsSnrD4` lists
#   the weekdays, 1 = Monday: red/blue and violet/yellow Monday to Thursday, orange/white and green/black Friday
#   to Monday) and the Moogle Cave (`sx4kyW0i` 3, three a day), within their `Tx6MGkJ1`..`2x2W5439` dates.
# The retired backend's deal weights were not recovered: regular offers are dealt uniformly at random among
# the regular expeditions not already on the list.
TUTORIAL, REGULAR, SUPERCITE, MOOGLE = "0", "2", "1", "3"


def _kind(row):
    return str((row or {}).get("sx4kyW0i") or "")


def _today():
    return (int(time.time()) - DAY_ANCHOR) // 86400


def _next_reset(now):
    return ((now - DAY_ANCHOR) // 86400 + 1) * 86400 + DAY_ANCHOR


def _in_dates(row, now):
    stamp = time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime(now))
    start, end = str(row.get("Tx6MGkJ1") or ""), str(row.get("2x2W5439") or "")
    return (not start or start <= stamp) and (not end or stamp <= end)


def _fixed_ids(masters, now):
    """Supercite expeditions of today and the Moogle Cave."""
    weekday = str(time.gmtime(now - DAY_ANCHOR).tm_wday + 1)
    out = []
    for mid, row in masters.items():
        if _kind(row) == MOOGLE and _in_dates(row, now):
            out.append(mid)
        elif _kind(row) == SUPERCITE and _in_dates(row, now) and \
                weekday in str(row.get("5BsSnrD4") or "").split(","):
            out.append(mid)
    return sorted(out, key=int)


def _tutorial_start(masters):
    tutorial = {m for m, r in masters.items() if _kind(r) == TUTORIAL}
    chained = {str(r.get("sZ4964o7")) for m, r in masters.items() if m in tutorial}
    return sorted(tutorial - chained, key=int)


def _offer(block, mid):
    block["serial"] = _int(block.get("serial")) + 1
    key = "offline-" + str(block["serial"])
    block.setdefault("quests", {})[key] = {"q3D53k94": key, "Ko86047K": str(mid), "7mA422N6": "", "Tx6MGkJ1": "0",
                                           "2CL6pZmE": "0", "3JND4wjr": "1", "Sf2m961q": "0", "mqbn4Gdm": "0",
                                           "O82h92n5": "0", "2A6fYiEC": ""}


def _tutorial_pending(block, masters):
    if block.get("tutorial_done"):
        return False
    return any(_kind(masters.get(str(q.get("Ko86047K")))) == TUTORIAL for q in block.get("quests", {}).values())


def _deal(block, masters, count):
    """Replace the available regular offers with `count` new ones."""
    quests = block.setdefault("quests", {})
    for key in [k for k, q in quests.items() if str(q.get("3JND4wjr")) != "2"
                and _kind(masters.get(str(q.get("Ko86047K")))) == REGULAR]:
        del quests[key]
    listed = {str(q.get("Ko86047K")) for q in quests.values()}
    pool = sorted((m for m, r in masters.items() if _kind(r) == REGULAR and m not in listed), key=int)
    rng = secrets.SystemRandom()
    for mid in rng.sample(pool, min(count, len(pool))):
        _offer(block, mid)


def _tidy(block, masters, now):
    """Keep the fixed offers in step with the day, and drop repeated available offers."""
    quests = block.setdefault("quests", {})
    seen = set()
    for key in sorted(quests, key=lambda k: _int(k.rsplit("-", 1)[-1])):
        q = quests[key]
        mid = str(q.get("Ko86047K"))
        if str(q.get("3JND4wjr")) == "2":
            continue
        if mid not in masters or mid in seen:
            del quests[key]
            continue
        seen.add(mid)
    fixed = _fixed_ids(masters, now)
    for key in [k for k, q in quests.items() if str(q.get("3JND4wjr")) != "2"
                and _kind(masters.get(str(q.get("Ko86047K")))) in (SUPERCITE, MOOGLE)
                and str(q.get("Ko86047K")) not in fixed]:
        del quests[key]
    listed = {str(q.get("Ko86047K")) for q in quests.values()}
    for mid in fixed:
        if mid not in listed:
            _offer(block, mid)


def _settle_offers(block, masters, now, available):
    """Seed a new list, or bring an existing one up to date. True when the block changed."""
    before = deepcopy(block)
    if "quests" not in block:
        block["quests"] = {}
        for mid in _tutorial_start(masters):
            _offer(block, mid)
        if not block["quests"]:
            block["tutorial_done"] = True
        block["next_free"] = _next_reset(now)
    elif block.get("offers") != OFFERS_VERSION:
        # Lists dealt by the older scheme (ids in order, so the tutorial chain three at once): keep running
        # jobs, keep the tutorial going if it is under way, and deal regular offers once it is done.
        if not _tutorial_pending(block, masters):
            block["tutorial_done"] = True
        if block.get("tutorial_done"):
            _deal(block, masters, available)
        block["next_free"] = min(_int(block.get("next_free")) or _next_reset(now), _next_reset(now))
    block["offers"] = OFFERS_VERSION
    _tidy(block, masters, now)
    if block.get("tutorial_done") and not any(
            _kind(masters.get(str(q.get("Ko86047K")))) == REGULAR for q in block["quests"].values()):
        _deal(block, masters, available)
    return block != before


def expedition_info(spec, req):
    """Open/reopen the native Expedition list with durable jobs and milestones."""
    masters = _mst("F_EXPEDITION_MST.ndjson", "Ko86047K")
    available = _int(_define("EXPEDITION_MAX_AVAILABLE"))
    if masters and available > 0 and State.player.mode != 'frozen':
        block = deepcopy(_store('expedition'))
        if _settle_offers(block, masters, int(time.time()), available):
            _put('expedition', block)
    return expedition_refresh(spec, {})


def expedition_refresh(spec, req):
    out = _quest_reply(spec)
    block = deepcopy(_store("expedition"))
    out["nUM2AENx"] = [{"NB9uKefC": str(block.get("next_free", 0))}]
    out['Ec901P4A'] = _milestones(_expedition_week())
    out['nv1j95sC'] = _points()
    node = _node(req, QUEST)
    # The original free-refresh request serializes an empty group, not [{}].
    if node is None and req.get(QUEST) == []:
        node = {}
    if node is None or not _writable(out):
        return out
    now = int(time.time())
    selector = str(node.get("0B8RL54c") or "")
    exchange = _parse_rewards(_define("EXPEDITION_REFRESH_EXCHANGE"))
    payment = next((r for r in exchange if f"{r['kind']}:{r['id']}" == selector), None)
    if selector and (selector not in ("50:1", str(_define("EXPEDITION_REFRESH_ID"))) or not payment):
        return _refuse(out, "unknown refresh selector; nothing charged")
    if not selector and now < _int(block.get("next_free")):
        return _refuse(out, "free refresh is not due")
    masters = _mst("F_EXPEDITION_MST.ndjson", "Ko86047K")
    available = _int(_define("EXPEDITION_MAX_AVAILABLE"))
    if not masters or available <= 0:
        return _refuse(out, "missing expedition offer definitions; nothing charged")
    _settle_offers(block, masters, now, available)
    if _tutorial_pending(block, masters):
        return _refuse(out, "the tutorial expeditions come first; nothing charged")
    if payment:
        paid = (State.player.spend_lapis(payment["count"]) if payment["kind"] == 50 else
                State.player.spend_item(payment["kind"], payment["id"], payment["count"]))
        if not paid:
            return _refuse(out, "insufficient refresh payment")
    _deal(block, masters, available)
    if not selector:
        block["next_free"] = _next_reset(now)
    _put("expedition", block)
    out = _quest_reply(_refresh(spec))
    out["nUM2AENx"] = [{"NB9uKefC": str(block.get("next_free", 0))}]
    weekly = _expedition_week()
    out['Ec901P4A'] = _milestones(weekly)
    out['nv1j95sC'] = _points()
    return out


def _live(req):
    node = _node(req, QUEST) or {}
    key = str(node.get("Ko86047K") or "")
    return node, key, _store("expedition").get("quests", {}).get(key)


def expedition_start(spec, req):
    out = _quest_reply(spec)
    node, key, quest = _live(req)
    if not quest or str(quest.get("3JND4wjr")) != "1" or not _writable(out):
        return _refuse(out, "start requires an available live quest")
    masters = _mst("F_EXPEDITION_MST.ndjson", "Ko86047K")
    row = masters.get(str(quest.get("Ko86047K"))) or {}
    difficulty = _mst("F_EXPEDITION_DIFFICULTY_MST.ndjson", "Up7229W2").get(str(row.get("Up7229W2"))) or {}
    duration, gil = _int(difficulty.get("7Ac7722s")), _int(row.get("7LIoPpG9"), -1)
    pairs = [p.split(":") for p in str(node.get("7mA422N6") or "").split(",")]
    roster = {str(u["instance_id"]): u for u in State.player.data["roster"]}
    quests = _store("expedition").get("quests", {})
    busy = {p.split(":")[0] for q in quests.values() if str(q.get("3JND4wjr")) == "2"
            for p in str(q.get("7mA422N6") or "").split(",") if p}
    running = sum(str(q.get("3JND4wjr")) == "2" for q in quests.values())
    if (duration <= 0 or gil < 0 or not 1 <= len(pairs) <= AUTHORED_PARTY_LIMIT or
            any(len(p) != 2 or p[0] not in roster or p[0] in busy or
                str(roster[p[0]]["master_id"]) != p[1] or roster[p[0]].get("storage_state", 0)
                for p in pairs) or len({p[0] for p in pairs}) != len(pairs) or
            running >= _int(_define("EXPEDITION_MAX_ONGOING"))):
        return _refuse(out, "invalid expedition party, capacity or master definition")
    limit = _int(row.get("7utfhGQa"))
    day = (int(time.time()) - 14400) // 86400
    attempts = _store('expedition').get('daily_attempts', {})
    attempt_key = str(day) + ':' + str(row.get('Ko86047K'))
    if limit > 0 and _int(attempts.get(attempt_key)) >= limit:
        return _refuse(out, "expedition attempt limit reached")
    flag = node.get("sO308L0M", "0")
    if str(flag) not in ("0", "1", "False", "True"):
        return _refuse(out, "invalid optional-consumable flag")
    costs, bonus = {}, 0
    if str(flag) in ("1", "True"):
        for entry in filter(None, str(row.get("sO308L0M") or "").split(",")):
            fields = entry.split(":")
            if len(fields) != 4 or not all(f.isdigit() for f in fields):
                return _refuse(out, "unresolved optional-consumable definition")
            kind, iid, count, value = map(int, fields)
            if kind not in (20, 23) or count <= 0:
                return _refuse(out, "unsupported optional-consumable kind or count")
            costs[kind, iid] = costs.get((kind, iid), 0) + count
            bonus += value
    if State.player.currencies.get("gil", 0) < gil or any(
            State.player.item_count(k, i) < c for (k, i), c in costs.items()):
        return _refuse(out, "insufficient start gil or consumables; nothing charged")
    State.player.spend_currency("gil", gil)
    for (kind, iid), count in costs.items():
        State.player.spend_item(kind, iid, count)
    now = int(time.time())
    block = deepcopy(_store("expedition"))
    block['daily_attempts'] = {k: v for k, v in attempts.items() if k.startswith(str(day) + ':')}
    block['daily_attempts'][attempt_key] = _int(attempts.get(attempt_key)) + 1
    block["quests"][key].update({"7mA422N6": ",".join(":".join(p) for p in pairs),
                                "Tx6MGkJ1": str(now), "2CL6pZmE": str(now + duration),
                                "3JND4wjr": "2", "Sf2m961q": str(bonus),
                                "mqbn4Gdm": str(_int(quest.get("mqbn4Gdm")) + 1)})
    _put("expedition", block)
    from ffbe_player import score_quest_action
    score_quest_action('44')
    return _quest_reply(_refresh(spec))


def expedition_accelerate(spec, req):
    out = _quest_reply(spec)
    node, key, quest = _live(req)
    costs = _parse_rewards(node.get("8Pa9U16z"))
    duration = _int(_define("EXPEDITION_ADV_DUR"))
    now = int(time.time())
    if quest:
        master = _mst('F_EXPEDITION_MST.ndjson', 'Ko86047K').get(str(quest.get('Ko86047K')), {})
        if master.get('Kxx2fFgK'):
            return _refuse(out, 'Moogle Cave cannot be accelerated')
    remaining = _int((quest or {}).get("2CL6pZmE")) - now
    if (not quest or str(quest.get("3JND4wjr")) != "2" or remaining <= 0 or duration <= 0 or
            len(costs) != 1 or f"{costs[0]['kind']}:{costs[0]['id']}" != _define("EXPEDITION_ACCELERATE_ID") or
            str(node.get("8Pa9U16z")) != f"{costs[0]['kind']}:{costs[0]['id']}:{costs[0]['count']}" or
            costs[0]["count"] > (remaining + duration - 1) // duration or not _writable(out)):
        return _refuse(out, "invalid acceleration quest or expenditure")
    cost = costs[0]
    if not State.player.spend_item(cost["kind"], cost["id"], cost["count"]):
        return _refuse(out, "insufficient acceleration items")
    block = deepcopy(_store("expedition"))
    block["quests"][key]["2CL6pZmE"] = str(max(now, now + remaining - cost["count"] * duration))
    _put("expedition", block)
    return _quest_reply(_refresh(spec))


@_atomic
def expedition_end(spec, req):
    from exvius_actions_shops import _require, _grant
    node, key, quest = _live(req)
    block = _expedition_week()
    receipt = block.get('receipts', {}).get(key)
    if receipt:
        return _out(_quest_reply(_refresh(spec)), UDBrChWN=[receipt],
                    nv1j95sC=_points(), Ec901P4A=_milestones(block))
    _require(quest and str(quest.get('3JND4wjr')) == '2', 'expedition is not dispatched')
    _require(_int(quest.get('2CL6pZmE')) <= int(time.time()), 'expedition has not finished')
    row = _mst('F_EXPEDITION_MST.ndjson', 'Ko86047K')[str(quest['Ko86047K'])]
    difficulty = _mst('F_EXPEDITION_DIFFICULTY_MST.ndjson', 'Up7229W2')[str(row['Up7229W2'])]
    try:
        rate = float(node.get('hKcId7sN', 0))
    except (ValueError, TypeError):
        rate = -1
    _require(math.isfinite(rate) and 0 <= rate <= 100, 'invalid expedition success percentage')
    trust = [int(x) for x in str(row.get('Kxx2fFgK') or '').split(':') if x]
    success = bool(trust) or secrets.randbelow(10000) < round(rate * 100)
    grade = 3
    policy = _expedition_policy()
    if success and not trust:
        draw = secrets.randbelow(100)
        grade = 1 if draw < policy['amazing_chance'] else 2 if draw < policy['amazing_chance'] + policy['great_chance'] else 3
    rewards = _expedition_rewards(row.get('4Ya160s7')) if success else []
    relics = _expedition_rewards(row.get('5Yn160s8')) if success else []
    bonus = deepcopy(rewards) if success and grade < 3 else []
    if grade == 1:
        for reward in bonus:
            reward['count'] *= 2
    _grant(rewards + relics + bonus)
    roster = {str(u['instance_id']): u for u in State.player.data['roster']}
    xp = max(1, _int(difficulty['7Ac7722s']) * policy['xp_per_hour'] // 3600)
    for entry in str(quest.get('7mA422N6') or '').split(','):
        iid = entry.split(':')[0]
        unit = roster.get(iid)
        if not unit:
            continue
        State.player.add_unit_exp(iid, xp)
        if trust:
            family = str(unit['master_id'])[:-1]
            rarity = next((n for n in range(1, 9) if unit_mst(family + str(n))), 7)
            # gain_trust caps at the unit's own requirement and pays the Trust Master reward when it is
            # reached (2026-11-07; before, this capped at 1000 and never paid the reward).
            State.player.gain_trust(iid, trust[min(rarity - 1, len(trust) - 1)])
    from ffbe_player import score_daily
    score_daily('expedition_finish')
    gained = _int(difficulty['2A07z50y']) if success else 0
    block['points'] = block.get('points', 0) + gained
    receipt = {'Ra7qY74q': _reward_csv(rewards + relics), '33ZM4Wyw': _reward_csv(bonus),
               '7x8K23fx': str(grade if success else 0)}
    block.setdefault('receipts', {})[key] = receipt
    del block['quests'][key]
    next_id = str(row.get('sZ4964o7') or '0')
    if _kind(row) == TUTORIAL and next_id == '0':
        # The last tutorial expedition opens the regular list.
        block['tutorial_done'] = True
        masters = _mst('F_EXPEDITION_MST.ndjson', 'Ko86047K')
        _deal(block, masters, _int(_define('EXPEDITION_MAX_AVAILABLE')))
    if next_id != '0' or trust:
        next_id = str(row['Ko86047K']) if trust else next_id
        block['serial'] = _int(block.get('serial')) + 1
        next_key = 'offline-' + str(block['serial'])
        block['quests'][next_key] = {**quest, 'q3D53k94': next_key, 'Ko86047K': next_id,
                                     '3JND4wjr': '1', '7mA422N6': '', 'Tx6MGkJ1': '0',
                                     '2CL6pZmE': '0', 'mqbn4Gdm': '0', '2A6fYiEC': quest.get('7mA422N6', '')}
    _put('expedition', block)
    points = _points()
    points[0]['edd6db2H'] = str(gained)
    return _out(_quest_reply(_refresh(spec)), UDBrChWN=[receipt], nv1j95sC=points, Ec901P4A=_milestones(block))


def expedition_recall(spec, req):
    out = _quest_reply(spec)
    _, key, quest = _live(req)
    if not quest or str(quest.get("3JND4wjr")) != "2" or not _writable(out):
        return _refuse(out, "recall requires a dispatched live quest")
    block = deepcopy(_store("expedition"))
    del block["quests"][key]
    _put("expedition", block)
    return _quest_reply(spec)


@_atomic
def milestone_claim(spec, req):
    from exvius_actions_shops import _require, _grant
    iid = str((_node(req, '5Xh859hl') or {}).get('k60s8T42', ''))
    block = _expedition_week()
    row = next((r for r in _milestones(block) if r['k60s8T42'] == iid), None)
    _require(row is not None, 'unknown expedition milestone')
    if row['3JND4wjr'] != '2':
        _require(row['3JND4wjr'] == '1', 'expedition milestone threshold not met')
        _grant(_expedition_rewards(row['23tA3948']))
        block.setdefault('claimed', []).append(iid)
        _put('expedition', block)
    return _out(_refresh(spec), Ec901P4A=_milestones(block), nv1j95sC=_points())


@_atomic
def challenge_clear(spec, req):
    from exvius_actions_shops import _require
    block = deepcopy(_store('challenge_reset'))
    if not block.get('used'):
        position = switch_position(_define('CHALLENGE_CLEAR_SWITCH'))
        _require(position and position[1] in State.player.switches.get(position[0], set()),
                 'challenge reset entitlement is not owned')
        # This explicit action resets challenge rewards, not story progression.
        progress = State.player.data['progress']
        progress['cleared_challenges'] = {}
        progress['paid_challenges'] = {}
        State.player.data.get('exvius_repeat', {}).pop('non_lapis_claims', None)
        State.player.switches[position[0]].discard(position[1])
        block.update(used=True, time=int(time.time()))
        _put('challenge_reset', block)
    return _switches(_out(_refresh(spec), TQ5AJd2K=[]), [])


def _definition_rows(spec, tag):
    rows = spec.get(tag, [])
    if rows:
        return rows
    for value in getattr(State, 'replies', {}).values():
        if isinstance(value, dict) and value.get(tag):
            return value[tag]
    return []


@_atomic
def dungeon_liberation(spec, req):
    from exvius_actions_shops import _require, _pay
    did = str((_node(req, '8FT3kBVA') or {}).get('U9iHsau3', ''))
    dungeon = _mst('F_DUNGEON_MST.ndjson', 'U9iHsau3').get(did)
    _require(dungeon is not None, 'unknown dungeon')
    block = deepcopy(_store('dungeon_release'))
    now = int(time.time())
    saved = block.get(did)
    if not saved or saved['expires'] <= now:
        # Archived offline events are permanent. Preserve an explicit key cost
        # when a supplied native condition requests one.
        condition = next((r for r in _definition_rows(spec, '0xkoNP8U')
                          if str(r.get('U9iHsau3')) == did), {})
        cost = str(condition.get('B2FW5Qjq') or '')
        key = 0
        if str(condition.get('0iWgxc1X')) == '2':
            fields = cost.split(':')
            _require(len(fields) == 2 and all(x.isdigit() for x in fields), 'invalid dungeon key definition')
            key, count = map(int, fields)
            _pay([{'kind': 23, 'id': key, 'count': count}])
        saved = {'expires': 2145916800, 'key': key}
        block[did] = saved
        _put('dungeon_release', block)
    row = {'0iWgxc1X': '2' if saved['key'] else '0', 'B2FW5Qjq': str(saved['key']),
           'Nf7IsB4A': str(dungeon.get('uv60hgDW', '0')), 'n2zX3VpH': did,
           '3rhPSiK1': time.strftime('%Y%m%d', time.gmtime(now)), 'H3tLd5k8': '1',
           'cD5iTP63': str(saved['expires'] - now), 'iyx5Xv6I': str(saved['expires'] - now)}
    return _out(_refresh(spec), eKZu2j0M=[row])


@_atomic
def mission_unlock(spec, req):
    from exvius_actions_shops import _require, _pay, _triples
    mid = str((_node(req, 'ySFXhkpu') or {}).get('qo3PECw6', ''))
    _require(mid in _mst('F_MISSION_MST.ndjson', 'qo3PECw6'), 'unknown mission')
    block = deepcopy(_store('mission_unlock'))
    now = int(time.time())
    if int(block.get(mid, 0)) <= now:
        definition = next((r for r in _definition_rows(spec, 'RyOoibYJ')
                           if str(r.get('qo3PECw6')) == mid), {})
        cost = _triples(definition.get('kHlsIdXd'))
        _pay([r for r in cost if r['kind'] != 50])
        lapis = sum(r['count'] for r in cost if r['kind'] == 50)
        _require(not lapis or State.player.spend_lapis(lapis), 'insufficient mission unlock lapis')
        duration = _int(definition.get('A31PNXmN'))
        block[mid] = min(2145916800, now + duration) if duration else 2145916800
        _put('mission_unlock', block)
    return _out(_refresh(spec), W0E8BHa8=[{'vUCf4Rw3': mid, 'zI5a9LPo': str(block[mid]), 'N6hVhvgf': '0'}])


def _switches(spec, ids):
    positions = [switch_position(sid) for sid in ids]
    if any(pos is None for pos in positions):
        return _refuse(spec, "unknown switch ID; switch update refused")
    for stype, index in positions:
        State.player.data["progress"]["switches"].setdefault(stype, set()).add(index)
    if positions:
        State.player.dirty = True
    out = _out(spec)
    out["ExQ7H1ok"] = [{"5opcUT9t": t, "juA0Z4m7": _switch_container(out, t)}
                        for t in sorted(State.player.data["progress"]["switches"])]
    return out


def _csv(value):
    return list(dict.fromkeys(x.strip() for x in str(value or "").split(",") if x.strip()))


def mission_switch_update(spec, req):
    if not _writable(spec):
        return spec
    node = _node(req, "0jqUZuT1") or {}
    ids = _csv(node.get("dIPkNn61"))
    carry = _node(req, "nE7pV2wr")
    entries = []
    if carry is not None:
        for entry in filter(None, str(carry.get("jsvoa0I2") or "").split(",")):
            parts = entry.split(":")
            if len(parts) != 3 or not all(p.isdigit() for p in parts):
                return _refuse(spec, "malformed carry list; update refused")
            entries.append(dict(zip(("disp_order", "item_id", "count"), map(int, parts))))
        old = State.player.data["inventory"].get("carry_items", [])
        before, after = {}, {}
        for row in old:
            before[row["item_id"]] = before.get(row["item_id"], 0) + row["count"]
        for row in entries:
            after[row["item_id"]] = after.get(row["item_id"], 0) + row["count"]
        debits = {iid: max(0, count - after.get(iid, 0)) for iid, count in before.items()}
        if (len({r["disp_order"] for r in entries}) != len(entries) or
                any(after.get(i, 0) > c for i, c in before.items()) or
                any(i not in before and c for i, c in after.items()) or
                any(State.player.item_count(20, i) < c for i, c in debits.items())):
            return _refuse(spec, "carry counts cannot increase or exceed owned inventory")
    if any(switch_position(sid) is None for sid in ids):
        return _refuse(spec, "unknown switch ID; update refused")
    out = _switches(spec, ids)
    if carry is not None:
        for iid, count in debits.items():
            State.player.spend_item(20, iid, count)
        State.player.data["inventory"]["carry_items"] = entries
        State.player.dirty = True
        out = _refresh(out)
        out["nE7pV2wr"] = State.player.carry_item_rows()
    return out


@_atomic
def mission_update(spec, req):
    from exvius_actions_shops import _require, _pay, _grant
    node = _node(req, "jQsE54Iz")
    town = _node(req, 'JcxS6A8N')
    if (node is None and town is None) or not _writable(spec):
        return spec
    mid = str((node or {}).get("qo3PECw6") or "")
    if node and mid not in _mst("F_MISSION_MST.ndjson", "qo3PECw6"):
        return _refuse(spec, "unknown mission checkpoint")
    block = deepcopy(_store("map"))
    if node:
        block['mission'] = mid
    if town:
        block['town'] = str(town.get('Gh92V3Tx') or '')
    operation = _node(req, '1sGiqV9T')
    if operation:
        masters = _mst('F_QUEST_MST.ndjson', 'Z34jU7ue')
        steps = _mst('F_QUEST_SUB_MST.ndjson', '7Svg2kdT')
        saved = block.setdefault('quests', {})
        # Each step's own switches (F_QUEST_SUB_MST): `juA0Z4m7` when accepted, `dIPkNn61` when completed. The map
        # and NPC scripts read them (Mitra's map: an event page conditioned on the completion switch); the phone's
        # completion request doesn't send them, so until 2026-11-12 a completed quest was offered again after a
        # restart. quest_switches.repair sets them for saves from before.
        step_switches = []
        for token, completed in [('9YPZuB2i', True), ('i9han5Sz', False)]:
            pair = str(operation.get(token) or '')
            if not pair:
                continue
            fields = pair.split(':')
            _require(len(fields) == 2 and all(x.isdigit() for x in fields), 'invalid quest step')
            qid, sid = fields
            quest, step = masters.get(qid), steps.get(sid)
            _require(quest and step and str(step['Z34jU7ue']) == qid, 'unknown quest step')
            old = saved.get(sid, {})
            step_switches += _csv(step.get('dIPkNn61' if completed or old.get('4kcAD9fW') == '2' else 'juA0Z4m7'))
            if old.get('4kcAD9fW') == '2':
                continue
            preceding = [r for r in steps.values() if r['Z34jU7ue'] == qid
                         and int(r['Z0EN6jSh']) < int(step['Z0EN6jSh'])]
            _require(all(saved.get(r['7Svg2kdT'], {}).get('4kcAD9fW') == '2' for r in preceding),
                     'previous quest step is incomplete')
            if completed and str(step.get('89EvGKHx')) == '1' and str(step.get('siLGXq94')) == '1':
                # Delivery tasks consume the original required items. Other
                # tasks are witnessed by the map script's completion message.
                _pay(_expedition_rewards(step.get('25oxcKwN')))
            saved[sid] = {'Z34jU7ue': qid, '7Svg2kdT': sid,
                          '4kcAD9fW': '2' if completed else '1', '0G7J2vfD': old.get('0G7J2vfD', '')}
            if completed:
                quest_steps = [r for r in steps.values() if r['Z34jU7ue'] == qid]
                if all(saved.get(r['7Svg2kdT'], {}).get('4kcAD9fW') == '2' for r in quest_steps):
                    if qid not in block.setdefault('rewarded', []):
                        _grant(_expedition_rewards(quest.get('dX6cor8j')))
                        block['rewarded'].append(qid)
        switches = list(dict.fromkeys(_csv(operation.get('dIPkNn61')) + step_switches))
        _require(all(switch_position(s) is not None for s in switches), 'unknown quest switch')
        spec = _switches(spec, switches)
    _put("map", block)
    return _out(_refresh(spec), JG96kr5C=list(block.get('quests', {}).values())) if operation else _out(spec)


def quest_steps(spec, req):
    """Quest steps carried by requests other than the two map updates. The game writes the same `1sGiqV9T` group
    into the battle-start request (`MissionStartRequest::createStartQuestTag`: `i9han5Sz`, a step accepted), the
    battle-end request (`MissionEndRequest::createEndQuestTag`: `9YPZuB2i`, the current step of each quest that
    is complete when the quest ends) and the town-exit request (TownOutRequest is a MapUpdateRequest, as
    MissionUpdateRequest is). Until 2026-11-13 only TownUpdateRequest and MissionUpdateRequest were read, so a
    step reported in the others was lost: never saved, never paid, no switch. Here the step goes through
    `mission_update` for the save only; these replies keep their own groups (the battle end's user-state
    projection and switch group already carry the result). The battle end adds one node per quest whose step
    is complete, so each node is handled on its own."""
    for node in req.get('1sGiqV9T') or []:
        if isinstance(node, dict):
            mission_update(spec, {**req, '1sGiqV9T': [node]})
    return spec


def _reward_rows(text):
    # Use the project's currency shorthand, but refuse unrecovered unit suffixes.
    from ffbe_player import _parse_reward
    entries = str(text or "").split(",")
    if any(len(e.split(":")) not in (2, 3) or not all(p.isdigit() for p in e.split(":")) for e in entries):
        return None
    rows = [{"kind": k, "id": i, "count": c} for k, i, c in _parse_reward(text)]
    if not rows or len(rows) != len(entries):
        return None
    for r in rows:
        if (r["kind"] not in STORAGE_CURRENCY and str(r["kind"]) not in GRANT_BAG_PROJECTED
                and r["kind"] not in (10, 21)) or (r["kind"] == 10 and unit_mst(r["id"]) is None):
            return None
    return rows


def comeback_claim(spec, req):
    node = _node(req, "cguj1Hd4") or {}
    campaign = str(node.get("MqUuo1XR") or "")
    ids = _csv(node.get("ElOXu3qi"))
    block = deepcopy(_store("comeback"))
    group = _mst("F_SG_COMEBACK_QUEST_GROUP_MST.ndjson", "MqUuo1XR").get(campaign)
    out = _out(spec, bbjE3Nwh=[])
    if (not group or not ids or str(block.get("campaign")) != campaign or not _writable(out)):
        return _refuse(out, "no active matching comeback campaign")
    masters = _mst("F_SG_COMEBACK_QUEST_MST.ndjson", "ElOXu3qi")
    grants, selected = [], []
    for qid in ids:
        row = masters.get(qid) or {}
        user = block.get("quests", {}).get(qid) or {}
        if str(user.get("6tSP4s8J")) == "3":
            selected.append(user)
            continue
        rewards = _reward_rows(row.get("dX6cor8j"))
        if (str(row.get("zF6QIY2r")) != str(group["zF6QIY2r"]) or
                str(user.get("6tSP4s8J")) != "2" or not rewards or
                _int(user.get("5rMfWv4X")) < _int(row.get("oz5Vt6AR"))):
            return _refuse(out, "comeback quest is not claimable or reward encoding unsupported")
        user.update({"9Tbns0eI": str(State.player.data["identity"]["user_id"]),
                     "MqUuo1XR": campaign, "zF6QIY2r": str(group["zF6QIY2r"]),
                     "ElOXu3qi": qid, "Pzn5h0Ga": str(row.get("Pzn5h0Ga") or ""), "6tSP4s8J": "3"})
        block["quests"][qid] = user
        grants.extend(rewards)
        selected.append(user)
    if grants:
        State.player._grant_items(grants)
        _put("comeback", block)
    return _out(_refresh(spec), bbjE3Nwh=selected)


def _panel_rewards(text):
    """A panel group's line/board reward, parsed like the panel quests' own rewards (`ffbe_player._quest_reward`):
    plain `kind:id[:count]` entries, and units with their extra fields (the 4-line Trust Moogle and the
    board-complete unit are `10:<id>:1:100:...`), which `_reward_rows` refuses."""
    from ffbe_player import _parse_reward
    from exvius_rewards import parse
    rows = []
    for entry in str(text or '').split(','):
        entry = entry.strip()
        if not entry:
            continue
        if len(entry.split(':')) == 2:
            rows.extend({'kind': k, 'id': i, 'count': c} for k, i, c in _parse_reward(entry))
        else:
            rows.extend(parse(entry))
    return rows


PANEL_LINES = ((1, 2, 3), (4, 5, 6), (7, 8, 9), (1, 4, 7), (2, 5, 8), (3, 6, 9), (1, 5, 9), (3, 5, 7))


def _panel_reached(gid):
    """{reward key: reached} for one panel group: `L<n>` and `COMPLETED`.

    `L<n>` is "Lines Completed: n" (PANEL_QUEST_LINE_COMPLETE_<n>): any n of the board's eight lines, not one
    particular line. Reading L1 as the top row refused a completed middle row (2026-11-06)."""
    from ffbe_player import _quest_index, player_progress
    quests = [q for q in _mst("F_PANEL_QUEST_MST.ndjson", "V36ygRYs").values()
              if str(q.get("zF6QIY2r")) == gid]
    index = _quest_index()
    cleared = {_int(q.get('Z0EN6jSh')) for q in quests
               if _int(q.get("oz5Vt6AR")) > 0 and
               player_progress(str(q["V36ygRYs"]), index.get(str(q["V36ygRYs"])) or {}) >= _int(q["oz5Vt6AR"])}
    lines = sum(all(p in cleared for p in line) for line in PANEL_LINES)
    reached = {f"L{n}": lines >= n for n in range(1, 9)}
    reached["COMPLETED"] = bool(quests) and len(cleared) == len(quests)
    return reached


def _panel_column(key):
    return "5e2xo65x" if key == "COMPLETED" else dict(zip((f"L{i}" for i in range(1, 9)), LINE_COLUMNS)).get(key)


def panel_extra_rows(picked=None):
    """`jksIZE9U` for the panel screen: one row per line/board reward the player has reached, claimed or not.

    The chest only claims when this row exists. `sgPanelQuestScene::checkExtraRewardOnTouched` (0x24c8400)
    looks up `getUserQuestExtraInfo(schedule, group, key)`: no row -> it opens the reward preview
    (`sgPanelQuestInfoScene`, 0x24c87c0); a row with `QCLs6SV8` = 1 -> nothing (already claimed); a row with
    0 -> it sends `sgPanelQuestExtraRewardRequest` (0x24c8724). The list is cleared by every reply that
    carries the tag (`onReadStarted` 0x19590c4), so every reply sends the full set."""
    from ffbe_player import panel_quest_picked
    claimed = _store("panel").get("claimed", {})
    rows = []
    for gid, grow in (panel_quest_picked() if picked is None else picked):
        schedule = str(grow.get("fK3W9qYA") or "")
        for key, reached in _panel_reached(gid).items():
            if not reached or not str(grow.get(_panel_column(key)) or "").strip():
                continue
            rows.append({"fK3W9qYA": schedule, "zF6QIY2r": gid, "xm7c08IS": key,
                         "QCLs6SV8": "1" if f"{schedule}:{gid}:{key}" in claimed else "0"})
    return rows


def panel_extra(spec, req):
    node = _node(req, "QxrSeO56") or {}
    schedule, gid, key = (str(node.get(k) or "") for k in ("fK3W9qYA", "zF6QIY2r", "xm7c08IS"))
    column = _panel_column(key)
    group = _mst("F_PANEL_QUEST_GROUP_MST.ndjson", "zF6QIY2r").get(gid) or {}
    out = _out(spec, jksIZE9U=panel_extra_rows())
    if not column or str(group.get("fK3W9qYA")) != schedule or not _writable(out):
        return _refuse(out, "unknown panel schedule/group/reward key")
    block = deepcopy(_store("panel"))
    claim_key = f"{schedule}:{gid}:{key}"
    reply = {"fK3W9qYA": schedule, "zF6QIY2r": gid, "xm7c08IS": key, "QCLs6SV8": "1"}
    if claim_key in block.get("claimed", {}):
        return _out(_refresh(spec), jksIZE9U=panel_extra_rows())
    if not _panel_reached(gid).get(key):
        return _refuse(out, "panel line or page is incomplete")
    rewards = _panel_rewards(group.get(column))
    if not rewards or not all(State.player._can_credit(row) for row in rewards):
        return _refuse(out, "panel reward encoding or reward kind unsupported")
    State.player._grant_items(rewards)
    block.setdefault("claimed", {})[claim_key] = reply
    _put("panel", block)
    return _out(_refresh(spec), jksIZE9U=panel_extra_rows())


def panel_status(spec, req):
    node = _node(req, "QxrSeO56") or {}
    sid = str(node.get("fK3W9qYA") or "")
    status = _store("panel").get("statuses", {}).get(sid)
    if not status:
        status = {"fK3W9qYA": sid, "es0Yun3Z": "0", "uX54AqwV": "0"}
    return _out(spec, UvwpPAtp=[status])


def extra_challenge_info(spec, req):
    node = _node(req, "vKmaUfYm") or {}
    progress = _store("extra_challenge").get("missions", {})
    masters = _mst("F_MISSION_MST.ndjson", "qo3PECw6")
    rows = []
    for mid in _csv(node.get("qo3PECw6")):
        if mid not in masters:
            _note("extra challenge: unknown mission " + mid)
            continue
        row = progress.get(mid, {})
        rows.append({"qo3PECw6": mid, **{k: str(row.get(k) or "") for k in
                     ("qdhWF7z9", "wf5Toh4k", "JJuN3uaH")}})
    return _out(spec, vKmaUfYm=rows)


def exbonus_update(spec, req):
    node = _node(req, "N7LA1tUj") or {}
    iid = str(node.get("og2GHy49") or "")
    unit = next((u for u in State.player.data["roster"] if str(u["instance_id"]) == iid), None)
    if not unit:
        return _refuse(spec, "EX-bonus target is not owned")
    groups = State.player.exbonus_groups()
    if not any(r['og2GHy49'] == iid for r in groups['5moIRSz6']):
        groups['5moIRSz6'].append({'og2GHy49': iid, 'upv38FtD': '1'})
    return _out(spec, **groups)


@_atomic
def exbonus_execute(spec, req):
    from exvius_actions_shops import _require, _pay
    node = _node(req, "Rv1YV69s") or {}
    iid = str(node.get("og2GHy49") or "")
    unit = next((u for u in State.player.data['roster'] if str(u['instance_id']) == iid), None)
    _require(unit is not None, 'EX-bonus target is not owned')
    count = _int(node.get('2RtVPS3b'))
    _require(count >= 1, 'invalid EX-bonus draw count')
    master = unit_mst(unit['master_id']) or {}
    _require(_int(master.get('JPW8Vs40')) > 0 and _int(unit.get('nv_ex_level')) >= 3,
             'EX bonuses require an EX+3 Neo Vision unit')
    # The shifted form uses its base form's series, as ExbonusUtil::getUnitSeries does.
    base = unit_mst(master.get('JPW8Vs40')) or master
    series = str(base.get('woghJa61') or master.get('woghJa61') or '')
    pieces = _mst('F_UNIT_SERIES_NV_PIECE_MST.ndjson', 'woghJa61').get(series)
    masters = list(_mst('F_UNIT_EX_BONUS_MST.ndjson', None).get('__rows__', []))
    candidates = [r for r in masters if str(r.get('woghJa61')) == series]
    _require(pieces and candidates, 'unit has no native EX-bonus definition')
    block = deepcopy(_store('exbonus'))
    user = block.setdefault('units', {}).setdefault(iid, {'step': 1, 'details': {}})
    remaining = sum(max(0, _int(r['es0Yun3Z']) - _int(user['details'].get(str(r['L3Nx1Jpb']))))
                    for r in candidates if _int(r['upv38FtD']) == user['step'])
    _require(count <= remaining, 'EX-bonus draw exceeds the remaining pool')
    selected = {}
    for _ in range(count):
        pool = [r for r in candidates if _int(r.get('upv38FtD')) == user['step']
                and _int(user['details'].get(str(r['L3Nx1Jpb']))) < _int(r['es0Yun3Z'])]
        _require(pool, 'all EX bonuses for this unit are already acquired')
        # xm7c08IS is the effect TYPE, not a probability. The native master
        # defines a finite box; each unacquired copy is one remaining result.
        weights = [_int(r['es0Yun3Z']) - _int(user['details'].get(str(r['L3Nx1Jpb']))) for r in pool]
        draw = secrets.randbelow(sum(weights))
        for row, weight in zip(pool, weights):
            draw -= weight
            if draw < 0:
                bid = str(row['L3Nx1Jpb'])
                user['details'][bid] = _int(user['details'].get(bid)) + 1
                selected[bid] = selected.get(bid, 0) + 1
                break
        current = [r for r in candidates if _int(r['upv38FtD']) == user['step']]
        if all(_int(user['details'].get(str(r['L3Nx1Jpb']))) >= _int(r['es0Yun3Z']) for r in current):
            later = [_int(r['upv38FtD']) for r in candidates if _int(r['upv38FtD']) > user['step']]
            if later:
                user['step'] = min(later)
    _pay([{'kind': 20, 'id': int(pieces['tL6G9egd']), 'count': count * 5}])
    _put('exbonus', block)
    from player_state import exbonus_status_bonus
    unit['exbonus_stats'] = exbonus_status_bonus(unit['master_id'], user['details'])
    out = exbonus_update(_refresh(spec), {'N7LA1tUj': [{'og2GHy49': iid}]})
    return _out(out, Rv1YV69s=[{'og2GHy49': iid, '2RtVPS3b': str(count),
                              'UJz5QED2': ','.join(f'{bid}:{n}' for bid, n in selected.items())}])


def _slot_key(node):
    return f"{node.get('o0T4S52k', '0')}:{node.get('YLi31qam', '0')}"


def _slot_row(slot):
    row = {k: str(slot.get(k) or "") for k in SLOT_FIELDS if k not in ("2A6fYiEC", "xBi3L6yR", "Na7YM2v4")}
    row["52W9gGbR"] = str(slot.get("2A6fYiEC") or "")
    return row


def _retain_owned_equipment():
    owned = State.player.equip_item_rows()
    equipment = State.player.data['inventory'].setdefault('equipment', [])
    by_id = {str(e['item_id']): e for e in equipment}
    for row in owned:
        iid, count = row['J1YX9kmM'], int(row['Qy5EvcK1'])
        if iid in by_id:
            by_id[iid]['count'] = max(int(by_id[iid].get('count', 0)), count)
        else:
            equipment.append({'item_id': int(iid), 'count': count})
    return owned


def _wire_loadouts(slot, members, slots=5):
    """Decode the original save-slot strings, including both unit forms."""
    loadouts = {}
    for token, fields, size in [('93Y6evuT', ('equipment', 'shift_equipment'), 6),
                                ('80NUYFMJ', ('materia', 'shift_materia'), 4)]:
        for entry in filter(None, str(slot.get(token) or '').split(',')):
            iid, raw = entry.split(':', 1)
            if iid not in members:
                raise ValueError('saved loadout unit is not in party')
            forms = raw.split('|')
            if len(forms) > 2:
                raise ValueError('too many unit forms')
            for field, form in zip(fields, forms):
                values = {str(n): '0' for n in range(1, size + 1)}
                seen = set()
                for pair in filter(None, form.split('@')):
                    position, item = pair.split('-', 1)
                    if position not in values or position in seen or not item.isdigit():
                        raise ValueError('invalid saved equipment slot')
                    seen.add(position)
                    values[position] = item
                loadouts.setdefault(iid, {})[field] = values if size == 6 else list(values.values())
    for token, field in [('w1JG7i9j', 'brave_shift'), ('2c8nqLrM', 'skin_id')]:
        for entry in filter(None, str(slot.get(token) or '').split(',')):
            iid, value = entry.split(':', 1)
            if iid not in members or not value.isdigit():
                raise ValueError('invalid saved unit property')
            loadouts.setdefault(iid, {})[field] = int(value)
    for entry in filter(None, str(slot.get('nQ1iAGf3') or '').split(',')):
        iid, raw = entry.split(':', 1)
        forms = raw.split('|')
        if iid not in members or len(forms) > 2 or any(not re.fullmatch(r'[0-9-]+', v) for v in forms):
            raise ValueError('invalid saved vision card')
        for field, card in zip(('vision_card', 'shift_vision_card'), forms):
            # Store the owned card's user_vc_id; the wire carries it as "0-<id>" ("0-0" = none).
            loadouts.setdefault(iid, {})[field] = vision_card_key(card)
    espers = [0] * slots
    for entry in filter(None, str(slot.get('XZ4Kh7Ic') or '').split(',')):
        position, value = entry.split(':', 1)
        if not position.isdigit() or not 0 <= int(position) < slots or not value.isdigit():
            raise ValueError('invalid saved esper')
        espers[int(position)] = int(value)
    return loadouts, espers


def party_save(spec, req):
    node = _node(req, SLOT)
    if (not node or _int(node.get("YLi31qam"), -1) < 0 or
            _int(node.get("o0T4S52k"), -1) < 0 or not _writable(spec)):
        return _refuse(spec, "invalid party slot")
    slot = {k: str(node.get(k, "")) for k in SLOT_FIELDS}
    kind = {'7': '7', '8': '8', '11': '11', '50': '11'}.get(str(node.get('xBi3L6yR', '1')))
    party = State.player.special_party(kind) if kind else State.player.data['party']
    size = 6 if kind else 5
    roster = {str(u['instance_id']): u for u in State.player.data['roster']}
    members = [p.split(':') for p in slot['2A6fYiEC'].split(',') if p]
    if (not 1 <= len(members) <= size or any(len(p) != 3 or p[0] not in ('0', '1')
            or not p[1].isdigit() or not 0 <= int(p[1]) < size or p[2] not in roster for p in members)
            or len({p[1] for p in members}) != len(members)
            or len({p[2] for p in members}) != len(members)):
        return _refuse(spec, 'invalid saved party members')
    # Keep the native strings for the original slot reader, and retain the
    # authoritative assignments alongside them for actual server-side loading.
    fields = ('equipment', 'materia', 'vision_card', 'skin', 'skin_id',
              'brave_shift', 'shift_equipment', 'shift_materia', 'shift_vision_card')
    slot['loadouts'] = {p[2]: {k: deepcopy(roster[p[2]].get(k)) for k in fields
                              if k in roster[p[2]]} for p in members}
    try:
        decoded, espers = _wire_loadouts(slot, slot['loadouts'], size)
    except (ValueError, TypeError):
        return _refuse(spec, 'invalid saved loadout')
    for iid, values in decoded.items():
        slot['loadouts'][iid].update(values)
    did = str(node.get('r21y0YzS', party['active_deck']))
    beast_decks = party.get('beast_decks', {}) if kind else State.player.data.get('beast_decks', {})
    slot['espers'] = espers if slot['XZ4Kh7Ic'] else deepcopy(beast_decks.get(did, [0] * size))
    block = deepcopy(_store("party_register"))
    _retain_owned_equipment()
    block.setdefault("slots", {})[_slot_key(slot)] = slot
    _put("party_register", block)
    return _out(spec, **{"0wV1vDmK": [_slot_row(slot)]})


def party_update(spec, req):
    node = _node(req, SLOT) or {}
    block = deepcopy(_store('party_register'))
    if not node or not _writable(spec):
        return _out(spec, dEA91X0o=[_slot_row(s) for s in block.get('slots', {}).values()])
    # Equipment growth does not change an item's master identity. Keep the
    # saved assignment while updating the native growing-item reference.
    for slot in block.get('slots', {}).values():
        if node.get('Na7YM2v4'):
            slot['Na7YM2v4'] = str(node['Na7YM2v4'])
    _put('party_register', block)
    return _out(spec, dEA91X0o=[_slot_row(s) for s in block.get('slots', {}).values()])


def party_load(spec, req):
    node = _node(req, SLOT) or {}
    slot = _store("party_register").get("slots", {}).get(_slot_key(node))
    if not slot or not _writable(spec):
        return _refuse(spec, "party slot not found")
    kind = {'7': '7', '8': '8', '11': '11', '50': '11'}.get(str(node.get('xBi3L6yR', '1')))
    party = State.player.special_party(kind) if kind else State.player.data['party']
    size = 6 if kind else 5
    roster = {str(u["instance_id"]): u for u in State.player.data["roster"]}
    pairs = [p.split(":") for p in str(slot.get("2A6fYiEC") or "").split(",") if p]
    shifts = [p.split(":") for p in str(slot.get("w1JG7i9j") or "").split(",") if p]
    if (not 1 <= len(pairs) <= size or any(len(p) != 3 or p[0] not in ("0", "1") or
            not p[1].isdigit() or not 0 <= int(p[1]) < size or p[2] not in roster for p in pairs) or
            len({p[1] for p in pairs}) != len(pairs) or len({p[2] for p in pairs}) != len(pairs) or
            any(len(p) != 2 or p[0] not in roster or not p[1].isdigit() for p in shifts)):
        return _refuse(spec, "party load refused: unknown units, duplicate positions or shifted forms")
    did = str(node.get("r21y0YzS", "0"))
    deck = next((d for d in party['decks'] if str(d['id']) == did), None)
    if deck is None:
        return _refuse(spec, "unknown destination party deck")
    try:
        decoded, wire_espers = _wire_loadouts(slot, {p[2] for p in pairs}, size)
    except (ValueError, TypeError):
        return _refuse(spec, 'invalid saved loadout')
    # Some old saves represent ownership only through equipped references. Retain
    # those copies in the established inventory before clearing any assignments.
    owned = _retain_owned_equipment()
    deck["members"] = [{"member_type": int(t), "disp_order": int(p), "instance_id": iid} for t, p, iid in pairs]
    party['active_deck'] = int(did)
    if kind == '11':
        State.player.set_active_deck(did)
    espers = deepcopy(slot.get('espers', wire_espers))
    beast_owner = party if kind else State.player.data
    beast_owner.setdefault('beast_decks', {})[did] = [e if not e or State.player.owns_beast(e) else 0 for e in espers]
    for _, _, iid in pairs:
        saved = slot.get('loadouts', {}).get(iid)
        if saved is not None:
            roster[iid].update(deepcopy(saved))
        else:
            roster[iid].update(deepcopy(decoded.get(iid, {})))
    # Restore only copies that still exist. Prioritize the loaded members and
    # remove conflicting assignments from other units rather than minting gear.
    gear_left = Counter({r['J1YX9kmM']: int(r['Qy5EvcK1']) for r in owned})
    materia_left = Counter({r['H5jBL0Vf']: int(r['Qy5EvcK1']) for r in State.player.materia_rows()})
    cards_left = {str(c['user_vc_id']) for c in State.player.data.get('vision_cards', [])}
    selected = [p[2] for p in pairs]
    order = selected + [iid for iid in roster if iid not in selected]
    for iid in order:
        unit = roster[iid]
        used_gear, used_materia, used_cards = Counter(), Counter(), set()
        for field in ('equipment', 'shift_equipment'):
            counts = Counter()
            clean = {}
            for position, item in (unit.get(field) or {}).items():
                item = str(item)
                counts[item] += 1
                # The same unit's two forms may share owned equipment copies.
                if item != '0' and counts[item] <= gear_left[item] + used_gear[item]:
                    clean[position] = item
                else:
                    clean[position] = '0'
            unit[field] = clean
            needed = Counter(clean.values())
            for item, count in needed.items():
                if item == '0':
                    continue
                extra = max(0, count - used_gear[item])
                gear_left[item] -= extra
                used_gear[item] += extra
        for field in ('materia', 'shift_materia'):
            clean, counts = [], Counter()
            for item in unit.get(field) or []:
                item = str(item)
                counts[item] += 1
                clean.append(item if item != '0' and counts[item] <= materia_left[item] + used_materia[item] else '0')
            unit[field] = clean
            for item, count in Counter(clean).items():
                if item != '0':
                    extra = max(0, count - used_materia[item])
                    materia_left[item] -= extra
                    used_materia[item] += extra
        for field in ('vision_card', 'shift_vision_card'):
            card = vision_card_key(unit.get(field))   # also older saves' "0-<id>" values
            unit[field] = card if card in cards_left or card in used_cards else ''
            if unit[field]:
                cards_left.discard(card)
                used_cards.add(card)
    block = deepcopy(_store("party_register"))
    block["last_load"] = {"slot": _slot_key(node), "deck": did, "party_type": kind or '1'}
    _put("party_register", block)
    return _out(_refresh(spec), **{"0wV1vDmK": [_slot_row(slot)]})


HANDLERS = {
    "hW0804Q9": expedition_info,
    "Ik142Ff6": expedition_accelerate, "2pe3Xa8b": expedition_end,
    "r4A791RF": milestone_claim, "vTgYyHM6": expedition_refresh,
    "I8uq68c3": expedition_start, "0Fb87D0F": expedition_recall,
    "D9xphQ8X": challenge_clear, "nQMb2L4h": dungeon_liberation,
    "Tvq54dx6": mission_switch_update, "j5JHKq6S": mission_update,
    "G1hQM8Dr": mission_update,
    "29JRaDbd": quest_steps, "x5Unqg2d": quest_steps, "sJcMPy04": quest_steps,   # MissionStart, MissionEnd, TownOut
    "1IOdaWOW": comeback_claim, "AOY6npa3": panel_extra, "egJpaGtk": panel_status,
    "LJhqu0x6": mission_unlock, "dzU2t3HA": extra_challenge_info,
    "68RQ9GwN": exbonus_execute, "HaJp14F6": exbonus_update,
    "Q7jV6pno": party_load, "CE98eghN": party_save, "RQ5BjDE0": party_update,
}
