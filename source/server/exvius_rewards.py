"""Decode the original rated reward tuples without dropping unit metadata."""
from player_state import unit_mst


def _recipe_or_item(reward):
    """A recipe whose recipe-book row is missing can't be granted or crafted; pay the item it crafted instead
    (content/recipe_substitutes.json, operator's request 2026-11-09). Usable recipes are left as they are."""
    from player_state import _load_ndjson
    book = _load_ndjson('F_RECIPE_BOOK_MST.ndjson', 'staFu8U1').get(str(reward['id']))
    if book and str(book.get('gJf3zp8a', '')).isdigit():
        return reward
    sub = _substitutes().get(str(reward['id']))
    if not sub:
        return reward
    kind, iid = sub.split(':')[:2]
    return {'kind': int(kind), 'id': int(iid), 'count': reward['count']}


_SUBSTITUTES = None


def _substitutes():
    global _SUBSTITUTES
    if _SUBSTITUTES is None:
        import json
        from pathlib import Path
        try:
            doc = json.loads(Path(__file__).with_name('content').joinpath('recipe_substitutes.json')
                             .read_text(encoding='utf-8'))
            _SUBSTITUTES = {k: v['reward'] for k, v in doc.get('recipes', {}).items()}
        except (OSError, ValueError, KeyError):
            _SUBSTITUTES = {}
    return _SUBSTITUTES


def card_text(text: str) -> str:
    """A reward string with every Vision Card entry (kind 27) in Global's full form, `27:id:count:100:level`.

    Global's tables write card rewards that way 3,447 times (F_MEDAL_EXCHANGE_MST, F_NV_EX_CLASS_UP_MST, ...).
    The short `27:id:count` left the level empty, and viewing such a card (the VIP Shop's Metal Gigantuar's
    Here!, 2026-11-12) crashed the phone: a card at level 0 makes it look up its level row at index -1
    (`VisionCardGrowMst::getGrowthRate`, see `PlayerState.vision_card_rows`)."""
    out = []
    for entry in str(text or "").split(","):
        fields = entry.split(":")
        if len(fields) >= 3 and fields[0].strip() == "27" and len(fields) < 5:
            fields = fields[:3] + ["100", "1"] if len(fields) == 3 else fields[:4] + ["1"]
        out.append(":".join(fields))
    return ",".join(out)


def reward_text(rows) -> str:
    """`kind:id:count` per reward row, comma-joined, Vision Cards in the full form (card_text)."""
    return card_text(",".join(f"{r['kind']}:{r['id']}:{r['count']}" for r in rows))


def parse(raw, exchange=False):
    """Reward tuples `kind:id:count[:rate[:...]]`. A rate other than 100 is refused, except for an exchange
    (`exchange=True`): a purchase always pays, and four F_MEDAL_EXCHANGE_MST rows carry other values there
    (Mana Mystery's Aura Glove 70712 `:101` and Ninja's Trump 70713 `:102`; 226406/228606 `:0`). Refusing
    them raised in King Mog's store and the phone showed "A connection error has occurred" (2026-11-11)."""
    result = []
    for entry in filter(None, str(raw or '').split(',')):
        fields = [field.strip() for field in entry.split(':')]
        if len(fields) not in (3, 4, 5, 7, 9, 10) or not all(f.isascii() and f.isdigit() for f in fields):
            raise ValueError('invalid native reward tuple: ' + entry)
        kind, iid, count = map(int, fields[:3])
        if count <= 0 or (len(fields) > 3 and fields[3] != '100' and not exchange):
            raise ValueError('invalid native reward quantity or rate')
        reward = {'kind': kind, 'id': iid, 'count': count}
        if kind == 60:
            reward = _recipe_or_item(reward)    # a lost recipe pays the item it crafted
        if kind == 10:
            if len(fields) >= 5:
                reward['level'] = max(1, int(fields[4]))
            if len(fields) in (7, 9, 10):
                points = int(fields[5])
                target = int(fields[-1])
                channel = 1 if target >= 1000000000 else 0
                target_id = target - channel * 1000000000
                # Only trust moogles carry a target trust reward. Cactuar
                # targets are unit-specific fusion restrictions instead.
                if str(iid).startswith(('904', '906')):
                    master = unit_mst(target_id) if target else None
                    descriptor = (master or {}).get(('9mu4boy7', 'C74EmZ1I')[channel])
                    reward['affinity_points'] = ['', '']
                    reward['affinity_info'] = ['', '']
                    if descriptor:
                        reward['affinity_info'][channel] = descriptor
                        points = points or int(descriptor.split(':')[3])
                    elif 100000000 < target_id <= 100000100:
                        # Original generic trust IDs encode the percentage:
                        # 100000005 = 5%, 1100000050 = 50% super trust.
                        points = points or (target_id - 100000000) * 10
                    reward['affinity_points'][channel] = str(points)
                elif target:
                    reward['reward_target_master'] = target
        elif kind == 27 and len(fields) == 5:
            reward['level'] = max(1, int(fields[4]))
        elif len(fields) > 5 or (len(fields) == 5 and fields[4] not in ('0', '1')):
            raise ValueError('unit metadata attached to a non-unit reward')
        result.append(reward)
    return result
