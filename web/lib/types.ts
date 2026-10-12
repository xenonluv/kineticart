export type ArtworkLite = {
  id: string;
  title: string;
  artist: string | null;
  created_year: number | null;
  image_url: string;
  thumbnail_url: string | null; // 장변 480 WebP(갤러리 카드·참조 칩). 없으면 image_url 로 폴백
  tags: string[] | null;
};

export type ArtworkFull = ArtworkLite & {
  description: string | null;
  materials: string | null;
  display_url: string | null; // 장변 1600 WebP(상세 화면용, GIF 는 애니메이션 WebP)
  detail_text_url: string | null;
  license: string | null;
  attribution: string | null;
  source_url: string | null;
};

// 파생본 <img> 가 404 등으로 실패하면 원본(fallback)으로 한 번만 교체.
export const fallbackTo =
  (fallback: string) => (e: { currentTarget: HTMLImageElement }) => {
    const img = e.currentTarget;
    if (img.dataset.fellBack || img.src === fallback) return;
    img.dataset.fellBack = "1";
    img.src = fallback;
  };

// 화면 용도별 이미지 URL — 파생본이 없으면 원본으로 폴백.
export const thumbOf = (a: Pick<ArtworkLite, "thumbnail_url" | "image_url">) =>
  a.thumbnail_url || a.image_url;
export const displayOf = (
  a: Pick<ArtworkFull, "display_url" | "thumbnail_url" | "image_url">,
) => a.display_url || a.image_url;

export type Facets = {
  tags: { tag: string; count: number }[];
  artists: { artist: string; count: number }[];
  decades: { decade: number; count: number }[];
};

export type Filters = {
  q: string;
  tags: string[];
  artist: string | null;
  decade: number | null;
  sort: string;
};

export const DEFAULT_FILTERS: Filters = {
  q: "",
  tags: [],
  artist: null,
  decade: null,
  sort: "year_desc",
};
