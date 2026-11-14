"""Art for the deal banners (`gacha_deals.json`), downloaded once on startup.

Each deal banner names its list and detail images (`art.banner`, `art.detail_banner`, both `deal-<id>-*.png`)
and where Global published them (`art.urls`: the official news CDN, read through the Wayback Machine, or the
wiki). This module downloads each missing file into `DEAL_ART_ROOT` (`<data>/deal_art`), where the banner art
index finds it. A file that can't be fetched is retried on the next start; until then the summon list shows
the banner without art, as for any banner whose file is missing.

Remove: delete `<data>/deal_art` (README, removal section).

Since 2026-11-13 the summon art pack carries these images (art_pack.py) and nothing is downloaded unless
EXVIUS_DEAL_ART_FETCH=1 asks for it.
"""
from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request

PNG = b'\x89PNG\r\n\x1a\n'


def _targets() -> list[tuple[str, str, str, tuple]]:
    """[(file name, url or "", title, size)] for every deal banner image."""
    from ffbe_config import GACHA_DEALS, GACHA_RAIDS
    banners = []
    import late_banners
    for path in (GACHA_DEALS, GACHA_RAIDS, late_banners.PATH):   # raid stand-ins (2026-11-10), late banners (11-12)
        try:
            with open(path, encoding='utf-8') as fh:
                banners += json.load(fh).get('banners', [])
        except (OSError, ValueError):
            pass
    out = []
    for banner in banners:
        art = banner.get('art') or {}
        for name, url in (art.get('urls') or {}).items():
            if name:
                size = (640, 392) if name == art.get('detail_banner') and name != art.get('banner') else (640, 160)
                out.append((name, url or '', str(banner.get('name') or ''), size))
    return out


def render(title: str, size: tuple) -> bytes:
    """A plain banner with the summon's title, for deals whose Global art is lost."""
    import io
    from PIL import Image, ImageDraw, ImageFont
    width, height = size
    image = Image.new('RGB', size, (18, 28, 64))
    draw = ImageDraw.Draw(image)
    for y in range(height):   # a simple vertical gradient
        shade = int(28 + 50 * y / height)
        draw.line([(0, y), (width, y)], fill=(18, shade, 96 + shade // 2))
    draw.rectangle([3, 3, width - 4, height - 4], outline=(226, 190, 96), width=3)
    try:
        font = ImageFont.load_default(size=30 if height <= 200 else 36)
    except TypeError:   # Pillow < 10.1
        font = ImageFont.load_default()
    words, lines, line = title.split(), [], ''
    for word in words:
        trial = (line + ' ' + word).strip()
        if draw.textlength(trial, font=font) > width - 48 and line:
            lines.append(line)
            line = word
        else:
            line = trial
    lines.append(line)
    step = (font.size if hasattr(font, 'size') else 12) + 8
    top = (height - step * len(lines)) // 2
    for i, text in enumerate(lines):
        x = (width - draw.textlength(text, font=font)) // 2
        draw.text((x + 2, top + i * step + 2), text, font=font, fill=(0, 0, 0))
        draw.text((x, top + i * step), text, font=font, fill=(255, 236, 170))
    out = io.BytesIO()
    image.save(out, 'PNG')
    return out.getvalue()


def _png(data: bytes) -> bytes:
    if data[:8] == PNG:
        return data
    import io
    from PIL import Image
    out = io.BytesIO()
    Image.open(io.BytesIO(data)).convert('RGBA').save(out, 'PNG')
    return out.getvalue()


def fetch(log=print) -> int:
    """Download the deal banners' missing art. Returns how many files were added."""
    if os.environ.get('EXVIUS_DEAL_ART_FETCH', '0') != '1':
        return 0
    import data_paths
    folder = data_paths.DEAL_ART_ROOT
    os.makedirs(folder, exist_ok=True)
    added = failed = 0
    # Drawn stand-ins first and without a pause (they cost nothing remote), then the web downloads.
    for name, url, title, size in sorted(_targets(), key=lambda t: bool(t[1])):
        path = os.path.join(folder, name)
        if os.path.isfile(path):
            continue
        try:
            if not url:
                data = render(title, size)
            else:
                req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0 (ExviusOffline deal art)'})
                with urllib.request.urlopen(req, timeout=30) as resp:
                    data = resp.read()
                data = _png(data)
        except urllib.error.HTTPError as exc:
            if exc.code == 404:   # gone from the archive: a titled stand-in, so the banner isn't blank
                data = render(title, size)
            else:
                failed += 1
                if failed <= 5:
                    log(f'DEAL-ART {name}: {exc}')
                continue
        except Exception as exc:  # noqa: BLE001 -- retried on the next start
            failed += 1
            if failed <= 5:
                log(f'DEAL-ART {name}: {exc}')
            continue
        with open(path + '.tmp', 'wb') as fh:
            fh.write(data)
        os.replace(path + '.tmp', path)
        added += 1
        if url:
            time.sleep(0.5)   # be gentle with the Wayback Machine
    if added:
        import ffbe_gacha
        ffbe_gacha._BANNER_ART_INDEX.clear()   # rebuilt on the next lookup, now with these files
    if added or failed:
        log(f'DEAL-ART: {added} image(s) added, {failed} not reachable (retried next start)')
    return added
