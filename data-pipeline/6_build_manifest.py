#!/usr/bin/env python3
"""스테이지 6: 최종 산출물 생성.

described.json (+ 선택적 review_decisions.json) 에서 최종 TARGET_FINAL 개를 선별해:
  - dataset/manifest.json      : Supabase kinetic_artworks 스키마(+보강) 전 필드
  - dataset/seed.sql           : INSERT 문 (인프라 준비 후 service_role 로 1회 실행)
  - dataset/schema_additions.sql : video_url/license/attribution/source_url 컬럼 추가
  - dataset/deploy_files.txt    : 집 Mac(works/·texts/)으로 복사할 최종 파일 목록

선별 우선순위: 승인(approved) > auto_ok > needs_review, 동점은 품질점수·id.
'키네틱 작품 아님' 플래그는 명시 승인 없으면 제외.

실행:  python 6_build_manifest.py
"""
from __future__ import annotations

import json
import sys

import config
from lib.models import load_records, save_records

DECISIONS = config.DATASET_DIR / "review_decisions.json"
SCHEMA_SQL = config.DATASET_DIR / "schema_additions.sql"
DEPLOY_TXT = config.DATASET_DIR / "deploy_files.txt"


_NOISE_MARKERS = ("키네틱 작품 아님", "최종 제외", "제외 검토", "키네틱 아님",
                  "정물", "not kinetic", "not-really-kinetic", "not really kinetic")


def _rank(r: dict, decision: str | None) -> tuple:
    d_rank = {"approved": 3, "rejected": -1}.get(decision, 0)
    auto = 1 if r.get("review_status") == "auto_ok" else 0
    has_artist = 1 if r.get("artist") else 0
    return (d_rank, has_artist, auto, r.get("_score", 0))


def _is_noise(r: dict) -> bool:
    n = (r.get("notes") or "").lower()
    return any(m.lower() in n for m in _NOISE_MARKERS)


_LUMINO_PATTERNS = ("lumino", "루미노", "kinetic spoon", "sstar", "striangle",
                    "kinetic ec", "kinetic tri")


def _is_lumino(r: dict) -> bool:
    # 원본 메타 + 한글 제목(title_display) 모두 검사 — 원본에 'lumino' 가 없어도
    # 서브에이전트가 '루미노 …'로 식별했거나 시리즈 파일명 패턴이면 익명 LED 공예로 간주.
    blob = " ".join([r.get("title") or "", r.get("desc_src") or "",
                     r.get("source_title") or ""]).lower()
    return any(p in blob for p in _LUMINO_PATTERNS)


def _select(records: list[dict], decisions: dict) -> list[dict]:
    pool = [r for r in records if r.get("description_ko")]
    # 거부 제외
    pool = [r for r in pool if decisions.get(r["local_id"]) != "rejected"]
    # 노이즈(키네틱 아님) 제외 — 단, 명시 승인은 유지
    pool = [r for r in pool
            if not _is_noise(r) or decisions.get(r["local_id"]) == "approved"]

    key = lambda r: _rank(r, decisions.get(r["local_id"]))
    non_lumino = sorted((r for r in pool if not _is_lumino(r)), key=key, reverse=True)
    lumino = sorted((r for r in pool if _is_lumino(r)), key=key, reverse=True)

    # 비-Lumino(식별작품 우선)로 채우고, 부족분만 대표 Lumino 소수로 보충
    selected = non_lumino[:config.TARGET_FINAL]
    if len(selected) < config.TARGET_FINAL:
        need = config.TARGET_FINAL - len(selected)
        selected += lumino[:min(config.LUMINO_CAP, need)]
    return selected


def _sql_str(v) -> str:
    if v is None or v == "":
        return "NULL"
    return "'" + str(v).replace("'", "''") + "'"


def _sql_int(v) -> str:
    return str(int(v)) if v not in (None, "") else "NULL"


def _sql_num(v) -> str:
    return str(v) if v not in (None, "") else "NULL"


def _sql_arr(tags) -> str:
    if not tags:
        return "NULL"
    inner = ",".join("'" + str(t).replace("'", "''") + "'" for t in tags)
    return f"ARRAY[{inner}]::text[]"


def _manifest_row(r: dict) -> dict:
    base = config.BASE_IMAGE_URL.rstrip("/")
    return {
        "local_id": r["local_id"],
        "title": r.get("title"),
        "artist": r.get("artist"),
        "description": r.get("description_ko"),
        "created_year": r.get("created_year"),
        "materials": r.get("materials"),
        "dimensions": r.get("dimensions"),
        "tags": r.get("tags") or [],
        "thumbnail_url": None,
        "image_url": f"{base}/works/{r['image_file']}",
        "detail_text_url": f"{base}/texts/{r['text_file']}" if r.get("text_file") else None,
        "video_url": r.get("video_url"),
        "file_size_mb": r.get("file_size_mb"),
        "license": r.get("license"),
        "attribution": r.get("attribution"),
        "source_url": r.get("source_page_url"),
        "embedding": r.get("embedding"),  # 스테이지 5b 산출(의미검색용, 없으면 None)
    }


def _seed_sql(rows: list[dict]) -> str:
    cols = ("title", "artist", "description", "created_year", "materials", "dimensions",
            "tags", "image_url", "detail_text_url", "video_url",
            "file_size_mb", "license", "attribution", "source_url")
    lines = [
        "-- 키네틱 아트 시드 데이터 (자동 생성)",
        "-- 실행 전 schema_additions.sql 먼저 적용하세요.",
        "-- service_role 권한으로 1회만 실행.",
        "",
    ]
    for r in rows:
        vals = [
            _sql_str(r["title"]), _sql_str(r["artist"]), _sql_str(r["description"]),
            _sql_int(r["created_year"]), _sql_str(r["materials"]),
            _sql_str(r["dimensions"]), _sql_arr(r["tags"]),
            _sql_str(r["image_url"]), _sql_str(r["detail_text_url"]),
            _sql_str(r["video_url"]), _sql_num(r["file_size_mb"]),
            _sql_str(r["license"]), _sql_str(r["attribution"]),
            _sql_str(r["source_url"]),
        ]
        lines.append(
            f"insert into kinetic_artworks ({', '.join(cols)})\n"
            f"values ({', '.join(vals)});"
        )
    return "\n".join(lines) + "\n"


_SCHEMA_ADDITIONS = """-- kinetic_artworks 스키마 보강 (환경설치.md 기본 스키마에 추가)
-- 작가(검색 핵심) + 출처 표기 의무 + 영상 링크 반영. 1회 실행.
alter table kinetic_artworks add column if not exists artist text;
alter table kinetic_artworks add column if not exists video_url text;
alter table kinetic_artworks add column if not exists license text;
alter table kinetic_artworks add column if not exists attribution text;
alter table kinetic_artworks add column if not exists source_url text;
"""


def main() -> int:
    if not config.DESCRIBED_JSON.exists():
        print(f"먼저 4_describe_ko.py ingest 로 {config.DESCRIBED_JSON} 를 만드세요.")
        return 1

    records = load_records(config.DESCRIBED_JSON)
    decisions = {}
    if DECISIONS.exists():
        decisions = json.load(open(DECISIONS, encoding="utf-8"))
        print(f"검수 결정 반영: {DECISIONS.name} "
              f"(승인 {sum(v=='approved' for v in decisions.values())}, "
              f"거부 {sum(v=='rejected' for v in decisions.values())})")

    selected = _select(records, decisions)
    rows = [_manifest_row(r) for r in selected]

    save_records(config.MANIFEST_JSON, rows)
    config.SEED_SQL.write_text(_seed_sql(rows), encoding="utf-8")
    SCHEMA_SQL.write_text(_SCHEMA_ADDITIONS, encoding="utf-8")

    # 배포 파일 목록 (집 Mac 으로 복사할 것)
    deploy = []
    for r in selected:
        deploy.append(f"works/{r['image_file']}")
        if r.get("text_file"):
            deploy.append(f"texts/{r['text_file']}")
    DEPLOY_TXT.write_text("\n".join(deploy) + "\n", encoding="utf-8")

    # 요약
    n_flagged = sum(1 for r in selected if r.get("review_status") == "needs_review")
    print(f"\n최종 선별: {len(selected)}개 / 목표 {config.TARGET_FINAL}")
    print(f"  (그 중 needs_review 포함: {n_flagged}개 — review.html 로 최종 확인 권장)")
    print(f"저장:")
    print(f"  {config.MANIFEST_JSON}")
    print(f"  {config.SEED_SQL}")
    print(f"  {SCHEMA_SQL}")
    print(f"  {DEPLOY_TXT}  ({len(deploy)}개 파일)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
