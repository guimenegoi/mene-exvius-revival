"""The function table's version, told to the phone before the title screen (2026-11-13).

Why. Convert to Prism and Convert to Fragments were empty after every fresh start of the game. The game keeps a
list of its tables and rebuilds it when the title screen opens (GL libgame 0x1d3c17c, from
`TitleScene::initConnect`). One table, `F_SACRIFICE_MST` (what a unit converts to), is only put in the list if
the function table (`F_FUNCTION_MST`) is already loaded and holds `FUNCTION_SP_CLASSUP` (0x1d3d154). A table
that isn't in the list is never downloaded and can't be loaded. With this server the function table was first
loaded after the tap, when the Initialize reply's version list (`c1qYg84Q`) arrived: after the rebuild. The lists
only worked once the title had been opened a second time in the same run (Menu, return to title).

What the game does before the title. `PostStartupScene` sends `GetBackgroundDownloadInfoRequest`, and when the
reply has arrived it loads every table the reply's version list names whose file is on the phone
(`PostStartupScene::checkConnectResult` 0x22402fc -> `DownloadMstFileList::loadMstList`). This server never put a
version list in that reply. With one row there, naming the function table at the version the phone already holds,
the game loads it before the title, the rebuild finds `FUNCTION_SP_CLASSUP`, and the login then downloads and
loads `F_SACRIFICE_MST` like any other table. Nothing is added to what the player sees or to what the phone asks.

When the row is NOT sent. If the named file is not on the phone, the game goes another way: it asks to download
it before the title (`DownloadSequencePopup`: a size prompt, then its download screen). That path has never run
against this server and could not be shown safe, so the row is only sent to a phone that is known to hold the
file at exactly that version:

  * the request says which save the phone knows (`LhVz6aD2`.`9Tbns0eI`, sent with every request): it must be
    this save's user id. A freshly installed game has none yet;
  * that phone (`6e4ik6kA`, its device id) has reached the home screen after an Initialize reply that gave the
    function table this same version. Reaching the home screen means the login's table download finished.

The record is in the save (`early_function_table`: device -> version), so it survives a restart and a new game
starts without it. A changed version (a server update) simply isn't matched until the phone has logged in once
more. The version sent is the recorded one, which is the one the Initialize reply gives: nothing is downloaded
twice.

`EXVIUS_CONVERT_EARLY_TABLE=0` turns it off: the row is never sent.
"""
from __future__ import annotations

import json
import os

LEDGER = "early_function_table"
TABLE = "F_FUNCTION_MST"
EARLY = "lEHBdOEf"           # GetBackgroundDownloadInfoRequest: sent before the title screen
LOGIN = "75fYdNxq"           # InitializeRequest: carries the whole version list
HOME = "Daud71Hn"            # RoutineHomeUpdateRequest: the home screen is reached
VERSIONS = "c1qYg84Q"
KEEP = 8                     # devices remembered in a save

_PENDING: dict = {}          # device -> the version the last Initialize reply gave it (this run of the server)


def enabled() -> bool:
    return os.environ.get("EXVIUS_CONVERT_EARLY_TABLE", "1").strip().lower() not in ("0", "off", "false", "no")


def phone(plaintext) -> tuple:
    """(user id, device id) the request states about the phone, or ("", "") when it says nothing."""
    try:
        body = json.JSONDecoder().raw_decode(plaintext)[0] if plaintext else {}
    except (ValueError, TypeError):
        return "", ""
    rows = body.get("LhVz6aD2") if isinstance(body, dict) else None
    row = rows[0] if isinstance(rows, list) and rows and isinstance(rows[0], dict) else {}
    return str(row.get("9Tbns0eI") or "").strip(), str(row.get("6e4ik6kA") or "").strip()


def _knows_this_save(player, user: str) -> bool:
    return bool(user) and user != "0" and user == str((player.data.get("identity") or {}).get("user_id") or "")


def decide(player, plaintext) -> tuple:
    """(version or None, why): the function table's version to name before the title for this request."""
    if not enabled():
        return None, "switched off (EXVIUS_CONVERT_EARLY_TABLE=0)"
    if player is None:
        return None, "no save is loaded"
    user, device = phone(plaintext)
    if not _knows_this_save(player, user):
        return None, "the phone names no save of this server yet (a fresh install, or it has never logged in)"
    held = str((player.data.get(LEDGER) or {}).get(device) or "")
    if not held:
        return None, "this phone has not reached the home screen since the record began"
    from ffbe_battle import advertised_version
    now = advertised_version(TABLE)
    if held != now:
        return None, f"the phone holds version {held}, the login now gives {now}: it is named again after one login"
    return held, "this phone reached the home screen with it"


def step(spec, reply_id, plaintext, state):
    """Pipeline step, after `serve_version_table`."""
    reply_id = str(reply_id)
    if reply_id not in (EARLY, LOGIN, HOME) or not isinstance(spec, dict):
        return spec
    player = getattr(state, "player", None)
    if reply_id == LOGIN:
        user, device = phone(plaintext)
        given = next((str(r.get("wM9AfX6I")) for r in spec.get(VERSIONS) or []
                      if isinstance(r, dict) and r.get("a4hXTIm0") == TABLE), None)
        _PENDING.pop(device, None)
        if given and player is not None and _knows_this_save(player, user):
            _PENDING[device] = given
        return spec
    if reply_id == HOME:
        user, device = phone(plaintext)
        given = _PENDING.get(device)
        if (given and player is not None and player.mode != "frozen" and _knows_this_save(player, user)
                and (player.data.get(LEDGER) or {}).get(device) != given):
            ledger = dict(player.data.get(LEDGER) or {})
            ledger.pop(device, None)
            ledger[device] = given                      # newest last
            while len(ledger) > KEEP:
                ledger.pop(next(iter(ledger)))
            player.data[LEDGER] = ledger
            player.dirty = True
            state.state_dirty = True
            print(f"CONVERT-TABLE early: this phone holds the function table at version {given}; "
                  f"it is named before the title from its next launch", flush=True)
        return spec
    version, why = decide(player, plaintext)
    if version is None:
        print(f"CONVERT-TABLE early: function table not named before the title ({why})", flush=True)
        return spec
    spec = dict(spec)
    spec[VERSIONS] = [{"a4hXTIm0": TABLE, "wM9AfX6I": version}]
    print(f"CONVERT-TABLE early: function table version {version} named before the title ({why})", flush=True)
    return spec
