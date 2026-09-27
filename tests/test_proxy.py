import json
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer

from toolgate.errors import UpstreamError
from toolgate.models import Binding, EndpointConfig, Tool
from toolgate.proxy import call_endpoint


class EchoUpstream(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def _handle(self):
        length = int(self.headers.get("Content-Length", 0) or 0)
        body = self.rfile.read(length) if length else b""
        payload = json.dumps({
            "method": self.command,
            "path": self.path,
            "authorization": self.headers.get("Authorization"),
            "x_api_key": self.headers.get("X-Api-Key"),
            "body": body.decode("utf-8"),
        }).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    do_GET = _handle
    do_POST = _handle
    do_PUT = _handle


class ProxyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.upstream = HTTPServer(("127.0.0.1", 0), EchoUpstream)
        cls.port = cls.upstream.server_address[1]
        cls.thread = threading.Thread(target=cls.upstream.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.upstream.shutdown()
        cls.upstream.server_close()

    def _tool(self, *bindings):
        return Tool(name="up", kind="endpoint", endpoint=EndpointConfig(
            base_url=f"http://127.0.0.1:{self.port}",
            bindings=list(bindings)))

    def test_header_query_basic_injection_and_passthrough(self):
        tool = self._tool(
            Binding("c", "header", "X-Api-Key"),
            Binding("c", "query", "key"),
            Binding("c", "basic_auth", "alice"),
        )
        resolved = [(b, "SECRET") for b in tool.endpoint.bindings]
        response = call_endpoint(
            tool, "POST", "items", "verbose=true",
            {"X-Custom": "yes", "Content-Type": "application/json"},
            b'{"q":1}', resolved, 10,
        )
        self.assertEqual(response.status, 200)
        data = json.loads(response.body)
        self.assertEqual(data["method"], "POST")
        self.assertTrue(data["path"].startswith("/items?"))
        self.assertIn("verbose=true", data["path"])
        self.assertIn("key=SECRET", data["path"])
        self.assertEqual(data["x_api_key"], "SECRET")
        self.assertEqual(data["authorization"], "Basic " + __import__("base64").b64encode(
            b"alice:SECRET").decode())
        self.assertEqual(data["body"], '{"q":1}')

    def test_bearer_template(self):
        tool = self._tool(Binding("c", "header", "Authorization", "Bearer {value}"))
        resolved = [(tool.endpoint.bindings[0], "TOK")]
        response = call_endpoint(tool, "GET", "", "", {}, b"", resolved, 10)
        data = json.loads(response.body)
        self.assertEqual(data["authorization"], "Bearer TOK")

    def test_unreachable_upstream(self):
        tool = Tool(name="dead", kind="endpoint",
                    endpoint=EndpointConfig("http://127.0.0.1:9"))
        with self.assertRaises(UpstreamError):
            call_endpoint(tool, "GET", "", "", {}, b"", [], 2)


if __name__ == "__main__":
    unittest.main()
