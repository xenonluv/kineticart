"use client";
import { createElement, useEffect, useState } from "react";

// <model-viewer> 웹 컴포넌트(구글, three.js 기반)는 브라우저 전용 → 클라이언트에서만 동적 로드
export function ModelViewer({ src, alt }: { src: string; alt: string }) {
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

  if (failed) return <div className="grid h-56 place-items-center text-xs text-neutral-500">3D 미리보기를 불러오지 못했습니다.</div>;
  if (!ready) return <div className="grid h-56 place-items-center text-xs text-neutral-500">3D 뷰어 준비 중…</div>;
  return createElement("model-viewer", {
    src,
    alt,
    "camera-controls": true,
    "auto-rotate": true,
    "shadow-intensity": "1",
    "touch-action": "pan-y",
    style: { width: "100%", height: "14rem", background: "#171717" },
  });
}
