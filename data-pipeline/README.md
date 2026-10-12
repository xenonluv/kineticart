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
| 1 | `1_discover.py` | (API) → `dataset/candidates{_bN}.json` | Wikimedia 등 후보 수집 + 라이선스 필터 |
| 2 | `2_download.py` | candidates → `works/`, `downloaded{_bN}.json` | 다운로드·검증·해상도 상한. **id 자동 발급**, 25건마다 중간 저장(이어받기) |
| 2b | `2b_derivatives.py` | `works/` → `cards/`(480)·`thumbs/`(768)·`display/`(1600) | 웹 표시용 WebP 파생본(GIF 는 상세에서 애니메이션 WebP). **3단계 직후** 실행 — 선별분만 생성 |
| 3 | `3_enrich.py` | downloaded → `enriched{_bN}.json` | 작가/연도 정규화, 태그, **dHash 근접중복 제거**(배치 간 포함), 상위 선별 |
| 4a | `4_describe_ko.py prepare` | described/enriched → `describe_queue{_bN}.json` | **멱등**: 검증된 설명·거부된 항목은 건너뜀 |
| 4b | `4_describe_ko.py split --size 15` | queue → `desc_out{_bN}/run_<시각>/in_NN.json` | 서브에이전트 파트 분할 |
| 4c | (서브에이전트, haiku) | `in_NN.json` + `thumbs/` → `part_NN.json` | 이미지 보고 한글 설명/거부 판정 (`prompts/describe_ko.md`) |
| 4d | `4_describe_ko.py merge <run_dir>` | parts → `described{_bN}.json`, `texts/` | 검증 후 병합(무효·누락은 다음 prepare 에서 재큐잉) |
| 5 | `5_build_review.py` | described → `dataset/review{_bN}.html` | 사람 검수 UI (승인/거부 → `review_decisions{_bN}.json`) |
| 5b | `5b_embed.py` | described → described(+`embedding`) | 텍스트 임베딩 생성(로컬 e5-large, 무료) — 의미검색 대비 |
| 6 | `6_build_manifest.py` | 전 배치 described + 전 배치 decisions → `manifest.json`, `seed.sql`, `seed_sync.sql` | **검증 게이트** + pinned 우선 + 선별 + 무결성 검사(`check_manifest.py`) |
| 7 | (DB 적용) | `seed_sync.sql` → 라이브 DB | 백업 → 적용 → `6_build_manifest.py --mark-live` |

### 배치 규칙 (2차 이후 수집)
- `KINERAG_BATCH=b3` 처럼 **b+숫자**만 허용. 미지정 시 1~3단계는 1차 산출물이 있으면 **중단**한다.
- `KINERAG_ID_START` 는 지정하지 말 것 — 2단계가 기존 최대 id 기준으로 100 단위 경계에서 자동 발급.
- 6단계는 `described.json` + `described_b*.json`, `review_decisions*.json` 을 **모두** 통합한다.

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

## 4단계(한글 생성) 상세 — Haiku 순차 교대
```bash
KINERAG_BATCH=b2 ./.venv/bin/python 4_describe_ko.py prepare          # 미검증분만 큐에
KINERAG_BATCH=b2 ./.venv/bin/python 4_describe_ko.py split --size 15  # run_<시각>/in_NN.json
#   → 서브에이전트 실행 (아래 규칙)
KINERAG_BATCH=b2 ./.venv/bin/python 4_describe_ko.py merge ../dataset/desc_out_b2/run_<시각>
```
**서브에이전트 실행 규칙 (세션 한도 429 사고 재발 방지)**
1. 모델 **haiku**, 파트당 **15건**, 동시 실행 **최대 3개**. 하나 끝나면 다음 하나 투입(순차 교대).
2. 입력 이미지는 `thumbs/NNN.webp`(장변 768) — 원본 대비 비전 토큰 약 70% 절감.
3. 프롬프트는 `prompts/describe_ko.md` 그대로. 이미지를 못 연 항목은 결과에서 **빼게** 한다.
4. 429/실패 파트는 **비워 둔다**. 원문 복사 등으로 대신 채우는 것은 금지 —
   `merge` 가 무효 처리하고 6단계 검증 게이트(`lib/validate.py`)가 최종적으로 막는다.
   한도 리셋 후 `prepare → split` 을 다시 돌리면 남은 것만 큐에 들어간다.
5. `merge` 후 메인 세션이 무작위 10% 를 썸네일과 대조해 표본 검수한다.

## 최종 산출물 (`dataset/`)
- `manifest.json` — 작품별 전 필드(… `thumbnail_url`=cards 480, `display_url`=display 1600, `image_url`=원본 …)
- `seed.sql` — 최초 기동(db/init)용 **멱등 upsert** (`ON CONFLICT DO UPDATE`)
- `seed_sync.sql` — 라이브 DB 를 manifest 와 **일치**(upsert + manifest 에 없는 행 삭제, 단일 트랜잭션,
  삭제 50% 초과 시 자동 중단). 적용 절차:
  ```bash
  docker exec kinerag-db pg_dump -U postgres kinerag > ../backups/kinerag_$(date +%Y%m%d_%H%M%S).sql
  docker exec -i kinerag-db psql -U postgres -d kinerag -v ON_ERROR_STOP=1 < ../dataset/seed_sync.sql
  ./.venv/bin/python 6_build_manifest.py --mark-live      # pinned_live.json ← 현재 manifest
  docker compose restart postgrest                          # 컬럼 추가 시 스키마 캐시 갱신
  ```
- `schema_additions.sql` — 스키마 보강 컬럼(… `display_url`)
- `deploy_files.txt` — 복사할 최종 파일 목록(works·cards·thumbs·display·texts)

## 배포 연결 (환경설치.md 와의 접점)
- `works/`, `texts/` 의 최종 파일을 집 Mac `kinetic-art-server/{works,texts}/` 로 복사(rsync).
- `config.BASE_IMAGE_URL` 을 실제 도메인(`https://images.내도메인.com`)으로 바꾸고 `6_build_manifest.py`
  재실행 → manifest/seed 의 URL 이 실도메인으로 갱신됨.
- `schema_additions.sql` → `seed.sql` 순서로 Supabase SQL Editor 에서 실행.
