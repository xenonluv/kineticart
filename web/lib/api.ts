// 서버 컴포넌트 전용 조회 헬퍼 — 내부 PostgREST·파일서버 직통(공개 도메인 왕복 없음).
import { fetchDetailText, isUuid, pgrst } from "./rest";
import type { ArtworkFull } from "./types";

export async function getArtwork(id: string): Promise<ArtworkFull | null> {
  if (!isUuid(id)) return null;
  const res = await pgrst(`/kinetic_artworks?id=eq.${id}&select=*`);
  if (!res.ok) throw new Error(`REST ${res.status}`);
  const rows: ArtworkFull[] = await res.json();
  return rows[0] ?? null;
}

// 상세 설명 원문(texts/NNN.txt)
export const getDetailText = fetchDetailText;
