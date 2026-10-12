#!/usr/bin/env python3
"""스테이지 6: 최종 산출물 생성.

described.json (+ 선택적 review_decisions.json) 에서 최종 TARGET_FINAL 개를 선별해:
  - dataset/manifest.json      : Supabase kinetic_artworks 스키마(+보강) 전 필드
  - dataset/seed.sql           : INSERT 문 (인프라 준비 후 service_role 로 1회 실행)
  - dataset/schema_additions.sql : video_url/license/attribution/source_url 컬럼 추가
  - dataset/deploy_files.txt    : 집 Mac(works/·texts/)으로 복사할 최종 파일 목록

  - dataset/seed_sync.sql      : 라이브 DB 를 manifest 와 '일치'시키는 트랜잭션
                                 (upsert + manifest 에 없는 행 삭제). 적용 전 pg_dump 백업 필수.

선별 우선순위: 승인(approved) > auto_ok > needs_review, 동점은 품질점수·id.
'키네틱 작품 아님' 플래그는 명시 승인 없으면 제외.
검증 게이트(lib/validate.py): 이미지 미확인 fallback·한글 없음·원문 복붙은 무조건 제외.

실행:  python 6_build_manifest.py
       python 6_build_manifest.py --mark-live   # DB 적용 성공 후: pinned_live.json ← manifest id
"""
from __future__ import annotations

import hashlib
import json
import re
import sys

import check_manifest
import config
from lib.models import load_records, save_records
from lib.validate import coerce_year, unverified_reason

PINNED = config.DATASET_DIR / "pinned_live.json"   # 이미 라이브 DB/파일서버에 배포된 local_id
SCHEMA_SQL = config.DATASET_DIR / "schema_additions.sql"
SYNC_SQL = config.DATASET_DIR / "seed_sync.sql"
DEPLOY_TXT = config.DATASET_DIR / "deploy_files.txt"

# seed_sync 가 한 번에 지울 수 있는 기존 행 비율 상한 — 잘못 만든 manifest 로 DB 를 비우는 사고 방지
MAX_DELETE_RATIO = 0.5


def _load_decisions() -> dict[str, str]:
    """모든 배치의 검수 결정(review_decisions*.json)을 병합. 같은 id 는 뒤 파일이 우선."""
    merged: dict[str, str] = {}
    files = sorted(config.DATASET_DIR.glob("review_decisions*.json"))
    for f in files:
        d = json.load(open(f, encoding="utf-8"))
        merged.update({str(k): v for k, v in d.items() if v in ("approved", "rejected")})
        print(f"  검수 결정: {f.name} (승인 {sum(v == 'approved' for v in d.values())}, "
              f"거부 {sum(v == 'rejected' for v in d.values())})")
    if not files:
        print("  검수 결정 파일 없음(review_decisions*.json) — 자동 판정만 사용")
    return merged


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


# 익명 업로더의 반복 LED 장신구 시리즈(Lumino). 파일명 연작(Kinetic ec3, spoon3, swb1 …)과
# 공통 원문 문구로 식별한다. 단어 경계를 써서 'IlluminoCity' 같은 실제 작품을 오탐하지 않는다.
_LUMINO_RE = re.compile(
    r"\blumino\b|(?<![가-힣])루미노|\bkinetic[ _-]?(?:spoon|sstar|striangle|ec|tri|swb)\d*\b"
    r"|created with steel and led",
    re.I,
)


def _is_lumino(r: dict) -> bool:
    # 원본 메타 + 한글 제목(title_display) 모두 검사 — 원본에 'lumino' 가 없어도
    # 서브에이전트가 '루미노 …'로 식별했거나 시리즈 파일명 패턴이면 익명 LED 공예로 간주.
    blob = " ".join([r.get("title") or "", r.get("desc_src") or "",
                     r.get("source_title") or ""])
    return bool(_LUMINO_RE.search(blob))


def _select(records: list[dict], decisions: dict) -> list[dict]:
    # 1) 검증 게이트 — 이미지 미확인 fallback/한글 없음/원문 복붙/source_url 없음은 무조건 제외
    #    (사람이 '승인'해도 내용 자체가 가짜면 공개할 수 없다)
    gated: dict[str, int] = {}
    pool = []
    for r in records:
        why = unverified_reason(r)
        if why is None and not r.get("source_page_url"):
            why = "source_url 없음"
        if why is None and not r.get("image_file"):
            why = "이미지 없음"
        if why:
            gated[why] = gated.get(why, 0) + 1
            continue
        pool.append(r)
    if gated:
        print(f"  검증 게이트 제외: {sum(gated.values())}건 {gated}")

    # 2) 라이브 작품(pinned)은 필터 '이전'에 분리 — 노이즈 판정 때문에 조용히 빠지지 않게.
    #    명시 거부만 예외(경고와 함께 제외 → seed_sync 가 DB 에서도 삭제).
    pinned_ids = set(json.load(open(PINNED, encoding="utf-8"))) if PINNED.exists() else set()
    pinned = []
    for r in pool:
        if r["local_id"] not in pinned_ids:
            continue
        if decisions.get(r["local_id"]) == "rejected":
            print(f"  ⚠ 라이브 작품 {r['local_id']} 명시 거부 → 제외(DB 에서도 삭제됨)")
            continue
        if _is_noise(r):
            print(f"  ⚠ 라이브 작품 {r['local_id']} 노이즈 표시 — 유지함(필요시 검수에서 거부)")
        pinned.append(r)
    lost = sorted(pinned_ids - {r["local_id"] for r in pinned})
    if lost:
        print(f"  ⚠ 라이브 작품 {len(lost)}건이 manifest 에서 빠짐(게이트/거부): {lost[:15]}")
    pool = [r for r in pool if r["local_id"] not in pinned_ids]

    # 3) 신규 후보: 거부·노이즈 제외 — 단, 노이즈는 명시 승인 시 유지
    pool = [r for r in pool if decisions.get(r["local_id"]) != "rejected"]
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
    return pinned + selected


def _sql_str(v) -> str:
    if v is None or v == "":
        return "NULL"
    return "'" + str(v).replace("'", "''") + "'"


def _sql_int(v) -> str:
    return str(int(v)) if v is not None else "NULL"


def _sql_num(v) -> str:
    return str(v) if v not in (None, "") else "NULL"


def _sql_arr(tags) -> str:
    if not tags:
        return "NULL"
    inner = ",".join("'" + str(t).replace("'", "''") + "'" for t in tags)
    return f"ARRAY[{inner}]::text[]"


def _versioned_url(base: str, sub: str, path) -> str | None:
    """파생본 URL + ?v=<내용해시>. 내용이 바뀌면 URL 이 바뀌므로 immutable 캐시가 안전."""
    if not path.exists():
        return None
    v = hashlib.sha1(path.read_bytes()).hexdigest()[:10]
    return f"{base}/{sub}/{path.name}?v={v}"


def _manifest_row(r: dict) -> dict:
    base = config.BASE_IMAGE_URL.rstrip("/")
    stem = r["image_file"].rsplit(".", 1)[0]
    return {
        "local_id": r["local_id"],
        "title": r.get("title"),
        "artist": r.get("artist"),
        "description": r.get("description_ko"),
        "created_year": coerce_year(r.get("created_year")),   # "c. 1972" 등도 int 로
        "materials": r.get("materials"),
        "dimensions": r.get("dimensions"),
        "tags": r.get("tags") or [],
        "thumbnail_url": _versioned_url(base, "cards", config.CARDS_DIR / f"{stem}.webp"),
        "display_url": _versioned_url(base, "display", config.DISPLAY_DIR / f"{stem}.webp"),
        "image_url": f"{base}/works/{r['image_file']}",
        "detail_text_url": f"{base}/texts/{r['text_file']}" if r.get("text_file") else None,
        "video_url": r.get("video_url"),
        "file_size_mb": r.get("file_size_mb"),
        "license": r.get("license"),
        "attribution": r.get("attribution"),
        "source_url": r.get("source_page_url"),
        "embedding": r.get("embedding"),  # 스테이지 5b 산출(의미검색용, 없으면 None)
    }


_COLS = ("title", "artist", "description", "created_year", "materials", "dimensions",
         "tags", "thumbnail_url", "display_url", "image_url", "detail_text_url", "video_url",
         "file_size_mb", "license", "attribution", "source_url")

# 스키마 보강 + source_url 유니크 인덱스(중복 행이 있으면 명확한 오류로 중단)
_PREAMBLE = [
    "alter table kinetic_artworks add column if not exists display_url text;",
    "do $$ begin",
    "  if exists (select 1 from kinetic_artworks where source_url is not null",
    "             group by source_url having count(*) > 1) then",
    "    raise exception 'kinetic_artworks 에 source_url 중복 행이 있어 중단 — 먼저 정리하세요';",
    "  end if;",
    "end $$;",
    "create unique index if not exists kinetic_artworks_source_url_key",
    "  on kinetic_artworks (source_url);",
]


def _upsert(r: dict) -> str:
    vals = [
        _sql_str(r["title"]), _sql_str(r["artist"]), _sql_str(r["description"]),
        _sql_int(r["created_year"]), _sql_str(r["materials"]),
        _sql_str(r["dimensions"]), _sql_arr(r["tags"]),
        _sql_str(r["thumbnail_url"]), _sql_str(r["display_url"]),
        _sql_str(r["image_url"]), _sql_str(r["detail_text_url"]),
        _sql_str(r["video_url"]), _sql_num(r["file_size_mb"]),
        _sql_str(r["license"]), _sql_str(r["attribution"]),
        _sql_str(r["source_url"]),
    ]
    sets = ", ".join(f"{c} = excluded.{c}" for c in _COLS if c != "source_url")
    return (f"insert into kinetic_artworks ({', '.join(_COLS)})\n"
            f"values ({', '.join(vals)})\n"
            f"on conflict (source_url) do update set {sets}, updated_at = now();")


def _seed_sql(rows: list[dict]) -> str:
    """최초 기동(db/init) 및 수동 재적재용. 멱등 upsert — 기존 행은 최신 내용으로 갱신된다."""
    lines = [
        "-- 키네틱 아트 시드 데이터 (자동 생성 — 6_build_manifest.py)",
        "-- 멱등: source_url 유니크 + ON CONFLICT DO UPDATE (재실행 시 최신 내용으로 갱신).",
        "-- 삭제는 하지 않는다. 라이브 DB 를 manifest 와 '일치'시키려면 seed_sync.sql 사용.",
        "",
        *_PREAMBLE,
        "",
    ]
    lines += [_upsert(r) for r in rows]
    return "\n".join(lines) + "\n"


def _sync_sql(rows: list[dict]) -> str:
    """라이브 DB 를 manifest 와 정확히 일치시킨다: upsert + manifest 에 없는 행 삭제.
    단일 트랜잭션 — 중간 실패 시 전부 롤백. 삭제 비율이 MAX_DELETE_RATIO 를 넘으면 중단."""
    keep = ", ".join(f"({_sql_str(r['source_url'])})" for r in rows)
    lines = [
        "-- 라이브 DB ↔ manifest 동기화 (자동 생성 — 6_build_manifest.py)",
        "-- 적용 전 반드시 백업: docker exec kinerag-db pg_dump -U postgres kinerag > backup.sql",
        "-- 적용: docker exec -i kinerag-db psql -U postgres -d kinerag -v ON_ERROR_STOP=1 < seed_sync.sql",
        "begin;",
        *_PREAMBLE,
        "create temp table _keep (source_url text primary key) on commit drop;",
        f"insert into _keep (source_url) values {keep};",
        "do $$ declare n_all int; n_del int; begin",
        "  select count(*) into n_all from kinetic_artworks;",
        "  select count(*) into n_del from kinetic_artworks k",
        "   where k.source_url is null or not exists (select 1 from _keep x where x.source_url = k.source_url);",
        f"  if n_all > 0 and n_del > n_all * {MAX_DELETE_RATIO} then",
        "    raise exception '삭제 대상 %/% 행 — 상한(%) 초과로 중단. manifest 를 확인하세요', n_del, n_all, "
        f"'{int(MAX_DELETE_RATIO * 100)}%';",
        "  end if;",
        "  raise notice 'seed_sync: 기존 % 행 중 % 행 삭제 예정', n_all, n_del;",
        "end $$;",
        "",
    ]
    lines += [_upsert(r) for r in rows]
    lines += [
        "",
        "delete from kinetic_artworks k",
        " where k.source_url is null or not exists (select 1 from _keep x where x.source_url = k.source_url);",
        "commit;",
    ]
    return "\n".join(lines) + "\n"


_SCHEMA_ADDITIONS = """-- kinetic_artworks 스키마 보강 (환경설치.md 기본 스키마에 추가)
-- 작가(검색 핵심) + 출처 표기 의무 + 영상 링크 반영. 1회 실행.
alter table kinetic_artworks add column if not exists artist text;
alter table kinetic_artworks add column if not exists video_url text;
alter table kinetic_artworks add column if not exists license text;
alter table kinetic_artworks add column if not exists attribution text;
alter table kinetic_artworks add column if not exists source_url text;
alter table kinetic_artworks add column if not exists display_url text;
"""


def mark_live() -> int:
    """DB 적용(seed_sync) 성공 '후'에만 실행 — 현재 manifest 를 라이브 고정 목록으로 기록.
    다음 배치에서 라이브 작품이 선별 정원 경쟁에 밀려 manifest/배포 목록에서 빠지는 것을 막는다."""
    rows = load_records(config.MANIFEST_JSON)
    ids = sorted({r["local_id"] for r in rows})
    prev = set(json.load(open(PINNED, encoding="utf-8"))) if PINNED.exists() else set()
    PINNED.write_text(json.dumps(ids, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"pinned_live.json 갱신: {len(prev)} → {len(ids)} "
          f"(추가 {len(set(ids) - prev)}, 제거 {len(prev - set(ids))})")
    return 0


def main() -> int:
    if "--mark-live" in sys.argv:
        return mark_live()
    sources = config.all_described_files()
    if not sources:
        print(f"먼저 4_describe_ko.py ingest 로 {config.DESCRIBED_JSON} 를 만드세요.")
        return 1

    # 모든 배치(1차 described.json + 2차 described_b2.json …)를 local_id 기준 통합
    records = []
    seen_ids: set[str] = set()
    for path in sources:
        batch = load_records(path)
        added = [r for r in batch if r.get("local_id") not in seen_ids]
        seen_ids.update(r["local_id"] for r in added if r.get("local_id"))
        records.extend(added)
        print(f"  배치 로드: {path.name} {len(batch)}개 (신규 {len(added)})")
    decisions = _load_decisions()

    selected = _select(records, decisions)
    rows = [_manifest_row(r) for r in selected]

    no_deriv = [r["local_id"] for r in rows if not r["thumbnail_url"] or not r["display_url"]]
    if no_deriv:
        print(f"  ⚠ 파생 이미지 없음 {len(no_deriv)}건(원본으로 폴백) — 2b_derivatives.py 실행 권장: "
              f"{no_deriv[:10]}")

    errors = check_manifest.check(rows)
    if errors:
        print(f"✗ manifest 검사 실패 {len(errors)}건 — 저장하지 않고 중단:")
        for e in errors[:30]:
            print(f"  - {e}")
        return 1

    save_records(config.MANIFEST_JSON, rows)
    config.SEED_SQL.write_text(_seed_sql(rows), encoding="utf-8")
    SYNC_SQL.write_text(_sync_sql(rows), encoding="utf-8")
    SCHEMA_SQL.write_text(_SCHEMA_ADDITIONS, encoding="utf-8")

    # 배포 파일 목록 (집 Mac 으로 복사할 것)
    deploy = []
    for r in selected:
        stem = r["image_file"].rsplit(".", 1)[0]
        deploy.append(f"works/{r['image_file']}")
        for d, sub in ((config.CARDS_DIR, "cards"), (config.THUMBS_DIR, "thumbs"),
                       (config.DISPLAY_DIR, "display")):
            if (d / f"{stem}.webp").exists():
                deploy.append(f"{sub}/{stem}.webp")
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
    print(f"  {SYNC_SQL}   ← 라이브 DB 동기화(백업 후 적용, 이후 --mark-live)")
    print(f"  {SCHEMA_SQL}")
    print(f"  {DEPLOY_TXT}  ({len(deploy)}개 파일)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
