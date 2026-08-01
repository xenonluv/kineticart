import { NextRequest, NextResponse } from "next/server";
import { pgrst } from "@/lib/rest";

export const dynamic = "force-dynamic";

const ORDER: Record<string, string> = {
  year_desc: "created_year.desc.nullslast",
  year_asc: "created_year.asc.nullsfirst",
  title_asc: "title.asc",
};

// 검색어에서 PostgREST 필터 문법 특수문자 제거(구문 깨짐 방지)
function sanitize(q: string): string {
  return q.replace(/[,().*]/g, " ").trim();
}

export async function GET(req: NextRequest) {
  const sp = req.nextUrl.searchParams;
  const q = sanitize(sp.get("q") ?? "");
  const tags = (sp.get("tags") ?? "").split(",").map((s) => s.trim()).filter(Boolean);
  const artist = sp.get("artist")?.trim();
  const decade = sp.get("decade");
  const sort = sp.get("sort") ?? "year_desc";
  const limit = Math.min(Math.max(Number(sp.get("limit") ?? 48), 1), 100);
  const offset = Math.max(Number(sp.get("offset") ?? 0), 0);

  const p = new URLSearchParams();
  p.set("select", "id,title,artist,created_year,image_url,tags");
  p.set("order", ORDER[sort] ?? ORDER.year_desc);
  if (q) {
    const like = `*${q}*`;
    p.set("or", `(title.ilike.${like},artist.ilike.${like},description.ilike.${like})`);
  }
  if (tags.length) p.set("tags", `ov.{${tags.join(",")}}`);
  if (artist) p.set("artist", `eq.${artist}`);
  if (decade) {
    const d = Number(decade);
    p.append("created_year", `gte.${d}`);
    p.append("created_year", `lt.${d + 10}`);
  }
  p.set("limit", String(limit));
  p.set("offset", String(offset));

  const res = await pgrst(`/kinetic_artworks?${p.toString()}`, {
    headers: { Prefer: "count=exact" },
  });
  if (!res.ok) {
    return NextResponse.json({ error: `REST ${res.status}` }, { status: 502 });
  }
  const items = await res.json();
  const range = res.headers.get("content-range"); // "0-47/69"
  const total = range && range.includes("/") ? Number(range.split("/")[1]) : items.length;
  const nextOffset = offset + items.length < total ? offset + items.length : null;

  return NextResponse.json({ items, total, nextOffset });
}
