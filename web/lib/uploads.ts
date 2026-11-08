// 서버 전용: 사용자 업로드 그림 저장소.
// 파일서버(공개)와 분리된 디렉토리(/app/uploads)에 두고, 비밀번호 게이트 뒤의 /api/upload/[id] 로만 노출한다.
import { readFile, rename, utimes, writeFile } from "fs/promises";
import path from "path";
import { isUuid } from "./rest";
import type { RefImage } from "./imagegen";

export const UPLOAD_DIR = process.env.UPLOAD_DIR || "/app/uploads";
export const MAX_UPLOAD_BYTES = 8 * 1024 * 1024; // 8MB (미들웨어 본문 버퍼 한도 10MB 아래)
export const ALLOWED_MIME = ["image/png", "image/jpeg", "image/webp", "image/gif"];

// id 는 서버가 발급한 uuid 만 허용 → 경로 조작(../) 원천 차단
export function uploadPath(id: string): string | null {
  return isUuid(id) ? path.join(UPLOAD_DIR, `${id.toLowerCase()}.webp`) : null;
}

export async function loadUpload(id: string): Promise<RefImage | null> {
  const p = uploadPath(id);
  if (!p) return null;
  try {
    const buf = await readFile(p);
    // 사용할 때마다 보관 기간 갱신(자동 삭제는 '마지막 사용' 기준) — 분석 캐시도 함께
    const now = new Date();
    await Promise.all([
      utimes(p, now, now),
      utimes(p.replace(/\.webp$/, ".json"), now, now),
    ].map((x) => x.catch(() => {})));
    return { mime: "image/webp", b64: buf.toString("base64") };
  } catch {
    return null;
  }
}

// 그림 분석 결과(한글 설명) 캐시: <id>.json — 재분석 비용·지연 방지, 생성 프롬프트에 재사용
export type SketchAnalysis = { description: string };

export async function readAnalysis(id: string): Promise<SketchAnalysis | null> {
  const p = uploadPath(id);
  if (!p) return null;
  try {
    const j = JSON.parse(await readFile(p.replace(/\.webp$/, ".json"), "utf8"));
    return typeof j?.description === "string" && j.description ? { description: j.description } : null;
  } catch {
    return null;
  }
}

export async function writeAnalysis(id: string, a: SketchAnalysis): Promise<void> {
  const p = uploadPath(id);
  if (!p) return;
  const dest = p.replace(/\.webp$/, ".json");
  const tmp = `${dest}.${process.pid}.${Date.now()}.tmp`;
  await writeFile(tmp, JSON.stringify(a), "utf8");
  await rename(tmp, dest); // 원자적 교체 — 잘린 JSON 이 남지 않게
}
