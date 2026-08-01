"""라이선스 판정: 재배포 가능한 것만 통과.

허용: CC0, Public Domain(PD), CC-BY(모든 버전), CC-BY-SA(모든 버전), GFDL(자유 라이선스).
차단: NC(비영리)/ND(변경금지) 조건, "all rights reserved", "fair use" 등.

원본 이미지를 집 Mac에서 외부로 공개 서빙하므로, 재배포 가능한 라이선스만 수집한다.
"""
from __future__ import annotations

# 확실히 차단해야 하는 표식 (비영리/변경금지/저작권 보유)
_DENY_MARKERS = (
    "non-commercial", "noncommercial", "non commercial", "-nc", " nc ",
    "no derivative", "noderiv", "-nd", " nd ",
    "all rights reserved", "fair use", "copyright", "©",
)

# 허용 라이선스 표식
_ALLOW_MARKERS = (
    "cc0", "cc-zero", "public domain", "publicdomain", "pd-", "pdart",
    "cc-by", "cc by", "attribution", "gfdl", "free art license",
)


def classify(short_name: str | None,
             license_code: str | None,
             usage_terms: str | None = None) -> dict:
    """라이선스 문자열들을 받아 정규화 결과 반환.

    returns {"label", "allowed", "attribution_required"}
    """
    parts = [p for p in (short_name, license_code, usage_terms) if p]
    text = " ".join(parts).lower()

    if not text:
        return {"label": "unknown", "allowed": False, "attribution_required": False}

    # 차단 우선
    if any(m in text for m in _DENY_MARKERS):
        # 단, "public domain"과 "copyright"가 함께 있는 애매한 경우는 아래에서 재검토하지 않고 차단 유지
        return {"label": _clean_label(short_name, license_code),
                "allowed": False, "attribution_required": False}

    # CC0 / Public Domain → 표기 불필요
    if any(m in text for m in ("cc0", "cc-zero", "public domain", "publicdomain", "pd-", "pdart", "pdmark")):
        return {"label": _pd_label(short_name, license_code),
                "allowed": True, "attribution_required": False}

    # CC-BY / CC-BY-SA / GFDL → 표기 필요
    if any(m in text for m in ("cc-by", "cc by", "gfdl", "free art license", "attribution")):
        return {"label": _clean_label(short_name, license_code),
                "allowed": True, "attribution_required": True}

    return {"label": _clean_label(short_name, license_code),
            "allowed": False, "attribution_required": False}


def _clean_label(short_name: str | None, license_code: str | None) -> str:
    if short_name:
        return short_name.strip()
    if license_code:
        return license_code.strip().upper()
    return "unknown"


def _pd_label(short_name: str | None, license_code: str | None) -> str:
    label = _clean_label(short_name, license_code)
    low = label.lower()
    if "cc0" in low or "zero" in low:
        return "CC0"
    return "Public Domain"
