import { getFacets } from "@/lib/server-data";
import { Studio } from "@/components/Studio";

export const dynamic = "force-dynamic";

export default async function Home() {
  const facets = await getFacets();
  return <Studio facets={facets} />;
}
