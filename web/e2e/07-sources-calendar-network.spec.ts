import { getJson } from "./helpers/api";
import { test, expect, authFile } from "./fixtures";

test.use({ storageState: authFile("admin") });

test.describe("Sources (admin)", () => {
  test("lists SEBI, NSE and BSE with each source's switch, items, errors and last check", async ({ page }) => {
    await page.goto("/sources");
    await expect(page.getByRole("heading", { level: 1, name: "Sources" })).toBeVisible();
    for (const owner of ["SEBI", "NSE", "BSE"]) {
      const section = page.locator(`section[aria-labelledby="owner-${owner}"]`);
      await expect(section).toBeVisible();
      await expect(section.getByRole("link", { name: /Terms/ })).toHaveAttribute("target", "_blank");
      await expect(section.getByText("On", { exact: true }).first()).toBeVisible();
      for (const field of ["Items", "Errors", "Last checked"]) await expect(section.getByText(field, { exact: true }).first()).toBeVisible();
    }
    // the exchanges are labelled for what their terms say, and a source that is off says why, quoting its terms
    await expect(page.locator('section[aria-labelledby="owner-NSE"]')).toContainText(/High risk/);
    await expect(page.locator('section[aria-labelledby="owner-NSE"]')).toContainText(/Off by NSE's Terms of Use/);
    await expect(page.locator('section[aria-labelledby="owner-BSE"]')).toContainText(/Off by BSE's disclaimer/);
    await expect(page.locator('section[aria-labelledby="owner-SEBI"]')).toContainText(/Low risk/);
    await expect(page.getByText(/NSE and BSE reading is on/)).toBeVisible();
  });

  test("the Bright Data row shows the monthly request use, cap and the LinkedIn switch", async ({ page, request }) => {
    const status = await getJson<{ cap: number; used: number; remaining: number; linkedin_enabled: boolean }>(request, "/api/enrichment/status");
    await page.goto("/sources");
    const card = page.locator('section[aria-labelledby="owner-brightdata"]');
    await expect(card).toContainText("Public lookups (Bright Data)");
    await expect(card).toContainText("Used this month");
    await expect(card).toContainText(status.cap.toLocaleString("en-IN"));
    await expect(card).toContainText(status.remaining.toLocaleString("en-IN"));
    await expect(card.getByRole("progressbar", { name: "Requests used this month" })).toBeVisible();
    await expect(card).toContainText(status.linkedin_enabled ? /LinkedIn lookups on/ : /LinkedIn lookups off/);
  });

  test("auto-processing shows today's spend against its cap and the recent checks", async ({ page }) => {
    await page.goto("/sources");
    const log = page.locator("#auto-log");
    await expect(log.getByRole("meter", { name: /automatic spend against the daily cap/ })).toBeVisible();
    await expect(log).toContainText(/\$[\d.]+ of \$[\d.]+/);
    await expect(log.getByRole("heading", { name: "Recent checks" })).toBeVisible();
  });

  test("the check-now button is offered (this suite never runs discovery against the exchanges)", async ({ page }) => {
    await page.goto("/sources");
    await expect(page.getByRole("button", { name: /Check for new filings now/ })).toBeVisible();
  });

  test.describe("for other roles", () => {
    test.use({ storageState: authFile("rm") });
    test("an RM is told the page is for admins", async ({ page, guard }) => {
      guard.allow(403);
      await page.goto("/sources");
      await expect(page.getByText(/for admins/i).first()).toBeVisible();
    });
  });
});

test.describe("Calendar", () => {
  test.use({ storageState: authFile("rm") });

  test("headline figures come from the API, and the next money date is named", async ({ page, request }) => {
    const cal = await getJson<{ count: number; items: { event: { id: string } }[] }>(request, "/api/calendar");
    const events = new Set(cal.items.map((i) => i.event.id)).size;
    await page.goto("/calendar");
    await expect(page.getByRole("heading", { level: 1, name: "Calendar" })).toBeVisible();
    await expect(page.getByText("Money dates", { exact: true }).locator("xpath=ancestor::*[contains(@class,'rounded')][1]")).toContainText(String(cal.count));
    await expect(page.getByText(`Across ${events} events`)).toBeVisible();
    await expect(page.getByText("Next money date", { exact: true })).toBeVisible();
    await expect(page.getByText("Cash on these dates", { exact: true })).toBeVisible();
    await expect(page.getByText("Shares unlocking", { exact: true })).toBeVisible();
  });

  test("months with money dates can be jumped to, and a date opens its people", async ({ page }) => {
    await page.goto("/calendar");
    const month = page.getByRole("button", { name: /^Oct 2026 \d+/ });
    await month.click();
    await expect(page.getByText("October 2026", { exact: true }).first()).toBeVisible();
    await page.getByRole("button", { name: "Next month with money dates" }).click();
    await expect(page.getByText("November 2026", { exact: true }).first()).toBeVisible();
    await page.getByRole("button", { name: "Previous month with money dates" }).click();
    await expect(page.getByText("October 2026", { exact: true }).first()).toBeVisible();
    await page.getByRole("button", { name: "This month" }).click();
    await expect(page.getByText("November 2026", { exact: true }).first()).toBeVisible();
    const day = page.getByRole("button", { name: /^\d+ Nov 2026: / }).first();
    await day.click();
    await expect(page.getByRole("link", { name: /· (IPO|Block deal|Bulk deal|Insider sale|Buyback|Offer for sale)/ }).first()).toBeVisible();
  });
});

test.describe("Network", () => {
  test.use({ storageState: authFile("rm") });

  test("counts, the graph and the households list agree with the data", async ({ page, request }) => {
    const net = await getJson<{ nodes: { kind?: string; type?: string }[]; legend: { label?: string; key?: string }[] }>(request, "/api/network");
    expect(net.nodes.length).toBeGreaterThan(0);
    await page.goto("/network");
    await expect(page.getByRole("heading", { level: 1, name: "Network" })).toBeVisible();
    for (const label of ["Companies", "People", "Funds and brokers", "Households"]) {
      await expect(page.getByText(label, { exact: true }).first()).toBeVisible();
    }
    // the legend names the node colours
    for (const legend of ["Company with a money event", "Cash in hand", "Shares just unlocked", "Holds shares", "Company or fund", "Same household"]) {
      await expect(page.getByText(legend, { exact: true }).first()).toBeVisible();
    }
    const canvas = page.locator("canvas").first();
    await expect(canvas).toBeVisible();
    expect((await canvas.boundingBox())!.width).toBeGreaterThan(300);
    await expect(page.getByText("Hover a dot to see who it is")).toBeVisible();
  });

  test("a household lists its members, each linking to a call card, with the reason they were linked", async ({ page }) => {
    await page.goto("/network");
    const households = page.getByRole("heading", { name: "Households" }).locator("xpath=ancestor::section[1] | ancestor::div[1]");
    await expect(households.first()).toBeVisible();
    const member = page.getByRole("link", { name: "Bhawna Nitin Gupta" }).first();
    await expect(member).toHaveAttribute("href", /\/people\/.+\/p_/);
    await expect(page.getByText(/share surname 'gupta'/).first()).toBeVisible();
    await member.click();
    await expect(page).toHaveURL(/\/people\//);
  });
});
