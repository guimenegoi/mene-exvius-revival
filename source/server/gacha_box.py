"""Finite raid boxes, sampled without replacement, through the native box screens."""
import copy
import secrets


def state(player, banner):
    return copy.deepcopy((player.data if player is not None else {}).get('gacha', {}).get('boxes', {}).get(str(banner['id']),
                         {'index': 0, 'drawn': {}}))


def detail_id(player, banner):
    return str(int(banner['id']) * 10 + state(player, banner)['index'] + 1)


def box_id(player, banner):
    index = state(player, banner)['index']
    return str(int(banner['box_base_id']) + index) if index < len(banner['boxes']) else '0'


def _target(entry):
    reward = entry['reward']
    return '%s:%s:%s:10000:1' % (reward['kind'], reward['id'], reward['count'])


def groups(player, banner):
    saved = state(player, banner)
    index = saved['index']
    masters, owned = [], []
    for number, box in enumerate(banner['boxes']):
        bid = int(banner['box_base_id']) + number
        counts = saved['drawn'].get(str(number), {})
        for order, entry in enumerate(box):
            eid = str(bid * 1000 + order + 1)
            target = _target(entry)
            if number == index:
                masters.append({'h6Tg0oGd': str(bid), 'Eebs2mB1': eid,
                    '7iJpH5zZ': target, 'G4L0YIB2': entry['label'],
                    'es0Yun3Z': str(entry['copies']), 'Z0EN6jSh': str(order),
                    '0A34Ucnk': str(entry['copies'] if entry.get('featured') else 0)})
            if counts.get(eid):
                owned.append({'h6Tg0oGd': str(bid), 'Eebs2mB1': eid,
                              '08MuyfqD': str(counts[eid]), '5vFjunq1': target})
    return {'z79fCYip': masters, '05GvszcZ': owned}


def roll(player, banner, requested_detail, repeats=1):
    if player.mode == 'frozen' or str(requested_detail) != detail_id(player, banner):
        return None
    saved = state(player, banner)
    index = saved['index']
    repeats = int(repeats)
    maximum = 50 if index < len(banner['boxes']) else 500
    if not 1 <= repeats <= maximum:
        return None
    if index >= len(banner['boxes']):
        # After the last box: the raid's standard summon, at its own price where Global's differed
        # (`after_cost`, e.g. 100 coins against 200 a box pull; 2026-11-10).
        cost = dict(banner['cost'], **(banner.get('after_cost') or {}))
        offer = dict(banner, draws=repeats, cost=dict(cost, amount=int(cost['amount']) * repeats))
        result = player.roll_gacha(offer, repeats)
        if result:
            result['detail_id'] = detail_id(player, banner)
        return result
    box = banner['boxes'][index]
    bid = int(banner['box_base_id']) + index
    counts = saved['drawn'].setdefault(str(index), {})
    total = sum(int(entry['copies']) - int(counts.get(str(bid * 1000 + order + 1), 0))
                for order, entry in enumerate(box))
    if total <= 0:
        return None
    draws = min(repeats, total)
    cost = banner['cost']
    if player.item_count(20, cost['item_id']) < int(cost['amount']) * draws:
        return None
    before, dirty = copy.deepcopy(player.data), player.dirty
    result = None
    try:
        for _ in range(draws):
            pick = secrets.randbelow(total)
            for order, entry in enumerate(box):
                eid = str(bid * 1000 + order + 1)
                pick -= int(entry['copies']) - int(counts.get(eid, 0))
                if pick < 0:
                    break
            selected = dict(banner, draws=1, reward_pool=[dict(entry['reward'], rate=1)])
            pulled = player.roll_gacha(selected, 1)
            if pulled is None:
                raise ValueError('Raid box reward could not be granted')
            if result is None:
                result = copy.deepcopy(pulled)
            else:
                for field in ('awards', 'nv_cards', 'bonus_awards', 'reward_awards'):
                    result[field].extend(pulled[field])
            counts[eid] = int(counts.get(eid, 0)) + 1
            total -= 1
    except Exception:
        player.data, player.dirty = before, dirty
        raise
    player.data['gacha'].setdefault('boxes', {})[str(banner['id'])] = saved
    player.dirty = True
    result['detail_id'] = detail_id(player, banner)
    result['count'] = result['repeats'] = draws
    from player_state import effect_pattern_for
    result['pattern_id'] = effect_pattern_for(max((int(a.get('granted_rarity') or 1)
                                                 for a in result['awards']), default=1), banner['id'])
    totals = {}
    for reward in result['reward_awards']:
        key = (reward['kind'], reward['id'])
        totals[key] = totals.get(key, 0) + reward['count']
    result['reward_awards'] = [{'kind': k, 'id': iid, 'count': count} for (k, iid), count in totals.items()]
    player.data['gacha']['last_pull'] = result
    return result


def next_box(spec, req):
    from exvius_actions import _node, _refresh
    from ffbe_gacha import all_banners, gacha_groups
    from ffbe_state import State, _note
    player = State.player
    node = _node(req, '5yLD4dYI') or {}
    banners = all_banners()
    banner = next((b for b in banners if str(b['id']) == str(node.get('X1IuZnj2')) and b.get('boxes')), None)
    if player is None or player.mode == 'frozen' or banner is None:
        return spec
    saved = state(player, banner)
    index = saved['index']
    if str(node.get('nqzG3b2v')) == detail_id(player, banner) and index < len(banner['boxes']):
        bid = int(banner['box_base_id']) + index
        drawn = saved['drawn'].get(str(index), {})
        pending = any(int(drawn.get(str(bid * 1000 + order + 1), 0)) < entry['copies']
                      for order, entry in enumerate(banner['boxes'][index]) if entry.get('featured'))
        if not pending:
            saved['index'] += 1
            player.data['gacha'].setdefault('boxes', {})[str(banner['id'])] = saved
            player.dirty = True
        else:
            _note('Raid box: featured rewards must be drawn before advancing')
    out = _refresh(spec)
    out.pop('5yLD4dYI', None)
    # The same list the summon screen and a pull's reply carry (ffbe_gacha.serve_gacha_info): this week's summons
    # and the ones a held ticket opens. Every banner in the game was sent here (1,300+ rows, 2 s).
    import os
    shown = banners
    if os.environ.get('EXVIUS_SUMMON_ARCHIVE') == '1':
        from gacha_archive import visible_banners
        shown = visible_banners(player, banners)
    out.update(gacha_groups(shown))
    return out


HANDLERS = {'xa9uR3pI': next_box}
