"""The summon drop-rate page ("Drop Rates" on a summon's detail screen).

The stock iPhone app opens `F_URL_MST` `GACHA_RATE_URL` (`<WEB>/lapisProd/app/php/web/statics/probability/
sg_summons_list.php`) and posts `gacha_id=<banner>&localization=<lang>` (`sgGachaDropRateWebScene::getUrl` /
`setParameter`, GL 0x2191af0 / 0x2191cfc). The Android build's hook (`summon_menu.js`) opens
`/exvius/gacha-rates/<banner>.html` instead. Both are answered with `page(banner_id)`.

The page lists exactly what a pull draws from: the pool comes from `player_state.summon_pool` and the
guaranteed slots from `summon_guarantee_pool` / `summon_slots`, the same functions `PlayerState.roll_gacha`
uses, so it follows the historical replay, rate-ups and every other pool rule as they are this week. Units
are grouped by rarity, lowest first, each with its picture (the game's own, `/exvius/notice-art/unit/<id>.png`, unit_art.py),
name, rarity and chance per draw.
"""
from functools import lru_cache
from html import escape
import json
import math
from pathlib import Path

from data_paths import TEXT_DIR


@lru_cache(maxsize=1)
def _item_names():
    names = {}
    for filename in ('F_TEXT_ITEM_NAME.ndjson', 'F_TEXT_IMPORTANT_ITEM_NAME.ndjson'):
        with (Path(TEXT_DIR) / filename).open(encoding='utf-8') as source:
            for line in source:
                row = json.loads(line)
                values = row.get('v', [])
                if values:
                    names[row['key'].rsplit('_', 1)[-1]] = values[0]
    return names


def reward_name(reward):
    from ffbe_gacha import unit_name
    if reward.get('display_name'):
        return str(reward['display_name'])
    if int(reward['kind']) in (30, 31, 50):
        return {30: 'Gil', 31: 'Friend Points', 50: 'Lapis'}[int(reward['kind'])]
    if int(reward['kind']) == 10:
        name = unit_name(reward['id']) or 'Unit ' + str(reward['id'])
        points = reward.get('affinity_points', [])
        if len(points) == 2 and any(str(point).isdigit() and int(point) for point in points):
            name += ' (ALL ' + str(max(int(p) if str(p).isdigit() else 0 for p in points) / 10).rstrip('0').rstrip('.') + '%)'
        return name
    return _item_names().get(str(reward['id']), 'Item ' + str(reward['id']))


# ---- formatting ---------------------------------------------------------------------------------------

def _pct(share: float) -> str:
    """A chance as a percentage with three significant figures, never in exponent form."""
    value = share * 100
    if value <= 0:
        return '0%'
    if value >= 10:
        return f'{value:.1f}%'
    decimals = max(2, 2 - int(math.floor(math.log10(value))))
    return f'{value:.{decimals}f}%'


def _rarity(row) -> int:
    try:
        return int(row.get('rarity') or 0)
    except (TypeError, ValueError):
        return 0


def _rarity_label(rarity: int) -> str:
    if rarity >= 7:
        return 'Neo Vision'
    return f'{rarity}★' if rarity else 'Rewards'


def _stars(rarity: int) -> str:
    if rarity >= 7:
        return '<span class="nv">NV</span>'
    return '<span class="stars">' + '★' * max(0, rarity) + '</span>' if rarity else ''


def _is_unit(row) -> bool:
    return int(row.get('kind', 10) or 10) == 10 and row.get('unit_id') is not None


def _name(row) -> str:
    from ffbe_gacha import unit_name
    if _is_unit(row):
        return unit_name(row['unit_id']) or 'Unit ' + str(row['unit_id'])
    return reward_name(row)


# A unit with no picture in the game data (unit_art.py): the server answers 404 and the space stays blank.
_NO_PICTURE = "this.onerror=null;this.classList.add('none');"


def _card(row, share: float | None, tail: str | None = None) -> str:
    rarity = _rarity(row)
    count = int(row.get('count', 1) or 1)
    name = escape(_name(row)) + (f' &times;{count}' if count != 1 else '')
    if _is_unit(row):
        import unit_art
        uid = str(row['unit_id'])
        art = (f'<img src="/exvius/notice-art/unit/{escape(uid)}.png" alt="" loading="lazy" '
               f'onerror="{_NO_PICTURE}">') if unit_art.enabled() else ''
    else:
        art = '<span class="token" aria-hidden="true">&#x2756;</span>'
    return f'<li>{art}<b>{name}</b>{_stars(rarity)}<em>{tail if tail is not None else _pct(share)}</em></li>'


def _pool_html(pool: list, note: str = '') -> str:
    """The pool grouped by rarity, lowest first; within a rarity, the likeliest first, then by name."""
    rates = [max(0.0, float(r.get('rate', 0) or 0)) for r in pool]
    total = sum(rates)
    if not total:
        return '<p class="empty">Nothing can be drawn here.</p>'
    groups: dict = {}
    for row, rate in zip(pool, rates):
        if rate > 0:
            groups.setdefault(_rarity(row), []).append((row, rate))
    parts = [f'<p class="note">{note}</p>'] if note else []
    for rarity in sorted(groups):
        rows = sorted(groups[rarity], key=lambda pair: (-pair[1], _name(pair[0]).lower()))
        share = sum(rate for _, rate in rows) / total
        count = len(rows)
        noun = 'unit' if all(_is_unit(r) for r, _ in rows) else 'reward'
        parts.append(f'<div class="tier r{min(rarity, 7)}"><h3>{_rarity_label(rarity)}'
                     f'<span>{count} {noun}{"s" if count != 1 else ""} &middot; {_pct(share)} per draw</span></h3>'
                     '<ul class="units">' + ''.join(_card(row, rate / total) for row, rate in rows) + '</ul></div>')
    return ''.join(parts)


# ---- what each offer does -----------------------------------------------------------------------------

def _cost_text(cost) -> str:
    if not isinstance(cost, dict):
        return 'Free'
    amount = int(cost.get('amount', 0) or 0)
    if not amount:
        return 'Free'
    kind = str(cost.get('kind', ''))
    if cost.get('item_id'):
        label = _item_names().get(str(cost['item_id']), 'Item ' + str(cost['item_id']))
    else:
        label = {'lapis': 'Lapis', 'paid_lapis': 'paid Lapis', 'friend_point': 'Friend Points',
                 'gil': 'Gil'}.get(kind, kind.replace('_', ' '))
    return f'{amount:,} {escape(label)}'


def _offers(banner: dict) -> list:
    """[(label, cost, draws, step)] in the order the detail screen shows them, as `roll_gacha` charges them."""
    out = []
    steps = banner.get('steps') or []
    if steps:
        for index, step in enumerate(steps):
            cost = step.get('cost', banner.get('cost')) or {}
            draws = int((cost.get('draws') if isinstance(cost, dict) else 0) or step.get('draws') or
                        banner.get('draws') or 1)
            out.append((f'Step {index + 1}', cost, draws, step, None))
        return out
    cost = banner.get('cost') or {}
    costs = cost if isinstance(cost, list) else [cost]
    for entry in costs:
        draws = int((entry.get('draws') if isinstance(entry, dict) else 0) or banner.get('draws') or 1)
        out.append(('Multi-summon' if draws > 1 else 'Single summon', entry, draws, {}, None))
    offer = banner.get('secondary_offer')
    if isinstance(offer, dict) and offer:
        cost = offer.get('cost') or {}
        draws = int((cost.get('draws') if isinstance(cost, dict) else 0) or offer.get('draws') or
                    banner.get('draws') or 1)
        out.append(('Multi-summon' if draws > 1 else 'Single summon', cost, draws, {}, offer))
    if len(out) == 2 and out[0][0] == out[1][0]:
        out = [(f'Summon {i + 1}', *rest) for i, (_, *rest) in enumerate(out)]
    return out


def _guarantee_html(banner, pool, guarantee, draws, slots) -> tuple[str, list]:
    """(sentences, [(title, pool)]) for one offer's guarantee, as `roll_gacha` applies it."""
    from ffbe_gacha import unit_name
    from player_state import summon_guarantee_pool
    lines, tables = [], []
    if guarantee.get('unit_id') is not None:
        lines.append(f'{escape(unit_name(guarantee["unit_id"]) or "A featured unit")} is guaranteed: '
                     'if no draw gives them, the first draw is replaced.')
    if guarantee.get('any_of'):
        names = ', '.join(escape(unit_name(u) or str(u)) for u in guarantee['any_of'])
        lines.append(f'One of {names} is guaranteed: if none is drawn, the lowest draw becomes one of them, '
                     'equally likely.')
    rarity = guarantee.get('rarity')
    if rarity is not None and guarantee.get('unit_id') is None:
        rarity = int(rarity)
        if 'count' in guarantee:
            count = int(guarantee.get('count', 1))
            reserved = sum(c for c, _, _ in slots)
            lines.append(f'{count} of the {draws} draws {"is" if count == 1 else "are"} drawn only from '
                         f'{_rarity_label(rarity)}{" or higher" if rarity < 7 else ""}'
                         + (f' (before the {reserved} slot{"s" if reserved != 1 else ""} below)' if reserved else '')
                         + '.')
            tables.append((f'Guaranteed {_rarity_label(rarity)}+ draw', summon_guarantee_pool(pool, guarantee, banner)))
        else:
            lines.append(f'At least one {_rarity_label(rarity)}{" or higher" if rarity < 7 else ""}: '
                         'if no draw reaches it, the lowest draw is replaced with one picked from this list.')
            cand = [e for e in pool if _rarity(e) >= rarity] or pool
            tables.append((f'Guaranteed {_rarity_label(rarity)}+ draw', cand))
    for count, candidates, label in slots:
        lines.append(f'{count} more draw{"s" if count != 1 else ""}: one {escape(label)} each, from its own list.')
        tables.append((f'{escape(label[:1].upper() + label[1:])} slot', candidates))
    return ' '.join(lines), tables


def page(banner_id):
    from ffbe_gacha import all_banners
    from player_state import summon_pool, summon_slots
    banner = next((b for b in all_banners() if str(b['id']) == str(banner_id)), None)
    if banner is None:
        return None
    from urllib.parse import quote
    name = str(banner.get('name') or 'Summon')
    art = (banner.get('art') or {}).get('banner') or ''
    parts = ['<header class="mast">']
    if art:
        parts.append(f'<img class="art" src="/banner/en/sd/static_banner/gacha/main/{escape(quote(art))}" '
                     'alt="" width="640" height="160" onerror="this.style.display=\'none\'">')
    parts.append(f'<p class="eyebrow">Summon Rates</p><h1>{escape(name)}</h1></header>')

    if banner.get('selection'):
        from exvius_actions import _mst
        from ffbe_gacha import unit_name
        choices = _mst('F_GACHA_SELECT_UNIT_MST.ndjson', '3HriTp6B')
        import exvius_gacha_select      # the limited and collab units added to the list (EXVIUS_SELECT_LIMITED)
        choices = dict(choices, **{row['3HriTp6B']: row for row in exvius_gacha_select.extra_unit_rows()
                                   if row['3HriTp6B'] not in choices})
        rows = sorted(({'unit_id': uid, 'rarity': (__import__('player_state').unit_mst(uid) or {}).get('9fW0TePj'),
                        'rate': 1, 'tickets': row.get('e4mG8jTc')} for uid, row in choices.items()),
                      key=lambda r: (_rarity(r), unit_name(r['unit_id']).lower()))
        parts.append('<section><h2><span>Choose one</span></h2><p class="note">Pick a unit from the selection '
                     'list; nothing is drawn at random.</p><ul class="units">' + ''.join(
                         _card(r, None, escape(str(r["tickets"])) + ' tickets')
                         for r in rows) + '</ul></section>')
        return _wrap(name, parts)

    if banner.get('boxes'):
        parts.append('<section><h2><span>Boxes</span></h2><p class="note">The boxes are drawn without '
                     'replacement; their contents and what is left are on the Box Details screen. After the last '
                     'box, every draw of the standard summon uses the chances below.</p></section>')
        after = summon_pool(banner)       # the banner's own list and rates, as gacha_box.roll draws it
        if after:
            parts.append('<section><h2><span>After the boxes</span></h2>' + _pool_html(after) + '</section>')
        return _wrap(name, parts)

    pool = summon_pool(banner)
    rows = []
    for label, cost, draws, step, offer in _offers(banner):
        guarantee = (step.get('guarantee') or (offer or {}).get('guarantee') or banner.get('guarantee') or {})
        slots = summon_slots(banner, step)
        part = offer if (offer or {}).get('pool') is not None else step
        own = summon_pool(banner, part) if (part or {}).get('pool') is not None else None
        text, tables = _guarantee_html(banner, own or pool, guarantee, draws, slots)
        if own:
            # A step with raised rates draws from its own list: show it under that step.
            tables = [(f'{label}: every draw', own)] + tables
            text = (text + ' ' if text else '') + 'This step draws with its own, higher chances (listed below).'
        bonuses = (offer or {}).get('bonus_rewards', step.get('bonus_rewards', banner.get('bonus_rewards', [])))
        choices = (offer or {}).get('bonus_choice', step.get('bonus_choice', banner.get('bonus_choice', [])))
        rows.append((label, cost, draws, text, tables, bonuses, choices))

    parts.append('<section><h2><span>How it pulls</span></h2><div class="offers">')
    for label, cost, draws, text, _tables, bonuses, choices in rows:
        extra = ''
        if bonuses:
            extra += '<p class="bonus">Also: ' + ', '.join(
                escape(reward_name(r)) + f' &times;{int(r.get("count", 1))}' for r in bonuses) + '</p>'
        if choices:
            total = sum(float(c['rate']) for c in choices) or 1
            extra += '<p class="bonus">Plus one of: ' + '; '.join(
                ', '.join(escape(reward_name(r)) + f' &times;{int(r.get("count", 1))}' for r in c['rewards'])
                + f' ({_pct(float(c["rate"]) / total)})' for c in choices) + '</p>'
        parts.append(f'<div class="offer"><h3>{escape(label)}<span>{draws} draw{"s" if draws != 1 else ""} '
                     f'&middot; {_cost_text(cost)}</span></h3>'
                     + (f'<p>{text}</p>' if text else '<p>Every draw uses the chances below.</p>') + extra + '</div>')
    if banner.get('ticket_group_id'):
        parts.append('<p class="note">A summon ticket guarantees at least its own rarity on the draw it pays for.</p>')
    milestone = banner.get('milestone_bonus') or {}
    if int(milestone.get('every', 0) or 0) > 0:
        parts.append('<p class="note">Every ' + str(int(milestone['every'])) + ' summons also give: ' + ', '.join(
            escape(reward_name(r)) + f' &times;{int(r.get("count", 1))}' for r in milestone.get('rewards', []))
            + '.</p>')
    parts.append('</div></section>')

    parts.append('<section><h2><span>Every draw</span></h2>' + _pool_html(pool) + '</section>')
    seen = set()
    for _label, _cost, _draws, _text, tables, _b, _c in rows:
        for title, table in tables:
            key = (title, tuple(sorted((str(r.get('unit_id') or r.get('id')), r.get('rate')) for r in table)))
            if key in seen:
                continue
            seen.add(key)
            parts.append(f'<section><h2><span>{title}</span></h2>' + _pool_html(table) + '</section>')
    parts.append('<footer>Chances are per draw, from the pool this summon draws from this week.</footer>')
    return _wrap(name, parts)


def index_page() -> str:
    """This week's summons, each linking to its rates page: the answer when a request names no banner."""
    import os
    from ffbe_gacha import all_banners
    from ffbe_state import State
    from urllib.parse import quote
    # The same list the summon screen gets (ffbe_gacha.serve_gacha_info): this week's summons plus any the
    # player's tickets unlock.
    banners = all_banners()
    if os.environ.get('EXVIUS_SUMMON_ARCHIVE') == '1':
        from gacha_archive import visible_banners
        banners = visible_banners(State.player, banners)
    by_id = {str(b['id']): b for b in banners}
    ids = list(by_id)
    parts = ['<header class="mast"><p class="eyebrow">Summon Rates</p><h1>This week\'s summons</h1></header>',
             '<section class="offers">']
    for bid in ids:
        banner = by_id[bid]
        art = (banner.get('art') or {}).get('banner') or ''
        img = (f'<img class="art" src="/banner/en/sd/static_banner/gacha/main/{escape(quote(art))}" alt="" '
               'loading="lazy" onerror="this.style.display=\'none\'">') if art else ''
        parts.append(f'<a class="offer link" href="/exvius/gacha-rates/{escape(bid)}.html">{img}'
                     f'<h3>{escape(str(banner.get("name") or bid))}<span>View rates &rsaquo;</span></h3></a>')
    parts.append('</section>')
    return _wrap('Summon Rates', parts)


def _wrap(name: str, parts: list) -> str:
    return PAGE.replace('{{TITLE}}', escape(name)).replace('{{BODY}}', '\n'.join(parts))


PAGE = """<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<title>{{TITLE}}</title>
<style>
/* The notice pages' look (replay_notices.py): night-blue sheet, gold rules, gilt headings. */
:root{--night:#0d1230;--sheet:#151b42;--ink:#f3ecd9;--muted:#b4abc9;--gold:#e8c46a;--gilt:#fff1bf;
--line:rgba(232,196,106,.45);color-scheme:dark;
--display:"Cinzel","Trajan Pro",Georgia,"Times New Roman",serif;--body:"Avenir Next","Segoe UI",Roboto,Helvetica,Arial,sans-serif}
*{box-sizing:border-box}
html{background:var(--night)}
body{margin:0;background:radial-gradient(120% 60% at 50% 0%,#2a2464 0%,var(--night) 70%) fixed,var(--night);
color:var(--ink);font:16px/1.45 var(--body);padding:18px max(16px,env(safe-area-inset-right,0px)) 36px max(16px,env(safe-area-inset-left,0px))}
.mast{text-align:center;padding:0 0 14px;border-bottom:1px solid var(--line);margin-bottom:16px}
.mast .art{display:block;width:100%;height:auto;border:1px solid var(--line);border-radius:4px;margin-bottom:12px;background:#0a0d22}
.eyebrow{margin:0;font:600 11px/1 var(--body);letter-spacing:.28em;text-transform:uppercase;color:var(--gold)}
h1{margin:8px 0 0;font:700 23px/1.15 var(--display);color:var(--gilt);text-wrap:balance;
text-shadow:0 1px 0 #6b4c12,0 0 18px rgba(232,196,106,.25)}
section{display:grid;gap:12px;margin-bottom:22px}
h2{display:flex;align-items:center;gap:10px;margin:4px 0 0;font:700 15px/1 var(--display);letter-spacing:.14em;
text-transform:uppercase;color:var(--gold)}
h2::before,h2::after{content:"";flex:1;height:1px;background:linear-gradient(90deg,transparent,var(--line))}
h2::after{background:linear-gradient(90deg,var(--line),transparent)}
.offers{display:grid;gap:10px}
.offer{background:var(--sheet);border:1px solid var(--line);border-radius:4px;padding:10px 12px}
.offer h3,.tier h3{margin:0;display:flex;flex-wrap:wrap;align-items:baseline;justify-content:space-between;gap:2px 10px;
font:700 16px/1.25 var(--display);color:var(--gilt)}
.offer h3 span,.tier h3 span{font:600 12px/1.3 var(--body);color:var(--muted);font-variant-numeric:tabular-nums}
.offer p{margin:6px 0 0;font-size:14px;color:var(--ink)}
.offer .bonus{color:var(--gilt)}
.offer.link{display:grid;gap:8px;color:inherit;text-decoration:none}
.offer.link .art{width:100%;height:auto;border-radius:3px}
.note{margin:0;font-size:13px;color:var(--muted)}
.tier{background:var(--sheet);border:1px solid var(--line);border-radius:4px;padding:10px 8px 6px}
.tier h3{padding:0 4px 6px;border-bottom:1px solid rgba(232,196,106,.2)}
.tier.r5 h3,.tier.r6 h3{color:#ffe08a}
.tier.r7 h3{color:#ffb8e6}
.units{list-style:none;margin:0;padding:8px 0 4px;display:grid;grid-template-columns:repeat(auto-fill,minmax(84px,1fr));gap:12px 4px}
.units li{display:grid;justify-items:center;align-content:end;text-align:center;min-width:0;
background:radial-gradient(50% 9px at 50% 72px,rgba(232,196,106,.22),transparent) no-repeat}
.units img{height:76px;width:auto;max-width:100%;object-fit:contain;image-rendering:pixelated;filter:drop-shadow(0 3px 2px rgba(0,0,0,.6))}
.units img.none{visibility:hidden}
.units .token{height:76px;display:grid;place-items:center;font-size:34px;color:var(--gold)}
.units b{font:600 12px/1.2 var(--body);color:var(--gilt);margin-top:4px;overflow-wrap:anywhere}
.units .stars{font-size:11px;letter-spacing:-.05em;color:var(--gold);line-height:1.3}
.units .nv{font:700 10px/1 var(--body);letter-spacing:.08em;color:#2b0a28;background:linear-gradient(90deg,#ffb8e6,#fff1bf);
padding:2px 5px;border-radius:2px;margin:2px 0 1px}
.units em{font:normal 600 12px/1.2 var(--body);color:var(--ink);font-variant-numeric:tabular-nums}
.empty{margin:0;color:var(--muted);font-size:14px;text-align:center}
footer{text-align:center;color:var(--muted);font-size:11px;letter-spacing:.06em}
</style></head><body>
{{BODY}}
</body></html>"""
