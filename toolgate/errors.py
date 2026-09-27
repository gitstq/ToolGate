"""Exception hierarchy for ToolGate.

All ToolGate-specific errors inherit from :class:`ToolGateError` so callers
can catch the whole family with a single ``except`` clause.
"""
from __future__ import annotations


class ToolGateError(Exception):
    """Base class for every ToolGate error."""

    #: machine-readable error code, rendered in JSON responses
    code: str = "error"
    #: suggested HTTP status code when raised inside the HTTP server
    http_status: int = 400

    def __init__(self, message: str = "", *, code: str | None = None, http_status: int | None = None):
        super().__init__(message or self.__class__.__doc__)
        self.message = message or self.__class__.__doc__
        if code is not None:
            self.code = code
        if http_status is not None:
            self.http_status = http_status

    def to_dict(self) -> dict:
        return {"error": self.code, "message": self.message}


class ConfigError(ToolGateError):
    """Configuration is missing or invalid."""

    code = "config_error"
    http_status = 500


class CryptoError(ToolGateError):
    """Encryption / decryption failed."""

    code = "crypto_error"
    http_status = 500


class NotFoundError(ToolGateError):
    """The requested resource does not exist."""

    code = "not_found"
    http_status = 404


class ConflictError(ToolGateError):
    """The request conflicts with the current state (e.g. duplicate name)."""

    code = "conflict"
    http_status = 409


class ValidationError(ToolGateError):
    """The submitted payload failed validation."""

    code = "validation_error"
    http_status = 422


class AuthError(ToolGateError):
    """Authentication failed or the token is missing."""

    code = "unauthorized"
    http_status = 401


class PermissionError(ToolGateError):  # noqa: A001 - intentional shadow for API clarity
    """The authenticated token is not allowed to perform this action."""

    code = "forbidden"
    http_status = 403


class RateLimitError(ToolGateError):
    """The caller exceeded its rate limit."""

    code = "rate_limited"
    http_status = 429


class UpstreamError(ToolGateError):
    """The upstream tool returned an error or could not be reached."""

    code = "upstream_error"
    http_status = 502


class ToolExecutionError(ToolGateError):
    """The command-line tool exited unsuccessfully or timed out."""

    code = "tool_execution_error"
    http_status = 502
