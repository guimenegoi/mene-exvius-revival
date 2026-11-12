"""Native chest master rows and durable settlement of reported treasure IDs."""
from functools import lru_cache
from copy import deepcopy
import json
from pathlib import Path

from ffbe_state import State, _note
from player_state import switch_position

GROUP = 'pDFgB3i0'
RESULT = '09HRWXDf'
# MissionResultResponse::readParam in the pinned GL9 libgame.so. These are
# category-5 treasure channels, each containing kind:id:count triples.
CHEST_CHANNELS = {20: 'Z7G0yxXe', 21: 'Mh1BA4uv', 22: '30u6XYiB', 23: '95JxZzuG'}


def _rows(request, group):
    rows = request.get(group)
    return [row for row in rows if isinstance(row, dict)] if isinstance(rows, list) else []


def _credit(iid, row):
    player = State.player
    credited = player.data.get('exvius_field_treasures', [])
    if iid in credited:
        return False
    # Preserved prototype and retail rows can name the same global chest.
    # Mission results report reward/switch tuples, so those aliases must not
    # turn one reported chest into multiple inventory grants.
    if row['switch'] and any(
            old.get('switch') == row['switch'] and old.get('rewards') == row['rewards']
            for key in credited for old in [catalogue().get(str(key), {})]):
        return False
    rewards = [{'kind': int(k), 'id': int(i), 'count': int(n)}
               for k, i, n in (entry.split(':') for entry in row['rewards'].split(','))]
    if not all(player._can_credit(reward) for reward in rewards):
        _note('field treasure: unprojectable reward for ' + iid)
        return False
    if player._grant_items(rewards) != rewards:
        raise RuntimeError('partial field treasure grant')
    player.data.setdefault('exvius_field_treasures', []).append(iid)
    pos = switch_position(row['switch'])
    if pos:
        player.grant_switch(*pos)
    player.dirty = True
    print('field treasure: credited ' + iid + ' ' + row['rewards'], flush=True)
    return True


REPORT_CHANNELS = (*CHEST_CHANNELS.values(), 'R1kg3EBA')


def reported_tuples(result: dict) -> set:
    """Every `kind:id:count:switch` the phone reported as opened, from all chest channels."""
    return {entry for channel in REPORT_CHANNELS
            for entry in str((result or {}).get(channel) or '').split(',') if entry}


def _mission_treasures(out, request):
    nodes = _rows(request, 'jQsE54Iz')
    results = _rows(request, RESULT)
    if not nodes or not results or RESULT not in out:
        return out
    attempt = State.player.data.get('exvius_repeat', {}).get('attempt', {})
    mid = str(nodes[0].get('qo3PECw6') or '')
    # This transform follows normal reward credit and completion in the pipeline.
    # Walking out of an exploration settles treasures with cleared=False too.
    # The matching loaded result, exact reward and opening switch are required.
    if (attempt.get('mid') != mid or attempt.get('status') != 'completed'
            or not attempt.get('normal_rewards_recorded')):
        return out
    # Opened-chest tuples arrive per kind (`MissionResultInfoBase::toJsonGroup`, GL): items Z7G0yxXe, equipment
    # Mh1BA4uv, materia 30u6XYiB, key items 95JxZzuG (CHEST_CHANNELS); R1kg3EBA is also read. Until 2026-11-12
    # only Z7G0yxXe and R1kg3EBA were read, so equipment, materia and key-item chests opened but never paid.
    reported = reported_tuples(results[0])
    opened = set(str(nodes[0].get('dIPkNn61') or '').split(','))
    display = {}
    for iid, row in catalogue().items():
        missions = set(map(str, row.get('missions', [])))
        if row.get('mission'):
            missions = {str(row['mission'])}
        if missions and mid not in missions:
            continue
        if not missions and (row.get('town') or row.get('towns')):
            continue
        if row['switch'] and str(row['switch']) not in opened:
            continue
        entries = row['rewards'].split(',')
        if not all(entry + ':' + str(row['switch']) in reported for entry in entries):
            continue
        if any(int(entry.split(':')[0]) not in (*CHEST_CHANNELS, 30, 50, 51, 60) for entry in entries):
            continue
        if _credit(iid, row):
            attempt.setdefault('field_treasures', []).append(iid)
        # A retry can repeat its result display but cannot pay a second time.
        if iid not in attempt.get('field_treasures', []):
            continue
        for entry in entries:
            kind, item, count = map(int, entry.split(':'))
            if kind in (30, 50, 51):
                continue  # authoritative currency totals come from PlayerState
            channel = 'eAM5B1qt' if kind == 60 else CHEST_CHANNELS[kind]
            # In THIS group eAM5B1qt is recipe ID CSV, not the ownership bitmap.
            display.setdefault(channel, []).append(str(item) if kind == 60 else entry)
    if display:
        out = deepcopy(out)
        for result in out[RESULT]:
            if isinstance(result, dict):
                for channel, entries in display.items():
                    result[channel] = ','.join(entries)
    return out


@lru_cache(maxsize=1)
def catalogue():
    path = Path(__file__).with_name('content') / 'field_treasures.json'
    rows = json.loads(path.read_text(encoding='utf8'))['treasures']
    return {str(row['id']): row for row in rows}


def serve(spec, plaintext, reply_id=None):
    """The GL9 script otherwise skips rewards when FieldTreasureMst is absent."""
    if not isinstance(spec, dict) or State.player is None:
        return spec
    out = dict(spec)
    if reply_id is None or reply_id in {'75fYdNxq', 'X07iYtp5', '6H1R9WID', 'jnw49dUq'}:
        out[GROUP] = [{'4tNM5fGC': iid, '1IdhQ3Rw': '1', 'NiG2wL3A': row['rewards'],
                       'juA0Z4m7': str(row['switch']), 'dIPkNn61': str(row['switch'])}
                      for iid, row in catalogue().items()]
    try:
        req = json.JSONDecoder().raw_decode(plaintext)[0] if plaintext else {}
    except (ValueError, TypeError):
        return out
    if not isinstance(req, dict) or State.player.mode == 'frozen':
        return out
    # GL9 TownUpdateRequest::createBody: NiG2wL3A is TreasureGetInfoList::toCsv.
    before, dirty_before = deepcopy(State.player.data), State.player.dirty
    try:
        return _settle(out, req)
    except Exception:
        State.player.data, State.player.dirty = before, dirty_before
        raise


def _settle(out, req):
    for node in _rows(req, 'JcxS6A8N'):
        for iid in str(node.get('NiG2wL3A') or '').split(','):
            row = catalogue().get(iid)
            if row is None:
                if iid:
                    _note('field treasure: missing reward definition for ' + iid)
                continue
            towns = set(map(str, row.get('towns', [])))
            if row.get('town'):
                towns = {str(row['town'])}
            if not towns and (row.get('mission') or row.get('missions')):
                continue
            if towns and str(node.get('Gh92V3Tx')) not in towns:
                _note('field treasure: town mismatch for ' + iid)
                continue
            if not towns:
                from exvius_actions import _mst
                if str(node.get('Gh92V3Tx')) not in _mst('F_TOWN_MST.ndjson', 'Gh92V3Tx'):
                    continue
            _credit(iid, row)
    return _mission_treasures(out, req)
