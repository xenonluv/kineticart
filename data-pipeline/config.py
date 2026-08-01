"""중앙 설정: 경로, 네트워크 매너, 수집 목표, 소스 정의.

모든 스테이지 스크립트(1_discover.py ~ 6_build_manifest.py)가 이 값을 공유한다.
"""
from pathlib import Path

# ---------------------------------------------------------------------------
# 경로
# ---------------------------------------------------------------------------
PIPELINE_DIR = Path(__file__).resolve().parent          # .../kinerag/data-pipeline
ROOT = PIPELINE_DIR.parent                              # .../kinerag
WORKS_DIR = ROOT / "works"                              # 원본 이미지 (NNN.ext)
TEXTS_DIR = ROOT / "texts"                              # 한글 상세 설명 (NNN.txt)
DATASET_DIR = ROOT / "dataset"                          # 중간/최종 산출물

CANDIDATES_JSON = DATASET_DIR / "candidates.json"       # 1_discover 산출
DOWNLOADED_JSON = DATASET_DIR / "downloaded.json"       # 2_download 산출
ENRICHED_JSON = DATASET_DIR / "enriched.json"           # 3_enrich 산출
DESCRIBED_JSON = DATASET_DIR / "described.json"         # 4_describe_ko 산출
REVIEW_HTML = DATASET_DIR / "review.html"               # 5_build_review 산출
MANIFEST_JSON = DATASET_DIR / "manifest.json"           # 6_build 산출
SEED_SQL = DATASET_DIR / "seed.sql"                     # 6_build 산출

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
TARGET_FINAL = 100          # 최종 큐레이션 목표
TARGET_CANDIDATES = 150     # 과수집 목표 (중복/저품질 제거 여유)
DESCRIBE_TARGET = 120       # 한글 생성(비용 큼) 대상 상위 N개 — 검수에서 100개로 확정
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
    "Kinetic art",
    "Kinetic sculptures",
    "Kinetic art installations",
    "Mobiles (sculpture)",
    "Wind sculptures",
    "Zoetropes",
]
WIKIMEDIA_SUBCAT_DEPTH = 3          # 하위 카테고리 재귀 깊이
WIKIMEDIA_MAX_FILES = 220           # Wikimedia에서 가져올 파일 상한
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
MET_MAX_OBJECTS = 30                 # PD + 이미지 있는 것만, 이 개수까지
# Met "kinetic" 키워드 검색은 키네틱 아트 운동과 무관한 노이즈(초상화/시계 등)만 반환됨이 확인되어
# 기본 비활성화. Wikimedia Commons 만으로 목표 수량 충족.
USE_MET = False

# ---------------------------------------------------------------------------
# 허용 라이선스 (재배포 가능한 것만)
# ---------------------------------------------------------------------------
# 실제 판정 로직은 lib/license.py 참조.
