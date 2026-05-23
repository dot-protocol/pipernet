# SPDX-License-Identifier: Apache-2.0
# Part of oracle-axxis — https://github.com/dot-protocol/oracle-sdk-py

"""oracle_axxis.client — sync (Oracle) and async (AsyncOracle) clients.

Mem0-parity surface: ``add()`` / ``search()`` plus an Oracle-specific dialog
primitive (``ask()``) and graph neighbourhood (``connections()``). Auth is
either bearer (full write surface via ``add()``) or signed-request keypair
(write surface restricted to dotpost/icontact per signed-request-v0.1).
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Iterator, Literal
from urllib.parse import urlencode

import httpx
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from .errors import (
    AuthError,
    IngestError,
    NotFoundError,
    OracleError,
    RateLimitError,
)
from .signing import Keypair, sign_request
from .types import (
    AskResponse,
    Capabilities,
    Citation,
    ConnectionGraph,
    Observation,
    SearchResult,
    SelfInfo,
)

DEFAULT_BASE_URL = "https://oracle.axxis.world"
DEFAULT_TIMEOUT = 120.0  # /ask + /p/ask can take 30-60s on CPU Ollama

AuthMode = Literal["bearer", "signed", "open"]


def _resolve_base_url(base_url: str | None) -> str:
    return (base_url or os.environ.get("ORACLE_BASE_URL") or DEFAULT_BASE_URL).rstrip(
        "/"
    )


def _resolve_bearer(api_key: str | None) -> str | None:
    return (
        api_key
        or os.environ.get("ORACLE_TOKEN")
        or os.environ.get("TREE_AUTH_TOKEN")
    )


def _retry_decorator():
    """Tenacity policy: 3 attempts, exp backoff, retry on conn + 5xx only."""
    return retry(
        reraise=True,
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=4),
        retry=retry_if_exception_type(
            (httpx.ConnectError, httpx.ReadTimeout, httpx.RemoteProtocolError)
        ),
    )


def _raise_for_status(response: httpx.Response) -> None:
    """Translate HTTP status into oracle_axxis exceptions."""
    sc = response.status_code
    if sc < 400:
        return

    try:
        body = response.json()
        message = body.get("error") or body.get("message") or response.text
    except Exception:
        body = {}
        message = response.text or f"HTTP {sc}"

    if sc == 401:
        raise AuthError(f"authentication failed: {message}", status_code=sc)
    if sc == 404:
        raise NotFoundError(str(message))
    if sc == 429:
        retry_after = body.get("retry_after_s") if isinstance(body, dict) else None
        raise RateLimitError(
            f"rate limited: {message}",
            retry_after_s=retry_after,
        )
    if 400 <= sc < 500:
        raise IngestError(f"client error {sc}: {message}", status_code=sc)
    raise OracleError(f"server error {sc}: {message}", status_code=sc)


def _dotpost_tags(*, to: str, channel: str, reply_to: str | None) -> list[str]:
    tags = [f"to:{to}", "dotpost", f"channel:{channel}"]
    if reply_to:
        tags.append(f"in_reply_to:{reply_to}")
    return tags


def _ingest_payload(
    *,
    body: str,
    obs_type: str,
    channel: str,
    tags: list[str],
    source: str | None,
) -> dict[str, Any]:
    """Shape the request body for /ingest and /p/ingest."""
    return {
        "source": source or "oracle-axxis-sdk",
        "extracted": {
            "items": [
                {
                    "content": body,
                    "type": obs_type,
                    "channel": channel,
                    "tags": tags,
                }
            ]
        },
    }


def _parse_observation(data: dict[str, Any]) -> Observation:
    """Pull the first observation out of /ingest's response shape."""
    if "id" in data and "statement" in data:
        return Observation.model_validate(data)
    for key in ("observation", "obs"):
        if key in data and isinstance(data[key], dict):
            return Observation.model_validate(data[key])
    items = data.get("items") or data.get("observations") or data.get("inserted")
    if isinstance(items, list) and items:
        return Observation.model_validate(items[0])
    # Fallback: synthesise from whatever fields we got
    return Observation.model_validate(
        {
            "id": data.get("id", "OBS-unknown"),
            "statement": data.get("statement", ""),
            **{k: v for k, v in data.items() if k not in {"id", "statement"}},
        }
    )


class _BaseOracle:
    """Shared resolution logic for sync + async clients."""

    def __init__(
        self,
        *,
        api_key: str | None = None,
        keypair: str | Path | dict[str, Any] | Keypair | None = None,
        base_url: str | None = None,
        timeout: float = DEFAULT_TIMEOUT,
    ) -> None:
        self.base_url = _resolve_base_url(base_url)
        self.timeout = timeout

        # Auth precedence: keypair > api_key > env bearer > open (capabilities only)
        self._keypair: Keypair | None = None
        self._bearer: str | None = None
        self.auth_mode: AuthMode

        if keypair is not None:
            self._keypair = (
                keypair if isinstance(keypair, Keypair) else Keypair.load(keypair)
            )
            self.auth_mode = "signed"
        else:
            bearer = _resolve_bearer(api_key)
            if bearer:
                self._bearer = bearer
                self.auth_mode = "bearer"
            else:
                self.auth_mode = "open"

    # ---- routing helpers -------------------------------------------------

    def _path_for(self, signed_path: str, bearer_path: str) -> str:
        return signed_path if self.auth_mode == "signed" else bearer_path

    def _build_headers(
        self,
        *,
        method: str,
        path: str,
        query_string: str,
        body: bytes,
        require_auth: bool = True,
    ) -> dict[str, str]:
        headers = {"Accept": "application/json"}
        if body:
            headers["Content-Type"] = "application/json"

        if self.auth_mode == "bearer":
            assert self._bearer is not None
            headers["Authorization"] = f"Bearer {self._bearer}"
        elif self.auth_mode == "signed":
            assert self._keypair is not None
            headers.update(
                sign_request(
                    self._keypair,
                    method=method,
                    path=path,
                    query_string=query_string,
                    body=body,
                )
            )
        elif require_auth:
            raise AuthError(
                "no credentials: pass keypair=..., api_key=..., or set ORACLE_TOKEN"
            )
        return headers


class Oracle(_BaseOracle):
    """Synchronous Oracle client.

    Hello world::

        from oracle_axxis import Oracle
        oracle = Oracle(keypair="key.json")
        oracle.add_dotpost(body="hello world", to="all", channel="lab")
        results = oracle.search("hello")
        print(results[0].statement)
    """

    def __init__(
        self,
        *,
        api_key: str | None = None,
        keypair: str | Path | dict[str, Any] | Keypair | None = None,
        base_url: str | None = None,
        timeout: float = DEFAULT_TIMEOUT,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        super().__init__(
            api_key=api_key, keypair=keypair, base_url=base_url, timeout=timeout
        )
        self._client = httpx.Client(
            base_url=self.base_url,
            timeout=self.timeout,
            transport=transport,
        )

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> Oracle:
        return self

    def __exit__(self, *exc: Any) -> None:
        self.close()

    # ---- core request -----------------------------------------------------

    @_retry_decorator()
    def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json_body: Any = None,
        require_auth: bool = True,
        stream: bool = False,
    ) -> httpx.Response:
        body_bytes = b""
        if json_body is not None:
            body_bytes = json.dumps(json_body, separators=(",", ":")).encode("utf-8")

        query_string = urlencode(params, doseq=True) if params else ""
        headers = self._build_headers(
            method=method,
            path=path,
            query_string=query_string,
            body=body_bytes,
            require_auth=require_auth,
        )

        request = self._client.build_request(
            method,
            path,
            params=params,
            content=body_bytes if body_bytes else None,
            headers=headers,
        )
        response = self._client.send(request, stream=stream)
        if not stream:
            _raise_for_status(response)
        return response

    # ---- bearer-only writes ----------------------------------------------

    def add(
        self,
        text: str,
        *,
        channel: str,
        tags: list[str] | None = None,
        source: str | None = None,
        obs_type: str = "observation",
    ) -> Observation:
        """Generic ingest — bearer auth only.

        Signed-request callers must use :meth:`add_dotpost` or
        :meth:`add_icontact` because ``/p/ingest`` restricts message types.
        """
        if self.auth_mode != "bearer":
            raise AuthError(
                "add() requires bearer auth. Use add_dotpost() or add_icontact() "
                "with a keypair, or pass api_key=..."
            )
        payload = _ingest_payload(
            body=text,
            obs_type=obs_type,
            channel=channel,
            tags=tags or [],
            source=source,
        )
        resp = self._request("POST", "/ingest", json_body=payload)
        return _parse_observation(resp.json())

    # ---- dotpost / icontact (both auth modes) -----------------------------

    def add_dotpost(
        self,
        body: str,
        *,
        to: str,
        channel: str = "dotpost",
        reply_to: str | None = None,
        tags: list[str] | None = None,
    ) -> Observation:
        all_tags = _dotpost_tags(to=to, channel=channel, reply_to=reply_to)
        if tags:
            all_tags.extend(tags)
        path = self._path_for("/p/ingest", "/ingest")
        payload = _ingest_payload(
            body=body,
            obs_type="dotpost",
            channel=channel,
            tags=all_tags,
            source=None,
        )
        resp = self._request("POST", path, json_body=payload)
        return _parse_observation(resp.json())

    def add_icontact(
        self,
        body: str,
        *,
        to: str,
        channel: str = "icontact",
        tags: list[str] | None = None,
    ) -> Observation:
        all_tags = [f"to:{to}", "icontact", f"channel:{channel}"]
        if tags:
            all_tags.extend(tags)
        path = self._path_for("/p/ingest", "/ingest")
        payload = _ingest_payload(
            body=body,
            obs_type="icontact",
            channel=channel,
            tags=all_tags,
            source=None,
        )
        resp = self._request("POST", path, json_body=payload)
        return _parse_observation(resp.json())

    # ---- reads ------------------------------------------------------------

    def search(
        self, query: str, *, top_k: int = 10, rerank: bool = True
    ) -> list[SearchResult]:
        path = self._path_for("/p/search", "/search")
        body = {"query": query, "top_k": top_k, "rerank": rerank}
        resp = self._request("POST", path, json_body=body)
        data = resp.json()
        items = data.get("results") or data.get("hits") or []
        return [SearchResult.model_validate(item) for item in items]

    def recent(
        self, *, limit: int = 20, channel: str | None = None
    ) -> list[Observation]:
        path = self._path_for("/p/recent", "/recent")
        params: dict[str, Any] = {"limit": limit}
        if channel:
            params["channel"] = channel
        resp = self._request("GET", path, params=params)
        data = resp.json()
        items = data.get("items") or data.get("observations") or []
        return [Observation.model_validate(item) for item in items]

    def ask(
        self, query: str, *, stream: bool = False
    ) -> AskResponse | Iterator[str]:
        path = self._path_for("/p/ask", "/ask")
        body: dict[str, Any] = {"question": query}
        if stream:
            body["stream"] = True
            resp = self._request(
                "POST", path, json_body=body, stream=True
            )
            _raise_for_status(resp)
            return _iter_sse_tokens(resp)
        resp = self._request("POST", path, json_body=body)
        return AskResponse.model_validate(resp.json())

    def connections(self, obs_id: str) -> ConnectionGraph:
        signed = f"/p/connections/{obs_id}"
        bearer = f"/connections/{obs_id}"
        path = self._path_for(signed, bearer)
        resp = self._request("GET", path)
        data = resp.json()
        data.setdefault("obs_id", obs_id)
        return ConnectionGraph.model_validate(data)

    def self_info(self) -> SelfInfo:
        path = self._path_for("/p/self", "/self")
        resp = self._request("GET", path)
        return SelfInfo.model_validate(resp.json())

    def capabilities(self) -> Capabilities:
        # Open endpoint — never sign, never bearer
        resp = self._request("GET", "/capabilities", require_auth=False)
        return Capabilities.model_validate(resp.json())


class AsyncOracle(_BaseOracle):
    """Asynchronous Oracle client. Mirrors :class:`Oracle` method-for-method."""

    def __init__(
        self,
        *,
        api_key: str | None = None,
        keypair: str | Path | dict[str, Any] | Keypair | None = None,
        base_url: str | None = None,
        timeout: float = DEFAULT_TIMEOUT,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        super().__init__(
            api_key=api_key, keypair=keypair, base_url=base_url, timeout=timeout
        )
        self._client = httpx.AsyncClient(
            base_url=self.base_url,
            timeout=self.timeout,
            transport=transport,
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    async def __aenter__(self) -> AsyncOracle:
        return self

    async def __aexit__(self, *exc: Any) -> None:
        await self.aclose()

    @_retry_decorator()
    async def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json_body: Any = None,
        require_auth: bool = True,
    ) -> httpx.Response:
        body_bytes = b""
        if json_body is not None:
            body_bytes = json.dumps(json_body, separators=(",", ":")).encode("utf-8")

        query_string = urlencode(params, doseq=True) if params else ""
        headers = self._build_headers(
            method=method,
            path=path,
            query_string=query_string,
            body=body_bytes,
            require_auth=require_auth,
        )

        request = self._client.build_request(
            method,
            path,
            params=params,
            content=body_bytes if body_bytes else None,
            headers=headers,
        )
        response = await self._client.send(request)
        _raise_for_status(response)
        return response

    async def add(
        self,
        text: str,
        *,
        channel: str,
        tags: list[str] | None = None,
        source: str | None = None,
        obs_type: str = "observation",
    ) -> Observation:
        if self.auth_mode != "bearer":
            raise AuthError(
                "add() requires bearer auth. Use add_dotpost() or add_icontact()."
            )
        payload = _ingest_payload(
            body=text,
            obs_type=obs_type,
            channel=channel,
            tags=tags or [],
            source=source,
        )
        resp = await self._request("POST", "/ingest", json_body=payload)
        return _parse_observation(resp.json())

    async def add_dotpost(
        self,
        body: str,
        *,
        to: str,
        channel: str = "dotpost",
        reply_to: str | None = None,
        tags: list[str] | None = None,
    ) -> Observation:
        all_tags = _dotpost_tags(to=to, channel=channel, reply_to=reply_to)
        if tags:
            all_tags.extend(tags)
        path = self._path_for("/p/ingest", "/ingest")
        payload = _ingest_payload(
            body=body,
            obs_type="dotpost",
            channel=channel,
            tags=all_tags,
            source=None,
        )
        resp = await self._request("POST", path, json_body=payload)
        return _parse_observation(resp.json())

    async def add_icontact(
        self,
        body: str,
        *,
        to: str,
        channel: str = "icontact",
        tags: list[str] | None = None,
    ) -> Observation:
        all_tags = [f"to:{to}", "icontact", f"channel:{channel}"]
        if tags:
            all_tags.extend(tags)
        path = self._path_for("/p/ingest", "/ingest")
        payload = _ingest_payload(
            body=body,
            obs_type="icontact",
            channel=channel,
            tags=all_tags,
            source=None,
        )
        resp = await self._request("POST", path, json_body=payload)
        return _parse_observation(resp.json())

    async def search(
        self, query: str, *, top_k: int = 10, rerank: bool = True
    ) -> list[SearchResult]:
        path = self._path_for("/p/search", "/search")
        body = {"query": query, "top_k": top_k, "rerank": rerank}
        resp = await self._request("POST", path, json_body=body)
        data = resp.json()
        items = data.get("results") or data.get("hits") or []
        return [SearchResult.model_validate(item) for item in items]

    async def recent(
        self, *, limit: int = 20, channel: str | None = None
    ) -> list[Observation]:
        path = self._path_for("/p/recent", "/recent")
        params: dict[str, Any] = {"limit": limit}
        if channel:
            params["channel"] = channel
        resp = await self._request("GET", path, params=params)
        data = resp.json()
        items = data.get("items") or data.get("observations") or []
        return [Observation.model_validate(item) for item in items]

    async def ask(self, query: str) -> AskResponse:
        path = self._path_for("/p/ask", "/ask")
        resp = await self._request("POST", path, json_body={"question": query})
        return AskResponse.model_validate(resp.json())

    async def connections(self, obs_id: str) -> ConnectionGraph:
        signed = f"/p/connections/{obs_id}"
        bearer = f"/connections/{obs_id}"
        path = self._path_for(signed, bearer)
        resp = await self._request("GET", path)
        data = resp.json()
        data.setdefault("obs_id", obs_id)
        return ConnectionGraph.model_validate(data)

    async def self_info(self) -> SelfInfo:
        path = self._path_for("/p/self", "/self")
        resp = await self._request("GET", path)
        return SelfInfo.model_validate(resp.json())

    async def capabilities(self) -> Capabilities:
        resp = await self._request("GET", "/capabilities", require_auth=False)
        return Capabilities.model_validate(resp.json())


def _iter_sse_tokens(response: httpx.Response) -> Iterator[str]:
    """Yield text tokens from a streaming /ask SSE response.

    The server emits ``data: {"token": "..."}`` lines separated by blank
    lines, with ``event: done`` at the end. Anything we can't parse is
    skipped silently — robustness over strictness here.
    """
    try:
        for line in response.iter_lines():
            if not line or not line.startswith("data:"):
                continue
            payload = line[len("data:") :].strip()
            if payload in ("", "[DONE]"):
                continue
            try:
                obj = json.loads(payload)
            except json.JSONDecodeError:
                continue
            token = obj.get("token") or obj.get("delta") or obj.get("content")
            if token:
                yield token
    finally:
        response.close()
