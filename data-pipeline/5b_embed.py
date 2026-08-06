#!/usr/bin/env python3
"""스테이지 5b: 텍스트 임베딩 생성 (의미검색 대비, 무료·로컬).

described.json 의 각 레코드를 로컬 임베딩 모델로 벡터화해 'embedding' 필드에 저장한다.
1만+ 규모에서 키워드(ilike) 검색이 놓치는 '의미 검색'을 대비해, 수집 파이프라인에
임베딩 단계를 미리 심어두는 것이 목적. 작품이 늘 때마다 이 단계가 벡터를 자동 부착한다.

- 모델: intfloat/multilingual-e5-large — 다국어 '검색(retrieval)' 특화, 1024차원.
  로컬 ONNX 로 계산하므로 API·키·과금·요청한도가 전혀 없다(전액 무료 원칙 부합).
  ※ 계획서의 BAAI/bge-m3 는 fastembed 0.7.4 미지원 → 동급 다국어 리트리벌 모델로 대체.
     차원(1024)이 같아 이후 DB(pgvector vector(1024)) 계획은 그대로 유지된다.
- 임베딩 대상: title + description_ko + tags 를 합친 텍스트(개념 검색에 강함).
  description_ko 가 없으면 title 만으로라도 임베딩(빈 텍스트 레코드는 건너뜀).
- e5 규약(중요): 문서(passage)는 "passage: " 접두. 나중에 '검색 단계'에서 사용자
  질의는 반드시 "query: " 접두로 임베딩해야 정확도가 나온다(embedding_model 로 확인).
- 저장 벡터는 L2 정규화(코사인 유사도 일관성).
- 멱등: 같은 모델의 embedding 이 이미 있으면 스킵 → 재실행 안전.

실행:  ./.venv/bin/python 5b_embed.py
"""
from __future__ import annotations

import hashlib
import math
import sys

import config
from lib.models import load_records, save_records

MODEL_NAME = "intfloat/multilingual-e5-large"
EMBED_DIM = 1024
E5_PASSAGE_PREFIX = "passage: "  # e5 문서 임베딩 규약(질의는 "query: ")


def _embed_text(r: dict) -> str:
    """레코드에서 임베딩할 한글 개념 텍스트를 구성(제목 + 요약 + 태그)."""
    parts = [r.get("title") or "", r.get("description_ko") or ""]
    tags = r.get("tags") or []
    if tags:
        parts.append(" ".join(str(t) for t in tags))
    return "\n".join(p for p in parts if p).strip()


def _src_sha(text: str) -> str:
    """임베딩 소스 텍스트의 해시(텍스트가 바뀌면 재임베딩 트리거)."""
    return hashlib.sha1(text.encode("utf-8")).hexdigest()


def _needs_embedding(r: dict) -> bool:
    src = _embed_text(r)
    if not src:
        return False  # 임베딩할 텍스트가 없음
    if not r.get("embedding") or r.get("embedding_model") != MODEL_NAME:
        return True   # 미임베딩 또는 다른 모델
    return r.get("embedding_src_sha") != _src_sha(src)  # 소스 텍스트가 바뀜 → 갱신


def main() -> int:
    if not config.DESCRIBED_JSON.exists():
        print(f"먼저 4_describe_ko.py ingest 로 {config.DESCRIBED_JSON} 를 만드세요.")
        return 1

    records = load_records(config.DESCRIBED_JSON)
    todo = [r for r in records if _needs_embedding(r)]
    if not todo:
        have = sum(1 for r in records if r.get("embedding"))
        print(f"임베딩 최신 상태 — 새로 계산할 레코드 없음 "
              f"(전체 {len(records)}개, 임베딩 보유 {have}개).")
        return 0

    print(f"모델 로드: {MODEL_NAME} (최초 실행 시 ~2.2GB 다운로드)…")
    from fastembed import TextEmbedding

    model = TextEmbedding(model_name=MODEL_NAME)

    texts = [E5_PASSAGE_PREFIX + _embed_text(r) for r in todo]
    print(f"임베딩 계산: {len(texts)}개…")
    vectors = list(model.embed(texts))  # 제너레이터 → 입력 순서 보존

    if len(vectors) != len(todo):
        print(f"오류: 벡터 수({len(vectors)}) != 대상 수({len(todo)})")
        return 1

    bad = []  # 비유한 벡터(NaN/inf) 레코드 — poison JSON 방지 위해 저장 제외
    for r, vec in zip(todo, vectors):
        v = [float(x) for x in vec]
        norm = math.sqrt(sum(x * x for x in v))
        # NaN 은 truthy 이므로 `or 1.0` 로는 못 걸러짐 → 유한성/양수 명시 검사
        if not all(math.isfinite(x) for x in v) or not (norm > 0 and math.isfinite(norm)):
            bad.append(r.get("local_id"))
            continue
        r["embedding"] = [x / norm for x in v]
        r["embedding_model"] = MODEL_NAME
        r["embedding_dim"] = len(v)
        r["embedding_src_sha"] = _src_sha(_embed_text(r))

    save_records(config.DESCRIBED_JSON, records)

    if bad:
        print(f"  ⚠️ 비유한(NaN/inf) 벡터로 저장 제외된 레코드: {bad}")

    dims = sorted({len(r["embedding"]) for r in records if r.get("embedding")})
    total = sum(1 for r in records if r.get("embedding"))
    print(f"완료: 이번에 {len(todo) - len(bad)}개 임베딩 → {config.DESCRIBED_JSON}")
    print(f"  임베딩 보유 총 {total}개, 차원 {dims} (기대 {EMBED_DIM})")
    if dims != [EMBED_DIM]:
        print(f"  ⚠️ 차원이 기대({EMBED_DIM})와 다릅니다 — DB vector(N) 정의를 맞추세요.")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
