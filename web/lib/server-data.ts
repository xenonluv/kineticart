import { pgrst } from "./rest";
import type { Facets } from "./types";

// 서버 컴포넌트에서 패싯(필터 카운트) 조회 — 내부 PostgREST.
export async function getFacets(): Promise<Facets> {
  const [tags, artists, decades] = await Promise.all([
    pgrst("/tag_facets?order=count.desc&limit=40").then((r) => r.json()),
    pgrst("/artist_facets?order=count.desc&limit=60").then((r) => r.json()),
    pgrst("/decade_facets?order=decade.desc").then((r) => r.json()),
  ]);
  return { tags, artists, decades };
}
