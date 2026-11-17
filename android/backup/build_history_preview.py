"""Build a compact preview index from the current FFBE source catalogues.

Usage: python3 android/backup/build_history_preview.py source/server android/backup/history_preview_index.json
Run at release/build time, not inside the Web Helper or Android. All date
intervals are derived using the game's history_runs rather than hand-entered.
"""
from __future__ import annotations
import json
import sys
from pathlib import Path


def build(source: Path) -> dict:
    source = Path(source).resolve()
    sys.path.insert(0, str(source))
    try:
        import history_runs
        from event_archive import document
        from gacha_archive import permanent
        from gacha_rotation import _kind
        out = {'schema': 1, 'banners': [], 'events': []}
        seen = set()
        for filename in ('gacha_community.json', 'gacha_authored.json', 'gacha_named.json',
                         'gacha_deals.json', 'gacha_catalogue.json', 'gacha_raids.json'):
            for banner in json.loads((source / filename).read_text('utf-8')).get('banners', []):
                bid = str(banner.get('id', ''))
                if not bid or bid in seen or permanent(banner):
                    continue
                seen.add(bid)
                run = history_runs.banner_run(banner)
                if run is None:
                    continue
                release_info = (banner.get('community') or {})
                explicit_end = (release_info.get('until') or banner.get('until') or
                                (history_runs._doc('banner_runs.json').get('runs', {}).get(bid) or {}).get('until'))
                kind = 'Limitado' if banner.get('tab') == 'limited' or banner.get('community') else 'Outro banner'
                out['banners'].append({
                    'name': str(banner.get('name') or 'Banner sem nome')[:240], 'kind': kind,
                    'runs': [[run[0].isoformat(), run[1].isoformat(), not bool(explicit_end)]]})
        # Calendar/recovered catalogues can publish the same named campaign
        # under different IDs. Keep one entry and prefer a documented end.
        deduplicated = {}
        for row in out['banners']:
            key = (row['name'], row['runs'][0][0], row['kind'])
            current = deduplicated.get(key)
            if current is None or (current['runs'][0][2] and not row['runs'][0][2]):
                deduplicated[key] = row
        out['banners'] = list(deduplicated.values())
        for event in document()['events']:
            if event.get('group') == 'permanent':
                continue  # The preview concerns temporary content, not permanent chambers.
            windows = event.get('windows') or []
            if windows:
                runs = [[str(start), str(end), False] for start, end in windows]
            else:
                known = history_runs._doc('event_runs.json').get('runs', {}).get(str(event.get('area')), [])
                runs = []
                for start, end in history_runs.event_runs(event):
                    documented = any(history_runs._day(x.get('start')) == start and x.get('end')
                                     for x in known)
                    runs.append([start.isoformat(), end.isoformat(), not documented])
            if runs:
                out['events'].append({'name': str(event.get('name') or 'Evento sem nome')[:240],
                                      'kind': str(event.get('kind') or 'Evento')[:100], 'runs': runs})
        return out
    finally:
        sys.path.remove(str(source))


if __name__ == '__main__':
    if len(sys.argv) != 3:
        raise SystemExit('usage: build_history_preview.py SOURCE_DIR OUTPUT_JSON')
    output = Path(sys.argv[2])
    contents = json.dumps(build(Path(sys.argv[1])), ensure_ascii=False, separators=(',', ':'))
    output.write_text(contents + '\n', encoding='utf-8')
    print('PREVIEW_INDEX', output, len(contents), 'bytes')
