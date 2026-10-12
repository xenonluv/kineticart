import { NextRequest, NextResponse } from "next/server";
import { mkdir, writeFile } from "fs/promises";
import { randomUUID } from "crypto";
import path from "path";
import { IMAGE_PUBLIC_BASE, isUuid, pgrst, refThumbUrl, toInternalFileUrl } from "@/lib/rest";
import { generateImage, type RefImage } from "@/lib/imagegen";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";
export const maxDuration = 300;

const GEN_DIR = process.env.GENERATED_DIR || "/app/generated";
// 참조 작품 이미지(최대 3장)를 내부 파일서버에서 받아 base64 로.
// 원본(최대 2000px, GIF 는 수십 MB) 대신 768px 정지 썸네일(thumbs/)을 보낸다 — 업로드·지연 대폭 감소.
async function loadRefs(referenceIds: string[]): Promise<RefImage[]> {
  const ids = referenceIds.filter(isUuid).slice(0, 3);
  if (!ids.length) return [];
  const res = await pgrst(`/kinetic_artworks?id=in.(${ids.join(",")})&select=image_url`);
  if (!res.ok) return [];
  const rows: { image_url: string }[] = await res.json();
  // 참조 3장을 병렬로 — 각 장은 768px 정지 썸네일 우선, 없으면 원본
  const loaded = await Promise.all(
    rows.map(async (r): Promise<RefImage | null> => {
      try {
        let ir = await fetch(toInternalFileUrl(refThumbUrl(r.image_url)), { cache: "no-store" });
        if (!ir.ok) ir = await fetch(toInternalFileUrl(r.image_url), { cache: "no-store" });
        if (!ir.ok) return null;
        const buf = Buffer.from(await ir.arrayBuffer());
        return { mime: ir.headers.get("content-type") || "image/jpeg", b64: buf.toString("base64") };
      } catch {
        return null;
      }
    }),
  );
  return loaded.filter((x): x is RefImage => x !== null);
}

function buildPrompt(concept: string): string {
  return [
    "You are generating a NEW, original kinetic art sculpture concept image.",
    `User's concept (Korean): ${concept || "an original kinetic art sculpture"}`,
    "Use any provided reference artwork image(s) only as stylistic/structural inspiration — do NOT copy them.",
    "Produce a single photorealistic image of the new kinetic sculpture installed in a clean gallery or outdoor setting, conveying a clear sense of movement. No text, no watermark.",
  ].join("\n");
}

export async function POST(req: NextRequest) {
  const { concept, referenceIds } = (await req.json()) as {
    concept?: string;
    referenceIds?: string[];
  };

  try {
    const refs = await loadRefs(referenceIds ?? []);
    const { mime, b64 } = await generateImage(buildPrompt(concept ?? ""), refs);

    await mkdir(GEN_DIR, { recursive: true });
    const ext = mime.includes("png") ? "png" : mime.includes("webp") ? "webp" : "jpg";
    const name = `${Date.now()}-${randomUUID().slice(0, 8)}.${ext}`;
    await writeFile(path.join(GEN_DIR, name), Buffer.from(b64, "base64"));

    return NextResponse.json({ imageUrl: `${IMAGE_PUBLIC_BASE}/generated/${name}` });
  } catch (e) {
    const msg = e instanceof Error ? e.message : "이미지 생성 실패";
    const billing = /quota|billing|exceeded/i.test(msg);
    return NextResponse.json(
      {
        error: billing
          ? "이미지 생성은 Google 결제(billing) 활성화가 필요합니다 — 무료 티어에 미포함(~$0.039/장). AI Studio에서 결제를 켜면 바로 작동합니다."
          : msg,
      },
      { status: billing ? 402 : 500 },
    );
  }
}
