import { NextRequest, NextResponse } from "next/server";
import { getGeneration } from "@/lib/generations";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

const NO_STORE = { "cache-control": "private, no-store" };

export async function GET(_req: NextRequest, { params }: { params: Promise<{ id: string }> }) {
  try {
    const g = await getGeneration((await params).id);
    if (!g) return NextResponse.json({ error: "생성물을 찾을 수 없습니다." }, { status: 404, headers: NO_STORE });
    return NextResponse.json(g, { headers: NO_STORE });
  } catch {
    return NextResponse.json({ error: "조회에 실패했습니다." }, { status: 500, headers: NO_STORE });
  }
}
