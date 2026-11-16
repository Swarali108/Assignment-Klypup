import { expect, type APIRequestContext, type Page } from "@playwright/test";

/** Type a question in the prompt box and send it with Enter. */
export async function ask(page: Page, text: string) {
  const box = page.locator("#prompt");
  await expect(box).toBeEnabled();
  await box.fill(text);
  await box.press("Enter");
}

/** The turn is over when the Stop button is gone and the composer can send again. */
export async function settled(page: Page, timeout = 45_000) {
  await expect(page.getByRole("button", { name: "Stop answering" })).toBeHidden({ timeout });
}

export type Conversation = { id: string; title: string; updated_at: string };

export async function conversations(request: APIRequestContext): Promise<Conversation[]> {
  const res = await request.get("/api/chat/conversations");
  expect(res.ok()).toBeTruthy();
  return (await res.json()) as Conversation[];
}

/** Newest conversation with exactly this title. */
export async function conversationByTitle(request: APIRequestContext, title: string): Promise<Conversation> {
  let found: Conversation | undefined;
  await expect
    .poll(async () => (found = (await conversations(request)).find((c) => c.title === title)), { message: `conversation “${title}” in the list` })
    .toBeTruthy();
  return found!;
}

export async function deleteConversations(request: APIRequestContext, ids: string[]) {
  for (const id of ids) await request.delete(`/api/chat/conversations/${id}`, { data: {}, headers: { "content-type": "application/json" } });
}

/** Delete every conversation of this user that is not in `keep` (the ones that existed before the test). */
export async function deleteExcept(request: APIRequestContext, keep: Set<string>) {
  const now = await conversations(request);
  await deleteConversations(request, now.filter((c) => !keep.has(c.id)).map((c) => c.id));
}
