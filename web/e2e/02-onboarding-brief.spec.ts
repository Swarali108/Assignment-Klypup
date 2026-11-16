import type { APIRequestContext } from "@playwright/test";
import { sql, todayIst } from "./helpers/state";
import { test, expect, authFile } from "./fixtures";

// new.rm@ is the account that sees the setup guide on its first sign-in. Everything it changes (preferences, client
// book, the brief flag) is put back by global-teardown, and again here so a re-run starts from the same place.
test.use({ storageState: authFile("newrm"), keepSetupGuide: true });

async function resetNewRm(request: APIRequestContext) {
  await request.put("/api/me/preferences", { data: { onboarded: false, event_types: [], min_ticket_cr: null, alerts: "daily" } });
  await request.delete("/api/me/book", { data: {} });
  // "first sign-in of the day" again (the brief tables exist only on builds with the daily brief)
  sql(`DELETE FROM user_brief WHERE email = 'new.rm@aurelia.demo' AND day = '${todayIst()}'`, "write");
}
test.beforeAll(async ({ playwright, baseURL }) => {
  const ctx = await playwright.request.newContext({ baseURL, storageState: authFile("newrm") });
  await resetNewRm(ctx);
  await ctx.dispose();
});
test.afterAll(async ({ playwright, baseURL }) => {
  const ctx = await playwright.request.newContext({ baseURL, storageState: authFile("newrm") });
  await resetNewRm(ctx);
  await ctx.dispose();
});

const csv = (names: string[]) => ({ name: "clients.csv", mimeType: "text/csv", buffer: Buffer.from(`name\n${names.join("\n")}\n`) });

test.describe("first sign-in: the setup guide", () => {
  test("opens by itself, walks coverage → book → alerts → tour, and saves what was chosen", async ({ page, request }) => {
    await page.goto("/");
    const guide = page.getByRole("dialog").filter({ has: page.getByRole("button", { name: "Close the setup guide" }) });
    await expect(guide).toBeVisible();
    await expect(guide).toContainText("Welcome, Neha.");
    await expect(guide.getByText("1 of 4")).toBeVisible();

    // 1. coverage
    await guide.getByRole("checkbox", { name: /IPOs/ }).click();
    await expect(guide.getByRole("checkbox", { name: /IPOs/ })).toBeChecked();
    await guide.getByRole("radio", { name: "₹50 Cr" }).click();
    await expect(guide.getByText(/people on today's list fit this coverage/)).toBeVisible();
    await guide.getByRole("button", { name: "Continue" }).click();

    // 2. the client book (a CSV of names)
    await expect(guide).toContainText("Bring your book");
    await expect(guide.getByText("2 of 4")).toBeVisible();
    await guide.locator('input[type="file"]').setInputFiles(csv(["Manish Sharma", "Nobody In Particular"]));
    await expect(guide.getByText("2 names loaded")).toBeVisible();
    await expect(guide.getByRole("link", { name: /Download a sample CSV/ })).toBeVisible();
    await guide.getByRole("button", { name: "Continue" }).click();

    // 3. alerts
    await expect(guide).toContainText("How should we nudge you?");
    await guide.getByRole("radio", { name: /Monday summary/ }).click();
    await guide.getByRole("button", { name: "Continue" }).click();

    // 4. the tour
    await expect(guide).toContainText("A quick look around");
    await expect(guide.getByText("The cost check")).toBeVisible();
    await guide.getByRole("button", { name: "Start the tour" }).click();
    await expect(guide).toBeHidden();

    // the choices were saved on the account
    const prefs = await (await request.get("/api/me/preferences")).json();
    expect(prefs).toMatchObject({ onboarded: true, event_types: ["ipo"], min_ticket_cr: 50, alerts: "weekly", book_count: 2 });
  });

});

test.describe("first sign-in of the day: the daily brief sheet", () => {
  test.use({ keepBriefSheet: true });
  // The brief arrived with the daily-brief feature; /api/me/since is its marker.
  test.beforeEach(async ({ request }) => {
    test.skip((await request.get("/api/me/since")).status() === 404, "daily brief not deployed on this build");
  });

  test("opens once on the first load after setup, with bullets that link to the work and three actions", async ({ page, request }) => {
    await request.put("/api/me/preferences", { data: { onboarded: true } });
    await page.goto("/");
    const sheet = page.getByRole("dialog").filter({ hasText: /your brief for/i });
    await expect(sheet).toBeVisible({ timeout: 30_000 });
    await expect(sheet).toContainText(/Good (morning|afternoon|evening), Neha/);
    expect(await sheet.getByRole("listitem").count()).toBeGreaterThanOrEqual(1);
    await expect(sheet.getByRole("link", { name: /Start calling/ })).toHaveAttribute("href", "/today");
    await expect(sheet.getByRole("button", { name: /Copy as email/ })).toBeEnabled();
    await expect(sheet).toContainText("numbers from the filings");

    // "Ask about this" leaves the question in the prompt box, unsent
    await sheet.getByRole("button", { name: /Ask about this/ }).click();
    await expect(sheet).toBeHidden();
    await expect(page.locator("#prompt")).not.toHaveValue("");
    await expect(page.getByRole("button", { name: "Stop answering" })).toHaveCount(0);

    // shown once: a reload does not open it again, the account menu does
    await page.reload();
    await expect(page.getByRole("heading", { level: 1 })).toContainText("Neha");
    await expect(sheet).toBeHidden();
    await page.getByRole("button", { name: /Account menu for/ }).click();
    await page.getByRole("menuitem", { name: /Today’s brief/ }).click();
    await expect(sheet).toBeVisible();
    await page.keyboard.press("Escape");
    await expect(sheet).toBeHidden();
    const brief = await (await request.get(`/api/me/brief?day=${todayIst()}`)).json();
    expect(brief.shown).toBe(true);
    expect(brief.bullets.length).toBeGreaterThanOrEqual(1);
    expect(brief.bullets.length).toBeLessThanOrEqual(5);
  });
});

test.describe("after setup: tour, coverage and reopening the guide", () => {
  test("the product tour has four stops and can be left at any time", async ({ page }) => {
    await page.goto("/");
    await page.getByRole("button", { name: /Account menu for/ }).click();
    await page.getByRole("menuitem", { name: /Product tour/ }).click();
    await expect(page.getByText("Ask in plain words")).toBeVisible();
    await page.keyboard.press("ArrowRight");
    await expect(page.getByText("Today is your call list")).toBeVisible();
    await page.keyboard.press("ArrowRight");
    await expect(page.getByText("Every ₹ has a source")).toBeVisible();
    await page.keyboard.press("ArrowRight");
    await expect(page.getByText("Nothing paid runs without you")).toBeVisible();
    await page.keyboard.press("Escape");
    await expect(page.getByText("Nothing paid runs without you")).toBeHidden();
  });

  test("Today defaults to the saved coverage, with one click to show everyone, and the book marks “In your book”", async ({ page }) => {
    await page.goto("/today");
    await expect(page.getByText(/Matched to your coverage:/)).toBeVisible();
    await page.getByRole("button", { name: "Show everyone" }).click();
    await expect(page.getByText(/Matched to your coverage:/)).toHaveCount(0);
    await page.getByPlaceholder("Search name, company or household").fill("Manish Sharma");
    await expect(page.locator("section[aria-labelledby^='tier-'] ol > li").filter({ hasText: "Manish Sharma" }).first()).toContainText("In your book");
  });

  test("the guide can be reopened from the account menu with the saved answers", async ({ page }) => {
    await page.goto("/today");
    await page.getByRole("button", { name: /Account menu for/ }).click();
    await page.getByRole("menuitem", { name: /Setup guide/ }).click();
    const guide = page.getByRole("dialog").filter({ has: page.getByRole("button", { name: "Close the setup guide" }) });
    await expect(guide.getByRole("checkbox", { name: /IPOs/ })).toBeChecked();
    await expect(guide.getByRole("radio", { name: "₹50 Cr" })).toBeChecked();
    await page.getByRole("button", { name: "Close the setup guide" }).click();
    await expect(guide).toBeHidden();
  });
});

