"use client";
import { useEffect, useRef } from "react";
import { Check, Plus } from "lucide-react";
import type { ArtworkLite } from "@/lib/types";
import { cn } from "@/lib/utils";

export function ArtworkGrid({
  items,
  loading,
  hasMore,
  loadMore,
  onOpen,
  onAddRef,
  isRef,
}: {
  items: ArtworkLite[];
  loading: boolean;
  hasMore: boolean;
  loadMore: () => void;
  onOpen: (id: string) => void;
  onAddRef: (a: ArtworkLite) => void;
  isRef: (id: string) => boolean;
}) {
  const sentinel = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const el = sentinel.current;
    if (!el) return;
    const io = new IntersectionObserver(
      (entries) => {
        if (entries[0].isIntersecting) loadMore();
      },
      { rootMargin: "600px" },
    );
    io.observe(el);
    return () => io.disconnect();
  }, [loadMore]);

  return (
    <main className="flex-1 overflow-y-auto p-4">
      {items.length === 0 && !loading && (
        <div className="grid h-full place-items-center text-sm text-neutral-500">
          조건에 맞는 작품이 없습니다.
        </div>
      )}

      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5">
        {items.map((a) => (
          <div
            key={a.id}
            className="group relative overflow-hidden rounded-lg bg-neutral-900 ring-1 ring-neutral-800"
            style={
              {
                contentVisibility: "auto",
                containIntrinsicSize: "260px",
              } as React.CSSProperties
            }
          >
            <button onClick={() => onOpen(a.id)} className="block w-full text-left">
              <div className="aspect-square overflow-hidden bg-neutral-800">
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img
                  src={a.image_url}
                  alt={a.title}
                  loading="lazy"
                  className="h-full w-full object-cover transition duration-500 group-hover:scale-105"
                />
              </div>
              <div className="p-2">
                <h3 className="truncate text-xs font-medium">{a.title}</h3>
                <p className="truncate text-[11px] text-neutral-400">
                  {a.artist ?? "작가 미상"}
                  {a.created_year ? ` · ${a.created_year}` : ""}
                </p>
              </div>
            </button>
            <button
              onClick={() => onAddRef(a)}
              title="참조로 담기"
              className={cn(
                "absolute right-2 top-2 grid h-7 w-7 place-items-center rounded-full text-white transition",
                isRef(a.id)
                  ? "bg-emerald-600 opacity-100"
                  : "bg-black/60 opacity-0 hover:bg-black/80 group-hover:opacity-100",
              )}
            >
              {isRef(a.id) ? <Check size={15} /> : <Plus size={15} />}
            </button>
          </div>
        ))}
      </div>

      <div ref={sentinel} className="h-10" />
      {loading && (
        <div className="py-6 text-center text-sm text-neutral-500">불러오는 중…</div>
      )}
      {!hasMore && items.length > 0 && (
        <div className="py-6 text-center text-xs text-neutral-600">— 끝 —</div>
      )}
    </main>
  );
}
