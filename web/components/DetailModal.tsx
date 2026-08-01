"use client";
import { useEffect, useState } from "react";
import { Plus, X } from "lucide-react";
import type { ArtworkFull, ArtworkLite } from "@/lib/types";

export function DetailModal({
  id,
  onClose,
  onAddRef,
}: {
  id: string;
  onClose: () => void;
  onAddRef: (a: ArtworkLite) => void;
}) {
  const [art, setArt] = useState<ArtworkFull | null>(null);
  const [detail, setDetail] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    fetch(`/api/artwork/${id}`)
      .then((r) => r.json())
      .then((d) => {
        if (!alive) return;
        setArt(d.artwork ?? null);
        setDetail(d.detailText ?? null);
      })
      .catch(() => {});
    return () => {
      alive = false;
    };
  }, [id]);

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4"
      onClick={onClose}
    >
      <div
        className="relative max-h-[90vh] w-full max-w-3xl overflow-y-auto rounded-xl bg-neutral-900 ring-1 ring-neutral-700"
        onClick={(e) => e.stopPropagation()}
      >
        <button
          onClick={onClose}
          className="absolute right-3 top-3 z-10 grid h-8 w-8 place-items-center rounded-full bg-black/60 text-white hover:bg-black/80"
        >
          <X size={18} />
        </button>

        {!art ? (
          <div className="grid h-64 place-items-center text-neutral-500">
            불러오는 중…
          </div>
        ) : (
          <>
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img
              src={art.image_url}
              alt={art.title}
              className="max-h-[60vh] w-full bg-black object-contain"
            />
            <div className="p-5">
              <div className="flex items-start justify-between gap-4">
                <div>
                  <h2 className="text-xl font-bold">{art.title}</h2>
                  <p className="mt-1 text-neutral-400">
                    {art.artist ?? "작가 미상"}
                    {art.created_year ? ` · ${art.created_year}` : ""}
                  </p>
                </div>
                <button
                  onClick={() => onAddRef(art)}
                  className="flex shrink-0 items-center gap-1 rounded-md bg-emerald-600 px-3 py-1.5 text-sm text-white hover:bg-emerald-500"
                >
                  <Plus size={15} /> 참조 담기
                </button>
              </div>
              {art.materials && (
                <p className="mt-1 text-sm text-neutral-500">{art.materials}</p>
              )}
              {art.description && (
                <p className="mt-4 leading-relaxed">{art.description}</p>
              )}
              {detail && detail !== art.description && (
                <p className="mt-3 whitespace-pre-wrap leading-relaxed text-neutral-300">
                  {detail}
                </p>
              )}
              {art.tags && art.tags.length > 0 && (
                <div className="mt-4 flex flex-wrap gap-1.5">
                  {art.tags.map((t) => (
                    <span
                      key={t}
                      className="rounded bg-neutral-800 px-2 py-0.5 text-xs text-neutral-300"
                    >
                      {t}
                    </span>
                  ))}
                </div>
              )}
              {(art.attribution || art.source_url || art.license) && (
                <p className="mt-5 border-t border-neutral-800 pt-3 text-xs text-neutral-500">
                  {art.license}
                  {art.attribution ? ` · ${art.attribution}` : ""}
                  {art.source_url && (
                    <>
                      {" · "}
                      <a
                        href={art.source_url}
                        target="_blank"
                        rel="noreferrer"
                        className="underline hover:text-neutral-300"
                      >
                        출처
                      </a>
                    </>
                  )}
                </p>
              )}
            </div>
          </>
        )}
      </div>
    </div>
  );
}
