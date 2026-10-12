import { unstable_cache } from "next/cache";
import { pgrst } from "./rest";
import type { Facets } from "./types";

async function json<T>(path: string): Promise<T> {
  const res = await pgrst(path);
  if (!res.ok) throw new Error(`REST ${res.status} ${path}`);
  return res.json();
}

// 패싯(필터 카운트) — 데이터는 배치 적재 때만 바뀌므로 5분 캐시.
// (홈 진입마다 집계 쿼리 3회를 반복하지 않는다. 실패는 캐시되지 않음)
export const getFacets = unstable_cache(
  async (): Promise<Facets> => {
    const [tags, artists, decades] = await Promise.all([
      json<Facets["tags"]>("/tag_facets?order=count.desc&limit=40"),
      json<Facets["artists"]>("/artist_facets?order=count.desc&limit=60"),
      json<Facets["decades"]>("/decade_facets?order=decade.desc"),
    ]);
    return { tags, artists, decades };
  },
  ["facets-v1"],
  { revalidate: 300 },
);
