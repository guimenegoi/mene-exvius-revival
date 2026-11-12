"""Local title-menu actions using the existing persistent PlayerState format."""
import json
from pathlib import Path
import shutil
import threading
import time

from player_state import PlayerState

STATE_LOCK = threading.RLock()


def status(state, state_file):
    player = state.player
    return {
        'has_save': Path(state_file).is_file() and player is not None,
        'name': player.data['identity']['handle_name'] if player else '',
        'rank': player.data['rank']['level'] if player else 1,
    }


def new_game(state, state_file, slot):
    destination = Path(state_file)
    fresh = PlayerState.load('', slot=slot, mode='live')
    # The upstream harness seeds ticket 180 for its focused summon fixture.
    # A player's New Game must not inherit those test resources.
    test_tickets = fresh.item_count(23, 180)
    if test_tickets and not fresh.spend_item(23, 180, test_tickets):
        raise RuntimeError('The fresh-save test ticket seed could not be removed')
    fresh.data['inventory']['items'] = [row for row in fresh.data['inventory']['items']
                                       if (row['item_type'], row['item_id']) != (23, 180)]
    fresh.data.setdefault('meta', {})['offline_started'] = True
    if destination.exists():
        recovery = destination.parent / 'backups'
        recovery.mkdir(exist_ok=True)
        backup = recovery / (destination.stem + '-' + str(time.time_ns()) + '.json')
        shutil.copyfile(destination, backup)
    if not fresh.save(str(destination), force=True):
        raise OSError('The new local save could not be written. The previous save is preserved.')
    state.player = fresh
    state.state_dirty = False
    return status(state, state_file)


# The Convert screen test (2026-11-12): one duplicate of each kind the Convert lists treat differently. Only the
# units the phone should list are named in the reply; the rest show the lists leave them out.
CONVERT_TEST_UNITS = (
    ("306001303", "3★ base, no conversion row: listed nowhere"),
    ("306000605", "3★ base with a row, at 5★: Convert to Prism"),
    ("100004604", "4★ base, no conversion row: listed nowhere"),
    ("208000404", "4★ base with a row, at 4★: listed nowhere"),
    ("208000405", "4★ base with a row, at 5★: Convert to Prism and to Fragments"),
    ("306000905", "5★ base, prism only: Convert to Prism"),
    ("100000315", "Dark Fina 5★: Convert to Prism and to Fragments"),
    ("100000317", "Dark Fina 7★: Convert to Fragments"),
    ("100044807", "a summoned NV: Convert to Fragments"),
    ("100000327", "Dark Fina NV (NV-awakened): Convert to Fragments"),
)


def convert_test(state, state_file):
    """Save a copy of the save, then add CONVERT_TEST_UNITS to it (the server's own save path)."""
    player = state.player
    if player is None:
        raise ValueError('No save loaded.')
    destination = Path(state_file)
    backup = None
    if destination.exists():
        recovery = destination.parent / 'backups'
        recovery.mkdir(exist_ok=True)
        backup = recovery / (destination.stem + '-before-convert-test-' + time.strftime('%Y%m%d-%H%M%S') + '.json')
        shutil.copyfile(destination, backup)
    added = []
    for master_id, what in CONVERT_TEST_UNITS:
        player.grant_unit(master_id)
        added.append(f'{master_id}: {what}')
    player.dirty = True
    if not player.save(str(destination)):
        raise OSError('The save could not be written.')
    state.state_dirty = False
    return {'added': added, 'backup': str(backup) if backup else ''}


def convert_test_undo(state, state_file, slot):
    """Put back the save `convert_test` copied last (the running server loads it and writes it as the save)."""
    destination = Path(state_file)
    copies = sorted((destination.parent / 'backups').glob(destination.stem + '-before-convert-test-*.json'))
    if not copies:
        raise ValueError('No copy from convert-test was found in server/state/backups/.')
    try:
        saved = json.loads(copies[-1].read_text(encoding='utf-8'))
    except (OSError, ValueError) as exc:
        raise ValueError(f'The copy {copies[-1].name} could not be read ({exc}). Nothing was changed.')
    restored = PlayerState.load(str(copies[-1]), slot=slot, mode='live')
    if len(restored.data.get('roster') or []) != len(saved.get('roster') or []):
        raise ValueError(f'The copy {copies[-1].name} did not load as saved. Nothing was changed.')
    restored.dirty = True
    if not restored.save(str(destination)):
        raise OSError('The save could not be written. The test save is still in place.')
    state.player = restored
    state.state_dirty = False
    return {'restored_from': str(copies[-1]), **status(state, state_file)}
