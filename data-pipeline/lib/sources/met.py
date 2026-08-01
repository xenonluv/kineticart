"""The Met Open Access 수집기 (보조 소스, 키 불필요).

"kinetic" 검색은 노이즈가 있으므로 isPublicDomain=True + primaryImage 존재 건만 통과시키고,
최종 큐레이션(검수 단계)에서 키네틱 아트 여부를 사람이 확인한다.
모든 통과 건은 CC0(Public Domain)이라 재배포 안전.
"""
from __future__ import annotations

import config
from lib.http import get_json
from lib.models import new_candidate


def collect() -> list[dict]:
    search = get_json(config.MET_SEARCH_API,
                      {"q": config.MET_QUERY, "hasImages": "true"})
    object_ids = search.get("objectIDs") or []
    print(f"  [met] 검색 결과 {len(object_ids)}건, PD+이미지 필터링 중...")

    candidates: list[dict] = []
    for oid in object_ids:
        if len(candidates) >= config.MET_MAX_OBJECTS:
            break
        try:
            obj = get_json(f"{config.MET_OBJECT_API}/{oid}")
        except RuntimeError:
            continue

        if not obj.get("isPublicDomain"):
            continue
        image_url = obj.get("primaryImage")
        if not image_url:
            continue

        candidates.append(new_candidate(
            source="met",
            source_id=str(oid),
            source_page_url=obj.get("objectURL"),
            image_src_url=image_url,
            image_orig_url=image_url,
            mime="image/jpeg",
            license="CC0",
            license_url="https://creativecommons.org/publicdomain/zero/1.0/",
            attribution=None,
            attribution_required=False,
            license_allowed=True,
            title=obj.get("title") or None,
            artist=obj.get("artistDisplayName") or None,
            year_raw=obj.get("objectDate") or None,
            materials_raw=obj.get("medium") or None,
            dimensions_raw=obj.get("dimensions") or None,
            desc_src=_met_desc(obj),
        ))
    return candidates


def _met_desc(obj: dict) -> str | None:
    """Met 메타를 영문 설명 문장으로 조립 (한글 생성 근거용)."""
    bits = []
    if obj.get("title"):
        bits.append(obj["title"])
    if obj.get("artistDisplayName"):
        bits.append(f"by {obj['artistDisplayName']}")
    if obj.get("objectDate"):
        bits.append(f"({obj['objectDate']})")
    if obj.get("medium"):
        bits.append(f"Medium: {obj['medium']}.")
    if obj.get("classification"):
        bits.append(f"Classification: {obj['classification']}.")
    if obj.get("department"):
        bits.append(f"Dept: {obj['department']}.")
    return " ".join(bits) or None
