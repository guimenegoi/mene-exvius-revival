"""Ask the game to upload its own error log, and keep what it sends.

The client keeps a report log (`Reports`, the "REPORTSMODULE"): among other things, a failed table load
writes `Error loading MST INFO=<details>` to it (LoginScene::procStateMstLoadWait and
procStateTextMstLoadWait). The live servers could ask for that log with a "report back" group in any
reply; the client's report scheduler (`Reports::update`) then uploads it with `sgStoreLogReportRequest`
and waits for a "report state" group in the answer. Read from the Android 9.0 library:

  report back   group 383e98ad (sgReportBackResponse)
                  86f76840  send-after time, "%Y-%m-%d %H:%M:%S" UTC (CommonUtils::convertToTime);
                            "0" means "no request"
                  da99ba05  hold flag; "0" lets the upload go ahead
  store log     request sgStoreLogReportRequest, /actionSymbol/6611dc2f.php, key af7a56a0
  report state  group cd87bd8b (sgReportStateResponse), 950510b8 = 0 for success

This matters for a stock client such as the iPhone app, whose own system log is redacted: its reports
are the only place the client says what went wrong. Turned on with EXVIUS_CLIENT_REPORTS=1; each upload
is saved under <server data>/client-reports/.

OFF BY DEFAULT since 2026-11-10. The request used to ride on every RoutineHomeUpdateRequest reply too, which the
game sends about every 15 seconds, and the game then uploaded its whole log each time (a player measured about
22 MB every 15 seconds, public repo PR #2), so loading was slow. Off, the server asks for nothing; an upload
the game already has queued is still answered (report state 0) so it doesn't retry, but not saved, and the
server prints one line with its size. The per-request records (capture_server) never keep a report's body.
On, the request goes out once per launch, on the GameSettingRequest reply only (operator, 2026-11-10).
"""
from __future__ import annotations

import json
import os
import time

REPORT_BACK_GROUP = "383e98ad"
REPORT_BACK_TIME = "86f76840"
REPORT_BACK_HOLD = "da99ba05"
REPORT_STATE_GROUP = "cd87bd8b"
REPORT_STATE_VALUE = "950510b8"
STORE_LOG_REQUEST = "6611dc2f"
# The reply that carries the request: the first call of every launch, so the game uploads once per launch.
# Not RoutineHomeUpdateRequest (Daud71Hn): it comes about every 15 seconds, and each reply made the game upload
# its whole log again (2026-11-10).
CARRIERS = {"OTX6Fmvu"}   # GameSettingRequest


def enabled() -> bool:
    return os.environ.get("EXVIUS_CLIENT_REPORTS") == "1"


def _folder() -> str:
    import data_paths
    base = os.environ.get("FFBE_DATA") or getattr(data_paths, "DATA_ROOT", None) or "."
    folder = os.path.join(base, "client-reports")
    os.makedirs(folder, exist_ok=True)
    return folder


def _digest(plaintext) -> str:
    import hashlib
    text = plaintext if isinstance(plaintext, str) else repr(plaintext)
    return hashlib.sha1(text.encode("utf-8", "replace")).hexdigest()[:16]


def saved_copy(plaintext) -> str | None:
    """The file an identical upload was already saved in, or None. The game sends every log file it still holds
    at each launch (the operator's phone: the same six older logs again, then the newest, 2026-11-13), so without
    this each launch added tens of MB of copies. The digest is the last part of the file name."""
    mark = "-" + _digest(plaintext) + ".txt"
    try:
        for name in sorted(os.listdir(_folder())):
            if name.endswith(mark):
                return os.path.join(_folder(), name)
    except OSError:
        pass
    return None


def _save(plaintext) -> str:
    stamp = time.strftime("%Y%m%d-%H%M%S")
    path = os.path.join(_folder(), f"{stamp}-{int(time.time() * 1000) % 1000:03d}-{_digest(plaintext)}.txt")
    text = plaintext if isinstance(plaintext, str) else repr(plaintext)
    # The log itself is usually one string field inside the request; unwrap it so the file is readable.
    pretty = text
    try:
        body = json.JSONDecoder().raw_decode(text)[0]
        pieces = []
        for group, rows in body.items():
            for row in rows if isinstance(rows, list) else [rows]:
                if isinstance(row, dict):
                    for key, value in row.items():
                        pieces.append(f"[{group}.{key}]\n{value}")
        if pieces:
            pretty = "\n\n".join(pieces)
    except (ValueError, AttributeError):
        pass
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(pretty)
        fh.write("\n\n----- raw request -----\n")
        fh.write(text)
    return path


# The game encrypts each line of its log (AES-CBC, padded twice; key and IV from libgame, as in
# ios-server/devtools/decode_reports.py).
LOG_KEY, LOG_IV = b"FFBE2020DevsRGod", b"dZMjkk8gFDzKHlsx"
LOG_GROUP, LOG_FIELD = "a8035010", "FPGJbL8x"


def log_lines(plaintext) -> list:
    """The readable lines of an uploaded game log (lines that don't decode are left out)."""
    import ffbe_crypto
    text = plaintext if isinstance(plaintext, str) else repr(plaintext)
    try:
        body = json.JSONDecoder().raw_decode(text)[0]
        raw = str(body[LOG_GROUP][0][LOG_FIELD])
    except (ValueError, KeyError, IndexError, TypeError):
        return []
    out = []
    for line in raw.split("\n"):
        if not line.strip():
            continue
        try:
            plain = ffbe_crypto.cbc_decrypt(LOG_KEY, line.strip(), LOG_IV)
        except Exception:  # noqa: BLE001 -- not a line the game encrypted
            continue
        if plain and 1 <= plain[-1] <= 16 and plain[-plain[-1]:] == bytes([plain[-1]]) * plain[-1]:
            plain = plain[:-plain[-1]]              # the game's own second padding
        out.append(plain.decode("utf-8", "replace"))
    return out


def table_report(plaintext, name: str = "F_SACRIFICE_MST", token: str = "w5JFGPh3") -> list:
    """`CONVERT-TABLE phone log` lines for the server log: what the phone's own log says about the Convert
    screens' table (2026-11-13, operator's test: the lists were empty and the phone had not asked for the table).
    A failed table load is written there as `MST > Failed to load MST. REASON=... MSTNAME=... MSTFILE=...`."""
    import collections
    import re
    lines = log_lines(plaintext)
    if not lines:
        return ["CONVERT-TABLE phone log: no readable line in the upload"]
    about = [ln for ln in lines if name in ln or token in ln]
    failed = collections.Counter(m for ln in lines if "Failed to load MST" in ln for m in re.findall(r"MSTNAME=(\w+)", ln))
    out = [f"CONVERT-TABLE phone log: {len(lines)} line(s) read, {len(about)} about {name}"]
    for ln in about[-3:]:
        out.append("CONVERT-TABLE phone log, about the table: " + " ".join(ln.split())[:400])
    if failed:
        out.append("CONVERT-TABLE phone log, tables the phone failed to load: "
                   + ", ".join(f"{table} x{count}" for table, count in failed.most_common(8)))
    else:
        out.append("CONVERT-TABLE phone log: no failed table load in it")
    return out


def handle(spec, reply_id, plaintext):
    """Add the report-back request to carrier replies (when on), and answer a log upload (saved when on)."""
    if reply_id == STORE_LOG_REQUEST:
        size = len(plaintext or "")
        if enabled():
            have = saved_copy(plaintext or "")
            if have:
                print(f"CLIENT REPORT: game sent a log again ({size} chars); already saved as {have}", flush=True)
                return {REPORT_STATE_GROUP: [{REPORT_STATE_VALUE: "0"}]}
            path = _save(plaintext or "")
            print(f"CLIENT REPORT: game uploaded its log ({size} chars) -> {path}", flush=True)
            try:
                for line in table_report(plaintext or ""):
                    print(line, flush=True)
            except Exception as exc:  # noqa: BLE001 -- the upload is saved either way
                print(f"CONVERT-TABLE phone log: could not be read ({exc!r})", flush=True)
        else:
            print(f"CLIENT REPORT: game uploaded a queued log ({size} chars); not saved "
                  f"(EXVIUS_CLIENT_REPORTS=0)", flush=True)
        return {REPORT_STATE_GROUP: [{REPORT_STATE_VALUE: "0"}]}
    if not enabled():
        return spec
    if reply_id in CARRIERS and isinstance(spec, dict):
        spec = dict(spec)
        # A time in the past: upload as soon as the report scheduler next runs.
        spec[REPORT_BACK_GROUP] = [{REPORT_BACK_TIME: "2020-01-01 00:00:00", REPORT_BACK_HOLD: "0"}]
    return spec
