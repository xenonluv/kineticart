"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import { PanelRightClose, PanelRightOpen } from "lucide-react";
import type { ArtworkLite, Facets, Filters } from "@/lib/types";
import { DEFAULT_FILTERS } from "@/lib/types";
import { PAGE_SIZE, useArtworks } from "@/lib/useArtworks";
import { Pagination } from "./Pagination";
import { FilterRail } from "./FilterRail";
import { ArtworkGrid } from "./ArtworkGrid";
import { ChatPanel } from "./ChatPanel";
import { DetailModal } from "./DetailModal";

// 주소(URL) ↔ 화면 상태. 새로고침·뒤로가기·공유 시 같은 페이지/필터를 복원한다.
function readUrl(): { filters: Filters; page: number } {
  const p = new URLSearchParams(window.location.search);
  const num = (v: string | null) => (v != null && /^-?\d+$/.test(v) ? Number(v) : null);
  const page = Math.max(1, num(p.get("page")) ?? 1);
  return {
    page,
    filters: {
      q: p.get("q") ?? "",
      tags: (p.get("tags") ?? "").split(",").filter(Boolean),
      artist: p.get("artist") || null,
      decade: num(p.get("decade")),
      sort: p.get("sort") || DEFAULT_FILTERS.sort,
    },
  };
}

function toQs(f: Filters, page: number): string {
  const p = new URLSearchParams();
  if (f.q) p.set("q", f.q);
  if (f.tags.length) p.set("tags", f.tags.join(","));
  if (f.artist) p.set("artist", f.artist);
  if (f.decade != null) p.set("decade", String(f.decade));
  if (f.sort !== DEFAULT_FILTERS.sort) p.set("sort", f.sort);
  if (page > 1) p.set("page", String(page));
  const s = p.toString();
  return s ? `?${s}` : window.location.pathname;
}

export function Studio({ facets }: { facets: Facets }) {
  const [filters, setFiltersRaw] = useState<Filters>(DEFAULT_FILTERS);
  const [page, setPage] = useState(1);
  const [ready, setReady] = useState(false); // URL 복원 완료 전에는 조회하지 않음
  const scrollRef = useRef<HTMLElement>(null);

  // 필터가 바뀌면 항상 1페이지로
  const setFilters = useCallback((u: Filters | ((f: Filters) => Filters)) => {
    setFiltersRaw((prev) => {
      const next = typeof u === "function" ? u(prev) : u;
      if (JSON.stringify(next) === JSON.stringify(prev)) return prev; // 내용 동일 → 변화 없음
      setPage(1);
      return next;
    });
  }, []);
  const [references, setReferences] = useState<ArtworkLite[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [chatOpen, setChatOpen] = useState(true);
  const { items, total, totalPages, loading, error } = useArtworks(filters, page, ready);

  // 최초 1회: URL → 상태 복원, 뒤로/앞으로가기 시에도 복원
  useEffect(() => {
    const restore = () => {
      const s = readUrl();
      setFiltersRaw(s.filters);
      setQInput(s.filters.q);
      setPage(s.page);
    };
    restore();
    setReady(true);
    window.addEventListener("popstate", restore);
    return () => window.removeEventListener("popstate", restore);
  }, []);

  // 상태 → URL. 둘 다 정규형으로 비교(표기 차이로 인한 중복 push 방지).
  // 기본은 push(뒤로가기 가능), 검색어 입력·범위 보정은 replace(히스토리 오염 방지).
  const navMode = useRef<"push" | "replace">("push");
  useEffect(() => {
    if (!ready) return;
    const cur = readUrl();
    const url = toQs(filters, page);
    if (url !== toQs(cur.filters, cur.page)) {
      if (navMode.current === "replace") window.history.replaceState(null, "", url);
      else window.history.pushState(null, "", url);
    }
    navMode.current = "push";
  }, [filters, page, ready]);

  // 범위를 벗어난 페이지(예: 데이터 감소 후 옛 링크) → 마지막 페이지로
  useEffect(() => {
    if (!loading && !error && page > totalPages) {   // total=0 이면 totalPages=1 → 1페이지로
      navMode.current = "replace";
      setPage(totalPages);
    }
  }, [loading, error, total, page, totalPages]);

  const goPage = useCallback((p: number) => {
    setPage(p);
    scrollRef.current?.scrollTo({ top: 0 });
  }, []);

  // 검색어는 입력 즉시가 아니라 300ms 멈춘 뒤 반영 — 키 입력마다 API 호출 방지
  const [qInput, setQInput] = useState(filters.q);
  useEffect(() => {
    const t = setTimeout(() => {
      setFilters((f) => {
        if (f.q === qInput) return f;
        navMode.current = "replace"; // 실제로 바뀔 때만
        return { ...f, q: qInput };
      });
    }, 300);
    return () => clearTimeout(t);
  }, [qInput]);

  const addReference = useCallback((a: ArtworkLite) => {
    setReferences((prev) =>
      prev.find((x) => x.id === a.id) || prev.length >= 3 ? prev : [...prev, a],
    );
    setChatOpen(true);
  }, []);
  const removeReference = useCallback((id: string) => {
    setReferences((prev) => prev.filter((x) => x.id !== id));
  }, []);
  const isRef = useCallback(
    (id: string) => references.some((r) => r.id === id),
    [references],
  );

  return (
    <div className="flex h-screen flex-col">
      <header className="flex items-center gap-3 border-b border-neutral-800 px-4 py-2.5">
        <h1 className="hidden whitespace-nowrap text-base font-bold sm:block">
          키네틱 아트 스튜디오
        </h1>
        <input
          value={qInput}
          onChange={(e) => setQInput(e.target.value)}
          placeholder="작품·작가·설명 검색…"
          className="w-full max-w-md rounded-md bg-neutral-900 px-3 py-1.5 text-sm text-neutral-100 ring-1 ring-neutral-800 outline-none focus:ring-neutral-600"
        />
        <span className="ml-auto whitespace-nowrap text-xs text-neutral-500">
          {total > 0
            ? `${total}점 중 ${(page - 1) * PAGE_SIZE + 1}–${Math.min(page * PAGE_SIZE, total)}`
            : `${total}점`}
        </span>
        <button
          onClick={() => setChatOpen((v) => !v)}
          className="hidden rounded-md p-1.5 text-neutral-400 hover:bg-neutral-800 md:block"
          title="대화 패널 토글"
        >
          {chatOpen ? <PanelRightClose size={18} /> : <PanelRightOpen size={18} />}
        </button>
      </header>

      <div className="flex min-h-0 flex-1">
        <FilterRail facets={facets} filters={filters} setFilters={setFilters} />
        <ArtworkGrid
          items={items}
          loading={loading}
          error={error}
          scrollRef={scrollRef}
          footer={<Pagination page={page} totalPages={totalPages} onChange={goPage} />}
          onOpen={setSelectedId}
          onAddRef={addReference}
          isRef={isRef}
        />
        {chatOpen && (
          <ChatPanel references={references} onRemoveRef={removeReference} />
        )}
      </div>

      {selectedId && (
        <DetailModal
          id={selectedId}
          onClose={() => setSelectedId(null)}
          onAddRef={addReference}
        />
      )}
    </div>
  );
}
