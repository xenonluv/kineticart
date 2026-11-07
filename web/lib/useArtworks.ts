"use client";
import { useEffect, useRef, useState } from "react";
import type { ArtworkLite, Filters } from "./types";

export const PAGE_SIZE = 48;

function buildQs(f: Filters, offset: number): string {
  const p = new URLSearchParams();
  if (f.q) p.set("q", f.q);
  if (f.tags.length) p.set("tags", f.tags.join(","));
  if (f.artist) p.set("artist", f.artist);
  if (f.decade != null) p.set("decade", String(f.decade));
  p.set("sort", f.sort);
  p.set("limit", String(PAGE_SIZE));
  p.set("offset", String(offset));
  return p.toString();
}

// 페이지 번호 기반 데이터 훅. filters/page 가 바뀌면 해당 페이지만 로드(누적 없음).
// 새 요청이 시작되면 진행 중이던 이전 요청은 네트워크 수준에서 취소한다.
// enabled=false 동안은 요청하지 않는다(URL 상태 복원 전 불필요한 첫 요청 방지).
export function useArtworks(filters: Filters, page: number, enabled = true) {
  const [items, setItems] = useState<ArtworkLite[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(false);
  const reqId = useRef(0);

  useEffect(() => {
    if (!enabled) return;
    const id = ++reqId.current;
    const ac = new AbortController();
    setLoading(true);
    setError(false);
    fetch(`/api/artworks?${buildQs(filters, (page - 1) * PAGE_SIZE)}`, {
      signal: ac.signal,
    })
      .then((res) => {
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        return res.json();
      })
      .then((data) => {
        if (id !== reqId.current) return; // 오래된 응답 무시
        setItems(data.items);
        setTotal(data.total);
      })
      .catch((e) => {
        if ((e as Error).name === "AbortError") return; // 새 요청이 대체함
        if (id === reqId.current) {
          setItems([]);
          setError(true);
        }
      })
      .finally(() => {
        if (id === reqId.current) setLoading(false);
      });
    return () => ac.abort();
  }, [filters, page, enabled]);

  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));
  return { items, total, totalPages, loading, error };
}
