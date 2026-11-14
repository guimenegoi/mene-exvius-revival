"""Back-pay for equipment, materia and key-item chests that opened but never paid (2026-11-12).

Until 2026-11-12 `exvius_field_treasures._mission_treasures` only read opened-chest tuples from `Z7G0yxXe` (items) and
`R1kg3EBA`; the phone reports equipment in `Mh1BA4uv`, materia in `30u6XYiB` and key items in `95JxZzuG`
(`MissionResultInfoBase::toJsonGroup`). So any chest holding one of those (kinds 21/22/23) showed its message and paid
nothing, and its opening switch was never saved (the mission-end path leaves chest switches to the payout).

What the server can still prove, checked once per save at login (`deliver`):
  * request records (`server/requests/`, one file per game request; kept FFBE_REQUEST_LOG_DAYS days, default 3, and
    under FFBE_REQUEST_LOG_MB): a battle-end request that reported the chest's exact tuples with its opening switch
    for that chest's mission;
  * the save's switches: the chest's own switch saved from a field switch update (`MissionSwitchUpdateRequest`
    saves whatever the phone sends, chest switches included).
A chest with neither left no trace. Its switch was never saved, so it is closed again on the phone and pays when
opened now. Each owed chest is paid once by mail, recorded as received (`exvius_field_treasures`) and its switch
set, so neither the mail nor the chest can pay it again. EXVIUS_CHEST_BACKPAY=0 turns the back-pay off.
"""
from __future__ import annotations

import copy
import json
import os
from pathlib import Path

LEDGER = "chest_backpay"
TITLE = "Treasure Chests"
KINDS = (21, 22, 23)           # equipment, materia, key items: the channels the payout didn't read


def enabled() -> bool:
    return os.environ.get("EXVIUS_CHEST_BACKPAY", "1").strip().lower() not in ("0", "off", "false", "no")


def _affected(row) -> bool:
    return any(int(entry.split(":")[0]) in KINDS for entry in str(row.get("rewards") or "").split(",") if entry)


def _received(player, iid, row) -> bool:
    from exvius_field_treasures import catalogue
    got = set(map(str, player.data.get("exvius_field_treasures", [])))
    if str(iid) in got:
        return True
    return bool(row.get("switch")) and any(
        (catalogue().get(key) or {}).get("switch") == row["switch"]
        and (catalogue().get(key) or {}).get("rewards") == row["rewards"] for key in got)


def _missions(row) -> set:
    missions = set(map(str, row.get("missions", [])))
    if row.get("mission"):
        missions = {str(row["mission"])}
    return missions


def _when(text, form):
    from datetime import datetime, timezone
    try:
        stamp = datetime.strptime(str(text), form)
    except ValueError:
        return None
    return stamp if stamp.tzinfo else stamp.replace(tzinfo=timezone.utc)


def _reports(folder, created=None):
    """(mission id, opened switches, reported tuples, file name) from saved battle-end requests. Records made
    before the save existed (`created`, the save's meta.created_utc) belong to an earlier save (a New Game
    keeps the request records) and are left out (2026-11-12)."""
    from exvius_field_treasures import RESULT, reported_tuples
    born = _when(created, "%Y-%m-%dT%H:%M:%SZ") if created else None
    try:
        names = sorted(os.listdir(folder))
    except OSError:
        return
    for name in names:
        if not name.endswith(".json"):
            continue
        try:
            rec = json.loads(Path(folder, name).read_text(encoding="utf-8"))
            text = rec.get("plaintext") or ""
            if "jQsE54Iz" not in text or RESULT not in text or not (rec.get("reply") or {}).get("len"):
                continue
            made = _when(rec.get("ts"), "%Y-%m-%dT%H:%M:%S%z") if born else None
            if made and made < born:
                continue
            req = json.JSONDecoder().raw_decode(text)[0]
        except (OSError, ValueError, AttributeError):
            continue
        nodes, results = req.get("jQsE54Iz"), req.get(RESULT)
        if not (isinstance(nodes, list) and nodes and isinstance(nodes[0], dict)
                and isinstance(results, list) and results and isinstance(results[0], dict)):
            continue
        yield (str(nodes[0].get("qo3PECw6") or ""), set(str(nodes[0].get("dIPkNn61") or "").split(",")),
               reported_tuples(results[0]), name)


def owed(player, folder) -> dict:
    """{chest id: evidence} for affected chests this save opened and never received."""
    from exvius_field_treasures import catalogue
    from player_state import switch_position
    candidates = {iid: row for iid, row in catalogue().items()
                  if _affected(row) and _missions(row) and not _received(player, iid, row)}
    out = {}
    for mid, opened, reported, name in _reports(folder, (player.data.get("meta") or {}).get("created_utc")):
        for iid, row in candidates.items():
            if iid in out or mid not in _missions(row):
                continue
            if row["switch"] and str(row["switch"]) not in opened:
                continue
            if all(entry + ":" + str(row["switch"]) in reported for entry in row["rewards"].split(",")):
                out[iid] = "request " + name
    switches = player.switches
    # A chest that paid saved its switch too, and the catalogue gives some switches to two different chests
    # (40003003: Earth Shrine's Potion chest and a Rod chest in Latius Woods). A saved switch a paid chest
    # accounts for proves nothing about the other chest (2026-11-12).
    paid = {str(catalogue()[key]["switch"]) for key in map(str, player.data.get("exvius_field_treasures", []))
            if key in catalogue() and catalogue()[key]["switch"]}
    for iid, row in candidates.items():
        pos = switch_position(row["switch"]) if row["switch"] else None
        if (iid not in out and pos and str(row["switch"]) not in paid
                and int(pos[1]) in switches.get(pos[0], set())):
            out[iid] = "saved switch " + str(row["switch"])
    return out


def deliver(spec, reply_id):
    """Pipeline step (login carriers): check once, mail what is owed."""
    from exvius_field_treasures import catalogue
    from exvius_rewards import parse
    from ffbe_config import ANNIVERSARY_TICKET_CARRIER
    from ffbe_state import State
    from player_state import switch_position
    player = State.player
    if (not enabled() or reply_id not in ANNIVERSARY_TICKET_CARRIER.split(",") or player is None
            or not isinstance(spec, dict) or player.mode == "frozen" or (player.data.get(LEDGER) or {}).get("checked")):
        return spec
    found = owed(player, State.outdir)
    before, dirty_before = copy.deepcopy(player.data), player.dirty
    try:
        rows = []
        for iid in list(found):
            parsed = parse(catalogue()[iid]["rewards"])
            if not all(player._can_credit(r) for r in parsed):
                print(f"chest back-pay: {iid} has a reward this save can't take; left for the chest itself", flush=True)
                found.pop(iid)
                continue
            rows.extend(parsed)
        led = player.data.setdefault(LEDGER, {})
        if rows:
            entry = player.deliver_mail(
                TITLE, [(r["kind"], r["id"], r["count"]) for r in rows], mail_id=str(933000000000 + len(found)),
                message="Equipment, materia and key items from treasure chests you opened that weren't delivered.",
                icon_type=2, attach_type=1)
            if entry is None:
                raise RuntimeError("chest back-pay mail refused")
        got = player.data.setdefault("exvius_field_treasures", [])
        for iid in found:
            got.append(str(iid))
            pos = switch_position(catalogue()[iid]["switch"]) if catalogue()[iid]["switch"] else None
            if pos:
                player.grant_switch(*pos)
        led.update(checked=True, paid={iid: why for iid, why in found.items()})
        player.dirty = True
        State.state_dirty = True
    except Exception:
        player.data, player.dirty = before, dirty_before
        raise
    print(f"chest back-pay: {len(found)} chest(s) "
          + (", ".join(f"{iid} ({why})" for iid, why in found.items()) or "(nothing owed)"), flush=True)
    return spec
