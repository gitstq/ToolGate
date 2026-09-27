"""Tool catalog, credential resolution and search.

The registry is the facade the rest of the application uses for:

* CRUD on tools and credentials (credentials are encrypted here)
* resolving the plaintext secrets referenced by a tool's bindings
* a small dependency-free TF-IDF search over the tool catalog
"""
from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass

from .crypto import Cipher
from .errors import NotFoundError, ValidationError
from .models import Binding, Credential, Tool
from .storage import Storage

_TOKEN_RE = re.compile(r"[a-z0-9]+|[一-鿿]")


def tokenize(text: str) -> list[str]:
    """Lowercase, split on word boundaries and treat each CJK ideograph as a token."""
    return _TOKEN_RE.findall((text or "").lower())


@dataclass
class SearchHit:
    tool: Tool
    score: float

    def public_dict(self) -> dict:
        data = self.tool.public_dict()
        data["score"] = round(self.score, 4)
        return data


class Registry:
    def __init__(self, storage: Storage, cipher: Cipher):
        self.storage = storage
        self.cipher = cipher

    # ------------------------------------------------------------ credentials
    def add_credential(self, name: str, secret: str, description: str = "", *, create_only: bool = False) -> Credential:
        if not isinstance(secret, str) or secret == "":
            raise ValidationError("Credential secret must be a non-empty string")
        ciphertext = self.cipher.encrypt(secret)
        return self.storage.put_credential(name, ciphertext, description, create_only=create_only)

    def update_credential_secret(self, name: str, secret: str) -> Credential:
        # ensures it exists
        self.require_credential(name)
        creds = {c.name: c for c in self.storage.list_credentials()}
        meta = creds[name]
        ciphertext = self.cipher.encrypt(secret)
        return self.storage.put_credential(name, ciphertext, meta.description)

    def list_credentials(self) -> list[Credential]:
        return self.storage.list_credentials()

    def require_credential(self, name: str) -> Credential:
        for cred in self.storage.list_credentials():
            if cred.name == name:
                return cred
        raise NotFoundError(f"Credential '{name}' does not exist")

    def delete_credential(self, name: str) -> None:
        self.storage.delete_credential(name)

    def _resolve(self, names: list[str]) -> dict[str, str]:
        """Return ``{credential_name: plaintext}`` for the given names."""
        result: dict[str, str] = {}
        for name in names:
            if name in result:
                continue
            ciphertext = self.storage.get_ciphertext(name)  # raises NotFoundError if missing
            result[name] = self.cipher.decrypt(ciphertext)
        return result

    # ------------------------------------------------------------------ tools
    def add_tool(self, tool: Tool) -> Tool:
        tool.validate()
        self._check_bindings_exist(tool)
        return self.storage.put_tool(tool, create_only=True)

    def update_tool(self, tool: Tool) -> Tool:
        self.storage.get_tool(tool.name)  # must exist
        tool.validate()
        self._check_bindings_exist(tool)
        return self.storage.put_tool(tool)

    def get_tool(self, name: str) -> Tool:
        return self.storage.get_tool(name)

    def list_tools(self, **kwargs) -> list[Tool]:
        return self.storage.list_tools(**kwargs)

    def delete_tool(self, name: str) -> None:
        self.storage.delete_tool(name)

    def set_tool_enabled(self, name: str, enabled: bool) -> None:
        self.storage.set_tool_enabled(name, enabled)

    def _check_bindings_exist(self, tool: Tool) -> None:
        if tool.kind == "endpoint":
            refs = sorted({b.credential for b in tool.endpoint.bindings})
        else:
            refs = sorted({e.credential for e in tool.cli.env})
        available = {c.name for c in self.storage.list_credentials()}
        missing = [r for r in refs if r not in available]
        if missing:
            raise ValidationError(
                "Tool references credentials that do not exist: " + ", ".join(missing) +
                ". Create them first with `toolgate creds set`."
            )

    # ------------------------------------------------------- secret injection
    def endpoint_bindings(self, tool: Tool) -> list[tuple[Binding, str]]:
        """Return resolved ``(binding, secret)`` pairs for an endpoint tool."""
        refs = [b.credential for b in tool.endpoint.bindings]
        secrets = self._resolve(refs)
        return [(b, secrets[b.credential]) for b in tool.endpoint.bindings]

    def cli_env(self, tool: Tool) -> dict[str, str]:
        """Return ``{ENV_VAR: secret}`` for a CLI tool."""
        refs = [e.credential for e in tool.cli.env]
        secrets = self._resolve(refs)
        return {e.env: secrets[e.credential] for e in tool.cli.env}

    # ----------------------------------------------------------------- search
    def search(self, query: str, *, kind: str | None = None, limit: int = 10) -> list[SearchHit]:
        tools = self.list_tools(kind=kind, include_disabled=False)
        if not tools:
            return []
        docs = [
            (t, tokenize(" ".join([t.name, t.description, " ".join(t.tags)])))
            for t in tools
        ]
        # document frequencies
        df: Counter[str] = Counter()
        for _, tokens in docs:
            df.update(set(tokens))
        n_docs = len(docs)
        idf = {tok: math.log(1 + (n_docs - df[tok] + 0.5) / (df[tok] + 0.5)) for tok in df}

        q_tokens = tokenize(query)
        if not q_tokens:
            return [SearchHit(t, 0.0) for t in tools[:limit]]
        q_counts = Counter(q_tokens)

        scored: list[SearchHit] = []
        for tool, tokens in docs:
            tf = Counter(tokens)
            doc_norm = 0.0
            score = 0.0
            for tok, count in tf.items():
                weight = (1 + math.log(count)) * idf.get(tok, 0.0)
                doc_norm += weight * weight
            for tok, qcount in q_counts.items():
                if tok in tf:
                    dw = (1 + math.log(tf[tok])) * idf.get(tok, 0.0)
                    qw = (1 + math.log(qcount)) * idf.get(tok, 0.0)
                    score += dw * qw
                    # exact name match is a strong relevance signal
                    if tok in tokenize(tool.name):
                        score += 1.5
            if doc_norm:
                score /= math.sqrt(doc_norm)
            if score > 0:
                scored.append(SearchHit(tool, score))
        scored.sort(key=lambda h: h.score, reverse=True)
        return scored[:limit]
