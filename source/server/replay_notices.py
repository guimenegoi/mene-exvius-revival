"""Weekly "New this week" notices on the in-game News board, for the historical replay (replay.py).

The News button opens InformationListScene, which sends NoticeUpdateRequest (`CQ4jTm2F`) and lists the
NoticeMst rows it holds in buckets 0 and 1. A reply group fills a bucket by its tag: `tN8f0PSB` is bucket
0 (NoticeMstResponse kinds 0-5 are tN8f0PSB, R17unt2e, 3BI1xSGW, VKA5urE1, oUk10RXm, fzm3je8p). The row
fields were read from NoticeMstResponse::readParam (libgame, Android build):

    td06MKEX notice id          i4Bb9ySk tab (1-4)            1fKgZk2I icon (0-5, inform_category*.png)
    5GNraZM0 notice type        15Y3fBmF caption, JSON {"en": "..."}   w7VR6ypY priority
    1d8R5ajV display date       VjJQ51uG / m8ivD4NX start / end         o6n5aQ8C / 9miE75sp "new" start / end
    5r8HSq1N / M9ZKJY3w open start / end    DSJpb89M open description   oIra47LK page type
    1X65WPLU url (opened when page type is 1)                            QLfe23bu read-flag index
    8amsKpQ2 popup flag         I2PbiZ1f / GTESVt57 popup start / end    52ihocTI hidden flag
    7DUC49n8 movie              qo3PECw6 mission id

Dates are "YYYY-MM-DD HH:MM:SS". The read mark is kept per display-date year and read-flag index
(exvius_actions.notice_state), so each week's notice has its own index.

Each notice opens /exvius/notices/<replay week>.html on the game's own host, served by capture_server.
The page lists the week's new summons, then (2026-11-07) its deal summons with a line on each deal
(`deal_terms`; dated permanent ones such as the Bonus Present Ticket Summon in the week they open), the
dated Shop bundles that go on sale (global_bundles.json `from`) and the replay mails due that week.
Off switch: EXVIUS_REPLAY_NOTICES=0. EXVIUS_REPLAY_NOTICE_WEEKS (default 8) is how many weeks stay listed.
"""
from __future__ import annotations

import html
import json
import os
from datetime import date, timedelta

TAG = 'tN8f0PSB'
NOTICE_ID_BASE = 880000
INDEX_BASE = 500
HOST = 'https://v900-lapis.gumi.sg'


def enabled() -> bool:
    import replay
    return replay.enabled() and os.environ.get('EXVIUS_REPLAY_NOTICES', '1') == '1'


def _weeks_listed() -> int:
    try:
        return max(1, int(os.environ.get('EXVIUS_REPLAY_NOTICE_WEEKS', '8')))
    except ValueError:
        return 8


def _moment(index: int):
    """A time inside replay week `index` (real time)."""
    import gacha_rotation
    import replay
    number, start, _nxt = gacha_rotation.week()
    current = number - replay.anchor_week(number, record=False)
    return start + timedelta(days=7 * (index - current), hours=1), start + timedelta(days=7 * (index - current))


_SUMMARIES: dict = {}


def week_summary(index: int) -> dict | None:
    """What arrived in replay week `index`: its real start, slice of history, summons and Vortex events.
    Cached: a week's contents never change once the replay's week 0 is fixed."""
    import replay
    key = (index, replay.anchor_week(-1, record=False), os.environ.get('EXVIUS_REPLAY_PACE', ''))
    if key not in _SUMMARIES:
        _SUMMARIES[key] = _week_summary(index)
    return _SUMMARIES[key]


def _featured_units(banner: dict) -> list[str]:
    units = [str(u) for u in ((banner.get('community') or {}).get('unit_ids') or [])]
    pool = banner.get('pool')
    if isinstance(pool, dict):
        for tier in pool.get('tiers') or []:
            units += [str(u) for u in tier.get('featured') or [] if str(u) not in units]
    return units


def _unit_name(unit_id: str) -> str:
    if 'unit_names' not in _SUMMARY_CACHE:
        names = {}
        try:
            import data_paths
            with open(os.path.join(data_paths.TEXT_DIR, 'F_TEXT_UNITS_NAME.ndjson'), encoding='utf-8') as fh:
                for line in fh:
                    row = json.loads(line)
                    if row.get('v'):
                        names[row['key'][len('MST_UNIT_NAME_'):]] = str(row['v'][0]).strip()
        except (OSError, ValueError, ImportError):
            pass
        _SUMMARY_CACHE['unit_names'] = names
    return _SUMMARY_CACHE['unit_names'].get(str(unit_id), '')


_SUMMARY_CACHE: dict = {}

_TEXT_TABLES = {20: ('F_TEXT_ITEM_NAME', 'MST_ITEM_NAME_'),
                23: ('F_TEXT_IMPORTANT_ITEM_NAME', 'MST_IMPORTANT_ITEM_NAME_')}


def _item_name(kind, item_id) -> str:
    """English name of a reward (kind 10 unit, 20 item, 23 important item, 30 gil, 50 Lapis), or ''."""
    kind, item_id = int(kind), str(item_id)
    if kind == 50:
        return 'Lapis'
    if kind == 30:
        return 'Gil'
    if kind == 10:
        return _unit_name(item_id)
    if kind not in _TEXT_TABLES:
        return ''
    if 'items' not in _SUMMARY_CACHE:
        names = {}
        try:
            import data_paths
            for table_kind, (table, prefix) in _TEXT_TABLES.items():
                with open(os.path.join(data_paths.TEXT_DIR, table + '.ndjson'), encoding='utf-8') as fh:
                    for line in fh:
                        row = json.loads(line)
                        if row.get('v') and str(row.get('key', '')).startswith(prefix):
                            names[f"{table_kind}:{row['key'][len(prefix):]}"] = str(row['v'][0]).strip()
        except (OSError, ValueError, ImportError):
            pass
        try:   # names the iPhone text patch adds (items the shipped tables have no English for)
            here = os.path.dirname(os.path.abspath(__file__))
            with open(os.path.join(here, 'ios_text_items.json'), encoding='utf-8') as fh:
                for key, name in (json.load(fh).get('items') or {}).items():
                    names.setdefault(key, name)
        except (OSError, ValueError):
            pass
        _SUMMARY_CACHE['items'] = names
    return _SUMMARY_CACHE['items'].get(f'{kind}:{item_id}', '')


def _count(name: str, count: int) -> str:
    if name in ('Lapis', 'Gil'):
        return f'{count:,} {name}'
    return name if count == 1 else f'{name} ×{count:,}'


def _pulls(draws) -> str:
    draws = int(draws or 1)
    if draws in (6, 11):
        return f'{draws - 1}+1'
    return 'one summon' if draws == 1 else f'{draws} summons'


def _price(cost: dict) -> str:
    kind = (cost or {}).get('kind')
    if kind == 'lapis':
        return f"{int(cost.get('amount') or 0):,} Lapis"
    if kind in ('item', 'important', 'ticket'):
        name = _item_name(23 if kind == 'important' else 20, cost.get('item_id'))
        return name or 'a summon ticket'
    return ''


def _times(limit) -> str:
    try:
        limit = int(limit)
    except (TypeError, ValueError):
        return ''
    return 'once' if limit == 1 else f'up to {limit} times'


def _guarantee(guarantee) -> str:
    if not isinstance(guarantee, dict):
        return ''
    if guarantee.get('unit_id'):
        name = _unit_name(guarantee['unit_id'])
        return f'{name} guaranteed' if name else 'a featured unit guaranteed'
    try:
        rarity, count = int(guarantee.get('rarity') or 0), int(guarantee.get('count') or 1)
    except ValueError:
        return ''
    if not rarity:
        return ''
    what = 'NV' if rarity >= 7 else f'{rarity}★ or higher'
    return f'{what} guaranteed' if count == 1 else f'{count} units {what} guaranteed'


def deal_terms(banner: dict) -> str:
    """One plain line on what a deal summon offers, from its spec (gacha_deals.json)."""
    out = []
    steps = banner.get('steps') or []
    if steps:
        prices = sorted({int((s.get('cost') or {}).get('amount') or 0) for s in steps})
        price = f'{prices[0]:,} Lapis' if len(prices) == 1 else f'{prices[0]:,}–{prices[-1]:,} Lapis'
        text = f'Step-up: {len(steps)} steps, {price} a step'
        laps = _times(banner.get('lap_limit'))
        if laps:
            text += ', ' + ('one time through' if laps == 'once' else laps.replace('times', 'times through'))
        out.append(text)
        guaranteed = sum(1 for s in steps if s.get('guarantee'))
        bonus = sum(1 for s in steps if s.get('bonus_rewards'))
        if all(int((s.get('guarantee') or {}).get('rarity') or 0) >= 7 for s in steps):
            out.append('NV guaranteed on every step')
        elif guaranteed:
            out.append('a guarantee on every step' if guaranteed == len(steps) else 'a guarantee on one step'
                       if guaranteed == 1 else f'a guarantee on {guaranteed} of the steps')
        if bonus:
            out.append('bonus items on ' + ('every step' if bonus == len(steps) else 'one step' if bonus == 1
                                            else f'{bonus} of the steps'))
        return '. '.join(part[0].upper() + part[1:] for part in out) + '.'
    cost = banner.get('cost') or {}
    pulls = _pulls(banner.get('draws'))
    if cost.get('kind') == 'free':
        text = 'One free summon' if pulls == 'one summon' else f'Free {pulls}'
        if banner.get('daily_limit'):
            text += ' every day' if int(banner['daily_limit']) == 1 else f", {banner['daily_limit']} a day"
        elif banner.get('weekly_limit'):
            text += ' every week'
    elif cost.get('kind') in ('item', 'important', 'ticket'):
        text = f'{pulls[0].upper() + pulls[1:]} for each {_price(cost)}'
    else:
        text = f'{pulls} for {_price(cost)}' if _price(cost) else pulls
        text = text[0].upper() + text[1:]
    limit = _times(banner.get('purchase_limit'))
    if limit and not banner.get('daily_limit') and not banner.get('weekly_limit'):
        text += ', ' + limit
    out.append(text)
    if banner.get('guarantee'):
        out.append(_guarantee(banner['guarantee']))
    for slot in banner.get('guarantee_slots') or []:
        if slot.get('label'):
            out.append(f"{'one more ' if banner.get('guarantee') and slot['label'] != 'NV' else ''}"
                       f"{slot['label']} guaranteed")
    if banner.get('resummon'):
        out.append(f"redo the 10+1 for free up to {_times(banner['resummon']).replace('up to ', '')}")
    if banner.get('bonus_choice'):
        out.append('bonus Lapis with every pull')
    if banner.get('bonus_rewards'):
        out.append('bonus items included')
    if banner.get('unit_select_tickets'):
        out.append('comes with an NV Unit Select Ticket')
    return '. '.join(part[0].upper() + part[1:] for part in out if part) + '.'


def _unit_rows(banner: dict) -> list[dict]:
    from player_state import unit_mst
    units = []
    for uid in _featured_units(banner):
        name = _unit_name(uid)
        if name:
            units.append({'id': uid, 'name': name, 'rarity': str((unit_mst(uid) or {}).get('9fW0TePj') or '')})
    return units


def _bundles_from(begin: date, end: date) -> list[dict]:
    """Dated Shop bundles (global_bundles.json `from`) that go on sale in [begin, end)."""
    import ffbe_player
    out = []
    for bundle in ffbe_player._global_bundles():
        start = bundle.get('from')
        if not start or not begin.isoformat() <= start < end.isoformat():
            continue
        contents = []
        for entry in bundle.get('contents') or []:
            parts = str(entry).split(':')
            if len(parts) < 3:
                continue
            name = _item_name(parts[0], parts[1])
            if name:
                contents.append(_count(name, int(parts[2])))
        if 'usd' in bundle:
            price = f"${bundle['usd']}"
        elif 'gil' in bundle:
            price = f"{int(bundle['gil']):,} Gil"
        else:
            price = f"{int(bundle.get('lapis') or 0):,} Lapis"
        out.append({'id': str(bundle['id']), 'name': bundle['name'], 'released': start,
                    'until': bundle.get('until') or '', 'icon': bundle.get('icon') or '', 'price': price,
                    'limit': 'Once per player' if bundle.get('limit') == 'once' else '', 'contents': contents})
    return out


def _mails_from(begin: date, end: date) -> list[dict]:
    """Replay mails (replay_mails.py) whose Global date falls in [begin, end): they arrive this week."""
    import replay
    import replay_mails
    if not replay_mails.enabled():
        return []
    out = []
    for mail in replay_mails.mails():
        if not begin <= date.fromisoformat(mail['date']) < end:
            continue
        items = [_count(_item_name(kind, item_id) or 'a gift', count)
                 for kind, item_id, count in replay_mails.items_for(mail, replay.start_date())]
        out.append({'id': mail['id'], 'released': mail['date'], 'title': mail['title'],
                    'message': mail.get('message', ''), 'items': items})
    return out


def _week_summary(index: int) -> dict | None:
    import event_archive
    import gacha_rotation
    import replay
    from ffbe_gacha import all_banners
    moment, start = _moment(index)
    win = replay.window(moment)
    if win['index'] != index or index < 0:
        return None
    current = gacha_rotation.plan(all_banners(), moment)
    holiday_keys = {key for keys in current['holiday_sets'].values() for key in keys}
    summons, deals = [], []
    for key, members in current['sets']:
        banners = []
        for bid in members:
            banner = current['by_id'][bid]
            row = {'id': bid, 'name': banner.get('name', bid),
                   'art': (banner.get('art') or {}).get('banner') or '', 'units': _unit_rows(banner)}
            if banner.get('deal'):
                # Deal summons (gacha_deals.json) get their own section, with what the deal offers.
                row.update(released=key, terms=deal_terms(banner),
                           until=str((banner.get('community') or {}).get('until') or ''))
                deals.append(row)
            else:
                banners.append(row)
        if banners:
            summons.append({'released': key, 'names': [b['name'] for b in banners], 'banners': banners,
                            'holiday': key in holiday_keys})
    # Dated permanent deal summons (Guaranteed NV, Bonus Present Ticket...) stay listed for months; the
    # notice names them in the week they first open.
    for bid in current['permanent']:
        banner = current['by_id'][bid]
        span = banner.get('permanent')
        opened = span.get('from') if isinstance(span, dict) else None
        if not opened or not win['from'].isoformat() <= opened < win['to'].isoformat():
            continue
        deals.append({'id': bid, 'name': banner.get('name', bid),
                      'art': (banner.get('art') or {}).get('banner') or '', 'units': _unit_rows(banner),
                      'released': opened, 'terms': deal_terms(banner) if banner.get('deal') else '',
                      'until': span.get('until') or '', 'stays': True})
    deals.sort(key=lambda d: (d['released'], d['name']))
    try:
        bundles = _bundles_from(win['from'], win['to'])
    except Exception as exc:  # noqa: BLE001 -- the rest of the page still shows
        print(f'[replay-notices] bundles skipped ({exc})', flush=True)
        bundles = []
    try:
        mails = _mails_from(win['from'], win['to'])
    except Exception as exc:  # noqa: BLE001
        print(f'[replay-notices] mails skipped ({exc})', flush=True)
        mails = []
    art = _event_art()
    events, seen = [], set()
    for row in sorted(event_archive.weekly_events(now=moment), key=lambda r: (str(r.get('release')), str(r.get('area')))):
        if (row.get('group') == 'permanent' and not row.get('windows')) or not row.get('release'):
            continue
        key = (row['release'], row['name'])
        if key in seen:
            continue
        seen.add(key)
        events.append({'released': row['release'], 'name': row['name'],
                       'kind': str(row.get('kind') or '').split('<br>')[0], 'art': art.get(str(row.get('area')), '')})
    return {'index': index, 'start': start, 'from': win['from'], 'to': win['to'] - timedelta(days=1),
            'finished': win['finished'], 'holiday': current.get('holiday'), 'summons': summons,
            'deals': deals, 'bundles': bundles, 'mails': mails, 'events': events}


def _caption(summary: dict) -> str:
    # With full runs (history_runs.py) long banners stay up for weeks; the caption names what is new this week.
    first = summary['from'].isoformat()
    new = lambda released: str(released) >= first  # noqa: E731
    names = [name.replace(' Featured Summon', '') for entry in summary['summons'] if new(entry['released'])
             for name in entry['names']]
    names += [deal['name'] for deal in summary.get('deals') or [] if new(deal['released'])]
    names += [bundle['name'] for bundle in summary.get('bundles') or []]
    names += [mail['title'] for mail in summary.get('mails') or []]
    head = f"{summary['start']:%b} {summary['start'].day}: "
    if summary['holiday']:
        head += f"{summary['holiday']} summons! "
    if not names:
        return head + 'This week in history'
    text = head + names[0]
    if len(names) > 1:
        text += f' and {len(names) - 1} more'
    return text


def rows() -> list[dict]:
    import gacha_rotation
    import replay
    number, _start, _nxt = gacha_rotation.week()
    current = number - replay.anchor_week(number, record=False)
    out = []
    for index in range(max(0, current - _weeks_listed() + 1), current + 1):
        summary = week_summary(index)
        if not summary:
            continue
        begin = summary['start'].strftime('%Y-%m-%d %H:%M:%S')
        new_end = (summary['start'] + timedelta(days=7)).strftime('%Y-%m-%d %H:%M:%S')
        out.append({
            'td06MKEX': str(NOTICE_ID_BASE + index), '5GNraZM0': '0', 'i4Bb9ySk': '1', '1fKgZk2I': '1',
            '15Y3fBmF': json.dumps({'en': _caption(summary)}, ensure_ascii=False), 'w7VR6ypY': str(index),
            '1d8R5ajV': begin, 'VjJQ51uG': begin, 'm8ivD4NX': '2099-12-31 23:59:59',
            'o6n5aQ8C': begin, '9miE75sp': new_end, '5r8HSq1N': begin, 'M9ZKJY3w': '2099-12-31 23:59:59',
            'DSJpb89M': '', 'oIra47LK': '1', '1X65WPLU': f'{HOST}/exvius/notices/{index}.html',
            'QLfe23bu': str(INDEX_BASE + index), '8amsKpQ2': '0', 'I2PbiZ1f': '', 'GTESVt57': '',
            '7DUC49n8': '', 'qo3PECw6': '0', '52ihocTI': '0'})
    return out


def add_rows(spec):
    """Add this replay's weekly notices to a NoticeUpdateRequest reply."""
    if not enabled():
        return spec
    try:
        notices = rows()
    except Exception as exc:  # noqa: BLE001 -- the board just stays empty
        print(f'[replay-notices] skipped ({exc})', flush=True)
        return spec
    spec = dict(spec) if isinstance(spec, dict) else {}
    spec[TAG] = list(spec.get(TAG) or []) + notices
    return spec


def _day(value: date) -> str:
    return f'{value:%b} {value.day}, {value.year}'


def page(index: str) -> str | None:
    if not enabled():
        return None
    import gacha_rotation
    import replay
    from urllib.parse import quote
    number = gacha_rotation.week()[0]
    try:
        index = int(index)
    except (ValueError, TypeError):
        return None
    if index > number - replay.anchor_week(number, record=False):
        return None  # a week that hasn't happened yet
    summary = week_summary(index)
    if not summary:
        return None

    def src(kind: str, value: str) -> str:
        if kind == 'summon':
            # The path the summon list itself uses, so the CDN finds the file by name (a bare
            # /banner/<file> has no folder for its lookup to go on and was answered 404 on the phone).
            return '/banner/en/sd/static_banner/gacha/main/' + quote(value)
        if kind == 'event':
            return '/en/sd/area/' + quote(value)
        if kind == 'bundle':
            # The path the Shop's bundle tiles use (ffbe_player: common_lang/sd/static_banner/bundle/<icon>).
            return '/banner/common_lang/sd/static_banner/bundle/' + quote(value)
        return '/exvius/notice-art/unit/' + quote(value) + '.png'
    return render(summary, src)


# A unit with no picture in the game data: the server answers 404 and the space stays blank.
_NO_PICTURE = "this.onerror=null;this.style.visibility='hidden';"


def _span(released: str, until: str = '', stays: bool = False) -> str:
    """'Originally Feb 2 – Feb 15, 2018' for a one-off; for one that stays on offer, how long it stays."""
    try:
        first = date.fromisoformat(released)
    except (TypeError, ValueError):
        return ''
    try:
        last = date.fromisoformat(until) if until else None
    except ValueError:
        last = None
    if stays:
        if last:
            return f'Stays on offer until history reaches {_day(last)} (Global, from {_day(first)})'
        return f'Stays on offer from here on (Global, from {_day(first)})'
    if not last or last <= first:
        return f'Originally {_day(first)}'
    if last.year == first.year:
        return f'Originally {first:%b} {first.day} &ndash; {_day(last)}'
    return f'Originally {_day(first)} &ndash; {_day(last)}'


def _units(parts: list, units: list, src) -> None:
    if not units:
        return
    import unit_art
    esc = html.escape
    parts.append('<ul class="units">')
    for unit in units:
        stars = f'{unit["rarity"]}★ base' if unit['rarity'] and unit['rarity'] != '7' else (
            'Neo Vision' if unit['rarity'] == '7' else '')
        # The unit's picture from the game's own packs (unit_art.py); off: names only.
        img = (f'<img src="{esc(src("unit", unit["id"]))}" alt="" loading="lazy" onerror="{_NO_PICTURE}">'
               if unit_art.enabled() else '')
        parts.append(f'<li>{img}<b>{esc(unit["name"])}</b><i>{stars}</i></li>')
    parts.append('</ul>')


def render(summary: dict, src) -> str:
    """The notice page for one replay week. `src(kind, value)` gives each picture's URL: kind 'summon'
    (a summon's banner art file), 'event' (an event's banner file) or 'unit' (a unit id, its sprite)."""
    esc = html.escape
    start = summary['start']
    parts = ['<header class="mast">',
             '<p class="eyebrow">Brave Exvius News</p>',
             f'<h1>Week of {start:%B} {start.day}</h1>']
    if summary['finished']:
        parts.append('<p class="era">Global\'s history is complete. Summons rotate weekly now.</p>')
    else:
        parts.append(f'<p class="era"><span>Global history</span> {_day(summary["from"])} &ndash; '
                     f'{_day(summary["to"])}</p>')
    parts.append('</header>')
    if summary['holiday']:
        parts.append(f'<p class="ribbon">{esc(summary["holiday"])} summons are here this week</p>')
    parts.append('<section><h2><span>New Summons</span></h2>')
    if not summary['summons']:
        parts.append('<p class="empty">No new summons this week.</p>')
    for entry in summary['summons']:
        when = date.fromisoformat(entry['released']) if entry['released'][:1].isdigit() else None
        for banner in entry['banners']:
            parts.append('<article class="summon">')
            if banner['art']:
                parts.append(f'<img class="art" src="{esc(src("summon", banner["art"]))}" alt="" '
                             f'width="640" height="160" loading="lazy" onerror="this.style.display=\'none\'">')
            title = banner['name'].replace(' Featured Summon', '')
            parts.append(f'<div class="cap"><h3>{esc(title)}</h3>'
                         + (f'<p class="date">Originally {_day(when)}</p>' if when else '') + '</div>')
            _units(parts, banner['units'], src)
            parts.append('</article>')
    parts.append('</section>')
    if summary.get('deals'):
        parts.append('<section><h2><span>Deals</span></h2>')
        for deal in summary['deals']:
            parts.append('<article class="summon deal">')
            if deal['art']:
                parts.append(f'<img class="art" src="{esc(src("summon", deal["art"]))}" alt="" '
                             f'width="640" height="160" loading="lazy" onerror="this.style.display=\'none\'">')
            parts.append(f'<div class="cap"><h3>{esc(deal["name"])}</h3>')
            if deal.get('terms'):
                parts.append(f'<p class="terms">{esc(deal["terms"])}</p>')
            parts.append(f'<p class="date">{_span(deal["released"], deal.get("until"), deal.get("stays"))}</p></div>')
            _units(parts, deal['units'], src)
            parts.append('</article>')
        parts.append('</section>')
    if summary.get('bundles'):
        parts.append('<section><h2><span>In the Shop</span></h2>')
        for bundle in summary['bundles']:
            parts.append('<article class="bundle">')
            if bundle['icon']:
                parts.append(f'<img class="icon" src="{esc(src("bundle", bundle["icon"]))}" alt="" width="200" '
                             f'height="200" loading="lazy" onerror="this.style.display=\'none\'">')
            price = esc(bundle['price']) + (f' &middot; {esc(bundle["limit"])}' if bundle['limit'] else '')
            parts.append(f'<div class="cap"><h3>{esc(bundle["name"])}</h3><p class="terms">{price}</p>')
            if bundle['contents']:
                parts.append('<p class="contents">' + esc(', '.join(bundle['contents'])) + '</p>')
            parts.append(f'<p class="date">{_span(bundle["released"], bundle["until"], not bundle["until"])}</p>'
                         '</div></article>')
        parts.append('</section>')
    if summary.get('mails'):
        parts.append('<section><h2><span>In Your Gifts</span></h2>')
        for mail in summary['mails']:
            parts.append(f'<article class="mail"><div class="cap"><h3>{esc(mail["title"])}</h3>'
                         f'<p class="message">{esc(mail["message"])}</p>')
            if mail['items']:
                parts.append('<p class="terms">Attached: ' + esc(', '.join(mail['items'])) + '</p>')
            parts.append(f'<p class="date">Originally {_day(date.fromisoformat(mail["released"]))}</p>'
                         '</div></article>')
        parts.append('</section>')
    parts.append('<section><h2><span>In the Vortex</span></h2>')
    if not summary['events']:
        parts.append('<p class="empty">No new events this week. The permanent Vortex areas are open as usual.</p>')
    for event in summary['events']:
        when = date.fromisoformat(event['released'])
        parts.append('<article class="event">')
        if event['art']:
            parts.append(f'<img class="art" src="{esc(src("event", event["art"]))}" alt="{esc(event["name"])}" '
                         f'width="640" height="240" loading="lazy" onerror="this.style.display=\'none\'">')
        parts.append(f'<div class="cap"><h3>{esc(event["name"])}</h3><p class="date">'
                     + (f'{esc(event["kind"])} &middot; ' if event['kind'] else '')
                     + f'{_day(when)}</p></div></article>')
    parts.append('</section><footer>Banners and sprites are the original game art.</footer>')
    return PAGE.replace('{{BODY}}', '\n'.join(parts))


PAGE = """<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<title>This Week in Exvius</title>
<style>
/* One dark look, like the game's own menus: a night-blue sheet, gold rules and gilt headings. */
:root{--night:#0d1230;--sheet:#151b42;--ink:#f3ecd9;--muted:#b4abc9;--gold:#e8c46a;--gilt:#fff1bf;
--rose:#ff9db6;--line:rgba(232,196,106,.45);color-scheme:dark;
--display:"Cinzel","Trajan Pro",Georgia,"Times New Roman",serif;--body:"Avenir Next","Segoe UI",Roboto,Helvetica,Arial,sans-serif}
*{box-sizing:border-box}
html{background:var(--night)}
body{margin:0;background:radial-gradient(120% 60% at 50% 0%,#2a2464 0%,var(--night) 70%) fixed,var(--night);
color:var(--ink);font:16px/1.45 var(--body);padding:18px max(16px,env(safe-area-inset-right,0px)) 36px max(16px,env(safe-area-inset-left,0px))}
.mast{text-align:center;padding:4px 0 14px;border-bottom:1px solid var(--line);margin-bottom:14px}
.eyebrow{margin:0;font:600 11px/1 var(--body);letter-spacing:.28em;text-transform:uppercase;color:var(--gold)}
h1{margin:8px 0 6px;font:700 25px/1.15 var(--display);color:var(--gilt);text-wrap:balance;
text-shadow:0 1px 0 #6b4c12,0 0 18px rgba(232,196,106,.25)}
.era{margin:0;color:var(--muted);font-size:13px;font-variant-numeric:tabular-nums}
.era span{color:var(--gold);letter-spacing:.08em;text-transform:uppercase;font-size:11px;margin-right:6px}
.ribbon{margin:0 0 16px;padding:9px 12px;text-align:center;font:700 14px/1.3 var(--display);letter-spacing:.04em;
color:#3b0a18;background:linear-gradient(90deg,#f6a5b8,#ffd7a3,#f6a5b8);border-radius:3px}
section{display:grid;gap:14px;margin-bottom:22px}
h2{display:flex;align-items:center;gap:10px;margin:4px 0 0;font:700 15px/1 var(--display);letter-spacing:.14em;
text-transform:uppercase;color:var(--gold)}
h2::before,h2::after{content:"";flex:1;height:1px;background:linear-gradient(90deg,transparent,var(--line))}
h2::after{background:linear-gradient(90deg,var(--line),transparent)}
article{background:var(--sheet);border:1px solid var(--line);border-radius:4px;overflow:hidden}
.art{display:block;width:100%;height:auto;background:#0a0d22}
.cap{padding:9px 12px 10px}
h3{margin:0;font:600 15px/1.3 var(--body);color:var(--ink)}
.date{margin:2px 0 0;font-size:12px;color:var(--muted)}
.terms{margin:4px 0 0;font-size:13px;line-height:1.35;color:var(--gold)}
.contents,.message{margin:4px 0 0;font-size:13px;line-height:1.4;color:var(--ink)}
.bundle{display:flex;align-items:flex-start}
.bundle .icon{flex:none;width:76px;height:76px;margin:10px 0 10px 10px;border-radius:3px;background:#0a0d22;object-fit:contain}
.bundle .cap{flex:1;min-width:0}
.mail{border-left:3px solid var(--gold)}
.units{list-style:none;margin:0;padding:4px 8px 12px;display:grid;grid-template-columns:repeat(auto-fill,minmax(74px,1fr));gap:8px 4px}
.units li{display:grid;justify-items:center;align-content:end;text-align:center;min-width:0;
background:radial-gradient(50% 9px at 50% 72px,rgba(232,196,106,.22),transparent) no-repeat}
.units img{height:76px;width:auto;max-width:100%;object-fit:contain;image-rendering:pixelated;filter:drop-shadow(0 3px 2px rgba(0,0,0,.6))}
.units b{font:600 12px/1.2 var(--body);color:var(--gilt);margin-top:4px;overflow-wrap:anywhere}
.units i{font:normal 11px/1.2 var(--body);color:var(--muted)}
.empty{margin:0;color:var(--muted);font-size:14px;text-align:center}
footer{text-align:center;color:var(--muted);font-size:11px;letter-spacing:.06em}
</style></head><body>
{{BODY}}
</body></html>"""


# ---- Home banners (the marquee on the home screen) ----------------------------------------------------
# In replay mode the home banners are the original event banners of this week's Vortex events: the same
# 640x240 images (from the FFBE wiki, event_art.json) the Vortex tiles use, already in the data overlay
# at en/sd/area/<file>. Each row's url ends in HomeBanner_<id>.png, the client's own cache name; the CDN
# handler maps that name back to the event art (marquee_file). Off switch: EXVIUS_REPLAY_MARQUEE=0.

MARQUEE_ID_BASE = 7000000
_MARQUEE_CACHE: dict = {}


def marquee_enabled() -> bool:
    import replay
    return replay.enabled() and os.environ.get('EXVIUS_REPLAY_MARQUEE', '1') == '1'


def _event_art() -> dict:
    if 'art' not in _MARQUEE_CACHE:
        here = os.path.dirname(os.path.abspath(__file__))
        try:
            with open(os.path.join(here, 'event_art.json'), encoding='utf-8') as fh:
                events = json.load(fh).get('events') or {}
        except (OSError, ValueError):
            events = {}
        _MARQUEE_CACHE['art'] = {str(area): row.get('filename') for area, row in events.items()
                                 if row.get('filename')}
    art = dict(_MARQUEE_CACHE['art'])
    import event_archive
    for row in event_archive.history().get('added', []):
        name = event_archive.added_art(row['area'])   # only once the banner is on disk
        if name:
            art.setdefault(str(row['area']), name)
    return art


def marquee_entries() -> list[dict] | None:
    """This replay week's home banners, newest first, in banner_campaigns.json's entry shape.
    None when the replay marquee is off (the normal era selection applies)."""
    if not marquee_enabled():
        return None
    import event_archive
    import replay
    win = replay.window()
    if win['finished']:
        return None
    key = (win['index'], win['anchor'])
    if key in _MARQUEE_CACHE:
        return _MARQUEE_CACHE[key]
    try:
        limit = max(1, int(os.environ.get('EXVIUS_REPLAY_MARQUEE_MAX', '6')))
    except ValueError:
        limit = 6
    art = _event_art()
    rows = [r for r in event_archive.weekly_events()
            if (r.get('group') != 'permanent' or r.get('windows')) and r.get('release')]
    rows.sort(key=lambda r: (str(r['release']), str(r.get('area'))), reverse=True)
    out, seen = [], set()
    for row in rows:
        filename = art.get(str(row.get('area')))
        if not filename or filename in seen:
            continue
        seen.add(filename)
        banner_id = MARQUEE_ID_BASE + int(row['area'])
        entry = {'name': row['name'], 'start': row['release'],
                 'art': {'banner_id': banner_id, 'banner_version': 1, 'file': filename,
                         'store_path': f'homeMarquee/HomeBanner_{banner_id}.png'}}
        if (os.environ.get('EXVIUS_REPLAY_MARQUEE_TAP', '1') == '1' and not row.get('native_mode')
                and row.get('first_dungeon') and row.get('first_mission')):
            # Tapping the banner opens the event's stage list (ffbe_banner.event_link). Clash of Wills and
            # Dark Visions open their own scenes, so their banners keep the plain Vortex link.
            entry['event'] = {'area': str(row['area']), 'dungeon': str(row['first_dungeon']),
                              'mission': str(row['first_mission'])}
        out.append(entry)
        if len(out) >= limit:
            break
    _MARQUEE_CACHE[key] = out
    return out


def marquee_file(banner_id: str) -> str | None:
    """The event art (relative CDN path) behind a replay home banner's HomeBanner_<id>.png, or None."""
    try:
        area = int(banner_id) - MARQUEE_ID_BASE
    except ValueError:
        return None
    if area <= 0:
        return None
    filename = _event_art().get(str(area))
    return f'en/sd/area/{filename}' if filename else None


# ---- Unit pictures for the notice pages: unit_art.py (the game's own unit packs, 2026-11-10) -------------
