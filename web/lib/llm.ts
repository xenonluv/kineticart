// LLM provider 격리 — Gemini(OpenAI 호환 엔드포인트)로 스트리밍 대화.
// 나중에 다른 provider로 교체하려면 이 파일만 바꾸면 됨.
import OpenAI from "openai";

// gemini-flash-latest = 최신 Flash 별칭(무료 티어). 특정 버전 고정은 CHAT_MODEL env로.
export const CHAT_MODEL = process.env.CHAT_MODEL || "gemini-flash-latest";

export function getLLM(): OpenAI {
  return new OpenAI({
    apiKey: process.env.GOOGLE_API_KEY ?? "",
    baseURL: "https://generativelanguage.googleapis.com/v1beta/openai/",
  });
}
