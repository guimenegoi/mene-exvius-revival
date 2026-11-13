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
    markers = tuple(recovery_dir / name for name in (
        "pending-restore.json", "restore-request.json", "restore-processing.json"
    ))
    if not any(path.exists() or path.is_symlink() for path in markers):
        return "no_restore_journal"
    if not _engine_stopped():
        raise RuntimeError("Refusing restore: Revival engine may be running")

    # Import only if there is an interrupted transaction or explicit request.
    # Never load restore modules or read saves during an ordinary boot.
    pending = markers[0]
    if pending.exists() or pending.is_symlink():
        from ffbe_save_restore import recover_pending
        if not recover_pending(
            state_dir, recovery_dir, game_stopped=_engine_stopped,
        ):
            raise RuntimeError("Pending journal disappeared during recovery")
        # An interrupted requested restore has been rolled back; consume only
        # its stale processing marker and never re-apply it on this startup.
        if markers[2].exists() or markers[2].is_symlink():
            from ffbe_restore_request import consume_request
            cleanup = consume_request(
                state_dir, recovery_dir, game_stopped=_engine_stopped,
            )
            if cleanup != "interrupted_restore_request_discarded":
                raise RuntimeError("Unexpected restore recovery cleanup state")
        # Never execute a different queued restore in the same boot as a
        # rollback: the player must see the recovered game state first.
        return "interrupted_restore_rolled_back"

    from ffbe_restore_request import consume_request
    return consume_request(state_dir, recovery_dir, game_stopped=_engine_stopped)
