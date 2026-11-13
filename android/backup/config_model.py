"""Strict, versioned FFBE server configuration shared by Android and LXC.

This document is NEVER a save. No arbitrary environment keys, paths, commands,
or unbounded values are accepted from the network.
"""
from __future__ import annotations
import hashlib
import json
import os
import re
import stat
import tempfile
from datetime import date
from pathlib import Path

SCHEMA = 1
MAX_BYTES = 4096
ZERO_REVISION = "0"
BOOLEANS = frozenset({
    "EXVIUS_REPLAY", "EXVIUS_REPLAY_FULL_RUNS",
    "EXVIUS_REPLAY_NOTICES", "EXVIUS_REPLAY_MARQUEE",
    "EXVIUS_EVENT_ARCHIVE", "EXVIUS_SUMMON_ARCHIVE",
    "EXVIUS_QUEST_TRUST",
})
RANGES = {
    "EXVIUS_LAPIS_MULTIPLIER": (1, 10),
    "EXVIUS_DAILY_QUEST_LAPIS": (0, 5000),
    "EXVIUS_QUEST_TRUST_CHANCE": (0, 100),
    "EXVIUS_QUEST_TRUST_POINTS": (0, 100),
    "EXVIUS_QUEST_TRUST_BIG_CHANCE": (0, 100),
    "EXVIUS_QUEST_TRUST_BIG_POINTS": (0, 1000),
    "EXVIUS_REPLAY_NOTICE_WEEKS": (1, 52),
}
SPECIAL = frozenset({"EXVIUS_REPLAY_START", "EXVIUS_REPLAY_PACE", "MARQUEE_FLAG"})
ALLOWED = BOOLEANS | set(RANGES) | SPECIAL
DEFAULT_START = "2016-12-16"
DEFAULT_PACE = "3,2@2020-08-20"
PACE_PATTERN = re.compile(r"\d{1,2}(?:,\d{1,2}@\d{4}-\d{2}-\d{2}){0,5}\Z")


def _day(value: str) -> date:
    if not isinstance(value, str) or len(value) != 10:
        raise ValueError("Invalid historical date")
    try:
        day = date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError("Invalid historical date") from exc
    if not date(2016, 6, 30) <= day <= date(2024, 10, 30):
        raise ValueError("Historical date outside released Global FFBE period")
    return day


def validate_document(value: dict) -> dict:
    """Reject unknown fields and types: accepts no credentials or save data."""
    if not isinstance(value, dict) or set(value) != {"schema", "settings"}:
        raise ValueError("Invalid configuration envelope")
    if type(value["schema"]) is not int or value["schema"] != SCHEMA:
        raise ValueError("Unsupported configuration schema")
    incoming = value["settings"]
    if not isinstance(incoming, dict) or len(incoming) > len(ALLOWED):
        raise ValueError("Invalid configuration settings")
    settings = {}
    for key, raw in incoming.items():
        if not isinstance(key, str) or key not in ALLOWED:
            raise ValueError("Unknown or unsafe configuration setting")
        if key in BOOLEANS:
            if type(raw) is not bool:
                raise ValueError("Setting must be boolean: " + key)
        elif key in RANGES:
            low, high = RANGES[key]
            if type(raw) is not int or not low <= raw <= high:
                raise ValueError("Setting outside allowed range: " + key)
        elif key == "EXVIUS_REPLAY_START":
            _day(raw)
        elif key == "EXVIUS_REPLAY_PACE":
            if not isinstance(raw, str) or not PACE_PATTERN.fullmatch(raw):
                raise ValueError("Invalid replay pace")
            for index, part in enumerate(raw.split(",")):
                pace, sep, day = part.partition("@")
                if not 1 <= int(pace) <= 8 or (index and not sep):
                    raise ValueError("Invalid replay pace segment")
                if day:
                    _day(day)
        elif key == "MARQUEE_FLAG":
            if raw not in ("0", "1", "flag") or not isinstance(raw, str):
                raise ValueError("Invalid MARQUEE_FLAG")
        settings[key] = raw
    normalized = {"schema": SCHEMA, "settings": dict(sorted(settings.items()))}
    if len(encode(normalized)) > MAX_BYTES:
        raise ValueError("Configuration exceeds maximum size")
    return normalized


def encode(value: dict) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":"),
                       ensure_ascii=True) + "\n").encode("ascii")


def revision(document: dict) -> str:
    normalized = validate_document(document)
    return hashlib.sha256(encode(normalized)).hexdigest()


def parse(raw: bytes) -> dict:
    if not isinstance(raw, bytes) or len(raw) > MAX_BYTES:
        raise ValueError("Oversized configuration")
    try:
        document = json.loads(raw)
    except (UnicodeDecodeError, ValueError) as exc:
        raise ValueError("Malformed configuration") from exc
    return validate_document(document)


def read_private(path: Path) -> dict | None:
    path = Path(path)
    if path.is_symlink():
        raise ValueError("Configuration symlink refused")
    if not path.exists():
        return None
    stats = path.stat()
    if (not stat.S_ISREG(stats.st_mode) or stats.st_nlink != 1
            or stats.st_size > MAX_BYTES or stats.st_mode & 0o077):
        raise ValueError("Unsafe configuration file")
    return parse(path.read_bytes())


def write_private(path: Path, document: dict) -> None:
    path = Path(path)
    document = validate_document(document)
    if path.is_symlink():
        raise ValueError("Configuration symlink refused")
    parent = path.parent
    if parent.is_symlink():
        raise ValueError("Configuration directory symlink refused")
    parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    if parent.is_symlink():
        raise ValueError("Configuration directory symlink refused")
    os.chmod(parent, 0o700)
    fd, name = tempfile.mkstemp(prefix=".config-", dir=parent)
    try:
        with os.fdopen(fd, "wb") as output:
            os.fchmod(output.fileno(), 0o600)
            output.write(encode(document))
            output.flush()
            os.fsync(output.fileno())
        os.replace(name, path)
    finally:
        Path(name).unlink(missing_ok=True)


def compatible_with_save(document: dict, previous: dict | None,
                         replay_path: Path) -> tuple[bool, str]:
    """Never silently re-anchor an existing historical replay save."""
    settings = validate_document(document)["settings"]
    if replay_path.is_symlink():
        return False, "unsafe replay anchor"
    if not replay_path.is_file():
        return True, "no existing replay anchor"
    if replay_path.stat().st_size > 8192:
        return False, "invalid replay anchor size"
    try:
        anchor = json.loads(replay_path.read_text("utf-8"))
    except (OSError, ValueError, UnicodeError):
        return False, "unreadable replay anchor"
    if not isinstance(anchor, dict) or not isinstance(anchor.get("anchor_week"), int):
        return False, "invalid replay anchor"
    original_start = anchor.get("start")
    if ("EXVIUS_REPLAY_START" in settings
            and settings["EXVIUS_REPLAY_START"] != original_start):
        return False, "replay start change requires explicit migration"
    original = (previous or {"settings": {}}).get("settings", {})
    current_pace = original.get("EXVIUS_REPLAY_PACE", DEFAULT_PACE)
    if ("EXVIUS_REPLAY_PACE" in settings
            and settings["EXVIUS_REPLAY_PACE"] != current_pace):
        return False, "replay pace change requires explicit migration"
    return True, "historical anchor compatible"


def environment(document: dict) -> dict[str, str]:
    settings = validate_document(document)["settings"]
    return {
        key: ("1" if value else "0") if isinstance(value, bool) else str(value)
        for key, value in settings.items()
    }


def apply_on_boot(private: Path, replay_path: Path,
                  environ: dict | None = None) -> dict:
    """Promote validated staged config, otherwise retain old/local defaults.

    Never touch campaign.json or replay.json, and do not fetch remote data here.
    The caller must invoke this BEFORE importing serve/capture_server.
    """
    private = Path(private)
    active, pending = private / "server-config.json", private / "staged-config.json"
    destination = os.environ if environ is None else environ
    status = {"revision": ZERO_REVISION, "staged": False,
              "applied": False, "reason": "defaults"}
    try:
        previous = read_private(active)
    except (OSError, ValueError):
        previous = None
        status["reason"] = "invalid active config ignored"
    if pending.exists() or pending.is_symlink():
        status["staged"] = True
        try:
            proposal = read_private(pending)
            allowed, reason = compatible_with_save(proposal, previous, replay_path)
            if allowed:
                write_private(active, proposal)
                pending.unlink()
                previous = proposal
                status["staged"] = False
            else:
                status["reason"] = reason
        except (OSError, ValueError, TypeError) as exc:
            status["reason"] = "staged config rejected: " + type(exc).__name__
    if previous is not None:
        allowed, reason = compatible_with_save(previous, None, replay_path)
        # A previously applied pace setting must remain active; it was
        # validated on the first installation. A future change remains staged.
        if not allowed and "pace change" not in reason:
            status["reason"] = reason
            return status
        destination.update(environment(previous))
        status["applied"] = True
        status["revision"] = revision(previous)
    return status
