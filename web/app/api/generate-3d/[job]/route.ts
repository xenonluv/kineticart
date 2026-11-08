import { NextRequest, NextResponse } from "next/server";
import { isJobId, refreshJob } from "@/lib/model3d";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

// 3D 작업 진행 상태(클라이언트가 몇 초마다 호출)
export async function GET(_req: NextRequest, { params }: { params: Promise<{ job: string }> }) {
  const id = (await params).job;
  if (!isJobId(id)) return NextResponse.json({ error: "not found" }, { status: 404 });
  try {
    const v = await refreshJob(id);
    if (!v) return NextResponse.json({ error: "3D 작업을 찾을 수 없습니다." }, { status: 404 });
    return NextResponse.json({ job: id, ...v });
  } catch {
    return NextResponse.json({ error: "상태 확인 실패" }, { status: 500 });
  }
}
