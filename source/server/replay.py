"""Historical replay: the summons, the Vortex and the shops follow Global's own history, week by week.

Turned on with EXVIUS_REPLAY=1 (needs EXVIUS_SUMMON_ROTATION=1). The first week the server serves summons
with replay on becomes replay week 0 and shows what Global released from EXVIUS_REPLAY_START (default
2016-12-16, the Noctis week). Every later week moves history on by EXVIUS_REPLAY_PACE weeks:

    EXVIUS_REPLAY_PACE=3,2@2020-08-20   three historical weeks per real week, then two from 2020-08-20

2020-08-20 is Global's first Neo Vision banner (Cloud, FFVII Remake), the biggest jump in power the game had.

Each real week shows:
  * every banner set Global released in that week's slice of history (holiday sets excepted, see below);
  * the permanent summons, with their pools limited to units released by the end of the slice. NV EXVIUS
    stays hidden until the NV era (EXVIUS_REPLAY_NV_ERA, default 2020-08-20);
  * the Vortex events that launched with those sets (event_archive.weekly_events);
  * exchange shops without the units that have not come out yet (exvius_shop_catalogue).

Holiday sets (gacha_rotation.HOLIDAYS) leave the timeline and run in the week before each real holiday and
the holiday's own week. Each holiday shows the next original year that has not been shown (if it is less
than a year ahead of history), plus any earlier years the replay went past without showing (more history
passes than real time, so some years would otherwise be skipped). With more than one year, the older ones
run in the first week and the rest in the holiday week. A holiday set shown ahead of history offers its
featured units; the rest of its pool stays at this week's point in history.

When history runs out (after the last Global set), the normal random weekly rotation takes over, with
every unit.

A unit's release date is the first Global banner that featured it (unit_release.json, written by
`python3 replay.py --write-units`). Units no banner featured get the date of the next dated unit of the
same game series, so a reward unit is never early. Where Global's own update history (the FFBE wiki) dates
a unit earlier than that, its date wins (global_release_fixes, 2026-11-10).

The replay's week 0 is stored in state/replay.json. Delete that file to start over from EXVIUS_REPLAY_START.

Preview from a shell:  python3 replay.py --weeks 8
"""
from __future__ import annotations

import json
import os
from datetime import date, datetime, timedelta

_HERE = os.path.dirname(os.path.abspath(__file__))
UNITS_FILE = os.path.join(_HERE, 'unit_release.json')
_CACHE: dict = {}


def enabled() -> bool:
    import gacha_rotation
    return os.environ.get('EXVIUS_REPLAY') == '1' and gacha_rotation.enabled()


def start_date() -> date:
    try:
        return date.fromisoformat(os.environ.get('EXVIUS_REPLAY_START', '2016-12-16'))
    except ValueError:
        return date(2016, 12, 16)


def nv_era() -> date:
    try:
        return date.fromisoformat(os.environ.get('EXVIUS_REPLAY_NV_ERA', '2020-08-20'))
    except ValueError:
        return date(2020, 8, 20)


def end_date() -> date:
    """The day after Global's last banner set."""
    if 'end' not in _CACHE:
        dates = unit_dates().values()
        last = max((date.fromisoformat(d) for d in dates), default=date(2024, 8, 22))
        import history_runs
        # With full runs the late banners and events stay up until the end of service (2024-10-30).
        floor = date(2024, 10, 30) if history_runs.enabled() else date(2024, 8, 22)
        _CACHE['end'] = max(last, floor) + timedelta(days=1)
    return _CACHE['end']


def pace_segments() -> list[tuple[date | None, int]]:
    """[(from date or None, historical weeks per real week)], in order."""
    out: list[tuple[date | None, int]] = []
    for part in os.environ.get('EXVIUS_REPLAY_PACE', '3,2@2020-08-20').split(','):
        part = part.strip()
        if not part:
            continue
        pace, _, when = part.partition('@')
        try:
            out.append((date.fromisoformat(when) if when else None, max(1, int(pace))))
        except ValueError:
            continue
    out.sort(key=lambda seg: seg[0] or date.min)
    return out or [(None, 3)]


def _pace_at(day: date) -> int:
    pace = pace_segments()[0][1]
    for when, weeks in pace_segments():
        if when is None or day >= when:
            pace = weeks
    return pace


def historical_start(index: int) -> date:
    """Where history stands at the start of replay week `index` (0 = the first replay week)."""
    day = start_date()
    for _ in range(max(0, index)):
        day += timedelta(days=7 * _pace_at(day))
    return day


def _state_file() -> str:
    import data_paths
    return os.path.join(data_paths.STATE_DIR, 'replay.json')


def anchor_week(current: int, record: bool) -> int:
    """The rotation week that is replay week 0, recorded the first time summons are served."""
    path = _state_file()
    try:
        with open(path, encoding='utf-8') as fh:
            return int(json.load(fh)['anchor_week'])
    except (OSError, ValueError, KeyError, TypeError):
        pass
    if record:
        try:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, 'w', encoding='utf-8') as fh:
                json.dump({'anchor_week': current, 'start': start_date().isoformat()}, fh)
        except OSError:
            pass
    return current


def window(now: datetime | None = None, record: bool = False, anchor: int | None = None) -> dict:
    """This real week's slice of history: {'index', 'from', 'to', 'finished'} ('to' is exclusive)."""
    import gacha_rotation
    number = gacha_rotation.week(now)[0]
    first = anchor if anchor is not None else anchor_week(number, record)
    index = number - first
    begin, end = historical_start(index), historical_start(index + 1)
    return {'index': index, 'from': begin, 'to': end, 'finished': begin >= end_date(), 'anchor': first}


# ---- unit release dates -------------------------------------------------------------------------------

def global_release_fixes() -> dict[str, str]:
    """Unit -> Global's release date, for the units unit_release.json dates later than Global did (player report,
    2026-11-10: Gilgamesh (FFV) dated 2019-08-30, out on Global on 2016-11-24). content/unit_release_global.json,
    built by ios-server/devtools/build_unit_release_check.py from the FFBE wiki's Global update history."""
    if 'fixes' not in _CACHE:
        try:
            with open(os.path.join(_HERE, 'content', 'unit_release_global.json'), encoding='utf-8') as fh:
                _CACHE['fixes'] = {str(u): str(v['global']) for u, v in json.load(fh)['later'].items()}
        except (OSError, ValueError, KeyError):
            _CACHE['fixes'] = {}
    return _CACHE['fixes']


def unit_dates() -> dict[str, str]:
    if 'units' not in _CACHE:
        try:
            with open(UNITS_FILE, encoding='utf-8') as fh:
                _CACHE['units'] = {str(k): str(v) for k, v in json.load(fh)['units'].items()}
        except (OSError, ValueError, KeyError):
            _CACHE['units'] = {}
        for unit, day in global_release_fixes().items():
            if unit in _CACHE['units'] and day < _CACHE['units'][unit]:
                _CACHE['units'][unit] = day
        # And the units unit_release.json dates EARLIER than Global did (2026-11-12: Silent Knight Charlotte dated
        # 2022-07-07, out on Global on 2022-12-29): Global's date wins both ways (research/UNIT_RELEASE_CHECK.md).
        for unit, day in global_release_earlier().items():
            if unit in _CACHE['units'] and day > _CACHE['units'][unit]:
                _CACHE['units'][unit] = day
    return _CACHE['units']


def global_release_earlier() -> dict[str, str]:
    """Unit -> Global's release date, for the units unit_release.json dates before Global did
    (content/unit_release_global.json `units`, the wiki's Global update history)."""
    if 'earlier' not in _CACHE:
        out = {}
        try:
            with open(UNITS_FILE, encoding='utf-8') as fh:
                ours = {str(k): str(v) for k, v in json.load(fh)['units'].items()}
            with open(os.path.join(_HERE, 'content', 'unit_release_global.json'), encoding='utf-8') as fh:
                found = json.load(fh).get('units') or {}
            for unit, row in found.items():
                day = str((row or {}).get('global') or '') if isinstance(row, dict) else ''
                if day and unit in ours and ours[unit] < day:
                    out[str(unit)] = day
        except (OSError, ValueError, KeyError):
            pass
        _CACHE['earlier'] = out
    return _CACHE['earlier']


def released_by(unit_id, cutoff: date) -> bool:
    """True when the unit had come out by `cutoff`. Units with no date (moogles, materials) always count."""
    day = unit_dates().get(str(unit_id))
    return day is None or day <= cutoff.isoformat()


def pool_cutoff(banner: dict | None = None, now: datetime | None = None) -> date | None:
    """The last release date a summon pool may draw from this week, or None for no limit.

    The same for every banner: a holiday set shown ahead of history still offers its own featured units
    (expand_pool keeps those), but the rest of its pool stays at this week's point in history."""
    if not enabled():
        return None
    if banner and full_pool(banner):
        return None  # one-off ticket summons keep their whole pool (see full_pool)
    win = window(now)
    if win['finished']:
        return None
    return win['to'] - timedelta(days=1)


def _unlimited_shop_items() -> set[str]:
    """`kind:id` of items the Shop sells with no purchase limit (global_bundles.json)."""
    if 'unlimited' not in _CACHE:
        out = set()
        try:
            with open(os.path.join(_HERE, 'global_bundles.json'), encoding='utf-8') as fh:
                for bundle in json.load(fh).get('bundles', []):
                    if not bundle.get('limit'):
                        out |= {':'.join(str(c).split(':')[:2]) for c in bundle.get('contents', [])}
        except (OSError, ValueError):
            pass
        _CACHE['unlimited'] = out
    return _CACHE['unlimited']


KEEP_REPLAY_LIMIT = {'9200106'}   # plain SP Special Summon, see full_pool


def full_pool(banner: dict) -> bool:
    """A summon paid only with a ticket you can't buy over and over keeps its whole pool: a held ticket is
    a one-off chance (operator, 2026-11-05). Tickets the Shop sells without limit (Bonus/Boss Rush/Brave
    Ability Box tickets) keep the replay's limit. EXVIUS_REPLAY_FULL_POOL names more banners by id.

    The plain SP Special Summon (9200106) always keeps the limit: its 300-Lapis ticket was taken out of the
    Shop on 2026-11-07 (it was a cheaper way to summon), and tickets already held shouldn't turn into a
    draw from the whole pool now that nothing sells it."""
    if str(banner.get('id')) in KEEP_REPLAY_LIMIT:
        return False
    if str(banner.get('id')) in full_pool_ids():
        return True
    cost = banner.get('cost')
    cost = cost[0] if isinstance(cost, list) and cost else cost
    if not isinstance(cost, dict) or str(cost.get('kind')) not in ('item', 'important') or not cost.get('item_id'):
        return False
    kind = '20' if str(cost.get('kind')) == 'item' else '23'
    return f"{kind}:{cost['item_id']}" not in _unlimited_shop_items()


def full_pool_ids() -> set[str]:
    """Banners exempt from the replay's unit limit: the SP ticket summons, which can only be pulled with a
    once-only ticket from the Shop (global_bundles.json 990000108/990000109)."""
    raw = os.environ.get('EXVIUS_REPLAY_FULL_POOL', '9200107,9200108')
    return {part.strip() for part in raw.split(',') if part.strip()}


def build_unit_dates(banners: list) -> dict[str, str]:
    """First Global banner date per featured unit; JP-only banners count only for units Global never featured."""
    import gacha_rotation
    from player_state import unit_roots_by_rarity
    _fixed, special, featured, by_id = gacha_rotation.pools(banners)
    best: dict[str, tuple[int, str]] = {}
    for key, ids in sorted(special + featured):
        try:
            date.fromisoformat(key)
        except ValueError:
            continue
        for bid in ids:
            banner = by_id[bid]
            rank = 1 if str(banner.get('source', '')).startswith('translated-jp') or banner.get('region') == 'jp' else 0
            units = set(str(u) for u in ((banner.get('community') or {}).get('unit_ids') or []))
            pool = banner.get('pool')
            if isinstance(pool, dict):
                for tier in pool.get('tiers') or []:
                    units |= {str(u) for u in tier.get('featured') or []}
            # A banner's full reward list is not used: it holds every unit in the pool, not what was new.
            for unit in units:
                if unit not in best or (rank, key) < best[unit]:
                    best[unit] = (rank, key)
    dated = {u: key for u, (_rank, key) in best.items()}
    # Units no banner featured: the next dated unit of the same series (same first three digits, higher
    # running number), else the end of history. An undated 7-star-base (NV) unit is never before the NV era.
    rarity = {u: r for r, rows in unit_roots_by_rarity().items() for u in rows}
    last = max(dated.values(), default='2024-08-22')
    roots = [u for u in rarity if not u.startswith('9')]
    series: dict[str, list[tuple[str, str]]] = {}
    for unit, day in dated.items():
        series.setdefault(unit[:3], []).append((unit[3:7], day))
    for rows in series.values():
        rows.sort()
    # Global's own release date where our banner records feature a unit later (global_release_fixes).
    for unit, day in global_release_fixes().items():
        if unit in dated and day < dated[unit]:
            dated[unit] = day
    out = dict(dated)
    for unit in roots:
        if unit in out or len(unit) < 9:
            continue
        rows = series.get(unit[:3]) or []
        later = [day for number, day in rows if number > unit[3:7]]
        day = min(later) if later else last
        if rarity.get(unit) == '7':
            day = max(day, nv_era().isoformat())
        out[unit] = day
    return dict(sorted(out.items()))


def describe(weeks: int = 8, now: datetime | None = None) -> str:
    import gacha_rotation
    from ffbe_gacha import all_banners
    banners = all_banners()
    number, start, _nxt = gacha_rotation.week(now)
    first = anchor_week(number, record=False)
    lines = [f"Replay from {start_date()} at pace {os.environ.get('EXVIUS_REPLAY_PACE', '3,2@2020-08-20')}; "
             f"replay week 0 is rotation week {first}."]
    for offset in range(weeks):
        moment = start + timedelta(days=7 * offset, hours=1)
        win = window(moment, anchor=first)
        current = gacha_rotation.plan(banners, moment, anchor=first)
        lines.append(f"{current['starts']:%a %b %d %Y}: history {win['from']} to {win['to'] - timedelta(days=1)}"
                     + ('  [history finished, random rotation]' if win['finished'] else '')
                     + (f"  [{current['holiday']}]" if current['holiday'] else ''))
        for key, members in current['sets']:
            lines.append(f"    {key}: " + '; '.join(current['by_id'][b].get('name', b) for b in members))
        if offset == 0:
            lines.append('    Always: ' + ', '.join(current['by_id'][b].get('name', b) for b in current['permanent']))
    return '\n'.join(lines)


def main(argv=None) -> int:
    import argparse
    parser = argparse.ArgumentParser(description='Preview the historical replay.')
    parser.add_argument('--weeks', type=int, default=8)
    parser.add_argument('--write-units', action='store_true', help='rewrite unit_release.json')
    args = parser.parse_args(argv)
    for name, value in (('GACHA_ONLY', 'all'), ('GACHA_CAMPAIGN', 'all'), ('EXVIUS_SUMMON_ARCHIVE', '1'),
                        ('GACHA_STANDARD', '1'), ('GACHA_CATALOGUE', '1'), ('EXVIUS_SUMMON_ROTATION', '1'),
                        ('EXVIUS_REPLAY', '1')):
        os.environ.setdefault(name, value)
    if args.write_units:
        from ffbe_gacha import all_banners
        units = build_unit_dates(all_banners())
        with open(UNITS_FILE, 'w', encoding='utf-8') as fh:
            json.dump({'_meta': {'what': 'first Global release date per unit id (replay.py)',
                                 'generator': 'python3 replay.py --write-units'},
                       'units': units}, fh, indent=0)
            fh.write('\n')
        print(f'{len(units)} unit dates written to {UNITS_FILE}')
        return 0
    print(describe(max(1, args.weeks)))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
