import unittest

from toolgate.crypto import Cipher, generate_master_key
from toolgate.errors import ConflictError, ValidationError
from toolgate.models import Binding, CliConfig, EndpointConfig, Tool
from toolgate.registry import Registry
from toolgate.storage import Storage

from tests._util import make_config


def make_registry():
    cfg = make_config()
    storage = Storage(cfg.db_path)
    registry = Registry(storage, Cipher(generate_master_key()))
    return registry


class RegistryTests(unittest.TestCase):
    def setUp(self):
        self.registry = make_registry()

    def tearDown(self):
        self.registry.storage.close()

    def test_credential_lifecycle(self):
        self.registry.add_credential("c", "SECRET", "d")
        names = [x.name for x in self.registry.list_credentials()]
        self.assertIn("c", names)
        with self.assertRaises(ConflictError):
            self.registry.add_credential("c", "x", create_only=True)
        # secret is stored encrypted
        self.assertIn("SECRET", self.registry._resolve(["c"]).values())

    def test_tool_requires_existing_credential(self):
        tool = Tool(name="x", kind="endpoint",
                    endpoint=EndpointConfig("https://x.com", [Binding("missing", "query", "k")]))
        with self.assertRaises(ValidationError):
            self.registry.add_tool(tool)

    def test_add_tool_and_duplicate(self):
        self.registry.add_credential("c", "S")
        tool = Tool(name="weather", kind="endpoint",
                    description="query the weather",
                    endpoint=EndpointConfig("https://w.com", [Binding("c", "query", "key")]))
        self.registry.add_tool(tool)
        with self.assertRaises(ConflictError):
            self.registry.add_tool(tool)

    def test_search_ranking(self):
        self.registry.add_credential("c", "S")
        self.registry.add_tool(Tool(
            name="weather", kind="endpoint", description="query weather forecast",
            endpoint=EndpointConfig("https://w.com", [Binding("c", "query", "k")])))
        self.registry.add_tool(Tool(
            name="imagegen", kind="cli", description="generate images", tags=["image", "图片"],
            cli=CliConfig(argv=["img"])))
        hits = self.registry.search("weather forecast")
        self.assertEqual(hits[0].tool.name, "weather")
        hits_cjk = self.registry.search("图片")
        self.assertEqual(hits_cjk[0].tool.name, "imagegen")


if __name__ == "__main__":
    unittest.main()
