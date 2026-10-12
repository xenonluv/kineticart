import { getFacets } from "@/lib/server-data";
import { Studio } from "@/components/Studio";

export const dynamic = "force-dynamic";

const EMPTY_FACETS = { tags: [], artists: [], decades: [] };

export default async function Home() {
  // 패싯 조회 실패가 갤러리 전체를 막지 않게 빈 필터로 폴백
  const facets = await getFacets().catch(() => EMPTY_FACETS);
  return <Studio facets={facets} />;
}
