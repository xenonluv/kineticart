// 서버 전용: 생성 이미지 1장당 3D 작업 1개(작업 id = 이미지 파일 이름).
// 상태는 비공개 UPLOAD_DIR/3d-<id>.json, 완성 GLB 는 공개 GENERATED_DIR/<id>.glb (생성 이미지와 같은 공개 수준).
import { mkdir, open, readdir, readFile, rename, stat, unlink, writeFile } from "fs/promises";
import path from "path";
import { IMAGE_PUBLIC_BASE } from "./rest";
import { UPLOAD_DIR } from "./uploads";
import { createImageToModel, getTask, TripoError } from "./tripo";

const GEN_DIR = process.env.GENERATED_DIR || "/app/generated";
const JOB_RE = /^\d{13}-[0-9a-f]{8}$/; // generate-image 가 만드는 파일 이름(확장자 제외)
const IMG_RE = /^(\d{13}-[0-9a-f]{8})\.(png|jpg|webp)$/;
const DAILY_LIMIT = Math.max(0, Number(process.env.TRIPO_DAILY_LIMIT ?? 20) || 0); // 0 = 무제한
const MAX_ACTIVE = 3; // 동시에 진행 중인 3D 작업 상한(크레딧 보호)
const TIMEOUT_MS = 15 * 60 * 1000;
const MAX_GLB_BYTES = 200 * 1024 * 1024;

export type JobState = {
  taskId?: string; // 'starting' 동안은 없음(유료 작업 생성 직전 기록 → 크래시 시 이중 과금 방지)
  image: string; // 원본 생성 이미지 파일 이름
  // failed 는 'Tripo 가 실패/취소라고 응답한 경우'만(=환불됨). 로컬 문제(다운로드·지연)는 localError 로만 표시
  status: "starting" | "queued" | "running" | "success" | "failed";
  progress: number;
  createdAt: number;
  error?: string;
  localError?: string;
};
export type JobView = { status: JobState["status"]; progress: number; modelUrl?: string; error?: string };

export const isJobId = (s: string) => JOB_RE.test(s);
const statePath = (id: string) => path.join(UPLOAD_DIR, `3d-${id}.json`);
const glbPath = (id: string) => path.join(GEN_DIR, `${id}.glb`);
const glbUrl = (id: string) => `${IMAGE_PUBLIC_BASE}/generated/${id}.glb`;
const STARTING_STALE_MS = 5 * 60 * 1000;

export async function readState(id: string): Promise<JobState | null> {
  try {
    return JSON.parse(await readFile(statePath(id), "utf8")) as JobState;
  } catch {
    return null;
  }
}
async function writeState(id: string, s: JobState): Promise<void> {
  await mkdir(UPLOAD_DIR, { recursive: true });
  const tmp = `${statePath(id)}.${process.pid}.${Date.now()}.tmp`;
  await writeFile(tmp, JSON.stringify(s), "utf8");
  await rename(tmp, statePath(id));
}
const exists = (p: string) => stat(p).then((s) => s.isFile(), () => false);

function view(id: string, s: JobState): JobView {
  if (s.status === "success") return { status: "success", progress: 100, modelUrl: glbUrl(id) };
  return { status: s.status, progress: s.progress, error: s.error ?? s.localError };
}

// 공개 생성 이미지 URL → 작업 id. 우리 서버가 만든 이미지만 허용(임의 URL 로 크레딧 소모 방지)
export function jobIdFromImageUrl(url: unknown): { id: string; file: string } | null {
  if (typeof url !== "string") return null;
  const prefix = `${IMAGE_PUBLIC_BASE}/generated/`;
  if (!url.startsWith(prefix)) return null;
  const m = IMG_RE.exec(url.slice(prefix.length));
  return m ? { id: m[1], file: m[0] } : null;
}

// 한국 시간(KST) 기준 오늘 0시 — 컨테이너 시계는 UTC
function kstDayStart(now = Date.now()): number {
  const KST = 9 * 3600 * 1000;
  return Math.floor((now + KST) / 86_400_000) * 86_400_000 - KST;
}

async function countStates(): Promise<{ today: number; active: number }> {
  let names: string[] = [];
  try {
    names = (await readdir(UPLOAD_DIR)).filter((n) => /^3d-\d{13}-[0-9a-f]{8}\.json$/.test(n));
  } catch {
    /* 폴더 없음 */
  }
  const dayStart = kstDayStart();
  let today = 0;
  let active = 0;
  for (const n of names) {
    try {
      const s = JSON.parse(await readFile(path.join(UPLOAD_DIR, n), "utf8")) as JobState;
      // Tripo 가 실패로 돌려준(환불된) 작업만 한도에서 제외
      if (s.createdAt >= dayStart && s.status !== "failed") today++;
      const live = s.status === "starting" ? Date.now() - s.createdAt < STARTING_STALE_MS : s.status === "queued" || s.status === "running";
      if (live && Date.now() - s.createdAt < TIMEOUT_MS) active++;
    } catch {
      /* 손상 파일 무시 */
    }
  }
  return { today, active };
}

// 모든 '시작' 요청을 한 줄로 직렬화 — 한도 검사·유료 작업 생성·상태 기록이 끼어들지 않게(단일 Node 프로세스)
let startChain: Promise<unknown> = Promise.resolve();
export function startJob(id: string, file: string): Promise<JobView> {
  const p = startChain.then(() => doStart(id, file));
  startChain = p.catch(() => {});
  return p;
}

async function doStart(id: string, file: string): Promise<JobView> {
  const prev = await readState(id);
  if (prev) {
    if (prev.status === "starting") {
      if (Date.now() - prev.createdAt < STARTING_STALE_MS) return view(id, prev);
      // 생성 도중 서버가 죽은 흔적 — 아래에서 새로 생성(드문 경우)
    } else if (prev.status !== "failed") {
      // 진행 중·완료 작업은 재사용(재과금 없음). 완료인데 GLB 가 없으면 Tripo 에서 새 주소로 다시 받음
      const v = await refreshJob(id, true); // 진행 중인 조회·다운로드와 공유(임시 파일 충돌 방지)
      if (v) return v;
    }
  }
  if (!(await exists(path.join(GEN_DIR, file)))) {
    throw new TripoError("원본 생성 이미지가 없습니다(보관 기간이 지나 삭제되었을 수 있음).", "bad_input");
  }
  const { today, active } = await countStates();
  if (active >= MAX_ACTIVE) throw new TripoError("다른 3D 작업이 진행 중입니다. 잠시 후 다시 시도해 주세요.", "rate");
  if (DAILY_LIMIT && today >= DAILY_LIMIT)
    throw new TripoError(`오늘 3D 생성 한도(${DAILY_LIMIT}개)를 다 썼습니다.`, "rate");

  const base: JobState = { image: file, status: "starting", progress: 0, createdAt: Date.now() };
  await writeState(id, base); // 유료 호출 전에 먼저 기록
  let taskId: string;
  try {
    taskId = await createImageToModel(`${IMAGE_PUBLIC_BASE}/generated/${file}`);
  } catch (e) {
    // 생성 자체가 거절됨(과금 없음) → 상태 제거 대신 실패로 기록해 다시 시도 가능하게
    await writeState(id, { ...base, status: "failed", error: e instanceof Error ? e.message : "3D 요청 실패" });
    throw e;
  }
  const s: JobState = { ...base, taskId, status: "queued" };
  await writeState(id, s);
  return view(id, s);
}

// 라우트 번들이 나뉘어도 같은 작업의 조회·다운로드를 공유하도록 프로세스 전역에 둔다
type Shared = { lastPoll: Map<string, number>; refreshing: Map<string, Promise<JobView | null>> };
const g = globalThis as unknown as { __kinerag3d?: Shared };
const { lastPoll, refreshing } = (g.__kinerag3d ??= { lastPoll: new Map(), refreshing: new Map() });

// 상태 조회: 진행 중이면 Tripo 에 확인(작업당 2초에 1회 이하), 완료되면 GLB 를 즉시 내려받아 보관
export function refreshJob(id: string, force = false): Promise<JobView | null> {
  let p = refreshing.get(id);
  if (!p) {
    p = doRefresh(id, force).finally(() => refreshing.delete(id));
    refreshing.set(id, p);
  }
  return p;
}

async function doRefresh(id: string, force = false): Promise<JobView | null> {
  const s = await readState(id);
  if (!s) return null;
  if (s.status === "failed" || s.status === "starting" || !s.taskId) return view(id, s);
  if (s.status === "success" && (await exists(glbPath(id)))) return view(id, s);

  const now = Date.now();
  if (!force && now - (lastPoll.get(id) ?? 0) < 2000) return view(id, s);
  lastPoll.set(id, now);
  if (lastPoll.size > 1000) for (const [k, t] of lastPoll) if (now - t > TIMEOUT_MS) lastPoll.delete(k);

  let t;
  try {
    t = await getTask(s.taskId); // 매번 새로 조회 → 만료(5분)된 model_url 도 새 주소로 받음
  } catch {
    return view(id, { ...s, localError: "3D 서버 확인 지연 — 자동으로 다시 확인합니다." });
  }
  if (t.status === "success") {
    if (!t.modelUrl) return view(id, { ...s, localError: "3D 결과 주소가 아직 없습니다 — 다시 확인합니다." });
    try {
      await downloadGlb(id, t.modelUrl);
    } catch {
      // 결과는 Tripo 에 있음(이미 과금) — 실패로 바꾸지 않고 다음 조회·재클릭에서 다시 받는다
      const r: JobState = { ...s, status: "running", progress: 99, localError: "3D 파일 받기 지연 — 다시 시도합니다." };
      await writeState(id, r);
      return view(id, r);
    }
    const ok: JobState = { image: s.image, taskId: s.taskId, createdAt: s.createdAt, status: "success", progress: 100 };
    await writeState(id, ok);
    return view(id, ok);
  }
  if (t.status === "failed" || t.status === "cancelled") {
    const f: JobState = { ...s, status: "failed", localError: undefined, error: t.error || "3D 생성에 실패했습니다(크레딧은 차감되지 않음)." };
    await writeState(id, f);
    return view(id, f);
  }
  const next: JobState = {
    ...s,
    status: t.status === "queued" ? "queued" : "running",
    progress: t.progress,
    localError: Date.now() - s.createdAt > TIMEOUT_MS ? "평소보다 오래 걸립니다 — 계속 확인 중입니다." : undefined,
  };
  if (next.status !== s.status || next.progress !== s.progress || next.localError !== s.localError) await writeState(id, next);
  return view(id, next);
}

// 스트리밍 저장(메모리에 통째로 올리지 않음) + 크기 상한 + GLB 시그니처 확인
async function downloadGlb(id: string, url: string): Promise<void> {
  if (!/^https:\/\//i.test(url)) throw new Error("bad url");
  const res = await fetch(url, { cache: "no-store", signal: AbortSignal.timeout(120_000) });
  if (!res.ok || !res.body) throw new Error(`HTTP ${res.status}`);
  if (Number(res.headers.get("content-length") || 0) > MAX_GLB_BYTES) throw new Error("too large");
  const tmp = `${glbPath(id)}.${process.pid}.tmp`;
  const fh = await open(tmp, "w");
  let size = 0;
  let head = Buffer.alloc(0);
  try {
    for await (const chunk of res.body as unknown as AsyncIterable<Uint8Array>) {
      size += chunk.length;
      if (size > MAX_GLB_BYTES) throw new Error("too large");
      if (head.length < 4) head = Buffer.concat([head, Buffer.from(chunk)]).subarray(0, 4);
      await fh.write(chunk);
    }
  } catch (e) {
    await fh.close();
    await unlink(tmp).catch(() => {});
    throw e;
  }
  await fh.close();
  if (head.toString("ascii") !== "glTF") {
    await unlink(tmp).catch(() => {});
    throw new Error("not glb");
  }
  await rename(tmp, glbPath(id));
}
