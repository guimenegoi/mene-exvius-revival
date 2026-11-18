"""Build a compact preview index from the current FFBE source catalogues.

Usage: python3 android/backup/build_history_preview.py source/server android/backup/history_preview_index.json
Run at release/build time, not inside the Web Helper or Android. All date
intervals are derived using the game's history_runs rather than hand-entered.
"""
from __future__ import annotations
import json
import re
import sys
from pathlib import Path


def vault_2016_calendar(note: Path) -> list[dict]:
    """Extract only dated event/trial entries, never infer when they ended.

    Availability wording comes from the vault's separate preservation table.
    The original note is read at index-generation time, not served at runtime.
    """
    contents = Path(note).read_text('utf-8')
    main = contents.split('## Disponibilidade dos eventos de 2016 no Offline', 1)[0]
    table = contents.split('## Disponibilidade dos eventos de 2016 no Offline', 1)[-1]
    availability = []
    for row in table.splitlines():
        columns = [item.strip() for item in row.strip().strip('|').split('|')]
        if len(columns) == 3 and re.fullmatch(r'2016-\d{2}-\d{2}', columns[0]):
            availability.append((columns[1], columns[2]))
    collected = []
    for row in main.splitlines():
        match = re.match(r'^- \*\*(2016-\d\d-\d\d)\*\* · :Li(CalendarDays|Swords): (?:Evento|Trial) — (.+)$', row)
        if not match:
            continue
        when, symbol, name = match.groups()
        # Strip only Markdown emphasis; retain the source's terminology.
        name = name.replace('**', '').split(' · ', 1)[0].strip()
        label = 'Trial' if symbol == 'Swords' else 'Evento'
        matching = [description for title, description in availability if title.casefold() in name.casefold()]
        status = matching[0] if matching else 'Disponibilidade no Revival não verificada'
        collected.append({'date': when, 'name': name[:240], 'kind': label,
                          'availability': status[:240]})
    return collected


def build(source: Path, vault_2016: Path | None = None) -> dict:
    source = Path(source).resolve()
    sys.path.insert(0, str(source))
    try:
        import history_runs
        from event_archive import document
        from gacha_archive import permanent
        from gacha_rotation import _kind
        out = {'schema': 1, 'banners': [], 'events': []}
        if vault_2016 is not None:
            out['calendar'] = vault_2016_calendar(vault_2016)
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
    if len(sys.argv) not in (3, 4):
        raise SystemExit('usage: build_history_preview.py SOURCE_DIR OUTPUT_JSON [VAULT_2016_NOTE]')
    output = Path(sys.argv[2])
    contents = json.dumps(build(Path(sys.argv[1]), Path(sys.argv[3]) if len(sys.argv) == 4 else None),
                          ensure_ascii=False, separators=(',', ':'))
    output.write_text(contents + '\n', encoding='utf-8')
    print('PREVIEW_INDEX', output, len(contents), 'bytes')
