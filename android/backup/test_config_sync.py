"""FFBE configuration model, LXC revision protocol and offline sync tests."""
from __future__ import annotations
import hashlib
import json
import os
import pathlib
import ssl
import sys
import tempfile
import unittest
from unittest import mock
from http.server import ThreadingHTTPServer
import threading
import urllib.request
import urllib.error

sys.path.insert(0, str(pathlib.Path(__file__).parent))
import config_model as model
import config_service as service
import config_sync as sync
import lxc_backup

def doc(**settings):
    return {"schema": 1, "settings": settings}

class ConfigModelTests(unittest.TestCase):
    def test_defaults_are_not_persisted_or_changed(self):
        with tempfile.TemporaryDirectory() as t:
            env = {"EXVIUS_REPLAY_START": "2016-12-16"}
            result = model.apply_on_boot(pathlib.Path(t)/"absent",
                                         pathlib.Path(t)/"replay.json", env)
            self.assertFalse(result["applied"])
            self.assertEqual(env["EXVIUS_REPLAY_START"], "2016-12-16")
            self.assertEqual(list(pathlib.Path(t).iterdir()), [])

    def test_roundtrip_revision_order_independent(self):
        left = doc(EXVIUS_REPLAY=True, EXVIUS_LAPIS_MULTIPLIER=5)
        right = doc(EXVIUS_LAPIS_MULTIPLIER=5, EXVIUS_REPLAY=True)
        self.assertEqual(model.revision(left), model.revision(right))
        self.assertEqual(model.parse(model.encode(left)), model.validate_document(right))

    def test_allows_start_and_dynamic_pace(self):
        self.assertIn("EXVIUS_REPLAY_PACE", model.validate_document(
            doc(EXVIUS_REPLAY_START="2016-06-30",
                EXVIUS_REPLAY_PACE="3,2@2020-08-20"))["settings"])

    def test_disallows_unknown_paths_and_secrets(self):
        for bad in ("FFBE_SERVER_ROOT", "FFBE_DATA_DIR", "STATE_FILE",
                    "TOKEN", "__class__", "EXVIUS_REPLAY_START;rm -rf /"):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                model.validate_document(doc(**{bad: "/tmp/hidden"}))

    def test_disallows_invalid_types_ranges_and_dates(self):
        invalid = [
            doc(EXVIUS_REPLAY=1),
            doc(EXVIUS_LAPIS_MULTIPLIER=True),
            doc(EXVIUS_LAPIS_MULTIPLIER=100),
            doc(EXVIUS_QUEST_TRUST_CHANCE=150),
            doc(EXVIUS_REPLAY_START="2016-06-29"),
            doc(EXVIUS_REPLAY_START="2020-02-30"),
            doc(EXVIUS_REPLAY_PACE="0,2@2020-08-20"),
            doc(EXVIUS_REPLAY_PACE="9"),
            doc(EXVIUS_REPLAY_PACE="2,5@2020-13-30"),
            doc(MARQUEE_FLAG=1),
            doc(EXVIUS_REPLAY="true"),
        ]
        for item in invalid:
            with self.subTest(item=item), self.assertRaises(ValueError):
                model.validate_document(item)

    def test_rejects_extra_fields_and_oversized(self):
        with self.assertRaises(ValueError):
            model.validate_document({"schema": 1, "settings": {}, "token": "a"})
        with self.assertRaises(ValueError):
            model.parse(b" " * (model.MAX_BYTES + 1))

    def test_private_permissions_and_symlink_blocking(self):
        with tempfile.TemporaryDirectory() as t:
            base = pathlib.Path(t)
            p = base/"private"/"config.json"
            model.write_private(p, doc(EXVIUS_REPLAY=True))
            self.assertEqual(p.stat().st_mode & 0o777, 0o600)
            self.assertEqual(p.parent.stat().st_mode & 0o777, 0o700)
            self.assertEqual(model.read_private(p)["settings"]["EXVIUS_REPLAY"], True)
            (base/"link").symlink_to(p)
            with self.assertRaises(ValueError):
                model.read_private(base/"link")
            p.chmod(0o644)
            with self.assertRaises(ValueError):
                model.read_private(p)

    def test_prevents_replay_anchor_rebase(self):
        with tempfile.TemporaryDirectory() as t:
            replay = pathlib.Path(t)/"replay.json"
            replay.write_text(json.dumps({"anchor_week": 123, "start": "2016-12-16"}))
            self.assertFalse(model.compatible_with_save(
                doc(EXVIUS_REPLAY_START="2016-06-30"), None, replay)[0])
            self.assertFalse(model.compatible_with_save(
                doc(EXVIUS_REPLAY_PACE="1"), None, replay)[0])
            self.assertTrue(model.compatible_with_save(
                doc(EXVIUS_REPLAY_START="2016-12-16"), None, replay)[0])

    def test_staged_config_applies_only_on_restart(self):
        with tempfile.TemporaryDirectory() as t:
            private = pathlib.Path(t)/"config"
            stage = private/"staged-config.json"
            model.write_private(stage, doc(EXVIUS_LAPIS_MULTIPLIER=3,
                                           EXVIUS_REPLAY_START="2016-06-30"))
            env={}
            result = model.apply_on_boot(private, pathlib.Path(t)/"no-replay.json", env)
            self.assertTrue(result["applied"])
            self.assertFalse(stage.exists())
            self.assertEqual(env["EXVIUS_LAPIS_MULTIPLIER"], "3")

    def test_staged_rebase_blocked_but_other_active_stays(self):
        with tempfile.TemporaryDirectory() as t:
            base=pathlib.Path(t)
            private=base/"config"
            replay=base/"replay.json"
            replay.write_text('{"anchor_week":1,"start":"2016-12-16"}')
            model.write_private(private/"server-config.json",doc(EXVIUS_LAPIS_MULTIPLIER=5))
            model.write_private(private/"staged-config.json",doc(EXVIUS_REPLAY_START="2016-06-30"))
            env={}
            result=model.apply_on_boot(private,replay,env)
            self.assertTrue(result["staged"])
            self.assertIn("explicit migration",result["reason"])
            self.assertEqual(env["EXVIUS_LAPIS_MULTIPLIER"],"5")
            self.assertTrue((private/"staged-config.json").is_file())

    def test_active_config_survives_offline(self):
        with tempfile.TemporaryDirectory() as t:
            private=pathlib.Path(t)
            model.write_private(private/"server-config.json",doc(EXVIUS_REPLAY_NOTICES=False))
            env={}
            result=model.apply_on_boot(private,private/"missing.json",env)
            self.assertTrue(result["applied"])
            self.assertEqual(env["EXVIUS_REPLAY_NOTICES"],"0")


class ConfigServerTests(unittest.TestCase):
    def test_cas_revisions_history_no_overwrite_on_conflict(self):
        with tempfile.TemporaryDirectory() as t:
            root=pathlib.Path(t)
            first=doc(EXVIUS_LAPIS_MULTIPLIER=3)
            second=doc(EXVIUS_LAPIS_MULTIPLIER=4)
            status,response=service.put(root,"phone",model.encode(first),"0")
            self.assertEqual(status,201)
            rev=response["revision"]
            self.assertEqual(service.get(root,"phone")["revision"],rev)
            conflict,_=service.put(root,"phone",model.encode(second),"0")
            self.assertEqual(conflict,409)
            self.assertEqual(service.get(root,"phone")["revision"],rev)
            ok,response=service.put(root,"phone",model.encode(second),rev)
            self.assertEqual(ok,201)
            history=root/"config-history"/"phone"/(rev+".json")
            self.assertEqual(model.read_private(history),first)
            self.assertEqual(history.stat().st_mode & 0o777,0o600)

    def test_requires_revision(self):
        with tempfile.TemporaryDirectory() as t:
            code,_=service.put(pathlib.Path(t),"phone",model.encode(doc()),"")
            self.assertEqual(code,428)

    def test_rejects_malicious_device_and_schema(self):
        with tempfile.TemporaryDirectory() as t:
            code,_=service.put(pathlib.Path(t),"../phone",model.encode(doc()),"0")
            self.assertEqual(code,400)
            code,_=service.put(pathlib.Path(t),"phone",b'{"schema":1,"settings":{"TOKEN":"abc"}}',"0")
            self.assertEqual(code,400)

    def test_unauthenticated_http_get_put(self):
        with tempfile.TemporaryDirectory() as t:
            root=pathlib.Path(t)
            server=ThreadingHTTPServer(("127.0.0.1",0),lxc_backup.make_handler(root,"t"*32))
            thread=threading.Thread(target=server.serve_forever,daemon=True)
            thread.start()
            url=f"http://127.0.0.1:{server.server_port}/v1/configs/phone"
            try:
                for method in ("GET","PUT"):
                    req=urllib.request.Request(url,method=method)
                    with self.assertRaises(urllib.error.HTTPError) as error:
                        urllib.request.urlopen(req,timeout=2)
                    self.assertEqual(error.exception.code,401)
            finally:
                server.shutdown();server.server_close();thread.join(2)

    def test_authorized_http_and_hash_and_cas(self):
        with tempfile.TemporaryDirectory() as t:
            root=pathlib.Path(t)
            token="t"*32
            server=ThreadingHTTPServer(("127.0.0.1",0),lxc_backup.make_handler(root,token))
            thread=threading.Thread(target=server.serve_forever,daemon=True)
            thread.start()
            url=f"http://127.0.0.1:{server.server_port}/v1/configs/phone"
            body=model.encode(doc(EXVIUS_REPLAY=True))
            try:
                request=urllib.request.Request(url,headers={"Authorization":"Bearer "+token})
                with self.assertRaises(urllib.error.HTTPError) as error:
                    urllib.request.urlopen(request,timeout=2)
                self.assertEqual(error.exception.code,404)
                request=urllib.request.Request(url,data=body,method="PUT",headers={
                    "Authorization":"Bearer "+token,"Content-Type":"application/json",
                    "If-Match":"0","X-Content-SHA256":hashlib.sha256(body).hexdigest()
                })
                with urllib.request.urlopen(request,timeout=2) as response:
                    self.assertEqual(response.status,201)
                    self.assertEqual(json.load(response)["revision"],model.revision(doc(EXVIUS_REPLAY=True)))
                with urllib.request.urlopen(urllib.request.Request(url,headers={
                    "Authorization":"Bearer "+token}),timeout=2) as response:
                    self.assertEqual(json.load(response)["document"],doc(EXVIUS_REPLAY=True))
            finally:
                server.shutdown();server.server_close();thread.join(2)


class ConfigSyncTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.root=pathlib.Path(self.temp.name)
        self.agent=sync.ConfigSync(self.root,lambda: ({"endpoint":"https://proxmox.tailcf6a16.ts.net:18447",
                                                       "token":"T"*48,"device":"phone"},
                                                      self.root/"ca.pem"))
    def tearDown(self):self.temp.cleanup()

    def test_not_paired_does_not_connect_or_create_files(self):
        agent=sync.ConfigSync(self.root,lambda:None)
        with mock.patch.object(sync,"_request") as request:
            self.assertFalse(agent.poll())
            request.assert_not_called()
        self.assertFalse(list(self.root.iterdir()))

    def test_remote_config_is_staged_not_applied_live(self):
        remote=doc(EXVIUS_REPLAY_START="2016-06-30")
        with mock.patch.object(sync,"_request",return_value=(200,{"revision":model.revision(remote),
                                                                 "document":remote})):
            self.assertTrue(self.agent.poll())
        self.assertFalse(self.agent.active.exists())
        self.assertEqual(model.read_private(self.agent.pending),remote)
        self.assertEqual(self.agent.status()["state"],"pending_restart")

    def test_divergent_updates_never_overwrite_remote(self):
        local=doc(EXVIUS_LAPIS_MULTIPLIER=2)
        remote=doc(EXVIUS_LAPIS_MULTIPLIER=5)
        model.write_private(self.agent.active,local)
        with mock.patch.object(sync,"_request",return_value=(200,{"revision":model.revision(remote),
                                                                 "document":remote})) as request:
            self.assertFalse(self.agent.poll())
            self.assertEqual(self.agent.status()["state"],"conflict")
            self.assertEqual(request.call_count,1)

    def test_offline_errors_are_nonfatal_and_redacted(self):
        with mock.patch.object(sync,"_request",side_effect=OSError("private token excluded")):
            self.assertFalse(self.agent.poll())
        self.assertEqual(self.agent.status()["last_error"],"OSError")
        self.assertNotIn("private token excluded",json.dumps(self.agent.status()))

if __name__=="__main__":
    unittest.main()
