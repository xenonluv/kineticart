"""Wikimedia Commons 수집기 (주력 소스).

seed 카테고리에서 시작해 하위 카테고리를 재귀 탐색하여 파일을 모으고,
imageinfo + extmetadata 로 이미지 URL / 라이선스 / 작가 / 설명을 한 번에 가져온다.
"""
from __future__ import annotations

import html
import re

import config
from lib import license as lic
from lib.http import get_json
from lib.models import new_candidate

_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")
_IMAGE_MIME = {"image/jpeg", "image/png", "image/webp", "image/gif"}


def _clean_html(value: str | None) -> str | None:
    if not value:
        return None
    text = _TAG_RE.sub(" ", value)
    text = html.unescape(text)
    text = _WS_RE.sub(" ", text).strip()
    return text or None


def _ext_value(extmeta: dict, key: str) -> str | None:
    node = extmeta.get(key)
    if isinstance(node, dict):
        return node.get("value")
    return None


def _category_members(title: str, cmtype: str) -> list[dict]:
    """카테고리의 멤버(파일 또는 하위카테고리)를 continuation 포함 전량 반환."""
    members: list[dict] = []
    cont: dict = {}
    while True:
        params = {
            "action": "query",
            "list": "categorymembers",
            "cmtitle": f"Category:{title}",
            "cmtype": cmtype,          # "file" 또는 "subcat"
            "cmlimit": "500",
            "format": "json",
            **cont,
        }
        data = get_json(config.WIKIMEDIA_API, params)
        members.extend(data.get("query", {}).get("categorymembers", []))
        if "continue" in data:
            cont = data["continue"]
        else:
            break
    return members


def _collect_file_titles() -> list[str]:
    """seed 카테고리 → 하위 재귀 → 파일 제목 목록(중복 제거)."""
    seen_cats: set[str] = set()
    file_titles: list[str] = []
    seen_files: set[str] = set()

    # (category_title, depth) 큐
    queue = [(c, 0) for c in config.WIKIMEDIA_SEED_CATEGORIES]

    while queue and len(file_titles) < config.WIKIMEDIA_MAX_FILES:
        cat, depth = queue.pop(0)
        if cat in seen_cats:
            continue
        seen_cats.add(cat)

        # 이 카테고리의 파일
        for m in _category_members(cat, "file"):
            title = m.get("title")
            if title and title not in seen_files:
                seen_files.add(title)
                file_titles.append(title)
                if len(file_titles) >= config.WIKIMEDIA_MAX_FILES:
                    break

        # 하위 카테고리 재귀 (depth 제한 + denylist 필터)
        if depth < config.WIKIMEDIA_SUBCAT_DEPTH:
            for m in _category_members(cat, "subcat"):
                sub = (m.get("title") or "").replace("Category:", "")
                low = sub.lower()
                if any(bad in low for bad in config.WIKIMEDIA_SUBCAT_DENYLIST):
                    continue
                queue.append((sub, depth + 1))

    return file_titles


def _imageinfo_batch(titles: list[str]) -> list[dict]:
    """최대 50개 제목의 imageinfo(+extmetadata) 조회."""
    params = {
        "action": "query",
        "titles": "|".join(titles),
        "prop": "imageinfo",
        "iiprop": "url|size|mime|extmetadata",
        "iiurlwidth": str(config.MAX_LONG_EDGE),
        "format": "json",
    }
    data = get_json(config.WIKIMEDIA_API, params)
    pages = data.get("query", {}).get("pages", {})
    return list(pages.values())


def collect() -> list[dict]:
    """Wikimedia Commons 후보 레코드 리스트 반환."""
    titles = _collect_file_titles()
    print(f"  [wikimedia] 파일 제목 {len(titles)}개 수집, imageinfo 조회 중...")

    candidates: list[dict] = []
    for i in range(0, len(titles), 50):
        batch = titles[i:i + 50]
        for page in _imageinfo_batch(batch):
            rec = _page_to_candidate(page)
            if rec is not None:
                candidates.append(rec)
    return candidates


def _page_to_candidate(page: dict) -> dict | None:
    info_list = page.get("imageinfo")
    if not info_list:
        return None
    info = info_list[0]

    mime = info.get("mime")
    if mime not in _IMAGE_MIME:
        return None

    width = info.get("width") or 0
    height = info.get("height") or 0
    if max(width, height) < config.MIN_LONG_EDGE:
        return None

    ext = info.get("extmetadata", {}) or {}
    short = _ext_value(ext, "LicenseShortName")
    code = _ext_value(ext, "License")
    usage = _ext_value(ext, "UsageTerms")
    verdict = lic.classify(short, code, usage)
    if not verdict["allowed"]:
        return None

    artist = _clean_html(_ext_value(ext, "Artist"))
    credit = _clean_html(_ext_value(ext, "Credit"))
    title = _clean_html(_ext_value(ext, "ObjectName")) \
        or page.get("title", "").replace("File:", "").rsplit(".", 1)[0]
    desc = _clean_html(_ext_value(ext, "ImageDescription"))
    date = _clean_html(_ext_value(ext, "DateTimeOriginal")) \
        or _clean_html(_ext_value(ext, "DateTime"))

    attribution = None
    if verdict["attribution_required"]:
        bits = [b for b in (artist, credit, verdict["label"], "via Wikimedia Commons") if b]
        attribution = " / ".join(dict.fromkeys(bits))  # 중복 제거 유지 순서

    return new_candidate(
        source="wikimedia",
        source_id=str(page.get("pageid")),
        source_page_url=info.get("descriptionurl"),
        image_src_url=info.get("thumburl") or info.get("url"),
        image_orig_url=info.get("url"),
        mime=mime,
        license=verdict["label"],
        license_url=_ext_value(ext, "LicenseUrl"),
        attribution=attribution,
        attribution_required=verdict["attribution_required"],
        license_allowed=True,
        title=title,
        artist=artist,
        year_raw=date,
        desc_src=desc,
    )
