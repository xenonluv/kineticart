#!/usr/bin/env python3
"""스테이지 3: 메타데이터 정규화 + 태그 + 근접중복 제거 + 선별.

downloaded.json 을 받아:
 - artist 정리(업로더 노이즈 제거, title 의 'by X' 활용)
 - created_year(int) 파싱
 - 매체 키워드 → 한글 태그 파생
 - 같은 작품의 다중 사진(근접중복) 1장만 유지
 - 품질 점수로 상위 DESCRIBE_TARGET 개를 selected=True (한글 생성 대상)
enriched.json 저장.

실행:  python 3_enrich.py
"""
from __future__ import annotations

import json
import re
import sys

import config
from lib import imaging
from lib.models import load_records, save_records

_YEAR_RE = re.compile(r"\b(1[89]\d{2}|20[0-2]\d)\b")
_WORD_RE = re.compile(r"[a-z0-9가-힣]+")
_UPLOADER_MARKS = ("uploaded", "ttee", "trust", "revocab", "own work", "self-photo")

# 매체/움직임 키워드 → 한글 태그
_MEDIUM_KW = {
    "motor": "모터", "motoriz": "모터", "wind": "바람", "led": "LED",
    "light": "빛", "neon": "네온", "mobile": "모빌", "mirror": "거울",
    "water": "물", "fountain": "분수", "magnet": "자석", "solar": "태양광",
    "steel": "스틸", "aluminum": "알루미늄", "aluminium": "알루미늄",
    "rotat": "회전", "spin": "회전", "pendulum": "진자", "wire": "와이어",
    "glass": "유리", "kinetic": "키네틱", "zoetrope": "조트로프",
    "installation": "설치", "sculpture": "조각",
}
# 노이즈 신호 (작품이 아닌 사진일 가능성)
_NOISE_KW = ("facade", "street view", "exhibition prep", "voorbereiding",
             "building exterior", "museum interior", "car park", "parking")


def _valid_name(name: str | None) -> str | None:
    if not name:
        return None
    name = name.strip(" .,'\"()")
    if 2 <= len(name) <= 60 and not any(m in name.lower() for m in _UPLOADER_MARKS):
        return name
    return None


def _extract_artist(raw: str | None, title: str | None,
                    desc: str | None, source: str) -> str | None:
    """작품 '창작자' 추출.

    Met: raw(artistDisplayName)이 곧 창작자.
    Wikimedia: raw 는 대개 '사진가' → 무시하고 title/desc 에서 창작자 추출.
    확정 못 하면 None (describe 단계 LLM 이 이미지+desc 로 최종 확정).
    """
    if source == "met":
        return _valid_name(raw)

    title = title or ""
    desc = desc or ""
    # 1) title 의 'by <Artist>'
    m = re.search(r"\bby\s+([^,;0-9]+)", title, re.IGNORECASE)
    if (name := _valid_name(m.group(1) if m else None)):
        return name
    # 2) desc 의 '© <Artist>'
    m = re.search(r"©\s*([^.,;\n]+)", desc)
    if (name := _valid_name(m.group(1) if m else None)):
        return name
    # 3) desc 의 'by (South Korean) artist <Name>' 또는 'by <Name>'
    m = re.search(r"\bby\s+(?:[a-z\- ]*?artist\s+)?([A-Z][\w.\-]+(?:\s+[A-Z][\w.\-]+){0,2})",
                  desc)
    if (name := _valid_name(m.group(1) if m else None)):
        return name
    # 4) desc 서두 'Name, "Title"' 패턴
    m = re.match(r"([A-Z][\w.\-]+(?:\s+[A-Z][\w.\-]+){0,2}),\s*[\"']", desc)
    if (name := _valid_name(m.group(1) if m else None)):
        return name
    return None


def _parse_year(*texts: str | None) -> int | None:
    for t in texts:
        if not t:
            continue
        for m in _YEAR_RE.findall(t):
            y = int(m)
            if 1850 <= y <= 2026:
                return y
    return None


def _derive_tags(rec: dict) -> list[str]:
    blob = " ".join(filter(None, [rec.get("title"), rec.get("desc_src"),
                                  rec.get("materials_raw")])).lower()
    tags: list[str] = ["키네틱아트"]
    for kw, ko in _MEDIUM_KW.items():
        if kw in blob and ko not in tags:
            tags.append(ko)
    # 작가 성(姓) 태그 (문자/한글만, 노이즈 제거)
    if rec.get("artist"):
        surname = re.sub(r"[^A-Za-z가-힣]", "", rec["artist"].split()[-1])
        if len(surname) >= 2:
            tags.append(surname)
    return tags[:8]


DUP_HAMMING = 12  # dHash(256bit) 해밍 거리 이하 = 같은 이미지(재인코딩·크롭 소폭·리사이즈)


def _title_key(rec: dict) -> str | None:
    """작가가 확정된 경우에만 '작가|제목 전체' 일치를 중복으로 본다.
    (예전엔 제목 앞 3단어·숫자 제거로 비교해 연도/연번만 다른 '서로 다른 작품'을 합쳐 버렸다)"""
    artist = (rec.get("artist") or "").strip().lower()
    words = _WORD_RE.findall((rec.get("title") or "").lower())
    if not artist or len(words) < 2:
        return None
    return artist + "|" + " ".join(words)


# dHash 캐시 — 이전 배치 이미지(GIF 수십 MB 포함)를 매 실행마다 다시 디코딩하지 않도록.
# 키에 크기·mtime 을 넣어 파일이 바뀌면 자동으로 재계산된다. 값 "" = 판정 불가(단색).
_HASH_CACHE_PATH = config.DATASET_DIR / "dhash_cache.json"
_hash_cache: dict[str, str] = {}


def _load_hash_cache() -> None:
    if _HASH_CACHE_PATH.exists():
        try:
            _hash_cache.update(json.loads(_HASH_CACHE_PATH.read_text(encoding="utf-8")))
        except ValueError:
            pass


def _save_hash_cache() -> None:
    _HASH_CACHE_PATH.write_text(json.dumps(_hash_cache), encoding="utf-8")


def _hash_of(rec: dict) -> int | None:
    path = config.WORKS_DIR / (rec.get("image_file") or "")
    if not rec.get("image_file") or not path.exists():
        return None
    st = path.stat()
    key = f"{path.name}|{st.st_size}|{st.st_mtime_ns}"
    if key not in _hash_cache:
        try:
            h = imaging.dhash(path)
        except Exception:  # noqa: BLE001 — 해시 실패는 중복 판정만 건너뜀
            h = None
        _hash_cache[key] = format(h, "x") if h is not None else ""
    v = _hash_cache[key]
    return int(v, 16) if v else None


def _prior_hashes() -> list[int]:
    """이전 배치에서 이미 쓰고 있는(선별/설명된) 작품 이미지의 해시 — 배치 간 중복 방지."""
    out = []
    for path in config.prior_record_files():
        if not path.name.startswith("described"):
            continue
        for r in load_records(path):
            if r.get("selected") or r.get("description_ko"):
                h = _hash_of(r)
                if h is not None:
                    out.append(h)
    return out


def _score(rec: dict) -> int:
    s = 0
    if rec.get("artist"):
        s += 2
    d = rec.get("desc_src") or ""
    if len(d) >= 40:
        s += 2
    if len(d) >= 120:
        s += 1
    if rec.get("created_year"):
        s += 1
    if len(rec.get("tags") or []) >= 3:
        s += 1
    if max(rec.get("width") or 0, rec.get("height") or 0) >= 1200:
        s += 1
    blob = ((rec.get("title") or "") + " " + d).lower()
    if any(n in blob for n in _NOISE_KW):
        s -= 4
    if not rec.get("artist") and len(d) < 40:
        s -= 2
    return s


def main() -> int:
    print("== 스테이지 3: 정규화 + 선별 ==")
    config.guard_first_batch(config.ENRICHED_JSON)
    records = load_records(config.DOWNLOADED_JSON)
    print(f"입력 {len(records)}개")

    # 1) 정규화
    for r in records:
        raw_artist = r.get("artist")
        if r["source"] == "wikimedia":
            r["photographer"] = raw_artist   # 참고용(사진가)
        r["artist"] = _extract_artist(raw_artist, r.get("title"),
                                      r.get("desc_src"), r["source"])
        # 연도: 작품 설명/제목 우선 (사진 EXIF 날짜 year_raw 는 후순위)
        r["created_year"] = _parse_year(r.get("desc_src"), r.get("title"),
                                        r.get("year_raw"))
        r["materials"] = r.get("materials_raw")  # 상세 매체는 한글 생성 단계에서 보강
        r["tags"] = _derive_tags(r)

    # 2) 근접중복 제거 — 같은 이미지(dHash) 또는 같은 작가·같은 제목 전체 → 최대 해상도 1장.
    #    이전 배치에 이미 있는 이미지와 같은 것도 제외한다.
    _load_hash_cache()
    prior = set(_prior_hashes())
    kept_hashes: list[int] = list(prior)
    kept_titles: set[str] = set()
    unique: list[dict] = []
    dup_img = dup_title = dup_prior = 0
    by_area = sorted(records, key=lambda r: (r.get("width") or 0) * (r.get("height") or 0),
                     reverse=True)
    for r in by_area:
        h = _hash_of(r)
        if h is not None:
            near = [k for k in kept_hashes if imaging.hamming(h, k) <= DUP_HAMMING]
            if near:
                if any(k in prior for k in near):
                    dup_prior += 1
                else:
                    dup_img += 1
                continue
        tk = _title_key(r)
        if tk and tk in kept_titles:
            dup_title += 1
            continue
        if h is not None:
            kept_hashes.append(h)
        if tk:
            kept_titles.add(tk)
        unique.append(r)
    _save_hash_cache()
    print(f"근접중복 제거: {len(records)} → {len(unique)} "
          f"(같은 이미지 {dup_img}, 같은 작가·제목 {dup_title}, 이전 배치와 중복 {dup_prior})")

    # 3) 점수 → 상위 DESCRIBE_TARGET 선별
    for r in unique:
        r["_score"] = _score(r)
    unique.sort(key=lambda x: x["_score"], reverse=True)
    for i, r in enumerate(unique):
        r["selected"] = i < config.DESCRIBE_TARGET

    n_sel = sum(1 for r in unique if r["selected"])
    print(f"선별(한글 생성 대상): {n_sel}개 / 전체 {len(unique)}개")
    print(f"  점수 분포 상위: {[r['_score'] for r in unique[:5]]} ... "
          f"하위선별: {[r['_score'] for r in unique[max(0,n_sel-3):n_sel]]}")

    save_records(config.ENRICHED_JSON, unique)
    print(f"저장: {config.ENRICHED_JSON}")

    # 표본
    print("\n선별 표본 5개:")
    for r in unique[:5]:
        print(f"• [{r['local_id']}] {(r['title'] or '-')[:45]}  "
              f"작가:{r['artist'] or '-'}  연도:{r['created_year'] or '-'}")
        print(f"    태그:{r['tags']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
