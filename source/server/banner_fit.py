"""Summon detail art letterboxed to the frame the stock app draws it in.

The summon detail screen draws its banner art (requested from `.../static_banner/gacha/sub/<file>`) into
a fixed frame about 3.5 times as wide as it is tall, and stretches whatever image it gets to fill it.
Many of the archived banners are 640x160 or 640x392, so on the iPhone their lettering came out squashed
(operator screenshots, 2026-11-05). The Android build fits them with a hook (source/exvius/summon_art.js);
the iPhone has none, so the server pads each such image to the frame's proportions instead, centred on a
blurred, darkened copy of itself. The list banners (`gacha/main/`) size their rows to the image and are left alone.

Results are cached in ios-cache/banner-fit/. Needs Pillow; without it, or with EXVIUS_IOS_BANNER_FIT=0,
images are served as they are.

The app keeps every banner image it has downloaded and never asks for that file again, so a phone that saw the
squashed art keeps showing it. With EXVIUS_IOS_BANNER_FIT_NAMES=1 (the iPhone server's default) the summon
tables name each detail image `<name>-fit.png`, which the phone has never downloaded; the server maps that
name back to the real file (`real_rel`) and pads it. Raise FIT_SUFFIX's number to make phones fetch again.

Size (2026-11-13, GitHub #6/#7). The padded image used to be made at the art's own resolution. One of the web
downloads (`deal_art`) is a whole news page image thousands of pixels tall; padding it to 3.5:1 asked for a
canvas of 32,192 x 9,205, Pillow refused it (DecompressionBombError), the exception ended the request without
an answer, and because nothing was cached every retry failed the same way: the summon download could never
finish for a player who lists that banner (everyone with EXVIUS_SUMMON_ROTATION=0). Now:
  * nothing sent is larger than MAX_SCALE (about 3) times the frame's size on the phone (`limit`): larger
    art is scaled down first, in bands, so the only large thing in memory is the decoded source;
  * the backdrop is made from the part of the art it shows, never by enlarging the whole art;
  * a list image (`gacha/main/`) larger than that is scaled down too (`cap`);
  * an image too large to decode within READ_LIMIT pixels is answered with a drawn stand-in, and any other
    failure serves the file as it is (`for_phone`): a request is never left without an answer.
"""
from __future__ import annotations

import contextlib
import hashlib
import io
import os
import struct
import threading

FRAME = (640, 183)          # the detail frame's proportions, measured from the phone (848 x 242 points)
BASE_FRAME = (640, 392)     # the base GachaDetailScene's frame (friend-point and other layout-0 summons)
TOLERANCE = 0.06            # images already within 6% of the frame's shape are left alone
STYLE = "blur2"             # part of the cache key: change it when the padding's look changes
POINTS = 848 / 640          # the detail frame is 848 points wide on the phone for FRAME's 640
# Nothing is sent larger than this many pixels a point. The densest iPhone screen has 3; 3.3 so that the
# 1280 x 784 art of about a hundred deal banners, which pads to 2742 x 784, stays exactly as it was (the same
# cached files): only art beyond that is touched.
MAX_SCALE = 3.3
MAIN_LIMIT = (round(848 * MAX_SCALE),) * 2     # a list image: neither side above the frame's largest width
READ_LIMIT = 89_000_000     # pixels: a larger image isn't decoded at all (4 bytes a pixel: about 360 MB)
BIG = 4_000_000             # pixels: images above this are worked on one at a time
_BIG_LOCK = threading.Lock()


class TooLarge(Exception):
    """The image has more pixels than READ_LIMIT: decoding it would need more memory than it is worth."""


def limit(frame: tuple[int, int]) -> tuple[int, int]:
    """The largest padded image ever sent for `frame`: MAX_SCALE pixels a point (2798 x 800 for FRAME)."""
    return round(frame[0] * POINTS * MAX_SCALE), round(frame[1] * POINTS * MAX_SCALE)


def image_size(data: bytes) -> tuple[int, int] | None:
    """(width, height) from the file's header, without decoding it; None when it isn't an image."""
    if data[:8] == b"\x89PNG\r\n\x1a\n" and data[12:16] == b"IHDR" and len(data) >= 24:
        return struct.unpack(">II", data[16:24])
    try:
        from PIL import Image
        with Image.open(io.BytesIO(data)) as image:
            return image.size
    except Exception as exc:  # noqa: BLE001
        if type(exc).__name__ == "DecompressionBombError":      # Pillow's own refusal: far beyond READ_LIMIT
            raise TooLarge(str(exc)) from None
        return None


def _reduced(image, factor: int):
    """`image` as RGBA with each side divided by `factor` (every output pixel the average of a block), made a
    band at a time: no second image as large as the source is ever held."""
    from PIL import Image
    width, height = image.size
    out = Image.new("RGBA", ((width + factor - 1) // factor, (height + factor - 1) // factor))
    rows = factor * max(1, 2_000_000 // (width * factor))           # about 2 million pixels a band
    for top in range(0, height, rows):
        band = image.crop((0, top, width, min(height, top + rows))).convert("RGBA")
        out.paste(band.reduce(factor), (0, top // factor))
    return out


def _near(image, size: tuple[int, int]):
    """`image` as RGBA, reduced by the largest whole factor that still leaves it at least `size`. This is the
    step that needs the decoded source; the caller drops the source before finishing with `_exact`."""
    factor = int(min(image.width / size[0], image.height / size[1]))
    return _reduced(image, factor) if factor >= 2 else image.convert("RGBA")


def _exact(small, size: tuple[int, int]):
    from PIL import Image
    return small if small.size == size else small.resize(size, Image.LANCZOS)


def _backdrop(image, canvas):
    """The padding: the art itself, scaled to cover the frame, blurred and darkened, so the sides read as
    part of the banner instead of empty bars. Only the middle part of the art that ends up on the canvas is
    scaled (`box`); enlarging the whole art and cutting the middle out needed, for a tall narrow image, a
    picture many times the canvas."""
    from PIL import Image, ImageEnhance, ImageFilter
    width, height = image.size
    scale = max(canvas[0] / width, canvas[1] / height)
    part = (min(width, canvas[0] / scale), min(height, canvas[1] / scale))    # of the art, in its own pixels
    left, top = max(0.0, (width - part[0]) / 2), max(0.0, (height - part[1]) / 2)
    box = (left, top, min(width, left + part[0]), min(height, top + part[1]))  # inside the art, whatever rounds
    cover = image.convert("RGB").resize(canvas, Image.BILINEAR, box=box)
    cover = cover.filter(ImageFilter.GaussianBlur(max(4, canvas[1] // 14)))
    cover = ImageEnhance.Brightness(cover).enhance(0.45)
    return cover.convert("RGBA")


def enabled() -> bool:
    return os.environ.get("EXVIUS_IOS_BANNER_FIT", "1") == "1"


FIT_SUFFIX = "-fit1"
# Friend-point and other layout-0 summons (the Standard Summon) open `GachaDetailScene`, whose frame is
# 640x392 (BASE_FRAME), not the paid summons' 3.5:1 frame (`GachaPayDetailScene`). Padding their art to
# 3.5:1 squeezed it into the middle of that frame (operator screenshot, 2026-11-06). They get this name
# instead (one the phone hasn't cached) and are fitted to BASE_FRAME: 640x392 art is served as it is.
PLAIN_SUFFIX = "-full1"


# A list image that isn't a strip. 138 deal and late banners have one file for the list and the detail page:
# Global's 640x392 detail art (the news images are 1280x784), and the summon list draws every row at its image's
# own size, so those banners were giant tiles between the 640x160 strips (operator's screenshots, 2026-11-13).
# The list is sent `x-strip1.png` instead: a 4:1 band cut from that art (`strip`). Global's own strips for these
# banners are lost; a cut strip is made, not Global's, and the operator approves each (banner art brief).
# Only added pictures are cut (news images, Japanese banners: ffbe_gacha._cut_for_list). A list image from the
# game's own banner files is never cut: 39 banners of 2016-17 have a 640x392 list image, and that is their real
# list art (the first version cut those too, and the list showed only the bottom of each).
STRIP_SUFFIX = "-strip1"
STRIP_SHAPE = 2.4           # width / height from which an image counts as a strip (640x240 is 2.67, 640x392 1.63)
STRIP_WIDTH = 1280          # a cut strip is sent no wider than this (640 points at two pixels a point)


def names_enabled() -> bool:
    return enabled() and os.environ.get("EXVIUS_IOS_BANNER_FIT_NAMES", "0") == "1"


def screens_enabled() -> bool:
    """EXVIUS_SUMMON_SCREENS (default on; 0 = off): art is fitted to the screen its summon really opens, a paid
    summon whose art is 640x392 opens the 640x392 screen, and an added list image (a news or Japanese picture)
    that isn't a strip is sent as a cut strip (ffbe_gacha.gacha_groups). Off: as before 2026-11-13."""
    return enabled() and os.environ.get("EXVIUS_SUMMON_SCREENS", "1").strip().lower() not in ("0", "off", "false", "no")


def is_strip_shaped(size) -> bool:
    return bool(size) and size[1] > 0 and size[0] / size[1] >= STRIP_SHAPE


_SHAPES: dict = {}


def file_shape(path: str):
    """(width, height) of an image file, read from its header and remembered by path, size and time; None when
    it can't be read."""
    try:
        stat = os.stat(path)
    except OSError:
        return None
    key = (path, stat.st_size, int(stat.st_mtime))
    if key not in _SHAPES:
        try:
            with open(path, "rb") as fh:
                head = fh.read(32)
            size = image_size(head) if head[:8] == b"\x89PNG\r\n\x1a\n" else None
            if size is None:
                with open(path, "rb") as fh:
                    size = image_size(fh.read())
        except (OSError, TooLarge):
            size = None
        _SHAPES[key] = size
    return _SHAPES[key]


def strip_name(name: str) -> str:
    """The list image name for art that isn't a strip: `x.png` -> `x-strip1.png`."""
    if not name or not names_enabled() or not name.lower().endswith(".png") or STRIP_SUFFIX + "." in name:
        return name
    return name[:-4] + STRIP_SUFFIX + name[-4:]


def is_strip(rel: str) -> bool:
    """True for a requested `.../gacha/main/x-strip1.png`: send the strip cut from `x.png`."""
    return _main(rel) and rel.lower().endswith(STRIP_SUFFIX + ".png")


def fit_name(name: str, pad: bool = True) -> str:
    """The detail image name the summon tables send: `x.png` -> `x-fit1.png` when renaming is on
    (`x-full1.png` for art that must not be padded)."""
    if (not name or not names_enabled() or not name.lower().endswith(".png")
            or FIT_SUFFIX + "." in name or PLAIN_SUFFIX + "." in name):
        return name
    return name[:-4] + (FIT_SUFFIX if pad else PLAIN_SUFFIX) + name[-4:]


def _sub(rel: str) -> bool:
    return "/static_banner/gacha/sub/" in "/" + rel


def is_plain(rel: str) -> bool:
    """True for a requested `.../gacha/sub/x-full1.png`: fit it to BASE_FRAME, not FRAME."""
    return _sub(rel) and rel.lower().endswith(PLAIN_SUFFIX + ".png")


def real_rel(rel: str) -> str:
    """A requested `.../gacha/sub/x-fit1.png` (or `x-full1.png`) back to the file it stands for."""
    for suffix in (FIT_SUFFIX, PLAIN_SUFFIX):
        if _sub(rel) and rel.lower().endswith(suffix + ".png"):
            return rel[:-len(suffix + ".png")] + rel[-4:]
    if is_strip(rel):
        return rel[:-len(STRIP_SUFFIX + ".png")] + rel[-4:]
    return rel


def wants(rel: str) -> bool:
    return enabled() and "/static_banner/gacha/sub/" in "/" + rel and rel.lower().endswith(".png")


def _cache_dir() -> str:
    try:
        import ios_art
        base = ios_art.cache_dir()
    except Exception:  # noqa: BLE001
        base = os.path.join(os.environ.get("FFBE_SERVER_ROOT", "."), "ios-cache")
    path = os.path.join(base, "banner-fit")
    os.makedirs(path, exist_ok=True)
    return path


def _key(data: bytes, *parts) -> str:
    return os.path.join(_cache_dir(), hashlib.sha1(data + "".join(parts).encode()).hexdigest()[:20] + ".png")


def _open(data: bytes, size: tuple[int, int]):
    from PIL import Image
    if size[0] * size[1] > READ_LIMIT:
        raise TooLarge(f"{size[0]}x{size[1]}")
    image = Image.open(io.BytesIO(data))
    image.load()
    return image


def _png(image) -> bytes:
    buf = io.BytesIO()
    image.save(buf, "PNG", optimize=True)
    return buf.getvalue()


def _store(path: str, result: bytes) -> None:
    """Write a cache file whole or not at all (two requests may be making the same one)."""
    tmp = f"{path}.{os.getpid()}.{threading.get_ident()}.tmp"
    with open(tmp, "wb") as fh:
        fh.write(result)
    os.replace(tmp, path)


def fit(data: bytes, frame: tuple[int, int] = FRAME) -> tuple[bytes, str | None]:
    """(bytes, note): the image padded to the frame's shape and no larger than `limit(frame)`, or the input
    unchanged. Raises TooLarge for an image beyond READ_LIMIT; `for_phone` is the caller that never raises."""
    try:
        from PIL import Image  # noqa: F401
    except ImportError:
        return data, None
    size = image_size(data)
    if size is None or size[0] <= 0 or size[1] <= 0:
        return data, None                                # not an image we can read: serve it as it is
    width, height = size
    target = frame[0] / frame[1]
    most = limit(frame)
    shaped = abs(width / height - target) / target <= TOLERANCE
    if shaped and width <= most[0]:
        return data, None
    # Canvas at the image's own resolution: as wide as the image, or as tall, whichever keeps every pixel...
    if shaped:
        canvas = (width, height)
    elif width / height > target:
        canvas = (width, round(width / target))
    else:
        canvas = (round(height * target), height)
    # ...unless that is more than the phone can use: then the art is scaled down to fit `most`.
    scale = min(1.0, most[0] / canvas[0], most[1] / canvas[1])
    capped = scale < 1.0
    # The cache key is the old one whenever the result is what it always was, so files made before stay in use.
    cached = _key(data, STYLE, "" if frame == FRAME else repr(frame), f"max{most}" if capped else "")
    if os.path.isfile(cached):
        with open(cached, "rb") as fh:
            return fh.read(), "letterboxed (cached)"
    with _BIG_LOCK if width * height > BIG else contextlib.nullcontext():
        if os.path.isfile(cached):                       # made by the request that held the lock before us
            with open(cached, "rb") as fh:
                return fh.read(), "letterboxed (cached)"
        try:
            image = _open(data, size)
        except TooLarge:
            raise
        except Exception:  # noqa: BLE001 -- not an image we can read: serve it as it is
            return data, None
        if capped:
            art_size = (max(1, min(most[0], round(width * scale))), max(1, min(most[1], round(height * scale))))
            art = _near(image, art_size)
            del image                                    # the decoded source: by far the largest thing held
            art = _exact(art, art_size)
            canvas = art_size if shaped else most
        else:
            art = image.convert("RGBA")
            del image
        if shaped:
            out = art
        else:
            out = _backdrop(art, canvas)
            out.paste(art, ((canvas[0] - art.width) // 2, (canvas[1] - art.height) // 2), art)
        result = _png(out)
        _store(cached, result)
    what = "scaled" if shaped else "letterboxed"
    return result, f"{what} {width}x{height} -> {canvas[0]}x{canvas[1]}"


def cap(data: bytes, most: tuple[int, int] = MAIN_LIMIT) -> tuple[bytes, str | None]:
    """(bytes, note): a list image scaled down to fit inside `most` (its shape kept), or the input unchanged
    when it already fits. Raises TooLarge like `fit`."""
    try:
        from PIL import Image  # noqa: F401
    except ImportError:
        return data, None
    size = image_size(data)
    if size is None or size[0] <= 0 or size[1] <= 0 or (size[0] <= most[0] and size[1] <= most[1]):
        return data, None
    width, height = size
    scale = min(most[0] / width, most[1] / height)
    new = (max(1, round(width * scale)), max(1, round(height * scale)))
    cached = _key(data, "cap", repr(most))
    if os.path.isfile(cached):
        with open(cached, "rb") as fh:
            return fh.read(), "scaled down (cached)"
    with _BIG_LOCK if width * height > BIG else contextlib.nullcontext():
        if os.path.isfile(cached):
            with open(cached, "rb") as fh:
                return fh.read(), "scaled down (cached)"
        try:
            image = _open(data, size)
        except TooLarge:
            raise
        except Exception:  # noqa: BLE001
            return data, None
        small = _near(image, new)
        del image
        result = _png(_exact(small, new))
        _store(cached, result)
    return result, f"scaled down {width}x{height} -> {new[0]}x{new[1]}"


def _main(rel: str) -> bool:
    return "/static_banner/gacha/main/" in "/" + rel


def strip(data: bytes) -> tuple[bytes, str | None]:
    """(bytes, note): a 4:1 strip cut from art that isn't one: the full-width band with the most detail in it
    (edges per row, summed over the band), no wider than STRIP_WIDTH. Art that is already a strip is returned
    as it is. Raises TooLarge like `fit`."""
    try:
        from PIL import Image, ImageFilter
    except ImportError:
        return data, None
    size = image_size(data)
    if size is None or size[0] <= 0 or size[1] <= 0 or is_strip_shaped(size):
        return data, None
    width, height = size
    # "strip2": the cut keeps the art's transparency (2026-11-13). The first version flattened it, so art with
    # clear margins (the Japanese notice banners) got white bars at both ends of its strip.
    cached = _key(data, "strip2", STRIP_SUFFIX, repr(STRIP_WIDTH))
    if os.path.isfile(cached):
        with open(cached, "rb") as fh:
            return fh.read(), "strip cut from the art (cached)"
    with _BIG_LOCK if width * height > BIG else contextlib.nullcontext():
        image = _open(data, size).convert("RGBA")
        if width > STRIP_WIDTH:                      # work at the size that is sent
            image = _exact(_near(image, (STRIP_WIDTH, max(1, round(height * STRIP_WIDTH / width)))),
                           (STRIP_WIDTH, max(1, round(height * STRIP_WIDTH / width))))
            width, height = image.size
        band = max(1, min(height, round(width / 4)))
        rows = list(image.convert("L").filter(ImageFilter.FIND_EDGES).resize((1, height), Image.BOX).tobytes())
        best, top, run = -1, 0, sum(rows[:band])
        for y in range(0, height - band + 1):
            if y:
                run += rows[y + band - 1] - rows[y - 1]
            if run > best:
                best, top = run, y
        cut = image.crop((0, top, width, top + band))
        if cut.getextrema()[3][0] == 255:            # nothing transparent in it: no alpha channel to carry
            cut = cut.convert("RGB")
        result = _png(cut)
        _store(cached, result)
    return result, f"strip cut from the art (rows {top}-{top + band} of {height})"


def for_phone(rel: str, data: bytes, plain: bool = False, cut: bool = False) -> tuple[bytes, str | None]:
    """(bytes, note) for a summon image about to be sent (`rel` is the real file's path): detail art fitted
    to its frame, list art scaled down when it is oversized, anything else untouched. Never raises: an image
    too large to decode is answered with a drawn stand-in, and any other failure serves the file as it is."""
    if not enabled() or not rel.lower().endswith(".png") or not (_sub(rel) or _main(rel)):
        return data, None
    frame = BASE_FRAME if plain else FRAME
    try:
        if _sub(rel):
            return fit(data, frame)
        if cut:                                       # asked for as `x-strip1.png` (`cut`: is_strip of the request)
            made, note = strip(data)
            if note:
                print(f"BANNER-FIT {rel}: list {note}", flush=True)
            return made, note
        return cap(data)
    except TooLarge as exc:
        why = f"image too large to fit: {exc}"
        print(f"BANNER-FIT {rel}: {why}; a drawn stand-in is sent", flush=True)
        try:
            import summon_art
            drawn = summon_art.fallback(rel, why=why)
            if drawn:
                picture, how = drawn
                if _sub(rel):
                    picture = fit(picture, frame)[0]
                return picture, how
        except Exception as inner:  # noqa: BLE001
            print(f"BANNER-FIT {rel}: no stand-in either ({inner!r}); the file is sent as it is", flush=True)
        return data, "not fitted (" + why + ")"
    except Exception as exc:  # noqa: BLE001 -- whatever went wrong, the phone still gets the file
        print(f"BANNER-FIT {rel}: {exc!r}; the file is sent as it is", flush=True)
        return data, f"not fitted ({type(exc).__name__})"
