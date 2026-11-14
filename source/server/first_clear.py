"""First-clear rewards: `F_MISSION_MST.1x4bG2J8`, paid once per mission on its first successful clear.

The shipped mission table lists each mission's first-clear reward (`kind:id:count:rate[:unit fields]`, comma
list; 5,036 of 17,690 missions: Lapis, items such as event currency, units, tickets, equipment, materia).
Global's server paid it the first time a mission was cleared. Nothing here read it before 2026-11-09, so
e.g. Mana Mystery's quests paid no Candy at all.

The phone can't pay or report these itself: its `MissionMst` parser never reads the column (only
`ClsmRoundMst` reads `1x4bG2J8`). The result screen does have a first-clear section: the result reply's
`p1K5NecV` (in `09HRWXDf`) is stored as `MissionResultInfoBase::firstClearBonus` (+0x118,
`MissionResultResponse::readParam`), and `MissionResultScene::setupFirstClearBonus` (called from
`initConnect`) splits it on ',' and ':' and lists each `kind:id:count` as a source-17 item
(`getFirstClearBonusList`). "" or "0" shows nothing.

Which clears count: a mission pays when it is cleared and it is neither in this save's paid list nor in the
`baseline`, the missions already cleared when this feature first saw the save (those are "old clears"; see
`backpay`). Same success rule as `ffbe_battle.grant_cleared_mission`: a battle needs its loaded attempt
completed and cleared; a zero-wave mission (exploration, story beat) needs a result reply that doesn't
report a failure. Lapis goes through `PlayerState._grant_items`, so the earned-Lapis multiplier applies, and
the result screen shows the multiplied amount (what was credited).

Settings: EXVIUS_FIRST_CLEAR (1) pays first-clear rewards; 0 turns it off.
"""
from __future__ import annotations

import copy
import os

LEDGER = "first_clear"


def enabled() -> bool:
    return os.environ.get("EXVIUS_FIRST_CLEAR", "1").strip() != "0"


def raw(mid) -> str:
    """The mission's shipped first-clear reward string, or ''."""
    from player_state import _load_ndjson
    row = _load_ndjson("F_MISSION_MST.ndjson", "qo3PECw6").get(str(mid)) or {}
    value = str(row.get("1x4bG2J8") or "").strip()
    import reward_overrides          # the wiki's reward where the operator chose it (2026-11-10)
    value = reward_overrides.first_clear(mid, value).strip()
    value = "" if value == "0" else value
    import story_recipes             # recipes the story gave that Global's final data dropped (issue #3)
    more = story_recipes.extra(mid)
    return ",".join(v for v in (value, more) if v)


def rewards(mid) -> list[dict]:
    """Parsed reward rows (the shared native-tuple parser, unit metadata kept). Bad entries are skipped."""
    from exvius_rewards import parse
    out = []
    for entry in raw(mid).split(","):
        if not entry.strip():
            continue
        try:
            out.extend(parse(entry))
        except ValueError as exc:
            print(f"first-clear: mission {mid}: entry {entry!r} skipped ({exc})", flush=True)
    return out


def ledger(player) -> dict:
    """This save's record: `baseline` (clears that predate the feature) and `paid` (missions paid).

    Created on first use with the save's cleared missions as the baseline, so missions cleared before the
    feature existed never pay through a replay; only `backpay` can pay those.
    """
    led = player.data.get(LEDGER)
    if not isinstance(led, dict):
        led = {"baseline": list(player.data.get("progress", {}).get("cleared_missions", [])), "paid": []}
        player.data[LEDGER] = led
        player.dirty = True
    led.setdefault("baseline", [])
    led.setdefault("paid", [])
    return led


def is_due(player, mid) -> bool:
    led = player.data.get(LEDGER)
    if not isinstance(led, dict):
        return str(mid) not in player.data.get("progress", {}).get("cleared_missions", [])
    return str(mid) not in led.get("paid", []) and str(mid) not in led.get("baseline", [])


def _succeeded(player, mid, plaintext) -> bool:
    from ffbe_battle import mission_result_from
    from player_state import mission_wave_count
    waves = mission_wave_count(mid)
    if waves is None:
        return False
    context = mission_result_from(plaintext)
    if waves == 0:
        return context.get("cleared") is not False
    attempt = player.data.get("exvius_repeat", {}).get("attempt", {})
    return (context.get("cleared") is True and attempt.get("mid") == str(mid)
            and attempt.get("status") == "completed" and attempt.get("cleared") is True)


def shown(rows) -> str:
    """The result screen's `p1K5NecV` text: `kind:id:count` per row, Lapis as credited (multiplier applied)."""
    from lapis_economy import earned
    from exvius_rewards import card_text
    return card_text(",".join(f"{r['kind']}:{r['id']}:{earned(r['count']) if r['kind'] == 50 else r['count']}"
                              for r in rows))


def grant(player, rows) -> tuple[list, list]:
    """Credit `rows`; returns (granted, skipped). Raises if a supported row doesn't credit (caller rolls back)."""
    granted, skipped = [], []
    for row in rows:
        if not player._can_credit(row):
            skipped.append(row)
            continue
        if player._grant_items([row]) != [row]:
            raise RuntimeError(f"first-clear reward {row['kind']}:{row['id']} did not credit")
        granted.append(row)
    return granted, skipped


def _extra_groups(spec, kinds, player):
    if 27 in kinds:
        spec["4hPYneL3"] = player.vision_card_rows()
    if 28 in kinds:
        from exvius_actions_shops import _point_rows
        spec["z36FApms"] = _point_rows()
    if kinds.intersection((90, 91)):
        from exvius_actions_shops import _switches
        spec = _switches(spec)
    return spec


def _show(spec, text):
    from ffbe_config import RESULT_TAG
    spec = copy.deepcopy(spec)
    for row in spec.get(RESULT_TAG, []):
        if isinstance(row, dict):
            row["p1K5NecV"] = text
    return spec


def pay(spec, mid, plaintext):
    """Pipeline step (MissionEnd reply, before `grant_cleared_mission`): pay a first clear and list it."""
    from ffbe_config import RESULT_TAG
    from ffbe_state import State
    player = State.player
    if (not enabled() or player is None or player.mode == "frozen" or not mid
            or not isinstance(spec, dict) or RESULT_TAG not in spec):
        return spec
    mid = str(mid)
    attempt = player.data.get("exvius_repeat", {}).get("attempt", {})
    led = player.data.get(LEDGER)
    last = led.get("last", {}) if isinstance(led, dict) else {}
    if last.get("mid") == mid and last.get("sequence") == attempt.get("sequence") and last.get("shown"):
        # Paid by this attempt already (a mode handler builds its own result after the pipeline ran).
        return _show(spec, last["shown"])
    if not raw(mid):
        return spec
    led = ledger(player)
    if mid in led["paid"] or mid in led["baseline"] or not _succeeded(player, mid, plaintext):
        return spec
    before, dirty_before = copy.deepcopy(player.data), player.dirty
    try:
        granted, skipped = grant(player, rewards(mid))
        led = ledger(player)
        led["paid"].append(mid)
        import story_recipes
        story_recipes.note_paid(player, mid)
        text = shown(granted)
        led["last"] = {"mid": mid, "sequence": attempt.get("sequence"), "shown": text}
        player.dirty = True
        State.state_dirty = True
    except Exception:
        player.data, player.dirty = before, dirty_before
        raise
    print(f"first-clear: mission {mid} paid {text or 'nothing'}"
          + (f"; skipped {','.join(str(r['kind']) + ':' + str(r['id']) for r in skipped)} (no projection)"
             if skipped else ""), flush=True)
    if not text:
        return spec
    spec = _show(spec, text)
    return _extra_groups(spec, {r["kind"] for r in granted}, player)


# --- Back-pay for clears made before first-clear rewards were paid (operator's choice, 2026-11-09) ---------
# One mail (split into parts of BACKPAY_PART attachments) with every unpaid first-clear reward of the missions
# in the save's baseline. Sent once per save, at login (same carrier replies as the weekly gift). Units keep
# their reward metadata (Trust Moogle targets) through the mail item's `meta`, which `receive_mail` merges.
# Lapis is mailed at its base amount and multiplied when received, like every other mailed Lapis.

BACKPAY_PART = 10
BACKPAY_TITLE = "First-Clear Rewards"


def backpay_enabled() -> bool:
    return enabled() and os.environ.get("EXVIUS_FIRST_CLEAR_BACKPAY", "1").strip() != "0"


def backpay_rows(player) -> tuple[list[str], list[dict]]:
    """(missions, rows): the baseline's unpaid missions with a first-clear reward, and their rewards merged.

    Plain rows of one kind/id are summed; rows with metadata (units, vision cards) stay one row each.
    Rows the save can't credit are left out (logged by the caller's count).
    """
    led = player.data.get(LEDGER) or {}
    paid = set(led.get("paid", []))
    missions, merged, extra = [], {}, []
    for mid in led.get("baseline", []):
        if mid in paid or not raw(mid):
            continue
        rows = [r for r in rewards(mid) if player._can_credit(r)]
        if not rows:
            continue
        missions.append(mid)
        for row in rows:
            if set(row) == {"kind", "id", "count"}:
                key = (row["kind"], row["id"])
                merged[key] = merged.get(key, 0) + row["count"]
            else:
                extra.append(row)
    rows = [{"kind": k, "id": i, "count": c} for (k, i), c in merged.items()] + extra
    return missions, rows


def deliver_backpay(spec, reply_id):
    """Pipeline step: mail the old clears' first-clear rewards once per save."""
    from ffbe_config import ANNIVERSARY_TICKET_CARRIER
    from ffbe_state import State
    player = State.player
    if (not backpay_enabled() or reply_id not in ANNIVERSARY_TICKET_CARRIER.split(",") or player is None
            or not isinstance(spec, dict) or player.mode == "frozen"):
        return spec
    led = ledger(player)
    if led.get("backpaid"):
        return spec
    missions, rows = backpay_rows(player)
    before, dirty_before = copy.deepcopy(player.data), player.dirty
    try:
        parts = [rows[i:i + BACKPAY_PART] for i in range(0, len(rows), BACKPAY_PART)]
        for n, part in enumerate(parts, 1):
            title = BACKPAY_TITLE + (f" ({n}/{len(parts)})" if len(parts) > 1 else "")
            entry = player.deliver_mail(
                title, [(r["kind"], r["id"], r["count"]) for r in part], mail_id=str(930000000000 + n),
                message=f"First-clear rewards for the {len(missions)} quest(s) you cleared before they "
                        "were paid. Lapis is multiplied when you receive it, like all earned Lapis.",
                icon_type=2, attach_type=1)
            if entry is None:
                raise RuntimeError("back-pay mail refused")
            for item, row in zip(entry["items"], part):
                meta = {k: v for k, v in row.items() if k not in ("kind", "id", "count")}
                if meta:
                    item["meta"] = meta
        led = ledger(player)
        led["paid"].extend(missions)
        led["backpaid"] = True
        import story_recipes
        for mid in missions:
            story_recipes.note_paid(player, mid)
        player.dirty = True
        State.state_dirty = True
    except Exception:
        player.data, player.dirty = before, dirty_before
        raise
    print(f"first-clear back-pay: {len(missions)} mission(s), {len(rows)} reward row(s) in "
          f"{(len(rows) + BACKPAY_PART - 1) // BACKPAY_PART} mail(s): "
          + ",".join(f"{r['kind']}:{r['id']}x{r['count']}" for r in rows), flush=True)
    return spec


# --- Missed first clears (operator, 2026-11-11: "Pay first-clear rewards (Lapis, items, units) for any quest the
# save has cleared but has no record of being paid, whichever build the clear happened on. Never pay twice") -----
# Any cleared quest (progress.cleared_missions) with a first-clear reward that is not in the ledger's `paid` list
# is paid by mail at login, after the one-time back-pay above, and recorded as paid. A unit reward is left out when
# the save already holds that unit (the clear's unit came some other way), a recipe when the save already owns it.
# EXVIUS_FIRST_CLEAR_MISSED: `1` (default, operator 2026-11-11) mails it, `0` turns it off, `preview` only logs what
# it would pay ("first-clear missed (preview)").
MISSED_TITLE = "Missed First-Clear Rewards"


def missed_mode() -> str:
    value = os.environ.get("EXVIUS_FIRST_CLEAR_MISSED", "1").strip().lower()
    return value if value in ("0", "1", "preview") else "1"


def missed_enabled() -> bool:
    return enabled() and missed_mode() != "0"


def missed_rows(player) -> tuple[list[str], list[dict]]:
    """(missions, rows): cleared quests with a first-clear reward this save has no record of being paid."""
    led = player.data.get(LEDGER) or {}
    paid = set(led.get("paid", []))
    held_units = {str(u.get("master_id")) for u in player.data.get("roster", [])}
    import story_recipes
    owned_recipes = story_recipes._owned_recipes(player)     # a story recipe already mailed or bought
    cleared = [str(m) for m in player.data.get("progress", {}).get("cleared_missions", [])]
    missions, merged, extra = [], {}, []
    for mid in dict.fromkeys(cleared):
        if mid in paid or not raw(mid):
            continue
        missions.append(mid)
        for row in rewards(mid):
            if row["kind"] == 10 and str(row["id"]) in held_units and not str(row["id"]).startswith("9"):
                # already holds that clear's unit. Not for enhancer units (ids 9xxxxxxxx: Trust Moogles, cactuars,
                # pots; 289 of the 296 unit first clears): they stack, so holding one says nothing about this clear.
                continue
            if row["kind"] == 60 and str(row["id"]) in owned_recipes:
                continue
            if not player._can_credit(row):
                continue
            if set(row) == {"kind", "id", "count"}:
                key = (row["kind"], row["id"])
                merged[key] = merged.get(key, 0) + row["count"]
            else:
                extra.append(row)
    rows = [{"kind": k, "id": i, "count": c} for (k, i), c in merged.items()] + extra
    return missions, rows


def deliver_missed(spec, reply_id):
    """Pipeline step (login carriers): mail first-clear rewards of cleared quests never paid."""
    from ffbe_config import ANNIVERSARY_TICKET_CARRIER
    from ffbe_state import State
    player = State.player
    if (not missed_enabled() or reply_id not in ANNIVERSARY_TICKET_CARRIER.split(",") or player is None
            or not isinstance(spec, dict) or player.mode == "frozen"):
        return spec
    led = player.data.get(LEDGER)
    if not isinstance(led, dict) or not led.get("backpaid"):
        return spec               # the one-time back-pay goes first (deliver_backpay)
    missions, rows = missed_rows(player)
    if not missions:
        return spec
    if missed_mode() == "preview":
        lapis = sum(r["count"] for r in rows if r["kind"] == 50)
        print(f"first-clear missed (preview, nothing mailed): {len(missions)} quest(s), {lapis} Lapis before the "
              f"multiplier, {len(rows)} reward row(s): "
              + ",".join(f"{r['kind']}:{r['id']}x{r['count']}" for r in rows), flush=True)
        return spec
    before, dirty_before = copy.deepcopy(player.data), player.dirty
    try:
        parts = [rows[i:i + BACKPAY_PART] for i in range(0, len(rows), BACKPAY_PART)]
        for n, part in enumerate(parts, 1):
            led["missed_mails"] = int(led.get("missed_mails", 0)) + 1
            title = MISSED_TITLE + (f" ({n}/{len(parts)})" if len(parts) > 1 else "")
            entry = player.deliver_mail(
                title, [(r["kind"], r["id"], r["count"]) for r in part],
                mail_id=str(932000000000 + led["missed_mails"]),
                message=f"First-clear rewards for {len(missions)} quest(s) you cleared that were never paid. "
                        "Lapis is multiplied when you receive it, like all earned Lapis.",
                icon_type=2, attach_type=1)
            if entry is None:
                raise RuntimeError("missed first-clear mail refused")
            for item, row in zip(entry["items"], part):
                meta = {k: v for k, v in row.items() if k not in ("kind", "id", "count")}
                if meta:
                    item["meta"] = meta
        led["paid"].extend(m for m in missions if m not in led["paid"])
        import story_recipes
        for mid in missions:
            story_recipes.note_paid(player, mid)
        player.dirty = True
        State.state_dirty = True
    except Exception:
        player.data, player.dirty = before, dirty_before
        raise
    print(f"first-clear missed: {len(missions)} quest(s), {len(rows)} reward row(s): "
          + ",".join(f"{r['kind']}:{r['id']}x{r['count']}" for r in rows), flush=True)
    return spec
