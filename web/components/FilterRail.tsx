"use client";
import type { Dispatch, SetStateAction } from "react";
import type { Facets, Filters } from "@/lib/types";
import { cn } from "@/lib/utils";

const SORTS = [
  { v: "year_desc", label: "최신순" },
  { v: "year_asc", label: "오래된순" },
  { v: "title_asc", label: "제목순" },
];

export function FilterRail({
  facets,
  filters,
  setFilters,
}: {
  facets: Facets;
  filters: Filters;
  setFilters: Dispatch<SetStateAction<Filters>>;
}) {
  const toggleTag = (tag: string) =>
    setFilters((f) => ({
      ...f,
      tags: f.tags.includes(tag)
        ? f.tags.filter((t) => t !== tag)
        : [...f.tags, tag],
    }));

  return (
    <aside className="hidden w-56 shrink-0 overflow-y-auto border-r border-neutral-800 p-4 md:block">
      <Section title="정렬">
        <div className="flex flex-wrap gap-1">
          {SORTS.map((s) => (
            <Chip
              key={s.v}
              active={filters.sort === s.v}
              onClick={() => setFilters((f) => ({ ...f, sort: s.v }))}
            >
              {s.label}
            </Chip>
          ))}
        </div>
      </Section>

      <Section title="매체·움직임">
        <div className="flex flex-wrap gap-1.5">
          {facets.tags
            .filter((t) => t.tag !== "키네틱아트")
            .slice(0, 20)
            .map((t) => (
              <button
                key={t.tag}
                onClick={() => toggleTag(t.tag)}
                className={cn(
                  "rounded-full px-2.5 py-1 text-xs transition",
                  filters.tags.includes(t.tag)
                    ? "bg-emerald-600 text-white"
                    : "bg-neutral-900 text-neutral-300 hover:bg-neutral-800",
                )}
              >
                {t.tag} <span className="text-[10px] opacity-60">{t.count}</span>
              </button>
            ))}
        </div>
      </Section>

      <Section title="연대">
        <div className="flex flex-wrap gap-1.5">
          {facets.decades.map((d) => (
            <Chip
              key={d.decade}
              active={filters.decade === d.decade}
              onClick={() =>
                setFilters((f) => ({
                  ...f,
                  decade: f.decade === d.decade ? null : d.decade,
                }))
              }
            >
              {d.decade}s <span className="opacity-60">{d.count}</span>
            </Chip>
          ))}
        </div>
      </Section>

      <Section title="작가">
        <div className="flex flex-col gap-0.5">
          {facets.artists.slice(0, 15).map((a) => (
            <button
              key={a.artist}
              title={a.artist}
              onClick={() =>
                setFilters((f) => ({
                  ...f,
                  artist: f.artist === a.artist ? null : a.artist,
                }))
              }
              className={cn(
                "truncate rounded px-2 py-1 text-left text-xs transition",
                filters.artist === a.artist
                  ? "bg-neutral-100 text-neutral-900"
                  : "text-neutral-400 hover:bg-neutral-800",
              )}
            >
              {a.artist} <span className="opacity-60">{a.count}</span>
            </button>
          ))}
        </div>
      </Section>
    </aside>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="mb-5">
      <div className="mb-2 text-xs font-semibold text-neutral-500">{title}</div>
      {children}
    </div>
  );
}

function Chip({
  active,
  onClick,
  children,
}: {
  active: boolean;
  onClick: () => void;
  children: React.ReactNode;
}) {
  return (
    <button
      onClick={onClick}
      className={cn(
        "rounded px-2 py-1 text-xs transition",
        active
          ? "bg-neutral-100 text-neutral-900"
          : "bg-neutral-900 text-neutral-400 hover:bg-neutral-800",
      )}
    >
      {children}
    </button>
  );
}
