import { NextRequest, NextResponse } from "next/server";
import { fetchDetailText, isUuid, pgrst } from "@/lib/rest";

export const dynamic = "force-dynamic";

// 단일 작품 상세(전 필드) + 원문 설명 텍스트 프록시.
export async function GET(
  _req: NextRequest,
  { params }: { params: Promise<{ id: string }> },
) {
  const { id } = await params;
  if (!isUuid(id)) return NextResponse.json({ error: "not found" }, { status: 404 });

  const res = await pgrst(`/kinetic_artworks?id=eq.${id}&select=*`);
  if (!res.ok) return NextResponse.json({ error: "not found" }, { status: 404 });
  const rows = await res.json();
  const artwork = rows[0];
  if (!artwork) return NextResponse.json({ error: "not found" }, { status: 404 });

  const detailText = await fetchDetailText(artwork.detail_text_url);
  return NextResponse.json({ artwork, detailText });
}
