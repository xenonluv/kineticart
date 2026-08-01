"""후보(candidate) 레코드 스키마 + JSON 입출력 헬퍼.

파이프라인 전 스테이지가 이 dict 구조를 이어받아 필드를 채워 나간다.
Supabase kinetic_artworks 스키마(+ video_url/license/attribution/source_url 보강)와 정렬된다.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any


# 하나의 후보 작품 레코드. None = 아직 미채움.
def new_candidate(**kwargs: Any) -> dict:
    rec = {
        # --- 출처/원본 (discover) ---
        "source": None,            # "wikimedia" | "met"
        "source_id": None,         # 소스 내부 ID (pageid / objectID)
        "source_page_url": None,   # 원본 설명 페이지 URL
        "image_src_url": None,     # 다운로드용 이미지 URL (해상도 상한 반영본)
        "image_orig_url": None,    # 원본 풀해상도 URL (참고)
        "mime": None,

        # --- 라이선스 (discover) ---
        "license": None,            # 정규화 라벨: "CC0" | "Public Domain" | "CC-BY-4.0" ...
        "license_url": None,
        "attribution": None,        # CC-BY 계열 출처 표기 문구
        "attribution_required": False,
        "license_allowed": False,   # 재배포 허용 여부

        # --- 원본 메타 (discover, 언어 무관) ---
        "title": None,
        "artist": None,
        "year_raw": None,           # 원문 날짜 문자열
        "materials_raw": None,      # 원문 재료/매체
        "dimensions_raw": None,
        "desc_src": None,           # 원문 설명(영문 등)

        # --- 다운로드 결과 (2_download) ---
        "local_id": None,           # "001" 형식 순번
        "image_file": None,         # "001.jpg"
        "width": None,
        "height": None,
        "file_size_mb": None,

        # --- 정규화 메타 (3_enrich) ---
        "created_year": None,       # int
        "materials": None,
        "dimensions": None,
        "tags": [],
        "video_url": None,

        # --- 한글 설명 (4_describe_ko) ---
        "description_ko": None,     # 짧은 요약 (DB description)
        "detail_text_ko": None,     # 긴 원문 (texts/NNN.txt)
        "text_file": None,          # "001.txt"

        # --- 검수 (5_review) ---
        "review_status": "pending",  # pending | approved | rejected
        "notes": None,               # 불확실 플래그/메모
    }
    rec.update(kwargs)
    return rec


def load_records(path: Path) -> list[dict]:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_records(path: Path, records: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(records, f, ensure_ascii=False, indent=2)
