# CLAUDE.md — 키네틱 아트 플랫폼 (kinerag)

> 최종 목표(`목적1.md`): 키네틱 아트 갤러리를 보며 LLM과 대화 → 참조 작품 선택 → 새 이미지 생성 → 3D Mesh(GLB) 다운로드.
> **전부 집 Mac에서 Docker로 자체호스팅**, Cloudflare Tunnel로 외부 노출, **이미지생성·3D 외 전액 무료**, 향후 AWS 등으로 컨테이너째 이전 가능하게 설계.

---

## 현재 상태 (2026-08-06)

| 목적1 단계 | 내용 | 상태 |
|---|---|---|
| 1 | 원천 이미지·설명 파일서버 | ✅ LIVE `images.kctikinec.cloud` |
| 2 | 메타데이터 + REST API | ✅ LIVE `api.kctikinec.cloud` |
| 3 | 웹 갤러리(스케일러블) | ✅ LIVE `www.kctikinec.cloud` |
| 4 | LLM 대화(RAG) | ✅ 무료(Gemini) |
| 5 | 새 이미지 생성 | ✅ Nano Banana(결제 활성) |
| 6 | 3D 생성·다운로드 | ⏳ **미완(Tripo 키 필요)** |
| — | 비밀번호 게이트(보안) | ✅ 웹앱 전체 로그인 보호 |
| — | 의미검색 준비(텍스트 임베딩) | ✅ 로컬 e5-large(무료), 실검색 연결은 ~1000개 시점 |
| — | artdata 협업 수집 저장소 | ✅ github.com/xenonluv/artdata (kinerag 병합 도구는 미구현) |

**데이터**: 키네틱 아트 69작품(이미지+한글설명), CC/오픈액세스만. 수집 파이프라인은 `data-pipeline/`.

**의미검색 준비(2026-08-06)**: 수집 파이프라인에 텍스트 임베딩 단계 추가 — `data-pipeline/5b_embed.py`, 로컬 `fastembed`+`intfloat/multilingual-e5-large`(1024차원, **무료·무API**). `described.json`/`manifest.json`에 임베딩 부착(멱등=소스텍스트 sha). 실제 벡터검색(pgvector) 연결은 데이터 ~1000개 시점으로 미룸(임베딩만 미리 심음). ⚠️계획서의 bge-m3는 fastembed 미지원→e5-large 대체(차원 동일). e5 규약: 문서 `passage:`/질의 `query:` 접두.

**협업 수집 저장소 `artdata`(2026-08-06)**: 별도 공개 repo **github.com/xenonluv/artdata**(kinerag와 분리, 이 프로젝트 무수정). 여러 명이 clone해 키네틱 아트를 수집(위키미디어 크롤 `tools/collect.py` / 수동)·검증(`tools/validate.py`)해 `contributions/<이름>/records.csv`로 제출. **이미지는 git에 안 넣고 URL만**(저장소 경량), Mac 직접쓰기 배제(보안). 병합계약=records.csv 필드(필수 `source_url`(자연키)·`image_url`·`title`·`license`). 적대적 리뷰 2회 통과·하드닝(BOM/라이선스/mime).
- **실제 kinerag 병합은 미구현(별도 단계)**: `data-pipeline/7_import_contrib.py`(URL→이미지 다운로드→`works/`, 설명 비면 stage4 생성, 5b 임베딩, `seed_delta.sql` ON CONFLICT) + DB `source_url` 유니크 인덱스. **필드 매핑 필수**: `source_url→source_page_url`·`image_url→image_src_url`·`source_desc→desc_src`, `tags` `;`분리, `created_year` 정수.
- **여러 명 수집 시 중복 처리(3단계, 병합 도구가 구현)**: ①`source_url` 정확(자동) ②이미지 **SHA-256** 동일(자동) ③**perceptual hash** near-dup→'중복 후보' 리포트로 사람 검토. (자연키만으론 '같은 작품 다른 URL/사진' 못 잡음)
- 상세 계획: `~/.claude/plans/enumerated-hatching-parnas.md`(현재 Phase 7=artdata 전용으로 재작성됨).

---

## 아키텍처 (Docker 컨테이너 5개, 한 `docker-compose.yml`)

```
인터넷 → Cloudflare 엣지(HTTPS, 유동IP 무관) → cloudflared 터널 → 집 Mac Docker
  www.kctikinec.cloud    → web        (Next.js 15, 비밀번호 게이트)
  api.kctikinec.cloud    → postgrest  → db (Postgres, 외부 비노출)
  images.kctikinec.cloud → file-server(nginx: /works /texts /generated)
```

| 컨테이너 | 이미지 | 역할 | 포트(로컬) |
|---|---|---|---|
| `kinerag-file-server` | nginx:alpine (빌드) | 원본/생성 이미지·텍스트 정적 서빙 | 8787 |
| `kinerag-db` | postgres:16-alpine | 메타 DB(외부 비노출) | (내부 5432) |
| `kinerag-postgrest` | postgrest/postgrest | 자동 REST API(읽기전용 web_anon) | 3001→3000 |
| `kinerag-web` | Next.js standalone (빌드) | 웹앱(갤러리·대화·생성) | 3002→3000 |
| `kinerag-tunnel` | cloudflare/cloudflared | 외부 노출 터널 | — |

---

## 디렉토리 구조

```
kinerag/
├── docker-compose.yml        # 스택 전체 정의
├── .env                      # 비밀(gitignore) — 아래 '환경변수' 참조
├── 목적1.md / 환경설치.md      # 요구사항·설계 문서
├── file-server/              # nginx Dockerfile + default.conf(CORS, /works /texts /generated)
├── db/init/                  # 최초 기동 SQL: 00-init.sh(스키마+시드), 01-search.sql(pg_trgm+패싯뷰)
├── works/  texts/            # 원본 이미지·한글설명 (파일서버가 서빙, 최종 69개는 deploy_files.txt)
├── generated/                # AI 생성 이미지 저장(web가 쓰고 file-server가 서빙)
├── dataset/                  # 파이프라인 산출물(manifest.json, seed.sql, review.html 등)
├── data-pipeline/            # 데이터 수집 파이프라인(Python, 6단계) — README.md 참조
└── web/                      # Next.js 앱 (App Router, TS, Tailwind)
    ├── app/                  # page.tsx(스튜디오), login/, artwork/[id]/, api/*
    ├── components/           # Studio, FilterRail, ArtworkGrid, DetailModal, ChatPanel
    ├── lib/                  # rest.ts, server-data.ts, useArtworks.ts, llm.ts, imagegen.ts, sse.ts, types.ts
    └── middleware.ts         # 비밀번호 게이트
```

---

## 실행 / 운영

```bash
cd /Users/jinjin/kinerag
docker compose up -d                 # 전체 기동
docker compose up -d --build web     # web만 재빌드·재기동(코드 수정 후)
docker compose up -d db postgrest    # DB/REST만
docker compose ps                    # 상태
docker compose logs -f web           # 로그
```

- **DB 스키마 변경**: `db/init/*`는 최초 1회만 자동 적용. 실행중 DB엔 `docker exec -i kinerag-db psql -U postgres -d kinerag < db/init/01-search.sql` 후 `docker compose restart postgrest`(스키마 캐시 재로드).
- **24시간 운영**: Docker Desktop "로그인 시 자동 시작" 켜기 + `sudo pmset -c sleep 0`(Mac 절전 해제). 컨테이너는 `restart: unless-stopped`.
- **Cloudflare Tunnel 라우트**(Zero Trust→Networks→Tunnels→`kinerag`→Routes): `images`→`http://file-server:8787`, `api`→`http://postgrest:3000`, `www`→`http://web:3000`.
- **Docker Hub**: 커스텀 이미지 2개 게시됨 — `xenonluv/kinerag-web`, `xenonluv/kinerag-file-server`(현재 public). 코드 수정 후 갱신: `docker compose build web && docker compose push web`. 새 서버 이전: `docker compose pull && docker compose up -d`. ⚠️ **데이터(works/·texts/·generated/·DB)와 `.env`는 이미지에 없으므로 별도 복사** 필요(볼륨 마운트).

---

## 웹앱 (web/) 요점

- **스택**: Next.js 15(App Router)+React 19+TS+Tailwind+lucide-react. `output: standalone`(경량 Docker·이식성).
- **갤러리(스케일)**: 5,000개 대비 — 검색+패싯필터(태그/작가/연대)+무한스크롤(48개씩)+카드 `content-visibility`. 상태는 client, 프록시 API로 페이지네이션.
- **프록시 API**(서버→내부 PostgREST `http://postgrest:3000`): `/api/artworks`(검색·필터·페이지·카운트), `/api/facets`, `/api/artwork/[id]`.
- **대화(RAG)**: `/api/chat`(SSE 스트리밍). 참조ID·키워드로 PostgREST 검색→작품 메타를 시스템 컨텍스트로 주입. provider는 `lib/llm.ts`(openai SDK→Gemini OpenAI호환 엔드포인트).
- **이미지 생성**: `/api/generate-image`. 참조 이미지(inline_data)+대화 컨셉을 Nano Banana로 융합→`generated/`에 저장→`images.kctikinec.cloud/generated/`.
- **비밀번호 게이트**: `middleware.ts`가 전 경로 보호(로그인 쿠키 `kinerag_auth`==`AUTH_TOKEN`). 미인증 페이지→`/login` 리다이렉트, API→401. 로그인=`/api/login`(비번=`SITE_PASSWORD`, 성공 시 30일 쿠키).

---

## 환경변수 (`.env`, gitignore)

| 키 | 용도 |
|---|---|
| `CLOUDFLARE_TUNNEL_TOKEN` | 터널 커넥터 |
| `POSTGRES_PASSWORD` / `AUTHENTICATOR_PASSWORD` | DB / PostgREST 접속(랜덤 생성) |
| `GOOGLE_API_KEY` | Gemini 대화 + Nano Banana 이미지 |
| `SITE_PASSWORD` | 웹앱 로그인 비밀번호 |
| `AUTH_TOKEN` | 로그인 성공 쿠키 값(랜덤) |
| `TRIPO_API_KEY` | (예정) 3D 생성 |

- API 키 원본 메모: `googleapi.md`, `apigoo.md`(둘 다 gitignore). **현재 유효 Google 키는 `apigoo.md`의 프로젝트 gen-lang-client-0246258645(결제 활성)**.
- 비밀번호 변경: `.env`의 `SITE_PASSWORD` 수정 → `docker compose up -d web`.

---

## 비용 / 외부 API 주의사항

- **무료**: 갤러리·검색·대화(Gemini **무료 티어**, 모델 `gemini-flash-latest`), Supabase 대신 자체 Postgres, Vercel 대신 자체호스팅, Cloudflare Tunnel.
- **유료**: 이미지 생성(Nano Banana `gemini-2.5-flash-image`, ~$0.039/장) — **결제는 API 키가 속한 프로젝트에 걸려야** 함(free_tier limit:0 오류 시 프로젝트 불일치). 3D(Tripo, 월 300크레딧 무료 후 종량).
- 모델 함정: `gemini-2.5-flash`는 신규계정 404 → 대화는 `gemini-flash-latest` 사용.

---

## 확정된 설계 결정
- REST API는 Supabase 클라우드 대신 **자체 Postgres+PostgREST**(PostgREST가 Supabase REST의 실체). 집 Mac은 파일·DB·API·웹 전부 Docker 호스팅.
- **Vercel 미사용** — 웹앱도 Docker 자체호스팅(이식성·무료·락인 회피).
- LLM은 `lib/`에 격리, Vercel AI SDK 미사용(각 provider 직접).
- 데이터는 CC/오픈액세스만(재배포 안전). 품질 우선(수량 억지로 안 채움) → 69개.

---

## 다음 작업 (Phase 5 — 3D)
- `web/lib/tripo.ts` + `/api/generate-3d`: 생성 이미지 URL → `POST api.tripo3d.ai/v2/openapi/task`(image_to_model) → 폴링 → `output.model`(GLB) 다운로드. ChatPanel의 `[3D 만들기]` 버튼 활성화.
- 필요: `TRIPO_API_KEY`(tripo3d.ai 발급).
- 계획 문서: `~/.claude/plans/enumerated-hatching-parnas.md`.
