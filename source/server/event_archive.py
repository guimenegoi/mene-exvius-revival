"""Browse recovered Vortex content without changing mission progress or rewards."""
from collections import defaultdict
from copy import deepcopy
import json
from pathlib import Path

GROUPS = (('all', 'All Events'), ('permanent', 'Permanent'),
          ('season1', 'Season 1'), ('season2', 'Season 2'),
          ('season3', 'Season 3'), ('season4', 'Season 4'),
          ('collaborations', 'Collab'), ('other', 'Other Events'))
_DOCUMENT = None


_HISTORY = None
REPLAY_LOOKBACK_DAYS = 14   # first replay week: events still running when the replay starts


def history():
    """event_history.json: Global run dates the archive lacks (first runs, reruns) and events it lacks."""
    global _HISTORY
    if _HISTORY is None:
        try:
            _HISTORY = json.loads(Path(__file__).with_name('event_history.json').read_text(encoding='utf-8'))
        except (OSError, ValueError):
            _HISTORY = {}
    return _HISTORY


def document():
    """The archive, plus event_history.json's added events. Every row gets `runs`: all its Global run dates."""
    global _DOCUMENT
    if _DOCUMENT is None:
        path = Path(__file__).with_name('event_archive.json')
        document = json.loads(path.read_text(encoding='utf-8'))
        extra = history()
        document['events'] = document['events'] + [dict(row) for row in extra.get('added', [])]
        runs = extra.get('runs', {})
        for row in document['events']:
            dates = set(runs.get(str(row['area']), []))
            if row.get('release'):
                dates.add(str(row['release']))
            row['runs'] = sorted(dates)
            if str(row['area']) in extra.get('windows', {}):
                row['windows'] = extra['windows'][str(row['area'])]
        _DOCUMENT = document
    return _DOCUMENT


def events():
    return document()['events']


def area_ids():
    return [str(event['area']) for event in events()]


# Holiday-themed events: they open with the holiday banners (the week before the holiday and its week, the
# original year chosen the way gacha_rotation picks holiday sets), never on their history date. Picked by
# name and theme from the Global events that ran in each holiday's season; events that only launched beside a
# holiday set (story events, explorations) are not here and keep their history dates.
HOLIDAY_EVENTS = {
    'Christmas': {'906', '952', '992', '993', '1039', '1040', '1088', '1098', '9920', '9921'},
    'Easter': {'911', '9909', '962', '1056', '1057'},
    'Halloween': {'919', '921', '983', '986', '1033', '1034', '1081', '1082', '9910', '9911'},
    "Valentine's Day": {'1004', '1005'},
}
# Permanent Vortex areas themed for a holiday (Chamber of Challenges' Halloween and Christmas battles): they
# take their turn in the rotation only in that holiday's two weeks, and then ahead of the others.
HOLIDAY_PERMANENT = {'902': 'Halloween', '903': 'Halloween', '904': 'Halloween', '905': 'Christmas'}
HOLIDAY_SEASON = (-30, 14)   # days from the holiday: a holiday event's run in this range belongs to that year


def holiday_runs(row):
    """{run date: holiday} for a holiday event's runs in its holiday's season (HOLIDAY_EVENTS)."""
    from datetime import date
    import gacha_rotation
    out = {}
    for name, areas in HOLIDAY_EVENTS.items():
        if str(row.get('area')) not in areas:
            continue
        when = gacha_rotation.HOLIDAYS[name][0]
        for text in row.get('runs') or [row.get('release')]:
            try:
                run = date.fromisoformat(str(text or ''))
            except ValueError:
                continue
            if HOLIDAY_SEASON[0] <= (run - when(run.year)).days <= HOLIDAY_SEASON[1]:
                out[run] = name
    return out


_ART_KEYS = None


def art_key(row):
    """What a row's Vortex tile looks like: two rows with the same name and art key look identical."""
    global _ART_KEYS
    if _ART_KEYS is None:
        try:
            art = json.loads(Path(__file__).with_name('event_art.json').read_text(encoding='utf-8'))['events']
        except (OSError, ValueError, KeyError):
            art = {}
        _ART_KEYS = {area: info.get('runtime_sha256') or info.get('filename') for area, info in art.items()}
    area = str(row['area'])
    return _ART_KEYS.get(area) or row.get('art_url') or area


def _one_per_look(rows, pick):
    """Rows grouped by (name, art): pick(group) chooses the one tile each group keeps."""
    groups = {}
    for row in rows:
        groups.setdefault((row['name'], art_key(row)), []).append(row)
    keep = {id(pick(group)) for group in groups.values()}
    return [row for row in rows if id(row) in keep]


def rotation_enabled():
    """The Vortex follows the weekly summon rotation (EXVIUS_VORTEX_ROTATION, on with the summon rotation)."""
    import os
    return (os.environ.get('EXVIUS_SUMMON_ROTATION') == '1'
            and os.environ.get('EXVIUS_VORTEX_ROTATION', '1') == '1')


def weekly_events(rows=None, now=None):
    """This week's Vortex: the permanent dungeons, the events that ran beside this week's summon sets,
    and a few of the undated recurring events.

    Global launched most events on the same day as a summon set (478 of the 626 dated events here), and
    they were built to be played together: the event's featured units, its currency and its banner tickets
    belong to that set. So an event is open while a set released between 3 days after and 13 days before
    one of its runs is on the summon screen (`gacha_rotation.vortex_week`; holiday sets do not count). An
    event's runs are its release date plus the reruns and earlier first runs in event_history.json. Holiday
    events (HOLIDAY_EVENTS) follow the holiday banners instead: they open only in the week before and the
    week of their holiday, in the year the rotation picks, never on their history date. Undated,
    non-permanent events (Boss Rush, Cactuar Dunes, Challenge of the Brave, ...) rotate EXVIUS_VORTEX_EXTRA
    at a time (default 2). With the historical replay on (replay.py), events with a run in this week's
    slice of history are open too (the first week also reaches back REPLAY_LOOKBACK_DAYS, for events
    already running when the replay starts). An event opened by a later run is returned with `release`
    set to that run (`first_release` keeps the original), so the News board and home banners date it right.
    """
    import os
    import random
    from datetime import date, timedelta
    rows = events() if rows is None else rows
    if not rotation_enabled():
        return rows
    import gacha_rotation
    holiday_of_run = {id(row): holiday_runs(row) for row in rows}
    event_keys = {}
    for runs in holiday_of_run.values():
        for run, name in runs.items():
            event_keys.setdefault(name, []).append(run.isoformat())
    summons = gacha_rotation.vortex_week(now, event_keys)
    dates = summons['dates']
    number = gacha_rotation.week(now)[0]
    import replay
    import history_runs
    win = replay.window(now) if replay.enabled() else None
    if win and win['finished']:
        win = None
    earliest = win and (win['from'] - timedelta(days=REPLAY_LOOKBACK_DAYS) if win['index'] == 0 else win['from'])
    kept, extra, permanent, ranked = [], [], [], []
    for row in rows:
        windows = row.get('windows')
        if windows:
            # A ranked event Global ran in set periods (Dark Visions, Clash of Wills): open only while one of
            # them overlaps this week's history (replay), or else beside a set released near its start.
            opened = []
            for first, last in windows:
                start, end = date.fromisoformat(first), date.fromisoformat(last)
                if (start < win['to'] and end >= earliest if win else
                        any(timedelta(days=-3) <= start - d <= timedelta(days=13) for d in dates)):
                    opened.append(start)
            if opened:
                ranked.append(dict(row, release=max(opened).isoformat()))
            continue
        if row.get('group') == 'permanent':
            permanent.append(row)
            continue
        released = []
        for text in row.get('runs') or [row.get('release')]:
            try:
                released.append(date.fromisoformat(str(text or '')))
            except ValueError:
                pass
        full_runs = bool(win and history_runs.enabled())
        if not released and not (full_runs and history_runs.event_runs(row)):
            extra.append(row)        # undated: the random weekly few (content/event_runs.json dates some)
            continue
        holiday = holiday_of_run[id(row)]
        if full_runs:
            # EXVIUS_REPLAY_FULL_RUNS: open in every week one of its Global runs overlaps (history_runs.py);
            # holiday runs keep the holiday weeks.
            def holiday_name(start):
                return next((name for day, name in holiday.items() if abs((day - start).days) <= 3), None)
            opened = [start for start, last in history_runs.event_runs(row)
                      if (summons['holiday'] == holiday_name(start) and start.isoformat()[:4] in summons['years']
                          if holiday_name(start) else history_runs.overlaps((start, last), earliest, win['to']))]
            if opened:
                run = max(opened).isoformat()
                if str(row.get('area')) in history_runs.OPEN_ENDED:
                    # A feature kept open from its first run is one long run here; the quests Global added on
                    # its later dates come when history reaches them (only_existing_quests cuts at `release`).
                    started = [d for d in released if d < win['to']]
                    if started:
                        run = max(started).isoformat()
                kept.append(row if run == row.get('release') else
                            dict(row, release=run, first_release=row.get('release')))
            continue
        opened = [run for run in released
                  if (summons['holiday'] == holiday[run] and run.isoformat()[:4] in summons['years']
                      if run in holiday else
                      any(timedelta(days=-3) <= run - d <= timedelta(days=13) for d in dates)
                      or (win and earliest <= run < win['to']))]
        if opened:
            run = max(opened).isoformat()
            kept.append(row if run == row.get('release') else
                        dict(row, release=run, first_release=row.get('release')))
    try:
        per_week = max(0, int(os.environ.get('EXVIUS_VORTEX_EXTRA', '2')))
    except ValueError:
        per_week = 2
    if extra and per_week:
        names = sorted({row['name'] for row in extra})
        cycle, start = divmod(number * per_week, len(names))
        order = list(range(len(names)))
        random.Random(f'vortex-extra:{cycle}').shuffle(order)
        picked = {names[order[(start + i) % len(names)]] for i in range(min(per_week, len(names)))}
        # One tile per name: a name with several areas (Challenge of the Brave, Monthly Fortune Hunt, ...)
        # shows the next of them each time it comes round.
        for name in picked:
            variants = sorted((row for row in extra if row['name'] == name), key=lambda r: int(r['area']))
            kept.append(variants[cycle % len(variants)])
    # No two tiles that look the same. Permanent areas sharing a name and banner (Chamber of Challenges,
    # Chamber of Crysts) take turns, one a week; dated events sharing both (later copies of an event, kept
    # under new area ids) show the earliest area.
    def take_turns(group):
        themed = [r for r in group if HOLIDAY_PERMANENT.get(str(r['area'])) == summons['holiday']]
        plain = [r for r in group if str(r['area']) not in HOLIDAY_PERMANENT]
        pool = sorted(themed or plain or group, key=lambda r: int(r['area']))
        return pool[number % len(pool)]
    permanent = [row for row in permanent if str(row['area']) not in HOLIDAY_PERMANENT or
                 HOLIDAY_PERMANENT[str(row['area'])] == summons['holiday'] or
                 not any(r['name'] == row['name'] and str(r['area']) not in HOLIDAY_PERMANENT for r in permanent)]
    permanent = _one_per_look(permanent, take_turns)
    # Of a ranked event's runs overlapping this week, only the newest. Where Global ran two at once (two Clash
    # of Wills bosses on the same dates, with the same banner), they take turns a week each.
    newest = {}
    for row in ranked:
        newest[row['name']] = max(newest.get(row['name'], ''), row['release'])
    ranked = [row for row in ranked if row['release'] == newest[row['name']]]
    ranked = _one_per_look(ranked, lambda group: sorted(group, key=lambda r: int(r['area']))[number % len(group)])
    dated = _one_per_look(kept, lambda group: min(group, key=lambda r: int(r['area'])))
    # Events first (the Vortex lists tiles in this order, see ffbe_player.serve_event_gate): holiday events, then
    # the rest newest first, then the ranked events, then the permanent dungeons.
    holiday_areas = {area for areas in HOLIDAY_EVENTS.values() for area in areas}
    dated.sort(key=lambda r: (str(r['area']) in holiday_areas, str(r.get('release') or ''), int(r['area'])),
               reverse=True)
    return hide_clone_quests(only_existing_quests([row for row in dated + ranked + permanent
                                                   if str(row.get('area')) not in hidden_areas()], win))



# --- only the quests that existed in that run (operator's request, 2026-11-10) -----------------------
# An open event used to serve every quest its area holds, including ones a later run added (Chamber of the
# Vengeful's 2024 "The Empress's Vengeance" in 2019, with its 8th Anniversary currency). content/
# event_quest_dates.json (ios-server/devtools/build_event_quest_dates.py, from Global's update history) dates
# the quests that came after their event's first run, and the permanent trial events (Chamber of Arms, of the
# Fallen, of the Vengeful, Training the Soul) by their first trial. A dated event serves a quest only if it
# ran by the run that opened it this week; a permanent event only once the replay's history has reached it,
# and not at all before its first trial. Ranked events (own periods) are unchanged. An event left with no
# quest is not opened. The quests held back are listed in `held_back` (the Vortex drops shipped rows for
# them). EXVIUS_EVENT_RUN_QUESTS=0 serves every quest, as before.
_QUEST_DATES = None


# Events kept out of the Vortex because they can't be played as Global ran them (operator, 2026-11-10).
# Memories from the Aquapolis (711): its five stage files (each stage's limits, boss trigger, end and chests,
# laid over the shared map) are lost from Global's tables, our data and the Japanese archive, so every stage
# played the bare map with no chests and no proper end (HANDOFF, "Memories from the Aquapolis"). Hidden from the
# Vortex, the News notices and the home banners (all use weekly_events). EXVIUS_HIDDEN_EVENTS lists the areas
# (comma-separated); 0 or empty hides nothing.
HIDDEN_EVENTS_DEFAULT = '711'


def hidden_areas():
    import os
    raw = str(os.environ.get('EXVIUS_HIDDEN_EVENTS', HIDDEN_EVENTS_DEFAULT)).strip()
    if raw.lower() in ('', '0', 'off', 'none', 'no'):
        return set()
    return {part.strip() for part in raw.split(',') if part.strip()}


def run_quests_enabled():
    import os
    return str(os.environ.get('EXVIUS_EVENT_RUN_QUESTS', '1')).strip().lower() not in ('0', 'off', 'false', 'no')


def quest_dates():
    global _QUEST_DATES
    if _QUEST_DATES is None:
        path = Path(__file__).with_name('content').joinpath('event_quest_dates.json')
        try:
            _QUEST_DATES = json.loads(path.read_text(encoding='utf-8'))
        except (OSError, ValueError):
            _QUEST_DATES = {}
    return _QUEST_DATES


def only_existing_quests(rows, win=None):
    """This week's rows with the quests of later runs left out (see above)."""
    if not run_quests_enabled():
        return rows
    from player_state import mission_row
    dates = quest_dates()
    first_trial, later = dates.get('events') or {}, dates.get('missions') or {}
    reached = win['to'].isoformat() if win else None
    out = []
    for row in rows:
        area = str(row['area'])
        if row.get('windows'):
            out.append(row)
            continue
        if row.get('group') == 'permanent':
            if reached is None:
                out.append(row)
                continue
            if first_trial.get(area, '') >= reached:
                continue
            cut, inclusive = reached, False
        else:
            cut, inclusive = str(row.get('release') or ''), True
            if not cut:
                out.append(row)
                continue
        quests = [str(m) for m in row.get('missions') or []]
        keep = [m for m in quests if m not in later or (later[m] <= cut if inclusive else later[m] < cut)]
        if len(keep) == len(quests):
            out.append(row)
            continue
        if not keep:
            continue
        dungeon = {m: str((mission_row(m) or {}).get('U9iHsau3') or '') for m in keep}
        kept_dungeons = [d for d in row.get('dungeons') or [] if d in set(dungeon.values())]
        out.append(dict(row, missions=keep, held_back=[m for m in quests if m not in keep],
                        dungeons=kept_dungeons or row.get('dungeons'), first_mission=keep[0],
                        first_dungeon=dungeon[keep[0]] or row.get('first_dungeon')))
    return out

# --- exact copies of a quest within one event (operator's request, 2026-11-10) -------------------------------
# Some events hold the same quest several times over (Chamber of Challenges' 930-933: up to six copies of each
# trial; Elemental Turn Challenge; Producer of the Crystal), all served at once. content/clone_quests.json
# (ios-server/devtools/build_clone_quests.py; report ios-server/research/CLONE_QUESTS.md) lists the copies that
# match the quest kept in every respect: quest row apart from its own switches, the battle, missions and
# first-clear rewards. They join `held_back`, so the Vortex leaves them out. EXVIUS_HIDE_CLONE_QUESTS=0 serves
# them again.
_CLONES = None


def clone_quests():
    """area -> {copy quest id: quest kept}."""
    global _CLONES
    if _CLONES is None:
        path = Path(__file__).with_name('content').joinpath('clone_quests.json')
        try:
            doc = json.loads(path.read_text(encoding='utf-8'))
            _CLONES = {area: dict(v.get('hidden') or {}) for area, v in (doc.get('areas') or {}).items()}
        except (OSError, ValueError):
            _CLONES = {}
    return _CLONES


def hide_clones_enabled():
    import os
    return str(os.environ.get('EXVIUS_HIDE_CLONE_QUESTS', '1')).strip().lower() not in ('0', 'off', 'false', 'no')


def hide_clone_quests(rows):
    if not hide_clones_enabled():
        return rows
    clones = clone_quests()
    out = []
    for row in rows:
        hidden = clones.get(str(row['area']))
        quests = [str(m) for m in row.get('missions') or []]
        if not hidden or not any(m in hidden for m in quests):
            out.append(row)
            continue
        keep = [m for m in quests if m not in hidden]
        out.append(dict(row, missions=keep,
                        held_back=list(row.get('held_back') or []) + [m for m in quests if m in hidden]))
    return out

# --- banners of the added events -------------------------------------------------------------------

def _art_folder():
    import os
    root = os.environ.get('CDN_ROOT')
    return os.path.join(root, 'en', 'sd', 'area') if root else None


def added_art_names():
    """File names of the added events' banners (ios_art packs those that are on disk)."""
    return [row['filename'] for row in history().get('added', []) if row.get('filename')]


def added_art(area):
    """The banner of an added event once its file is on disk, else None.

    A Vortex tile must never name art missing from the phone's banner pack (a null tile texture crashed
    the Enhance tab, see ios_art.py), so without the file the tile keeps the server's default art."""
    import os
    row = next((r for r in history().get('added', []) if str(r['area']) == str(area)), None)
    folder = _art_folder()
    if row and folder and os.path.isfile(os.path.join(folder, row['filename'])):
        return row['filename']
    return None


def fetch_added_art(log=print):
    """Download each added event's banner from the wiki into en/sd/area/ (once), as a 640x240 PNG. Only when
    EXVIUS_EVENT_ART_FETCH=1 asks for it: the banners are in the game data (the summon art pack carries them)."""
    import io
    import os
    import urllib.request
    if os.environ.get('EXVIUS_EVENT_ART_FETCH', '0') != '1':
        return 0
    folder = _art_folder()
    if not folder or not os.path.isdir(folder):
        return 0
    fetched = 0
    for row in history().get('added', []):
        path = os.path.join(folder, row['filename'])
        if os.path.isfile(path) or not row.get('art_url'):
            continue
        try:
            req = urllib.request.Request(row['art_url'] + '?format=original',
                                         headers={'User-Agent': 'Mozilla/5.0 (ExviusOffline event art)'})
            with urllib.request.urlopen(req, timeout=20) as resp:
                data = resp.read()
            if data[:8] != b'\x89PNG\r\n\x1a\n' or data[16:24] != (640).to_bytes(4, 'big') + (240).to_bytes(4, 'big'):
                from PIL import Image
                image = Image.open(io.BytesIO(data)).convert('RGBA').resize((640, 240))
                out = io.BytesIO()
                image.save(out, 'PNG')
                data = out.getvalue()
        except Exception as exc:  # noqa: BLE001 -- the tile keeps the default art; retried next start
            log(f"EVENT-ART {row['area']} {row['name']}: {exc}")
            continue
        with open(path + '.tmp', 'wb') as fh:
            fh.write(data)
        os.replace(path + '.tmp', path)
        fetched += 1
    if fetched:
        log(f'EVENT-ART downloaded {fetched} event banner(s) into {folder}')
    return fetched


def listings():
    """One tile per published campaign, with every original area retained."""
    campaigns = {}
    for row in events():
        identity = (row.get('source_page'), row.get('banner_title'),
                    row.get('release'), row.get('group'))
        # Unidentified records must never collapse merely because fields are empty.
        if not identity[0] or not identity[1]:
            identity = ('area', str(row['area']))
        campaigns.setdefault(identity, []).append(row)
    return [(rows[0], [str(row['area']) for row in rows[1:]])
            for rows in campaigns.values()]


def menu(player, selection=''):
    if ':' in selection:
        return activate_mode(player, selection)
    members = defaultdict(list)
    campaigns = listings()
    rows = [row for row, _aliases in campaigns]
    permanent = [str(row['area']) for row in rows if row['group'] == 'permanent']
    for row in rows:
        members[row['group']].append(str(row['area']))
    groups = []
    for key, label in GROUPS:
        ids = [str(row['area']) for row in rows] if key == 'all' else members[key]
        if key not in ('all', 'permanent'):
            ids = list(dict.fromkeys(permanent + ids))
        groups.append({'id': key, 'label': label, 'ids': ids,
                       'count': len(rows) if key == 'all' else len(members[key]), 'tab': 0})
    if selection:
        if selection not in {row['id'] for row in groups}:
            raise ValueError('Unknown event season')
        if player.data.get('event_archive') != selection:
            player.data['event_archive'] = selection
            player.dirty = True
    selected = player.data.get('event_archive', 'season1') if player else 'season1'
    group = next((row for row in groups if row['id'] == selected), groups[0])
    from player_state import _load_ndjson
    missions = _load_ndjson('F_MISSION_MST.ndjson', 'qo3PECw6')
    modes = {str(row['area']): row['native_mode'] for row in events() if row.get('native_mode')}
    mode_dungeon_ids = sorted({str(m['U9iHsau3']) for m in missions.values()
                               if str(m.get('uv60hgDW')) in modes})
    dungeons = {str(m['U9iHsau3']): {'mode': modes[str(m['uv60hgDW'])], 'area': str(m['uv60hgDW'])}
                for m in missions.values() if str(m.get('uv60hgDW')) in modes
                and str(m.get('gQR24kST')) in ('12', '50')}
    names = {}
    from exvius_fortuna import level_rewards
    cow = level_rewards()
    dark = sorted((r for r in events() if r['name'] == 'Dark Visions'), key=lambda r: int(r['area']))
    numbered = {r['area']: n for n, r in enumerate(dark, 1)}
    for row in events():
        candidates = [did for did in row['dungeons'] if did in dungeons]
        if not candidates:
            continue
        entry = candidates[0]
        for did in candidates:
            dungeons[did]['entry'] = did == entry
        names[entry] = (cow[row['area']]['name'] if row.get('native_mode') == 'tfa' else
                        'Dark Visions ' + str(numbered[row['area']]) if row['area'] in numbered else row['name'])
    return {'groups': groups, 'selected': group, 'area_ids': area_ids(),
            'native_modes': modes, 'native_dungeons': dungeons, 'dungeon_names': names,
            'mode_dungeon_ids': mode_dungeon_ids,
            'area_aliases': {str(row['area']): aliases for row, aliases in campaigns if aliases}}


def activate_mode(player, selection):
    """Select a preserved season before the original native mode scene opens."""
    from exvius_actions_modes import _tfa, _parade
    from player_state import _load_ndjson
    mode, did = selection.split(':', 1)
    allowed = {str(row['area']): row.get('native_mode') for row in events()}
    rows = [r for r in _load_ndjson('F_MISSION_MST.ndjson', 'qo3PECw6').values()
            if str(r.get('U9iHsau3')) == did and str(r.get('gQR24kST')) in ('12', '50')]
    if (player is None or player.mode == 'frozen' or not rows or mode not in ('tfa', 'parade')
            or any(allowed.get(str(r.get('uv60hgDW'))) != mode for r in rows)):
        raise ValueError('Unknown event season')
    area = str(rows[0]['uv60hgDW'])
    feature = deepcopy(player.data.get('exvius_' + mode, {}))
    if feature.get('active'):
        raise ValueError('Finish or retire the current battle first')
    if mode == 'tfa':
        _tfa(feature, did)
        party_kind = '11'
    else:
        _parade(feature, area, player)
        party_kind = '8'
    player.data['exvius_' + mode] = feature
    player.dirty = True
    groups = deepcopy(feature['groups'])
    groups.update(player.special_party_groups(party_kind))
    groups['8PEB5o7G'] = [{'r21y0YzS': str(player.data['party']['active_deck']),
                          'b61ICxJk': str(player.special_party('8')['active_deck'])
                          if mode == 'parade' else '0', 'Isc1ga3G': '-1', 'igrz05CY': '-1'}]
    result = {'mode': mode, 'area': area, 'dungeon': did,
              'native_groups': groups, 'scene': 940000 if mode == 'tfa' else 'parade'}
    if mode == 'tfa':
        event = next(r for r in groups['L6XRZb0z'] if str(r['U9iHsau3']) == did)
        ranking_id = str(event['L84eYzxv'])
        result['ranking_id'] = int(ranking_id)
        result['ranking_rewards'] = [r for r in _load_ndjson('F_SUMALLY_REWARD_MST.ndjson')['__rows__']
                                     if str(r['L84eYzxv']) == ranking_id]
        if not result['ranking_rewards']:
            raise ValueError('Clash ranking rewards are missing')
    return result
