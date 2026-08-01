"use client";
import { useCallback, useState } from "react";
import { PanelRightClose, PanelRightOpen } from "lucide-react";
import type { ArtworkLite, Facets, Filters } from "@/lib/types";
import { DEFAULT_FILTERS } from "@/lib/types";
import { useArtworks } from "@/lib/useArtworks";
import { FilterRail } from "./FilterRail";
import { ArtworkGrid } from "./ArtworkGrid";
import { ChatPanel } from "./ChatPanel";
import { DetailModal } from "./DetailModal";

export function Studio({ facets }: { facets: Facets }) {
  const [filters, setFilters] = useState<Filters>(DEFAULT_FILTERS);
  const [references, setReferences] = useState<ArtworkLite[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [chatOpen, setChatOpen] = useState(true);
  const { items, total, loading, loadMore, nextOffset } = useArtworks(filters);

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
          value={filters.q}
          onChange={(e) => setFilters((f) => ({ ...f, q: e.target.value }))}
          placeholder="작품·작가·설명 검색…"
          className="w-full max-w-md rounded-md bg-neutral-900 px-3 py-1.5 text-sm text-neutral-100 ring-1 ring-neutral-800 outline-none focus:ring-neutral-600"
        />
        <span className="ml-auto whitespace-nowrap text-xs text-neutral-500">
          {total}점
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
          hasMore={nextOffset != null}
          loadMore={loadMore}
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
