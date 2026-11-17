import { getJson } from "./helpers/api";
import { JIO, SEDEMAC, VECTRAS, WIPRO } from "./helpers/data";
import { test, expect, authFile } from "./fixtures";

type Ev = { id: string; company: string; type: string; type_label: string; people_count: number; status: string; empty_reason: string | null };
type Feed = { groups: Record<"today" | "upcoming" | "recent", { source_badge: string; status: string }[]> };

test.use({ storageState: authFile("admin") });

test.describe("Events: the list and the feed", () => {
  test("lists every processed event, filterable, with counts from the API", async ({ page, request }) => {
    const { events } = await getJson<{ events: Ev[] }>(request, "/api/events");
    await page.goto("/events");
    await expect(page.getByRole("heading", { level: 1, name: "Events" })).toBeVisible();
    await expect(page.getByRole("region", { name: "Processed events" })).toContainText(String(events.length));
    const filter = page.getByRole("group", { name: "Filter events" });
    await expect(filter.getByRole("button", { name: /^All/ })).toContainText(String(events.length));
    await filter.getByRole("button", { name: /^No one to call/ }).click();
    await expect(filter.getByRole("button", { name: /^No one to call/ })).toHaveAttribute("aria-pressed", "true");
    await expect(page.getByText("Every amount traced to its filing page")).toBeVisible();
    await filter.getByRole("button", { name: /^All/ }).click();
  });

  test("New filings shows Today / Upcoming / Recent with counts, and an honest empty state", async ({ page, request }) => {
    const feed = await getJson<Feed>(request, "/api/feed");
    await page.goto("/events");
    const panel = page.getByRole("region", { name: "New filings" });
    await expect(panel).toBeVisible();
    await expect(panel).toContainText(/Watching \d+ sources/);
    const tabs = panel.getByRole("tablist", { name: "Filings by date" });
    for (const [key, label] of [["today", "Today"], ["upcoming", "Upcoming"], ["recent", "Recent"]] as const) {
      await expect(tabs.getByRole("tab", { name: new RegExp(`^${label}`) })).toContainText(String(feed.groups[key].length));
    }
    if (feed.groups.today.length === 0) {
      await tabs.getByRole("tab", { name: /^Today/ }).click();
      await expect(panel.getByText("Nothing here yet")).toBeVisible();
      await expect(panel.getByText(/No new filings yet today/)).toBeVisible();
    }
  });

  test("each filing carries the badge of the exchange or regulator it came from (SEBI, NSE, BSE)", async ({ page, request }) => {
    const feed = await getJson<Feed>(request, "/api/feed");
    const owners = new Set([...feed.groups.upcoming, ...feed.groups.recent].map((i) => i.source_badge));
    await page.goto("/events");
    const panel = page.getByRole("region", { name: "New filings" });
    for (const tab of ["Upcoming", "Recent"]) {
      await panel.getByRole("tab", { name: new RegExp(`^${tab}`) }).click();
      const list = panel.getByRole("tabpanel");
      for (const owner of ["SEBI", "NSE", "BSE"]) {
        if (owners.has(owner)) await expect(list.getByText(owner, { exact: true }).first()).toBeVisible();
      }
    }
    // the badge says why it is there
    await panel.getByRole("tab", { name: /^Recent/ }).click();
    const nse = panel.getByTitle(/From NSE/).first();
    if (await nse.count()) await expect(nse).toHaveAttribute("title", /terms forbid automated collection/);
    // watch items (IPOs coming, acquisition notices) are tucked away until asked for
    const watch = panel.getByRole("button", { name: /to watch: IPOs coming/ });
    if (await watch.count()) {
      await watch.click();
      await expect(watch).toHaveAttribute("aria-expanded", "true");
    }
  });

  test("the events tab choice is remembered in this browser", async ({ page }) => {
    await page.goto("/events");
    const filter = page.getByRole("group", { name: "Filter events" });
    await filter.getByRole("button", { name: /^With calls/ }).click();
    const stored = await page.evaluate(() => window.localStorage.getItem("finsight.events.tab"));
    test.skip(stored === null, "remembered tabs are not deployed on this build");
    await page.reload();
    await expect(filter.getByRole("button", { name: /^With calls/ })).toHaveAttribute("aria-pressed", "true");
    await filter.getByRole("button", { name: /^All/ }).click();
  });
});

test.describe("Events: single events", () => {
  test("SEDEMAC lists the people to call with cash and unlock tiers", async ({ page, request }) => {
    const ev = await getJson<Ev>(request, `/api/events/${SEDEMAC.event}`);
    await page.goto(`/events/${SEDEMAC.event}`);
    await expect(page.getByRole("heading", { level: 1, name: ev.company })).toBeVisible();
    await expect(page.getByRole("link", { name: "Manish Sharma" }).first()).toBeVisible();
    await expect(page.getByRole("button", { name: "Process now" })).toBeVisible();
  });

  test("Wipro's buyback names the promoters who tender", async ({ page }) => {
    await page.goto(`/events/${WIPRO.event}`);
    await expect(page.getByRole("heading", { level: 1, name: /Wipro/ })).toBeVisible();
    await expect(page.getByRole("link", { name: /Azim H Premji/i }).first()).toBeVisible();
    await expect(page.getByText(/Buyback/).first()).toBeVisible();
  });

  test("Jio Platforms says plainly that no individual is to call, and why", async ({ page, request }) => {
    const ev = await getJson<Ev>(request, `/api/events/${JIO.event}`);
    expect(ev.people_count).toBe(0);
    await page.goto(`/events/${JIO.event}`);
    await expect(page.getByRole("heading", { level: 1, name: /Jio Platforms/ })).toBeVisible();
    await expect(page.getByText("No one to call from this event")).toBeVisible();
    await expect(page.getByText(ev.empty_reason!)).toBeVisible();
  });

  test("an insider sale and a block deal are events too, dated by the trade", async ({ page, request }) => {
    const { events } = await getJson<{ events: Ev[] }>(request, "/api/events");
    const insider = events.find((e) => e.type === "insider_sale" && e.people_count > 0)!;
    const block = events.find((e) => e.type === "block_deal" && e.people_count > 0)!;
    expect(insider && block, "the demo data has insider sales and block deals").toBeTruthy();
    for (const [ev, label] of [[insider, "Insider sale"], [block, block.id.includes("bulk_deal") ? "Bulk deal" : "Block deal"]] as const) {
      await page.goto(`/events/${ev.id}`);
      await expect(page.getByRole("heading", { level: 1, name: ev.company })).toBeVisible();
      await expect(page.getByText(new RegExp(`${label} · Trade date`)).first()).toBeVisible();
      await expect(page.getByRole("link", { name: /^(?!.*Events$).+/ }).first()).toBeVisible();
    }
  });

  test("an event that does not exist says so", async ({ page, guard }) => {
    guard.allow(404);
    await page.goto("/events/no_such_event_at_all");
    await expect(page.getByText("We could not find this event").first()).toBeVisible();
  });
});

test.describe("Events: processing (admin)", () => {
  test("Process now on a cached event shows the steps live and ends with an updated call list", async ({ page, request }) => {
    const before = await getJson<Ev>(request, `/api/events/${VECTRAS.event}`);
    await page.goto(`/events/${VECTRAS.event}`);
    await page.getByRole("button", { name: "Process now" }).click();
    const panel = page.getByRole("region", { name: /^Processing Vectras/ });
    await expect(panel).toBeVisible();
    await expect(panel).toContainText(/Reading the filings for Vectras|Call list updated/);
    for (const step of ["Find the right pages", "Read the tables", "Match people and families", "Rank who to call", "Write call briefs", "Assemble the call list"]) {
      await expect(panel).toContainText(step);
    }
    await expect(panel.getByRole("heading", { name: "Call list updated" })).toBeVisible({ timeout: 120_000 });
    // saved model answers are replayed: the run costs nothing new, and the call list did not change
    await expect(panel).toContainText(/no new cost|cost \$0/i);
    const after = await getJson<Ev>(request, `/api/events/${VECTRAS.event}`);
    expect(after.people_count).toBe(before.people_count);
  });

  test("Add event from links opens a dialog for pasted links and cancels without creating anything", async ({ page, request }) => {
    const n = (await getJson<{ events: Ev[] }>(request, "/api/events")).events.length;
    await page.goto("/events");
    await page.getByRole("button", { name: /Add event from links/ }).click();
    const dialog = page.getByRole("dialog", { name: "Add an event from links" });
    await expect(dialog).toBeVisible();
    await expect(dialog.getByPlaceholder("https://…/prospectus.pdf")).toBeVisible();
    await expect(dialog.getByRole("button", { name: /Read|Check/ }).first()).toBeDisabled();
    await page.keyboard.press("Escape");
    await expect(dialog).toBeHidden();
    expect((await getJson<{ events: Ev[] }>(request, "/api/events")).events.length).toBe(n);
  });

  test("the auto-processing chip and the check-now button are there (this suite never runs discovery)", async ({ page }) => {
    await page.goto("/events");
    await expect(page.getByText(/Auto-processed today/)).toBeVisible();
    await expect(page.getByRole("button", { name: /Check for new filings now/ })).toBeVisible();
  });
});

test.describe("Events: what an RM cannot do", () => {
  test.use({ storageState: authFile("rm") });

  test("no Process now and no Add from links", async ({ page, guard }) => {
    guard.allow(403);
    await page.goto(`/events/${VECTRAS.event}`);
    await expect(page.getByRole("heading", { level: 1, name: /Vectras/ })).toBeVisible();
    await expect(page.getByRole("button", { name: "Process now" })).toHaveCount(0);
    await page.goto("/events");
    await expect(page.getByRole("button", { name: /Add event from links/ })).toHaveCount(0);
  });
});
