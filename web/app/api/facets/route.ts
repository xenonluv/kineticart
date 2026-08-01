import { NextResponse } from "next/server";
import { pgrst } from "@/lib/rest";

export const dynamic = "force-dynamic";

export async function GET() {
  const [tags, artists, decades] = await Promise.all([
    pgrst("/tag_facets?order=count.desc&limit=40").then((r) => r.json()),
    pgrst("/artist_facets?order=count.desc&limit=60").then((r) => r.json()),
    pgrst("/decade_facets?order=decade.desc").then((r) => r.json()),
  ]);
  return NextResponse.json({ tags, artists, decades });
}
