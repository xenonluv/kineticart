// Next.js 서버 기동 시 1회 호출 — 오래된 업로드·생성 파일 자동 정리 스케줄 시작(Node 런타임만)
export async function register() {
  if (process.env.NEXT_RUNTIME === "nodejs") {
    const { startCleanupSchedule } = await import("./lib/cleanup");
    startCleanupSchedule();
  }
}
