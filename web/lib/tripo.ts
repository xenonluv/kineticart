// 서버 전용: Tripo v3 API (이미지 → 3D GLB). 다른 3D 제공자로 바꿀 땐 이 파일만 교체.
// 문서: https://developers.tripo3d.ai/en/docs/generation-image-to-model/standard
const BASE = process.env.TRIPO_API_BASE || "https://openapi.tripo3d.ai/v3"; // 글로벌(.ai). 중국 키는 .com
const KEY = () => process.env.TRIPO_API_KEY ?? "";
// H 시리즈 최신. 표준 텍스처 이미지→3D = 30크레딧($0.30)
export const TRIPO_MODEL = process.env.TRIPO_MODEL || "v3.1-20260211";

export class TripoError extends Error {
  constructor(
    message: string,
    public kind: "config" | "credits" | "rate" | "bad_input" | "upstream",
  ) {
    super(message);
  }
}

export type TripoTask = {
  status: "queued" | "running" | "success" | "failed" | "cancelled" | "unknown";
  progress: number;
  modelUrl?: string;
  error?: string;
};

async function call(path: string, init?: RequestInit): Promise<Record<string, unknown>> {
  if (!KEY()) throw new TripoError("TRIPO_API_KEY 가 설정되지 않았습니다.", "config");
  let res: Response;
  try {
    res = await fetch(`${BASE}${path}`, {
      ...init,
      headers: { Authorization: `Bearer ${KEY()}`, "Content-Type": "application/json" },
      cache: "no-store",
      signal: AbortSignal.timeout(30_000),
    });
  } catch {
    throw new TripoError("3D 서버에 연결하지 못했습니다.", "upstream");
  }
  const j = (await res.json().catch(() => null)) as Record<string, unknown> | null;
  if (!j) throw new TripoError(`3D 서버 응답 오류(HTTP ${res.status})`, "upstream");
  if (j.code !== 0) {
    const msg = String(j.message ?? "3D 서버 오류");
    if (res.status === 401 || j.code === 2) throw new TripoError("Tripo API 키가 유효하지 않습니다.", "config");
    if (res.status === 429) throw new TripoError("3D 요청이 많습니다. 잠시 후 다시 시도해 주세요.", "rate");
    if (/credit|balance|insufficient/i.test(msg) || res.status === 402 || res.status === 403)
      throw new TripoError("Tripo 크레딧이 부족합니다. 콘솔에서 충전해 주세요.", "credits");
    if (res.status === 400) throw new TripoError(`3D 요청이 거부되었습니다: ${msg}`, "bad_input");
    throw new TripoError(`3D 서버 오류: ${msg}`, "upstream");
  }
  return (j.data ?? {}) as Record<string, unknown>;
}

// 이미지(공개 URL) → 3D 작업 생성. task_id 반환.
export async function createImageToModel(imageUrl: string): Promise<string> {
  const d = await call("/generation/image-to-model", {
    method: "POST",
    body: JSON.stringify({
      input: imageUrl,
      model: TRIPO_MODEL,
      texture: true,
      pbr: true,
      texture_quality: "standard", // HD/8K 는 추가 크레딧
      face_limit: 50_000, // 웹 미리보기·다운로드에 적당한 크기
    }),
  });
  const id = d.task_id;
  if (typeof id !== "string" || !id) throw new TripoError("3D 작업 ID를 받지 못했습니다.", "upstream");
  return id;
}

export async function getTask(taskId: string): Promise<TripoTask> {
  const d = await call(`/tasks/${encodeURIComponent(taskId)}`);
  const raw = String(d.status ?? "unknown");
  const status: TripoTask["status"] =
    raw === "banned" || raw === "expired"
      ? "failed"
      : (["queued", "running", "success", "failed", "cancelled"] as const).find((s) => s === raw) ?? "unknown";
  const out = (d.output ?? {}) as Record<string, unknown>;
  return {
    status,
    progress: Math.max(0, Math.min(100, Number(d.progress) || 0)),
    modelUrl: typeof out.model_url === "string" ? out.model_url : undefined,
    error: typeof d.error_message === "string" ? d.error_message : undefined,
  };
}
