import { NextRequest, NextResponse } from "next/server";
import { mkdir, writeFile } from "fs/promises";
import { randomUUID } from "crypto";
import sharp from "sharp";
import { ALLOWED_MIME, MAX_UPLOAD_BYTES, UPLOAD_DIR, uploadPath } from "@/lib/uploads";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

// 사용자 그림 업로드: 검증 → 재인코딩(장변 1600 WebP, EXIF/메타 제거, 투명 배경은 흰색) → 랜덤 id 저장.
// 원본 바이트는 저장하지 않는다(재인코딩이 악성 페이로드·위치정보 제거를 겸함).
export async function POST(req: NextRequest) {
  // 길이 미표기(chunked)는 미들웨어 10MB 버퍼에서 잘릴 수 있어 거절 → 항상 정확한 413/411
  const len = Number(req.headers.get("content-length") || NaN);
  if (!Number.isFinite(len)) {
    return NextResponse.json({ error: "Content-Length 가 필요합니다." }, { status: 411 });
  }
  if (len > MAX_UPLOAD_BYTES + 64 * 1024) {
    return NextResponse.json({ error: "파일이 너무 큽니다(최대 8MB)." }, { status: 413 });
  }
  let file: File | null = null;
  try {
    const f = (await req.formData()).get("file");
    file = f instanceof File ? f : null;
  } catch {
    /* 아래에서 처리 */
  }
  if (!file) return NextResponse.json({ error: "파일이 없습니다." }, { status: 400 });
  if (file.size > MAX_UPLOAD_BYTES) {
    return NextResponse.json({ error: "파일이 너무 큽니다(최대 8MB)." }, { status: 413 });
  }
  if (!ALLOWED_MIME.includes(file.type)) {
    return NextResponse.json({ error: "PNG·JPG·WebP·GIF 이미지만 올릴 수 있습니다." }, { status: 415 });
  }

  let out: Buffer;
  try {
    out = await sharp(Buffer.from(await file.arrayBuffer()), { limitInputPixels: 40_000_000 })
      .rotate() // EXIF 방향 반영 후 메타데이터는 출력에서 제외(기본 동작)
      .resize(1600, 1600, { fit: "inside", withoutEnlargement: true })
      .flatten({ background: "#ffffff" })
      .webp({ quality: 88 })
      .toBuffer();
  } catch {
    return NextResponse.json({ error: "이미지를 읽을 수 없습니다." }, { status: 415 });
  }

  const id = randomUUID();
  try {
    await mkdir(UPLOAD_DIR, { recursive: true });
    await writeFile(uploadPath(id)!, out);
  } catch {
    return NextResponse.json({ error: "저장에 실패했습니다. 잠시 후 다시 시도해 주세요." }, { status: 500 });
  }
  return NextResponse.json({ id, url: `/api/upload/${id}` });
}
