import { chatTurn } from "./helpers/api";
import { ask, conversationByTitle, conversations, deleteExcept, settled } from "./helpers/chat";
import { VECTRAS } from "./helpers/data";
import { test, expect, authFile } from "./fixtures";

// One role for every chat test in this file; the file runs in order so the conversations it creates are its own.
test.use({ storageState: authFile("rm") });

let before = new Set<string>();
test.beforeAll(async ({ playwright, baseURL }) => {
  const ctx = await playwright.request.newContext({ baseURL, storageState: authFile("rm") });
  before = new Set((await conversations(ctx)).map((c) => c.id));
  await ctx.dispose();
});
test.afterAll(async ({ playwright, baseURL }) => {
  const ctx = await playwright.request.newContext({ baseURL, storageState: authFile("rm") });
  await deleteExcept(ctx, before);
  await ctx.dispose();
});

test.describe("control tower: home", () => {
  test("greets the RM, offers the four suggestion chips and today's briefing", async ({ page }) => {
    await page.goto("/");
    await expect(page.getByRole("heading", { level: 1 })).toContainText(/Good (morning|afternoon|evening), Rohan\./);
    for (const chip of ["Who came into money this week?", "What money does Manish Sharma have?", "Cash in hand above ₹50 Cr", "Process a new IPO from a link"]) {
      await expect(page.getByLabel("Suggestions").getByRole("button", { name: chip, exact: true })).toBeVisible();
    }
    await expect(page.getByText("Today’s briefing")).toBeVisible();
    await expect(page.getByRole("link", { name: /Full call list/ })).toBeVisible();
    await expect(page.locator("#prompt")).toBeEditable();
  });

  test("the Send button stays off until there is text", async ({ page }) => {
    await page.goto("/");
    await expect(page.getByRole("button", { name: "Send" })).toBeDisabled();
    await page.locator("#prompt").fill("hello");
    await expect(page.getByRole("button", { name: "Send" })).toBeEnabled();
  });
});

test.describe("control tower: answers", () => {
  test("“this week” answers in plain words and says so when nothing falls inside the window", async ({ page }) => {
    await page.goto("/");
    await page.getByLabel("Suggestions").getByRole("button", { name: "Who came into money this week?", exact: true }).click();
    await expect(page.getByText("Understanding your question").first()).toBeVisible();
    await settled(page);
    const outside = page.getByRole("heading", { name: /Nearest money dates, outside/ });
    if (await outside.count()) {
      await expect(page.locator("main")).toContainText(/No one came into money this week/i);
      await expect(page.locator("main")).toContainText(/outside this window|ago/i);
    } else {
      await expect(page.locator("main")).toContainText(/came into money this week/i);
    }
    // a lookup is code only: no model, no cost
    await expect(page.getByRole("button", { name: /No model/ })).toBeVisible();
  });

  test("an exact lookup answers with a call card and puts the person in focus", async ({ page }) => {
    await page.goto("/");
    await ask(page, "What money does Manish Sharma have?");
    await settled(page);
    await expect(page.locator("main")).toContainText("Manish Sharma");
    await expect(page.locator("main")).toContainText("SEDEMAC");
    await expect(page.getByRole("link", { name: /Open the full call card/ })).toBeVisible();
    await expect(page.getByLabel("Talking about").first()).toContainText("Manish Sharma");
  });

  test("the answer streams sentence by sentence and every number was checked", async ({ page }) => {
    const chat = await chatTurn(page.request, { message: "What money does Manish Sharma have?" });
    const types = chat.events.map((e) => e.type);
    expect(types[0]).toBe("meta");
    expect(types.at(-1)).toBe("done");
    expect(types).toContain("step");
    const text = chat.of("text");
    expect(text.length).toBeGreaterThanOrEqual(2);
    expect(text.at(-1).final).toBe(true);
    expect(chat.of("done")[0].verifier?.checked ?? 0).toBeGreaterThan(0);
    expect(chat.of("done")[0].total_cost_usd).toBe(0);
    const convo = chat.of("meta")[0].conversation_id as string;
    await page.request.delete(`/api/chat/conversations/${convo}`, { data: {}, headers: { "content-type": "application/json" } });
  });

  test("a vague name asks back with real people, the pick sets the focus, a script follows, and removing the chip drops it", async ({ page }) => {
    await page.goto("/");
    await ask(page, "Anand");
    await settled(page);
    await expect(page.getByText(/people match .Anand./)).toBeVisible();
    const options = page.locator("button[aria-pressed]");
    expect(await options.count()).toBeGreaterThanOrEqual(2);
    // options are people (or actions on them), never the home suggestions
    await expect(page.getByLabel("Suggestions")).toHaveCount(0);
    await options.filter({ hasText: "Anand Kamalnayan Pandit" }).first().click();
    await settled(page);
    await expect(page.getByLabel("Talking about").first()).toContainText("Anand Kamalnayan Pandit");

    // a follow-up with no name binds to the focused person; model-written script, filled by code (one paid call, about $0.004)
    await ask(page, "script for the call");
    await settled(page, 60_000);
    const script = page.getByRole("region", { name: /Call script: Anand Kamalnayan Pandit/ });
    await expect(script).toBeVisible();
    for (const heading of ["Opening", "Why now", "Three questions", "Likely objections", "Next step"]) {
      await expect(script.getByRole("heading", { name: new RegExp(heading, "i") })).toBeVisible();
    }
    await expect(script.getByRole("button", { name: /Copy all/ })).toBeVisible();

    // the context meter shows after a model turn
    const meter = page.getByRole("button", { name: /^Context .* tokens/ });
    await expect(meter).toBeVisible();
    await meter.hover();
    await expect(page.getByText("Sent to the model").first()).toBeVisible();

    await page.mouse.move(5, 5); // leave the tooltip, which would cover the chip
    await page.keyboard.press("Escape");
    await expect(page.getByRole("tooltip")).toHaveCount(0); // it closes on a short delay; wait rather than race it
    // removing the chip tells the server to forget the focus on the next turn
    await page.getByRole("button", { name: /Stop talking about Anand/ }).click();
    await expect(page.getByLabel("Talking about")).toHaveCount(0);
    const next = page.waitForRequest((r) => r.url().endsWith("/api/chat") && r.method() === "POST");
    await ask(page, "Who came into money this week?");
    expect((await next).postDataJSON().focus).toEqual([]);
    await settled(page);
  });
});

test.describe("control tower: money-spending actions need a confirm", () => {
  test("a cached event shows an itemised estimate, Confirm runs it, and the steps stream", async ({ page }) => {
    await page.goto("/");
    await ask(page, "Process Vectras IPO again");
    await settled(page);
    await expect(page.getByText("Costs money · needs your go-ahead")).toBeVisible();
    await expect(page.getByRole("heading", { name: /Vectras Enprocon Limited · IPO/ })).toBeVisible();
    await expect(page.getByRole("row", { name: /^Total/ })).toContainText("$");
    for (const step of ["Find the right pages", "Read the tables", "Match people and families"]) {
      await expect(page.getByRole("cell", { name: step })).toBeVisible();
    }
    // nothing ran yet
    await expect(page.getByText("Confirmed. Running below.")).toHaveCount(0);
    await page.getByRole("button", { name: /Confirm & run/ }).click();
    await expect(page.getByText("Confirmed. Running below.")).toBeVisible();
    await settled(page, 120_000);
    await expect(page.getByRole("alert").filter({ hasText: /./ })).toHaveCount(0);
    await expect(page.locator("main")).toContainText(VECTRAS.company);
  });

  test("cancelling an estimate spends nothing; a deep dive lists its Bright Data requests before any spend", async ({ page }) => {
    await page.goto("/");
    await ask(page, "What money does Kusum have?");
    await settled(page);
    await ask(page, "deep dive on this person");
    await settled(page);
    await expect(page.getByText("Costs money · needs your go-ahead")).toBeVisible();
    await expect(page.getByRole("heading", { name: /Deep dive: KUSUM HARISH DHARAMSHI/ })).toBeVisible();
    // public lookups are priced in requests, not dollars; this suite never confirms them (the cap is 15 requests)
    await expect(page.getByText(/LinkedIn profile search by name \(Bright Data\)/)).toBeVisible();
    await expect(page.getByText(/\d+ req\./).first()).toBeVisible();
    await page.getByRole("button", { name: "Cancel", exact: true }).click();
    await expect(page.getByText("Not run. Nothing was spent.")).toBeVisible();
    await expect(page.getByRole("button", { name: /Confirm & run/ })).toHaveCount(0);
  });
});

test.describe("control tower: models", () => {
  test("the model switcher lists the allow-list with prices and remembers the choice for the conversation", async ({ page }) => {
    await page.goto("/");
    const trigger = page.getByRole("button", { name: "Choose the model for this conversation" });
    await expect(trigger).toContainText("Default model");
    await trigger.click();
    for (const m of ["GPT-6 Luna", "GPT-6.1 Terra", "DeepSeek V4.1 Flash", "GLM 5.3 Flash", "Qwen 3.8 Flash"]) {
      await expect(page.getByRole("menuitem", { name: new RegExp(m) })).toBeVisible();
    }
    await expect(page.getByText(/per 1M tokens/).first()).toBeVisible();
    await page.getByRole("menuitem", { name: /GLM 5.3 Flash/ }).click();
    await expect(trigger).toContainText("GLM 5.3 Flash");
    await trigger.click();
    await page.getByRole("menuitem", { name: /^Default/ }).click();
    await expect(trigger).toContainText("Default model");
  });

  test("Compare runs one question on two cheap models side by side with cost and time", async ({ page }) => {
    await page.goto("/");
    await page.getByRole("button", { name: "Compare", exact: true }).click();
    const dialog = page.getByRole("dialog", { name: "Compare two models" });
    await expect(dialog).toBeVisible();
    await dialog.getByLabel("Question").fill("Who came into money this week?");
    await dialog.getByLabel("Model A").selectOption({ label: "GLM 5.3 Flash" });
    await dialog.getByLabel("Model B").selectOption({ label: "Qwen 3.8 Flash" });
    await dialog.getByRole("button", { name: "Run both" }).click();
    const sections = dialog.locator("section");
    await expect(sections).toHaveCount(2, { timeout: 60_000 });
    await expect(sections.nth(0)).toContainText("GLM 5.3 Flash");
    await expect(sections.nth(1)).toContainText("Qwen 3.8 Flash");
    for (const i of [0, 1]) await expect(sections.nth(i).locator("header")).toContainText(/\$[\d.]+ · [\d.]+ s/);
  });
});

test.describe("history, exports and print routes", () => {
  test("history lists the thread, searches it and shows its cost and context", async ({ page, request }) => {
    const convo = await conversationByTitle(request, "Process Vectras IPO again");
    await page.goto("/history");
    await expect(page.getByRole("heading", { level: 1, name: "History" })).toBeVisible();
    const search = page.getByPlaceholder("Search questions, answers and names");
    await search.fill("Vectras");
    await expect(page.getByText("Process Vectras IPO again").first()).toBeVisible();
    await search.fill("zzzz-no-such-thing-zzzz");
    await expect(page.getByText(/Nothing matches/)).toBeVisible();
    await page.getByRole("button", { name: "Clear the search" }).click();
    await page.goto(`/history/${convo.id}`);
    await expect(page.getByRole("heading", { level: 1, name: "Process Vectras IPO again" })).toBeVisible();
    await expect(page.getByRole("region", { name: "What this conversation cost" })).toBeVisible();
    await expect(page.getByLabel("What this answer cost").first()).toBeVisible();
  });

  test("export.md is a clean Markdown report and the Download menu saves it", async ({ page, request }) => {
    const convo = await conversationByTitle(request, "Process Vectras IPO again");
    const md = await request.get(`/api/chat/conversations/${convo.id}/export.md`);
    expect(md.status()).toBe(200);
    expect(md.headers()["content-type"]).toMatch(/text\/(markdown|plain)/);
    const text = await md.text();
    expect(text).toMatch(/^#/m);
    expect(text).toContain("Vectras");

    await page.goto(`/history/${convo.id}`);
    await page.getByRole("button", { name: /^Download/ }).first().click();
    const [download] = await Promise.all([page.waitForEvent("download"), page.getByRole("menuitem", { name: /Markdown/ }).click()]);
    expect(download.suggestedFilename()).toMatch(/\.md$/);
  });

  test("the conversation print route renders an A4 page without the app chrome", async ({ page, request }) => {
    const convo = await conversationByTitle(request, "Process Vectras IPO again");
    await page.goto(`/history/${convo.id}/print`);
    await expect(page.getByRole("button", { name: /Print or save as PDF/ })).toBeEnabled();
    await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
    await expect(page.getByText(/Every number in this document was checked/)).toBeVisible();
    await expect(page.getByRole("navigation", { name: "Main" })).toHaveCount(0);
  });

  test("the call-pack print route renders the card, the brief and the script", async ({ page }) => {
    await page.goto("/people/sedemac_ipo/p_manish_sharma/print");
    await expect(page.getByRole("heading", { level: 1, name: /Call pack: Manish Sharma/ })).toBeVisible();
    await expect(page.getByText(/Every number in this document was checked/)).toBeVisible();
    await expect(page.getByRole("button", { name: /Print or save as PDF/ })).toBeEnabled();
  });

  test("callpack.md carries the card, brief and evidence links", async ({ request }) => {
    const res = await request.get("/api/people/sedemac_ipo/p_manish_sharma/callpack.md");
    expect(res.status()).toBe(200);
    const text = await res.text();
    expect(text).toContain("Manish Sharma");
    expect(text).toMatch(/SEDEMAC/);
  });
});
