import { NextResponse } from "next/server";
import { getFacets } from "@/lib/server-data";

export const dynamic = "force-dynamic";

export async function GET() {
  try {
    return NextResponse.json(await getFacets());
  } catch {
    return NextResponse.json({ error: "facets unavailable" }, { status: 502 });
  }
}
