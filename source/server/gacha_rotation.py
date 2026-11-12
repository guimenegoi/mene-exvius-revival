"""Weekly summon rotation: permanent summons plus a few release sets that change every week.

Turned on with EXVIUS_SUMMON_ROTATION=1. When it is on, the summon screen shows:

  * every permanent summon (Standard, Rare, Premium 10+1, 5-star Guaranteed 10+1, Arena,
    EXVIUS, NV EXVIUS, 5+1 Ticket, Friend), always;
  * this week's sets. A set is every banner that shares one release date in the archive, so a
    featured banner arrives together with the step-up, ticket or select banners that launched
    beside it. Each week shows EXVIUS_ROTATION_SPECIAL sets that contain a step-up, ticket,
    select or box banner (default 1) and EXVIUS_ROTATION_FEATURED other sets (default 2).

The week changes at EXVIUS_ROTATION_DAY / EXVIUS_ROTATION_HOUR in EXVIUS_ROTATION_TZ (default
Sunday 22:00 America/New_York, daylight saving included). Each list of sets is shuffled with a
fixed seed and walked in order, so no set repeats until every set of its kind has appeared; then
the next cycle uses a fresh shuffle. The choice depends only on the date, so it needs no scheduled
job: the server works it out on every request.

HOLIDAYS (EXVIUS_ROTATION_HOLIDAYS=1, the default). A set is a holiday set when it was originally released
in that holiday's season AND one of its banners carries the holiday's mark (a name like "Santa Roselia" or
"Grim Lord Sakura"; see HOLIDAYS). Holiday sets leave the random pool. Instead, the week before the holiday
and the week the holiday falls in show one original year's holiday sets, oldest year first: the first
Christmas you play gets the 2016 Christmas units, the next one 2017's, and so on, so the strongest holiday
units are not on offer in the first year. After the last year the order starts again.
EXVIUS_ROTATION_FIRST_WEEK lists release dates (set keys, e.g. 2016-12-16) to feature in the first
week the server serves summons; the week is recorded in state/summon_rotation.json. Those sets take
the first slots of their kind that week, and every later week is random as usual.

Preview from a shell:  python3 gacha_rotation.py --weeks 4
"""
from __future__ import annotations

import os
import random
from collections import OrderedDict
from datetime import date, datetime, timedelta
import re

try:
    from zoneinfo import ZoneInfo
except ImportError:  # pragma: no cover - Python < 3.9
    ZoneInfo = None

ANCHOR = datetime(2026, 1, 4)  # a Sunday; week 0 of the rotation starts on the rotation day of this week
_LOGGED_WEEK = [None]


def enabled() -> bool:
    return os.environ.get('EXVIUS_SUMMON_ROTATION') == '1'


def _int_env(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, default))
    except ValueError:
        return default


def settings() -> dict:
    return {
        'tz': os.environ.get('EXVIUS_ROTATION_TZ', 'America/New_York'),
        # Python weekday numbers: Monday 0 ... Sunday 6.
        'day': _int_env('EXVIUS_ROTATION_DAY', 6) % 7,
        'hour': _int_env('EXVIUS_ROTATION_HOUR', 22) % 24,
        'special': max(0, _int_env('EXVIUS_ROTATION_SPECIAL', 1)),
        'featured': max(0, _int_env('EXVIUS_ROTATION_FEATURED', 2)),
        'seed': os.environ.get('EXVIUS_ROTATION_SEED', 'exvius-weekly'),
    }


def _now(cfg: dict, now: datetime | None) -> datetime:
    zone = ZoneInfo(cfg['tz']) if ZoneInfo else None
    if now is None:
        return datetime.now(zone)
    if now.tzinfo is None and zone is not None:
        return now.replace(tzinfo=zone)
    return now.astimezone(zone) if zone is not None else now


def week(now: datetime | None = None, cfg: dict | None = None) -> tuple[int, datetime, datetime]:
    """(week number, this week's start, next change) as local times in the rotation's time zone."""
    cfg = cfg or settings()
    local = _now(cfg, now)
    days_back = (local.weekday() - cfg['day']) % 7
    start = (local - timedelta(days=days_back)).replace(hour=cfg['hour'], minute=0, second=0, microsecond=0)
    if start > local:
        start -= timedelta(days=7)
    # Rebuild the start in its own zone so daylight-saving changes keep the wall-clock hour.
    start = datetime(start.year, start.month, start.day, cfg['hour'], tzinfo=local.tzinfo)
    anchor = ANCHOR + timedelta(days=(cfg['day'] - ANCHOR.weekday()) % 7)
    number = (start.date() - anchor.date()).days // 7
    nxt = start + timedelta(days=7)
    nxt = datetime(nxt.year, nxt.month, nxt.day, cfg['hour'], tzinfo=local.tzinfo)
    return number, start, nxt


def _kind(banner: dict) -> str:
    if banner.get('selection'):
        return 'select'
    if banner.get('steps'):
        return 'step-up'
    if banner.get('deal'):
        return 'deal'      # gacha_deals.json: free dailies, once-per-player 10+1s, rate-ups...
    if banner.get('boxes'):
        return 'box'
    cost = banner.get('cost')
    cost = cost[0] if isinstance(cost, list) and cost else cost
    if isinstance(cost, dict) and cost.get('kind') in ('ticket', 'important', 'item'):
        return 'ticket'
    return 'featured'


def _easter(year: int) -> date:
    """Western Easter (anonymous Gregorian algorithm)."""
    a, b, c = year % 19, year // 100, year % 100
    d, e = b // 4, b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = c // 4, c % 4
    m = (32 + 2 * e + 2 * i - h - k) % 7
    n = (a + 11 * h + 22 * m) // 451
    month, day = divmod(h + m - 7 * n + 114, 31)
    return date(year, month, day + 1)


# name: (holiday date in a year, how far before/after it the original sets were released (days), the mark).
HOLIDAYS = {
    'Valentine\'s Day': (lambda y: date(y, 2, 14), (-21, 3),
                         re.compile(r"valentine|white day|sakura & ayaka|sieghard & ignacio|cupid|sweet (luka|nichol)", re.I)),
    'Easter': (_easter, (-21, 7), re.compile(r"easter|egg|bunny", re.I)),
    'Halloween': (lambda y: date(y, 10, 31), (-16, 3),
                  re.compile(r"halloween|hallowe|grim lord|dracu|demon rain|black cat|pumpkin|lilith|full moon",
                             re.I)),
    'Christmas': (lambda y: date(y, 12, 25), (-18, 8),
                  re.compile(r"christmas|santa|holiday|xmas|winter|white knight noel|kryla", re.I)),
}


def holidays_enabled() -> bool:
    return os.environ.get('EXVIUS_ROTATION_HOLIDAYS', '1') == '1'


def holiday_of(key: str, names: list) -> str | None:
    """The holiday a set belongs to, from its original release date and its banners' names."""
    try:
        released = date.fromisoformat(key)
    except ValueError:
        return None
    for holiday, (when, (before, after), mark) in HOLIDAYS.items():
        day = when(released.year)
        if before <= (released - day).days <= after and any(mark.search(n or '') for n in names):
            return holiday
    return None


def _holiday_this_week(start: datetime, nxt: datetime):
    """(holiday, its date, 0 or 1) when this is the week before a holiday (0) or the week it falls in (1)."""
    for holiday, (when, _window, _mark) in HOLIDAYS.items():
        for year in (start.year, start.year + 1):
            day = when(year)
            noon = datetime(day.year, day.month, day.day, 12, tzinfo=start.tzinfo)
            if start <= noon < nxt:
                return holiday, day, 1
            if start + timedelta(days=7) <= noon < nxt + timedelta(days=7):
                return holiday, day, 0
    return None


def _jp_only(ids: list, by_id: dict) -> bool:
    """A set made only of JP banners (translated from the JP calendar): not part of Global's history."""
    return all(str(by_id[bid].get('source', '')).startswith('translated-jp') for bid in ids)


def _replay_holiday_years(entries: list, name: str, day: date, slot: int, anchor: int, tz) -> list:
    """The original years of `name` to show this week in the replay.

    Walks every real occurrence of the holiday since replay week 0: each shows the years the replay has
    gone past without showing, plus the next one ahead of it. Once every year has been shown, they start
    again. Several years are split: the older ones the week before, the rest in the holiday's week."""
    import replay
    years = sorted({key[:4] for key, _ids in entries})
    first_day = {y: min(key for key, _ids in entries if key[:4] == y) for y in years}
    when = HOLIDAYS[name][0]
    shown: set = set()
    pick: list = []
    year = day.year - 12
    while year <= day.year:
        occurrence = when(year)
        year += 1
        noon = datetime(occurrence.year, occurrence.month, occurrence.day, 12, tzinfo=tz)
        holiday_week = week(noon)[0]
        if holiday_week - anchor < 0:
            continue
        reached = replay.historical_start(max(0, holiday_week - 1 - anchor)).isoformat()
        pending = [y for y in years if y not in shown]
        if not pending:
            shown, pending = set(), list(years)
        pick = [y for y in pending if first_day[y] <= reached]
        # The next year ahead, unless it is more than a year ahead of history (a holiday some early years
        # never had would otherwise bring much later units).
        horizon = (date.fromisoformat(reached) + timedelta(days=365)).isoformat()
        ahead = [y for y in pending if reached < first_day[y] <= horizon]
        if ahead:
            pick.append(ahead[0])
        shown |= set(pick)
        if occurrence == day:
            break
    if len(pick) > 1:
        half = (len(pick) + 1) // 2
        pick = pick[:half] if slot == 0 else pick[half:]
    return pick


def pools(banners: list) -> tuple[list, list, list, dict]:
    """(permanent ids, special sets, featured sets, banners by id), in the archive's own order.

    Uses the summon archive's de-duplication, so a banner and its calendar alias count once."""
    from gacha_archive import catalogue, permanent, _released, _standard_families
    by_id = {str(b['id']): b for b in banners}
    families = _standard_families()
    seen, ordered = set(), []
    for group in catalogue(banners):
        for bid in group['ids']:
            if bid not in seen:
                seen.add(bid)
                ordered.append(bid)
    fixed = [bid for bid in ordered if permanent(by_id[bid], families)]
    sets: OrderedDict[str, list] = OrderedDict()
    for bid in ordered:
        if bid in fixed:
            continue
        released = _released(by_id[bid])
        key = released.isoformat() if released else 'undated-' + bid
        sets.setdefault(key, []).append(bid)
    special, featured = [], []
    for key, ids in sets.items():
        entry = (key, ids)
        if any(_kind(by_id[bid]) != 'featured' for bid in ids):
            special.append(entry)
        else:
            featured.append(entry)
    return fixed, special, featured, by_id


def _pick(entries: list, per_week: int, number: int, seed: str, label: str) -> list:
    """Walk a shuffled cycle of `entries`, `per_week` at a time; reshuffle for every new cycle."""
    if not entries or per_week <= 0:
        return []
    count = len(entries)
    keys = sorted(entries, key=lambda entry: entry[0])
    chosen, used = [], set()
    for slot in range(per_week):
        position = number * per_week + slot
        cycle, index = divmod(position, count)
        order = list(range(count))
        random.Random(f'{seed}:{label}:{cycle}').shuffle(order)
        entry = keys[order[index]]
        if entry[0] not in used:
            used.add(entry[0])
            chosen.append(entry)
    return chosen


def _first_week_file() -> str:
    import data_paths
    return os.path.join(data_paths.STATE_DIR, 'summon_rotation.json')


def first_week(current: int, record: bool) -> int:
    """The rotation week this save started in. Recorded the first time banners are served, so the
    EXVIUS_ROTATION_FIRST_WEEK sets appear in the first week you actually play, whenever that is."""
    import json
    path = _first_week_file()
    try:
        with open(path, encoding='utf-8') as fh:
            return int(json.load(fh)['first_week'])
    except (OSError, ValueError, KeyError, TypeError):
        pass
    if record:
        try:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, 'w', encoding='utf-8') as fh:
                json.dump({'first_week': current}, fh)
        except OSError:
            pass
    return current


def _pinned(cfg: dict) -> list:
    return [key.strip() for key in os.environ.get('EXVIUS_ROTATION_FIRST_WEEK', '').split(',') if key.strip()]


def plan(banners: list, now: datetime | None = None, record: bool = False, first: int | None = None,
         anchor: int | None = None) -> dict:
    """This week's rotation: its number, start and end, and the sets on offer."""
    cfg = settings()
    number, start, nxt = week(now, cfg)
    fixed, special, featured, by_id = pools(banners)
    import replay
    win = replay.window(now, record=record, anchor=anchor) if replay.enabled() else None
    if win and win['finished']:
        win = None
    if win:
        special = [entry for entry in special if not _jp_only(entry[1], by_id)]
        featured = [entry for entry in featured if not _jp_only(entry[1], by_id)]
    holiday_sets = {}
    if holidays_enabled():
        def split(entries):
            kept = []
            for key, ids in entries:
                holiday = holiday_of(key, [by_id[bid].get('name', '') for bid in ids])
                if holiday:
                    holiday_sets.setdefault(holiday, []).append((key, ids))
                else:
                    kept.append((key, ids))
            return kept
        special, featured = split(special), split(featured)
    if win:
        return _replay_plan(number, start, nxt, fixed, special, featured, by_id, holiday_sets, win)
    from gacha_archive import permanent_open
    fixed = [bid for bid in fixed if permanent_open(by_id[bid])]
    picked_special = _pick(special, cfg['special'], number, cfg['seed'], 'special')
    picked_featured = _pick(featured, cfg['featured'], number, cfg['seed'], 'featured')
    pins = _pinned(cfg)
    if pins and number == (first if first is not None else first_week(number, record)):
        # The opening week: the chosen sets take the first slots of their kind; the rest stay random.
        pinned_special = [entry for entry in special if entry[0] in pins]
        pinned_featured = [entry for entry in featured if entry[0] in pins]
        keys = {entry[0] for entry in pinned_special + pinned_featured}
        picked_special = pinned_special + [e for e in picked_special if e[0] not in keys][
            :max(0, cfg['special'] - len(pinned_special))]
        picked_featured = pinned_featured + [e for e in picked_featured if e[0] not in keys][
            :max(0, cfg['featured'] - len(pinned_featured))]
        sets = pinned_special + pinned_featured + [e for e in picked_special + picked_featured if e[0] not in keys]
    else:
        sets = picked_special + picked_featured
    holiday = _holiday_this_week(start, nxt) if holiday_sets else None
    if holiday and holiday[0] in holiday_sets:
        name, day, _slot = holiday
        # The n-th time this holiday comes round since the save's first week shows the n-th original year.
        first_number = first if first is not None else first_week(number, record=False)
        first_start = start - timedelta(days=7 * (number - first_number))
        first_day = HOLIDAYS[name][0](first_start.year)
        if first_day <= first_start.date():
            first_day = HOLIDAYS[name][0](first_start.year + 1)
        occurrence = max(0, day.year - first_day.year)
        years = sorted({key[:4] for key, _ids in holiday_sets[name]})
        year = years[occurrence % len(years)]
        chosen = [entry for entry in sorted(holiday_sets[name]) if entry[0][:4] == year]
        sets = chosen + [entry for entry in sets if entry[0] not in {k for k, _ in chosen}]
    return {'week': number, 'starts': start, 'ends': nxt, 'permanent': fixed, 'sets': sets,
            'by_id': by_id, 'pool_sizes': {'special': len(special), 'featured': len(featured)},
            'holiday': holiday[0] if holiday and holiday[0] in holiday_sets else None,
            'holiday_sets': {name: [key for key, _ids in entries] for name, entries in holiday_sets.items()}}


def _replay_plan(number, start, nxt, fixed, special, featured, by_id, holiday_sets, win) -> dict:
    """The replay's week: every set released in this week's slice of history, plus holiday sets."""
    import replay
    import history_runs
    begin, end = win['from'].isoformat(), win['to'].isoformat()
    if history_runs.enabled():
        # EXVIUS_REPLAY_FULL_RUNS: every banner whose Global run overlaps this week's slice (history_runs.py);
        # a set shows with those of its banners that are still running.
        sets = []
        for key, ids in sorted(special + featured):
            running = [bid for bid in ids
                       if (run := history_runs.banner_run(by_id[bid])) and history_runs.overlaps(
                           run, win['from'], win['to'])]
            if running:
                sets.append((key, running))
    else:
        sets = sorted(entry for entry in special + featured if begin <= entry[0] < end)
    holiday = _holiday_this_week(start, nxt) if holiday_sets else None
    shown_holiday = None
    if holiday and holiday[0] in holiday_sets:
        name, day, slot = holiday
        years = _replay_holiday_years(holiday_sets[name], name, day, slot, win['anchor'], start.tzinfo)
        chosen = [entry for entry in sorted(holiday_sets[name]) if entry[0][:4] in years]
        if chosen:
            shown_holiday = name
            sets = chosen + [entry for entry in sets if entry[0] not in {k for k, _ in chosen}]
    if win['to'] <= replay.nv_era():
        fixed = [bid for bid in fixed if 'NV' not in str(by_id[bid].get('name', ''))]
    from gacha_archive import permanent_open
    fixed = [bid for bid in fixed if permanent_open(by_id[bid], win['from'], win['to'])]
    return {'week': number, 'starts': start, 'ends': nxt, 'permanent': fixed, 'sets': sets,
            'by_id': by_id, 'pool_sizes': {'special': len(special), 'featured': len(featured)},
            'holiday': shown_holiday, 'replay': win,
            'holiday_sets': {name: [key for key, _ids in entries] for name, entries in holiday_sets.items()}}


def vortex_week(now: datetime | None = None, event_keys: dict | None = None) -> dict:
    """What the Vortex needs from this week's summons (event_archive.weekly_events).

    dates: original release dates of this week's sets that are not holiday sets.
    holiday: the holiday whose week (or week before) this is, if any.
    years: the original years of that holiday whose events open this week. They are picked the way the
    holiday's sets are (_replay_holiday_years in the replay, otherwise the years of the sets on offer), with
    the years the holiday's events ran in (event_keys: holiday -> run dates) counted beside the sets' years,
    so a year that had holiday events but no holiday units still comes round.
    """
    from ffbe_gacha import all_banners
    current = plan(all_banners(), now)
    held = {key for keys in current['holiday_sets'].values() for key in keys}
    dates = []
    for key, _ids in current['sets']:
        if key in held:
            continue
        try:
            dates.append(date.fromisoformat(key))
        except ValueError:
            pass
    out = {'dates': dates, 'holiday': None, 'years': set()}
    if not holidays_enabled():
        return out
    number, start, nxt = week(now)
    holiday = _holiday_this_week(start, nxt)
    if not holiday:
        return out
    name, day, slot = holiday
    keys = sorted(set(current['holiday_sets'].get(name, [])) | set((event_keys or {}).get(name, [])))
    if not keys:
        return out
    win = current.get('replay')
    if win:
        years = _replay_holiday_years([(key, None) for key in keys], name, day, slot, win['anchor'], start.tzinfo)
    else:
        years = [key[:4] for key, _ids in current['sets'] if key in current['holiday_sets'].get(name, [])]
    out.update(holiday=name, years=set(years))
    return out


def set_dates(now: datetime | None = None) -> list:
    """Original release dates of this week's sets (for the Vortex rotation, event_archive.weekly_events)."""
    from ffbe_gacha import all_banners
    out = []
    for key, _ids in plan(all_banners(), now)['sets']:
        try:
            out.append(date.fromisoformat(key))
        except ValueError:
            pass
    return out


def rotation_ids(banners: list, now: datetime | None = None) -> list:
    """Banner ids to show this week: the permanent summons, then this week's sets."""
    current = plan(banners, now, record=True)
    ids = list(current['permanent'])
    for _key, members in current['sets']:
        ids.extend(bid for bid in members if bid not in ids)
    if _LOGGED_WEEK[0] != current['week']:
        _LOGGED_WEEK[0] = current['week']
        names = '; '.join(f"{key}: " + ', '.join(current['by_id'][bid].get('name', bid) for bid in members)
                          for key, members in current['sets'])
        print(f"summon rotation week {current['week']} "
              f"({current['starts']:%a %Y-%m-%d %H:%M %Z} to {current['ends']:%a %Y-%m-%d %H:%M %Z}): "
              f"{len(current['permanent'])} permanent + {names}", flush=True)
    return ids


def describe(banners: list, weeks: int = 1, now: datetime | None = None) -> str:
    cfg = settings()
    number, start, _nxt = week(now, cfg)
    first = first_week(number, record=False)
    lines = []
    for offset in range(weeks):
        moment = start + timedelta(days=7 * offset, hours=1)
        current = plan(banners, moment, first=first)
        lines.append(f"Week {current['week']}: {current['starts']:%a %b %d %I:%M %p %Z} "
                     f"to {current['ends']:%a %b %d %I:%M %p %Z}"
                     + (f"  [{current['holiday']}]" if current['holiday'] else ''))
        if offset == 0:
            lines.append('  Always: ' + ', '.join(current['by_id'][b].get('name', b) for b in current['permanent']))
        for key, members in current['sets']:
            lines.append(f'  Set released {key}:')
            for bid in members:
                banner = current['by_id'][bid]
                lines.append(f"    [{_kind(banner)}] {banner.get('name', bid)} (id {bid})")
    sizes = plan(banners, now)['pool_sizes']
    lines.append(f"Pool: {sizes['special']} sets with step-up/ticket/select/box banners, "
                 f"{sizes['featured']} featured-only sets.")
    held = plan(banners, now)['holiday_sets']
    for name, keys in held.items():
        lines.append(f"{name} sets (the week before {name} and its own week, oldest first): {', '.join(sorted(keys))}")
    return '\n'.join(lines)


def main(argv=None) -> int:
    import argparse
    parser = argparse.ArgumentParser(description='Preview the weekly summon rotation.')
    parser.add_argument('--weeks', type=int, default=1, help='how many weeks to show, starting now')
    args = parser.parse_args(argv)
    for name, value in (('GACHA_ONLY', 'all'), ('GACHA_CAMPAIGN', 'all'), ('EXVIUS_SUMMON_ARCHIVE', '1'),
                        ('GACHA_STANDARD', '1'), ('GACHA_CATALOGUE', '1')):
        os.environ.setdefault(name, value)
    from ffbe_gacha import all_banners
    print(describe(all_banners(), max(1, args.weeks)))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
