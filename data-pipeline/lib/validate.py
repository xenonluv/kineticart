"""한글 설명 레코드 검증 게이트.

4단계(서브에이전트) 결과 중 '이미지를 실제로 보고 쓴 정상 한글 설명'만 통과시킨다.
세션 한도(429) 등으로 실패한 파트를 원문 복사로 메운 fallback 이 최종 manifest/DB 로
새어 들어간 사고(2차 배치 125건)를 구조적으로 막기 위한 것이다.
"""
from __future__ import annotations

import re

HANGUL = re.compile(r"[가-힣]")
HTML_TAG = re.compile(r"<[a-zA-Z/][^>]*>")
_YEAR = re.compile(r"\d{3,4}")
# fallback/미검증 표시 — 이 문구가 notes 에 있으면 이미지 미확인 산출물로 간주
_UNVERIFIED_MARKERS = ("이미지 미확인", "자동 생성", "image not checked", "fallback")


def unverified_reason(r: dict) -> str | None:
    """검증 실패 사유(문자열) 또는 통과 시 None."""
    if r.get("review_status") == "rejected":
        return "거부됨"
    desc = (r.get("description_ko") or "").strip()
    if not desc:
        return "설명 없음"
    if not HANGUL.search(desc):
        return "한글 없음"
    if HTML_TAG.search(desc) or HTML_TAG.search(r.get("detail_text_ko") or ""):
        return "HTML 태그 포함"
    src = (r.get("desc_src") or "").strip()
    if src and desc == src:
        return "원문 복붙"
    notes = (r.get("notes") or "").lower()
    if any(m.lower() in notes for m in _UNVERIFIED_MARKERS):
        return "이미지 미확인 표시"
    return None


def coerce_year(v) -> int | None:
    """LLM 이 낸 연도("c. 1972", "1960s", "1972년", 1972)를 int 로. 해석 불가면 None."""
    if v is None or v == "" or isinstance(v, bool):
        return None
    if isinstance(v, int):
        return v
    m = _YEAR.search(str(v))
    return int(m.group(0)) if m else None


def is_verified(r: dict) -> bool:
    return unverified_reason(r) is None
