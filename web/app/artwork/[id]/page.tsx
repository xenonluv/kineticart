import Link from "next/link";
import { notFound } from "next/navigation";
import { getArtwork, getDetailText } from "@/lib/api";

export const dynamic = "force-dynamic";

export default async function ArtworkPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  const art = await getArtwork(id);
  if (!art) notFound();

  const detail = await getDetailText(art.detail_text_url);

  return (
    <main className="mx-auto max-w-4xl px-4 py-10">
      <Link href="/" className="text-sm text-neutral-400 hover:text-neutral-200">
        ← 갤러리로
      </Link>

      <div className="mt-6 overflow-hidden rounded-xl bg-black ring-1 ring-neutral-800">
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img
          src={art.image_url}
          alt={art.title}
          className="max-h-[70vh] w-full object-contain"
        />
      </div>

      <div className="mt-6">
        <h1 className="text-2xl font-bold">{art.title}</h1>
        <p className="mt-1 text-neutral-400">
          {art.artist ?? "작가 미상"}
          {art.created_year ? ` · ${art.created_year}` : ""}
        </p>
        {art.materials && (
          <p className="mt-1 text-sm text-neutral-500">{art.materials}</p>
        )}

        {art.description && (
          <p className="mt-4 leading-relaxed">{art.description}</p>
        )}
        {detail && detail !== art.description && (
          <p className="mt-4 whitespace-pre-wrap leading-relaxed text-neutral-300">
            {detail}
          </p>
        )}

        {art.tags && art.tags.length > 0 && (
          <div className="mt-5 flex flex-wrap gap-2">
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
          <p className="mt-8 border-t border-neutral-800 pt-4 text-xs text-neutral-500">
            {art.license && <span>{art.license}</span>}
            {art.attribution && <span> · {art.attribution}</span>}
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
    </main>
  );
}
