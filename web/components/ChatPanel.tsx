"use client";
import { useEffect, useRef, useState } from "react";
import { Box, ImagePlus, Send, Sparkles, X } from "lucide-react";
import type { ArtworkLite } from "@/lib/types";
import { readSse } from "@/lib/sse";
import { cn } from "@/lib/utils";

type Turn = {
  role: "user" | "assistant";
  content: string;
  image?: string; // 생성된 이미지 URL
};

export function ChatPanel({
  references,
  onRemoveRef,
}: {
  references: ArtworkLite[];
  onRemoveRef: (id: string) => void;
}) {
  const [turns, setTurns] = useState<Turn[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [generating, setGenerating] = useState(false);
  const [lightbox, setLightbox] = useState<string | null>(null); // 확대 팝업 이미지 URL
  const bottom = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottom.current?.scrollIntoView({ behavior: "smooth" });
  }, [turns]);

  const patchLast = (fn: (t: Turn) => Turn) =>
    setTurns((prev) => {
      const c = [...prev];
      c[c.length - 1] = fn(c[c.length - 1]);
      return c;
    });

  const send = async () => {
    const text = input.trim();
    if (!text || busy || generating) return;
    setInput("");
    const base: Turn[] = [...turns, { role: "user", content: text }];
    setTurns([...base, { role: "assistant", content: "" }]);
    setBusy(true);
    try {
      const res = await fetch("/api/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          messages: base.map((t) => ({ role: t.role, content: t.content })),
          referenceIds: references.map((r) => r.id),
        }),
      });
      for await (const ev of readSse<{ text?: string; error?: string }>(res)) {
        if (ev.text) patchLast((t) => ({ ...t, content: t.content + ev.text }));
        else if (ev.error) patchLast((t) => ({ ...t, content: `⚠️ ${ev.error}` }));
      }
    } catch {
      /* 무시 */
    } finally {
      setBusy(false);
    }
  };

  const generate = async () => {
    if (busy || generating) return;
    const concept = turns
      .filter((t) => t.role === "user")
      .map((t) => t.content)
      .join(" ")
      .trim();
    setTurns((prev) => [
      ...prev,
      { role: "assistant", content: "🎨 이미지 생성 중… (수 초 소요)" },
    ]);
    setGenerating(true);
    try {
      const res = await fetch("/api/generate-image", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ concept, referenceIds: references.map((r) => r.id) }),
      });
      const data = await res.json();
      if (data.imageUrl) {
        patchLast(() => ({ role: "assistant", content: "", image: data.imageUrl }));
      } else {
        patchLast(() => ({ role: "assistant", content: `⚠️ ${data.error ?? "생성 실패"}` }));
      }
    } catch {
      patchLast(() => ({ role: "assistant", content: "⚠️ 생성 요청 실패" }));
    } finally {
      setGenerating(false);
    }
  };

  const canGenerate =
    !busy &&
    !generating &&
    (references.length > 0 || turns.some((t) => t.role === "user"));

  return (
    <aside className="hidden w-full max-w-sm shrink-0 flex-col border-l border-neutral-800 md:flex">
      <div className="border-b border-neutral-800 px-4 py-3">
        <h2 className="flex items-center gap-2 text-sm font-semibold">
          <Sparkles size={15} className="text-emerald-500" /> 창작 대화
        </h2>
        <p className="mt-0.5 text-xs text-neutral-500">
          작품을 참조로 담고 어떤 키네틱 아트를 만들지 이야기해 보세요.
        </p>
      </div>

      <div className="flex-1 space-y-3 overflow-y-auto p-4">
        {turns.length === 0 && (
          <div className="grid h-full place-items-center px-4 text-center text-xs leading-relaxed text-neutral-600">
            예) “바람에 천천히 도는 금속 모빌을 만들고 싶어. 물결 같은 느낌으로.”
          </div>
        )}
        {turns.map((t, i) => (
          <div
            key={i}
            className={cn(
              "max-w-[92%] rounded-lg text-sm leading-relaxed",
              t.role === "user"
                ? "ml-auto bg-emerald-600 px-3 py-2 text-white"
                : t.image
                  ? "overflow-hidden bg-neutral-800"
                  : "bg-neutral-800 px-3 py-2 text-neutral-100",
            )}
          >
            {t.image ? (
              <div>
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img
                  src={t.image}
                  alt="생성된 키네틱 아트"
                  onClick={() => setLightbox(t.image!)}
                  title="클릭하면 크게 보기"
                  className="w-full cursor-zoom-in"
                />
                <div className="flex items-center justify-between p-2">
                  <span className="text-xs text-neutral-400">생성 이미지</span>
                  <button
                    disabled
                    title="다음 단계(Phase 5)에서 연결"
                    className="flex items-center gap-1 rounded bg-neutral-700 px-2 py-1 text-[11px] text-neutral-400"
                  >
                    <Box size={12} /> 3D 만들기
                  </button>
                </div>
              </div>
            ) : (
              t.content || (busy && i === turns.length - 1 ? "…" : "")
            )}
          </div>
        ))}
        <div ref={bottom} />
      </div>

      {references.length > 0 && (
        <div className="border-t border-neutral-800 p-3">
          <div className="mb-2 text-xs text-neutral-500">참조 이미지 {references.length}/3</div>
          <div className="flex gap-2">
            {references.map((r) => (
              <div
                key={r.id}
                className="relative h-14 w-14 overflow-hidden rounded ring-1 ring-neutral-700"
              >
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img src={r.image_url} alt={r.title} className="h-full w-full object-cover" />
                <button
                  onClick={() => onRemoveRef(r.id)}
                  className="absolute right-0 top-0 grid h-4 w-4 place-items-center rounded-bl bg-black/70 text-white"
                >
                  <X size={11} />
                </button>
              </div>
            ))}
          </div>
        </div>
      )}

      <div className="border-t border-neutral-800 p-3">
        <div className="flex items-end gap-2 rounded-lg bg-neutral-900 px-3 py-2 ring-1 ring-neutral-800 focus-within:ring-neutral-600">
          <textarea
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
                e.preventDefault();
                send();
              }
            }}
            rows={1}
            placeholder="메시지를 입력하세요…"
            className="max-h-28 w-full resize-none bg-transparent text-sm outline-none placeholder:text-neutral-600"
          />
          <button
            onClick={send}
            disabled={busy || generating || !input.trim()}
            className="grid h-7 w-7 shrink-0 place-items-center rounded bg-neutral-700 text-white disabled:text-neutral-500"
            title="보내기"
          >
            <Send size={14} />
          </button>
        </div>
        <button
          onClick={generate}
          disabled={!canGenerate}
          className="mt-2 flex w-full items-center justify-center gap-1.5 rounded-lg bg-emerald-600 py-2 text-sm font-medium text-white transition hover:bg-emerald-500 disabled:bg-neutral-800 disabled:text-neutral-600"
        >
          <ImagePlus size={15} />
          {generating ? "생성 중…" : "이 컨셉으로 이미지 생성"}
        </button>
      </div>
      {/* 이미지 확대 팝업 — 화면 정중앙, 아무 곳이나 클릭하면 닫힘 */}
      {lightbox && (
        <div
          className="fixed inset-0 z-[60] flex cursor-zoom-out items-center justify-center bg-black/85 p-4"
          onClick={() => setLightbox(null)}
        >
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img
            src={lightbox}
            alt="확대 이미지"
            className="max-h-[95vh] max-w-[95vw] object-contain"
          />
        </div>
      )}
    </aside>
  );
}
