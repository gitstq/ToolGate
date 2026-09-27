import json
import sys
import tempfile
import unittest
from pathlib import Path

from toolgate.errors import ToolExecutionError, ValidationError
from toolgate.models import ArgSchema, CliConfig, EnvBinding, NamedArg, Tool
from toolgate.runner import build_argv, run_cli

SCRIPT = (
    "import sys,os,json;"
    "print(json.dumps({'argv':sys.argv[1:],'TGTEST':os.environ.get('TGTEST')}))"
)


def make_tool(**schema):
    return Tool(name="probe", kind="cli", cli=CliConfig(
        argv=[sys.executable, "-c", SCRIPT],
        env=[EnvBinding("c", "TGTEST")],
        arg_schema=ArgSchema(**schema),
    ))


class RunnerTests(unittest.TestCase):
    def test_named_arg_and_env_injection(self):
        tool = make_tool(named=[NamedArg("fmt", "--format")])
        result = run_cli(tool, params={"fmt": "json"}, env_secrets={"TGTEST": "S3"}, timeout=10)
        self.assertEqual(result.exit_code, 0)
        data = json.loads(result.stdout)
        self.assertEqual(data["argv"], ["--format", "json"])
        self.assertEqual(data["TGTEST"], "S3")

    def test_unknown_param_rejected(self):
        tool = make_tool(named=[NamedArg("fmt", "--format")])
        with self.assertRaises(ValidationError):
            build_argv(tool, {"bogus": "1"}, [])

    def test_free_args_rejected_then_allowed(self):
        tool = make_tool(free_args=False)
        with self.assertRaises(ValidationError):
            build_argv(tool, {}, ["x"])
        tool2 = make_tool(free_args=True, free_args_flag="--")
        argv = build_argv(tool2, {}, ["a", "b"])
        self.assertEqual(argv[-3:], ["--", "a", "b"])

    def test_repeatable(self):
        tool = make_tool(named=[NamedArg("tag", "--tag", repeatable=True)])
        argv = build_argv(tool, {"tag": ["x", "y"]}, [])
        self.assertEqual(argv[-4:], ["--tag", "x", "--tag", "y"])

    def test_timeout(self):
        tool = Tool(name="slow", kind="cli",
                    cli=CliConfig(argv=[sys.executable, "-c", "import time;time.sleep(2)"]))
        with self.assertRaises(ToolExecutionError):
            run_cli(tool, timeout=0.5)

    def test_missing_executable(self):
        tool = Tool(name="nope", kind="cli",
                    cli=CliConfig(argv=["definitely-no-such-binary-xyz"]))
        with self.assertRaises(ToolExecutionError):
            run_cli(tool, timeout=5)


if __name__ == "__main__":
    unittest.main()
