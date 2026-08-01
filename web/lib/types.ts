export type ArtworkLite = {
  id: string;
  title: string;
  artist: string | null;
  created_year: number | null;
  image_url: string;
  tags: string[] | null;
};

export type ArtworkFull = ArtworkLite & {
  description: string | null;
  materials: string | null;
  detail_text_url: string | null;
  license: string | null;
  attribution: string | null;
  source_url: string | null;
};

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
