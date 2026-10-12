"""중앙 설정: 경로, 네트워크 매너, 수집 목표, 소스 정의.

모든 스테이지 스크립트(1_discover.py ~ 6_build_manifest.py)가 이 값을 공유한다.
"""
import json
import os
import re
from pathlib import Path

# ---------------------------------------------------------------------------
# 경로
# ---------------------------------------------------------------------------
PIPELINE_DIR = Path(__file__).resolve().parent          # .../kinerag/data-pipeline
ROOT = PIPELINE_DIR.parent                              # .../kinerag
WORKS_DIR = ROOT / "works"                              # 원본 이미지 (NNN.ext)
TEXTS_DIR = ROOT / "texts"                              # 한글 상세 설명 (NNN.txt)
DATASET_DIR = ROOT / "dataset"                          # 중간/최종 산출물

# ---------------------------------------------------------------------------
# 배치(batch) — 2차 이후 수집을 1차(69작품)와 섞지 않기 위한 파일 분리
#   KINERAG_BATCH=b3  → candidates_b3.json … described_b3.json 로 산출 (형식 b<숫자> 만 허용)
#   KINERAG_ID_START  → 생략 권장. 2_download 가 기존 최대 id 기준으로 자동 발급한다.
# ---------------------------------------------------------------------------
BATCH = os.environ.get("KINERAG_BATCH", "").strip()
if BATCH and not re.fullmatch(r"b\d+", BATCH):
    # described_b*.json 만 6단계 통합 대상이므로, 규칙 밖 이름은 배치가 통째로 누락된다
    raise SystemExit(f"KINERAG_BATCH='{BATCH}' 형식 오류 — 'b3' 처럼 b+숫자만 허용")
_SFX = f"_{BATCH}" if BATCH else ""
ID_START = int(os.environ.get("KINERAG_ID_START", "0"))
ID_START_SET = "KINERAG_ID_START" in os.environ


def guard_first_batch(path: "Path") -> None:
    """배치 미지정 실행이 1차 산출물을 덮어쓰는 사고 방지(실제로 한 번 발생 — 5cb9ed8 에서 복구).
    1~3단계는 산출 직전에 호출한다. 1차를 의도적으로 재생성하려면 KINERAG_ALLOW_FIRST_BATCH=1."""
    if not BATCH and path.exists() and os.environ.get("KINERAG_ALLOW_FIRST_BATCH") != "1":
        raise SystemExit(
            f"✗ KINERAG_BATCH 미지정 — 1차 산출물 {path.name} 을 덮어쓰게 됩니다. 중단.\n"
            f"  새 배치는 KINERAG_BATCH=b3 처럼 지정하세요.")


def known_max_id() -> int:
    """지금까지 발급된 local_id 최댓값(모든 배치 산출물 + pinned + works/ + texts/)."""
    ids: set[int] = set()
    for pat in ("downloaded*.json", "described*.json", "pinned_live.json"):
        for f in DATASET_DIR.glob(pat):
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            for r in data:
                lid = r.get("local_id") if isinstance(r, dict) else r
                if str(lid).isdigit():
                    ids.add(int(lid))
    for d in (WORKS_DIR, TEXTS_DIR):
        if d.exists():
            ids.update(int(p.stem) for p in d.iterdir() if p.stem.isdigit())
    return max(ids) if ids else -1


def auto_id_start() -> int:
    """새 배치의 시작 id — 기존 최대 id 다음의 100 단위 경계(예: 1099 → 1100)."""
    return (known_max_id() // 100 + 1) * 100


def prior_record_files() -> list["Path"]:
    """배치 수집 시 '이미 가진 작품'으로 간주할 이전 배치 산출물.

    현재 배치 자신의 산출물(downloaded{_SFX}.json 등)은 제외해야 한다 —
    포함하면 같은 배치를 다시 돌릴 때 자기 자신을 전부 제외해 후보가 비어버린다.
    """
    if not BATCH:
        return []
    own = {f"downloaded{_SFX}.json", f"described{_SFX}.json"}
    files = sorted(DATASET_DIR.glob("downloaded*.json")) + \
        sorted(DATASET_DIR.glob("described*.json"))
    return [p for p in files if p.name not in own]

CANDIDATES_JSON = DATASET_DIR / f"candidates{_SFX}.json"   # 1_discover 산출
DOWNLOADED_JSON = DATASET_DIR / f"downloaded{_SFX}.json"   # 2_download 산출
ENRICHED_JSON = DATASET_DIR / f"enriched{_SFX}.json"       # 3_enrich 산출
DESCRIBED_JSON = DATASET_DIR / f"described{_SFX}.json"     # 4_describe_ko 산출
REVIEW_HTML = DATASET_DIR / f"review{_SFX}.html"           # 5_build_review 산출
MANIFEST_JSON = DATASET_DIR / "manifest.json"              # 6_build 산출(항상 통합)


def all_described_files() -> list[Path]:
    """6_build_manifest 가 통합할 배치별 described 파일들 (1차 + b* 배치)."""
    files = [DATASET_DIR / "described.json"]
    files += sorted(DATASET_DIR.glob("described_b*.json"))
    return [p for p in files if p.exists()]


SEED_SQL = DATASET_DIR / "seed.sql"                        # 6_build 산출(항상 통합)

# ---------------------------------------------------------------------------
# 네트워크 매너 (Wikimedia 등은 서술형 User-Agent + 연락처 필수)
# ---------------------------------------------------------------------------
CONTACT = "xenonluv@gist.ac.kr"
USER_AGENT = f"kinerag-datacollector/0.1 (kinetic-art research; {CONTACT})"
REQUEST_DELAY = 0.4      # API 호출 사이 최소 지연(초)
REQUEST_TIMEOUT = 30     # 초

# ---------------------------------------------------------------------------
# 수집 목표
# ---------------------------------------------------------------------------
TARGET_FINAL = 300          # 최종 큐레이션 목표 (2차 확장: 69 → 300+)
TARGET_CANDIDATES = 900     # 과수집 목표 (중복/저품질 제거 여유)
DESCRIBE_TARGET = 400       # 한글 생성 대상 상위 N개
# 익명 'Lumino' LED 공예 시리즈(한 업로더의 반복 장신구)는 데이터셋 품질을 위해 전면 제외.
# (사용자 결정: 순수 양질 작품만. 대표 소수 포함을 원하면 값을 8 등으로 올릴 것)
LUMINO_CAP = 0

# ---------------------------------------------------------------------------
# 이미지 처리
# ---------------------------------------------------------------------------
MAX_LONG_EDGE = 2000        # 다운로드/저장 시 장변 상한(px) — 용량 관리
MIN_LONG_EDGE = 500         # 이 미만은 후보에서 제외 (썸네일/아이콘 배제)
JPEG_QUALITY = 88

# 웹 표시용 파생본 (2b_derivatives.py) — 원본 works/ 는 '원본 보기'용으로만 서빙
CARDS_DIR = ROOT / "cards"              # 갤러리 카드·채팅 참조 칩 (DB thumbnail_url)
THUMBS_DIR = ROOT / "thumbs"            # Haiku 비전 입력·이미지 생성 참조(내부 전용)
DISPLAY_DIR = ROOT / "display"          # 상세 화면 (DB display_url)
CARD_LONG_EDGE = 480                    # 카드 표시폭 ~260px × 2(레티나) 기준
CARD_QUALITY = 65
THUMB_LONG_EDGE = 768
THUMB_QUALITY = 72
DISPLAY_LONG_EDGE = 1600
DISPLAY_QUALITY = 80
DISPLAY_ANIM_LONG_EDGE = 800            # 애니메이션 WebP 는 프레임 수만큼 커지므로 더 작게
DISPLAY_ANIM_QUALITY = 60

# ---------------------------------------------------------------------------
# 최종 공개 URL 베이스 (도메인 확정 전 placeholder)
#   manifest 의 image_url = f"{BASE_IMAGE_URL}/works/NNN.ext"
#   도메인 정해지면 이 값만 교체
# ---------------------------------------------------------------------------
BASE_IMAGE_URL = "https://images.kctikinec.cloud"

# ---------------------------------------------------------------------------
# Wikimedia Commons (주력 소스)
#   seed 카테고리에서 시작해 하위 카테고리를 depth 만큼 재귀 수집.
#   denylist 키워드가 든 하위 카테고리는 건너뜀(작가 사진/전시/우표 등 비작품 노이즈 배제).
# ---------------------------------------------------------------------------
WIKIMEDIA_API = "https://commons.wikimedia.org/w/api.php"
WIKIMEDIA_SEED_CATEGORIES = [
    # --- 1차(69작품) 시드 ---
    "Kinetic art",
    "Kinetic sculptures",
    "Kinetic art installations",
    "Mobiles (sculpture)",
    "Wind sculptures",
    "Zoetropes",
    # --- 2차 확장: 움직임/광학 계열 ---
    "Op art",
    "Optical illusions in art",
    "Moiré patterns",
    "Anamorphosis",
    "Sound sculptures",
    "Light art",
    "Light installations",
    "Interactive art",
    "Wind chimes",
    "Whirligigs",
    "Weather vanes",
    "Water sculptures",
    "Kinetic fountains",
    "Automata",
    "Mechanical toys",
    "Tensegrity structures",
    "Hoberman spheres",
    "Mechanical sculptures",
    "Moving sculptures",
    "Pendulums in art",
    "Foucault pendulums",
    "Kugel fountains",
    "Praxinoscopes",
    "Phenakistiscopes",
    "Thaumatropes",
    "Flip books",
    "Solar sculptures",
    "Mobile sculptures",
    # --- 2차 확장: 대표 작가 ---
    "Alexander Calder",
    "Sculptures by Alexander Calder",
    "Jean Tinguely",
    "Works by Jean Tinguely",
    "George Rickey",
    "Theo Jansen",
    "Strandbeest",
    "Naum Gabo",
    "Nicolas Schöffer",
    "Pol Bury",
    "Takis",
    "Julio Le Parc",
    "Carlos Cruz-Diez",
    "Jesús Rafael Soto",
    "Victor Vasarely",
    "Bridget Riley",
    "Yaacov Agam",
    "Len Lye",
    "Arthur Ganson",
    "Anthony Howe (sculptor)",
    "Reuben Margolin",
    "Ned Kahn",
    "Tim Prentice",
    "Susumu Shingu",
    "Rebecca Horn",
    "Olafur Eliasson",
    "Studio Drift",
    "Daniel Rozin",
    "Zimoun",
    "Bruce Munro",
]
WIKIMEDIA_SUBCAT_DEPTH = 3          # 하위 카테고리 재귀 깊이
WIKIMEDIA_MAX_FILES = 2500          # Wikimedia에서 가져올 파일 상한(2차 확장)
WIKIMEDIA_SUBCAT_DENYLIST = [
    "artist", "people", "portrait", "exhibition", "museum", "gallery",
    "stamp", "logo", "diagram", "grave", "signature", "documents",
]

# ---------------------------------------------------------------------------
# The Met Open Access (보조 소스, 키 불필요, CC0/PD)
# ---------------------------------------------------------------------------
MET_SEARCH_API = "https://collectionapi.metmuseum.org/public/collection/v1/search"
MET_OBJECT_API = "https://collectionapi.metmuseum.org/public/collection/v1/objects"
MET_QUERY = "kinetic"
MET_MAX_OBJECTS = 60                 # PD + 이미지 있는 것만, 이 개수까지
# 2차 확장: 단일 "kinetic" 검색은 노이즈가 많았으나, 다중 질의 + 3_enrich 노이즈 필터 +
# 최종 큐레이션으로 걸러내는 전제 하에 재활성화(수량 확보 우선).
USE_MET = True

# 여러 소스가 공유하는 키네틱 아트 검색 질의
ART_QUERIES = [
    "kinetic sculpture", "kinetic art", "mobile sculpture", "op art",
    "optical art", "moving sculpture", "wind sculpture", "automaton",
]

# ---------------------------------------------------------------------------
# Cleveland Museum of Art Open Access (키 불필요, CC0)
# ---------------------------------------------------------------------------
CMA_API = "https://openaccess-api.clevelandart.org/api/artworks/"
CMA_MAX_OBJECTS = 120
USE_CMA = True

# ---------------------------------------------------------------------------
# Art Institute of Chicago (키 불필요, PD 여부는 is_public_domain)
# ---------------------------------------------------------------------------
AIC_API = "https://api.artic.edu/api/v1/artworks/search"
AIC_IIIF_BASE = "https://www.artic.edu/iiif/2"
AIC_MAX_OBJECTS = 120
USE_AIC = True

# ---------------------------------------------------------------------------
# 허용 라이선스 (재배포 가능한 것만)
# ---------------------------------------------------------------------------
# 실제 판정 로직은 lib/license.py 참조.
