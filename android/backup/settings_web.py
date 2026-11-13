#!/usr/bin/env python3
"""FFBE Revival settings panel. Tailnet-only reverse proxy + independent login.

Edits only allow-listed server-config.json through config_service CAS.
Never handles FFBE saves, backup bearer tokens, or APK uploads.
"""
from __future__ import annotations

import argparse
import hashlib
import hmac
import html
import json
import ipaddress
import os
import re
import secrets
import ssl
import threading
import time
from datetime import datetime, timezone
from http import cookies
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import config_model
import config_service

DEVICE = "samsung-android"
COOKIE = "__Host-ffbe_session"
SESSION_TTL = 8 * 3600
FORM_LIMIT = 16384
LOGIN_LIMIT = 6
LOGIN_WINDOW = 900
PBKDF2_ROUNDS = 480000
FIELDS = {
    "Cronologia": [
        ("EXVIUS_REPLAY", "Reprodução histórica", "bool", "Ativa a progressão histórica de conteúdo."),
        ("EXVIUS_REPLAY_START", "Data inicial", "date", "Primeiro dia da cronologia Global (2016–2024)."),
        ("EXVIUS_REPLAY_PACE", "Ritmo do calendário", "text", "Ex.: 3,2@2020-08-20 — semanas históricas por semana real."),
        ("EXVIUS_REPLAY_FULL_RUNS", "Duração original dos eventos", "bool", "Considera o intervalo histórico completo de cada evento."),
    ],
    "Eventos e invocações": [
        ("EXVIUS_EVENT_ARCHIVE", "Arquivo de eventos", "bool", "Mantém o acervo de eventos disponível."),
        ("EXVIUS_SUMMON_ARCHIVE", "Arquivo de invocações", "bool", "Disponibiliza as invocações históricas."),
        ("EXVIUS_REPLAY_NOTICES", "Notícias históricas", "bool", "Exibe notícias relativas à semana histórica."),
        ("EXVIUS_REPLAY_NOTICE_WEEKS", "Semanas de notícias", "number", "Quantidade de semanas mantidas no mural."),
        ("EXVIUS_REPLAY_MARQUEE", "Banners históricos na Home", "bool", "Ativa a seleção histórica de banners."),
        ("MARQUEE_FLAG", "Modo de exibição dos banners", "marquee", "O modo flag é experimental; mantenha o padrão se houver instabilidade."),
    ],
    "Economia e Trust": [
        ("EXVIUS_LAPIS_MULTIPLIER", "Multiplicador de Lapis", "number", "Multiplica Lapis obtidos no jogo."),
        ("EXVIUS_DAILY_QUEST_LAPIS", "Lapis das missões diárias", "number", "Valor concedido por missão diária."),
        ("EXVIUS_QUEST_TRUST", "Trust nas missões", "bool", "Permite evolução de Trust ao concluir missões."),
        ("EXVIUS_QUEST_TRUST_CHANCE", "Chance de Trust (%)", "number", "Chance de evolução de Trust por unidade."),
        ("EXVIUS_QUEST_TRUST_POINTS", "Trust por acerto", "number", "Valor em décimos de ponto percentual."),
        ("EXVIUS_QUEST_TRUST_BIG_CHANCE", "Chance de bônus Trust (%)", "number", "Probabilidade de conceder o bônus maior."),
        ("EXVIUS_QUEST_TRUST_BIG_POINTS", "Valor do bônus Trust", "number", "Valor do bônus maior em décimos."),
    ],
}
ALL_FIELDS = {item[0]: item for group in FIELDS.values() for item in group}
# Effective defaults from the embedded Revival engine at this source revision:
# ios-server/serve.py, source/server/replay.py, lapis_economy.py,
# quest_trust.py, replay_notices.py, history_runs.py.
# These are presentation defaults, NOT saved overrides.
EFFECTIVE_DEFAULTS = {
    "EXVIUS_REPLAY": True,
    "EXVIUS_REPLAY_START": "2016-12-16",
    "EXVIUS_REPLAY_PACE": "3,2@2020-08-20",
    "EXVIUS_REPLAY_FULL_RUNS": True,
    "EXVIUS_EVENT_ARCHIVE": True,
    "EXVIUS_SUMMON_ARCHIVE": True,
    "EXVIUS_REPLAY_NOTICES": True,
    "EXVIUS_REPLAY_NOTICE_WEEKS": 8,
    "EXVIUS_REPLAY_MARQUEE": True,
    "MARQUEE_FLAG": "1",
    "EXVIUS_LAPIS_MULTIPLIER": 5,
    "EXVIUS_DAILY_QUEST_LAPIS": 150,
    "EXVIUS_QUEST_TRUST": True,
    "EXVIUS_QUEST_TRUST_CHANCE": 30,
    "EXVIUS_QUEST_TRUST_POINTS": 10,
    "EXVIUS_QUEST_TRUST_BIG_CHANCE": 5,
    "EXVIUS_QUEST_TRUST_BIG_POINTS": 50,
}
assert set(EFFECTIVE_DEFAULTS) == set(ALL_FIELDS)
CSS = """
:root{color-scheme:dark;font-family:Inter,system-ui,-apple-system,Segoe UI,sans-serif;color:#e9eff5;background:#0b121b}
*{box-sizing:border-box}body{margin:0;line-height:1.48}a{color:inherit;text-decoration:none}
.container{width:min(1090px,calc(100% - 32px));margin:auto}
header{border-bottom:1px solid #263240;background:#101925}
.top{display:flex;align-items:center;justify-content:space-between;gap:14px;padding:17px 0}
.brand{display:flex;gap:11px;align-items:center}.mark{width:36px;height:36px;display:grid;place-items:center;border-radius:11px;background:#1e5857;color:#7cf3de;font-size:20px;font-weight:700}
.brand b{display:block;font-size:15px}.muted,.sub{color:#99aabb}.sub{font-size:12px}
.tag{font-size:12px;border:1px solid #31524d;border-radius:30px;padding:5px 10px;color:#78d7c2}
.hero{padding:37px 0 24px}h1{font-size:clamp(25px,4vw,36px);letter-spacing:-.8px;margin:0 0 7px}h2{font-size:19px;letter-spacing:-.3px;margin:0 0 6px}
p{margin:5px 0 12px}.hero p{color:#9cacbe;font-size:14px;max-width:730px}
.metrics{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:12px;margin:4px 0 24px}
.metric,.panel{background:#121d2a;border:1px solid #263647;border-radius:13px}
.metric{padding:15px 18px}.metric small{color:#93a7ba;display:block;margin-bottom:5px}.metric strong{font-size:16px;display:block;word-break:break-all}
.layout{display:grid;grid-template-columns:180px minmax(0,1fr);align-items:start;gap:20px}
nav{position:sticky;top:20px;padding-top:6px}nav a{display:block;color:#9cafc0;padding:10px 12px;border-radius:9px;font-size:13px}nav a:hover{background:#1b2c39;color:#fff}
.panel{padding:23px;margin-bottom:17px}section .explain{color:#99aabb;font-size:13px;margin-bottom:16px}
.field{display:flex;align-items:center;justify-content:space-between;gap:20px;padding:13px 0;border-top:1px solid #253544}
.field:first-of-type{border-top:0}.detail{min-width:0}.detail label{font-size:14px;font-weight:620}.detail p{font-size:12px;color:#8ea2b5;margin:4px 0 0}
.control{flex:0 0 215px}select,input{width:100%;padding:10px 11px;border-radius:9px;border:1px solid #344b5e;background:#0e1824;color:#e5eef3;font-size:13px;font-family:inherit}
input:focus,select:focus{outline:2px solid #64d6bb;outline-offset:1px}
button{border:0;border-radius:9px;background:#62d2bb;color:#06211c;padding:11px 18px;font-weight:730;cursor:pointer;font-size:13px}
button:hover{background:#7bebd2}.ghost{background:transparent;border:1px solid #435565;color:#d5e1eb}
.alert{border:1px solid #5e5840;background:#24251e;color:#e7d79d;border-radius:12px;padding:14px 17px;font-size:13px;margin:0 0 18px}
.alert.error{border-color:#814448;background:#301d25;color:#ffb6b6}
.alert.success{border-color:#2c6a52;background:#19372f;color:#a8f2c9}
.actions{display:flex;align-items:center;gap:16px;justify-content:flex-end;margin:17px 0 28px;flex-wrap:wrap}
.actions small{color:#9fb0c0}input[type=checkbox]{width:16px;height:16px;accent-color:#62d2bb}
.check{display:flex;gap:11px;align-items:flex-start;font-size:13px;color:#d8e4ed}
.history{font-size:12px;color:#9db0c1}.history li{padding:5px 0;font-variant-numeric:tabular-nums}
footer{padding:26px 0 40px;font-size:12px;color:#7890a3}
.login-shell{min-height:90vh;display:grid;place-items:center;padding:25px}
.login{max-width:390px;width:100%;padding:30px;background:#121d2a;border:1px solid #314459;border-radius:16px}
.login h1{font-size:24px}.login label{display:block;font-size:13px;margin:19px 0 8px}.login button{width:100%;margin-top:16px}
@media(max-width:700px){.container{width:calc(100% - 26px)}.hero{padding-top:26px}.metrics{grid-template-columns:1fr}.layout{grid-template-columns:1fr}nav{position:static;display:flex;overflow:auto;padding:0 0 4px;gap:3px}nav a{white-space:nowrap}.panel{padding:17px}.field{align-items:stretch;flex-direction:column;gap:10px}.control{flex:auto}.actions{justify-content:stretch}.actions button{width:100%}.top{align-items:flex-start}}
"""


def esc(value) -> str:
    return html.escape(str(value), quote=True)


def hash_password(password: str, salt: bytes | None = None) -> dict:
    salt = salt or secrets.token_bytes(24)
    result = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, PBKDF2_ROUNDS)
    return {"salt": salt.hex(), "hash": result.hex(), "iterations": PBKDF2_ROUNDS}


def verify_password(password: str, stored: dict) -> bool:
    if not isinstance(stored, dict) or stored.get("iterations") != PBKDF2_ROUNDS:
        return False
    try:
        calculated = hash_password(password, bytes.fromhex(stored["salt"]))["hash"]
        return hmac.compare_digest(calculated, stored["hash"])
    except (ValueError, KeyError, TypeError):
        return False


def provision_auth(path: Path) -> None:
    if path.exists():
        raise FileExistsError("Refusing to replace existing panel auth")
    password = secrets.token_urlsafe(20)
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    with os.fdopen(fd, "w") as output:
        json.dump(hash_password(password), output)
    # Initial password only readable by root; it is never printed by the
    # service or the CLI. Delete this file after first successful login.
    secret = path.parent / "initial-password.txt"
    fd = os.open(secret, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    with os.fdopen(fd, "w") as output:
        output.write(password + "\n")


def history(root: Path, device: str) -> list[tuple[str, str]]:
    directory = root / "config-history" / device
    if directory.is_symlink() or not directory.is_dir():
        return []
    result = []
    for path in directory.glob("*.json"):
        if path.is_symlink() or not re.fullmatch(r"[0-9a-f]{64}\.json", path.name):
            continue
        try:
            document = config_model.read_private(path)
            if document is None or config_model.revision(document) != path.stem:
                continue
            timestamp = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc).strftime("%d/%m/%Y %H:%M UTC")
            result.append((timestamp, path.stem[:12]))
        except (ValueError, OSError):
            continue
    return sorted(result, reverse=True)[:30]


def parse_settings(form: dict) -> dict:
    settings = {}
    for key, (_, _, kind, _) in ALL_FIELDS.items():
        values = form.get(key, [])
        if len(values) != 1:
            raise ValueError("Missing or duplicated field: " + key)
        raw = values[0]
        if raw == "":
            continue
        # An unchanged inherited value is not a persistent override. A
        # custom numeric/date/text value is saved only when different from
        # the current engine default.
        if kind == "bool":
            if raw not in ("true", "false"):
                raise ValueError("Invalid boolean: " + key)
            settings[key] = raw == "true"
        elif kind == "number":
            if not re.fullmatch(r"[0-9]{1,5}", raw):
                raise ValueError("Invalid number: " + key)
            settings[key] = int(raw)
        else:
            settings[key] = raw
        if key in settings and settings[key] == EFFECTIVE_DEFAULTS[key]:
            settings.pop(key)
    return config_model.validate_document({"schema": 1, "settings": settings})


def field_html(item: tuple, saved: dict) -> str:
    key, label, kind, description = item
    custom = key in saved
    value = saved.get(key, EFFECTIVE_DEFAULTS[key])
    name = esc(key)
    default = EFFECTIVE_DEFAULTS[key]
    default_text = ("Ativado" if default else "Desativado") if kind == "bool" else (
        {"0": "Oculto", "1": "Normal", "flag": "Somente flag"}[default]
        if kind == "marquee" else str(default))
    if kind == "bool":
        options = [("", "Padrão · " + default_text), ("true", "Ativado"), ("false", "Desativado")]
        selected = ("true" if value else "false") if custom else ""
        control = f'<select name="{name}" id="{name}">' + "".join(
            f'<option value="{esc(v)}"{" selected" if v == selected else ""}>{esc(text)}</option>'
            for v, text in options) + "</select>"
    elif kind == "marquee":
        options = [("", "Padrão · " + default_text), ("0", "Oculto"), ("1", "Normal"), ("flag", "Somente flag")]
        selected = str(value) if custom else ""
        control = f'<select name="{name}" id="{name}">' + "".join(
            f'<option value="{v}"{" selected" if v == selected else ""}>{esc(text)}</option>'
            for v, text in options) + "</select>"
    else:
        value_str = str(value)
        attrs = 'type="date" min="2016-06-30" max="2024-10-30"' if kind == "date" else (
            f'type="number" min="{config_model.RANGES[key][0]}" max="{config_model.RANGES[key][1]}" step="1"'
            if kind == "number" else 'type="text" maxlength="96" placeholder="3,2@2020-08-20"')
        control = f'<input {attrs} name="{name}" id="{name}" value="{esc(value_str)}">'
    source = ("Personalizado" if custom else "Padrão desta versão")
    return (f'<div class="field"><div class="detail"><label for="{name}">{esc(label)}</label>'
            f'<p>{esc(description)}</p><p class="sub">{esc(source)} · {esc(default_text) if not custom else "substitui o padrão"}</p>'
            f'</div><div class="control">{control}</div></div>')


class WebApp:
    def __init__(self, store: Path, auth_path: Path, public_origin: str,
                 device: str = DEVICE, lan_origin: str | None = None):
        self.store = Path(store)
        self.auth = json.loads(Path(auth_path).read_text("utf-8"))
        self.public_origin = public_origin.rstrip("/")
        self.allowed_origins = {self.public_origin}
        if lan_origin:
            self.allowed_origins.add(lan_origin.rstrip("/"))
        self.device = device
        if not re.fullmatch(r"[a-zA-Z0-9_-]{1,64}", device):
            raise ValueError("Invalid device")
        if any(not origin.startswith("https://") for origin in self.allowed_origins):
            raise ValueError("All allowed origins must use HTTPS")
        self.sessions = {}
        self.failed = {}
        self.lock = threading.Lock()

    def session(self, cookie_header: str):
        jar = cookies.SimpleCookie()
        try:
            jar.load(cookie_header or "")
            key = jar[COOKIE].value
        except (cookies.CookieError, KeyError):
            return None
        with self.lock:
            record = self.sessions.get(key)
            if not record:
                return None
            if time.monotonic() > record["expires"]:
                self.sessions.pop(key, None)
                return None
            return key, record

    def create_session(self):
        key = secrets.token_urlsafe(36)
        record = {"expires": time.monotonic() + SESSION_TTL,
                  "csrf": secrets.token_urlsafe(30)}
        with self.lock:
            self.sessions[key] = record
        return key, record

    def authenticate(self, password: str, remote: str) -> bool:
        now = time.monotonic()
        with self.lock:
            hits = [t for t in self.failed.get(remote, []) if now - t < LOGIN_WINDOW]
            if len(hits) >= LOGIN_LIMIT:
                return False
        good = verify_password(password, self.auth)
        with self.lock:
            if good:
                self.failed.pop(remote, None)
            else:
                self.failed[remote] = hits + [now]
        return good


def make_handler(app: WebApp):
    class Handler(BaseHTTPRequestHandler):
        server_version = "FFBE-Settings/1"
        def log_message(self, *args):
            # Never write session cookies, credentials or form values to logs.
            pass

        def _send(self, code, text, *, cookie=None, redirect=None):
            data = text.encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("Referrer-Policy", "same-origin")
            self.send_header("X-Frame-Options", "DENY")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Content-Security-Policy",
                             "default-src 'none'; style-src 'unsafe-inline'; "
                             "form-action 'self'; frame-ancestors 'none'; base-uri 'none'")
            if cookie:
                self.send_header("Set-Cookie", cookie)
            if redirect:
                self.send_header("Location", redirect)
            self.end_headers()
            if data:
                self.wfile.write(data)

        def _form(self):
            if self.headers.get_content_type() != "application/x-www-form-urlencoded":
                raise ValueError("Invalid form content type")
            try:
                size = int(self.headers.get("Content-Length", "0"))
                if not 1 <= size <= FORM_LIMIT:
                    raise ValueError("Form content length invalid")
                data = self.rfile.read(size)
                if len(data) != size:
                    raise ValueError("Truncated form")
                return parse_qs(data.decode("utf-8"), keep_blank_values=True,
                                max_num_fields=50, strict_parsing=True)
            except (UnicodeError, ValueError) as exc:
                raise ValueError("Invalid form") from exc

        def _origin_ok(self):
            # Some browsers omit Origin on HTTPS LAN forms after certificate
            # exceptions. Accept only explicit origins or strong same-origin
            # Fetch Metadata / Referer tied to the requested allowed host.
            origin = self.headers.get("Origin")
            if origin in app.allowed_origins:
                return True
            if origin not in (None, "null"):
                return False
            host = self.headers.get("Host", "")
            if host not in {urlsplit(x).netloc for x in app.allowed_origins}:
                return False
            if self.headers.get("Sec-Fetch-Site") == "same-origin":
                return True
            if origin is None:
                ref = urlsplit(self.headers.get("Referer", ""))
                return f"{ref.scheme}://{ref.netloc}" in app.allowed_origins
            return False

        def _layout(self, body):
            return ('<!doctype html><html lang="pt-BR"><head><meta charset="utf-8">'
                    '<meta name="viewport" content="width=device-width,initial-scale=1">'
                    '<meta name="theme-color" content="#101925">'
                    '<title>Configurações · FFBE Revival</title>'
                    f'<style>{CSS}</style></head><body>{body}</body></html>')

        def _login(self, error=""):
            alert = ('<div class="alert error">Senha incorreta ou limite de tentativas atingido.</div>'
                     if error else "")
            content = (f'<main class="login-shell"><div class="login"><div class="brand">'
                       '<div class="mark">F</div><div><b>FFBE Revival</b><span class="sub">'
                       'Painel privado · LXC 120</span></div></div><h1 style="margin-top:27px">'
                       'Configurações</h1><p class="muted">Acesso exclusivo pela sua rede Tailscale.</p>'
                       f'{alert}<form method="POST" action="/login">'
                       '<label for="password">Senha do painel</label>'
                       '<input id="password" name="password" type="password" '
                       'autocomplete="current-password" required autofocus>'
                       '<button type="submit">Entrar</button></form></div></main>')
            self._send(200 if not error else 401, self._layout(content))

        def _dashboard(self, record, *, error="", saved=False, code=200):
            try:
                current = config_service.get(app.store, app.device)
                revision = current["revision"] if current else "0"
                settings = current["document"]["settings"] if current else {}
                earlier = history(app.store, app.device)
            except (OSError, ValueError) as exc:
                self._send(500, self._layout('<main class="container"><h1>Erro ao ler configuração.</h1></main>'))
                return
            csrf = esc(record["csrf"])
            info = ('<div class="alert success">Configuração salva no servidor. '
                    'O Android aplicará a revisão após sincronizar e reiniciar.</div>' if saved else '')
            if error:
                info += f'<div class="alert error">{esc(error)}</div>'
            panels = []
            for index, (group, items) in enumerate(FIELDS.items()):
                panels.append(
                    f'<section class="panel" id="section-{index}"><h2>{esc(group)}</h2>'
                    '<p class="explain">Os valores padrão já aparecem preenchidos. Só alterações diferentes do padrão serão sincronizadas.</p>'
                    + "".join(field_html(item, settings) for item in items)
                    + '</section>')
            past = ('<ol class="history">' + "".join(
                f'<li>{esc(when)} · {esc(digest)}…</li>' for when, digest in earlier) + '</ol>'
                    if earlier else '<p class="muted">Nenhuma revisão anterior.</p>')
            content = (f'<header><div class="container top"><div class="brand"><div class="mark">F</div>'
                       '<div><b>FFBE Revival</b><span class="sub">Configurações do servidor</span></div></div>'
                       '<span class="tag">Tailscale · Privado</span></div></header>'
                       '<main class="container"><div class="hero"><h1>Configurações</h1>'
                       '<p>Ajuste as regras do Revival sem recompilar o APK. O jogo continuará funcionando '
                       'offline com a última configuração aprovada.</p></div>'
                       '<div class="metrics"><div class="metric"><small>Dispositivo</small>'
                       f'<strong>{esc(app.device)}</strong></div><div class="metric">'
                       f'<small>Revisão da LXC</small><strong>{esc(revision[:12])}'
                       f'{"…" if revision != "0" else " · inicial"}</strong></div>'
                       '<div class="metric"><small>Aplicação no Android</small>'
                       '<strong>Pendente de sincronização</strong></div></div>'
                       f'{info}<div class="layout"><nav><a href="#section-0">Cronologia</a>'
                       '<a href="#section-1">Eventos e invocações</a>'
                       '<a href="#section-2">Economia e Trust</a>'
                       '<a href="#history">Histórico</a></nav><div>'
                       '<form action="/settings" method="POST">'
                       f'<input type="hidden" name="csrf" value="{csrf}">'
                       f'<input type="hidden" name="revision" value="{esc(revision)}">'
                       + "".join(panels)
                       + '<div class="alert"><strong>Atenção à campanha histórica</strong><p>'
                       'Alterar data inicial ou ritmo pode exigir migração da âncora do replay. '
                       'O Android não deve aplicar uma cronologia incompatível automaticamente.</p>'
                       '<label class="check"><input type="checkbox" name="confirm_timeline" value="yes">'
                       '<span>Entendo que mudanças de cronologia poderão ficar pendentes no Android.</span>'
                       '</label></div>'
                       '<div class="actions"><small>Salvar cria uma revisão; não reinicia o jogo.</small>'
                       '<button type="submit">Salvar configurações</button></div></form>'
                       '<section class="panel" id="history"><h2>Histórico de revisões</h2>'
                       f'{past}</section>'
                       f'<form action="/logout" method="POST" class="actions">'
                       f'<input type="hidden" name="csrf" value="{csrf}">'
                       '<button class="ghost" type="submit">Encerrar sessão</button></form>'
                       '</div></div></main><footer class="container">FFBE Revival · '
                       'Configuração separada do save · Sem dependência de internet para jogar</footer>')
            self._send(code, self._layout(content))

        def do_GET(self):
            if self.path == "/healthz":
                return self._send(200, "ok")
            if self.path.split("?")[0] not in ("/",):
                return self._send(404, "Not found")
            session = app.session(self.headers.get("Cookie", ""))
            if not session:
                return self._login()
            return self._dashboard(session[1],
                                   saved="saved=1" in urlsplit(self.path).query)

        def do_POST(self):
            if not self._origin_ok():
                return self._send(403, "Forbidden origin")
            try:
                form = self._form()
            except ValueError:
                return self._send(400, "Invalid form")
            if self.path == "/login":
                password = form.get("password", [""])
                if len(password) != 1 or len(password[0]) > 256 or not app.authenticate(
                        password[0], self.client_address[0]):
                    return self._login(error="wrong")
                key, record = app.create_session()
                self._send(303, "", redirect="/",
                           cookie=f"{COOKIE}={key}; Path=/; Max-Age={SESSION_TTL}; "
                                  "Secure; HttpOnly; SameSite=Strict")
                return
            session = app.session(self.headers.get("Cookie", ""))
            if not session:
                return self._send(401, "Unauthenticated")
            key, record = session
            submitted = form.get("csrf", [""])
            if len(submitted) != 1 or not hmac.compare_digest(submitted[0], record["csrf"]):
                return self._send(403, "CSRF check failed")
            if self.path == "/logout":
                with app.lock:
                    app.sessions.pop(key, None)
                return self._send(303, "", redirect="/",
                                  cookie=f"{COOKIE}=; Path=/; Max-Age=0; "
                                         "Secure; HttpOnly; SameSite=Strict")
            if self.path != "/settings":
                return self._send(404, "Not found")
            try:
                versions = form.get("revision", [])
                if len(versions) != 1:
                    raise ValueError("Revisão inválida")
                previous = config_service.get(app.store, app.device)
                expected = previous["revision"] if previous else "0"
                if versions[0] != expected:
                    return self._dashboard(record, error="A revisão mudou em outra sessão. "
                                           "Recarregue e confira antes de salvar.", code=409)
                candidate = parse_settings(form)
                oldsettings = previous["document"]["settings"] if previous else {}
                edits = any(candidate["settings"].get(k) != oldsettings.get(k)
                            for k in ("EXVIUS_REPLAY_START", "EXVIUS_REPLAY_PACE"))
                if edits and form.get("confirm_timeline") != ["yes"]:
                    return self._dashboard(record, error="Confirme a alteração de cronologia "
                                           "para continuar.", code=422)
                code, result = config_service.put(app.store, app.device,
                        config_model.encode(candidate), expected)
                if code not in (200, 201):
                    return self._dashboard(record, error="Conflito ou configuração inválida; "
                                           "nenhuma alteração aplicada.", code=409)
                return self._send(303, "", redirect="/?saved=1")
            except (OSError, ValueError, TypeError) as exc:
                return self._dashboard(record, error="Valor inválido: " + str(exc)[:100],
                                       code=422)

    return Handler


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--bind", required=True)
    parser.add_argument("--port", type=int, default=18448)
    parser.add_argument("--store", required=True, type=Path)
    parser.add_argument("--auth", required=True, type=Path)
    parser.add_argument("--cert", required=True, type=Path)
    parser.add_argument("--key", required=True, type=Path)
    parser.add_argument("--public-origin", required=True)
    parser.add_argument("--lan-origin", default=None)
    parser.add_argument("--device", default=DEVICE)
    parser.add_argument("--provision-auth", action="store_true")
    args = parser.parse_args(argv)
    if args.provision_auth:
        provision_auth(args.auth)
        print("Panel authentication created; initial password stored in root-only file.")
        return 0
    if not args.auth.is_file() or args.auth.is_symlink() or args.auth.stat().st_mode & 0o007:
        parser.error("Panel auth must be an existing private file")
    address = ipaddress.ip_address(args.bind)
    if address.is_unspecified or not (address.is_private or address.is_loopback):
        parser.error("Panel must bind to a specific private address")
    if any(p.is_symlink() or not p.is_file() for p in (args.cert, args.key)):
        parser.error("TLS certificate and key must be regular files")
    if args.key.stat().st_mode & 0o077:
        parser.error("TLS key must be mode 0600")
    app = WebApp(args.store, args.auth, args.public_origin, args.device,
                 lan_origin=args.lan_origin)
    server = ThreadingHTTPServer((args.bind, args.port), make_handler(app))
    # Encrypt also the LAN hop between Proxmox and the LXC. Tailscale Serve
    # handles public HTTPS and reverse-proxies to this private TLS listener.
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    context.load_cert_chain(str(args.cert), str(args.key))
    server.socket = context.wrap_socket(server.socket, server_side=True)
    print("FFBE-SETTINGS-WEB READY", args.bind, args.port, flush=True)
    try:
        server.serve_forever()
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
