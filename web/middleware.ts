import { NextRequest, NextResponse } from "next/server";

const COOKIE = "kinerag_auth";
const PUBLIC = ["/login", "/api/login"];

// 웹앱 전체를 비밀번호로 보호. 로그인 성공 쿠키(AUTH_TOKEN)가 있어야 통과.
export function middleware(req: NextRequest) {
  const { pathname } = req.nextUrl;

  if (PUBLIC.some((p) => pathname === p || pathname.startsWith(p + "/"))) {
    return NextResponse.next();
  }

  const token = req.cookies.get(COOKIE)?.value;
  if (token && token === process.env.AUTH_TOKEN) {
    return NextResponse.next();
  }

  // API 는 401, 페이지는 로그인으로 리다이렉트
  if (pathname.startsWith("/api/")) {
    return new NextResponse(JSON.stringify({ error: "unauthorized" }), {
      status: 401,
      headers: { "content-type": "application/json" },
    });
  }
  const url = req.nextUrl.clone();
  url.pathname = "/login";
  return NextResponse.redirect(url);
}

export const config = {
  // 정적 자원/이미지 제외한 모든 경로
  matcher: [
    "/((?!_next/static|_next/image|favicon.ico|.*\\.(?:png|jpg|jpeg|svg|ico|webp)).*)",
  ],
};
