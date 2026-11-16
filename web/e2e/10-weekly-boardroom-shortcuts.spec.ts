import { ask, conversations, deleteExcept, settled } from "./helpers/chat";
import { test, expect, authFile } from "./fixtures";

// These features arrived together (weekly short list, boardroom mode, shortcuts, home date line); /api/me/since is their marker.
test.use({ storageState: authFile("head") });

let before = new Set<string>();
test.beforeAll(async ({ playwright, baseURL }) => {
  const ctx = await playwright.request.newContext({ baseURL, storageState: authFile("head") });
  before = new Set((await conversations(ctx)).map((c) => c.id));
  await ctx.dispose();
});
test.afterAll(async ({ playwright, baseURL }) => {
  const ctx = await playwright.request.newContext({ baseURL, storageState: authFile("head") });
  await deleteExcept(ctx, before);
  await ctx.dispose();
});
test.beforeEach(async ({ request }) => {
  test.skip((await request.get("/api/me/since")).status() === 404, "this build has no weekly list / boardroom mode / shortcuts");
});

test.describe("weekly short list (PDF)", () => {
  test("is an A4 page with the top 15 people, each with amount, timing, confidence and why now", async ({ page }) => {
    await page.goto("/weekly");
    await expect(page.getByRole("heading", { level: 1, name: "Weekly short list: who just came into money" })).toBeVisible();
    await expect(page.getByText(/Week of .* to .* · \d+ people · Prepared for Meera Joshi, Head of RMs/)).toBeVisible();
    const head = page.getByRole("columnheader");
    await expect(head).toHaveText(["#", "Person", "Roughly how much", "When", "How sure", "Why call now"]);
    const rows = page.locator("tbody tr");
    const n = await rows.count();
    expect(n).toBeGreaterThan(0);
    expect(n).toBeLessThanOrEqual(15);
    await expect(rows.first()).toContainText("₹");
    await expect(page.getByRole("button", { name: /Print or save as PDF/ })).toBeEnabled();
    await expect(page.getByRole("navigation", { name: "Main" })).toHaveCount(0); // no app chrome on paper
    await expect(page.getByText(/Every number in this document was checked/)).toBeVisible();
  });

  test("when no one is dated this week, it says the nearest dates were added", async ({ page }) => {
    await page.goto("/weekly");
    await expect(page.locator("tbody tr").first()).toBeVisible();
    const notice = page.getByText(/Fewer than 15 people have money dated this week, so the nearest dates are added/);
    // either the week has 15 people, or the page says so honestly
    const rows = await page.locator("tbody tr").count();
    if (rows === 15 && !(await notice.count())) return;
    await expect(notice).toBeVisible();
  });

  test("the Today and home links open it and ask the browser to print once it is ready", async ({ page }) => {
    await page.addInitScript(() => {
      (window as unknown as { __printed: number }).__printed = 0;
      window.print = () => void ((window as unknown as { __printed: number }).__printed += 1);
    });
    await page.goto("/today");
    await page.getByRole("link", { name: /Download weekly short list \(PDF\)/ }).click();
    await expect(page).toHaveURL(/\/weekly\?print=1/);
    await expect(page.locator("tbody tr").first()).toBeVisible();
    await expect.poll(() => page.evaluate(() => (window as unknown as { __printed: number }).__printed)).toBe(1);
    await page.goto("/");
    await expect(page.getByRole("link", { name: /Weekly short list \(PDF\)/ })).toHaveAttribute("href", "/weekly?print=1");
  });
});

test.describe("boardroom mode", () => {
  test("the B key and the account menu hide costs, model names and technical chips; it is remembered", async ({ page }) => {
    await page.goto("/");
    const picker = page.getByRole("button", { name: "Choose the model for this conversation" });
    await expect(picker).toBeVisible();
    await expect(page.locator("html")).not.toHaveAttribute("data-boardroom", /.*/);

    await page.keyboard.press("b");
    await expect(page.locator("html")).toHaveAttribute("data-boardroom", "");
    await expect(picker).toBeHidden();
    await expect(page.getByRole("button", { name: "Compare", exact: true })).toBeHidden();
    expect(await page.evaluate(() => window.localStorage.getItem("aurelia.boardroom"))).toBe("1");

    // an answer shows no cost footer, model badges or timings
    await ask(page, "Who came into money this week?");
    await settled(page);
    await expect(page.getByRole("button", { name: /No model|models?\b.*·/ })).toBeHidden();
    await expect(page.locator("[data-tech]").first()).toBeHidden();

    // remembered across a reload, and switched off from the account menu
    await page.reload();
    await expect(page.locator("html")).toHaveAttribute("data-boardroom", "");
    await page.getByRole("button", { name: /Account menu for/ }).click();
    await expect(page.getByRole("menuitem", { name: /Boardroom mode/ })).toContainText("On");
    await page.getByRole("menuitem", { name: /Boardroom mode/ }).click();
    await expect(page.locator("html")).not.toHaveAttribute("data-boardroom", /.*/);
    await expect(page.getByRole("button", { name: "Choose the model for this conversation" })).toBeVisible();
    expect(await page.evaluate(() => window.localStorage.getItem("aurelia.boardroom"))).toBe("0");
  });

  test("hides the freshness chips on a call card too, and the larger type returns to normal when off", async ({ page }) => {
    await page.goto("/people/sedemac_ipo/p_manish_sharma");
    await expect(page.getByRole("region", { name: "Call card" })).toBeVisible();
    const size = () => page.evaluate(() => getComputedStyle(document.documentElement).fontSize);
    const normal = await size();
    await page.keyboard.press("b");
    await expect.poll(size).not.toBe(normal);
    await page.keyboard.press("b");
    await expect.poll(size).toBe(normal);
  });
});

test.describe("keyboard shortcuts", () => {
  test("? opens the overlay listing every shortcut; Escape closes it", async ({ page }) => {
    await page.goto("/today");
    await page.keyboard.press("?");
    const dialog = page.getByRole("dialog", { name: "Keyboard shortcuts" });
    await expect(dialog).toBeVisible();
    for (const row of ["Search people, or ask a question", "Go to Today", "Go to Events", "Go to History", "Boardroom mode on or off", "Show this list"]) {
      await expect(dialog).toContainText(row);
    }
    await expect(dialog.locator("kbd")).toContainText(["⌘", "K", "g", "t", "g", "e", "g", "h", "b", "?"]);
    await page.keyboard.press("Escape");
    await expect(dialog).toBeHidden();
  });

  test("g then t / e / h jump to Today, Events and History", async ({ page }) => {
    await page.goto("/calendar");
    await page.keyboard.press("g");
    await page.keyboard.press("e");
    await expect(page).toHaveURL(/\/events$/);
    await page.keyboard.press("g");
    await page.keyboard.press("h");
    await expect(page).toHaveURL(/\/history$/);
    await page.keyboard.press("g");
    await page.keyboard.press("t");
    await expect(page).toHaveURL(/\/today$/);
  });

  test("the shortcuts are ignored while typing", async ({ page }) => {
    await page.goto("/");
    await page.locator("#prompt").click();
    await page.keyboard.type("b? g t");
    await expect(page.locator("#prompt")).toHaveValue("b? g t");
    await expect(page.locator("html")).not.toHaveAttribute("data-boardroom", /.*/);
    await expect(page).toHaveURL(/\/$/);
    await expect(page.getByRole("dialog", { name: "Keyboard shortcuts" })).toHaveCount(0);
  });

  test("the account menu lists the shortcuts too", async ({ page }) => {
    await page.goto("/today");
    await page.getByRole("button", { name: /Account menu for/ }).click();
    await page.getByRole("menuitem", { name: /Keyboard shortcuts/ }).click();
    await expect(page.getByRole("dialog", { name: "Keyboard shortcuts" })).toBeVisible();
  });
});

test.describe("home date line", () => {
  test("shows the day, the market status and what is new since the last visit", async ({ page, request }) => {
    const since = await (await request.get("/api/me/since")).json();
    await page.goto("/");
    await expect(page.getByText(/(Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday), \d+ \w+/)).toBeVisible();
    await expect(page.getByText(/\(regular hours\)/)).toBeVisible();
    await expect(page.getByText(/Markets? (open|closed)|opens|closes/i).first()).toBeVisible();
    const chip = page.getByRole("link", { name: /Since your last visit|In the last 7 days/ });
    await expect(chip).toHaveAttribute("href", "/events");
    await expect(chip).toContainText(since.new_events + since.new_people > 0 ? /new event/ : /nothing new/);
  });
});
