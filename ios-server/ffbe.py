#!/usr/bin/env python3
"""Container entry point.

    serve            run the game server (the default)
    fetch-data       download / update the game data
    rotation [N]     show this week's summon rotation (and the next N-1 weeks)
    status           show the save's status (asks the running server)
    new-game         reset the save and start over (asks the running server; keeps a backup)
    convert-test     add one duplicate of each kind the Convert screens treat differently (keeps a backup);
                     convert-test --undo puts that backup back
"""
import json
import os
import shutil
import sys
import time
import urllib.request
from pathlib import Path

APP = Path(__file__).resolve().parent


def _local(path: str, body: bytes | None = None) -> dict:
    port = os.environ.get('FFBE_HTTP_PORT', '80')
    request = urllib.request.Request(f'http://127.0.0.1:{port}{path}', data=body,
                                     headers={'Content-Type': 'application/json'} if body else {})
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.load(response)
    except OSError as exc:
        raise SystemExit(f'the server is not answering ({exc}); is the container running?')


def main(argv: list[str]) -> int:
    command, rest = (argv[0], argv[1:]) if argv else ('serve', [])
    if command == 'serve':
        sys.path.insert(0, str(APP))
        import serve
        return serve.main()
    if command == 'fetch-data':
        sys.path.insert(0, str(APP))
        import fetch_data
        return fetch_data.main(rest)
    if command == 'rotation':
        sys.path.insert(0, str(APP))
        import serve
        serve.configure_engine()
        import replay
        if replay.enabled():
            return replay.main(['--weeks', rest[0] if rest else '1'])
        import gacha_rotation
        return gacha_rotation.main(['--weeks', rest[0] if rest else '1'])
    if command == 'status':
        print(json.dumps(_local('/__exvius/status'), indent=1))
        return 0
    if command == 'new-game':
        if '--yes' not in rest:
            print('This erases the current save and starts the game over. '
                  'A copy of the save is kept in server/state/backups/. Run again with --yes to continue.')
            return 1
        state = Path(os.environ.get('FFBE_SERVER_ROOT', '/srv/ffbe/server-root')) / 'state'
        if state.is_dir():
            backup = state / 'backups' / time.strftime('%Y%m%d-%H%M%S')
            backup.mkdir(parents=True, exist_ok=True)
            for item in state.iterdir():
                if item.is_file():
                    shutil.copy2(item, backup / item.name)
            print(f'saved a copy of the current save in {backup}')
        print(json.dumps(_local('/__exvius/new-game', b'{"confirm": true}'), indent=1))
        return 0
    if command == 'convert-test':
        path = '/__exvius/convert-test-undo' if '--undo' in rest else '/__exvius/convert-test'
        print(json.dumps(_local(path, b'{"confirm": true}'), indent=1, ensure_ascii=False))
        return 0
    print(__doc__)
    return 2


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
