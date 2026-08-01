// Nano Banana(Gemini image) 네이티브 generateContent 호출.
// 참조 이미지(inline_data) + 프롬프트 → 새 이미지(base64) 반환.
const KEY = process.env.GOOGLE_API_KEY ?? "";
export const IMAGE_MODEL = process.env.IMAGE_MODEL || "gemini-2.5-flash-image";

export type RefImage = { mime: string; b64: string };
export type GenImage = { mime: string; b64: string };

export async function generateImage(
  prompt: string,
  refs: RefImage[],
): Promise<GenImage> {
  const parts: unknown[] = [{ text: prompt }];
  for (const r of refs) {
    parts.push({ inline_data: { mime_type: r.mime, data: r.b64 } });
  }

  const res = await fetch(
    `https://generativelanguage.googleapis.com/v1beta/models/${IMAGE_MODEL}:generateContent?key=${KEY}`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ contents: [{ parts }] }),
    },
  );
  const data = await res.json();
  if (data.error) throw new Error(data.error.message || "image generation error");

  const outParts = data?.candidates?.[0]?.content?.parts ?? [];
  for (const p of outParts) {
    const idd = p.inlineData || p.inline_data;
    if (idd?.data) {
      return { mime: idd.mimeType || idd.mime_type || "image/png", b64: idd.data };
    }
  }
  throw new Error("모델이 이미지를 반환하지 않았습니다.");
}
