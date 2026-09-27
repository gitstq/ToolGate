import unittest

from toolgate.errors import ValidationError
from toolgate.models import (
    ArgSchema, Binding, CliConfig, EndpointConfig, NamedArg, Tool,
)


class ModelValidationTests(unittest.TestCase):
    def test_binding_locations(self):
        Binding("cred", "header", "X-Api-Key").validate()
        Binding("cred", "query", "api_key").validate()
        Binding("cred", "basic_auth", "alice").validate()
        with self.assertRaises(ValidationError):
            Binding("cred", "cookie", "x").validate()
        with self.assertRaises(ValidationError):
            Binding("cred", "header", "Bad Header").validate()
        with self.assertRaises(ValidationError):
            Binding("cred", "header", "X", template="no placeholder").validate()

    def test_render_template(self):
        b = Binding("cred", "header", "Authorization", "Token {value}")
        self.assertEqual(b.render("abc"), "Token abc")

    def test_endpoint_tool(self):
        tool = Tool(
            name="weather", kind="endpoint",
            endpoint=EndpointConfig("https://api.example.com/v1", [
                Binding("wk", "query", "key")
            ]),
        ).validate()
        row = tool.to_row()
        restored = Tool.from_row(row)
        self.assertEqual(restored.endpoint.base_url, "https://api.example.com/v1")

    def test_cli_tool(self):
        tool = Tool(
            name="echoer", kind="cli",
            cli=CliConfig(
                argv=["echo"],
                arg_schema=ArgSchema(named=[NamedArg("fmt", "--format")], free_args=True),
            ),
        ).validate()
        restored = Tool.from_row(tool.to_row())
        self.assertTrue(restored.cli.arg_schema.free_args)

    def test_bad_names(self):
        for bad in ("UPPER", "with space", "-abc", ".abc", "", "a/b"):
            with self.assertRaises(ValidationError):
                Tool(name=bad, kind="endpoint",
                     endpoint=EndpointConfig("https://x.com")).validate()

    def test_kind_config_required(self):
        with self.assertRaises(ValidationError):
            Tool(name="x", kind="endpoint").validate()
        with self.assertRaises(ValidationError):
            Tool(name="x", kind="cli").validate()

    def test_base_url_validation(self):
        with self.assertRaises(ValidationError):
            EndpointConfig("ftp://x.com").validate()


if __name__ == "__main__":
    unittest.main()
