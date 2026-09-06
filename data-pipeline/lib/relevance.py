"""후보의 '키네틱 아트 관련도' 점수 (다운로드 전 선별용).

2차 확장에서 후보가 2000건을 넘어가면서, 이미지를 전부 받는 건 낭비다.
제목/설명/출처 텍스트의 키워드로 점수를 매겨 상위 TARGET_CANDIDATES 만 내려받는다.
(정밀 큐레이션은 3_enrich 노이즈 필터 + 최종 검수가 담당 — 여기선 거친 정렬만)
"""
from __future__ import annotations

# 강한 신호: 키네틱 아트 그 자체
_STRONG = {
    "kinetic": 10, "mobile": 6, "zoetrope": 8, "praxinoscope": 8,
    "phenakistiscope": 8, "thaumatrope": 7, "automaton": 6, "automata": 6,
    "strandbeest": 9, "op art": 8, "optical art": 8, "moiré": 5, "moire": 5,
    "tensegrity": 6, "whirligig": 6, "wind sculpture": 8,
}
# 약한 신호: 움직임/매체 맥락
_WEAK = {
    "sculpture": 3, "installation": 2, "moving": 3, "motion": 3, "rotat": 2,
    "spin": 2, "pendulum": 3, "wind": 2, "motor": 2, "solar": 1, "light art": 3,
    "sound sculpture": 4, "fountain": 2, "mechanic": 2, "interactive": 2,
    "illusion": 2, "anamorph": 3, "chime": 2, "weather vane": 3, "vane": 1,
}
# 대표 작가(있으면 거의 확실히 키네틱/옵아트)
_ARTISTS = ("calder", "tinguely", "rickey", "theo jansen", "gabo", "schöffer",
            "schoffer", "pol bury", "takis", "le parc", "cruz-diez", "soto",
            "vasarely", "bridget riley", "agam", "len lye", "ganson",
            "anthony howe", "margolin", "ned kahn", "prentice", "shingu",
            "rebecca horn", "eliasson", "rozin", "zimoun", "munro")
# 감점: 작품 사진이 아닐 가능성
_PENALTY = ("portrait of", "exhibition view", "museum interior", "facade",
            "street view", "parking", "signature", "grave", "stamp", "logo",
            "diagram", "map of", "poster for", "book cover")


def score(rec: dict) -> int:
    blob = " ".join(str(rec.get(k) or "") for k in
                    ("title", "desc_src", "artist", "source_page_url",
                     "materials_raw")).lower()

    total = 0
    for kw, pts in _STRONG.items():
        if kw in blob:
            total += pts
    for kw, pts in _WEAK.items():
        if kw in blob:
            total += pts
    if any(a in blob for a in _ARTISTS):
        total += 8
    for bad in _PENALTY:
        if bad in blob:
            total -= 6

    # 해상도가 확인되는 경우 약간 가산(원본 imageinfo 기준)
    if (rec.get("width") or 0) >= 1200:
        total += 1
    return total


def rank(records: list[dict], limit: int) -> list[dict]:
    """관련도 내림차순으로 정렬해 상위 limit 개 반환(점수를 _rel 에 기록)."""
    for r in records:
        r["_rel"] = score(r)
    ordered = sorted(records, key=lambda r: r["_rel"], reverse=True)
    return ordered[:limit]
