#!/usr/bin/env python3
"""manifest.json 무결성 검사 — 6_build_manifest.py 가 끝에서 자동 호출한다(단독 실행도 가능).

검사: 설명 한글·HTML 없음 / local_id·source_url 고유·비어있지 않음 / 파일 실재
      (works·cards·display·texts) / created_year 타입 / pinned ⊆ manifest.
실패 시 종료코드 1 — seed_sync 적용 전에 반드시 통과해야 한다.

실행:  python check_manifest.py
"""
from __future__ import annotations

import json
import sys

import config
from lib.models import load_records
from lib.validate import HANGUL, HTML_TAG


def _local_path(url: str | None):
    """공개 URL(…/cards/200.webp?v=…) → 로컬 파일 경로."""
    if not url:
        return None
    rel = url.split(config.BASE_IMAGE_URL.rstrip("/") + "/", 1)[-1].split("?", 1)[0]
    return config.ROOT / rel


def check(rows: list[dict]) -> list[str]:
    errors: list[str] = []
    for key in ("local_id", "source_url"):
        vals = [r.get(key) for r in rows]
        if any(not v for v in vals):
            errors.append(f"{key} 비어 있는 행 {sum(1 for v in vals if not v)}개")
        dup = sorted({v for v in vals if v and vals.count(v) > 1})
        if dup:
            errors.append(f"{key} 중복 {dup[:10]}")
    for r in rows:
        lid = r.get("local_id")
        d = r.get("description") or ""
        if not HANGUL.search(d):
            errors.append(f"{lid}: 설명에 한글 없음")
        if HTML_TAG.search(d):
            errors.append(f"{lid}: 설명에 HTML 태그")
        if r.get("created_year") is not None and not isinstance(r["created_year"], int):
            errors.append(f"{lid}: created_year 타입 {type(r['created_year']).__name__}")
        for f in ("image_url", "thumbnail_url", "display_url", "detail_text_url"):
            p = _local_path(r.get(f))
            if r.get(f) and not (p and p.exists()):
                errors.append(f"{lid}: {f} 파일 없음 ({p})")
        if not r.get("image_url"):
            errors.append(f"{lid}: image_url 없음")
    pinned_path = config.DATASET_DIR / "pinned_live.json"
    if pinned_path.exists():
        pinned = set(json.loads(pinned_path.read_text(encoding="utf-8")))
        lost = sorted(pinned - {r.get("local_id") for r in rows})
        if lost:
            # 경고만 — 검수 거부로 의도적으로 내린 라이브 작품일 수 있다(6단계 로그에 사유 출력)
            print(f"  ⚠ 라이브(pinned) 중 manifest 에 없는 {len(lost)}건: {lost[:15]}")
    return errors


def main() -> int:
    rows = load_records(config.MANIFEST_JSON)
    errors = check(rows)
    if errors:
        print(f"✗ manifest 검사 실패 {len(errors)}건:")
        for e in errors[:40]:
            print(f"  - {e}")
        return 1
    print(f"✓ manifest 검사 통과: {len(rows)}행")
    return 0


if __name__ == "__main__":
    sys.exit(main())
