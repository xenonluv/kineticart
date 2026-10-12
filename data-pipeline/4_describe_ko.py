#!/usr/bin/env python3
"""스테이지 4: 한글 설명 생성 (하이브리드).

생성 엔진은 Claude Code 서브에이전트(외부 API 키 불필요). 이 스크립트는 입출력만 맡는다:
  prepare : 아직 '검증된 설명'이 없는 selected 레코드 → describe_queue{_배치}.json (멱등)
  split   : 큐 → dataset/desc_out{_배치}/run_<시각>/in_NN.json (파트당 --size 개, 기본 15)
  merge   : run 디렉토리의 part_NN.json 을 검증·수집 → merged.json → ingest
  ingest  : LLM 결과(JSON 리스트) → described{_배치}.json 병합 + texts/{id}.txt 기록

서브에이전트 실행 규칙(README '4단계' 참조):
  - 모델 haiku, 파트당 15건, 동시 최대 3개, 하나 끝나면 다음 하나 투입(순차 교대)
  - 입력 이미지는 thumbs/NNN.webp(장변 768) — 원본(2000px) 대비 비전 토큰 약 70% 절감
  - 실패/429 파트는 비워 둔다. fallback(원문 복사로 채우기) 금지 — merge 가 거르고,
    다음 prepare 가 자동으로 다시 큐에 넣는다.

LLM 은 desc_src(원문 설명)를 '사실 근거'로 삼아 작가/연도/재료를 확정하고,
이미지를 함께 보고 한글 설명을 생성한다. 사진가/업로드 날짜는 작품 정보가 아님에 유의.

사용:
  python 4_describe_ko.py prepare
  python 4_describe_ko.py split [--size 15]
  python 4_describe_ko.py merge <run_dir>
  python 4_describe_ko.py ingest <results.json>
"""
from __future__ import annotations

import html
import json
import re
import sys
import time
from pathlib import Path

import config
from lib.models import load_records, save_records
from lib.validate import HANGUL, coerce_year, is_verified, unverified_reason

# LLM 이 각 항목에 대해 반환해야 하는 필드(ingest 가 기대하는 스키마)
RESULT_FIELDS = (
    "local_id", "title_display", "artist", "created_year",
    "materials_ko", "description_ko", "detail_text_ko", "tags_ko",
    "uncertain", "notes",
)
QUEUE_JSON = config.DATASET_DIR / f"describe_queue{config._SFX}.json"
OUT_ROOT = config.DATASET_DIR / f"desc_out{config._SFX}"
DESC_SRC_MAX = 600   # 큐에 싣는 원문 길이 상한(입력 토큰 절감)

_TAG = re.compile(r"<[^>]+>")
_WS = re.compile(r"\s+")


def _clean_src(text: str | None) -> str | None:
    if not text:
        return None
    t = _WS.sub(" ", html.unescape(_TAG.sub(" ", text))).strip()
    return (t[:DESC_SRC_MAX] + "…") if len(t) > DESC_SRC_MAX else (t or None)


def _base_records() -> list[dict]:
    """설명 상태를 아는 described 가 있으면 그것을, 없으면 enriched 를 기준으로."""
    return load_records(config.DESCRIBED_JSON if config.DESCRIBED_JSON.exists()
                        else config.ENRICHED_JSON)


def prepare() -> int:
    records = _base_records()
    selected = [r for r in records if r.get("selected")]

    # 사전검수(5_build_review.py prescreen)에서 거부한 id 는 설명 생성에서 제외
    decisions_path = config.DATASET_DIR / f"review_decisions{config._SFX}.json"
    rejected = set()
    if decisions_path.exists():
        decisions = json.loads(decisions_path.read_text(encoding="utf-8"))
        rejected = {k for k, v in decisions.items() if v == "rejected"}

    queue, skip = [], {"검증 완료": 0, "LLM 거부": 0, "사전검수 거부": 0, "썸네일 없음": 0}
    for r in selected:
        if r["local_id"] in rejected:
            skip["사전검수 거부"] += 1
            continue
        if r.get("review_status") == "rejected":
            skip["LLM 거부"] += 1        # 이미지를 보고 '키네틱 아님'으로 판정된 건 다시 안 돌린다
            continue
        if is_verified(r):
            skip["검증 완료"] += 1        # 멱등: 이미 정상 설명이 있으면 건너뜀
            continue
        stem = r["image_file"].rsplit(".", 1)[0]
        thumb = config.THUMBS_DIR / f"{stem}.webp"
        if not thumb.exists():
            skip["썸네일 없음"] += 1
            print(f"  ⚠ {r['local_id']} 썸네일 없음 — 2b_derivatives.py 먼저 실행")
            continue
        queue.append({
            "local_id": r["local_id"],
            "image": str(thumb),                         # 서브에이전트가 Read 할 경로(768px)
            "source_title": r.get("source_title") or r.get("title"),
            "desc_src": _clean_src(r.get("desc_src")),   # ★ 사실 근거
            "hint_artist": r.get("artist"),              # 힌트(사진가일 수 있음)
            "hint_year": r.get("created_year"),          # 힌트(촬영일일 수 있음)
            "hint_materials": r.get("materials"),
        })
    save_records(QUEUE_JSON, queue)
    print(f"{QUEUE_JSON.name} 저장: {len(queue)}개 / 건너뜀 {skip}")
    return 0


def split(size: int) -> int:
    if not QUEUE_JSON.exists():
        print("먼저 prepare 를 실행하세요.")
        return 1
    queue = load_records(QUEUE_JSON)
    if not queue:
        print("큐가 비어 있음 — 처리할 항목 없음.")
        return 0
    run_dir = OUT_ROOT / time.strftime("run_%Y%m%d_%H%M%S")
    run_dir.mkdir(parents=True, exist_ok=False)
    parts = [queue[i:i + size] for i in range(0, len(queue), size)]
    for i, part in enumerate(parts):
        save_records(run_dir / f"in_{i:02d}.json", part)
    print(f"{run_dir} : 파트 {len(parts)}개 × 최대 {size}건 (총 {len(queue)}건)")
    print("다음: 서브에이전트(haiku, 동시 최대 3)로 in_NN.json → part_NN.json, 끝나면 merge")
    return 0


def _check_item(res: dict) -> str | None:
    """병합 전 결과 1건 검증. 문제면 사유 반환(→ 버리고 다음 prepare 에서 재큐잉)."""
    if res.get("reject") is True:
        return None if (res.get("notes") or "").strip() else "거부 사유(notes) 없음"
    for f in ("title_display", "description_ko", "detail_text_ko"):
        if not (res.get(f) or "").strip():
            return f"{f} 비어 있음"
    if not HANGUL.search(res["description_ko"]):
        return "description_ko 한글 없음"
    probe = {"description_ko": res["description_ko"], "detail_text_ko": res["detail_text_ko"],
             "notes": res.get("notes")}
    return unverified_reason(probe)


def merge(run_dir: str) -> int:
    rd = Path(run_dir)
    inputs = {}
    for f in sorted(rd.glob("in_*.json")):
        for q in load_records(f):
            inputs[q["local_id"]] = f.name
    results, bad, unknown = [], [], []
    for f in sorted(rd.glob("part_*.json")):
        try:
            items = load_records(f)
        except Exception as e:  # noqa: BLE001
            print(f"  ✗ {f.name} JSON 파싱 실패: {e}")
            continue
        for res in items:
            lid = str(res.get("local_id", ""))
            if lid not in inputs:
                unknown.append(lid)
                continue
            res["local_id"] = lid       # LLM 이 숫자로 내도 입력과 같은 문자열 키로
            why = _check_item(res)
            if why:
                bad.append((lid, why))
                continue
            if res.get("reject") is not True:
                res["created_year"] = coerce_year(res.get("created_year"))
                tags = [t for t in (res.get("tags_ko") or []) if t and t != "키네틱아트"]
                res["tags_ko"] = ["키네틱아트", *tags][:6]
            results.append(res)

    got = {r["local_id"] for r in results}
    missing = sorted(set(inputs) - got - {b[0] for b in bad})
    print(f"merge: 입력 {len(inputs)} / 유효 {len(results)} "
          f"(거부 {sum(1 for r in results if r.get('reject'))}) / 무효 {len(bad)} / 누락 {len(missing)}")
    for lid, why in bad:
        print(f"  ✗ 무효 {lid}: {why}")
    if missing:
        print(f"  ✗ 누락(파트 미완료) {len(missing)}건: {missing[:20]}")
    if unknown:
        print(f"  ✗ 입력에 없는 id {len(unknown)}건 무시: {unknown[:10]}")
    if not results:
        return 1
    merged = rd / "merged.json"
    save_records(merged, results)
    rc = ingest(str(merged))
    if bad or missing:
        print("→ 무효/누락분은 prepare 를 다시 돌리면 자동으로 재큐잉된다.")
    return rc


def ingest(results_path: str) -> int:
    results = load_records(results_path)
    by_id = {str(r["local_id"]): r for r in results}

    # 기존 described 산출물이 있으면 그것을 베이스로 병합한다.
    # (enriched 만으로 새로 만들면 이전에 생성한 한글 설명이 통째로 날아간다)
    records = load_records(config.ENRICHED_JSON)
    if config.DESCRIBED_JSON.exists():
        prior = {r["local_id"]: r for r in load_records(config.DESCRIBED_JSON)
                 if r.get("local_id")}
        for i, r in enumerate(records):
            if r.get("local_id") in prior:
                merged_rec = dict(r)
                merged_rec.update({k: v for k, v in prior[r["local_id"]].items()
                                   if v not in (None, "", [])})
                records[i] = merged_rec
        known = {r.get("local_id") for r in records}
        records += [r for lid, r in prior.items() if lid not in known]
    config.TEXTS_DIR.mkdir(parents=True, exist_ok=True)

    merged = rejected = 0
    matched: set[str] = set()
    for r in records:
        res = by_id.get(r["local_id"])
        if not res:
            continue
        matched.add(r["local_id"])

        if res.get("reject") is True:
            # 이미지를 보고 '키네틱 아트 아님/작품 아님'으로 판정 — 설명을 비우고 거부 표시.
            # texts/NNN.txt 는 지우지 않는다: 라이브 DB 행이 seed_sync 적용 전까지 그 파일을
            # 가리키므로(detail_text_url) 즉시 지우면 공개 사이트에서 404 가 난다.
            # 6단계가 이 레코드를 manifest·배포 목록에서 빼므로 남은 파일은 무해한 고아다.
            for f in ("description_ko", "detail_text_ko", "text_file"):
                r[f] = None
            r["notes"] = res.get("notes")
            r["review_status"] = "rejected"
            rejected += 1
            continue

        r["title"] = res.get("title_display") or r.get("title")
        # 작가/연도는 LLM(이미지+원문 근거)이 최종 권위자.
        # LLM 이 null 로 두면 '미상'이 정답 — enrich 힌트(사진가/촬영일)로 되살리지 않는다.
        r["artist"] = res.get("artist")
        r["created_year"] = coerce_year(res.get("created_year"))
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
    print(f"ingest 완료: 설명 {merged}개 + 거부 {rejected}개 병합 → {config.DESCRIBED_JSON}")
    unmatched = sorted(set(by_id) - matched)
    if unmatched:
        # 배치 접미사(KINERAG_BATCH)를 잘못 지정하면 결과가 통째로 버려진다 — 조용히 넘기지 않는다
        print(f"✗ 이 배치에 없는 id {len(unmatched)}건이 버려짐: {unmatched[:20]} "
              f"(KINERAG_BATCH={config.BATCH or '(없음)'} 확인)")
        return 1
    return 0


def main() -> int:
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd == "prepare":
        return prepare()
    if cmd == "split":
        size = int(sys.argv[sys.argv.index("--size") + 1]) if "--size" in sys.argv else 15
        return split(size)
    if cmd in ("merge", "ingest"):
        if len(sys.argv) < 3:
            print(f"{cmd} 는 경로 인자가 필요합니다.")
            return 1
        return merge(sys.argv[2]) if cmd == "merge" else ingest(sys.argv[2])
    print(__doc__)
    return 1


if __name__ == "__main__":
    sys.exit(main())
