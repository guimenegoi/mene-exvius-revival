#!/usr/bin/env python3
"""Read-only integration proof for FFBE Global 2016 and real-calendar holidays.

This runs exclusively with a temporary FFBE_DATA and never mutates the Android
save, server configs, or the user's historical replay anchor.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from datetime import datetime
from pathlib import Path
from unittest.mock import patch


REPLAY_ANCHOR = "2016-12-16"
CANDIDATE = "2016-11-11"
NOW = datetime(2026, 11, 13, 12)
CHRISTMAS = datetime(2026, 12, 23, 12)
HALLOWEEN = datetime(2027, 10, 29, 12)


def run(mst: Path, text: Path) -> dict:
    repo = Path(__file__).resolve().parents[2]
    if not (mst / "F_MISSION_MST.ndjson").is_file():
        raise ValueError("Decoded mission corpus is required for the Vortex integration test")
    if not (text / "F_TEXT_UNITS_NAME.ndjson").is_file():
        raise ValueError("Decoded text corpus is required")
    with tempfile.TemporaryDirectory(prefix="ffbe-2016-holiday-proof-") as sandbox:
        settings = {
            "FFBE_DATA": sandbox,
            "MST_DIR": str(mst),
            "TEXT_DIR": str(text),
            "GACHA_ONLY": "all",
            "GACHA_CAMPAIGN": "all",
            "GACHA_STANDARD": "1",
            "GACHA_CATALOGUE": "1",
            "EXVIUS_REPLAY": "1",
            "EXVIUS_SUMMON_ROTATION": "1",
            "EXVIUS_VORTEX_ROTATION": "1",
            "EXVIUS_REPLAY_FULL_RUNS": "1",
            "EXVIUS_EVENT_ARCHIVE": "1",
            "EXVIUS_SUMMON_ARCHIVE": "1",
            "EXVIUS_ROTATION_HOLIDAYS": "1",
            "EXVIUS_REPLAY_PACE": "3,2@2020-08-20",
            "SEASON": "off",  # Do not change the independent authored season
        }
        with patch.dict(os.environ, settings):
            sys.path.insert(0, str(repo / "source/server"))
            sys.path.insert(0, str(repo / "android/backup"))
            import gacha_rotation
            import replay
            import event_archive
            import config_model
            from ffbe_gacha import all_banners

            catalog = all_banners()
            if len(catalog) < 1000:
                raise AssertionError("Incomplete Global banner catalogue")
            anchor = gacha_rotation.week(NOW)[0]
            output = {}
            for starting in (REPLAY_ANCHOR, CANDIDATE):
                os.environ["EXVIUS_REPLAY_START"] = starting
                with patch.object(replay, "anchor_week", return_value=anchor):
                    first = gacha_rotation.plan(catalog, NOW)
                    week_events = event_archive.weekly_events(now=NOW)
                    if first["replay"]["from"].isoformat() != starting:
                        raise AssertionError("Unexpected replay start")
                    matches = {
                        name: [row["area"] for row in week_events if row.get("name") == name]
                        for name in ("Grand Gaia Chronicles", "Trial of the Creator")
                    }
                    if starting == CANDIDATE and not all(matches.values()):
                        raise AssertionError("Confirmed 2016 Brave Frontier event missing")
                    if first["holiday"] is not None:
                        raise AssertionError("Holiday banners incorrectly opened in non-holiday week")
                    holidays = {}
                    for label, day in (("Christmas", CHRISTMAS), ("Halloween", HALLOWEEN)):
                        plan = gacha_rotation.plan(catalog, day)
                        listed = event_archive.weekly_events(now=day)
                        if plan["holiday"] != label:
                            raise AssertionError("Seasonal banner scheduling lost: " + label)
                        selected = [
                            key for key, _ids in plan["sets"]
                            if key in plan["holiday_sets"].get(label, [])
                        ]
                        if not selected:
                            raise AssertionError("Holiday event has no selectable banners: " + label)
                        areas = {
                            str(row["area"]) for row in listed
                            if str(row.get("area")) in event_archive.HOLIDAY_EVENTS[label]
                        }
                        holidays[label] = {
                            "selected_banner_sets": len(selected),
                            "banner_dates": sorted(selected),
                            "vortex_areas": sorted(areas),
                        }
                    output[starting] = {
                        "historical_window": {
                            "start": first["replay"]["from"].isoformat(),
                            "end_exclusive": first["replay"]["to"].isoformat()
                        },
                        "brave_frontier_vortex_areas": matches,
                        "seasonal": holidays,
                    }

            # Changing an already initialized replay is rejected on-device.
            # This test deliberately creates only a SYNTHETIC replay file.
            mock_replay = Path(sandbox) / "test-existing-replay.json"
            mock_replay.write_text(json.dumps({
                "anchor_week": anchor, "start": REPLAY_ANCHOR
            }))
            allowed, reason = config_model.compatible_with_save(
                {"schema": 1, "settings": {"EXVIUS_REPLAY_START": CANDIDATE}},
                None, mock_replay
            )
            if allowed or "explicit migration" not in reason:
                raise AssertionError("Historical anchor guard was bypassed")
            # Seasonal event areas must not disappear after the earlier start.
            for holiday in ("Halloween", "Christmas"):
                baseline = output[REPLAY_ANCHOR]["seasonal"][holiday]
                candidate = output[CANDIDATE]["seasonal"][holiday]
                if baseline["vortex_areas"] != candidate["vortex_areas"]:
                    raise AssertionError("Seasonal Vortex content changed: " + holiday)
                if baseline["banner_dates"] != candidate["banner_dates"]:
                    raise AssertionError("Seasonal banner year or dates changed: " + holiday)
            if not output[CANDIDATE]["seasonal"]["Halloween"]["vortex_areas"]:
                raise AssertionError("Halloween Vortex events are missing")
            return {
                "result": "PASS",
                "read_only": True,
                "banner_catalogue": len(catalog),
                "simulated_replay_anchor_week": anchor,
                "candidate": CANDIDATE,
                "anchor_migration_required": True,
                "baseline": output[REPLAY_ANCHOR],
                "candidate_result": output[CANDIDATE],
            }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mst-dir", type=Path, required=True)
    parser.add_argument("--text-dir", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(run(args.mst_dir, args.text_dir), ensure_ascii=False,
                     indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
