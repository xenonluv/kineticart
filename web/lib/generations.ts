// 서버 전용: 외부 전달용 REST(/api/v1/generations) 데이터 계층.
// 생성물의 원본은 파일(GENERATED_DIR)과 3D 상태(UPLOAD_DIR/3d-<id>.json) — DB 없이 이를 직접 읽어
// 자동 삭제(cleanup)와 목록이 어긋나지 않게 한다.
import { lstat, open, readdir } from "fs/promises";
import path from "path";
import { Readable } from "stream";
import { UPLOAD_DIR } from "./uploads";
import { retentionDays } from "./cleanup";
import { isJobId, readState, refreshJob, type JobState } from "./model3d";

const GEN_DIR = process.env.GENERATED_DIR || "/app/generated";
const API_BASE = (process.env.API_PUBLIC_BASE || "https://www.kctikinec.cloud").replace(/\/+$/, "");
const FILE_RE = /^(\d{13}-[0-9a-f]{8})\.(png|jpg|webp|glb)$/;
const STATE_RE = /^3d-(\d{13}-[0-9a-f]{8})\.json$/;
const IMAGE_EXTS = ["png", "jpg", "webp"] as const;
const MIME: Record<string, string> = {
  png: "image/png",
  jpg: "image/jpeg",
  webp: "image/webp",
  glb: "model/gltf-binary",
};
const DAY_MS = 24 * 3600 * 1000;
const OLD_POLL_MS = 10 * 60 * 1000; // 하루 넘게 미완료인 작업은 10분에 한 번만 Tripo 확인
const REFRESH_CONCURRENCY = 5;
const STARTING_STALE_MS = 5 * 60 * 1000; // 생성 요청 중 서버가 죽은 흔적으로 보는 시간(model3d 와 동일)
// 변경 동기화(since)에는 막 바뀐 항목을 잠시 숨긴다 — 파일 시각이 '보이게 된 시각'보다 약간 앞서므로,
// 안정화 전에 내주면 받는 쪽 기준점이 뒤늦게 나타난 항목을 지나칠 수 있다.
const SETTLE_MS = 5000;
const REFRESH_WAIT_MS = 3000; // GLB 다운로드는 백그라운드로 계속되고 응답은 기다리지 않음

export type ModelStatus = "none" | "queued" | "running" | "success" | "failed";
export type Generation = {
  id: string;
  created_at: string;
  updated_at: string;
  image: { url: string; mime: string; bytes: number } | null;
  model: { status: ModelStatus; progress: number; url: string | null; format: "glb" | null; bytes: number | null };
  expires_at: string | null; // 이 항목에서 가장 먼저 삭제될 파일의 예정 시각(자동 삭제 끔이면 null)
};

type Stat = { name: string; ext: string; size: number; mtimeMs: number };
type Entry = { id: string; image?: Stat; glb?: Stat; stateMtimeMs?: number };

const statFile = (dir: string, name: string) =>
  lstat(path.join(dir, name)).then(
    (s) => (s.isFile() ? s : null),
    () => null,
  );
const readdirSafe = (dir: string) => readdir(dir).catch(() => [] as string[]);

const lastOldPoll = new Map<string, number>();

function isDue(id: string, s: JobState | null): boolean {
  if (!s || !s.taskId || (s.status !== "queued" && s.status !== "running")) return false;
  const now = Date.now();
  const age = now - s.createdAt;
  if (age < DAY_MS) return true;
  if (age > (retentionDays() || 30) * DAY_MS || now - (lastOldPoll.get(id) ?? 0) < OLD_POLL_MS) return false;
  if (lastOldPoll.size > 2000) lastOldPoll.clear();
  lastOldPoll.set(id, now);
  return true;
}

// 브라우저가 닫혀 있어도 외부 조회만으로 3D 완성이 반영되도록, 조회 전에 진행 중 작업을 갱신한다.
async function refreshPending(ids: string[]): Promise<void> {
  const queue = [...ids];
  const work = Promise.all(
    Array.from({ length: REFRESH_CONCURRENCY }, async () => {
      for (let id = queue.shift(); id; id = queue.shift()) {
        const s = await readState(id).catch(() => null);
        if (isDue(id, s)) await refreshJob(id).catch(() => null);
      }
    }),
  );
  let timer: NodeJS.Timeout | undefined;
  await Promise.race([work, new Promise((r) => (timer = setTimeout(r, REFRESH_WAIT_MS)))]);
  clearTimeout(timer);
}

async function scan(): Promise<Map<string, Entry>> {
  const stateIds = (await readdirSafe(UPLOAD_DIR)).flatMap((n) => STATE_RE.exec(n)?.[1] ?? []);
  await refreshPending(stateIds);

  const map = new Map<string, Entry>();
  const get = (id: string) => {
    let e = map.get(id);
    if (!e) map.set(id, (e = { id }));
    return e;
  };
  await Promise.all(
    (await readdirSafe(GEN_DIR)).map(async (name) => {
      const m = FILE_RE.exec(name);
      if (!m) return;
      const st = await statFile(GEN_DIR, name);
      if (!st) return;
      const file: Stat = { name, ext: m[2], size: st.size, mtimeMs: st.mtimeMs };
      if (m[2] === "glb") get(m[1]).glb = file;
      else get(m[1]).image = file;
    }),
  );
  await Promise.all(
    stateIds.map(async (id) => {
      const e = map.get(id); // 파일이 모두 지워진 작업의 상태만 남은 경우는 목록에서 제외
      if (!e) return;
      const st = await statFile(UPLOAD_DIR, `3d-${id}.json`);
      if (st) e.stateMtimeMs = st.mtimeMs;
    }),
  );
  return map;
}

const updatedMs = (e: Entry) => Math.floor(Math.max(e.image?.mtimeMs ?? 0, e.glb?.mtimeMs ?? 0, e.stateMtimeMs ?? 0));

async function toGeneration(e: Entry): Promise<Generation> {
  const base = `${API_BASE}/api/v1/generations/${e.id}`;
  let model: Generation["model"] = { status: "none", progress: 0, url: null, format: null, bytes: null };
  if (e.glb) {
    model = { status: "success", progress: 100, url: `${base}/model`, format: "glb", bytes: e.glb.size };
  } else {
    const s = await readState(e.id);
    // 목록을 훑은 직후 다운로드가 끝났을 수 있어 한 번 더 확인. 그래도 없으면 GLB 가 삭제된 것 → none
    const late = s?.status === "success" ? await statFile(GEN_DIR, `${e.id}.glb`) : null;
    if (late) {
      model = { status: "success", progress: 100, url: `${base}/model`, format: "glb", bytes: late.size };
    } else if (s && s.status !== "success") {
      const age = Date.now() - s.createdAt;
      const dead = s.status === "failed" || (s.status === "starting" ? age > STARTING_STALE_MS : age > DAY_MS);
      model = {
        ...model,
        status: dead ? "failed" : s.status === "starting" ? "queued" : s.status,
        progress: dead ? 0 : Math.max(0, Math.min(100, Number(s.progress) || 0)),
      };
    }
  }
  const days = retentionDays();
  const oldest = Math.min(...[e.image, e.glb].filter((f): f is Stat => !!f).map((f) => f.mtimeMs));
  return {
    id: e.id,
    created_at: new Date(Number(e.id.slice(0, 13))).toISOString(),
    updated_at: new Date(updatedMs(e)).toISOString(),
    image: e.image ? { url: `${base}/image`, mime: MIME[e.image.ext], bytes: e.image.size } : null,
    model,
    expires_at: days ? new Date(oldest + days * 86_400_000).toISOString() : null,
  };
}

export type ListQuery = { type?: "2d" | "3d"; since?: number; afterId?: string; page: number; limit: number };

// since 가 있으면 오래된 변경부터 (updated_at, id) 순서로 이어받기(after_id). 페이지 번호는 항목이 변경되면
// 밀려서 건너뛸 수 있으므로 동기화에는 쓰지 않는다. since 가 없으면 최신순 페이지 조회.
export async function listGenerations(q: ListQuery) {
  let rows = [...(await scan()).values()].filter((e) => e.image || e.glb);
  if (q.type === "2d") rows = rows.filter((e) => e.image);
  if (q.type === "3d") rows = rows.filter((e) => e.glb);
  if (q.since !== undefined) {
    const { since, afterId } = q;
    const settled = Date.now() - SETTLE_MS;
    rows = rows.filter((e) => {
      const u = updatedMs(e);
      return u <= settled && (u > since || (u === since && (afterId === undefined || e.id > afterId)));
    });
  }
  const dir = q.since !== undefined ? 1 : -1;
  rows.sort((a, b) => dir * (updatedMs(a) - updatedMs(b)) || dir * (a.id < b.id ? -1 : a.id > b.id ? 1 : 0));
  const start = (q.page - 1) * q.limit;
  const items = await Promise.all(rows.slice(start, start + q.limit).map(toGeneration));
  return { items, page: q.page, limit: q.limit, total: rows.length, has_more: start + items.length < rows.length };
}

export async function getGeneration(id: string): Promise<Generation | null> {
  if (!isJobId(id)) return null;
  await refreshPending([id]);
  const e: Entry = { id };
  await Promise.all(
    [...IMAGE_EXTS, "glb"].map(async (ext) => {
      const name = `${id}.${ext}`;
      const st = await statFile(GEN_DIR, name);
      if (!st) return;
      const file: Stat = { name, ext, size: st.size, mtimeMs: st.mtimeMs };
      if (ext === "glb") e.glb = file;
      else e.image = file;
    }),
  );
  if (!e.image && !e.glb) return null;
  const st = await statFile(UPLOAD_DIR, `3d-${id}.json`);
  if (st) e.stateMtimeMs = st.mtimeMs;
  return toGeneration(e);
}

const fileHeaders = (name: string, ext: string, size: number) => ({
  "content-type": MIME[ext],
  "content-length": String(size),
  "content-disposition": `attachment; filename="${name}"`,
  "cache-control": "private, no-store",
  "x-content-type-options": "nosniff",
});
const notFound = () => Response.json({ error: "파일이 없습니다(보관 기간 경과 또는 미완성)." }, { status: 404 });
const candidates = (id: string, kind: "image" | "model") =>
  isJobId(id) ? (kind === "model" ? ["glb"] : [...IMAGE_EXTS]).map((ext) => ({ ext, name: `${id}.${ext}` })) : [];

// 파일 전달(미들웨어가 Bearer 키를 확인). 메모리에 올리지 않고 스트리밍.
export async function serveFile(id: string, kind: "image" | "model"): Promise<Response> {
  for (const { ext, name } of candidates(id, kind)) {
    if (!(await statFile(GEN_DIR, name))) continue;
    let fh;
    try {
      fh = await open(path.join(GEN_DIR, name), "r");
    } catch {
      continue; // 확인과 열기 사이에 삭제됨
    }
    let size: number;
    try {
      size = (await fh.stat()).size;
    } catch {
      await fh.close().catch(() => {});
      continue;
    }
    return new Response(Readable.toWeb(fh.createReadStream()) as ReadableStream, {
      headers: fileHeaders(name, ext, size),
    });
  }
  return notFound();
}

// HEAD: Next 기본 동작(GET 호출)은 열린 파일을 닫지 않으므로 파일을 열지 않고 응답
export async function headFile(id: string, kind: "image" | "model"): Promise<Response> {
  for (const { ext, name } of candidates(id, kind)) {
    const st = await statFile(GEN_DIR, name);
    if (st) return new Response(null, { headers: fileHeaders(name, ext, st.size) });
  }
  return new Response(null, { status: 404 });
}

// 시간대가 있는 ISO-8601 만 허용
export function parseSince(raw: string): number | null {
  const v = raw.replace(" ", "+"); // URL 에서 인코딩되지 않은 + 가 공백으로 온 경우
  if (!/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?(Z|[+-]\d{2}:\d{2})$/.test(v)) return null;
  const t = Date.parse(v);
  return Number.isFinite(t) ? t : null;
}
