import json
import sys
import threading
import unittest
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, HTTPServer

from toolgate.crypto import generate_token, hash_token
from toolgate.models import GatewayToken

from tests._util import make_config, start_server


class PingUpstream(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _handle(self):
        length = int(self.headers.get("Content-Length", 0) or 0)
        body = self.rfile.read(length) if length else b""
        payload = json.dumps({
            "path": self.path,
            "x_api_key": self.headers.get("X-Api-Key"),
            "body": body.decode(),
        }).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    do_GET = _handle
    do_POST = _handle


def http_request(base, path, token=None, method="GET", body=None):
    data = json.dumps(body).encode() if body is not None else None
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(base + path, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req) as resp:
            raw = resp.read()
            return resp.status, json.loads(raw) if raw else {}
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read())


class ServerEndToEndTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # upstream
        cls.upstream = HTTPServer(("127.0.0.1", 0), PingUpstream)
        cls.up_port = cls.upstream.server_address[1]
        cls.up_thread = threading.Thread(target=cls.upstream.serve_forever, daemon=True)
        cls.up_thread.start()
        # gateway
        cls.server, cls.base = start_server(make_config())
        # bootstrap an admin token directly in storage
        cls.admin = generate_token()
        cls.server.storage.create_token(GatewayToken(
            name="admin", scope="admin", token_hash=hash_token(cls.admin),
            prefix=cls.admin[:8]))

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.server.storage.close()
        cls.upstream.shutdown()
        cls.upstream.server_close()

    def test_01_health_and_auth(self):
        status, data = http_request(self.base, "/healthz")
        self.assertEqual(status, 200)
        self.assertEqual(data["status"], "ok")
        status, _ = http_request(self.base, "/v1/tools")
        self.assertEqual(status, 401)
        status, _ = http_request(self.base, "/v1/tools", token="garbage")
        self.assertEqual(status, 401)

    def test_02_admin_bootstrap(self):
        status, _ = http_request(self.base, "/v1/admin/credentials", self.admin, "POST",
                                 {"name": "c", "secret": "SECRET", "description": "d"})
        self.assertEqual(status, 201)
        status, _ = http_request(self.base, "/v1/admin/credentials", self.admin, "POST",
                                 {"name": "c", "secret": "SECRET"})
        self.assertEqual(status, 409)

        tool = {
            "name": "upapi", "kind": "endpoint", "description": "upstream api",
            "endpoint": {
                "base_url": f"http://127.0.0.1:{self.up_port}",
                "bindings": [
                    {"credential": "c", "location": "header", "name": "X-Api-Key"}
                ],
            },
        }
        status, _ = http_request(self.base, "/v1/admin/tools", self.admin, "POST", tool)
        self.assertEqual(status, 201)

        cli_tool = {
            "name": "probe", "kind": "cli",
            "cli": {
                "argv": [sys.executable, "-c",
                         "import os;print('TG='+os.environ.get('TG',''))"],
                "env": [{"env": "TG", "credential": "c"}],
                "arg_schema": {"named": [], "free_args": False},
            },
        }
        status, _ = http_request(self.base, "/v1/admin/tools", self.admin, "POST", cli_tool)
        self.assertEqual(status, 201)

    def test_03_create_call_token(self):
        status, data = http_request(self.base, "/v1/admin/tokens", self.admin, "POST",
                                    {"name": "caller", "scope": "call"})
        self.assertEqual(status, 201)
        self.__class__.caller = data["token"]
        # duplicate name conflicts
        status, _ = http_request(self.base, "/v1/admin/tokens", self.admin, "POST",
                                 {"name": "caller", "scope": "call"})
        self.assertEqual(status, 409)

    def test_04_call_scope(self):
        status, data = http_request(self.base, "/v1/tools", self.caller)
        self.assertEqual(status, 200)
        self.assertEqual(data["count"], 2)
        # call token cannot reach admin
        status, _ = http_request(self.base, "/v1/admin/stats", self.caller)
        self.assertEqual(status, 403)

    def test_05_unified_call_endpoint(self):
        status, data = http_request(self.base, "/v1/call/upapi", self.caller, "POST",
                                    {"method": "POST", "path": "ping",
                                     "body": {"hello": "world"}})
        self.assertEqual(status, 200)
        self.assertEqual(data["status"], 200)
        body = json.loads(data["body"])
        self.assertEqual(body["x_api_key"], "SECRET")
        self.assertEqual(body["body"], json.dumps({"hello": "world"}))

    def test_06_transparent_proxy(self):
        status, data = http_request(self.base, "/v1/tool/upapi/ping?x=1", self.caller)
        self.assertEqual(status, 200)
        self.assertEqual(data["x_api_key"], "SECRET")
        self.assertEqual(data["path"], "/ping?x=1")

    def test_07_call_cli(self):
        status, data = http_request(self.base, "/v1/call/probe", self.caller, "POST", {})
        self.assertEqual(status, 200)
        self.assertEqual(data["exit_code"], 0)
        self.assertIn("TG=SECRET", data["stdout"])

    def test_08_search_and_audit(self):
        status, data = http_request(self.base, "/v1/search?q=upstream", self.caller)
        self.assertEqual(status, 200)
        self.assertTrue(any(h["name"] == "upapi" for h in data["hits"]))
        status, data = http_request(self.base, "/v1/admin/audit?limit=5", self.admin)
        self.assertEqual(status, 200)
        self.assertGreaterEqual(data["count"], 1)


class RateLimitTests(unittest.TestCase):
    def test_rate_limit_returns_429(self):
        server, base = start_server(make_config(rate_limit_per_minute=3))
        try:
            token = generate_token()
            server.storage.create_token(GatewayToken(
                name="limited", scope="call", token_hash=hash_token(token),
                prefix=token[:8]))
            codes = [http_request(base, "/v1/tools", token)[0] for _ in range(6)]
            self.assertIn(429, codes)
        finally:
            server.shutdown()
            server.server_close()
            server.storage.close()


if __name__ == "__main__":
    unittest.main()
