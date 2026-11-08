import { NextRequest, NextResponse } from "next/server";
import { isJobId } from "@/lib/model3d";
import { listGenerations, parseSince, type ListQuery } from "@/lib/generations";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

const NO_STORE = { "cache-control": "private, no-store" };
const bad = (error: string) => NextResponse.json({ error }, { status: 400, headers: NO_STORE });

function intParam(raw: string | null, dflt: number, max: number): number | null {
  if (raw === null) return dflt;
  if (!/^\d{1,9}$/.test(raw)) return null;
  const n = Number(raw);
  return n >= 1 && n <= max ? n : null;
}

export async function GET(req: NextRequest) {
  const sp = req.nextUrl.searchParams;
  const q: ListQuery = { page: 1, limit: 20 };

  const type = sp.get("type");
  if (type !== null) {
    if (type !== "2d" && type !== "3d") return bad("type 은 2d 또는 3d 여야 합니다.");
    q.type = type;
  }
  const since = sp.get("since");
  if (since !== null) {
    const t = parseSince(since);
    if (t === null) return bad("since 는 시간대가 포함된 ISO-8601 형식이어야 합니다. 예: 2026-11-09T01:00:00.000Z");
    q.since = t;
  }
  const afterId = sp.get("after_id");
  if (afterId !== null) {
    if (since === null) return bad("after_id 는 since 와 함께 써야 합니다.");
    if (!isJobId(afterId)) return bad("after_id 형식이 잘못되었습니다.");
    q.afterId = afterId;
  }
  const page = intParam(sp.get("page"), 1, 1_000_000);
  if (page === null) return bad("page 는 1 이상의 정수여야 합니다.");
  const limit = intParam(sp.get("limit"), 20, 100);
  if (limit === null) return bad("limit 은 1~100 의 정수여야 합니다.");
  if (since !== null && page !== 1) return bad("since 를 쓸 때는 page 대신 after_id 로 이어받아야 합니다.");
  q.page = page;
  q.limit = limit;

  try {
    return NextResponse.json(await listGenerations(q), { headers: NO_STORE });
  } catch {
    return NextResponse.json({ error: "목록 조회에 실패했습니다." }, { status: 500, headers: NO_STORE });
  }
}
