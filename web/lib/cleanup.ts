// 서버 전용: 보관 기간이 지난 사용자 업로드 그림·AI 생성 이미지 자동 삭제.
// 서버가 만든 파일 이름 패턴만 지운다(다른 파일·하위 폴더·심볼릭 링크는 건드리지 않음).
import { lstat, readdir, unlink } from "fs/promises";
import path from "path";

const UPLOAD_DIR = process.env.UPLOAD_DIR || "/app/uploads";
const GEN_DIR = process.env.GENERATED_DIR || "/app/generated";

const UPLOAD_RE =
  /^([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\.(webp|json)|3d-\d{13}-[0-9a-f]{8}\.json)(\.\d+\.\d+\.tmp)?$/; // 그림·분석 캐시·3D 작업 상태
const GEN_RE = /^\d{13}-[0-9a-f]{8}\.(png|jpg|webp|glb)(\.\d+\.tmp)?$/; // 생성 이미지·3D 모델(GLB)

// 0 이하 또는 숫자가 아니면 자동 삭제 끔
export function retentionDays(): number {
  const n = Number(process.env.RETENTION_DAYS ?? 30);
  return Number.isFinite(n) && n > 0 ? n : 0;
}

async function sweep(dir: string, re: RegExp, cutoff: number): Promise<number> {
  let names: string[];
  try {
    names = await readdir(dir);
  } catch {
    return 0; // 폴더 없음
  }
  let n = 0;
  for (const name of names) {
    if (!re.test(name)) continue;
    const p = path.join(dir, name);
    try {
      const st = await lstat(p);
      if (!st.isFile() || st.mtimeMs >= cutoff) continue;
      await unlink(p);
      n++;
    } catch {
      /* 동시에 지워졌거나 권한 문제 — 다음 주기에 재시도 */
    }
  }
  return n;
}

export async function cleanupOldFiles(now = Date.now()): Promise<{ uploads: number; generated: number } | null> {
  const days = retentionDays();
  if (!days) return null;
  const cutoff = now - days * 24 * 60 * 60 * 1000;
  // 업로드 그림의 분석 캐시(.json)도 같은 기준 — 그림(.webp)과 함께 사라진다
  const [uploads, generated] = await Promise.all([
    sweep(UPLOAD_DIR, UPLOAD_RE, cutoff),
    sweep(GEN_DIR, GEN_RE, cutoff),
  ]);
  return { uploads, generated };
}

let started = false;
const INTERVAL_MS = 6 * 60 * 60 * 1000; // 6시간마다

export function startCleanupSchedule(): void {
  if (started || !retentionDays()) return;
  started = true;
  const run = () =>
    cleanupOldFiles()
      .then((r) => {
        if (r && (r.uploads || r.generated))
          console.log(`[cleanup] ${retentionDays()}일 경과 삭제: 업로드 ${r.uploads}, 생성 ${r.generated}`);
      })
      .catch((e) => console.error("[cleanup] 실패", e));
  setTimeout(run, 60_000).unref(); // 기동 1분 후 첫 실행
  setInterval(run, INTERVAL_MS).unref();
}
