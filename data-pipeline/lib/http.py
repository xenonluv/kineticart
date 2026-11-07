"""공용 HTTP 헬퍼: User-Agent 부착, 요청 간 지연, 타임아웃, 간단 재시도."""
from __future__ import annotations

import time
from typing import Any

import requests

import config

_session = requests.Session()
_session.headers.update({"User-Agent": config.USER_AGENT})

_last_call = 0.0


def _throttle() -> None:
    """마지막 호출 이후 REQUEST_DELAY 미만이면 대기."""
    global _last_call
    elapsed = time.time() - _last_call
    if elapsed < config.REQUEST_DELAY:
        time.sleep(config.REQUEST_DELAY - elapsed)
    _last_call = time.time()


def _retryable(e: Exception) -> bool:
    """4xx(408·429 제외)는 재시도해도 결과가 같으므로 즉시 포기."""
    resp = getattr(e, "response", None)
    code = getattr(resp, "status_code", None)
    return code is None or code >= 500 or code in (408, 429)


def _backoff(e: Exception, attempt: int) -> None:
    """429/503 은 Retry-After(없으면 지수 백오프, 최대 120초)를 따르고, 그 외는 짧게 대기."""
    resp = getattr(e, "response", None)
    if resp is not None and resp.status_code in (429, 503):
        ra = resp.headers.get("Retry-After", "")
        wait = min(120.0, float(ra)) if ra.isdigit() else min(120.0, 5.0 * 2 ** attempt)
        time.sleep(wait)
    else:
        time.sleep(1.0 + attempt)


def get_json(url: str, params: dict | None = None, *, retries: int = 6) -> Any:
    last_err: Exception | None = None
    for attempt in range(retries):
        _throttle()
        try:
            r = _session.get(url, params=params, timeout=config.REQUEST_TIMEOUT)
            r.raise_for_status()
            return r.json()
        except Exception as e:  # noqa: BLE001 - 네트워크 계열 광범위 재시도
            last_err = e
            if not _retryable(e):
                break
            _backoff(e, attempt)
    raise RuntimeError(f"GET failed after {retries} tries: {url} :: {last_err}")


def get_bytes(url: str, *, retries: int = 6) -> bytes:
    last_err: Exception | None = None
    for attempt in range(retries):
        _throttle()
        try:
            r = _session.get(url, timeout=config.REQUEST_TIMEOUT)
            r.raise_for_status()
            return r.content
        except Exception as e:  # noqa: BLE001
            last_err = e
            if not _retryable(e):
                break
            _backoff(e, attempt)
    raise RuntimeError(f"GET bytes failed after {retries} tries: {url} :: {last_err}")
