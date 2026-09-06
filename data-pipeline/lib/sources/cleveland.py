"""Cleveland Museum of Art Open Access 수집기 (보조 소스, 키 불필요).

CC0 로 공개된 소장품만 통과시킨다(share_license_status == "CC0").
"kinetic" 자체는 CMA 검색에 거의 없어(0건), 인접 질의(op art / mobile / moving sculpture …)로
후보를 모으고 키네틱 여부는 3_enrich 노이즈 필터 + 최종 큐레이션에서 가린다.
"""
from __future__ import annotations

import config
from lib.http import get_json
from lib.models import new_candidate


def _image_url(rec: dict) -> str | None:
    images = rec.get("images") or {}
    for key in ("web", "print", "full"):
        node = images.get(key)
        if isinstance(node, dict) and node.get("url"):
            return node["url"]
    return None


def _creator(rec: dict) -> str | None:
    creators = rec.get("creators") or []
    if creators and isinstance(creators[0], dict):
        name = creators[0].get("description") or creators[0].get("name")
        if name:
            return str(name).split("(")[0].strip(" ,")
    return None


def collect() -> list[dict]:
    candidates: list[dict] = []
    seen: set[str] = set()

    for query in config.ART_QUERIES:
        if len(candidates) >= config.CMA_MAX_OBJECTS:
            break
        try:
            data = get_json(config.CMA_API, {"q": query, "limit": 100,
                                             "has_image": 1, "skip": 0})
        except RuntimeError:
            continue

        for rec in data.get("data") or []:
            if len(candidates) >= config.CMA_MAX_OBJECTS:
                break
            oid = str(rec.get("id"))
            if oid in seen:
                continue
            if (rec.get("share_license_status") or "").upper() != "CC0":
                continue
            img = _image_url(rec)
            if not img:
                continue
            seen.add(oid)

            candidates.append(new_candidate(
                source="cma",
                source_id=oid,
                source_page_url=rec.get("url"),
                image_src_url=img,
                image_orig_url=img,
                mime="image/jpeg",
                license="CC0",
                license_url="https://creativecommons.org/publicdomain/zero/1.0/",
                attribution=None,
                attribution_required=False,
                license_allowed=True,
                title=rec.get("title") or None,
                artist=_creator(rec),
                year_raw=rec.get("creation_date") or None,
                materials_raw=rec.get("technique") or None,
                dimensions_raw=None,
                desc_src=rec.get("description") or rec.get("tombstone") or None,
            ))

    print(f"  [cma] CC0+이미지 {len(candidates)}건")
    return candidates
