"""Domain models and validation.

These dataclasses are the only structured representation of tools, bindings
and credentials that travels between the storage, registry and server layers.
Nothing in this module performs I/O.
"""
from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone

from .errors import ValidationError

_NAME_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")
_ENV_RE = re.compile(r"^[A-Z_][A-Z0-9_]*$")
_HEADER_RE = re.compile(r"^[A-Za-z0-9!#$%&'*+.^_`|~-]+$")


def utcnow() -> str:
    """Return an ISO-8601 UTC timestamp with seconds precision."""
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def validate_resource_name(name: str, *, what: str = "name") -> str:
    if not isinstance(name, str) or not _NAME_RE.match(name):
        raise ValidationError(
            f"Invalid {what} '{name}': use lowercase letters, digits, '-' or '_', "
            "starting with a letter or digit (max 64 chars)."
        )
    return name


def validate_base_url(url: str) -> str:
    if not isinstance(url, str) or not re.match(r"^https?://[^\s]+$", url):
        raise ValidationError(f"Invalid base_url '{url}': it must start with http:// or https://")
    return url.rstrip("/")


# ---------------------------------------------------------------- bindings
@dataclass
class Binding:
    """Injects one credential into an outgoing HTTP request."""

    credential: str
    location: str  # "header" | "query" | "basic_auth"
    name: str = ""  # header name / query param / basic-auth username
    template: str = "{value}"  # rendering template; {value} is replaced

    def validate(self) -> "Binding":
        validate_resource_name(self.credential, what="credential reference")
        if self.location not in {"header", "query", "basic_auth"}:
            raise ValidationError(f"Binding location must be header, query or basic_auth, got {self.location!r}")
        if self.location == "header":
            if not _HEADER_RE.match(self.name or ""):
                raise ValidationError(f"Invalid header name {self.name!r}")
        elif self.location == "query":
            if not self.name:
                raise ValidationError("Query binding requires a parameter name")
        elif self.location == "basic_auth":
            if not self.name:
                raise ValidationError("basic_auth binding requires a username in 'name'")
        if "{value}" not in self.template and self.location != "basic_auth":
            raise ValidationError("Binding template must contain the {value} placeholder")
        return self

    def render(self, secret: str) -> str:
        return self.template.replace("{value}", secret)


@dataclass
class EnvBinding:
    """Injects one credential into a CLI tool's environment."""

    env: str
    credential: str

    def validate(self) -> "EnvBinding":
        if not _ENV_RE.match(self.env or ""):
            raise ValidationError(f"Invalid environment variable name {self.env!r}")
        validate_resource_name(self.credential, what="credential reference")
        return self


@dataclass
class NamedArg:
    """A permitted named argument for a CLI tool, e.g. ``--format json``."""

    name: str
    flag: str
    repeatable: bool = False

    def validate(self) -> "NamedArg":
        validate_resource_name(self.name, what="argument name")
        if not self.flag.startswith("-"):
            raise ValidationError(f"Named argument flag must start with '-', got {self.flag!r}")
        return self


@dataclass
class ArgSchema:
    """Whitelist describing which arguments a CLI tool accepts."""

    named: list[NamedArg] = field(default_factory=list)
    free_args: bool = False
    free_args_flag: str = ""

    def validate(self) -> "ArgSchema":
        for arg in self.named:
            arg.validate()
        names = [a.name for a in self.named]
        if len(names) != len(set(names)):
            raise ValidationError("Duplicate named argument in CLI schema")
        if self.free_args_flag and not self.free_args_flag.startswith("-"):
            raise ValidationError("free_args_flag must start with '-'")
        return self


@dataclass
class EndpointConfig:
    base_url: str
    bindings: list[Binding] = field(default_factory=list)
    forward_query: bool = True

    def validate(self) -> "EndpointConfig":
        validate_base_url(self.base_url)
        for binding in self.bindings:
            binding.validate()
        return self


@dataclass
class CliConfig:
    argv: list[str] = field(default_factory=list)
    env: list[EnvBinding] = field(default_factory=list)
    arg_schema: ArgSchema = field(default_factory=ArgSchema)

    def validate(self) -> "CliConfig":
        if not self.argv or not all(isinstance(p, str) and p for p in self.argv):
            raise ValidationError("CLI tool requires a non-empty argv (e.g. ['mytool', '--flag'])")
        for binding in self.env:
            binding.validate()
        self.arg_schema.validate()
        return self


# -------------------------------------------------------------------- tool
@dataclass
class Tool:
    name: str
    kind: str  # "endpoint" | "cli"
    description: str = ""
    tags: list[str] = field(default_factory=list)
    enabled: bool = True
    endpoint: EndpointConfig | None = None
    cli: CliConfig | None = None
    created_at: str = field(default_factory=utcnow)
    updated_at: str = field(default_factory=utcnow)

    def validate(self) -> "Tool":
        validate_resource_name(self.name, what="tool name")
        if self.kind not in {"endpoint", "cli"}:
            raise ValidationError(f"Tool kind must be endpoint or cli, got {self.kind!r}")
        if self.kind == "endpoint":
            if self.endpoint is None:
                raise ValidationError("Endpoint tool requires endpoint configuration")
            self.endpoint.validate()
            self.cli = None
        else:
            if self.cli is None:
                raise ValidationError("CLI tool requires cli configuration")
            self.cli.validate()
            self.endpoint = None
        if not isinstance(self.tags, list) or not all(isinstance(t, str) for t in self.tags):
            raise ValidationError("tags must be a list of strings")
        return self

    # -- (de)serialisation of the kind-specific config -------------------
    def to_row(self) -> dict:
        if self.kind == "endpoint":
            config = asdict(self.endpoint)
        else:
            config = asdict(self.cli)
        return {
            "name": self.name,
            "kind": self.kind,
            "description": self.description,
            "tags": json.dumps(self.tags, ensure_ascii=False),
            "enabled": 1 if self.enabled else 0,
            "config": json.dumps(config, ensure_ascii=False),
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_row(cls, row: dict) -> "Tool":
        config = json.loads(row["config"])
        tags = json.loads(row.get("tags") or "[]")
        if row["kind"] == "endpoint":
            endpoint = EndpointConfig(
                base_url=config["base_url"],
                bindings=[Binding(**b) for b in config.get("bindings", [])],
                forward_query=config.get("forward_query", True),
            )
            cli = None
        else:
            cli = CliConfig(
                argv=config["argv"],
                env=[EnvBinding(**e) for e in config.get("env", [])],
                arg_schema=ArgSchema(
                    named=[NamedArg(**n) for n in config.get("arg_schema", {}).get("named", [])],
                    free_args=config.get("arg_schema", {}).get("free_args", False),
                    free_args_flag=config.get("arg_schema", {}).get("free_args_flag", ""),
                ),
            )
            endpoint = None
        return cls(
            name=row["name"],
            kind=row["kind"],
            description=row.get("description", ""),
            tags=tags,
            enabled=bool(row.get("enabled", 1)),
            endpoint=endpoint,
            cli=cli,
            created_at=row.get("created_at", utcnow()),
            updated_at=row.get("updated_at", utcnow()),
        )

    def public_dict(self) -> dict:
        """JSON-safe view exposed by the catalog API (never contains secrets)."""
        data = {
            "name": self.name,
            "kind": self.kind,
            "description": self.description,
            "tags": self.tags,
            "enabled": self.enabled,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }
        if self.kind == "endpoint":
            data["base_url"] = self.endpoint.base_url
            data["bindings"] = [
                {"credential": b.credential, "location": b.location, "name": b.name}
                for b in self.endpoint.bindings
            ]
        else:
            data["argv"] = self.cli.argv
            data["env"] = [{"env": e.env, "credential": e.credential} for e in self.cli.env]
            data["arg_schema"] = asdict(self.cli.arg_schema)
        return data


@dataclass
class Credential:
    name: str
    description: str = ""
    created_at: str = field(default_factory=utcnow)
    updated_at: str = field(default_factory=utcnow)


@dataclass
class GatewayToken:
    name: str
    scope: str  # "call" | "admin"
    token_hash: str
    prefix: str
    rate_limit: int = 0  # 0 = use server default
    enabled: bool = True
    id: int | None = None
    created_at: str = field(default_factory=utcnow)
    last_used_at: str | None = None

    def public_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "scope": self.scope,
            "prefix": self.prefix,
            "rate_limit": self.rate_limit,
            "enabled": self.enabled,
            "created_at": self.created_at,
            "last_used_at": self.last_used_at,
        }
