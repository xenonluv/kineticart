// POST 가능한 SSE 리더(EventSource 대체). `data: {json}\n\n` 프레임을 파싱해 yield.
export async function* readSse<T>(res: Response): AsyncGenerator<T> {
  if (!res.body) return;
  const reader = res.body.pipeThrough(new TextDecoderStream()).getReader();
  let buf = "";
  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buf += value;
    const frames = buf.split("\n\n");
    buf = frames.pop() ?? "";
    for (const frame of frames) {
      const line = frame.split("\n").find((l) => l.startsWith("data:"));
      if (!line) continue;
      const json = line.slice(5).trim();
      if (!json) continue;
      try {
        yield JSON.parse(json) as T;
      } catch {
        /* 무시 */
      }
    }
  }
}
