"""중앙 설정: 경로, 네트워크 매너, 수집 목표, 소스 정의.

모든 스테이지 스크립트(1_discover.py ~ 6_build_manifest.py)가 이 값을 공유한다.
"""
import os
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
# 배치(batch) — 2차 수집을 1차(69작품)와 섞지 않기 위한 파일 분리
#   KINERAG_BATCH=b2  → candidates_b2.json … described_b2.json 로 산출
#   KINERAG_ID_START=200 → local_id 를 200부터 발급(기존 000~190과 충돌 방지)
# ---------------------------------------------------------------------------
BATCH = os.environ.get("KINERAG_BATCH", "").strip()
_SFX = f"_{BATCH}" if BATCH else ""
ID_START = int(os.environ.get("KINERAG_ID_START", "0"))

# 배치 수집 시 '이미 가진 작품'으로 간주해 후보에서 제외할 이전 산출물
PRIOR_RECORD_FILES = [DATASET_DIR / "downloaded.json", DATASET_DIR / "described.json"]

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
