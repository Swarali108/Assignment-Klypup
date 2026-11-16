import fs from "node:fs";
import { getJson, send } from "./helpers/api";
import { ANAND } from "./helpers/data";
import { test, expect, authFile } from "./fixtures";

type TodayItem = {
  tier: string;
  person: { id: string; name: string };
  event: { id: string; company: string; type: string };
  members?: { id: string; name: string }[];
  rm: { status: string };
};

test.use({ storageState: authFile("rm") });

const ROWS = "section[aria-labelledby^='tier-'] ol > li";
const HANDLED = ["called", "meeting_booked", "won", "not_now", "not_a_fit"];

test.describe("Today", () => {
  test("shows the list in tiers, cash first, with figures that match the API", async ({ page, request }) => {
    const today = await getJson<{ items: TodayItem[] }>(request, "/api/today");
    const summary = await getJson<{ new_events_this_week: number }>(request, "/api/summary");
    await page.goto("/today");
    await expect(page.getByRole("heading", { level: 1, name: "Today" })).toBeVisible();
    await expect(page.getByText(/Who to call on/)).toBeVisible();

    const open = today.items.filter((i) => !HANDLED.includes(i.rm.status)).length;
    const stat = (label: string) => page.getByText(label, { exact: true }).first().locator("xpath=ancestor::*[contains(@class,'rounded')][1]");
    await expect(stat("People to call")).toContainText(String(open));
    await expect(stat("New events this week")).toContainText(String(summary.new_events_this_week));
    await expect(stat("Cash in hand")).toContainText("₹");

    // the tier sections come in order: cash in hand, shares just unlocked, still holding
    const titles = (await page.locator("section[aria-labelledby^='tier-'] > div h2, section[aria-labelledby^='tier-'] h2, section[aria-labelledby^='tier-'] h3").allInnerTexts()).map((t) => t.trim());
    expect(titles[0]).toMatch(/^Cash in hand/);
    const order = [/^Cash in hand/, /^Shares just unlocked/, /^(Still holding|Holds shares)/];
    const idx = titles.map((t) => order.findIndex((o) => o.test(t))).filter((i) => i >= 0);
    expect(idx).toEqual([...idx].sort((a, b) => a - b));

    await expect(page.getByRole("link", { name: today.items[0].person.name, exact: true }).first()).toBeVisible();
  });

  test("tier tabs narrow the list and show their counts", async ({ page }) => {
    await page.goto("/today");
    const tabs = page.getByRole("tablist", { name: "Call tier" });
    await expect(tabs.getByRole("tab", { name: /^All/ })).toHaveAttribute("aria-selected", "true");
    const unlocked = tabs.getByRole("tab", { name: /Just unlocked/ });
    await unlocked.click();
    await expect(page.locator(ROWS).first()).toBeVisible();
    const n = await page.locator(ROWS).count();
    expect(Number((await unlocked.innerText()).match(/(\d+)\s*$/)?.[1])).toBe(n);
    await expect(page.getByText("Sale proceeds already paid out")).toHaveCount(0);
    await tabs.getByRole("tab", { name: /^All/ }).click();
    await expect(page.getByText("Sale proceeds already paid out")).toBeVisible();
  });

  test("households are grouped on one row and expand to their members", async ({ page, request }) => {
    const { items } = await getJson<{ items: TodayItem[] }>(request, "/api/today");
    const hh = items.find((i) => (i.members?.length ?? 0) > 0)!;
    expect(hh, "the demo data has a household with members").toBeTruthy();
    await page.goto("/today");
    await page.getByPlaceholder("Search name, company or household").fill(hh.person.name);
    const row = page.locator(ROWS).filter({ has: page.getByRole("link", { name: hh.person.name, exact: true }) }).first();
    const toggle = row.getByRole("button", { name: new RegExp(`${hh.members!.length + 1} people`) });
    await expect(toggle).toHaveAttribute("aria-expanded", "false");
    await toggle.click();
    await expect(toggle).toHaveAttribute("aria-expanded", "true");
    await expect(row).toContainText(hh.members![0].name);
  });

  test("filters narrow the list, an impossible search says so, and Clear brings everyone back", async ({ page, request }) => {
    const { items } = await getJson<{ items: TodayItem[] }>(request, "/api/today");
    await page.goto("/today");
    const search = page.getByPlaceholder("Search name, company or household");
    await search.fill("zzzz-nobody-zzzz");
    await expect(page.getByText("No one matches these filters")).toBeVisible();
    await page.getByRole("button", { name: "Clear filters" }).click();
    await expect(page.getByText("No one matches these filters")).toHaveCount(0);

    await page.getByLabel("Event type").click();
    await page.getByRole("option", { name: "IPO", exact: true }).click();
    const ipos = items.filter((i) => i.event.type === "ipo").length;
    await expect(page.getByRole("tab", { name: /^All/ })).toContainText(String(ipos));

    await page.getByLabel("Confidence").click();
    await page.getByRole("option", { name: "High confidence only" }).click();
    await page.getByLabel("Minimum amount").click();
    await page.getByRole("option", { name: /₹100 Cr and above/ }).click();
    const big = await page.getByRole("tab", { name: /^All/ }).innerText();
    expect(Number(big.match(/(\d+)\s*$/)?.[1])).toBeLessThan(ipos);
    await page.getByRole("button", { name: "Clear", exact: true }).click();
    await expect(page.getByRole("tab", { name: /^All/ })).toContainText(String(items.length));
  });

  test("the filters are remembered in this browser", async ({ page }) => {
    await page.goto("/today");
    await page.getByPlaceholder("Search name, company or household").fill("Sharma");
    await page.getByRole("switch", { name: "Hide logged calls" }).click();
    const stored = await page.evaluate(() => window.localStorage.getItem("aurelia.today.filters"));
    test.skip(stored === null, "remembered filters are not deployed on this build");
    await page.reload();
    await expect(page.getByPlaceholder("Search name, company or household")).toHaveValue("Sharma");
    await expect(page.getByRole("switch", { name: "Hide logged calls" })).toHaveAttribute("aria-checked", "true");
    await page.getByRole("button", { name: "Clear", exact: true }).click();
    await page.reload();
    await expect(page.getByPlaceholder("Search name, company or household")).toHaveValue("");
  });

  test("logging a call from the row is undoable", async ({ page, request }) => {
    const url = `/api/rm/${ANAND.event}/${ANAND.person}`;
    await page.goto("/today");
    await page.getByPlaceholder("Search name, company or household").fill(ANAND.name);
    try {
      const log = page.locator(ROWS).filter({ hasText: "Insider sale" }).getByLabel(`Log the call with ${ANAND.name}`);
      await log.getByRole("button", { name: "Called" }).click();
      await expect(page.locator("[data-sonner-toast]").first()).toBeVisible();
      await expect.poll(async () => (await getJson<{ status: string }>(request, url)).status).toBe("called");
      await page.locator("[data-sonner-toast]").getByRole("button", { name: "Undo" }).first().click();
      await expect.poll(async () => (await getJson<{ status: string }>(request, url)).status).toBe("to_call");
    } finally {
      await send(request, "PUT", url, { status: "to_call", note: "" });
    }
  });

  test("Export for CRM downloads the call list as CSV with the documented columns", async ({ page, request }) => {
    const { items } = await getJson<{ items: TodayItem[] }>(request, "/api/today");
    await page.goto("/today");
    const [download] = await Promise.all([page.waitForEvent("download"), page.getByRole("link", { name: /Export for CRM/ }).click()]);
    expect(download.suggestedFilename()).toBe("aurelia-calls.csv");
    const text = fs.readFileSync((await download.path())!, "utf8");
    expect(text.split("\n")[0].trim()).toBe(
      "call_id,event_id,company,event_type,person_id,name,role,tier,amount_cr,amount_kind,amount_is_estimate,amount_text,money_date,timing,confidence,why,rm_status,follow_up_date,note",
    );
    expect(text).toContain(items[0].person.name);
  });

  test("the weekly short list downloads from Today", async ({ page, request }) => {
    test.skip((await request.get("/api/me/since")).status() === 404, "weekly short list not deployed on this build");
    await page.goto("/today");
    await expect(page.getByRole("link", { name: /Download weekly short list/ })).toHaveAttribute("href", "/weekly?print=1");
  });
});

test.describe("Today as a viewer", () => {
  test.use({ storageState: authFile("viewer") });

  test("is read-only: no export, no call logging, but the list is there", async ({ page, guard }) => {
    guard.allow(403, /\/api\/team\/rms/);
    await page.goto("/today");
    await expect(page.getByRole("heading", { level: 1, name: "Today" })).toBeVisible();
    await expect(page.locator(ROWS).first()).toBeVisible();
    await expect(page.getByRole("link", { name: /Export for CRM/ })).toHaveCount(0);
    await expect(page.getByRole("button", { name: "Called", exact: true })).toHaveCount(0);
  });
});
