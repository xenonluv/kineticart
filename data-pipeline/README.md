# 키네틱 아트 데이터 수집 파이프라인

키네틱 아트 **이미지 + 한글 설명** 쌍 약 100개를 수집해, Supabase 적재용 데이터셋으로 만드는 파이프라인.
설계 배경과 결정사항은 리포 루트의 `환경설치.md` 및 계획 문서를 참조.

## 원칙
- **이미지**: 재배포 가능한 오픈액세스/CC(CC0·CC-BY·PD)만. 주력 = Wikimedia Commons.
- **한글 설명**: 하이브리드 — 원문(desc_src)을 사실 근거로 Claude가 한글 생성, 사람이 검수.
- **사실 권위자**: 작가/연도/재료는 `desc_src` + 이미지 기반. Wikimedia의 Artist/날짜 메타는
  대개 '사진가/촬영일'이라 신뢰하지 않음(4단계 LLM 이 교정).

## 환경
```bash
cd data-pipeline
python3 -m venv .venv
./.venv/bin/python -m pip install -r requirements.txt
```

## 스테이지 (순서대로 실행)
| # | 스크립트 | 입력 → 출력 | 역할 |
|---|---|---|---|
| 1 | `1_discover.py` | (API) → `dataset/candidates.json` | Wikimedia 후보 수집 + 라이선스 필터 |
| 2 | `2_download.py` | candidates → `works/`, `downloaded.json` | 이미지 다운로드·검증·해상도 상한 |
| 3 | `3_enrich.py` | downloaded → `enriched.json` | 작가/연도 정규화, 태그, 근접중복 제거, 상위 120 선별 |
| 4a | `4_describe_ko.py prepare` | enriched → `describe_queue.json` | 한글 생성용 입력 번들 |
| 4b | (서브에이전트) | queue + `works/` 이미지 → `desc_out/part_*.json` | 이미지 보고 한글 설명 생성 |
| 4c | `4_describe_ko.py ingest <merged.json>` | parts → `described.json`, `texts/` | 결과 병합 + 상세 텍스트 파일 기록 |
| 5 | `5_build_review.py` | described → `dataset/review.html` | 사람 검수 UI (승인/거부 → decisions 내보내기) |
| 5b | `5b_embed.py` | described → described(+`embedding`) | 텍스트 임베딩 생성(로컬 e5-large, 무료) — 의미검색 대비 |
| 6 | `6_build_manifest.py` | described (+decisions) → `manifest.json`, `seed.sql` 등 | 최종 100개 선별 + 적재물 |

### 5b단계(텍스트 임베딩) 상세
1만+ 규모에서 키워드 검색이 놓치는 **의미 검색**을 대비해, 각 작품의 한글 개념 텍스트
(제목+요약+태그)를 로컬 임베딩 모델로 벡터화해 `described.json` 의 `embedding` 필드에 저장한다.
- **모델**: `intfloat/multilingual-e5-large`(다국어 검색 특화, **1024차원**). 로컬 ONNX 계산 →
  **API·키·과금·요청한도 없음**(전액 무료). 최초 실행 시 모델 ~2.2GB 다운로드.
- **멱등**: 이미 임베딩된 레코드는 스킵 → 재실행 안전. `./.venv/bin/python 5b_embed.py`
- **e5 규약**: 문서는 `passage: ` 접두로 임베딩됨. 추후 검색 단계에서 사용자 질의는
  반드시 `query: ` 접두로 임베딩해야 정확도가 나온다.
- **저장/검색(1만 개 도착 시)**: DB 이미지를 `pgvector/pgvector:pg16` 로 교체하고
  `embedding vector(1024)` 컬럼 + HNSW 인덱스를 추가한 뒤, seed 에 벡터를 실어 벡터검색을 켠다.
  (지금은 벡터가 `manifest.json` 에만 담겨 기존 동작을 바꾸지 않는다.)

## 4단계(한글 생성) 상세
`prepare` 후, `dataset/desc_out/assignments.json` 로 항목을 나눠 서브에이전트가 각자
이미지를 읽고 한글 설명을 생성해 `desc_out/part_N.json` 에 저장한다. 모든 part 를 합쳐
`ingest` 하면 `described.json` 과 `texts/NNN.txt` 가 만들어진다.

병합 예:
```bash
./.venv/bin/python - <<'PY'
import json, glob
rows=[]
for f in sorted(glob.glob("../dataset/desc_out/part_*.json")):
    rows += json.load(open(f))
json.dump(rows, open("../dataset/described_merged.json","w"), ensure_ascii=False, indent=2)
print(len(rows))
PY
./.venv/bin/python 4_describe_ko.py ingest ../dataset/described_merged.json
```

## 최종 산출물 (`dataset/`)
- `manifest.json` — 작품별 전 필드(제목·설명·연도·재료·태그·image_url·detail_text_url·license·attribution·source_url·video_url)
- `seed.sql` — `kinetic_artworks` INSERT (인프라 준비 후 `service_role` 로 1회)
- `schema_additions.sql` — 스키마 보강 컬럼(video_url/license/attribution/source_url)
- `deploy_files.txt` — 집 Mac `kinetic-art-server/`(works·texts)로 복사할 최종 파일 목록

## 배포 연결 (환경설치.md 와의 접점)
- `works/`, `texts/` 의 최종 파일을 집 Mac `kinetic-art-server/{works,texts}/` 로 복사(rsync).
- `config.BASE_IMAGE_URL` 을 실제 도메인(`https://images.내도메인.com`)으로 바꾸고 `6_build_manifest.py`
  재실행 → manifest/seed 의 URL 이 실도메인으로 갱신됨.
- `schema_additions.sql` → `seed.sql` 순서로 Supabase SQL Editor 에서 실행.
