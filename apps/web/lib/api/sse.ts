import { readCookie, refreshSession } from "@/lib/api/client";

export interface SseEvent {
  event: string;
  data: Record<string, unknown>;
}

function parseBlock(block: string): SseEvent | null {
  let event = "message";
  const data: string[] = [];
  for (const line of block.split("\n")) {
    if (line.startsWith("event:")) event = line.slice(6).trim();
    else if (line.startsWith("data:")) data.push(line.slice(5).trimStart());
  }
  if (!data.length) return null;
  try {
    return { event, data: JSON.parse(data.join("\n")) as Record<string, unknown> };
  } catch {
    return { event, data: { raw: data.join("\n") } };
  }
}

/** POST a JSON body and consume the text/event-stream response. */
export async function streamSse(
  url: string,
  body: unknown,
  onEvent: (ev: SseEvent) => void,
  signal?: AbortSignal,
): Promise<void> {
  const send = () =>
    fetch(url, {
      method: "POST",
      credentials: "include",
      headers: {
        "content-type": "application/json",
        accept: "text/event-stream",
        "x-csrf-token": decodeURIComponent(readCookie("twinpm_csrf") ?? ""),
      },
      body: JSON.stringify(body),
      signal,
    });
  let res = await send();
  if (res.status === 401 && (await refreshSession())) res = await send();
  if (!res.ok || !res.body) {
    let message = `Request failed (${res.status})`;
    try {
      const env = (await res.json()) as { error?: { message?: string } };
      message = env.error?.message ?? message;
    } catch {
      /* not JSON */
    }
    onEvent({ event: "error", data: { message } });
    return;
  }
  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true }).replace(/\r\n/g, "\n");
    let idx;
    while ((idx = buffer.indexOf("\n\n")) >= 0) {
      const ev = parseBlock(buffer.slice(0, idx));
      buffer = buffer.slice(idx + 2);
      if (ev && ev.event !== "ping") onEvent(ev);
    }
  }
}
