import { NextRequest } from "next/server";
import { getLLM, CHAT_MODEL } from "@/lib/llm";
import { pgrst } from "@/lib/rest";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";
export const maxDuration = 300;

type Msg = { role: "user" | "assistant" | "system"; content: string };

const SYSTEM = `너는 키네틱 아트(움직이는 예술) 창작을 돕는 큐레이터이자 디자인 어시스턴트다.
사용자가 만들고 싶은 새 키네틱 아트의 컨셉을 대화로 구체화하도록 돕는다: 움직임 방식(모터/바람/자기/손), 재료, 형태, 규모, 빛/색, 분위기.
아래 '참조 작품'과 '갤러리 관련 작품'을 활용해 구체적인 아이디어와 방향을 제안하라.
한국어로 간결하게(3~5문장) 답하고, 되물으며 컨셉을 좁혀라.
컨셉이 충분히 구체화되면 "오른쪽 아래 [생성] 버튼으로 이미지를 만들어 볼 수 있어요"라고 안내하라.`;

// RAG: 참조 작품 + 키워드로 검색한 관련 작품 메타를 시스템 컨텍스트로 주입
async function buildContext(referenceIds: string[], lastUser: string): Promise<string> {
  const parts: string[] = [];

  if (referenceIds.length) {
    const inList = referenceIds.map((id) => `"${id}"`).join(",");
    const res = await pgrst(
      `/kinetic_artworks?id=in.(${inList})&select=title,artist,created_year,materials,description,tags`,
    );
    if (res.ok) {
      const rows = await res.json();
      if (rows.length) {
        parts.push("[참조 작품]");
        for (const r of rows) {
          parts.push(
            `- ${r.title} / ${r.artist ?? "미상"}${r.created_year ? ` (${r.created_year})` : ""}: ${r.description ?? ""} [재료:${r.materials ?? "?"}] [태그:${(r.tags || []).join(",")}]`,
          );
        }
      }
    }
  }

  const kw = lastUser.replace(/[,().*]/g, " ").trim().slice(0, 40);
  if (kw) {
    const like = `*${kw}*`;
    const res = await pgrst(
      `/kinetic_artworks?or=(title.ilike.${like},description.ilike.${like})&select=title,artist,tags&limit=3`,
    );
    if (res.ok) {
      const rows = await res.json();
      if (rows.length) {
        parts.push("\n[갤러리 관련 작품]");
        for (const r of rows)
          parts.push(`- ${r.title} / ${r.artist ?? "미상"} [태그:${(r.tags || []).join(",")}]`);
      }
    }
  }
  return parts.join("\n");
}

export async function POST(req: NextRequest) {
  const { messages, referenceIds } = (await req.json()) as {
    messages: Msg[];
    referenceIds?: string[];
  };
  const lastUser = [...messages].reverse().find((m) => m.role === "user")?.content ?? "";
  const context = await buildContext(referenceIds ?? [], lastUser);
  const sys: Msg = {
    role: "system",
    content: context ? `${SYSTEM}\n\n${context}` : SYSTEM,
  };

  const llm = getLLM();
  const encoder = new TextEncoder();

  const stream = new ReadableStream({
    async start(controller) {
      const send = (obj: unknown) =>
        controller.enqueue(encoder.encode(`data: ${JSON.stringify(obj)}\n\n`));
      try {
        const completion = await llm.chat.completions.create(
          { model: CHAT_MODEL, messages: [sys, ...messages], stream: true },
          { signal: req.signal },
        );
        for await (const chunk of completion) {
          const t = chunk.choices[0]?.delta?.content;
          if (t) send({ text: t });
        }
        send({ done: true });
      } catch (e) {
        send({ error: e instanceof Error ? e.message : "error" });
      } finally {
        controller.close();
      }
    },
  });

  return new Response(stream, {
    headers: {
      "Content-Type": "text/event-stream; charset=utf-8",
      "Cache-Control": "no-cache",
      Connection: "keep-alive",
    },
  });
}
