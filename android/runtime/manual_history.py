"""Offline-first Android replay settings, before importing the Revival engine.

The optional private configuration store is NOT a game save. Manual history
acts as a read-only timeline overlay; the original replay anchor is untouched.
"""
from __future__ import annotations

import os
import threading
from pathlib import Path

_sync = None


def status() -> dict:
    """Local-only, non-secret diagnostic for the current historical period."""
    index = int(os.environ.get("EXVIUS_REPLAY_MANUAL_WEEK", "0"))
    from datetime import date, timedelta
    start = date.fromisoformat(os.environ.get("EXVIUS_REPLAY_START", "2016-06-30"))
    period = start + timedelta(weeks=index)
    state = _sync.status() if _sync is not None else {"state": "not_paired", "has_pending": False}
    return {**state, "historical_from": period.isoformat(),
            "historical_to": (period + timedelta(days=6)).isoformat(),
            "mode": os.environ.get("EXVIUS_REPLAY_MODE", "manual")}


def configure(files: Path) -> dict:
    """Select the 2016 launch by default; apply only validated local overrides."""
    import config_model
    files = Path(files)
    settings = files / "exvius/settings"
    replay = files / "exvius/server-root/state/replay.json"
    # This test candidate intentionally defaults to the requested launch.
    os.environ["EXVIUS_REPLAY"] = "1"
    os.environ["EXVIUS_SUMMON_ROTATION"] = "1"
    os.environ["EXVIUS_REPLAY_MODE"] = "manual"
    os.environ["EXVIUS_REPLAY_START"] = "2016-06-30"
    os.environ["EXVIUS_REPLAY_MANUAL_WEEK"] = "0"
    outcome = config_model.apply_on_boot(settings, replay)
    if os.environ["EXVIUS_REPLAY_MODE"] == "automatic":
        # Returning to automatic must restore the original default start,
        # not silently retain this APK's manual-launch override.
        try:
            active = config_model.read_private(settings / "server-config.json")
            explicit_start = active is not None and "EXVIUS_REPLAY_START" in active["settings"]
        except (OSError, ValueError, TypeError):
            explicit_start = False
        if not explicit_start:
            os.environ["EXVIUS_REPLAY_START"] = "2016-12-16"
    else:
        # No future random Vortex encounters/events or multi-week news carryover.
        os.environ["EXVIUS_VORTEX_EXTRA"] = "0"
        os.environ["EXVIUS_REPLAY_NOTICE_WEEKS"] = "1"
    print("FFBE-HISTORY: " + os.environ["EXVIUS_REPLAY_MODE"]
          + " start=" + os.environ["EXVIUS_REPLAY_START"]
          + " week=" + os.environ["EXVIUS_REPLAY_MANUAL_WEEK"]
          + " config=" + outcome["reason"], flush=True)
    return outcome


def start_sync(files: Path) -> threading.Event:
    """Poll optional paired settings asynchronously; never block engine startup."""
    stop = threading.Event()
    import json
    directory = Path(files) / "exvius/settings"
    enrolled = directory / "receiver-config.json"
    if not enrolled.is_file() or enrolled.is_symlink():
        return stop
    import config_sync
    from ffbe_history_pairing import ENDPOINT

    def credentials():
        if enrolled.is_symlink() or not enrolled.is_file() or enrolled.stat().st_mode & 0o077:
            raise ValueError("Settings credentials are not private")
        if enrolled.stat().st_size > 4096:
            raise ValueError("Oversized settings credentials")
        config = json.loads(enrolled.read_text("utf-8"))
        if not isinstance(config,dict) or set(config) != {"enabled", "url", "device", "token_file", "ca_file"}:
            raise ValueError("Invalid settings credentials")
        if config["enabled"] is not True or config["url"] != ENDPOINT or config["device"] != "samsung-android":
            raise ValueError("Untrusted settings receiver")
        token_file, ca = Path(config["token_file"]), Path(config["ca_file"])
        if (token_file.parent != directory or ca.parent != directory
                or any(p.is_symlink() or not p.is_file() for p in (token_file, ca))
                or token_file.stat().st_mode & 0o077 or ca.stat().st_mode & 0o077):
            raise ValueError("Unsafe settings credential files")
        token = token_file.read_text("utf-8").strip()
        if not 32 <= len(token) <= 256:
            raise ValueError("Invalid settings credential token")
        return {"endpoint": ENDPOINT, "device": "samsung-android", "token": token}, ca

    global _sync
    sync = config_sync.ConfigSync(Path(files) / "exvius/settings", credentials)
    _sync = sync

    def poll():
        while not stop.is_set():
            sync.poll()  # stores staged revision; never changes the running engine
            stop.wait(config_sync.INTERVAL)

    threading.Thread(target=poll, name="FFBE-HistoricalSettings", daemon=True).start()
    return stop
