import { NextRequest, NextResponse } from "next/server";
import { pgrst } from "@/lib/rest";

export const dynamic = "force-dynamic";

// 단일 작품 상세(전 필드) + 원문 설명 텍스트 프록시.
export async function GET(
  _req: NextRequest,
  { params }: { params: Promise<{ id: string }> },
) {
  const { id } = await params;
  const res = await pgrst(`/kinetic_artworks?id=eq.${id}&select=*`);
  if (!res.ok) return NextResponse.json({ error: "not found" }, { status: 404 });
  const rows = await res.json();
  const artwork = rows[0];
  if (!artwork) return NextResponse.json({ error: "not found" }, { status: 404 });

  let detailText: string | null = null;
  if (artwork.detail_text_url) {
    try {
      const t = await fetch(artwork.detail_text_url, { cache: "no-store" });
      if (t.ok) detailText = await t.text();
    } catch {
      /* 무시 */
    }
  }
  return NextResponse.json({ artwork, detailText });
}
