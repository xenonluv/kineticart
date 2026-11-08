// 사용자 그림 기반 생성 모드(클라이언트·서버 공용)
export const GEN_MODES = ["faithful", "fusion", "free"] as const;
export type GenMode = (typeof GEN_MODES)[number];

export const GEN_MODE_LABEL: Record<GenMode, { name: string; hint: string }> = {
  faithful: { name: "형태 충실", hint: "그림의 외곽선·구도를 그대로 실물 작품으로" },
  fusion: { name: "스타일 융합", hint: "그림 형태 + 참조 작품의 재질·분위기" },
  free: { name: "자유 해석", hint: "그림은 아이디어로만, 창의적으로 재해석" },
};

export function isGenMode(v: unknown): v is GenMode {
  return typeof v === "string" && (GEN_MODES as readonly string[]).includes(v);
}
