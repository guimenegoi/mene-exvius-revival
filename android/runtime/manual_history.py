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
    if not os.environ.get("FFBE_SAVE_BACKUP_CONFIG"):
        return stop
    import config_sync
    from save_backup import _configuration

    def credentials():
        current = _configuration()
        if current is None:
            return None
        endpoint, device, token, ca, _token_file = current
        return {"endpoint": endpoint, "device": device, "token": token}, ca

    global _sync
    sync = config_sync.ConfigSync(Path(files) / "exvius/settings", credentials)
    _sync = sync

    def poll():
        while not stop.is_set():
            sync.poll()  # stores staged revision; never changes the running engine
            stop.wait(config_sync.INTERVAL)

    threading.Thread(target=poll, name="FFBE-HistoricalSettings", daemon=True).start()
    return stop
