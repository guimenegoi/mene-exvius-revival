"""Guard an interrupted save restoration before importing the Revival engine.

Embedded as ffbe_restore_startup.py ONLY in an opt-in experimental APK.
This is not an interactive restore controller and provides no HTTP endpoint.
"""
from __future__ import annotations

import errno
import socket
import sys
from pathlib import Path

LOOPBACK_PORT = 18080


def _engine_stopped() -> bool:
    """Fail closed unless no imported Revival engine and no bound HTTP server.

    Only call in the dedicated bootstrap worker before serve is imported.
    A host process may contain unrelated threads, so this is a prerequisite,
    NOT a general-purpose proof that it is safe to restore while running.
    """
    if "serve" in sys.modules or "capture_server" in sys.modules:
        return False
    try:
        with socket.create_connection(("127.0.0.1", LOOPBACK_PORT), timeout=.25):
            return False
    except ConnectionRefusedError:
        return True
    except OSError as exc:
        # E.g. network unavailable or bad socket state is not positive proof.
        if exc.errno == errno.ECONNREFUSED:
            return True
        return False


def recover_before_engine(app_files: Path) -> str:
    """Recover an interrupted transaction before any serve/capture_server import.

    No recovery directory or pending marker: no save read or write. Recovery
    is only possible inside a process that has not started the engine yet.
    """
    files = Path(app_files)
    state_dir = files / "exvius/server-root/state"
    recovery_dir = files / "exvius/server-root/restore-private"
    if recovery_dir.is_symlink():
        raise RuntimeError("Restore recovery path is a symlink")
    if not recovery_dir.exists():
        return "no_restore_journal"
    if not recovery_dir.is_dir():
        raise RuntimeError("Restore recovery path is not a directory")
    pending = recovery_dir / "pending-restore.json"
    if not pending.exists() and not pending.is_symlink():
        return "no_restore_journal"
    if not _engine_stopped():
        raise RuntimeError("Refusing pending recovery: Revival engine may be running")

    # Import only when a pending journal exists, to avoid any save-related
    # dependencies or initialization cost in the common startup path.
    from ffbe_save_restore import recover_pending
    if recover_pending(
        state_dir, recovery_dir, game_stopped=_engine_stopped,
    ):
        return "interrupted_restore_rolled_back"
    raise RuntimeError("Pending restore unexpectedly disappeared")
