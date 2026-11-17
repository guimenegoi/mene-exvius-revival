"""Read-only, source-derived preview for a selected historical FFBE period.

The compact index is built from the game's own banners, event archive and
history_runs. No player state, remote credentials or live save is accessed.
"""
from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path

MAX_INDEX = 2_000_000
MAX_VISIBLE = 6
END_DATE = date(2024, 10, 30)


class Catalogue:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.banners = []
        self.events = []
        try:
            if self.path.is_symlink() or self.path.stat().st_size > MAX_INDEX:
                raise ValueError('Unsafe historical preview index')
            document = json.loads(self.path.read_text('utf-8'))
            if not isinstance(document, dict) or document.get('schema') != 1:
                raise ValueError('Invalid historical preview index')
            for group in ('banners', 'events'):
                rows = document[group]
                if not isinstance(rows, list) or len(rows) > 3000:
                    raise ValueError('Invalid historical preview entries')
                for row in rows:
                    if (not isinstance(row, dict) or set(row) != {'name', 'runs', 'kind'}
                            or not isinstance(row['name'], str) or len(row['name']) > 240
                            or not isinstance(row['runs'], list) or len(row['runs']) > 60
                            or not isinstance(row['kind'], str)):
                        raise ValueError('Invalid historical preview row')
                    for run in row['runs']:
                        if (not isinstance(run, list) or len(run) != 3
                                or type(run[2]) is not bool):
                            raise ValueError('Invalid historical preview interval')
                        start, end = date.fromisoformat(run[0]), date.fromisoformat(run[1])
                        if start > end:
                            raise ValueError('Inverted historical preview interval')
                setattr(self, group, rows)
        except (OSError, ValueError, KeyError, TypeError, UnicodeError):
            self.banners = []
            self.events = []
            self.available = False
        else:
            self.available = True

    def summary(self, start: date, week: int) -> dict:
        if not self.available:
            return {'available': False, 'banners': [], 'events': [], 'range': ''}
        if type(week) is not int or not 0 <= week <= 430 or start < date(2016, 6, 30):
            raise ValueError('Invalid historical period')
        begin = start + timedelta(weeks=week)
        end = begin + timedelta(days=6)
        if begin > END_DATE:
            raise ValueError('Historical period exceeds Global service')

        def group(rows):
            found = []
            for row in rows:
                overlaps = [r for r in row['runs'] if date.fromisoformat(r[0]) <= end
                            and date.fromisoformat(r[1]) >= begin]
                if overlaps:
                    found.append({'name': row['name'], 'kind': row['kind'],
                                  'estimated': all(r[2] for r in overlaps),
                                  'from': min(r[0] for r in overlaps)})
            found.sort(key=lambda r: (r['from'], r['name']), reverse=True)
            # Return a small representative sample; indicate truncation accurately.
            return {'total': len(found), 'items': [
                {'name': row['name'], 'kind': row['kind'], 'estimated': row['estimated']}
                for row in found[:MAX_VISIBLE]]}

        return {'available': True, 'range': f'{begin:%d/%m/%Y}–{end:%d/%m/%Y}',
                'banners': group(self.banners), 'events': group(self.events)}
