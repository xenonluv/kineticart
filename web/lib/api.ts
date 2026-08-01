// 자체호스팅 PostgREST(api.kctikinec.cloud) 조회 헬퍼.
// 서버 컴포넌트에서만 호출(서버→서버 fetch).

export type Artwork = {
  id: string;
  title: string;
  artist: string | null;
  description: string | null;
  created_year: number | null;
  materials: string | null;
  dimensions: string | null;
  tags: string[] | null;
  image_url: string;
  detail_text_url: string | null;
  license: string | null;
  attribution: string | null;
  source_url: string | null;
};

const API_BASE = process.env.API_BASE || "https://api.kctikinec.cloud";

export async function getArtworks(): Promise<Artwork[]> {
  const url =
    `${API_BASE}/kinetic_artworks` +
    `?select=*&order=created_year.desc.nullslast`;
  const res = await fetch(url, { next: { revalidate: 3600 } });
  if (!res.ok) throw new Error(`REST API ${res.status}`);
  return res.json();
}

export async function getArtwork(id: string): Promise<Artwork | null> {
  const url = `${API_BASE}/kinetic_artworks?id=eq.${id}&select=*`;
  const res = await fetch(url, { next: { revalidate: 3600 } });
  if (!res.ok) throw new Error(`REST API ${res.status}`);
  const rows: Artwork[] = await res.json();
  return rows[0] ?? null;
}

// 상세 설명 원문(집 Mac 파일서버의 texts/NNN.txt)
export async function getDetailText(url: string | null): Promise<string | null> {
  if (!url) return null;
  try {
    const res = await fetch(url, { next: { revalidate: 3600 } });
    if (!res.ok) return null;
    return await res.text();
  } catch {
    return null;
  }
}
