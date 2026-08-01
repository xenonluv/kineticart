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


def get_json(url: str, params: dict | None = None, *, retries: int = 3) -> Any:
    last_err: Exception | None = None
    for attempt in range(retries):
        _throttle()
        try:
            r = _session.get(url, params=params, timeout=config.REQUEST_TIMEOUT)
            r.raise_for_status()
            return r.json()
        except Exception as e:  # noqa: BLE001 - 네트워크 계열 광범위 재시도
            last_err = e
            time.sleep(1.0 + attempt)
    raise RuntimeError(f"GET failed after {retries} tries: {url} :: {last_err}")


def get_bytes(url: str, *, retries: int = 3) -> bytes:
    last_err: Exception | None = None
    for attempt in range(retries):
        _throttle()
        try:
            r = _session.get(url, timeout=config.REQUEST_TIMEOUT)
            r.raise_for_status()
            return r.content
        except Exception as e:  # noqa: BLE001
            last_err = e
            time.sleep(1.0 + attempt)
    raise RuntimeError(f"GET bytes failed after {retries} tries: {url} :: {last_err}")
