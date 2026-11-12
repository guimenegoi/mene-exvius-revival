"""Offline special-mode actions for Global v9.

The original native request and response codecs come from the pinned game
library. Mission settlement reuses normal loot, XP, challenge and retry ledgers.
Tower and RM progress follow shipped mission order. Survival retains witnessed
wave counts. Parade retains best stage scores and published milestone rewards.
Personal Glory and Clash of Wills scores use local
clear/damage/gimmick formulas because the retired backend score policies are
unavailable. No remote competitors or retail score accuracy are claimed.

Clash of Wills creates and persists Fortuna choices from published original
base rates. Four provisional slots can be replaced and collected once. Each
season retains its own progress and rewards. Bonus previews use native scaled
multipliers. Evergreen archive windows and per-clear local scores are offline
policies. Native endpoints have no universal run nonce, so delayed identical
End requests cannot be distinguished from a subsequent replay without a new
mission load. A load arms exactly one settlement.
"""
from copy import deepcopy
from functools import wraps
import json
import re
import secrets

from exvius_actions import _node, _refresh, _mst, _parse_rewards
from ffbe_state import State, _note

AUTHORED_RUNNING_STATE = "1"
AUTHORED_WINDOW = ("1577836800", "4102444800")  # Same offline window as serve_survival.
AUTHORED_TOWER_PROGRESS = "cleared_floor_count"
AUTHORED_TFA_FINISH_EMPTY = True
AUTHORED_NOTICE_CSV = True
AUTHORED_HELPER_POINTS = 10  # Normal MissionStart fallback at 0x19a88a0; no EventSetMst is shipped.
GLORY_MAGIC_KEY = "106100100"  # Client 0x21ca7c0: kind 20, quantity 1, F_ITEM_MST key.

MODE = {"tower": "9", "parade": "12", "rm": "12", "survival": "13", "glory": "14", "tfa": "50"}
TAGS = {
    "tower": ("MAq9rRd2", "61zcgy04", "56TsktBX"),
    "glory": ("auE57zyr", "dekE2X8K", "4FhDP05Q", "C9g3yKDL"),
    "survival": ("65cMLkuQ", "2w9Iyeaq"),
    "parade": ("gXrD1h58", "yA8Nn9vK", "94IYZAbg", "HMa5VTU8", "sMPhc96i", "EYa5g4wh"),
    "rm": ("Q4kJKh8b", "Wmr7y9a0", "jSC4Tx9H", "Ur6CKS2e"),
    "tfa": ("L6XRZb0z", "x51bb135", "Fs0sexp7", "AJb8pF71", "XHnyfiwg", "cBHNnXQZ"),
}
RM_SNAPSHOT = ("r21y0YzS", "h0XJ2nPj", "1w6Ju7Ie", "0VBhN1UC", "Zh73m5Nq", "Y3oqiA8S", "PH7Hg4Zh")


class _Refused(ValueError):
    pass


def _need(ok, reason):
    if not ok:
        raise _Refused(reason)


def _number(value):
    _need(not isinstance(value, bool) and bool(re.fullmatch(r"\d+", str(value))), "invalid unsigned integer")
    return int(value)


def _csv(value):
    if not value:
        return []
    parts = str(value).split(",")
    _need(all(p.isdigit() for p in parts) and len(parts) == len(set(parts)), "invalid ID CSV")
    return parts


def _handler(fn):
    """Rollback a refused action, including partial grants, without ever saving to disk."""
    @wraps(fn)
    def call(spec, req):
        player = State.player
        if player is None:
            _note(f"{fn.__name__}: no player")
            return spec
        before, dirty = deepcopy(player.data), player.dirty
        try:
            _need(isinstance(req, dict), "request must be an object")
            return fn(dict(spec or {}), req)
        except _Refused as exc:
            player.data.clear()
            player.data.update(before)
            player.dirty = dirty
            _note(f"{fn.__name__}: refused: {exc}")
            return spec
        except Exception:
            player.data.clear()
            player.data.update(before)
            player.dirty = dirty
            raise
    return call


def _feature(name, spec):
    f = deepcopy(State.player.data.get("exvius_" + name, {}))
    groups = f.setdefault("groups", {})
    for tag in TAGS[name]:
        if tag not in groups and isinstance(spec.get(tag), list):
            _need(all(isinstance(r, dict) for r in spec[tag]), "malformed default reply group")
            groups[tag] = deepcopy(spec[tag])
    return f


def _save(name, f):
    _need(State.player.mode != "frozen", "player is frozen")
    State.player.data["exvius_" + name] = f
    State.player.dirty = True


def _reply(spec, f, tags):
    out = dict(spec)
    for tag in tags:
        if tag in f["groups"]:
            out[tag] = deepcopy(f["groups"][tag])
    return out


def _missions(name, dungeon=None):
    return sorted((r for r in _mst("F_MISSION_MST.ndjson", "qo3PECw6").values()
                   if str(r.get("gQR24kST")) == MODE[name]
                   and (dungeon is None or str(r.get("U9iHsau3")) == str(dungeon))),
                  key=lambda r: (_number(r["Z0EN6jSh"]), _number(r["qo3PECw6"])))


def _mission(name, mid):
    row = _mst("F_MISSION_MST.ndjson", "qo3PECw6").get(str(mid))
    _need(row and (name not in MODE or str(row.get("gQR24kST")) == MODE[name]), "mission is not in this mode")
    return row


def _cost(row, op):
    _need(str(op.get('5qjK76ni') or '0') in ('0', '1'), 'invalid half-cost flag')
    amount, kind = _number(row["B6kyCQ9M"]), str(row["CQN15Hgr"])
    if not amount:
        return 0
    if kind not in ("1", "2"):
        define = _mst("F_DEFINE_MST.ndjson", "AK8Nn7ta").get("DUNGEON_NO_COST_LV")
        _need(define is not None, "DUNGEON_NO_COST_LV is missing")
        if int(State.player.data["rank"]["level"]) < _number(define["YjIUDJ97"]):
            return 0
    _need(kind in ('0', '1', '2', '6', '50'), 'unknown mission point account')
    # Orb accounts are separate from stamina and never receive the rank waiver.
    if kind != '0':
        return 0
    return (amount + 1) // 2 if str(op.get('5qjK76ni', '0')) == '1' else amount


def _helper(op):
    from ffbe_friends import all_friends as load_friends
    fri, guest = str(op.get("dUX7Pt5i") or ""), str(op.get("w40YsHIz") or "")
    _need(not (fri and guest), "two selected helpers")
    helper = fri or guest
    if helper:
        friend = next((f for f in load_friends() if str(f["friend_id"]) == helper), None)
        _need(friend is not None, "helper is not in the offline friend roster")
        _need(str(op.get("qLke7K8f") or "") == str(friend["unit"]["master_id"]), "helper master ID mismatch")
    own = str(op.get("ATkxpa3b") or "")
    if own:
        _need(any(str(u["instance_id"]) == own for u in State.player.data["roster"]), "own helper is not owned")
    # Never trust a client-supplied award or reinterpret it as a cost.
    _number(op.get("0XUs3Tv6", 0))
    return helper


def _seeds(op):
    sent = str(op.get("b6PwoB37") or "").split(",") if op.get("b6PwoB37") else []
    _need(len(sent) <= 4 and all(s.isdigit() and int(s) < 2**32 for s in sent), "invalid mission RNG seeds")
    seeds = [int(s) for s in sent] + [0] * (4 - len(sent))
    return ",".join(str(s or secrets.randbelow(2**32 - 1) + 1) for s in seeds)


def _begin(name, f, row, op, extra=None):
    mid = str(row["qo3PECw6"])
    active = f.get("active")
    if active:
        _need(active["mission"] == mid, "another mission is already active")
        return active
    _need(State.player.mode != "frozen", "player is frozen")
    for other in TAGS:
        if other != name:
            _need(not State.player.data.get("exvius_" + other, {}).get("active"), "another mode has an active mission")
    if op.get('J1YX9kmM'):
        _need(str(op['J1YX9kmM']) in _mst('F_EQUIP_ITEM_MST.ndjson', 'J1YX9kmM'), 'unknown mission equipment')
    cost = _cost(row, op)
    helper = _helper(op)
    rank = State.player.data["rank"]
    _need(int(rank["nrg"]) >= cost, "insufficient stamina")
    rank["nrg"] -= cost
    family = {'1': 'clsm', '2': 'event', '6': 'equip_grow', '50': 'tfa'}.get(str(row['CQN15Hgr']))
    if family and int(row.get('B6kyCQ9M', 0)):
        _need(State.player.spend_orbs(family, int(row['B6kyCQ9M'])), 'insufficient mission orbs')
    if helper and name in ("glory", "survival"):
        defines = _mst("F_DEFINE_MST.ndjson", "AK8Nn7ta")
        threshold = _number(defines["DUNGEON_NO_COST_LV"]["YjIUDJ97"])
        cap = _number(defines["FRIEND_POINT_POSSESSION_LIMIT"]["YjIUDJ97"])
        if int(rank["level"]) >= threshold:
            amount = min(AUTHORED_HELPER_POINTS, max(0, cap - int(State.player.data["currencies"]["friend_point"])))
            State.player.add_currency("friend_point", amount)
    elif helper and name == 'rm':
        State.player.add_currency('friend_point', AUTHORED_HELPER_POINTS)
    f["sequence"] = int(f.get("sequence", 0)) + 1
    active = {"mission": mid, "dungeon": str(row["U9iHsau3"]), "area": str(row["uv60hgDW"]),
              "sequence": f["sequence"], "helper": helper, "operation": deepcopy(op),
              "seeds": _seeds(op if name == "rm" else {}),
              "carry": deepcopy(State.player.data["inventory"]["carry_items"])}
    active.update(extra or {})
    from exvius_repeat import begin_attempt
    begin_attempt(State.player, mid)
    f.update(active=active, mission=mid, dungeon=active["dungeon"], area=active["area"])
    return active


def _resume(f, rm=False):
    run = f.get("active")
    row = {"qo3PECw6": run["mission"] if run else "0", "LJas52VE": AUTHORED_RUNNING_STATE if run else "0",
           "8prQv5nz": "0"}
    if rm:
        row.update(uv60hgDW=f.get("area", "0"), U9iHsau3=f.get("dungeon", "0"),
                   dUX7Pt5i=run.get("helper", "") if run else "")
    else:
        row.update(Gh92V3Tx="0", YJah04ud="0", PMp0Af1d="0", **{"6VA3jNPn": run.get("helper", "") if run else ""})
        for token in ("ATkxpa3b", "s654exed", "7RvvpruU"):
            row[token] = str(run["operation"].get(token) or "") if run else ""
    return [row]


def _rng(f):
    run = f["active"]
    return [{"b6PwoB37": run["seeds"], **{k: str(run["operation"].get(k) or "") for k in ("ATkxpa3b", "s654exed")}}]


def _carry(f, req):
    """The item set left after the battle (carry_report.apply, 2026-11-12): each slot keeps the smaller of its
    saved and reported count and the bag loses the difference. Until then this compared the report with the set
    saved at the run's start, so a Potion a field use had already taken was taken again, and a report that
    raised a count refused the whole battle end."""
    import carry_report
    carry_report.apply(State.player, req)


def _carry_reply(out):
    rows = sorted(State.player.data["inventory"]["carry_items"], key=lambda r: int(r["disp_order"]))
    out["nE7pV2wr"] = [{"jsvoa0I2": ",".join(f"{r['disp_order']}:{r['item_id']}:{r['count']}" for r in rows)}]


def _switches(op, retire=False):
    switches = _mst("F_SWITCH_MST.ndjson", "8vAYn3IX")
    types = _mst("F_SWITCH_TYPE_MST.ndjson", "5opcUT9t")
    for sid in _csv(op.get("dIPkNn61")):
        row = switches.get(sid)
        _need(row is not None, "unknown uploaded switch")
        typ = str(row["5opcUT9t"])
        allowed = typ in ("104", "204") if retire else str(types.get(typ, {}).get("2n9Zm8FG")) == "0"
        _need(allowed, "uploaded switch is outside the client-managed filter")
        State.player.data["progress"]["switches"].setdefault(typ, set()).add(_number(row["QLfe23bu"]))


def _grant(rewards):
    for row in rewards:
        table = {10: ("F_UNIT_MST.ndjson", "3HriTp6B"), 20: ("F_ITEM_MST.ndjson", "tL6G9egd"),
                 23: ("F_IMPORTANT_ITEM_MST.ndjson", "2dfixko3")}.get(row["kind"])
        if table:
            _need(str(row["id"]) in _mst(*table), "reward master is missing")
    granted = State.player._grant_items(rewards)
    _need(granted == rewards, "reward kind/master is not supported by PlayerState projection")


def _challenges(mid, run, req, base_result=None):
    from ffbe_battle import CONDITION_CHECKS, mission_result_from
    meta, tail = _node(req, "2urzfX6d") or {}, _node(req, "L4i4418y") or {}
    clear = [s for s in str(meta.get("69ieJGhD") or "").split(",") if s]
    _need(bool(clear), "no witnessed battle-clear log; active mission retained")
    turns = [s.split(":") for s in clear]
    party = State.player.battle_party(mid)
    members = next((d['members'] for d in party['decks']
                    if str(d['id']) == str(party['active_deck'])), [])
    ctx = mission_result_from(json.dumps(req))
    ctx['party_size'] = len(members) + bool(run.get('helper'))
    if run.get('helper'):
        from ffbe_friends import all_friends as load_friends
        friend = next((f for f in load_friends() if str(f['friend_id']) == str(run['helper'])), None)
        if friend:
            ctx['helper_master'] = str(friend['unit']['master_id'])
    progress = State.player.data["progress"]
    cleared = progress["cleared_challenges"].setdefault(mid, set())
    paid = progress["paid_challenges"].setdefault(mid, set())
    rewards, fresh = [], []
    clash = str(_mst('F_MISSION_MST.ndjson', 'qo3PECw6').get(mid, {}).get('gQR24kST')) == '50'
    challenge_rows = [] if clash else _mst("F_CHALLENGE_MST.ndjson", None).get("__rows__", [])
    for row in challenge_rows:
        if str(row.get("qo3PECw6")) != mid:
            continue
        cid = str(row["V36ygRYs"])
        cond, _, param = str(row.get("Pzn5h0Ga") or "").partition(":")
        check = CONDITION_CHECKS.get(cond)
        if cid in paid:
            continue
        if check is None or check(ctx, param) is not True:
            _note(f"modes: challenge {cid} not witnessed; no reward")
            continue
        text = str(row.get("dX6cor8j") or "")
        from exvius_rewards import parse
        try:
            parsed = parse(text)
        except ValueError as exc:
            raise _Refused(str(exc)) from exc
        _grant(parsed)
        rewards.extend(parsed)
        fresh.append(cid)
        cleared.add(cid)
        paid.add(cid)
    if mid not in progress["cleared_missions"]:
        progress["cleared_missions"].append(mid)
    result = deepcopy((base_result or [{}])[0])
    result.setdefault('kcb0tsM6', '0')
    result.setdefault('16LQuC5r', '0')
    if rewards:
        result["REB5tAL9"] = __import__('exvius_rewards').reward_text(rewards)
    if fresh:
        result["qdhWF7z9"] = ",".join(fresh)
    return [result]


def _finish(name, f, req, switches=True, spec=None):
    op = _node(req, "jQsE54Iz") or {}
    mid = str(op.get("qo3PECw6") or "")
    run = f.get("active")
    if not run:
        last = f.get("last_end")
        _need(last and last["mission"] == mid, "no matching active mission")
        return False
    _need(run["mission"] == mid, "mission does not match the active session")
    _mission(name, mid)
    from ffbe_battle import mission_end_echo, credit_mission_rewards, grant_cleared_mission
    # Use the normal game's settlement ledger. The pipeline may have already
    # credited this attempt, in which case this call preserves the result only.
    result_spec = mission_end_echo(deepcopy(spec or {'09HRWXDf': [{}]}), json.dumps(req))
    result_spec.setdefault('09HRWXDf', [{}])
    result_spec = credit_mission_rewards(json.dumps(req), result_spec)
    from exvius_repeat import repeat_challenge_rewards
    result_spec = repeat_challenge_rewards(result_spec, mid, json.dumps(req))
    from first_clear import pay as pay_first_clear
    result_spec = pay_first_clear(result_spec, mid, json.dumps(req))
    from ffbe_player import score_completed_quest_mission
    score_completed_quest_mission(json.dumps(req))
    result = _challenges(mid, run, req, result_spec['09HRWXDf'])
    # These mode handlers run after the normal pipeline's clear step. Publish
    # the same validated mission switches when this handler creates the result.
    grant_cleared_mission({'09HRWXDf': result}, mid, json.dumps(req))
    if name != "tower":
        _carry(f, req)
    if switches:
        _switches(op, retire=name in ("glory", "rm"))
    f.setdefault("settled", []).append({"sequence": run["sequence"], "mission": mid})
    f["last_end"] = {"mission": mid, "sequence": run['sequence'], "result": result, "upload": deepcopy(req)}
    f["active"] = None
    return True


def _event(area):
    return {"uv60hgDW": str(area), "VjJQ51uG": AUTHORED_WINDOW[0], "m8ivD4NX": AUTHORED_WINDOW[1]}


def _tower(f):
    rows = _missions("tower")
    _need(bool(rows), "Tower mission masters are missing")
    first = rows[0]
    old = (f["groups"].get("61zcgy04") or [{}])[0]
    f.setdefault("area", str(old.get("uv60hgDW", first["uv60hgDW"])))
    f.setdefault("dungeon", str(old.get("U9iHsau3", first["U9iHsau3"])))
    f.setdefault("mission", str(old.get("qo3PECw6", first["qo3PECw6"])))
    f.setdefault("progress", _number(old.get("5rMfWv4X", 0)))
    f["groups"].setdefault("MAq9rRd2", [_event(f["area"])])
    if "56TsktBX" not in f["groups"]:
        f["groups"]["56TsktBX"] = [{"r21y0YzS": str(d["id"]), "G4L0YIB2": d["name"],
            "2A6fYiEC": ",".join(f"{m['member_type']}:{m['disp_order']}:{m['instance_id']}" for m in d["members"])}
            for d in State.player.data["party"]["decks"]]
    f["groups"]["61zcgy04"] = [{"uv60hgDW": f["area"], "U9iHsau3": f["dungeon"],
        "qo3PECw6": f["mission"], "5rMfWv4X": str(f["progress"])}]


@_handler
def tower_entry(spec, req):
    f = _feature("tower", spec)
    _tower(f)
    _save("tower", f)
    return _reply(spec, f, TAGS["tower"])


def _start(name, spec, req):
    f = _feature(name, spec)
    op = _node(req, "jQsE54Iz") or {}
    row = _mission(name, op.get("qo3PECw6"))
    if name == "tower":
        _tower(f)
        _need(str(row["qo3PECw6"]) == f["mission"], "Tower floor is not the saved next floor")
    _begin(name, f, row, op)
    if name == "tower":
        _tower(f)
        tags = ("61zcgy04",)
    else:
        _survival(f)
        tags = TAGS["survival"]
    _save(name, f)
    out = _refresh(_reply(spec, f, tags))
    out.update({"1Ke2wFgm": _resume(f), "jQsE54Iz": _rng(f)})
    return out


@_handler
def tower_start(spec, req):
    return _start("tower", spec, req)


@_handler
def tower_end(spec, req):
    f = _feature("tower", spec)
    if _finish("tower", f, req, spec=spec):
        mid = f["last_end"]["mission"]
        f.setdefault("cleared", [])
        if mid not in f["cleared"]:
            f["cleared"].append(mid)
            f["progress"] += 1
        rows = _missions("tower", f["dungeon"])
        pos = next(i for i, row in enumerate(rows) if str(row["qo3PECw6"]) == mid)
        f["mission"] = str(rows[pos + 1]["qo3PECw6"]) if pos + 1 < len(rows) else "0"
        _tower(f)
        _save("tower", f)
    out = _refresh(_reply(spec, f, ("61zcgy04", "56TsktBX")))
    out["09HRWXDf"] = deepcopy(f["last_end"]["result"])
    return out


def _restart(name, spec, req):
    f = _feature(name, spec)
    op = _node(req, "jQsE54Iz") or {}
    _need(f.get("active") and str(op.get("qo3PECw6")) == f["active"]["mission"], "no matching saved session")
    tags = {"tower": ("61zcgy04",), "glory": (), "survival": TAGS["survival"], "rm": TAGS["rm"]}[name]
    out = _reply(spec, f, tags)
    out["Ur6CKS2e" if name == "rm" else "1Ke2wFgm"] = _resume(f, name == "rm")
    out["jQsE54Iz"] = _rng(f)
    if name == "glory":
        out["aGPc06ym"] = _glory_selection(f)
    return out


@_handler
def tower_restart(spec, req):
    return _restart("tower", spec, req)


def _retire(name, spec, req):
    f = _feature(name, spec)
    op = _node(req, "jQsE54Iz") or {}
    mid = str(op.get("qo3PECw6") or "")
    if not f.get("active"):
        _need(f.get("retired") == mid, "no matching active mission")
    else:
        _need(mid == f["active"]["mission"], "retire mission mismatch")
        if name != "tower":
            _carry(f, req)
        _switches(op, retire=True)
        if name == "rm":
            _rm_snapshot(f, req)
            f["run"] = False
        f.update(active=None, retired=mid)
        _save(name, f)
    tags = {"tower": ("61zcgy04",), "survival": ("65cMLkuQ",), "rm": TAGS["rm"]}[name]
    out = _reply(spec, f, tags)
    out["Ur6CKS2e" if name == "rm" else "1Ke2wFgm"] = _resume(f, name == "rm")
    if name != "tower":
        out = _refresh(out)
        _carry_reply(out)
    return out


@_handler
def tower_retire(spec, req):
    return _retire("tower", spec, req)


def _glory(f, area=None):
    joins = _mst("F_GLORY_MISSION_MST.ndjson", None).get("__rows__", [])
    if area is not None:
        matches = [r for r in joins if str(_mission("glory", r["qo3PECw6"])["uv60hgDW"]) == str(area)]
        _need(bool(matches), "area has no shipped Glory event")
        f["event"] = str(matches[0]["pvS5A4kE"])
        f["area"] = str(area)
    _need(f.get("event"), "Glory entry is required first")
    event = _mst("F_SEASON_EVENT_GLORY_MST.ndjson", "pvS5A4kE").get(f["event"])
    _need(event is not None, "Glory event master is missing")
    groups = [r for r in _mst("F_GLORY_GIMMICK_GROUP_MST.ndjson", None).get("__rows__", [])
              if str(r["Z20PuxDY"]) == str(event["Z20PuxDY"])]
    user = next((r for r in f["groups"].get("dekE2X8K", []) if str(r.get("pvS5A4kE")) == f["event"]), None)
    if user is None:
        user = {"pvS5A4kE": f["event"], "UbQ26oH4": "0", "5oPuXx1a": "0", "E5R3sMfb": "0",
                "D2gU5tET": "", "Vm07pZ2A": "", "C15d9FDP": "", "9B0KHFpJ": "0"}
        f["groups"].setdefault("dekE2X8K", []).append(user)
    unlocked = _csv(user.get("D2gU5tET"))
    for g in groups:
        if str(g["59kRbpKz"]) == "0" and str(g["M3JE6vnF"]) not in unlocked:
            unlocked.append(str(g["M3JE6vnF"]))
    user["D2gU5tET"] = ",".join(unlocked)
    f["groups"].setdefault("auE57zyr", [_event(f["area"])])
    f["groups"].setdefault("4FhDP05Q", [])
    f["groups"].setdefault("C9g3yKDL", [])
    return groups, user


@_handler
def glory_entry(spec, req):
    f = _feature("glory", spec)
    _glory(f, (_node(req, "V3oXMq9f") or {}).get("uv60hgDW"))
    _save("glory", f)
    return _reply(spec, f, TAGS["glory"])


def _glory_selection(f):
    run = f["active"]
    return [{"51xkq83U": run["gimmicks"], "U92bySoZ": "1" if run["use_key"] else "0"}]


@_handler
def glory_start(spec, req):
    f = _feature("glory", spec)
    op, choice = _node(req, "jQsE54Iz") or {}, _node(req, "9zULH4p1") or {}
    row = _mission("glory", op.get("qo3PECw6"))
    groups, user = _glory(f, row["uv60hgDW"])
    _need(str(choice.get("pvS5A4kE")) == f["event"], "Glory event mismatch")
    if not f.get("active"):
        ids = _csv(choice.get("51xkq83U"))
        allowed = {str(g["M3JE6vnF"]) for g in groups} & set(_csv(user["D2gU5tET"]))
        _need(set(ids) <= allowed, "gimmick is locked or outside this event")
        masters = _mst("F_GLORY_GIMMICK_MST.ndjson", "M3JE6vnF")
        options = [str(masters[i]["G97fnWwh"]) for i in ids if str(masters[i]["G97fnWwh"]) != "0"]
        _need(len(set(options)) == len(options), "mutually exclusive gimmicks")
        bonus = any(str(masters[i]["4Ny9ztLJ"]) == "2" for i in ids)
        use_key = choice.get("U92bySoZ") in (True, 1, "1") and bonus
        _need(not bonus or use_key, "bonus gimmick requires a magic key")
        if use_key:
            _need(GLORY_MAGIC_KEY in _mst("F_ITEM_MST.ndjson", "tL6G9egd"), "magic key master is missing")
            _need(State.player.spend_item(20, GLORY_MAGIC_KEY, 1), "no Glory magic key")
        _begin("glory", f, row, op, {"gimmicks": ",".join(ids), "use_key": use_key})
    else:
        _need(f["active"]["mission"] == str(row["qo3PECw6"]), "another Glory mission is active")
    _save("glory", f)
    out = _refresh(_reply(spec, f, ("dekE2X8K",)))
    out.update({"1Ke2wFgm": _resume(f), "jQsE54Iz": _rng(f), "aGPc06ym": _glory_selection(f)})
    return out


@_handler
def glory_end(spec, req):
    f = _feature("glory", spec)
    groups, user = _glory(f)
    run = deepcopy(f.get('active'))
    if _finish("glory", f, req, spec=spec):
        from ffbe_battle import mission_result_from
        context = mission_result_from(json.dumps(req))
        metrics = context.get('achievements', {})
        # Offline ranking is personal. Its score is based on the witnessed
        # clear, turn damage and selected gimmicks, never invented opponents.
        selected = _csv(run.get('gimmicks'))
        score = 10000 + min(30000, int(metrics.get('MAX_DAMAGE_TURN', 0)) // 100000) + 1000 * len(selected)
        f['high_score'] = max(int(f.get('high_score', 0)), score)
        user['UbQ26oH4'] = str(f['high_score'])
        user['5oPuXx1a'] = '1'
        user['E5R3sMfb'] = '101'
        user['C15d9FDP'] = ','.join(sorted(set(_csv(user.get('C15d9FDP'))) | set(selected)))
        unlocked = set(_csv(user.get('D2gU5tET')))
        for group in groups:
            condition = str(group['59kRbpKz'])
            if (condition == '3' and str(group['xHZj7Va5']) == run['mission'] or
                    condition == '1' and f['high_score'] >= int(group['J0tnsW5m'])):
                unlocked.add(str(group['M3JE6vnF']))
        notices = unlocked - set(_csv(user.get('D2gU5tET')))
        user['D2gU5tET'] = ','.join(sorted(unlocked))
        user['Vm07pZ2A'] = ','.join(sorted(set(_csv(user.get('Vm07pZ2A'))) | notices))
        f["ranking"] = [{"yN78E6XH": user["5oPuXx1a"], "V84xhbq3": user["5oPuXx1a"],
            "Pt3q6Se0": user["E5R3sMfb"], "B0CxyAK9": user["E5R3sMfb"],
            "qJre90x2": str(f.get("high_score", 0)), "eG6wicL9": str(f.get("high_score", 0)),
            "UbQ26oH4": user["UbQ26oH4"], "J0tnsW5m": "0", "C15d9FDP": user["C15d9FDP"]}]
        _save("glory", f)
    out = _refresh(_reply(spec, f, ("dekE2X8K", "4FhDP05Q", "C9g3yKDL")))
    out.update({"09HRWXDf": deepcopy(f["last_end"]["result"]), "ZDxy76LN": deepcopy(f["ranking"]), "1Ke2wFgm": _resume(f)})
    _carry_reply(out)
    return out


@_handler
def glory_restart(spec, req):
    return _restart("glory", spec, req)


@_handler
def glory_confirmed(spec, req):
    f = _feature("glory", spec)
    _, user = _glory(f)
    node = _node(req, "9zULH4p1") or {}
    _need(str(node.get("pvS5A4kE")) == f["event"], "Glory event mismatch")
    ids = _csv(node.get("51xkq83U"))
    _need(set(ids) <= set(_csv(user["D2gU5tET"])), "cannot confirm a locked gimmick")
    f["confirmed"] = sorted(set(f.get("confirmed", [])) | set(ids))
    if AUTHORED_NOTICE_CSV:
        user["Vm07pZ2A"] = ",".join(i for i in _csv(user.get("Vm07pZ2A")) if i not in f["confirmed"])
    _save("glory", f)
    return _reply(spec, f, ("dekE2X8K",))


def _survival(f):
    from ffbe_config import SURVIVAL_EVENT
    f["groups"].setdefault("65cMLkuQ", [{"pvS5A4kE": SURVIVAL_EVENT, "52ibRBqw": "0", "7SPHKY1j": "0", "UbQ26oH4": "0"}])
    f["groups"].setdefault("2w9Iyeaq", [{"3KJpzuC5": "1@0"}])


@_handler
def survival_start(spec, req):
    return _start("survival", spec, req)


@_handler
def survival_end(spec, req):
    f = _feature("survival", spec)
    _survival(f)
    if _finish("survival", f, req, switches=False, spec=spec):
        from ffbe_battle import mission_result_from
        context = mission_result_from(json.dumps(req))
        waves = len(context.get('wave_turns', {}))
        user = f['groups']['65cMLkuQ'][0]
        user['52ibRBqw'] = str(max(int(user.get('52ibRBqw', 0)), waves))
        user['7SPHKY1j'] = str(int(user.get('7SPHKY1j', 0)) + waves)
        user['UbQ26oH4'] = str(int(user.get('UbQ26oH4', 0)) + waves)
        party = _node(req, "2w9Iyeaq")
        if party is not None:
            packed = party.get("3KJpzuC5")
            _need(isinstance(packed, str) and packed.startswith("1@"), "invalid Survival party version")
            _need(all(len(p.split("|")) == 9 for p in packed.split("@")[2:]), "invalid Survival party record")
            f["groups"]["2w9Iyeaq"] = [{"3KJpzuC5": packed}]
        _save("survival", f)
    out = _refresh(_reply(spec, f, TAGS["survival"]))
    out.update({"09HRWXDf": deepcopy(f["last_end"]["result"]), "1Ke2wFgm": _resume(f)})
    _carry_reply(out)
    return out


@_handler
def survival_restart(spec, req):
    return _restart("survival", spec, req)


@_handler
def survival_retire(spec, req):
    return _retire("survival", spec, req)


@_handler
def survival_return(spec, req):
    f = _feature("survival", spec)
    area = str((_node(req, "V3oXMq9f") or {}).get("uv60hgDW") or "")
    _need(area and area == f.get("area"), "return area does not match the saved expedition")
    _need(not f.get("active"), "retire or finish the active mission before returning")
    _survival(f)
    f["groups"]["2w9Iyeaq"] = [{"3KJpzuC5": "1@0"}]
    f["returned"] = True
    _save("survival", f)
    out = _reply(spec, f, TAGS["survival"])
    out["1Ke2wFgm"] = _resume(f)
    return out


def _parade(f, area, player=None):
    """Use the original Parade engine, with independent permanent campaign saves.

    Reward schedule 65000/650001 is the published first Global Dark Visions
    schedule, present in the original masters. Unmatched archived campaigns
    reuse that schedule; this is an offline reconstruction, not recovered
    campaign-to-schedule server metadata.
    """
    player = player or State.player
    area = str(area)
    missions = [r for r in _missions('parade') if str(r['uv60hgDW']) == area]
    _need(missions, 'unknown Parade area')
    if f.get('area') and str(f['area']) != area:
        _need(not f.get('active'), 'finish the current Parade mission first')
        history = f.setdefault('seasons', {})
        history[str(f['area'])] = {k: deepcopy(v) for k, v in f.items() if k != 'seasons'}
        saved = deepcopy(history.get(area, {}))
        f.clear()
        f.update(saved, seasons=history)
    f['area'] = area
    f.setdefault('bests', {})
    f.setdefault('milestones', [])
    f['schedule'] = '65000'
    groups = f.setdefault('groups', {})
    event = {**_event(area), 'L84eYzxv': '650001', 'D1GdY4Vh': '1',
             'VjJQ51uG': '2020-01-01 00:00:00', 'm8ivD4NX': '2099-12-31 23:59:59',
             'RdV4nK8w': '1', 'td06MKEX': f['schedule']}
    groups['gXrD1h58'] = [event]
    score = sum(int(r['7HSK9eBV']) for r in f['bests'].values())
    groups['yA8Nn9vK'] = [{'pvS5A4kE': f['schedule'], 'UbQ26oH4': str(score),
                           # There is one local player and no remote leaderboard.
                           # Equal ranks avoid the empty competitive rank-up scene.
                           '52ibRBqw': '1' if score else '0', '7SPHKY1j': '1' if score else '0', 'ej7aEzn5': '1'}]
    groups['94IYZAbg'] = [deepcopy(f.get('last_archive') or _parade_archive(player, missions[0], {}))]
    groups['EYa5g4wh'] = list(deepcopy(f['bests']).values())
    groups['HMa5VTU8'] = [{'RdV4nK8w': f['schedule'], '7HSK9eBV': str(score),
                          '3F0ci9dV': '0', 'r64cDfnp': '0', 'vm3YsP7G': '0'}]
    groups['sMPhc96i'] = []
    player.special_party('8')
    return missions


def _parade_archive(player, row, context):
    metrics = context.get('achievements', {})
    def value(key, default=0):
        try:
            return max(0, int(metrics.get(key, default)))
        except (TypeError, ValueError):
            return 0
    damage = value('DMG_RANK_MAX_DAMAGE_TURN', metrics.get('MAX_DAMAGE_TURN', 0))
    received = value('TOTAL_DAMAGE_TAKE', metrics.get('DAMAGE_RECEIVED', 0))
    deaths = int(context.get('dead_count') or 0)
    turns = int(context.get('turns') or 1)
    chain = value('DMG_RANK_MAX_CHAIN_TURN', metrics.get('MAX_CHAIN_TURN', metrics.get('MAX_CHAIN', 0)))
    # Original published damage, KO, turn and chain point rules. The missing
    # server damage-received curve uses a monotonic local 1 point/100 HP loss.
    parts = [(damage, min(30000, 5000 + damage // 85899)),
             (received, max(0, 10000 - received // 100)),
             (deaths, max(0, 10000 - deaths * 1000)),
             (turns, max(0, 10000 - max(0, turns - 1) * 1000)),
             (chain, min(10000, chain * 100))]
    base = int(row.get('e3RBi8EF') or 0)
    from event_archive import events
    dark = sorted((e for e in events() if e['name'] == 'Dark Visions'), key=lambda e: int(e['area']))
    season = next((n for n, e in enumerate(dark, 1) if e['area'] == str(row.get('uv60hgDW'))), 0)
    dungeon = int(str(row['U9iHsau3'])[-2:])
    stage = int(row['Z0EN6jSh'])
    if 1 <= season <= 3:
        # The first three Global seasons publish the same per-stage awards.
        # e3RBi8EF is only populated on the opening row in the client master.
        base = (10000 if dungeon == 1 else 20000 if dungeon == 2 else
                30000 if stage <= 3 else 50000 if stage == 4 else 100000)
    elif 4 <= season <= 5:
        base = (150000 if stage == 1 else 200000) if dungeon == 5 else (50000 if stage == 1 else 100000)
    elif 6 <= season <= 19:
        # Published common-stage policy. Seasons 18 and 19 omit this table;
        # retain the preceding archive policy for those missing definitions.
        base = 50000 if stage == 1 else 100000
    elif 20 <= season <= 30:
        base = (30000 if stage == 1 else 80000) if dungeon <= 4 else (100000 if dungeon == 5 else 200000)
    elif season >= 31:
        base = (30000 if stage == 1 else 50000) if dungeon <= 4 else 80000
    total = base + sum(points for _, points in parts) if context else 0
    # The native artwork orders ranks from SSS (0) down to C (5).
    grades = [5 - min(5, points * 5 // (30000 if n == 0 else 10000))
              for n, (_, points) in enumerate(parts)]
    return {'9Tbns0eI': str(player.data['identity']['user_id']), 'L9IAY8iW': '65000',
            'qo3PECw6': str(row['qo3PECw6']), 'pvS5A4kE': '65000', '6DuiWx05': '0',
            '7HSK9eBV': str(total), 'cH15BhQ0': str(max(grades) if context else 0),
            'qf9S3TLg': str(base if context else 0), 'jE9V1oSk': '0', '0A7msQc9': '0',
            'wF5Ac6ey': ','.join(f'{n + 1}:{grades[n]}:{points}:{min(raw, 2147483647)}'
                                  for n, (raw, points) in enumerate(parts)),
            'km0aS4b1': '', 'Apfj8IT2': '', '6d9x1vIU': '1' if context else '0',
            # ParadeUtil asks for category keys 1 through 5. A missing last
            # key makes the original native loop run beyond its split vector.
            '5EWcu4M8': ','.join(f'{n}:{n}' for n in range(1, 6))}


def _parade_complete(f, mid, req):
    from ffbe_battle import mission_result_from
    row = _mission('parade', mid)
    archive = _parade_archive(State.player, row, mission_result_from(json.dumps(req)))
    f['last_archive'] = archive
    previous = deepcopy(list(f.get('bests', {}).values()))
    if int(archive['7HSK9eBV']) > int(f['bests'].get(mid, {}).get('7HSK9eBV', -1)):
        f['bests'][mid] = deepcopy(archive)
    _parade(f, row['uv60hgDW'])
    # The result compares against the previous record; the next entry projects
    # the newly persisted bests. Never replace the comparison before rendering.
    f['groups']['EYa5g4wh'] = previous
    f['party_history'] = deepcopy(_node(req, '9uzBbMgf') or {})
    score = int(f['groups']['yA8Nn9vK'][0]['UbQ26oH4'])
    awarded = []
    for reward in _mst('F_SEASON_EVENT_REWARD_MST.ndjson', None)['__rows__']:
        if str(reward.get('pvS5A4kE')) != f['schedule']:
            continue
        key = str(reward['rYGk3Q7t'])
        if int(reward['1UB3Hqfc']) <= score and key not in f['milestones']:
            from exvius_rewards import parse
            items = parse(reward['dX6cor8j'])
            _grant(items)
            awarded.extend(items)
            f['milestones'].append(key)
    if awarded:
        State.player.deliver_mail('Dark Visions: Point Rewards', [],
                                  message='Your point rewards have been added to your inventory.')
    f['last_point_rewards'] = awarded


def parade_rewards_page(player):
    """The original completion tab is a WebView, unlike its native rank tab."""
    from html import escape
    from gacha_rates import reward_name
    from exvius_rewards import parse
    if player is None:
        return None
    feature = player.data.get('exvius_parade', {})
    if not feature.get('area'):
        return None
    total = sum(int(row['7HSK9eBV']) for row in feature.get('bests', {}).values())
    claimed = set(feature.get('milestones', []))
    rows = []
    schedule = feature.get('schedule', '65000')
    for row in _mst('F_SEASON_EVENT_REWARD_MST.ndjson', None)['__rows__']:
        if str(row.get('pvS5A4kE')) != schedule:
            continue
        labels = '<br>'.join(escape(reward_name(r)) + ' x ' + format(r['count'], ',')
                              for r in parse(row['dX6cor8j']))
        obtained = str(row['rYGk3Q7t']) in claimed
        rows.append((int(row['1UB3Hqfc']), '<tr' + (' class="obtained"' if obtained else '') +
                     '><td>' + format(int(row['1UB3Hqfc']), ',') + '</td><td>' + labels +
                     ('<small>Received</small>' if obtained else '') + '</td></tr>'))
    return ('<!doctype html><html lang="en"><head><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width,initial-scale=1">'
            '<title>Completion Rewards</title><style>'
            'body{margin:0;padding:14px;background:#081d43;color:white;font:16px Arial,sans-serif}'
            'h1{font-size:21px;color:#ffe398}table{border-collapse:collapse;width:100%}'
            'td,th{padding:12px 9px;border:1px solid #4b6990;text-align:left}'
            'th{background:#194875;color:#ffe398}.obtained{background:#173f48}'
            'small{display:block;color:#a9e9cb;margin-top:5px}</style></head><body>'
            '<h1>Completion Rewards</h1><p>Individual points: <strong>' + format(total, ',') +
            '</strong></p><p>Rewards are added automatically when you reach each target.</p>'
            '<table><tr><th>Points</th><th>Rewards</th></tr>' +
            ''.join(html for _, html in sorted(rows)) + '</table></body></html>')


@_handler
def parade_entry(spec, req):
    f = _feature('parade', spec)
    area = str((_node(req, 'V3oXMq9f') or {}).get('uv60hgDW') or '')
    _parade(f, area)
    _save('parade', f)
    out = _reply(spec, f, TAGS['parade'])
    out.update(State.player.special_party_groups('8'))
    return out


@_handler
def parade_end(spec, req):
    f = _feature("parade", spec)
    if not f.get('active'):
        mid = str((_node(req, 'jQsE54Iz') or {}).get('qo3PECw6', ''))
        attempt = State.player.data.get('exvius_repeat', {}).get('attempt', {})
        if attempt.get('mid') == mid and attempt.get('sequence') != f.get('last_end', {}).get('sequence'):
            f['active'] = {'mission': mid, 'sequence': attempt['sequence'],
                           'carry': deepcopy(State.player.data['inventory']['carry_items']),
                           'operation': {}, 'helper': ''}
    _need(all(tag in f["groups"] for tag in TAGS["parade"][:4]), "Parade event state is unavailable")
    if _finish("parade", f, req, switches=False, spec=spec):
        _parade_complete(f, f['last_end']['mission'], req)
        _save("parade", f)
    out = _refresh(_reply(spec, f, TAGS["parade"][1:]))
    out.update({"09HRWXDf": deepcopy(f["last_end"]["result"]), "1Ke2wFgm": _resume(f)})
    _carry_reply(out)
    return out


def _rm_snapshot(f, req):
    node = _node(req, "jSC4Tx9H")
    if node is None:
        return
    _need(str(node.get("9Tbns0eI")) == str(State.player.data["identity"]["user_id"]), "RM snapshot owner mismatch")
    _need(_number(node.get("r21y0YzS")) in [d["id"] for d in State.player.data["party"]["decks"]], "unknown RM party deck")
    f["snapshot"] = deepcopy(node)  # Retain request-only tab too, but never echo it as an unsupported reply field.
    f["groups"]["jSC4Tx9H"] = [{k: node[k] for k in RM_SNAPSHOT if k in node}]


def _rm(f, player=None):
    player = player or State.player
    old = (f["groups"].get("Wmr7y9a0") or [{}])[0]
    f.setdefault("dungeon", str(old.get("U9iHsau3", "0")))
    f.setdefault("mission", str(old.get("qo3PECw6", "0")))
    if 'last_completed' not in f:
        rows = _missions('rm', f['dungeon']) if f['dungeon'] != '0' else []
        pos = next((n for n, r in enumerate(rows) if r['qo3PECw6'] == f['mission']), 0)
        f['last_completed'] = rows[pos - 1]['qo3PECw6'] if pos else '0'
    f["groups"].setdefault("Q4kJKh8b", [_event(f.get("area", _missions("rm")[0]["uv60hgDW"]))])
    f["groups"].setdefault("jSC4Tx9H", [{"r21y0YzS": str(player.data["party"]["active_deck"])}])
    native_mission = (f.get('active') or {}).get('mission', f['last_completed']) if f.get('run') else '0'
    f["groups"]["Wmr7y9a0"] = [{"U9iHsau3": f.get("dungeon", "0"), "qo3PECw6": native_mission,
                                      "5rMfWv4X": old.get("5rMfWv4X", "")}]
    f["groups"]["Ur6CKS2e"] = _resume(f, rm=True)


@_handler
def rm_entry(spec, req):
    f = _feature("rm", spec)
    if "snapshot" not in f and not f.get("run"):
        _rm_snapshot(f, req)
    _rm(f)
    _save("rm", f)
    return _reply(spec, f, TAGS["rm"])


@_handler
def rm_dungeon_start(spec, req):
    f = _feature("rm", spec)
    node = _node(req, "9Zok3IK2") or {}
    did = str(node.get("U9iHsau3") or "")
    rows = _missions("rm", did)
    _need(bool(rows), "dungeon has no RM missions")
    if f.get("run"):
        _need(f["dungeon"] == did, "another RM dungeon is active")
    else:
        # Entering a dungeon does not charge. The actual mission start debits
        # its original stamina/orb account through the shared start handler.
        _helper(node)
        _rm_snapshot(f, req)
        f.update(run=True, dungeon=did, area=str(rows[0]["uv60hgDW"]), mission=str(rows[0]["qo3PECw6"]), last_completed='0',
                 dungeon_operation=deepcopy(node), dungeon_settled=False)
    _rm(f)
    _save("rm", f)
    return _reply(spec, f, TAGS["rm"])


@_handler
def rm_start(spec, req):
    f = _feature("rm", spec)
    op = _node(req, "jQsE54Iz") or {}
    _need(f.get("run") and str(op.get("qo3PECw6")) == f["mission"], "no matching RM dungeon checkpoint")
    row = _mission("rm", op["qo3PECw6"])
    _need(str(row["U9iHsau3"]) == f["dungeon"], "RM dungeon mismatch")
    if not f.get("active"):
        _rm_snapshot(f, req)
    _begin("rm", f, row, op)
    _rm(f)
    _save("rm", f)
    out = _refresh(_reply(spec, f, TAGS["rm"]))
    out["jQsE54Iz"] = _rng(f)
    return out


@_handler
def rm_end(spec, req):
    f = _feature("rm", spec)
    if _finish("rm", f, req, spec=spec):
        _rm_snapshot(f, req)
        mid = f["last_end"]["mission"]
        rows = _missions("rm", f["dungeon"])
        pos = next(i for i, r in enumerate(rows) if str(r["qo3PECw6"]) == mid)
        f['last_completed'] = mid
        f["mission"] = str(rows[pos + 1]["qo3PECw6"]) if pos + 1 < len(rows) else "0"
        _rm(f)
        _save("rm", f)
    out = _refresh(_reply(spec, f, TAGS["rm"]))
    out["09HRWXDf"] = deepcopy(f["last_end"]["result"])
    _carry_reply(out)
    return out


@_handler
def rm_restart(spec, req):
    return _restart("rm", spec, req)


@_handler
def rm_retire(spec, req):
    f = _feature('rm', spec)
    mid = str((_node(req, 'jQsE54Iz') or {}).get('qo3PECw6') or '')
    if mid == '0' and f.get('run') and not f.get('active'):
        # The original map's Give Up action has no active battle and sends 0.
        _rm_snapshot(f, req)
        _carry(f, req)
        f.update(run=False, active=None, retired='0', dungeon='0', mission='0', last_completed='0')
        _rm(f)
        _save('rm', f)
        out = _refresh(_reply(spec, f, TAGS['rm']))
        _carry_reply(out)
        return out
    out = _retire("rm", spec, req)
    f = deepcopy(State.player.data["exvius_rm"])
    f.update(dungeon='0', mission='0', last_completed='0')
    _rm(f)
    _save("rm", f)
    return _reply(out, f, TAGS["rm"])


@_handler
def rm_dungeon_end(spec, req):
    f = _feature("rm", spec)
    did = str((_node(req, "9Zok3IK2") or {}).get("U9iHsau3") or "")
    _need(did == f.get("dungeon"), "RM dungeon mismatch")
    _need(not f.get("active") and f.get("mission") == "0", "RM dungeon has unfinished missions")
    if not f.get("dungeon_settled"):
        _need(f.get("run"), "no RM dungeon run")
        _rm_snapshot(f, req)
        f.update(run=False, dungeon_settled=True)
        _rm(f)
        _save("rm", f)
    out = _reply(spec, f, TAGS["rm"])
    # Specialized DungeonEnd has only unit parameters, never a second mission-loot award.
    out["09HRWXDf"] = [{"kcb0tsM6": "0", "16LQuC5r": "0"}]
    return out


def _tfa(f, did=None):
    if did is not None:
        if f.get('dungeon') and f['dungeon'] != did:
            f.setdefault('seasons', {})[f['dungeon']] = {k: deepcopy(v) for k, v in f.items() if k != 'seasons'}
            history = f['seasons']
            saved = deepcopy(history.get(did, {}))
            f.clear()
            f.update(saved, seasons=history)
        f["dungeon"] = did
    _need(f.get("dungeon"), "TFA entry is required")
    from exvius_fortuna import ensure
    try:
        ensure(f, f['dungeon'])
    except ValueError as exc:
        raise _Refused(str(exc)) from exc
    event = next((r for r in f["groups"].get("L6XRZb0z", []) if str(r.get("U9iHsau3")) == f["dungeon"]), None)
    _need(event and event.get("enkCGfPT"), "TFA event/MonsterScaleMissionMst is unavailable")
    status = (f["groups"].get("x51bb135") or [{}])[0]
    bonus = (f["groups"].get("Fs0sexp7") or [{}])[0]
    f.setdefault("pending", str(status.get("dc10ae96", "0")) == "1")
    f.setdefault("claimed", str(status.get("cEVau7d8", "1")) == "0")
    f.setdefault("slots", str(bonus.get("mXQWZ5Ql") or ""))
    f.setdefault("pass", str(bonus.get("bcd49985") or ""))
    f.setdefault("selection", str(bonus.get("IX1hKI6g", "0")) == "1")
    f["groups"]["x51bb135"] = [{"dc10ae96": "1" if f["pending"] else "0", "cEVau7d8": "0" if f["claimed"] else "1"}]
    f["groups"]["Fs0sexp7"] = [{"mXQWZ5Ql": f["slots"], "IX1hKI6g": "1" if f["selection"] else "0", "bcd49985": f["pass"]}]
    f["groups"].setdefault("AJb8pF71", [])
    from exvius_fortuna import sync_personal_ranking
    sync_personal_ranking(State.player, f)


def _tfa_items(text, limit):
    payload = str(text).split("/", 1)[-1]
    rows = []
    for part in payload.split(",") if payload else []:
        match = re.fullmatch(r"(\d+):(\d+):(\d+)(?:-(\d+))?", part)
        _need(match is not None, "unsupported TFA reward grammar")
        kind, iid, count, flag = match.groups()
        _need(int(count) > 0, "empty TFA reward")
        rows.append((int(kind), int(iid), int(count), int(int(flag or 0) > 0)))
    _need(len(rows) <= limit, "too many TFA reward records")
    return rows


def _tfa_pack(rows):
    return ",".join(f"{k}:{i}:{n}-{flag}" for k, i, n, flag in rows)


def _tfa_capacity(f):
    parts = f["pass"].split(":")
    _need(len(parts) == 3, "event-pass slot capacity is unavailable")
    event = next(r for r in f["groups"]["L6XRZb0z"] if str(r.get("U9iHsau3")) == f["dungeon"])
    capacity = _number(parts[2])
    _need(parts[1] == str(event.get("pvS5A4kE")) and 0 < capacity <= 4, "invalid event-pass capacity/event")
    return capacity


@_handler
def tfa_entry(spec, req):
    f = _feature("tfa", spec)
    did = str((_node(req, "9Zok3IK2") or {}).get("U9iHsau3") or "")
    _need(bool(_missions("tfa", did)), "dungeon has no TFA missions")
    _tfa(f, did)
    _save("tfa", f)
    out = _reply(spec, f, TAGS["tfa"])
    return _refresh(out) if f.get('claimed') else out


@_handler
def tfa_start(spec, req):
    op = _node(req, 'jQsE54Iz') or {}
    row = _mst('F_MISSION_MST.ndjson', 'qo3PECw6').get(str(op.get('qo3PECw6')))
    # Older trials share these native endpoints. Preserve their existing path.
    if not row or str(row.get('gQR24kST')) != '50':
        return spec
    f = _feature('tfa', spec)
    _tfa(f, str(row['U9iHsau3']))
    node = _node(req, 'WaBIK8pI') or {}
    _need(str(node.get('U9iHsau3', row['U9iHsau3'])) == str(row['U9iHsau3']), 'TFA dungeon mismatch')
    rows = _missions('tfa', row['U9iHsau3'])
    tier = next(n for n, r in enumerate(rows, 1) if r['qo3PECw6'] == row['qo3PECw6'])
    lower, upper = (1 if tier == 1 else (tier - 1) * 20), tier * 20 - 1
    level = _number(node.get('UTRQvH1q', lower))
    _need(lower <= level <= upper, 'boss level is outside its mission tier')
    gambits = _csv(node.get('i1kVPwjL'))
    from exvius_fortuna import gambit_bonuses
    try:
        gambit_bonuses(row['uv60hgDW'], tier, gambits)
    except ValueError as exc:
        raise _Refused(str(exc)) from exc
    _begin('tfa', f, row, op, {'boss_level': level, 'gambits': ','.join(gambits)})
    _save('tfa', f)
    out = _refresh(_reply(spec, f, TAGS['tfa']))
    out.update({'1Ke2wFgm': _resume(f), 'jQsE54Iz': _rng(f)})
    return out


@_handler
def tfa_end(spec, req):
    mid = str((_node(req, 'jQsE54Iz') or {}).get('qo3PECw6'))
    row = _mst('F_MISSION_MST.ndjson', 'qo3PECw6').get(mid)
    if not row or str(row.get('gQR24kST')) != '50':
        return spec
    f = _feature('tfa', spec)
    if _finish('tfa', f, req, spec=spec):
        # The common reward pipeline produces the choices and score. Retain
        # those new rows while closing this mode's active session.
        produced = deepcopy(State.player.data.get('exvius_tfa', {}))
        produced.update(active=None, last_end=f['last_end'], settled=f['settled'])
        f = produced
        _save('tfa', f)
    from exvius_fortuna import project
    out = _refresh(project(State.player, spec, mid))
    out['09HRWXDf'] = deepcopy(f['last_end']['result'])
    out['1Ke2wFgm'] = _resume(f)
    return out


@_handler
def tfa_retire(spec, req):
    f = _feature('tfa', spec)
    mid = str((_node(req, 'jQsE54Iz') or {}).get('qo3PECw6'))
    if not f.get('active') or f['active']['mission'] != mid:
        return spec
    f.update(active=None, retired=mid)
    attempt = State.player.data.get('exvius_repeat', {}).get('attempt', {})
    if attempt.get('mid') == mid:
        attempt['status'] = 'retired'
    _save('tfa', f)
    return _reply(spec, f, TAGS['tfa'])


@_handler
def tfa_fix(spec, req):
    f = _feature("tfa", spec)
    node = _node(req, "e262323b") or {}
    _tfa(f, str(node.get("U9iHsau3") or ""))
    choice = node.get("z4EhuqEN")
    _need(isinstance(choice, str), "missing TFA fix operation")
    if f["claimed"] or (choice and choice == f.get("last_choice") and not f['pending']):
        out = _reply(spec, f, ("Fs0sexp7", "x51bb135"))
        return _refresh(out) if not choice else out
    slots = _tfa_items(f["slots"], 4)
    capacity = _tfa_capacity(f)
    _need(len(slots) <= capacity, "obtained slots exceed the event-pass capacity")
    if choice:
        _need(f["pending"], "no pending candidate batch")
        pieces = choice.split(",")
        _need(len(pieces) in (1, 2), "invalid TFA replacement")
        new = _tfa_items(pieces[0], 1)
        _need(len(new) == 1 and new[0] in _tfa_items(f.get("candidates", ""), 3), "reward is not a persisted server candidate")
        if len(pieces) == 2:
            old = re.fullmatch(r"(\d+):(\d+):(\d+):(\d+)-([01])", pieces[1])
            _need(old is not None, "invalid replaced slot")
            k, i, n, index, flag = map(int, old.groups())
            _need(index < len(slots) and index < capacity and slots[index] == (k, i, n, flag), "old provisional slot mismatch")
            slots[index] = new[0]
        else:
            _need(len(slots) < capacity, "TFA slots are full; replacement required")
            slots.extend(new)
        f.update(slots=_tfa_pack(slots), candidates="", pending=False, last_choice=choice)
        if f.get('candidate_queue'):
            f['candidates'] = f['candidate_queue'].pop(0)
            f['pending'] = True
    elif AUTHORED_TFA_FINISH_EMPTY:
        _need(f["pending"] or f["selection"], "no reward selection to finalize")
        _grant([{"kind": k, "id": i, "count": n} for k, i, n, _ in slots])
        f.update(claimed=True, pending=False, selection=False, candidates="")
    _tfa(f)
    _save("tfa", f)
    out = _reply(spec, f, ("Fs0sexp7", "x51bb135"))
    if f.get('pending') and f.get('candidates'):
        out['u9jY6hQJ'] = [{'UJz5QED2': f['candidates']}]
    return _refresh(out) if not choice else out


@_handler
def tfa_resume(spec, req):
    f = _feature("tfa", spec)
    _tfa(f)
    _need(f["pending"] and not f["claimed"] and f.get("candidates"), "no persisted pending TFA candidates")
    _tfa_items(f["candidates"], 3)
    out = _reply(spec, f, ("Fs0sexp7", "x51bb135"))
    out["u9jY6hQJ"] = [{"UJz5QED2": f["candidates"]}]
    return out


@_handler
def tfa_bonus(spec, req):
    f = _feature("tfa", spec)
    node = _node(req, "b62c2649") or {}
    display = str(node.get("Nmcx68HU"))
    _need(display in ("1", "2"), "invalid bonus display type")
    _need(bool(_missions("tfa", str(node.get("U9iHsau3")))), "unknown TFA dungeon")
    keys = ("Nmcx68HU", "U9iHsau3", "7dkQA0K4", "F9gxH37C", "rSpOEfsX")
    key = "|".join(str(node.get(k, "")) for k in keys)
    if display == "2":
        for k in keys[2:]:
            _number(node.get(k))
    rows = f.get("bonus_previews", {}).get(key)
    if rows is None:
        from exvius_fortuna import preview
        tier = max(1, min(5, (int(node.get('7dkQA0K4', 1)) + 19) // 20))
        rows = [{'Nmcx68HU': display, 'k5Oa5kC0': '-1',
                 'mXQWZ5Ql': preview(None if display == '1' else tier,
                                     node.get('F9gxH37C', 1000), node.get('rSpOEfsX', 1000))}]
    out = dict(spec)
    out["hK7NyNhP"] = deepcopy(rows)
    return out


@_handler
def tfa_ranking(spec, req):
    from ffbe_friends import all_friends as load_friends
    f = _feature("tfa", spec)
    node = _node(req, "C0SFBLx4") or {}
    uid, did = str(node.get("m3Wghr1j") or ""), str(node.get("U9iHsau3") or "")
    known = {str(State.player.data["identity"]["user_id"])} | {str(r["friend_id"]) for r in load_friends()}
    _need(uid in known, "ranking player is not self or an offline friend")
    rows = f.get("ranking_details", {}).get(did, {}).get(uid)
    if rows is None:
        rows = f.get('seasons', {}).get(did, {}).get('ranking_details', {}).get(did, {}).get(uid)
    _need(rows is not None, "offline player has no persisted TFA ranking detail/party codec")
    out = dict(spec)
    out["LsaiWo2f"] = deepcopy(rows)
    return out


def equip_grow_entry(spec, req):
    """EquipGrowEntryRequest has only the pinned BaseRequest response codec.

    Entering the weapon selection screen refreshes current ownership. It
    does not choose a weapon, spend an orb or commit enhancement abilities.
    """
    return _refresh(spec)


def equip_grow_notice_page():
    """Instructions for the native screen whose retired notice URL is absent."""
    return '''<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Equipment Enhancement</title><style>
body{margin:0;padding:24px;background:#230b24;color:#fff5dc;font:18px Arial,sans-serif}
h1{font-size:24px;color:#ffe398;margin:0 0 24px}p{line-height:1.6;margin:0 0 20px}
strong{color:#ffe398}</style></head><body><h1>Equipment Enhancement</h1>
<p>Use <strong>Select Equipment to Enhance</strong> below to choose your weapon.</p>
<p>The <strong>Rewards</strong> button is at the top of this screen.</p>
</body></html>'''


HANDLERS = {
    "U8F0Q25i": equip_grow_entry,  # EquipGrowEntryRequest
    "VfEh2wD0": tower_entry,       # TowerEntryRequest
    "dZA90j5s": tower_start,       # TowerStartRequest
    "fBN47X2b": tower_end,         # TowerEndRequest
    "9Z3jCWfF": tower_restart,     # TowerRestartRequest
    "MTuX7ai2": tower_retire,      # TowerRetireRequest
    "UDb5Je1j": glory_entry,       # GloryEntryRequest
    "oj76TPS2": glory_start,      # GloryMissionStartRequest
    "BQG1rm3y": glory_end,        # GloryMissionEndRequest
    "YAF1wt9J": glory_restart,    # GloryMissionReStartRequest
    "7Bt6HTw0": glory_confirmed,  # GloryConfirmedGimmickRequest
    "67tFRKyo": survival_start,   # SurvivalMissionStartRequest
    "3cuPF20R": survival_end,     # SurvivalMissionEndRequest
    "p02YN1JA": survival_restart, # SurvivalMissionRestartRequest
    "yW35iC40": survival_retire,  # SurvivalMissionRetireRequest
    "Ge2ZLDC1": survival_return,  # SurvivalMissionReturnRequest
    "Q46YTgWo": parade_entry,     # ParadeEntryRequest
    "4cACW7y3": parade_end,       # ParadeMissionEndRequest
    "wx5sg9ye": rm_entry,         # RmEntryRequest
    "7FyJS3Zn": rm_start,         # RmStartRequest
    "fyp10Rrc": rm_end,           # RmEndRequest
    "yh21MTaG": rm_restart,       # RmRestartRequest
    "e0R3iDm1": rm_retire,        # RmRetireRequest
    "R5mWbQ3M": rm_dungeon_start, # RmDungeonStartRequest
    "WaPC2T6i": rm_dungeon_end,   # RmDungeonEndRequest
    "C0Lne0I7": tfa_entry,        # TfaEntryRequest
    "BSq28mwY": tfa_start,
    "JiglLZx6": tfa_end,
    "v51PM7wj": tfa_retire,
    "JO2zA1Jy": tfa_fix,          # TfaResultRewardFixRequest
    "4qVA8LFK": tfa_resume,       # TfaResultRewardSelectResumeRequest
    "fcPxKx8M": tfa_bonus,        # TfaBonusRewardInfoRequest
    "Bg1cbQV7": tfa_ranking,      # TfaRankingDetailRequest
}
