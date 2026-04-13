import type { SSEEvent } from "./types";

/**
 * Stream chat responses from the backend via POST-based SSE.
 *
 * Uses fetch + ReadableStream because the endpoint is POST (not GET),
 * which rules out the native EventSource API.
 */
export async function* streamChat(
  apiBaseUrl: string,
  token: string,
  prompt: string,
  signal?: AbortSignal,
  brand?: string,
  threadId?: string | null,
  parentMessageId?: number | null,
): AsyncGenerator<SSEEvent> {
  const body: Record<string, unknown> = { prompt };
  if (brand) body.brand = brand;
  if (threadId) {
    body.thread_id = threadId;
    body.parent_message_id = parentMessageId ?? 0;
  }

  const response = await fetch(`${apiBaseUrl}/chat`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${token}`,
    },
    body: JSON.stringify(body),
    signal,
  });

  if (!response.ok) {
    const errBody = await response.text().catch(() => "Unknown error");
    yield { event: "error", data: `HTTP ${response.status}: ${errBody}` };
    return;
  }

  const reader = response.body?.getReader();
  if (!reader) {
    yield { event: "error", data: "No response stream available" };
    return;
  }

  const decoder = new TextDecoder();
  let buffer = "";

  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      const parts = buffer.split("\n\n");
      buffer = parts.pop() || "";

      for (const part of parts) {
        const parsed = parseChunk(part);
        if (parsed) yield parsed;
      }
    }

    if (buffer.trim()) {
      const parsed = parseChunk(buffer);
      if (parsed) yield parsed;
    }
  } finally {
    reader.releaseLock();
  }
}

function parseChunk(chunk: string): SSEEvent | null {
  let event = "";
  let data = "";

  for (const line of chunk.split("\n")) {
    if (line.startsWith("event: ")) {
      event = line.slice(7);
    } else if (line.startsWith("data: ")) {
      data += (data ? "\n" : "") + line.slice(6);
    }
  }

  if (!event && !data) return null;
  return { event: event as SSEEvent["event"], data };
}
