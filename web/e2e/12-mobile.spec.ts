import type { Page } from "@playwright/test";
import { ask, conversations, deleteExcept, settled } from "./helpers/chat";
import { SEDEMAC } from "./helpers/data";
import { test, expect, authFile } from "./fixtures";

// The mobile subset (iPhone-sized, 390x844): run with `--project=mobile`. Admin has no chat history that other specs touch.
test.use({ storageState: authFile("admin") });

let before = new Set<string>();
test.beforeAll(async ({ playwright, baseURL }) => {
  const ctx = await playwright.request.newContext({ baseURL, storageState: authFile("admin") });
  before = new Set((await conversations(ctx)).map((c) => c.id));
  await ctx.dispose();
});
test.afterAll(async ({ playwright, baseURL }) => {
  const ctx = await playwright.request.newContext({ baseURL, storageState: authFile("admin") });
  await deleteExcept(ctx, before);
  await ctx.dispose();
});

/** True when the page scrolls sideways: something is wider than the screen. */
async function overflows(page: Page) {
  return page.evaluate(() => ({ scroll: document.documentElement.scrollWidth, client: document.documentElement.clientWidth, body: document.body.scrollWidth }));
}
async function expectNoHorizontalOverflow(page: Page, where: string) {
  await expect
    .poll(async () => {
      const w = await overflows(page);
      return Math.max(w.scroll, w.body) - w.client;
    }, { message: `horizontal overflow on ${where}` })
    .toBeLessThanOrEqual(1);
}

test.describe("mobile", () => {
  test("home: greeting, prompt, chips and briefing fit the screen @mobile", async ({ page }) => {
    await page.goto("/");
    await expect(page.getByRole("heading", { level: 1 })).toContainText(/Good (morning|afternoon|evening), Asha\./);
    await expect(page.locator("#prompt")).toBeVisible();
    await expect(page.getByLabel("Suggestions").getByRole("button", { name: "Who came into money this week?" })).toBeVisible();
    await expect(page.getByText("Today’s briefing")).toBeVisible();
    expect(page.viewportSize()!.width).toBe(390);
    await expectNoHorizontalOverflow(page, "home");
    // the desktop rail is hidden; the menu button is there
    await expect(page.getByRole("button", { name: "Open navigation" })).toBeVisible();
  });

  test("the navigation drawer opens, lists the role's pages, navigates and closes @mobile", async ({ page }) => {
    await page.goto("/");
    await page.getByRole("button", { name: "Open navigation" }).click();
    const drawer = page.getByRole("dialog");
    await expect(drawer).toBeVisible();
    for (const label of ["New chat", "Today", "Events", "Calendar", "Network", "History", "Team", "Review", "Trust & Ops", "Pipeline console"]) {
      await expect(drawer.getByText(label, { exact: true }).first()).toBeVisible();
    }
    await drawer.getByRole("link", { name: "Today", exact: true }).click();
    await expect(page).toHaveURL(/\/today$/);
    await expect(drawer).toBeHidden();
    await expect(page.getByRole("heading", { level: 1, name: "Today" })).toBeVisible();
  });

  test("chat answer: a lookup renders its card without sideways scrolling @mobile", async ({ page }) => {
    await page.goto("/");
    await ask(page, "What money does Manish Sharma have?");
    await settled(page);
    await expect(page.locator("main")).toContainText("SEDEMAC");
    await expect(page.getByRole("link", { name: /Open the full call card/ })).toBeVisible();
    await expect(page.getByLabel("Talking about").first()).toBeVisible();
    await expectNoHorizontalOverflow(page, "a chat answer");
    // the steps are readable and collapsible
    const steps = page.getByRole("button", { name: /\d+ steps? ·/ });
    await expect(steps).toBeVisible();
    await steps.click();
    await expectNoHorizontalOverflow(page, "the open step list");
  });

  test("Today: tabs, filters and rows fit, and a row opens the person @mobile", async ({ page }) => {
    await page.goto("/today");
    await expect(page.getByRole("heading", { level: 1, name: "Today" })).toBeVisible();
    await expect(page.locator("section[aria-labelledby^='tier-'] ol > li").first()).toBeVisible();
    await page.getByPlaceholder("Search name, company or household").fill("Manish Sharma");
    await page.locator("section[aria-labelledby^='tier-'] ol > li").getByRole("link", { name: "Manish Sharma", exact: true }).first().click();
    await expect(page).toHaveURL(/\/people\/sedemac_ipo\/p_manish_sharma/);
  });

  test("person: the call card, working and evidence viewer fit the screen @mobile", async ({ page }) => {
    await page.goto(`/people/${SEDEMAC.event}/${SEDEMAC.person}`);
    await expect(page.getByRole("region", { name: "Call card" }).getByRole("heading", { level: 1, name: SEDEMAC.name })).toBeVisible();
    await expect(page.getByRole("region", { name: "Call card" })).toContainText("₹");
    await expectNoHorizontalOverflow(page, "the call card");
    await page.getByRole("button", { name: /Prospectus · p\./ }).first().click();
    const dialog = page.getByRole("dialog");
    await expect(dialog.getByRole("img", { name: /Source page containing/ })).toBeVisible({ timeout: 40_000 });
    const box = await dialog.boundingBox();
    expect(box!.width).toBeLessThanOrEqual(390);
    await expectNoHorizontalOverflow(page, "the evidence viewer");
    await page.keyboard.press("Escape");
    await page.getByRole("tab", { name: "How we found them" }).click();
    await expect(page.getByRole("heading", { name: `How we found ${SEDEMAC.name}` })).toBeVisible();
    await expectNoHorizontalOverflow(page, "the trail");
  });

  // One test per page so a single wide element names the page that has it.
  for (const path of ["/", "/today", "/events", "/calendar", "/network", "/history", "/team", "/review", "/sources", "/ops", "/ops/accuracy", "/ops/health", "/admin/pipeline"]) {
    test(`no horizontal overflow on ${path} @mobile`, async ({ page }) => {
      await page.goto(path);
      await expect(page.getByRole("main")).toBeVisible();
      await page.waitForLoadState("networkidle");
      await expectNoHorizontalOverflow(page, path);
    });
  }
});
