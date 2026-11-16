import { expect, type APIRequestContext, type APIResponse } from "@playwright/test";

/** GET JSON and fail with the body when the call is not 2xx. */
export async function getJson<T = any>(request: APIRequestContext, url: string): Promise<T> {
  const res = await request.get(url);
  expect(res.status(), `${url} → ${res.status()} ${await res.text().then((t) => t.slice(0, 200))}`).toBe(200);
  return (await res.json()) as T;
}

/** A write with the JSON content type the API insists on. */
export async function send(request: APIRequestContext, method: "POST" | "PUT" | "DELETE", url: string, data: unknown = {}): Promise<APIResponse> {
  return request.fetch(url, { method, data, headers: { "content-type": "application/json" } });
}

/** One chat turn through the real endpoint, returning the SSE events by type (used for state set-up and checks). */
export async function chatTurn(request: APIRequestContext, body: Record<string, unknown>) {
  const res = await request.post("/api/chat", { data: { conversation_id: null, ...body } });
  expect(res.status()).toBe(200);
  const text = await res.text();
  const events: { type: string; data: any }[] = [];
  for (const block of text.split("\n\n")) {
    const type = /^event:\s*(.+)$/m.exec(block)?.[1]?.trim();
    const data = /^data:\s*(.+)$/m.exec(block)?.[1];
    if (type && data) events.push({ type, data: JSON.parse(data) });
  }
  return { events, of: (t: string) => events.filter((e) => e.type === t).map((e) => e.data) };
}
