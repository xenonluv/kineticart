import { NextRequest, NextResponse } from "next/server";
import { jobIdFromImageUrl, startJob } from "@/lib/model3d";
import { TripoError } from "@/lib/tripo";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

const STATUS: Record<TripoError["kind"], number> = { config: 503, credits: 402, rate: 429, bad_input: 400, upstream: 502 };

// 생성 이미지 → 3D 작업 시작. 응답 { job, status, progress, modelUrl? } — 이후 GET /api/generate-3d/{job} 로 진행 확인
export async function POST(req: NextRequest) {
  let imageUrl: unknown;
  try {
    imageUrl = ((await req.json()) as { imageUrl?: unknown }).imageUrl;
  } catch {
    return NextResponse.json({ error: "잘못된 요청입니다." }, { status: 400 });
  }
  const j = jobIdFromImageUrl(imageUrl);
  if (!j) return NextResponse.json({ error: "이 시스템에서 생성한 이미지만 3D로 만들 수 있습니다." }, { status: 400 });
  try {
    return NextResponse.json({ job: j.id, ...(await startJob(j.id, j.file)) });
  } catch (e) {
    if (e instanceof TripoError) return NextResponse.json({ error: e.message }, { status: STATUS[e.kind] });
    return NextResponse.json({ error: "3D 생성 요청에 실패했습니다." }, { status: 500 });
  }
}
