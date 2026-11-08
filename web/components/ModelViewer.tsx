"use client";
import { createElement, useEffect, useState } from "react";
import { cn } from "@/lib/utils";

// <model-viewer> 웹 컴포넌트(구글, three.js 기반)는 브라우저 전용 → 클라이언트에서만 동적 로드
// fill: 부모 높이를 가득 채움(전면 팝업용). 기본은 대화 패널 안의 작은 미리보기.
export function ModelViewer({ src, alt, fill = false }: { src: string; alt: string; fill?: boolean }) {
  const box = cn("grid place-items-center text-xs text-neutral-500", fill ? "h-full" : "h-56");
  const [ready, setReady] = useState(false);
  const [failed, setFailed] = useState(false);
  useEffect(() => {
    let alive = true;
    import("@google/model-viewer")
      .then(() => alive && setReady(true))
      .catch(() => alive && setFailed(true));
    return () => {
      alive = false;
    };
  }, []);

  if (failed) return <div className={box}>3D 미리보기를 불러오지 못했습니다.</div>;
  if (!ready) return <div className={box}>3D 뷰어 준비 중…</div>;
  return createElement("model-viewer", {
    src,
    alt,
    "camera-controls": true,
    "auto-rotate": true,
    "shadow-intensity": "1",
    "touch-action": fill ? "none" : "pan-y", // 전면 팝업엔 스크롤이 없으므로 세로 드래그도 회전으로
    style: { width: "100%", height: fill ? "100%" : "14rem", background: "#171717" },
  });
}
