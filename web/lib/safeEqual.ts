// 상수 시간 문자열 비교(엣지·노드 공용) — 비밀번호/토큰 비교 시 타이밍 정보 노출 방지
export function safeEqual(a: string, b: string): boolean {
  let diff = a.length ^ b.length;
  for (let i = 0; i < Math.max(a.length, b.length); i++) {
    diff |= (a.charCodeAt(i % (a.length || 1)) || 0) ^ (b.charCodeAt(i % (b.length || 1)) || 0);
  }
  return diff === 0 && a.length > 0;
}
