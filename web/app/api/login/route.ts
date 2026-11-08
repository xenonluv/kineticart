import { NextRequest, NextResponse } from "next/server";
import { safeEqual } from "@/lib/safeEqual";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

// 무차별 대입 방지: IP 별 15분에 실패 10회 초과 시 차단(프로세스 메모리, 단일 web 컨테이너 기준)
const WINDOW_MS = 15 * 60 * 1000;
const MAX_FAILS = 10;
const fails = new Map<string, { n: number; until: number }>();

function clientIp(req: NextRequest): string {
  return (
    req.headers.get("cf-connecting-ip") ||
    req.headers.get("x-forwarded-for")?.split(",")[0]?.trim() ||
    "unknown"
  );
}

export async function POST(req: NextRequest) {
  const ip = clientIp(req);
  const now = Date.now();
  const rec = fails.get(ip);
  if (rec && rec.until > now && rec.n >= MAX_FAILS) {
    return NextResponse.json(
      { ok: false, error: "시도가 너무 많습니다. 잠시 후 다시 시도해 주세요." },
      { status: 429 },
    );
  }

  let password = "";
  try {
    const b = (await req.json()) as { password?: unknown };
    password = typeof b.password === "string" ? b.password : "";
  } catch {
    /* 실패로 처리 */
  }

  const expected = process.env.SITE_PASSWORD ?? "";
  if (expected && safeEqual(password, expected)) {
    fails.delete(ip);
    const res = NextResponse.json({ ok: true });
    res.cookies.set("kinerag_auth", process.env.AUTH_TOKEN ?? "", {
      httpOnly: true,
      sameSite: "lax",
      secure: true,
      path: "/",
      maxAge: 60 * 60 * 24 * 30, // 30일
    });
    return res;
  }

  const cur = rec && rec.until > now ? rec : { n: 0, until: now + WINDOW_MS };
  fails.set(ip, { n: cur.n + 1, until: cur.until });
  if (fails.size > 10_000) {
    for (const [k, v] of fails) if (v.until <= now) fails.delete(k); // 메모리 상한
  }
  return NextResponse.json({ ok: false }, { status: 401 });
}
