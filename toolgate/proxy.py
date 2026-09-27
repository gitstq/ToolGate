"""Transparent reverse-proxy for endpoint tools.

The gateway *relays, it does not model*: the request method, path, query
string, body and (most) headers are forwarded untouched, while credentials
are injected server-side.  The upstream status code, headers and body are
returned verbatim.  Only the standard library is used.
"""
from __future__ import annotations

import base64
import http.client
import socket
from dataclasses import dataclass
from urllib.parse import urlsplit, urlencode

from .errors import UpstreamError
from .models import Binding

#: hop-by-hop headers that must not be forwarded (RFC 7230 §6.1) plus Host
HOP_BY_HOP = {
    "connection", "keep-alive", "proxy-authenticate", "proxy-authorization",
    "te", "trailers", "transfer-encoding", "upgrade", "host", "content-length",
}


@dataclass
class UpstreamResponse:
    status: int
    reason: str
    headers: list[tuple[str, str]]
    body: bytes

    def header_dict(self) -> dict[str, str]:
        # repeated headers collapse; last value wins (good enough for clients)
        result: dict[str, str] = {}
        for key, value in self.headers:
            if key.lower() not in HOP_BY_HOP:
                result[key] = value
        return result


def _build_url(tool, subpath: str, query: str, bindings: list[tuple[Binding, str]]) -> str:
    base = tool.endpoint.base_url
    parts = urlsplit(base)
    base_path = parts.path.rstrip("/")
    sub = (subpath or "").lstrip("/")
    path = "/".join([base_path, sub]) if sub else (base_path or "/")

    extra_query: list[tuple[str, str]] = []
    for binding, secret in bindings:
        if binding.location == "query":
            extra_query.append((binding.name, binding.render(secret)))
    if extra_query:
        merged = (query + "&" if query else "") + urlencode(extra_query)
    else:
        merged = query
    return f"{parts.scheme}://{parts.netloc}{path}" + (f"?{merged}" if merged else "")


def _build_headers(incoming: dict[str, str], bindings: list[tuple[Binding, str]]) -> dict[str, str]:
    headers: dict[str, str] = {}
    for key, value in incoming.items():
        if key.lower() not in HOP_BY_HOP:
            headers[key] = value
    for binding, secret in bindings:
        if binding.location == "header":
            headers[binding.name] = binding.render(secret)
        elif binding.location == "basic_auth":
            token = base64.b64encode(f"{binding.name}:{secret}".encode("utf-8")).decode("ascii")
            headers["Authorization"] = f"Basic {token}"
    return headers


def call_endpoint(
    tool,
    method: str,
    subpath: str,
    query: str,
    incoming_headers: dict[str, str],
    body: bytes,
    resolved: list[tuple[Binding, str]],
    timeout: float,
) -> UpstreamResponse:
    """Forward one HTTP request to the endpoint tool and return its response."""
    url = _build_url(tool, subpath, query if tool.endpoint.forward_query else "", resolved)
    headers = _build_headers(incoming_headers, resolved)
    parts = urlsplit(url)

    conn_cls = http.client.HTTPSConnection if parts.scheme == "https" else http.client.HTTPConnection
    conn = conn_cls(parts.hostname, parts.port, timeout=timeout)
    try:
        path = parts.path or "/"
        if parts.query:
            path += "?" + parts.query
        conn.request(method.upper(), path, body=body, headers=headers)
        response = conn.getresponse()
        data = response.read()
        return UpstreamResponse(
            status=response.status,
            reason=response.reason,
            headers=list(response.getheaders()),
            body=data,
        )
    except (socket.timeout, TimeoutError) as exc:
        raise UpstreamError(f"Upstream {tool.name} timed out after {timeout}s") from exc
    except (socket.gaierror, ConnectionError, OSError, http.client.HTTPException) as exc:
        raise UpstreamError(f"Unable to reach upstream {tool.name}: {exc}") from exc
    finally:
        conn.close()
