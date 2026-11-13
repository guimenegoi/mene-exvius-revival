#!/usr/bin/env python3
"""Edit versioned FFBE configuration inside the private LXC ZFS volume.

This local admin tool does not need or disclose a Bearer token.
No save files are opened or modified.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import config_model
import config_service


def parse_setting(key: str, value: str):
    if key not in config_model.ALLOWED:
        raise ValueError("Unsupported setting: " + key)
    if key in config_model.BOOLEANS:
        if value not in ("true", "false"):
            raise ValueError("Use true or false")
        return value == "true"
    if key in config_model.RANGES:
        if not value.isascii() or not value.isdecimal():
            raise ValueError("Use an integer")
        return int(value)
    return value


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--store", default="/var/lib/ffbe-save-backups", type=Path)
    parser.add_argument("--device", required=True, help="device ID, e.g. samsung-android")
    sub = parser.add_subparsers(dest="operation", required=True)
    sub.add_parser("show")
    set_p = sub.add_parser("set")
    set_p.add_argument("key")
    set_p.add_argument("value")
    del_p = sub.add_parser("unset")
    del_p.add_argument("key")
    args = parser.parse_args(argv)
    state = config_service.get(args.store, args.device)
    if args.operation == "show":
        print(json.dumps(state or {"revision": "0", "document": None}, indent=2))
        return 0
    previous = state["revision"] if state else "0"
    doc = (state["document"] if state else {"schema": 1, "settings": {}})
    settings = doc["settings"].copy()
    if args.operation == "set":
        settings[args.key] = parse_setting(args.key, args.value)
    else:
        if args.key not in config_model.ALLOWED:
            parser.error("Unsupported setting")
        settings.pop(args.key, None)
    candidate = config_model.validate_document({"schema": 1, "settings": settings})
    code, result = config_service.put(args.store, args.device,
                                      config_model.encode(candidate), previous)
    if code not in (200, 201):
        print(json.dumps({"error": result.get("error"), "status": code}))
        return 2
    print(json.dumps({"status": "updated", "revision": result["revision"],
                      "settings": candidate["settings"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
