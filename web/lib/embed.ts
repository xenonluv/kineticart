// 서버 전용: 내부 embed 컨테이너(e5-large) 호출 → 한글 텍스트와 비슷한 갤러리 작품.
import { pgrst } from "./rest";
import type { ArtworkLite } from "./types";

const EMBED = process.env.EMBED_INTERNAL_URL || "http://embed:8000";
const LITE = "id,title,artist,created_year,image_url,thumbnail_url,tags";

export type SimilarArtwork = ArtworkLite & { score: number };

export async function similarArtworks(text: string, k = 6): Promise<SimilarArtwork[]> {
  const res = await fetch(`${EMBED}/similar`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ text, k }),
    cache: "no-store",
    signal: AbortSignal.timeout(30_000),
  });
  if (!res.ok) throw new Error(`embed ${res.status}`);
  const { results } = (await res.json()) as { results: { image_url: string; score: number }[] };
  if (!results?.length) return [];

  // manifest 의 image_url ↔ DB image_url 로 연결(값에 : / 가 있어 큰따옴표로 감쌈)
  const list = results.map((r) => `"${r.image_url.replace(/"/g, "")}"`).join(",");
  const db = await pgrst(`/kinetic_artworks?select=${LITE}&image_url=in.(${encodeURIComponent(list)})`);
  if (!db.ok) throw new Error(`db ${db.status}`);
  const rows: ArtworkLite[] = await db.json();
  const byUrl = new Map(rows.map((r) => [r.image_url, r]));
  return results.flatMap((r) => {
    const a = byUrl.get(r.image_url);
    return a ? [{ ...a, score: r.score }] : []; // DB 에서 빠진 작품은 제외
  });
}
