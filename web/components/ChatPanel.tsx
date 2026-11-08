"use client";
import { useEffect, useRef, useState } from "react";
import { Box, Check, Download, ImagePlus, Loader2, PencilLine, Plus, Send, Sparkles, X } from "lucide-react";
import { ModelViewer } from "./ModelViewer";
import type { ArtworkLite } from "@/lib/types";
import { fallbackTo, thumbOf } from "@/lib/types";
import { readSse } from "@/lib/sse";
import { cn } from "@/lib/utils";
import { GEN_MODES, GEN_MODE_LABEL, type GenMode } from "@/lib/genModes";

type SimilarLite = ArtworkLite & { score: number };
// 사용자가 올린 그림과 분석 상태
type Sketch = {
  id: string | null; // 업로드 완료 전엔 null
  preview: string; // 로컬 미리보기(blob URL)
  status: "uploading" | "analyzing" | "ready" | "error";
  description?: string;
  similar?: SimilarLite[];
  error?: string;
};
const MAX_SKETCH_BYTES = 8 * 1024 * 1024;
const SKETCH_TYPES = ["image/png", "image/jpeg", "image/webp", "image/gif"];

type Turn = {
  role: "user" | "assistant";
  content: string;
  image?: string; // 생성된 이미지 URL
  model3d?: Model3D; // 이 이미지로 만든 3D
};

type Model3D = {
  status: "starting" | "queued" | "running" | "success" | "failed";
  progress: number;
  url?: string;
  error?: string;
};

export function ChatPanel({
  references,
  onRemoveRef,
  onAddRef,
  isRef,
}: {
  references: ArtworkLite[];
  onRemoveRef: (id: string) => void;
  onAddRef: (a: ArtworkLite) => void;
  isRef: (id: string) => boolean;
}) {
  const [turns, setTurns] = useState<Turn[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [generating, setGenerating] = useState(false);
  const [lightbox, setLightbox] = useState<string | null>(null); // 확대 팝업 이미지 URL
  const bottom = useRef<HTMLDivElement>(null);
  const alive = useRef(true);
  useEffect(() => {
    alive.current = true;
    return () => {
      alive.current = false; // 언마운트 후 진행 확인 중단
    };
  }, []);

  // 같은 이미지 URL 의 턴만 갱신(턴 순서가 바뀌어도 안전)
  const patch3d = (image: string, m: Model3D) =>
    setTurns((prev) => prev.map((t) => (t.image === image ? { ...t, model3d: m } : t)));

  const make3d = async (image: string) => {
    patch3d(image, { status: "starting", progress: 0 });
    try {
      const res = await fetch("/api/generate-3d", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ imageUrl: image }),
      });
      let d = await res.json().catch(() => ({}));
      if (!res.ok || !d.job) throw new Error(d.error || "3D 요청 실패");
      const job: string = d.job;
      // 완료·실패까지 3초 간격 확인(최대 약 15분)
      for (let i = 0; i < 300 && alive.current; i++) {
        if (d.status === "success") return patch3d(image, { status: "success", progress: 100, url: d.modelUrl });
        if (d.status === "failed") throw new Error(d.error || "3D 생성 실패");
        patch3d(image, { status: d.status === "starting" ? "starting" : d.status, progress: d.progress ?? 0, error: d.error });
        await new Promise((r) => setTimeout(r, 3000));
        const r = await fetch(`/api/generate-3d/${job}`).catch(() => null);
        if (r?.ok) d = await r.json().catch(() => d);
        else if (r && r.status !== 500) d = { status: "failed", error: (await r.json().catch(() => ({}))).error };
      }
      if (alive.current) throw new Error("3D 생성 확인 시간이 초과되었습니다. 다시 눌러 확인해 주세요.");
    } catch (e) {
      if (alive.current) patch3d(image, { status: "failed", progress: 0, error: (e as Error).message });
    }
  };
  const [sketch, setSketch] = useState<Sketch | null>(null);
  const [mode, setMode] = useState<GenMode>("faithful");
  const fileInput = useRef<HTMLInputElement>(null);
  const sketchSeq = useRef(0); // 그림 교체·삭제 시 이전 업로드/분석 응답 무시

  // 미리보기 blob URL 해제(교체·삭제·언마운트)
  const preview = sketch?.preview;
  useEffect(() => () => {
    if (preview) URL.revokeObjectURL(preview);
  }, [preview]);

  const patchSketch = (seq: number, patch: Partial<Sketch>) => {
    if (seq === sketchSeq.current) setSketch((s) => (s ? { ...s, ...patch } : s));
  };

  const pickSketch = async (file: File | undefined) => {
    if (!file) return;
    if (!SKETCH_TYPES.includes(file.type)) {
      alert("PNG·JPG·WebP·GIF 이미지만 올릴 수 있습니다.");
      return;
    }
    if (file.size > MAX_SKETCH_BYTES) {
      alert("파일이 너무 큽니다(최대 8MB).");
      return;
    }
    const seq = ++sketchSeq.current;
    setSketch({ id: null, preview: URL.createObjectURL(file), status: "uploading" });
    try {
      const fd = new FormData();
      fd.append("file", file);
      const up = await fetch("/api/upload", { method: "POST", body: fd });
      const ud = await up.json().catch(() => ({}));
      if (!up.ok || !ud.id) throw new Error(ud.error || "업로드 실패");
      patchSketch(seq, { id: ud.id, status: "analyzing" });

      const an = await fetch("/api/sketch/analyze", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ uploadId: ud.id }),
      });
      const ad = await an.json().catch(() => ({}));
      if (!an.ok || !ad.description) {
        // 업로드는 성공 → 그림만으로도 생성은 가능
        patchSketch(seq, { status: "ready", error: ad.error || "그림 인식 실패(생성은 가능)" });
        return;
      }
      patchSketch(seq, {
        status: "ready",
        description: ad.description,
        similar: ad.similar ?? [],
        error: ad.similarError ? "비슷한 작품 검색을 잠시 사용할 수 없습니다." : undefined,
      });
    } catch (e) {
      patchSketch(seq, { status: "error", error: (e as Error).message || "업로드 실패" });
    }
  };

  const clearSketch = () => {
    sketchSeq.current++;
    setSketch(null);
  };
  const sketchReady = sketch?.status === "ready" && !!sketch.id;
  const sketchBusy = sketch?.status === "uploading" || sketch?.status === "analyzing";
  const sketchFailed = sketch?.status === "error"; // 실패한 그림이 보이는데 그림 없이 생성되는 혼동 방지

  // 모드 라디오: 화살표 키로 이동(선택된 항목만 Tab 정지)
  const onModeKey = (e: React.KeyboardEvent) => {
    const d = e.key === "ArrowRight" || e.key === "ArrowDown" ? 1 : e.key === "ArrowLeft" || e.key === "ArrowUp" ? -1 : 0;
    if (!d) return;
    e.preventDefault();
    const next = GEN_MODES[(GEN_MODES.indexOf(mode) + d + GEN_MODES.length) % GEN_MODES.length];
    setMode(next);
    (e.currentTarget.querySelector(`[data-mode="${next}"]`) as HTMLElement | null)?.focus();
  };

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
          uploadId: sketchReady ? sketch!.id : undefined,
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
    if (busy || generating || sketchBusy) return;
    const useSketch = sketchReady;
    // 스타일 융합인데 담은 참조가 없으면 '비슷한 작품' 상위 2점을 자동 사용
    let refIds = references.map((r) => r.id);
    if (useSketch && mode === "fusion" && refIds.length === 0) {
      refIds = (sketch!.similar ?? []).slice(0, 2).map((a) => a.id);
      if (refIds.length === 0) {
        alert("스타일 융합은 참조 작품이 필요합니다. 갤러리에서 작품을 담아 주세요.");
        return;
      }
    }
    const concept = turns
      .filter((t) => t.role === "user")
      .map((t) => t.content)
      .join(" ")
      .trim();
    setTurns((prev) => [
      ...prev,
      {
        role: "assistant",
        content: useSketch
          ? `🎨 내 그림으로 생성 중… [${GEN_MODE_LABEL[mode].name}] (수 초 소요)`
          : "🎨 이미지 생성 중… (수 초 소요)",
      },
    ]);
    setGenerating(true);
    try {
      const res = await fetch("/api/generate-image", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(
          useSketch
            ? { concept, referenceIds: refIds, uploadId: sketch!.id, mode }
            : { concept, referenceIds: refIds },
        ),
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
    !sketchBusy &&
    !sketchFailed &&
    (sketchReady || references.length > 0 || turns.some((t) => t.role === "user"));

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
            <br />
            직접 그린 그림은 입력창 왼쪽 ✏️ 버튼으로 올릴 수 있어요.
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
                  {t.model3d?.status === "success" && t.model3d.url ? (
                    <a
                      href={t.model3d.url}
                      download
                      className="flex items-center gap-1 rounded bg-emerald-600 px-2 py-1 text-[11px] text-white hover:bg-emerald-500"
                    >
                      <Download size={12} /> GLB 다운로드
                    </a>
                  ) : (
                    <button
                      type="button"
                      onClick={() => make3d(t.image!)}
                      disabled={!!t.model3d && t.model3d.status !== "failed"}
                      title="이 이미지로 3D 모델(GLB) 만들기 · 약 1~2분"
                      className="flex items-center gap-1 rounded bg-neutral-700 px-2 py-1 text-[11px] text-neutral-200 hover:bg-neutral-600 disabled:text-neutral-400"
                    >
                      {t.model3d && t.model3d.status !== "failed" ? (
                        <>
                          <Loader2 size={12} className="animate-spin" /> 3D 생성 중 {t.model3d.progress}%
                        </>
                      ) : (
                        <>
                          <Box size={12} /> {t.model3d?.status === "failed" ? "3D 다시 시도" : "3D 만들기"}
                        </>
                      )}
                    </button>
                  )}
                </div>
                {t.model3d && t.model3d.status !== "success" && t.model3d.error && (
                  <p className={cn("px-2 pb-2 text-[11px]", t.model3d.status === "failed" ? "text-amber-400" : "text-neutral-500")}>
                    {t.model3d.error}
                  </p>
                )}
                {t.model3d?.status === "success" && t.model3d.url && (
                  <ModelViewer src={t.model3d.url} alt="생성된 3D 키네틱 아트" />
                )}
              </div>
            ) : (
              t.content || (busy && i === turns.length - 1 ? "…" : "")
            )}
          </div>
        ))}
        <div ref={bottom} />
      </div>

      {sketch && (
        <div className="max-h-[45%] overflow-y-auto border-t border-neutral-800 p-3">
          <div className="mb-2 flex items-center justify-between text-xs text-neutral-500">
            <span className="flex items-center gap-1">
              <PencilLine size={12} /> 내 그림
            </span>
            <button type="button" onClick={clearSketch} className="hover:text-neutral-300" title="그림 빼기">
              <X size={13} />
            </button>
          </div>
          <div className="flex gap-3">
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img
              src={sketch.preview}
              alt="내 그림"
              onClick={() => setLightbox(sketch.preview)}
              className="h-20 w-20 shrink-0 cursor-zoom-in rounded bg-white object-contain ring-1 ring-neutral-700"
            />
            <div className="min-w-0 text-xs leading-relaxed text-neutral-300">
              {sketchBusy && (
                <span className="flex items-center gap-1 text-neutral-500">
                  <Loader2 size={12} className="animate-spin" />
                  {sketch.status === "uploading" ? "올리는 중…" : "그림을 읽는 중…"}
                </span>
              )}
              {sketch.description && <p className="line-clamp-4" title={sketch.description}>{sketch.description}</p>}
              {sketch.error && <p className="mt-1 text-amber-400">{sketch.error}</p>}
              {sketchFailed && (
                <p className="mt-1 text-neutral-500">그림을 다시 올리거나 ✕로 빼야 생성할 수 있습니다.</p>
              )}
            </div>
          </div>

          {sketchReady && (
            <div className="mt-3 grid grid-cols-3 gap-1" role="radiogroup" aria-label="생성 모드" onKeyDown={onModeKey}>
              {GEN_MODES.map((m) => (
                <button
                  key={m}
                  type="button"
                  data-mode={m}
                  tabIndex={mode === m ? 0 : -1}
                  role="radio"
                  aria-checked={mode === m}
                  onClick={() => setMode(m)}
                  title={GEN_MODE_LABEL[m].hint}
                  className={cn(
                    "rounded-md px-1 py-1.5 text-[11px] transition",
                    mode === m
                      ? "bg-emerald-600 text-white"
                      : "bg-neutral-800 text-neutral-300 hover:bg-neutral-700",
                  )}
                >
                  {GEN_MODE_LABEL[m].name}
                </button>
              ))}
              <p className="col-span-3 mt-1 text-[11px] text-neutral-500">
                {GEN_MODE_LABEL[mode].hint}
                {mode === "fusion" && references.length === 0 && " — 담은 참조가 없으면 비슷한 작품 2점을 사용"}
              </p>
            </div>
          )}

          {!!sketch.similar?.length && (
            <div className="mt-3">
              <div className="mb-1 text-[11px] text-neutral-500">비슷한 갤러리 작품</div>
              <div className="flex gap-2 overflow-x-auto pb-1">
                {sketch.similar.map((a) => (
                  <div key={a.id} className="group relative h-14 w-14 shrink-0 overflow-hidden rounded ring-1 ring-neutral-700" title={`${a.title} · ${a.artist ?? "작가 미상"}`}>
                    {/* eslint-disable-next-line @next/next/no-img-element */}
                    <img src={thumbOf(a)} onError={fallbackTo(a.image_url)} alt={a.title} className="h-full w-full object-cover" />
                    <button
                      onClick={() => onAddRef(a)}
                      title="참조로 담기"
                      className={cn(
                        "absolute right-0 top-0 grid h-5 w-5 place-items-center rounded-bl text-white",
                        isRef(a.id) ? "bg-emerald-600" : "bg-black/70",
                      )}
                    >
                      {isRef(a.id) ? <Check size={11} /> : <Plus size={11} />}
                    </button>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}

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
                <img src={thumbOf(r)} onError={fallbackTo(r.image_url)} alt={r.title} className="h-full w-full object-cover" />
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
          <input
            ref={fileInput}
            type="file"
            accept={SKETCH_TYPES.join(",")}
            className="hidden"
            onChange={(e) => {
              pickSketch(e.target.files?.[0]);
              e.target.value = ""; // 같은 파일 다시 선택 가능
            }}
          />
          <button
            onClick={() => fileInput.current?.click()}
            disabled={generating || sketchBusy}
            className="grid h-7 w-7 shrink-0 place-items-center rounded text-neutral-400 hover:bg-neutral-800 hover:text-neutral-200 disabled:opacity-40"
            title="내 그림 올리기"
          >
            <PencilLine size={15} />
          </button>
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
          {generating
            ? "생성 중…"
            : sketchReady
              ? `내 그림으로 생성 · ${GEN_MODE_LABEL[mode].name}`
              : "이 컨셉으로 이미지 생성"}
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
