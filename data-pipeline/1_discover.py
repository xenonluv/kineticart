#!/usr/bin/env python3
"""스테이지 1: 후보 수집.

Wikimedia Commons(주력) + The Met(보조)에서 재배포 가능한 키네틱 아트 이미지 후보를 모아
중복 제거 후 dataset/candidates.json 으로 저장한다.

실행:  (data-pipeline 디렉토리에서)  python 1_discover.py
"""
from __future__ import annotations

import re
import sys

import config
from lib.models import save_records
from lib.sources import met, wikimedia

_NORM_RE = re.compile(r"[^a-z0-9가-힣]+")


def _norm(s: str | None) -> str:
    return _NORM_RE.sub("", (s or "").lower())


def _dedup(records: list[dict]) -> list[dict]:
    seen_keys: set[str] = set()
    seen_imgs: set[str] = set()
    out: list[dict] = []
    for r in records:
        img = (r.get("image_orig_url") or "").rsplit("/", 1)[-1]
        key = _norm(r.get("title")) + "|" + _norm(r.get("artist"))
        if img and img in seen_imgs:
            continue
        if key.strip("|") and key in seen_keys:
            continue
        seen_imgs.add(img)
        seen_keys.add(key)
        out.append(r)
    return out


def main() -> int:
    print("== 스테이지 1: 후보 수집 ==")

    all_records: list[dict] = []

    print("[1/2] Wikimedia Commons 수집...")
    try:
        wm = wikimedia.collect()
        print(f"  → {len(wm)}개 (라이선스 통과)")
        all_records.extend(wm)
    except Exception as e:  # noqa: BLE001
        print(f"  ! Wikimedia 수집 실패: {e}")

    if config.USE_MET:
        print("[2/2] The Met 수집...")
        try:
            mt = met.collect()
            print(f"  → {len(mt)}개 (PD+이미지)")
            all_records.extend(mt)
        except Exception as e:  # noqa: BLE001
            print(f"  ! Met 수집 실패: {e}")
    else:
        print("[2/2] The Met 비활성화 (config.USE_MET=False) — 노이즈로 제외")

    before = len(all_records)
    deduped = _dedup(all_records)
    print(f"\n중복 제거: {before} → {len(deduped)}")

    save_records(config.CANDIDATES_JSON, deduped)

    # 요약
    by_source: dict[str, int] = {}
    for r in deduped:
        by_source[r["source"]] = by_source.get(r["source"], 0) + 1
    print(f"\n저장: {config.CANDIDATES_JSON}")
    print(f"총 후보: {len(deduped)}  (소스별: {by_source})")
    print(f"목표 후보 수: {config.TARGET_CANDIDATES}")

    if len(deduped) < config.TARGET_FINAL:
        print(f"\n⚠️  최종 목표({config.TARGET_FINAL})보다 적습니다. "
              f"config 의 카테고리/상한을 늘리세요.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
