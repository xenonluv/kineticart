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
from lib import relevance
from lib.models import load_records, save_records
from lib.sources import artic, cleveland, met, wikimedia

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


def _prior_keys() -> tuple[set[str], set[str]]:
    """이전 배치에서 이미 수집한 작품의 (source_page_url, source|source_id) 집합."""
    urls: set[str] = set()
    sids: set[str] = set()
    for path in config.PRIOR_RECORD_FILES:
        if path == config.CANDIDATES_JSON or not path.exists():
            continue
        for r in load_records(path):
            if r.get("source_page_url"):
                urls.add(r["source_page_url"])
            if r.get("source_id"):
                sids.add(f"{r.get('source')}|{r['source_id']}")
    return urls, sids


def main() -> int:
    print("== 스테이지 1: 후보 수집 ==")
    if config.BATCH:
        print(f"배치 모드: {config.BATCH} (산출 → {config.CANDIDATES_JSON.name})")

    all_records: list[dict] = []

    sources = [("Wikimedia Commons", wikimedia.collect, True),
               ("The Met", met.collect, config.USE_MET),
               ("Cleveland Museum", cleveland.collect, config.USE_CMA),
               ("Art Institute of Chicago", artic.collect, config.USE_AIC)]

    for i, (name, fn, enabled) in enumerate(sources, 1):
        if not enabled:
            print(f"[{i}/{len(sources)}] {name} 비활성화 — 건너뜀")
            continue
        print(f"[{i}/{len(sources)}] {name} 수집...")
        try:
            recs = fn()
            print(f"  → {len(recs)}개 (라이선스 통과)")
            all_records.extend(recs)
        except Exception as e:  # noqa: BLE001
            print(f"  ! {name} 수집 실패: {e}")

    # 이전 배치에서 이미 가진 작품 제외 (배치 모드에서만 의미 있음)
    prior_urls, prior_sids = _prior_keys()
    if prior_urls or prior_sids:
        kept = [r for r in all_records
                if r.get("source_page_url") not in prior_urls
                and f"{r.get('source')}|{r.get('source_id')}" not in prior_sids]
        print(f"\n기존 수집분 제외: {len(all_records)} → {len(kept)}")
        all_records = kept

    before = len(all_records)
    deduped = _dedup(all_records)
    print(f"\n중복 제거: {before} → {len(deduped)}")

    # 관련도 상위 TARGET_CANDIDATES 만 남긴다(다운로드 비용 절감)
    if len(deduped) > config.TARGET_CANDIDATES:
        deduped = relevance.rank(deduped, config.TARGET_CANDIDATES)
        print(f"관련도 선별: 상위 {len(deduped)}개 "
              f"(점수 {deduped[-1]['_rel']} 이상)")

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
