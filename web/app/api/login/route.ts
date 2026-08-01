import { NextRequest, NextResponse } from "next/server";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function POST(req: NextRequest) {
  const { password } = (await req.json()) as { password?: string };

  if (password && password === process.env.SITE_PASSWORD) {
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
  return NextResponse.json({ ok: false }, { status: 401 });
}
