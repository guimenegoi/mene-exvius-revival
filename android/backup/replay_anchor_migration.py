"""Read-only FFBE replay anchor migration planning for experimental Android.

Never modifies a save, settings, device or time. The actual commit requires
an explicitly confirmed cold-start transaction with a recovery journal.
"""
from __future__ import annotations

import hashlib
import hmac
import io
import json
import zipfile
from datetime import date
from pathlib import Path

try:
    import ffbe_backup_transport as backup
except ModuleNotFoundError as exc:
    if exc.name != "ffbe_backup_transport":
        raise
    import lxc_backup as backup

import config_model

OLD_START = "2016-12-16"
CANDIDATE_START = "2016-11-11"
CONFIRMATION_PREFIX = "MIGRAR HISTORICO "


def _replay_record(raw: bytes) -> dict:
    record = json.loads(raw)
    if not isinstance(record, dict) or set(record) != {"start", "anchor_week"}:
        raise ValueError("Unexpected historical anchor schema")
    if record["start"] != OLD_START:
        raise ValueError("Replay is not anchored at the verified 2016-12-16 baseline")
    if type(record["anchor_week"]) is not int or not 0 <= record["anchor_week"] <= 100000:
        raise ValueError("Invalid replay anchor week")
    return record


def _settings_pair(config_dir: Path) -> tuple[dict | None, dict]:
    """Require a real, private, validated staged config before migration."""
    config_dir = Path(config_dir)
    if config_dir.is_symlink() or not config_dir.is_dir():
        raise ValueError("Unsafe or absent private-config directory")
    active = config_model.read_private(config_dir / "server-config.json")
    staged = config_model.read_private(config_dir / "staged-config.json")
    if staged is None:
        raise ValueError("Historical config has not been received by the device")
    proposed = staged["settings"]
    previous = (active or {"settings": {}})["settings"]
    if proposed.get("EXVIUS_REPLAY_START") != CANDIDATE_START:
        raise ValueError("Pending config must explicitly request 2016-11-11")
    if previous.get("EXVIUS_REPLAY_START", config_model.DEFAULT_START) != OLD_START:
        raise ValueError("Active historical setting is not the existing anchor")
    if (proposed.get("EXVIUS_REPLAY_PACE", config_model.DEFAULT_PACE) !=
            previous.get("EXVIUS_REPLAY_PACE", config_model.DEFAULT_PACE)):
        raise ValueError("Replay pace must remain unchanged for anchor migration")
    if (set(proposed) - {"EXVIUS_REPLAY_START"} !=
            set(previous) - {"EXVIUS_REPLAY_START"}):
        raise ValueError("Migration config must not alter other settings")
    for name in set(proposed) - {"EXVIUS_REPLAY_START"}:
        if proposed[name] != previous[name]:
            raise ValueError("Migration config must not alter seasonal or other settings")
    return active, staged


def _archive_with_replay(source_zip: bytes, replay_bytes: bytes) -> bytes:
    names = backup.validate(source_zip)
    if "replay.json" not in names:
        raise ValueError("Cannot migrate a replay anchor that does not exist")
    with zipfile.ZipFile(io.BytesIO(source_zip)) as source:
        files = {name: source.read("state/" + name) for name in names}
    files["replay.json"] = replay_bytes
    manifest = {"schema": backup.SCHEMA, "files": {
        name: hashlib.sha256(raw).hexdigest() for name, raw in sorted(files.items())
    }}
    memory = io.BytesIO()
    with zipfile.ZipFile(memory, "w", compression=zipfile.ZIP_STORED) as z:
        z.writestr("manifest.json", json.dumps(manifest, sort_keys=True).encode("ascii"))
        for name, raw in sorted(files.items()):
            z.writestr("state/" + name, raw)
    data = memory.getvalue()
    if len(data) > backup.MAX_PAYLOAD:
        raise ValueError("Migrated save too large")
    backup.validate(data)
    return data


def preview_migration(state_dir: Path, config_dir: Path) -> dict:
    """Return migration plan and a *synthetic candidate snapshot*, never writing.

    The snapshot is for tests or an OFFLINE, explicitly authorized cold-start
    workflow only. It MUST NOT be sent through the generic restore queue,
    which lacks the staged-config cross-check at consumption time.
    """
    _active, staged = _settings_pair(config_dir)
    before = backup.snapshot(Path(state_dir))
    with zipfile.ZipFile(io.BytesIO(before)) as z:
        raw_replay = z.read("state/replay.json")
        campaign = z.read("state/campaign.json")
    current = _replay_record(raw_replay)
    changed = dict(current, start=CANDIDATE_START)
    replay_raw = (json.dumps(changed, sort_keys=True, separators=(",", ":")) + "\n").encode("ascii")
    candidate = _archive_with_replay(before, replay_raw)
    with zipfile.ZipFile(io.BytesIO(candidate)) as z:
        if not hmac.compare_digest(hashlib.sha256(campaign).digest(),
                                   hashlib.sha256(z.read("state/campaign.json")).digest()):
            raise RuntimeError("Campaign changed during migration preview")
    sha_before = hashlib.sha256(before).hexdigest()
    sha_candidate = hashlib.sha256(candidate).hexdigest()
    return {
        "old_start": OLD_START,
        "new_start": CANDIDATE_START,
        "anchor_week": current["anchor_week"],
        "source_archive_sha256": sha_before,
        "candidate_archive_sha256": sha_candidate,
        "campaign_sha256": hashlib.sha256(campaign).hexdigest(),
        "staged_settings_revision": config_model.revision(staged),
        "confirmation": CONFIRMATION_PREFIX + CANDIDATE_START + " " + sha_candidate[:12],
        "candidate_archive": candidate,
    }
