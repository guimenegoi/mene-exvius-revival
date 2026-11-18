"""Security and behavior tests for the private FFBE settings panel."""
from __future__ import annotations

import html
import http.client
import json
import pathlib
import re
import sys
import tempfile
import threading
import unittest
from urllib.parse import urlencode

sys.path.insert(0, str(pathlib.Path(__file__).parent))
import config_model
import config_service
import settings_web as web


class SettingsWebTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self.temp.name)
        self.store = self.root / "zfs"
        self.store.mkdir()
        self.secret = self.root / "auth.json"
        self.secret.write_text(json.dumps(web.hash_password("correct horse battery staple")))
        self.origin = "https://test.example:8445"
        self.app = web.WebApp(self.store, self.secret, self.origin, "phone")
        self.http = web.ThreadingHTTPServer(("127.0.0.1", 0), web.make_handler(self.app))
        self.worker = threading.Thread(target=self.http.serve_forever, daemon=True)
        self.worker.start()
        self.cookie = None
        self.csrf = None

    def tearDown(self):
        self.http.shutdown()
        self.http.server_close()
        self.worker.join(2)
        self.temp.cleanup()

    def request(self, method="GET", path="/", fields=None, headers=None):
        conn = http.client.HTTPConnection("127.0.0.1", self.http.server_port, timeout=4)
        headers = dict(headers or {})
        if self.cookie:
            headers["Cookie"] = self.cookie
        if method == "POST":
            headers.setdefault("Origin", self.origin)
            headers.setdefault("Content-Type", "application/x-www-form-urlencoded")
            body = urlencode(fields or {}, doseq=True)
        else:
            body = None
        conn.request(method, path, body=body, headers=headers)
        response = conn.getresponse()
        code = response.status
        body = response.read().decode("utf-8")
        cookie = response.getheader("Set-Cookie")
        destination = response.getheader("Location")
        security = {key: response.getheader(key) for key in (
            "Content-Security-Policy", "X-Frame-Options", "Cache-Control")}
        conn.close()
        return code, body, cookie, destination, security

    def login(self):
        code, _, cookie, dest, _ = self.request("POST", "/login", {"password": "correct horse battery staple"})
        self.assertEqual(code, 303)
        self.assertEqual(dest, "/")
        self.assertIn("Secure; HttpOnly; SameSite=Strict", cookie)
        self.cookie = cookie.split(";", 1)[0]
        session = self.app.session(self.cookie)
        self.csrf = session[1]["csrf"]

    def settings_form(self, **overrides):
        values = {key: "" for key in web.ALL_FIELDS}
        values.update({"csrf": self.csrf, "revision": "0"})
        values.update(overrides)
        return values

    def test_historical_preview_requires_login_and_is_read_only(self):
        route='/history-preview?start=2016-06-30&week=1'
        status,body,_,_,_=self.request('GET',route)
        self.assertEqual(status,401)
        self.assertNotIn('Kefka',body)
        self.login()
        status,body,_,_,_=self.request('GET',route)
        self.assertEqual(status,200)
        data=json.loads(body)
        self.assertEqual(data['range'],'07/07/2016–13/07/2016')
        self.assertEqual(data['banners']['total'],1)
        self.assertIn('Kefka',data['banners']['items'][0]['name'])
        self.assertIn('calendar',data)
        august_status,august_body,_,_,_=self.request('GET','/history-preview?start=2016-06-30&week=4')
        self.assertEqual(august_status,200)
        august=json.loads(august_body)
        self.assertEqual(august['calendar']['total'],1)
        self.assertEqual(august['events']['total'],0)
        self.assertIn('Demons Unleashed',august['calendar']['items'][0]['name'])
        self.assertEqual(config_service.get(self.store,self.app.device),None)
        for invalid in ('week=-1','week=999','week=1&week=2','week=evil'):
            status,_,_,_,_=self.request('GET','/history-preview?start=2016-06-30&'+invalid)
            self.assertEqual(status,400,invalid)

    def test_history_preview_uses_hashed_inline_script_and_escapes_content(self):
        self.login()
        status,body,_,_,security=self.request('GET','/')
        self.assertEqual(status,200)
        self.assertIn('id="history-period-preview"',body)
        self.assertIn('Estreias no calendário Global',body)
        self.assertIn('Eventos no acervo Revival',body)
        self.assertIn('<script>'+web.PREVIEW_JS+'</script>',body)
        self.assertIn("'sha256-"+web.PREVIEW_HASH+"'",security['Content-Security-Policy'])
        self.assertIn("connect-src 'self'",security['Content-Security-Policy'])
        self.assertIn('li.textContent = key ===',web.PREVIEW_JS)
        self.assertIn('item.name',web.PREVIEW_JS)
        self.assertNotIn('innerHTML',web.PREVIEW_JS)

    def test_authenticated_pair_code_and_one_time_app_claim(self):
        self.login()
        with tempfile.TemporaryDirectory() as private:
            root=pathlib.Path(private)
            (root/'token').write_text('X'*48)
            (root/'cert.pem').write_text('-----BEGIN CERTIFICATE-----\nTEST\n-----END CERTIFICATE-----')
            self.app.pair_codes=web.phone_pairing.PairCodes(root)
            code,body,_,_,_=self.request('POST','/pair/create',{'csrf':self.csrf})
            self.assertEqual(code,200)
            self.assertNotIn('X'*48,body)
            match=re.search(r'[A-F0-9]{24}',body)
            self.assertIsNotNone(match)
            claim=json.dumps({'code':match.group(0),'device':'samsung-android'})
            def remote_claim():
                conn=http.client.HTTPConnection('127.0.0.1',self.http.server_port,timeout=4)
                conn.request('POST','/pair/claim',body=claim,headers={'Content-Type':'application/json'})
                response=conn.getresponse();status=response.status;payload=json.loads(response.read());conn.close()
                return status,payload
            status,payload=remote_claim()
            self.assertEqual(status,200)
            self.assertEqual(payload['token'],'X'*48)
            status,payload=remote_claim()
            self.assertEqual(status,403)
            self.assertNotIn('token',payload)

    def test_pair_code_requires_login_and_csrf(self):
        status,_,_,_,_=self.request('POST','/pair/create',{'csrf':'fake'})
        self.assertNotEqual(status,200)
        self.login()
        status,_,_,_,_=self.request('POST','/pair/create',{'csrf':'bad'})
        self.assertEqual(status,403)

    def test_unauthenticated_pages_are_login_only(self):
        code, body, _, _, sec = self.request()
        self.assertEqual(code, 200)
        self.assertIn("Senha do painel", body)
        self.assertNotIn("Lapis das missões", body)
        self.assertIn("frame-ancestors 'none'", sec["Content-Security-Policy"])
        self.assertEqual(sec["X-Frame-Options"], "DENY")

    def test_login_wrong_password(self):
        code, _, cookie, _, _ = self.request("POST", "/login", {"password": "bad"})
        self.assertEqual(code, 401)
        self.assertIsNone(cookie)

    def test_rate_limit(self):
        for index in range(web.LOGIN_LIMIT + 3):
            self.request("POST", "/login", {"password": "bad"})
        code, _, _, _, _ = self.request("POST", "/login", {"password": "correct horse battery staple"})
        self.assertNotEqual(code, 303)

    def test_lan_origin_explicitly_authorized(self):
        self.app.allowed_origins.add("https://192.168.15.230:18448")
        code, _, cookie, _, _ = self.request(
            "POST", "/login", {"password": "correct horse battery staple"},
            {"Origin": "https://192.168.15.230:18448"})
        self.assertEqual(code, 303)
        self.assertIn("Secure", cookie)

    def test_lan_self_signed_browser_fetch_metadata(self):
        self.app.allowed_origins.add("https://192.168.15.230:18448")
        code, _, cookie, _, _ = self.request(
            "POST", "/login", {"password": "correct horse battery staple"},
            {"Origin": "null", "Sec-Fetch-Site": "same-origin",
             "Host": "192.168.15.230:18448"})
        self.assertEqual(code, 303)
        self.assertIn("Secure", cookie)

    def test_rejects_cross_site_fetch_metadata(self):
        self.app.allowed_origins.add("https://192.168.15.230:18448")
        for headers in (
            {"Origin": "null", "Host": "192.168.15.230:18448"},
            {"Origin": "null", "Sec-Fetch-Site": "cross-site",
             "Host": "192.168.15.230:18448"},
            {"Origin": "null", "Sec-Fetch-Site": "same-origin",
             "Host": "elsewhere.example"},
        ):
            with self.subTest(headers=headers):
                code, _, _, _, _ = self.request(
                    "POST", "/login",
                    {"password": "correct horse battery staple"}, headers)
                self.assertEqual(code, 403)

    def test_legacy_same_origin_referer(self):
        self.app.allowed_origins.add("https://192.168.15.230:18448")
        code, _, cookie, _, _ = self.request(
            "POST", "/login",
            {"password": "correct horse battery staple"},
            {"Host": "192.168.15.230:18448",
             "Referer": "https://192.168.15.230:18448/"})
        self.assertEqual(code, 303)
        self.assertIn("Secure", cookie)

    def test_origin_enforced_on_login_and_save(self):
        code, _, _, _, _ = self.request("POST", "/login", {"password": "correct horse battery staple"},
                                         {"Origin": "https://attacker.example"})
        self.assertEqual(code, 403)
        self.login()
        code, _, _, _, _ = self.request("POST", "/settings", self.settings_form(),
                                         {"Origin": "https://attacker.example"})
        self.assertEqual(code, 403)

    def test_requires_csrf(self):
        self.login()
        form = self.settings_form()
        form["csrf"] = "wrong"
        code, _, _, _, _ = self.request("POST", "/settings", form)
        self.assertEqual(code, 403)

    def test_login_and_render_fields(self):
        self.login()
        code, body, _, _, _ = self.request()
        self.assertEqual(code, 200)
        self.assertIn("Cronologia", body)
        self.assertIn("Economia e Trust", body)
        self.assertIn("EXVIUS_REPLAY_START", body)
        self.assertNotIn("correct horse battery staple", body)

    def test_effective_defaults_are_visible_without_overrides(self):
        self.login()
        code, body, _, _, _ = self.request()
        self.assertEqual(code, 200)
        self.assertIn('value="2016-06-30"', body)
        self.assertIn('value="3,2@2020-08-20"', body)
        self.assertIn('value="150"', body)
        self.assertIn('value="30"', body)
        self.assertIn('Padrão · Ativado', body)
        self.assertIn('Padrão desta versão', body)
        self.assertIsNone(config_service.get(self.store, "phone"))

    def test_submitting_effective_defaults_does_not_force_overrides(self):
        self.login()
        inputs = self.settings_form()
        for key, value in web.EFFECTIVE_DEFAULTS.items():
            kind = web.ALL_FIELDS[key][2]
            if kind not in ("bool", "marquee"):
                inputs[key] = str(value)
        code, _, _, _, _ = self.request("POST", "/settings", inputs)
        self.assertEqual(code, 303)
        self.assertEqual(config_service.get(self.store, "phone")["document"]["settings"], {})

    def test_save_revision_and_optional_fields(self):
        self.login()
        fields = self.settings_form(EXVIUS_REPLAY_NOTICES="false",
                                    EXVIUS_LAPIS_MULTIPLIER="4")
        code, _, _, dest, _ = self.request("POST", "/settings", fields)
        self.assertEqual(code, 303)
        self.assertEqual(dest, "/?saved=1")
        stored = config_service.get(self.store, "phone")
        self.assertEqual(stored["document"]["settings"],
                         {"EXVIUS_LAPIS_MULTIPLIER": 4, "EXVIUS_REPLAY_NOTICES": False})
        self.assertEqual((self.store/"configs"/"phone.json").stat().st_mode & 0o777, 0o600)

    def test_replay_change_requires_explicit_acknowledgement(self):
        self.login()
        form = self.settings_form(EXVIUS_REPLAY_START="2016-07-07")
        code, body, _, _, _ = self.request("POST", "/settings", form)
        self.assertEqual(code, 422)
        self.assertIsNone(config_service.get(self.store, "phone"))
        form["confirm_timeline"] = "yes"
        code, _, _, _, _ = self.request("POST", "/settings", form)
        self.assertEqual(code, 303)

    def test_historical_period_is_shown_as_dates_not_week_number(self):
        self.login()
        code, body, _, _, _ = self.request()
        self.assertEqual(code, 200)
        self.assertIn('Datas que aparecem no jogo', body)
        self.assertIn('30/06 a 06/07/2016', body)
        self.assertIn('07/07 a 13/07/2016', body)
        self.assertNotIn('Semana histórica manual', body)
        self.assertIn('<option value="0" selected>30/06 a 06/07/2016</option>', body)
        self.assertIn('<option value="1">07/07 a 13/07/2016</option>', body)
        self.assertEqual(web.historical_period_label(web.date(2016, 12, 29), 0),
                         '29/12/2016 a 04/01/2017')

    def test_clarity_does_not_change_saved_protocol(self):
        self.login()
        status, body, _, _, _ = self.request()
        self.assertEqual(status, 200)
        for label in ("Como a cronologia avança", "Datas que aparecem no jogo",
                      "Velocidade do avanço automático", "Aplicação ainda não confirmada",
                      "Aparência dos destaques na Home", "Ganhar Trust após missões"):
            self.assertIn(label, body)
        self.assertIn('name="EXVIUS_REPLAY_MANUAL_WEEK"', body)
        self.assertIn('value="1">07/07 a 13/07/2016</option>', body)
        form = self.settings_form(EXVIUS_REPLAY_MANUAL_WEEK="1", confirm_timeline="yes")
        code, _, _, _, _ = self.request("POST", "/settings", form)
        self.assertEqual(code, 303)
        saved = config_service.get(self.store, "phone")["document"]["settings"]
        self.assertEqual(saved["EXVIUS_REPLAY_MANUAL_WEEK"], 1)
        self.assertEqual(saved["EXVIUS_REPLAY_MODE"], "manual")

    def test_date_period_follows_custom_historical_start(self):
        rendered = web.field_html(web.ALL_FIELDS['EXVIUS_REPLAY_MANUAL_WEEK'], {
            'EXVIUS_REPLAY_START': '2016-12-16', 'EXVIUS_REPLAY_MANUAL_WEEK': 1})
        self.assertIn('23/12 a 29/12/2016', rendered)
        self.assertIn('<option value="1" selected>', rendered)

    def test_manual_week_advance_with_default_mode_preserves_explicit_start(self):
        self.login()
        form = self.settings_form(EXVIUS_REPLAY_MANUAL_WEEK="1")
        form["confirm_timeline"] = "yes"
        code, _, _, _, _ = self.request("POST", "/settings", form)
        self.assertEqual(code, 303)
        stored = config_service.get(self.store, "phone")["document"]["settings"]
        self.assertEqual(stored["EXVIUS_REPLAY_MODE"], "manual")
        self.assertEqual(stored["EXVIUS_REPLAY_START"], "2016-06-30")
        self.assertEqual(stored["EXVIUS_REPLAY_MANUAL_WEEK"], 1)

    def test_switching_back_to_automatic_keeps_original_anchor_default(self):
        self.login()
        form = self.settings_form(EXVIUS_REPLAY_MODE="automatic")
        form["confirm_timeline"] = "yes"
        code, _, _, _, _ = self.request("POST", "/settings", form)
        self.assertEqual(code, 303)
        stored = config_service.get(self.store, "phone")["document"]["settings"]
        self.assertEqual(stored, {"EXVIUS_REPLAY_MODE": "automatic"})

    def test_manual_launch_settings_require_confirmation_and_store_revision(self):
        self.login()
        form = self.settings_form(EXVIUS_REPLAY_MODE="manual",
                                  EXVIUS_REPLAY_START="2016-06-30",
                                  EXVIUS_REPLAY_MANUAL_WEEK="1")
        code, _, _, _, _ = self.request("POST", "/settings", form)
        self.assertEqual(code, 422)
        self.assertIsNone(config_service.get(self.store, "phone"))
        form["confirm_timeline"] = "yes"
        code, _, _, dest, _ = self.request("POST", "/settings", form)
        self.assertEqual(code, 303)
        self.assertEqual(dest, "/?saved=1")
        saved = config_service.get(self.store, "phone")["document"]["settings"]
        self.assertEqual(saved["EXVIUS_REPLAY_MODE"], "manual")
        self.assertEqual(saved["EXVIUS_REPLAY_START"], "2016-06-30")
        self.assertEqual(saved["EXVIUS_REPLAY_MANUAL_WEEK"], 1)

    def test_optimistic_conflict_does_not_overwrite(self):
        self.login()
        first = config_model.validate_document({
            "schema": 1, "settings": {"EXVIUS_LAPIS_MULTIPLIER": 4}})
        code, _ = config_service.put(self.store, "phone",
                                     config_model.encode(first), "0")
        self.assertEqual(code, 201)
        code, body, _, _, _ = self.request(
            "POST", "/settings", self.settings_form(EXVIUS_LAPIS_MULTIPLIER="5"))
        self.assertEqual(code, 409)
        self.assertEqual(config_service.get(self.store, "phone")["document"], first)

    def test_invalid_numbers_rejected(self):
        self.login()
        form = self.settings_form(EXVIUS_LAPIS_MULTIPLIER="9999")
        code, _, _, _, _ = self.request("POST", "/settings", form)
        self.assertEqual(code, 422)

    def test_history_displays_no_private_values(self):
        self.login()
        first = config_model.validate_document({
            "schema": 1, "settings": {"EXVIUS_LAPIS_MULTIPLIER": 4}})
        second = config_model.validate_document({
            "schema": 1, "settings": {"EXVIUS_LAPIS_MULTIPLIER": 5}})
        code, result = config_service.put(self.store, "phone",
                                          config_model.encode(first), "0")
        code, _ = config_service.put(self.store, "phone",
                                     config_model.encode(second), result["revision"])
        status, body, _, _, _ = self.request()
        self.assertEqual(status, 200)
        self.assertIn(result["revision"][:12], body)

    def test_logout_invalidates_session(self):
        self.login()
        code, _, _, _, _ = self.request("POST", "/logout", {"csrf": self.csrf})
        self.assertEqual(code, 303)
        code, body, _, _, _ = self.request()
        self.assertIn("Senha do painel", body)

    def test_cannot_save_unknown_keys(self):
        self.login()
        form = self.settings_form()
        form["FFBE_DATA_DIR"] = "/tmp/poison"
        # Unknown form values are ignored, never become config keys.
        code, _, _, _, _ = self.request("POST", "/settings", form)
        self.assertEqual(code, 303)
        self.assertNotIn("FFBE_DATA_DIR", config_service.get(self.store, "phone")["document"]["settings"])


if __name__ == "__main__":
    unittest.main()
