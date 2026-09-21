"""Winziger HTTP-Client auf urllib - kein requests/httpx noetig."""

from __future__ import annotations

import json
import ssl
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

DEFAULT_TIMEOUT = 30
_CACHE: dict[str, tuple[float, Any]] = {}


class HttpError(RuntimeError):
    def __init__(self, status: int, url: str, body: str = "") -> None:
        super().__init__(f"HTTP {status} bei {url}: {body[:300]}")
        self.status = status
        self.url = url
        self.body = body


def _ssl_context() -> ssl.SSLContext:
    """Nutzt das System-CA-Bundle bzw. REQUESTS_CA_BUNDLE, falls gesetzt."""
    import os

    bundle = os.environ.get("REQUESTS_CA_BUNDLE") or os.environ.get("SSL_CERT_FILE")
    if bundle and os.path.isfile(bundle):
        return ssl.create_default_context(cafile=bundle)
    return ssl.create_default_context()


def request_json(
    url: str,
    *,
    params: dict[str, Any] | None = None,
    method: str = "GET",
    headers: dict[str, str] | None = None,
    body: Any = None,
    timeout: int = DEFAULT_TIMEOUT,
    cache_ttl: int = 0,
    retries: int = 2,
) -> Any:
    """JSON holen/senden. Optionaler In-Memory-Cache und einfache Retries."""
    if params:
        clean = {k: v for k, v in params.items() if v is not None}
        url = f"{url}{'&' if '?' in url else '?'}{urllib.parse.urlencode(clean)}"

    cache_key = f"{method}:{url}"
    if cache_ttl > 0 and cache_key in _CACHE:
        stored_at, value = _CACHE[cache_key]
        if time.time() - stored_at < cache_ttl:
            return value

    payload = None
    all_headers = {"Accept": "application/json", "User-Agent": "Jarvis/0.1"}
    if body is not None:
        payload = json.dumps(body).encode("utf-8")
        all_headers["Content-Type"] = "application/json"
    all_headers.update(headers or {})

    last_error: Exception | None = None
    for attempt in range(retries + 1):
        req = urllib.request.Request(url, data=payload, headers=all_headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=timeout, context=_ssl_context()) as resp:
                raw = resp.read().decode("utf-8", errors="replace")
            data = json.loads(raw) if raw.strip() else {}
            if cache_ttl > 0:
                _CACHE[cache_key] = (time.time(), data)
            return data
        except urllib.error.HTTPError as exc:                     # 4xx/5xx
            detail = exc.read().decode("utf-8", errors="replace")
            if exc.code < 500 or attempt == retries:
                raise HttpError(exc.code, url, detail) from exc
            last_error = exc
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            last_error = exc
            if attempt == retries:
                raise
        time.sleep(1.5 * (attempt + 1))

    raise last_error or RuntimeError("Anfrage fehlgeschlagen")


def clear_cache() -> None:
    _CACHE.clear()
