"""Strict one-time opt-in pairing, independent of the live Android save."""
from __future__ import annotations
import http.client
import json
import os
import tempfile
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

import history_pairing

CERT = '''-----BEGIN CERTIFICATE-----
MIIDBTCCAe2gAwIBAgIUX6H1Q/f6HGzdtSPSv5+L75mUABswDQYJKoZIhvcNAQEL
BQAwEjEQMA4GA1UEAwwHRkZCRS1DQTAeFw0yNjExMTcwMDAwMDBaFw0yNzExMTcw
MDAwMDBaMBIxEDAOBgNVBAMMB0ZGQkUtQ0EwggEiMA0GCSqGSIb3DQEBAQUAA4IB
DwAwggEKAoIBAQC9rmsoDFTWCNupVjsF3/vobPJu7aj/eE2BBvvHMmfDaOOIuHW5
6XrWk9X7COQc6LbjVJSyXJlNYxpDBPksx7sTvVvbpjhYzlhGpBMZ2Mm8FUn9f8U
CDMyUeHQW/sdQWJt4GhPkSTshd26YP0AIn5jVnmCrKf9eUEQOJAnS72tLQob
0tnydqwZBtaHXEfoIm0xQbbOmStQUPR77I8Sv95jvo4jzeZtENyZSzEl3VTy
SlaiPD04czzhgJsnbX3cKnWHTHzF/cMNbUmSXE88Sf28VTXg04nzXBqqvIP4Y
9ofbvkArEjsasKHObnS85mTp/9a2NnuL5AYUUbY8qx8PAgMBAAGjUzBRMB0G
A1UdDgQWBBSkGQ+ynKW7W/OdQa6hvCtsLAAC9TAfBgNVHSMEGDAWgBSkGQ+y
nKW7W/OdQa6hvCtsLAAC9TAPBgNVHRMBAf8EBTADAQH/MA0GCSqGSIb3DQEB
CwUAA4IBAQCRZeSpbcG+yOYY3OYCxIgoIRa4TudMJ5E0O7sqeWhXol0tXUEr
xPt9mcdyDrgKNGPccmBCbnQ9NL+pF2n7vASaNTVoXoQ4grRDQRjWHqwD4uk1J
OOr1L9f91A7jZXCG1u6QC+KOQH0Do2rt0L+E0WRMWqec22yXvGGNlXXIX4
Iw5shA6NTCxOgxKX5x6hV75UbbBrUi3ynqZWyo0cbsXzEzxoMMpMfMtYV/N6
CIMtaWOVtaEkbSrkACyWxiwxQkWpYp9JNeP/kZ9vqOxNEArFetaf0o99Qg2H
AuwqjuOoDcPmVEpEwXwY5JHbIeOjOdxRjvvHtwk4Cjql
-----END CERTIFICATE-----'''

class Base(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(204);self.end_headers()
    def do_POST(self):
        self.send_response(204);self.end_headers()
    def log_message(self,*args): pass

class PairingTests(unittest.TestCase):
    def sample(self, cert=CERT):
        return {'endpoint':history_pairing.ENDPOINT,'device':'samsung-android',
                'token':'x'*48,'ca_pem':cert}

    def test_rejects_without_code_and_does_not_write(self):
        with tempfile.TemporaryDirectory() as tmp:
            pair=history_pairing.Pairing(Path(tmp))
            with self.assertRaises(PermissionError):pair.pair(self.sample(),'incorrect')
            self.assertFalse(pair.paired())
            self.assertFalse((Path(tmp)/'exvius/settings/receiver-config.json').exists())

    def test_pair_is_one_time_and_writes_existing_bootstrap_format(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(history_pairing,'validate',return_value=('samsung-android','x'*48,b'test-CA')):
                pair=history_pairing.Pairing(Path(tmp))
                pair.pair(self.sample(),pair.challenge)
            self.assertTrue(pair.paired())
            root=Path(tmp)/'exvius/settings'
            self.assertFalse((Path(tmp)/'exvius/backup/config.json').exists())
            config=json.loads((root/'receiver-config.json').read_text())
            self.assertEqual(set(config),{'enabled','url','device','token_file','ca_file'})
            self.assertEqual(config['url'],history_pairing.ENDPOINT)
            self.assertEqual(Path(config['token_file']).read_text(),'x'*48)
            self.assertEqual(Path(config['ca_file']).read_bytes(),b'test-CA')
            for path in (root,root/'receiver-config.json',root/'receiver-ca.pem',root/'receiver-token.txt'):
                self.assertEqual(path.stat().st_mode & 0o077,0)
            with self.assertRaises(PermissionError):pair.pair(self.sample(),pair.challenge)

    def test_rejects_incorrect_endpoint_or_device(self):
        sample=self.sample()
        sample['endpoint']='https://evil.invalid:18447'
        with self.assertRaises(ValueError):history_pairing.validate(sample)
        sample=self.sample();sample['device']='../../etc'
        with self.assertRaises(ValueError):history_pairing.validate(sample)

    def test_phone_browser_page_and_code_exchange_without_adb(self):
        from unittest.mock import patch
        from urllib.parse import urlencode
        with tempfile.TemporaryDirectory() as tmp:
            pair=history_pairing.Pairing(Path(tmp))
            handler=history_pairing.wrap_handler(Base,pair,None)
            server=ThreadingHTTPServer(('127.0.0.1',0),handler)
            threading.Thread(target=server.serve_forever,daemon=True).start()
            conn=http.client.HTTPConnection(*server.server_address,timeout=3)
            try:
                conn.request('GET',history_pairing.CONNECT)
                response=conn.getresponse();body=response.read().decode('utf-8')
                self.assertEqual(response.status,200)
                self.assertIn('Conectar ao Web Helper',body)
                self.assertNotIn(pair.challenge,body)
                with patch.object(pair,'claim_via_phone') as claim:
                    conn.request('POST',history_pairing.CONNECT,
                        body=urlencode({'code':'A'*24}),headers={
                        'Content-Type':'application/x-www-form-urlencoded',
                        'Origin':'http://127.0.0.1:18080'})
                    response=conn.getresponse();body=response.read().decode('utf-8')
                    self.assertEqual(response.status,200)
                    claim.assert_called_once_with('A'*24)
                    self.assertIn('Conexão autorizada',body)
                conn.request('POST',history_pairing.CONNECT,
                    body=urlencode({'code':'A'*24}),headers={
                    'Content-Type':'application/x-www-form-urlencoded',
                    'Origin':'https://malicious.example'})
                response=conn.getresponse();body=response.read().decode('utf-8')
                self.assertNotIn('Conexão autorizada',body)
            finally:
                conn.close();server.shutdown();server.server_close()

    def test_remote_claim_uses_https_and_private_credentials(self):
        from unittest.mock import patch
        from io import BytesIO
        with tempfile.TemporaryDirectory() as tmp:
            pair=history_pairing.Pairing(Path(tmp))
            cert='-----BEGIN CERTIFICATE-----\nFAKE\n-----END CERTIFICATE-----'
            response=json.dumps(self.sample(cert)).encode('utf-8')
            class FakeResponse:
                status=200
                def __enter__(self):return self
                def __exit__(self,*args):pass
                def read(self,size):return response
            class FakeOpener:
                def open(self,request,timeout):
                    self_request=request
                    assert self_request.full_url==history_pairing.CLAIM_URL
                    assert json.loads(self_request.data)['code']=='A'*24
                    assert timeout==12
                    return FakeResponse()
            with patch.object(history_pairing.urllib.request,'build_opener',return_value=FakeOpener()),\
                 patch.object(history_pairing,'validate',return_value=('samsung-android','x'*48,b'CA')):
                pair.claim_via_phone('A'*24)
            self.assertTrue(pair.paired())
            self.assertEqual((Path(tmp)/'exvius/settings/receiver-token.txt').read_text(),'x'*48)

    def test_loopback_routes_do_not_interfere_with_game(self):
        with tempfile.TemporaryDirectory() as tmp:
            pair=history_pairing.Pairing(Path(tmp))
            handler=history_pairing.wrap_handler(Base,pair,None)
            server=ThreadingHTTPServer(('127.0.0.1',0),handler)
            threading.Thread(target=server.serve_forever,daemon=True).start()
            conn=http.client.HTTPConnection(*server.server_address,timeout=3)
            try:
                conn.request('GET','/game');self.assertEqual(conn.getresponse().status,204)
                conn.request('GET',history_pairing.STATUS)
                status=conn.getresponse();self.assertEqual(status.status,200)
                self.assertFalse(json.loads(status.read())['paired'])
                conn.request('POST',history_pairing.PAIR,body=json.dumps(self.sample()),
                             headers={'Content-Type':'application/json','X-FFBE-Pair-Code':'wrong'})
                status=conn.getresponse();self.assertEqual(status.status,403)
                self.assertNotIn('x'*48,status.read().decode())
                conn.request('POST','/game',body='{}');self.assertEqual(conn.getresponse().status,204)
            finally:
                conn.close();server.shutdown();server.server_close()

if __name__=='__main__':unittest.main()
