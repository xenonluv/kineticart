// 서버 전용: 같은 Docker 네트워크의 PostgREST를 내부 호출(고속·비공개).
// 외부(브라우저)는 이 모듈을 쓰지 않고 Next 프록시 라우트(/api/*)를 통해 접근.
const INTERNAL =
  process.env.PGRST_INTERNAL_URL || "http://postgrest:3000";

export async function pgrst(path: string, init?: RequestInit): Promise<Response> {
  return fetch(`${INTERNAL}${path}`, { ...init, cache: "no-store" });
}
