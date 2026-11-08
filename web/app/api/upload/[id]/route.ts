import { NextRequest, NextResponse } from "next/server";
import { readFile } from "fs/promises";
import { uploadPath } from "@/lib/uploads";

export const runtime = "nodejs";

// 업로드 그림 보기(비밀번호 게이트 뒤). 공개 파일서버로는 노출하지 않는다.
export async function GET(_req: NextRequest, { params }: { params: Promise<{ id: string }> }) {
  const p = uploadPath((await params).id);
  if (!p) return NextResponse.json({ error: "not found" }, { status: 404 });
  try {
    const buf = await readFile(p);
    return new NextResponse(new Uint8Array(buf), {
      headers: {
        "content-type": "image/webp",
        "cache-control": "private, max-age=31536000, immutable",
        "x-content-type-options": "nosniff",
      },
    });
  } catch {
    return NextResponse.json({ error: "not found" }, { status: 404 });
  }
}
