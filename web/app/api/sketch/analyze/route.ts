import { NextRequest, NextResponse } from "next/server";
import { CHAT_MODEL, getLLM } from "@/lib/llm";
import { loadUpload, readAnalysis, writeAnalysis } from "@/lib/uploads";
import { similarArtworks, type SimilarArtwork } from "@/lib/embed";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";
export const maxDuration = 120;

const VISION_PROMPT = [
  "다음은 사용자가 직접 그린 키네틱 아트(움직이는 조형물) 아이디어 스케치입니다.",
  "그림을 보고 한국어로 3~5문장 설명하세요:",
  "① 전체 형태와 구도 ② 구성 요소(축·팔·날개·추·원판 등)와 배치",
  "③ 어떻게 움직일 것으로 보이는지(회전·흔들림·바람·모터 등) ④ 연상되는 재질·분위기.",
  "보이지 않는 것은 지어내지 말고, 머리말·목록 기호 없이 설명 문장만 출력하세요.",
].join("\n");

// 같은 그림 동시 분석 시 Gemini 호출 1회로 합침(프로세스 내)
const inflight = new Map<string, Promise<string>>();

async function describe(mime: string, b64: string): Promise<string> {
  const r = await getLLM().chat.completions.create({
    model: CHAT_MODEL,
    messages: [
      {
        role: "user",
        content: [
          { type: "text", text: VISION_PROMPT },
          { type: "image_url", image_url: { url: `data:${mime};base64,${b64}` } },
        ],
      },
    ],
  });
  const d = (r.choices[0]?.message?.content ?? "").trim().slice(0, 2000);
  if (!d) throw new Error("빈 응답");
  return d;
}

// 사용자 그림 → Gemini 비전 한글 설명 → e5 질의 임베딩 → 비슷한 갤러리 작품
export async function POST(req: NextRequest) {
  let uploadId = "";
  try {
    uploadId = String(((await req.json()) as { uploadId?: string }).uploadId ?? "");
  } catch {
    /* 아래 검사 */
  }
  const img = await loadUpload(uploadId);
  if (!img) return NextResponse.json({ error: "업로드한 그림을 찾을 수 없습니다." }, { status: 404 });

  let analysis = await readAnalysis(uploadId);
  if (!analysis) {
    try {
      let p = inflight.get(uploadId);
      if (!p) {
        p = describe(img.mime, img.b64).finally(() => inflight.delete(uploadId));
        inflight.set(uploadId, p);
      }
      analysis = { description: await p };
      await writeAnalysis(uploadId, analysis).catch(() => {}); // 캐시 실패는 치명적이지 않음
    } catch (e) {
      const msg = e instanceof Error ? e.message : "";
      const limited = /429|quota|rate/i.test(msg);
      return NextResponse.json(
        { error: limited ? "그림 인식 요청이 많습니다. 잠시 후 다시 시도해 주세요." : "그림 인식에 실패했습니다." },
        { status: limited ? 429 : 502 },
      );
    }
  }

  // 유사 작품은 부가 기능 — 임베딩 서버가 꺼져 있어도 설명은 돌려준다
  let similar: SimilarArtwork[] = [];
  let similarError = false;
  try {
    similar = await similarArtworks(analysis.description, 6);
  } catch {
    similarError = true;
  }
  return NextResponse.json({ description: analysis.description, similar, similarError });
}
