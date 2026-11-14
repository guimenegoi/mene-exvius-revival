"""Browse the existing summon catalogue by story season and collaboration."""
from collections import defaultdict
from datetime import date
import json
from pathlib import Path


# Global story starts from the existing calendar's source, Update_Schedule.
# These are browsing eras, not save progression or real-time availability gates.
STORY_STARTS = (date(2017, 11, 16), date(2020, 1, 30), date(2021, 11, 18))
COLLABORATIONS = (
    'Brave Frontier', 'Crystal Defenders', 'Deus Ex', 'Dragon Quest',
    'Fullmetal Alchemist', 'Just Cause', "King's Knight", 'Kingdom Hearts',
    'Legend of Mana', 'NieR', 'Octopath Traveler', 'Secret of Mana', 'Star Ocean',
    'Tomb Raider', 'Trials of Mana', 'Valkyrie Profile', 'WOTV', 'Xenogears', 'Katy Perry',
)
GROUPS = (('standard', 'Standard'), ('season1', 'Season 1'), ('season2', 'Season 2'),
          ('season3', 'Season 3'), ('season4', 'Season 4'), ('collaborations', 'Collab'))
# Always-available summons, shown with every group (as on the live game).
PERMANENT_NAMES = {'Standard Summon', 'Rare Summon', 'Premium 10+1 Summon', '5★ Guaranteed 10+1 Summon'}
# Original GL9 tab of each GachaMst type code: GachaTopScene::setListLayout
# (0x2120554) files a banner by GachaMst::isPayType / isFreeType (0, 6, 900) /
# isLimitedType (50, 7).
FREE_CODES, LIMITED_CODES = {0, 6, 900}, {50, 7}


def english_art(banner):
    """True when the banner's art is Global English art: the saved Global cache or the community calendar."""
    import os
    import data_paths
    from ffbe_gacha import banner_art_index
    path = banner_art_index().get(str((banner.get('art') or {}).get('banner') or ''))
    if not path:
        return False
    roots = (data_paths.COMMUNITY_ART_ROOT, os.path.join(data_paths.GAME_FILES, 'en'),
             os.path.join(data_paths.CDN_ROOT, 'en'))
    path = os.path.normcase(os.path.abspath(path))
    return any(path.startswith(os.path.normcase(os.path.abspath(root)) + os.sep) for root in roots)


def _ticket_only(banner):
    cost = banner.get('cost')
    cost = cost[0] if isinstance(cost, list) and cost else cost
    return not cost or (
        isinstance(cost, dict) and cost.get('kind') in ('ticket', 'important', 'item'))


def wire_type(banner, code):
    """The GachaMst type code that puts the banner on its original tab.
    Community-calendar banners were the limited-time event summons; free, friend and
    ticket-only summons belong on the Standard Summon tab."""
    # Keep the native step-up type. Its behavior is distinct from the tab
    # category; the original client must still recognize isNewStepUpGacha.
    if banner.get('steps'):
        return 5
    if banner.get('selection'):
        return 6
    if banner.get('boxes'):
        return 7
    tab = banner.get('tab')
    if tab:  # an explicit original tab (named banners)
        return {'limited': 50, 'free': 0}.get(tab, code if code not in FREE_CODES | LIMITED_CODES else 1)
    if code in LIMITED_CODES or code in FREE_CODES:
        return code
    if banner.get('community'):
        return 50
    if banner.get('type') != 'step' and _ticket_only(banner):
        return 0
    return code


def _standard_families():
    doc = json.loads(Path(__file__).with_name('gacha_standard.json').read_text(encoding='utf-8'))
    return {str(row['id']) for row in doc.get('banners', [])}


def permanent(banner, families=None):
    families = _standard_families() if families is None else families
    return (str(banner['id']) in families or banner.get('name') in PERMANENT_NAMES
            or banner.get('type') == 'friend' or bool(banner.get('permanent')))


def permanent_open(banner, begin=None, end=None) -> bool:
    """Whether a dated permanent banner (`permanent: {from, until}`, YYYY-MM-DD, e.g. the Bonus Present
    Ticket Summon from Mar 2021) is on offer. With the replay, it is listed every week whose slice of history
    [begin, end) overlaps its Global period; without it, only an open-ended one is listed (2026-11-07)."""
    span = banner.get('permanent')
    if not isinstance(span, dict):
        return True
    start, until = span.get('from'), span.get('until')
    if begin is None or end is None:
        return not until
    return (not start or start < end.isoformat()) and (not until or until >= begin.isoformat())


def _collaboration(banner):
    search = banner.get('name', '') + ' ' + str((banner.get('art') or {}).get('banner', ''))
    return next((name for name in COLLABORATIONS if name.lower() in search.lower()), None)


SEASONAL_WORDS = ('halloween', 'christmas', 'holiday', 'festive', 'summer', 'swimsuit', 'valentine',
                  'bride', 'wedding', 'lunar new year', 'new year', 'spring', 'winter', 'easter')
LIMITED_SERIES = ('ffxv', 'final fantasy xv', 'ffvii remake', 'ff7r', 'final fantasy vii remake',
                  'ffx-2', 'ffxiv', 'ff14', 'dissidia', 'ff brave exvius heroes')


def limited_unit_ids() -> set:
    """Units that came only from limited-time banners: seasonal, collaborations (incl. Final Fantasy
    collabs such as FFXV), or marked `community.limited`. Most Global deal banners drew "units up to
    <date>, excluding limited/collab units" (`pool_rule.exclude`). A heuristic from banner names: a unit
    also featured on any ordinary banner is not counted (2026-11-07)."""
    global _LIMITED
    if _LIMITED is not None:
        return _LIMITED
    from ffbe_gacha import all_banners
    limited, ordinary = set(), set()
    for b in all_banners():
        com = b.get('community') or {}
        ids = {str(u) for u in (com.get('unit_ids') or [])}
        for tier in ((b.get('pool') or {}).get('tiers') or [] if isinstance(b.get('pool'), dict) else []):
            ids |= {str(u) for u in (tier.get('featured') or [])}
        if not ids:
            continue
        search = (str(b.get('name', '')) + ' ' + str((b.get('art') or {}).get('banner', ''))).lower()
        if (com.get('limited') or _collaboration(b) or any(w in search for w in SEASONAL_WORDS)
                or any(w in search for w in LIMITED_SERIES)):
            limited |= ids
        else:
            ordinary |= ids
    limited -= ordinary
    # Up to August 2019 there is a better list: banner 150 (40M DL Step-Up) carries every recovered
    # PERMANENT Global unit released by then, so any summonable unit from that period missing from it was
    # limited (FFVII, FFXV, the seasonal units...). Later units fall back to the name rule above.
    by_id = {str(b['id']): b for b in all_banners()}
    permanent = set()
    for ref in ('150', '9100203', '49'):
        pool = (by_id.get(ref) or {}).get('pool') or {}
        for tier in (pool.get('tiers') or [] if isinstance(pool, dict) else []):
            permanent |= {str(u) for u in (tier.get('units') or [])}
    if permanent:
        import replay
        from player_state import unit_roots_by_rarity
        dates = replay.unit_dates()
        roots = unit_roots_by_rarity()
        for ids in (roots.get('3', []), roots.get('4', []), roots.get('5', [])):
            for uid in ids:
                day = dates.get(str(uid))
                if day and day <= '2019-08-31' and str(uid) not in permanent and not str(uid).startswith('9'):
                    limited.add(str(uid))
    # Every unit whose wiki page was checked (content/unit_release_global.json, 2026-11-10) takes the wiki's own
    # flag: Limited / Collaboration / Seasonal, or No (Gilgamesh (FFV), a Rare Summon unit the rule above caught).
    # A blank flag keeps the rules above. A Japan-version page ("/JP", a unit Global never sold) can mark a unit
    # limited (a collaboration is one everywhere) but its "No" is Japan's record, so it doesn't clear the flag.
    try:
        import os
        with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'content', 'unit_release_global.json'),
                  encoding='utf-8') as fh:
            doc = json.load(fh)
        for uid, row in (doc.get('units') or {}).items():
            flag = (row or {}).get('limited', '')
            if flag in ('Yes', 'Collaboration', 'Seasonal'):
                limited.add(str(uid))
            elif flag == 'No' and not str((row or {}).get('page', '')).endswith('/JP'):
                limited.discard(str(uid))
        # The units Global launched with were its regular pool. Xiao and Cerius have no flag on the wiki and
        # were caught by the banner guess above (their featured banners were holiday ones).
        for uid in ((doc.get('launch') or {}).get('units') or {}):
            limited.discard(str(uid))
    except (OSError, ValueError, KeyError):
        pass
    _LIMITED = limited
    return _LIMITED


_LIMITED = None


def _released(banner):
    try:
        release = (banner.get('community') or {}).get('release') or banner['release']
        parts = list(map(int, str(release).split('-'))) + [1]
        return date(*parts[:3])
    except (KeyError, TypeError, ValueError):
        return None


def catalogue(banners):
    """Every non-permanent banner belongs to exactly one group; the permanent summons
    appear with every group. Uncertain dates stay under Standard. Collab banners are
    ordered by series, and seasons by release date."""
    families = _standard_families()
    members = defaultdict(list)
    shared = []
    seen = set()
    aliases = {str(alias) for banner in banners for alias in banner.get('alias_ids', [])
               if str(alias) != str(banner['id'])}
    for banner in banners:
        bid = str(banner['id'])
        if bid in aliases:
            continue
        # A reused picture does not make two campaigns the same. Preserve reruns
        # and distinct offers; collapse only identical campaign/offer records.
        offer = {key: banner.get(key) for key in ('cost', 'draws', 'steps', 'ticket_group_id',
                                                 'guarantee', 'secondary_offer', 'pool', 'reward_pool',
                                                 'selection', 'daily_limit', 'weekly_limit', 'purchase_limit',
                                                 'lap_limit', 'milestone_bonus', 'bonus_rewards', 'bonus_choice',
                                                 'guarantee_slots')}
        if bid in families:
            identity = ('standard', banner.get('name'), json.dumps(offer, sort_keys=True))
        else:
            identity = (((banner.get('art') or {}).get('banner'), str(_released(banner))),
                        json.dumps(offer, sort_keys=True))
        if identity in seen:
            continue
        seen.add(identity)
        if permanent(banner, families):
            shared.append(bid)
            continue
        collab = _collaboration(banner)
        released = _released(banner)
        if collab:
            members['collaborations'].append((collab, released or date.min, bid))
        elif banner.get('season'):
            members[banner['season']].append(('', released or date.min, bid))
        elif released:
            season = 1 + sum(released >= start for start in STORY_STARTS)
            members['season' + str(season)].append(('', released, bid))
        else:
            members['standard'].append(('', date.min, bid))
    by_id = {str(banner['id']): banner for banner in banners}
    from ffbe_gacha import gacha_type_code
    groups = []
    for key, label in GROUPS:
        ordered = [bid for _, _, bid in sorted(members[key], key=lambda row: (row[0], row[1]))]
        ids = shared + ordered
        # Open the group on its own lineup: Limited Time when it has limited banners.
        limited = any(by_id[bid].get('tab') == 'limited' or
                      gacha_type_code(by_id[bid]) in LIMITED_CODES for bid in ids)
        tab = 2 if limited and key != 'standard' else 0
        groups.append({'id': key, 'label': label, 'ids': ids, 'count': len(ordered), 'tab': tab})
    return groups


def selected_group(player, groups):
    selected = player.data.get('summon_archive') if player else None
    return next((group for group in groups if group['id'] == selected), groups[0])


def held_ticket_ids(player, banners):
    """Ticket-only banners (paid with an item, e.g. the SP Summon tickets) whose ticket the player holds.
    With the weekly rotation on they would otherwise be hidden, and a bought ticket would have no banner."""
    if player is None:
        return []
    import json
    out, seen = [], set()
    # Earliest first, so of two identical summons (same ticket, pool and draws) the older one is kept:
    # 9200022 over "NV Guaranteed EX Summon B" 9200023, Bonus Present Ticket Summon 9200029 (2021) over 9503470.
    def released(banner):
        return str(banner.get('release') or (banner.get('community') or {}).get('release') or '9999')
    for banner in sorted(banners, key=lambda b: (released(b), str(b['id']))):
        # Only ticket summons: a deal of another kind that happens to cost a ticket (9500060 "5★ Select
        # Ticket Lapis Summon", a 2019 `exchange` deal paid with ticket 260) isn't opened by holding it.
        if banner.get('deal') and banner.get('deal') != 'ticket':
            continue
        cost = banner.get('cost')
        cost = cost[0] if isinstance(cost, list) and cost else cost
        # `item` costs are bag items (type 20); `important` costs are important items (type 23), e.g. the
        # 1/10 NV Summon Ticket 110260 (9200022/9200023), the 5★ Select ticket 260, the Arena ticket 60 and the
        # 5+1 ticket 912. Only type 20 used to count, so a held important ticket never opened its banner.
        kind = cost.get('kind') if isinstance(cost, dict) else None
        if kind not in ('item', 'important') or not cost.get('item_id'):
            continue
        try:
            held = player.item_count(20 if kind == 'item' else 23, cost['item_id'])
        except Exception:  # noqa: BLE001 -- no inventory, no banner
            held = 0
        if held > 0:
            same = (kind, str(cost['item_id']), int(cost.get('amount') or 1),
                    json.dumps(banner.get('pool'), sort_keys=True), banner.get('draws'), banner.get('type'))
            if same in seen:
                continue
            seen.add(same)
            out.append(str(banner['id']))
    order = {str(b['id']): i for i, b in enumerate(banners)}
    return sorted(out, key=lambda bid: order[bid])    # listed in the banners' own order, as before


def used_up(player, banner) -> bool:
    """True when a deal banner can't be pulled again by this save: its per-player purchase limit is
    reached, or (for a deal step-up) all its rounds are done. Only deal banners (`deal` key) are hidden."""
    if not banner.get('deal') or player is None:
        return False
    gacha = (getattr(player, 'data', None) or {}).get('gacha', {})
    state_id = str(banner.get('state_id', banner['id']))
    limit = int(banner.get('purchase_limit') or 0)
    if limit and int(((gacha.get('user_banners') or {}).get(state_id) or {}).get('total_exe_count', 0)) >= limit:
        # A (Re)summon stays listed while its last result can still be redone.
        pending = (gacha.get('resummon') or {}).get(state_id) or {}
        return not (banner.get('resummon') and int(pending.get('left', 0)) > 0)
    laps = int(banner.get('lap_limit') or 0)
    return bool(laps and int((gacha.get('completed_laps') or {}).get(state_id, 0)) >= laps)


def visible_banners(player, banners):
    from gacha_rotation import enabled, rotation_ids
    if enabled():
        ids = rotation_ids(banners) + held_ticket_ids(player, banners)
    else:
        # EXVIUS_SUMMON_ROTATION=0: every banner at once (README), in the archive's order: the permanent summons,
        # then each group (collaborations, the story seasons, Standard), then held-ticket summons. One copy each.
        # The Android build's archive chooser can still narrow it to one group (menu); the iPhone has no chooser.
        groups = catalogue(banners)
        chosen = (player.data.get('summon_archive') if player else None) or 'all'
        group = next((g for g in groups if g['id'] == chosen), None)
        ids = (group['ids'] if group else all_ids(banners)) + held_ticket_ids(player, banners)
    ids = list(dict.fromkeys(ids))
    by_id = {str(banner['id']): banner for banner in banners}
    # A once-per-player deal (a "first 10+1" summon, the cash summon) leaves the list once it is used up,
    # as on Global, rather than staying greyed out (2026-11-07, deal banners). Same for a step-up whose
    # rounds are all done.
    ids = [bid for bid in ids if bid in by_id and not used_up(player, by_id[bid])]
    # GL9 sorts schedule rows by descending display order. Publish the archive's
    # series/date order there, rather than preserving unrelated old campaign ranks.
    return [dict(by_id[bid], schedule=dict(by_id[bid].get('schedule') or {},
                                         disp_order=len(ids) - index))
            for index, bid in enumerate(ids)]


def all_ids(banners) -> list:
    """Every listed banner, permanent summons first, then each archive group in order, without repeats."""
    out = []
    for group in catalogue(banners):
        out += group['ids']
    return list(dict.fromkeys(out))


def menu(player, banners, selection=''):
    from gacha_rotation import enabled, rotation_ids
    if enabled():
        # One fixed lineup: the season chooser has nothing to choose between.
        ids = rotation_ids(banners)
        week = {'id': 'rotation', 'label': 'This Week', 'count': len(ids), 'tab': 0}
        return {'groups': [week], 'selected': week}
    # Rotation off: "All Summons" first and by default (visible_banners), then the archive's groups.
    everything = {'id': 'all', 'label': 'All Summons', 'count': len(all_ids(banners)), 'tab': 0}
    groups = [everything] + catalogue(banners)
    if selection:
        if selection not in {group['id'] for group in groups}:
            raise ValueError('Unknown summon archive group')
        player.data['summon_archive'] = selection
        player.dirty = True
    chosen = selected_group(player, groups)
    return {'groups': [{key: group[key] for key in ('id', 'label', 'count', 'tab')} for group in groups],
            'selected': {key: chosen[key] for key in ('id', 'label', 'count', 'tab')}}
