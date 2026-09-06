"""Art Institute of Chicago 수집기 (보조 소스, 키 불필요).

is_public_domain == True 인 건만 통과(= 재배포 안전). 이미지는 IIIF 로 받는다.
CMA 와 마찬가지로 키네틱 여부는 후속 큐레이션에서 가린다.
"""
from __future__ import annotations

import config
from lib.http import get_json
from lib.models import new_candidate

_FIELDS = ("id,title,artist_display,date_display,medium_display,dimensions,"
           "image_id,is_public_domain,description,short_description")


def _artist(display: str | None) -> str | None:
    if not display:
        return None
    # "Henry Moore\nEnglish, 1898-1986" → "Henry Moore"
    return display.split("\n")[0].strip() or None


def collect() -> list[dict]:
    candidates: list[dict] = []
    seen: set[str] = set()

    for query in config.ART_QUERIES:
        if len(candidates) >= config.AIC_MAX_OBJECTS:
            break
        try:
            data = get_json(config.AIC_API, {"q": query, "limit": 100,
                                             "fields": _FIELDS})
        except RuntimeError:
            continue

        for rec in data.get("data") or []:
            if len(candidates) >= config.AIC_MAX_OBJECTS:
                break
            oid = str(rec.get("id"))
            if oid in seen:
                continue
            if not rec.get("is_public_domain") or not rec.get("image_id"):
                continue
            seen.add(oid)

            img = (f"{config.AIC_IIIF_BASE}/{rec['image_id']}"
                   f"/full/{config.MAX_LONG_EDGE},/0/default.jpg")
            desc = rec.get("description") or rec.get("short_description")

            candidates.append(new_candidate(
                source="aic",
                source_id=oid,
                source_page_url=f"https://www.artic.edu/artworks/{oid}",
                image_src_url=img,
                image_orig_url=img,
                mime="image/jpeg",
                license="Public Domain",
                license_url="https://www.artic.edu/open-access/open-access-images",
                attribution=None,
                attribution_required=False,
                license_allowed=True,
                title=rec.get("title") or None,
                artist=_artist(rec.get("artist_display")),
                year_raw=rec.get("date_display") or None,
                materials_raw=rec.get("medium_display") or None,
                dimensions_raw=rec.get("dimensions") or None,
                desc_src=desc or None,
            ))

    print(f"  [aic] PD+이미지 {len(candidates)}건")
    return candidates
