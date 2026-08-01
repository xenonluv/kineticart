#!/usr/bin/env python3
"""스테이지 4: 한글 설명 생성 (하이브리드).

생성 엔진은 Claude Code 서브에이전트(외부 API 키 불필요).
이 스크립트는 두 역할만 한다:
  prepare : enriched.json 의 selected 레코드 → describe_queue.json (LLM 입력 번들)
  ingest  : LLM 결과(JSON 리스트) → described.json 병합 + texts/{id}.txt 기록

LLM 은 desc_src(원문 설명)를 '사실 근거'로 삼아 작가/연도/재료를 확정하고,
이미지를 함께 보고 한글 설명을 생성한다. 사진가/업로드 날짜는 작품 정보가 아님에 유의.

사용:
  python 4_describe_ko.py prepare
  python 4_describe_ko.py ingest <results.json>
"""
from __future__ import annotations

import sys

import config
from lib.models import load_records, save_records

# LLM 이 각 항목에 대해 반환해야 하는 필드(ingest 가 기대하는 스키마)
RESULT_FIELDS = (
    "local_id", "title_display", "artist", "created_year",
    "materials_ko", "description_ko", "detail_text_ko", "tags_ko",
    "uncertain", "notes",
)


def prepare() -> int:
    records = load_records(config.ENRICHED_JSON)
    selected = [r for r in records if r.get("selected")]
    queue = []
    for r in selected:
        queue.append({
            "local_id": r["local_id"],
            "image_file": r["image_file"],            # works/{image_file} 를 Read
            "source_title": r.get("title"),
            "desc_src": r.get("desc_src"),            # ★ 사실 근거
            "hint_artist": r.get("artist"),           # 힌트(틀릴 수 있음)
            "hint_year": r.get("created_year"),       # 힌트(사진날짜일 수 있음)
            "hint_materials": r.get("materials"),
            "hint_tags": r.get("tags"),
            "source_page_url": r.get("source_page_url"),
        })
    save_records(config.DATASET_DIR / "describe_queue.json", queue)
    print(f"describe_queue.json 저장: {len(queue)}개 (works/ 이미지 + desc_src 근거)")
    return 0


def ingest(results_path: str) -> int:
    results = load_records(results_path)
    by_id = {r["local_id"]: r for r in results}

    records = load_records(config.ENRICHED_JSON)
    config.TEXTS_DIR.mkdir(parents=True, exist_ok=True)

    merged = 0
    for r in records:
        res = by_id.get(r["local_id"])
        if not res:
            continue
        r["title"] = res.get("title_display") or r.get("title")
        # 작가/연도는 LLM(이미지+원문 근거)이 최종 권위자.
        # LLM 이 null 로 두면 '미상'이 정답 — enrich 힌트(사진가/촬영일)로 되살리지 않는다.
        r["artist"] = res.get("artist")
        r["created_year"] = res.get("created_year")
        r["materials"] = res.get("materials_ko") or r.get("materials")
        r["description_ko"] = res.get("description_ko")
        r["detail_text_ko"] = res.get("detail_text_ko")
        if res.get("tags_ko"):
            r["tags"] = res["tags_ko"]
        r["notes"] = res.get("notes")
        r["review_status"] = "needs_review" if res.get("uncertain") else "auto_ok"

        # 상세 원문 → texts/{id}.txt
        if r.get("detail_text_ko"):
            text_name = f"{r['local_id']}.txt"
            (config.TEXTS_DIR / text_name).write_text(
                r["detail_text_ko"], encoding="utf-8")
            r["text_file"] = text_name
        merged += 1

    save_records(config.DESCRIBED_JSON, records)
    print(f"ingest 완료: {merged}개 병합 → {config.DESCRIBED_JSON}")
    print(f"texts/ 파일 기록 완료")
    return 0


def main() -> int:
    if len(sys.argv) < 2 or sys.argv[1] not in ("prepare", "ingest"):
        print(__doc__)
        return 1
    if sys.argv[1] == "prepare":
        return prepare()
    if len(sys.argv) < 3:
        print("ingest 는 결과 JSON 경로가 필요합니다.")
        return 1
    return ingest(sys.argv[2])


if __name__ == "__main__":
    sys.exit(main())
