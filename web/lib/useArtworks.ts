"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import type { ArtworkLite, Filters } from "./types";

const PAGE = 48;

function buildQs(f: Filters, offset: number): string {
  const p = new URLSearchParams();
  if (f.q) p.set("q", f.q);
  if (f.tags.length) p.set("tags", f.tags.join(","));
  if (f.artist) p.set("artist", f.artist);
  if (f.decade != null) p.set("decade", String(f.decade));
  p.set("sort", f.sort);
  p.set("limit", String(PAGE));
  p.set("offset", String(offset));
  return p.toString();
}

// 필터 기반 무한스크롤 데이터 훅. filters 가 바뀌면 초기화 후 첫 페이지를 다시 로드.
// 새 요청이 시작되면 진행 중이던 이전 요청은 네트워크 수준에서 취소한다(응답만 무시하지 않음).
export function useArtworks(filters: Filters) {
  const [items, setItems] = useState<ArtworkLite[]>([]);
  const [total, setTotal] = useState(0);
  const [nextOffset, setNextOffset] = useState<number | null>(0);
  const [loading, setLoading] = useState(false);
  const reqId = useRef(0);
  const ctrl = useRef<AbortController | null>(null);

  const fetchPage = useCallback(
    async (offset: number, replace: boolean) => {
      const id = ++reqId.current;
      ctrl.current?.abort();
      const ac = new AbortController();
      ctrl.current = ac;
      setLoading(true);
      try {
        const res = await fetch(`/api/artworks?${buildQs(filters, offset)}`, {
          signal: ac.signal,
        });
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const data = await res.json();
        if (id !== reqId.current) return; // 오래된 응답 무시
        setItems((prev) => (replace ? data.items : [...prev, ...data.items]));
        setTotal(data.total);
        setNextOffset(data.nextOffset);
      } catch (e) {
        if ((e as Error).name === "AbortError") return; // 새 요청이 대체함
        if (id === reqId.current) setNextOffset(null);
      } finally {
        if (id === reqId.current) setLoading(false);
      }
    },
    [filters],
  );

  useEffect(() => {
    fetchPage(0, true);
  }, [fetchPage]);

  // 언마운트 시 진행 중 요청 정리
  useEffect(() => () => ctrl.current?.abort(), []);

  const loadMore = useCallback(() => {
    if (loading || nextOffset == null) return;
    fetchPage(nextOffset, false);
  }, [loading, nextOffset, fetchPage]);

  return { items, total, nextOffset, loading, loadMore };
}
