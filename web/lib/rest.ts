// 서버 전용: 같은 Docker 네트워크의 PostgREST·파일서버를 내부 호출(고속·비공개).
// 외부(브라우저)는 이 모듈을 쓰지 않고 Next 프록시 라우트(/api/*)를 통해 접근.
const INTERNAL =
  process.env.PGRST_INTERNAL_URL || "http://postgrest:3000";
const FILE_INTERNAL =
  process.env.FILE_SERVER_INTERNAL || "http://file-server:8787";
export const IMAGE_PUBLIC_BASE =
  process.env.IMAGE_PUBLIC_BASE || "https://images.kctikinec.cloud";

export async function pgrst(path: string, init?: RequestInit): Promise<Response> {
  return fetch(`${INTERNAL}${path}`, { ...init, cache: "no-store" });
}

// PostgREST 의 id 는 uuid — 그 외 문자열은 필터 구문 주입/불필요한 왕복이므로 거른다.
const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
export function isUuid(id: string): boolean {
  return UUID_RE.test(id);
}

// 공개 파일서버 URL(https://images…/texts/001.txt) → 내부 주소.
// 서버가 자기 공개 도메인을 다시 부르면 인터넷→Cloudflare→터널로 되돌아오는 hairpin 이 생긴다.
export function toInternalFileUrl(url: string): string {
  return url.startsWith(IMAGE_PUBLIC_BASE)
    ? FILE_INTERNAL + url.slice(IMAGE_PUBLIC_BASE.length)
    : url;
}

// 원본 URL(…/works/123.jpg) → 같은 작품의 768px 참조용 썸네일(…/thumbs/123.webp).
// thumbs/ 는 DB 에 노출하지 않는 내부 파생본(2b_derivatives) — 이미지 생성 참조에 쓴다.
export function refThumbUrl(imageUrl: string): string {
  return imageUrl.replace(/\/works\/([^/?#]+)\.[a-z0-9]+(?:[?#].*)?$/i, "/thumbs/$1.webp");
}

// 상세 설명 원문(texts/NNN.txt)을 내부 파일서버에서 읽는다. 실패하면 null.
export async function fetchDetailText(url: string | null | undefined): Promise<string | null> {
  if (!url) return null;
  try {
    const res = await fetch(toInternalFileUrl(url), { cache: "no-store" });
    return res.ok ? await res.text() : null;
  } catch {
    return null;
  }
}
