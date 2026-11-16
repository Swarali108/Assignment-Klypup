import { expect as baseExpect } from "@playwright/test";
import { getJson, send } from "./helpers/api";
import { SEDEMAC } from "./helpers/data";
import { test, expect, authFile } from "./fixtures";

const URL = `/people/${SEDEMAC.event}/${SEDEMAC.person}`;
const API = `/api/people/${SEDEMAC.event}/${SEDEMAC.person}`;
const RM = `/api/rm/${SEDEMAC.event}/${SEDEMAC.person}`;
const NOTE_BOX = "What was discussed, what they asked for, next step";

type Card = {
  amount: { value_cr: number; display: string; detail: string };
  timing: { label: string };
  confidence: { level: string; reasons?: string[] };
  brief: { lines: string[] };
  amounts: { key: string; label: string; short: string; working: string }[];
  name_evidence: { image_url: string; cached: boolean }[];
};

test.use({ storageState: authFile("rm") });

test.describe("person page: the call card", () => {
  test("numbers on the card are the numbers the API returns", async ({ page, request }) => {
    const card = await getJson<Card>(request, API);
    await page.goto(URL);
    const view = page.getByRole("region", { name: "Call card" });
    await expect(view.getByRole("heading", { level: 1, name: SEDEMAC.name })).toBeVisible();
    await expect(view).toContainText(SEDEMAC.company);
    await expect(view).toContainText(card.amount.value_cr.toFixed(2));
    await expect(view).toContainText(card.amount.detail);
    await expect(view).toContainText(card.timing.label);
    for (const reason of card.confidence.reasons ?? []) await expect(view).toContainText(reason);
    // every figure under "How the amounts add up" shows the API's working, verbatim
    for (const a of card.amounts) {
      await expect(page.getByText(a.working, { exact: false }).first()).toBeVisible();
      await expect(page.getByText(a.short, { exact: false }).first()).toBeVisible();
    }
    for (const line of card.brief.lines) await expect(page.getByText(line.slice(0, 60), { exact: false }).first()).toBeVisible();
  });

  test("an evidence chip opens the filing page as an image with the quote highlighted", async ({ page, request }) => {
    const card = await getJson<Card>(request, API);
    expect(card.name_evidence[0].cached, "the demo machine has the filing cached").toBe(true);
    await page.goto(URL);
    await page.getByRole("button", { name: /Prospectus · p\./ }).first().click();
    const dialog = page.getByRole("dialog");
    await expect(dialog).toBeVisible();
    await expect(dialog.getByText("Quoted from the filing")).toBeVisible();
    const img = dialog.getByRole("img", { name: /Source page containing/ });
    await expect(img).toBeVisible({ timeout: 40_000 });
    await expect.poll(() => img.evaluate((el: HTMLImageElement) => el.complete && el.naturalWidth > 100), { timeout: 20_000 }).toBe(true);
    await expect(dialog.getByText(/Quote highlighted on the page|could not be marked/)).toBeVisible();
    await expect(dialog.getByRole("link", { name: /Open PDF at page \d+/ })).toHaveAttribute("href", /\/api\/docs\/[0-9a-f]+\.pdf#page=\d+/);
    await page.keyboard.press("Escape");
    await expect(dialog).toBeHidden();
  });

  test("the evidence page endpoint answers with a PNG and says whether the quote was found", async ({ request }) => {
    const card = await getJson<Card>(request, API);
    const res = await request.get(card.name_evidence[0].image_url);
    expect(res.status()).toBe(200);
    expect(res.headers()["content-type"]).toBe("image/png");
    expect(["found", "none"]).toContain(res.headers()["x-highlight"]);
  });

  test("“How we found them” lists every pipeline step and opens the evidence behind each", async ({ page, request }) => {
    const trail = await getJson<{ steps: { key: string; title: string }[] }>(request, `${API}/trail`);
    await page.goto(URL);
    await page.getByRole("tab", { name: "How we found them" }).click();
    await expect(page.getByRole("heading", { name: `How we found ${SEDEMAC.name}` })).toBeVisible();
    const steps = page.locator("button[aria-controls^='trail-']");
    await expect(steps).toHaveCount(trail.steps.length);
    for (const [i, s] of trail.steps.entries()) {
      await expect(steps.nth(i)).toContainText(`Step ${i + 1}`);
      await expect(steps.nth(i)).toContainText(s.title);
    }
    await page.getByRole("button", { name: "Expand all" }).click();
    await expect(page.getByRole("button", { name: "Collapse all" })).toBeVisible();
    await expect(page.locator("#trail-money")).toBeVisible();
    await expect(page.locator("#trail-rank")).toBeVisible();
    await page.goto(`${URL}?tab=trail`); // deep link
    await expect(page.getByRole("heading", { name: `How we found ${SEDEMAC.name}` })).toBeVisible();
  });

  test("public profile and web mentions show a result or say honestly that nothing was looked up", async ({ page }) => {
    await page.goto(URL);
    await expect(page.getByRole("heading", { name: "Public information" })).toBeVisible();
    await expect(page.getByRole("heading", { name: "Public profile", exact: true })).toBeVisible();
    await expect(page.getByRole("heading", { name: "Mentions on the web", exact: true })).toBeVisible();
    await expect(page.getByText(/has not been looked up for this person yet|No public profile with this name was found|from web search, not verified/i).first()).toBeVisible();
    // a lookup is a paid step: the buttons exist, this suite never presses them (the cap is 15 requests)
    await expect(page.getByRole("button", { name: "Look up public profile" })).toBeVisible();
    await expect(page.getByRole("button", { name: "Search the web" })).toBeVisible();
  });

  test("the RM's client book marks this person “In your book”; an admin's page does not", async ({ page, browser, baseURL }) => {
    await page.goto(URL);
    await expect(page.getByRole("region", { name: "Call card" })).toContainText("In your book");
    const ctx = await browser.newContext({ baseURL, storageState: authFile("admin") });
    const admin = await ctx.newPage();
    // this second page does not get the suite's fixture, so the daily-brief sheet is dismissed here
    await admin.addLocatorHandler(admin.getByRole("dialog").filter({ hasText: /your brief for/i }), async () => {
      await admin.keyboard.press("Escape");
    });
    await admin.goto(URL);
    await expect(admin.getByRole("region", { name: "Call card" })).toBeVisible();
    await expect(admin.getByRole("region", { name: "Call card" })).not.toContainText("In your book");
    await ctx.close();
  });

  test("the call pack menu offers PDF and Markdown", async ({ page }) => {
    await page.goto(URL);
    await page.getByRole("button", { name: /Call pack/ }).click();
    await expect(page.getByRole("menuitem", { name: /PDF/ })).toHaveAttribute("href", /\/print/);
    const [download] = await Promise.all([page.waitForEvent("download"), page.getByRole("menuitem", { name: /Markdown/ }).click()]);
    expect(download.suggestedFilename()).toMatch(/\.md$/);
  });
});

test.describe("person page: the call log and watching", () => {
  test("a logged call and note persist across a reload, then are reset", async ({ page, request }) => {
    const note = `e2e note ${Date.now()}`;
    try {
      await page.goto(URL);
      await page.getByRole("link", { name: "Log the call" }).click();
      await page.getByRole("radiogroup", { name: "Call status" }).getByRole("radio", { name: "Called" }).click();
      await expect(page.getByText("Marked “Called”")).toBeVisible();
      await page.getByPlaceholder(NOTE_BOX).fill(note);
      await page.getByRole("button", { name: "Save note" }).click();
      await expect(page.getByText("Note saved")).toBeVisible();

      await page.reload();
      await expect(page.getByRole("radiogroup", { name: "Call status" }).getByRole("radio", { name: "Called" })).toHaveAttribute("aria-checked", "true");
      await expect(page.getByPlaceholder(NOTE_BOX)).toHaveValue(note);
      expect(await getJson(request, RM)).toMatchObject({ status: "called", note });
    } finally {
      await send(request, "PUT", RM, { status: "to_call", note: "", follow_up_date: "" });
    }
    const after = await getJson<{ status: string; note: string }>(request, RM);
    expect(after.status).toBe("to_call");
    expect(after.note).toBe("");
    await page.reload();
    await expect(page.getByRole("radiogroup", { name: "Call status" }).getByRole("radio", { name: "To call" })).toHaveAttribute("aria-checked", "true");
  });

  test("marking “won” asks for the amount first and saves nothing until it is given", async ({ page, request }) => {
    try {
      await page.goto(URL);
      const status = page.getByRole("radiogroup", { name: "Call status" });
      await status.getByRole("radio", { name: "Won" }).click();
      await expect(page.getByText(/New money in, as you entered it/)).toBeVisible();
      await expect(page.getByRole("button", { name: "Mark as won" })).toBeDisabled();
      expect((await getJson<{ status: string }>(request, RM)).status).toBe("to_call");
    } finally {
      await send(request, "PUT", RM, { status: "to_call", note: "", follow_up_date: "" });
    }
  });

  test("following and unfollowing a person updates the button and the alerts bell", async ({ page, request }) => {
    await page.goto(URL);
    const follow = page.getByRole("button", { name: /^(Follow|Following)$/ }).first();
    try {
      if ((await follow.getAttribute("aria-pressed")) === "true") await follow.click();
      await expect(follow).toHaveAttribute("aria-pressed", "false");
      await follow.click();
      await expect(follow).toHaveAttribute("aria-pressed", "true");
      await expect(follow).toContainText("Following");
      const list = await getJson<{ follows: { kind: string; label: string }[] }>(request, "/api/watch");
      expect(list.follows.some((f) => f.kind === "person" && /Manish Sharma/i.test(f.label))).toBe(true);
      await page.getByRole("button", { name: /^Alerts/ }).click();
      await expect(page.getByRole("heading", { name: "Alerts" })).toBeVisible();
      await page.keyboard.press("Escape");
    } finally {
      if ((await follow.getAttribute("aria-pressed")) === "true") await follow.click();
    }
    await expect(follow).toHaveAttribute("aria-pressed", "false");
    await baseExpect
      .poll(async () => (await getJson<{ follows: { label: string }[] }>(request, "/api/watch")).follows.filter((f) => /Manish Sharma/i.test(f.label)).length)
      .toBe(0);
  });

  test("following the company works the same way", async ({ page, request }) => {
    await page.goto(URL);
    const follow = page.getByRole("button", { name: /^(Follow company|Following)$/ }).last();
    try {
      await follow.click();
      await expect(follow).toHaveAttribute("aria-pressed", "true");
      const list = await getJson<{ follows: { kind: string }[] }>(request, "/api/watch");
      expect(list.follows.some((f) => f.kind === "company")).toBe(true);
    } finally {
      if ((await follow.getAttribute("aria-pressed")) === "true") await follow.click();
    }
    await expect(follow).toHaveAttribute("aria-pressed", "false");
  });

  test("a person who is not on any call list says so plainly", async ({ page, guard }) => {
    guard.allow(404);
    await page.goto("/people/sedemac_ipo/p_nobody_at_all");
    await expect(page.getByText(/not on any call list|could not be loaded/i).first()).toBeVisible();
  });
});

test.describe("person page as a viewer", () => {
  test.use({ storageState: authFile("viewer") });

  test("shows the card but no call log", async ({ page, guard }) => {
    guard.allow(403, /\/api\/team\/rms/); // the assignment control asks for the RM list; a viewer is refused, quietly
    await page.goto(URL);
    await expect(page.getByRole("region", { name: "Call card" })).toBeVisible();
    await expect(page.getByRole("link", { name: "Log the call" })).toHaveCount(0);
    await expect(page.getByRole("radiogroup", { name: "Call status" })).toHaveCount(0);
  });
});
