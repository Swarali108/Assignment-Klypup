import { getJson, send } from "./helpers/api";
import { ANAND } from "./helpers/data";
import { test, expect, authFile } from "./fixtures";

test.use({ storageState: authFile("head") });

type Team = { total: { calls: number; meetings: number; won: number; assigned: number }; rms: { name: string; email: string; assigned: number }[] };
type ReviewItem = { id: string; title: string; names: string[]; decision: unknown; actions: { action: string; label: string }[] };

test.describe("Team (Head of RMs)", () => {
  test("shows calls, meetings and wins per RM, live from what the RMs log", async ({ page, request }) => {
    const team = await getJson<Team>(request, "/api/team");
    await page.goto("/team");
    await expect(page.getByRole("heading", { level: 1, name: "Team" })).toBeVisible();
    for (const label of ["Calls logged", "Meetings booked", "Won", "Event to first call"]) {
      await expect(page.getByText(label, { exact: true }).first()).toBeVisible();
    }
    await expect(page.getByText(`${team.total.assigned} people assigned to RMs`)).toBeVisible();
    await expect(page.getByText("By RM", { exact: true })).toBeVisible();
    for (const rm of team.rms) await expect(page.getByText(rm.name, { exact: true }).first()).toBeVisible();
    await expect(page.getByText("Follow-ups due").first()).toBeVisible();
  });

  test("assigning a person to an RM shows on Today and in the RM's count, and can be cleared", async ({ page, request }) => {
    const url = `/api/assignments/${ANAND.event}/${ANAND.person}`;
    await page.goto("/today");
    await page.getByPlaceholder("Search name, company or household").fill(ANAND.name);
    const row = page.locator("section[aria-labelledby^='tier-'] ol > li").filter({ hasText: "Insider sale" }).first();
    try {
      await row.getByRole("button", { name: "Assign to an RM" }).click();
      await page.getByRole("menuitem", { name: "Rohan Kapoor" }).click();
      await expect(page.locator("[data-sonner-toast]").first()).toContainText("Assigned to Rohan Kapoor");
      await expect(row.getByRole("button", { name: /Assigned to Rohan Kapoor/ })).toBeVisible();
      const team = await getJson<Team>(request, "/api/team");
      expect(team.rms.find((r) => r.email === "rm@aurelia.demo")!.assigned).toBeGreaterThanOrEqual(1);
      await page.goto("/team");
      await expect(page.getByText(/[1-9]\d* assigned/).first()).toBeVisible();

      // clearing it
      await page.goto("/today");
      await page.getByPlaceholder("Search name, company or household").fill(ANAND.name);
      await row.getByRole("button", { name: /Assigned to Rohan Kapoor/ }).click();
      await page.getByRole("menuitem", { name: "Clear assignment" }).click();
      await expect(row.getByRole("button", { name: "Assign to an RM" })).toBeVisible();
    } finally {
      await send(request, "PUT", url, { rm_email: null });
    }
  });

  test.describe("the RM sees only the name", () => {
    test.use({ storageState: authFile("rm") });
    test("an assigned person shows “Assigned to …” without a control", async ({ page, request, playwright, baseURL, guard }) => {
      guard.allow(403, /\/api\/team\/rms/);
      const url = `/api/assignments/${ANAND.event}/${ANAND.person}`;
      const head = await playwright.request.newContext({ baseURL, storageState: authFile("head") });
      try {
        expect((await send(head, "PUT", url, { rm_email: "rm@aurelia.demo" })).status()).toBe(200);
        await page.goto("/today");
        await page.getByPlaceholder("Search name, company or household").fill(ANAND.name);
        const row = page.locator("section[aria-labelledby^='tier-'] ol > li").filter({ hasText: "Insider sale" }).first();
        await expect(row.getByText(/Assigned to/)).toContainText("Rohan Kapoor");
        await expect(row.getByRole("button", { name: /Assign/ })).toHaveCount(0);
      } finally {
        await send(head, "PUT", url, { rm_email: null });
        await head.dispose();
      }
      void request;
    });
  });
});

test.describe("Review queue", () => {
  test("lists what the system was unsure about, with the question, the names and the reason", async ({ page, request }) => {
    const q = await getJson<{ open: number; decided: number; items: ReviewItem[] }>(request, "/api/review");
    await page.goto("/review");
    await expect(page.getByRole("heading", { level: 1, name: "Review" })).toBeVisible();
    await expect(page.getByRole("tab", { name: `To review ${q.open}` })).toHaveAttribute("aria-selected", "true");
    await expect(page.getByRole("tab", { name: `Decided ${q.decided}` })).toBeVisible();
    const first = q.items.find((i) => !i.decision)!;
    await expect(page.getByRole("heading", { name: first.title }).first()).toBeVisible();
    for (const a of first.actions) await expect(page.getByRole("button", { name: a.label, exact: true }).first()).toBeVisible();
  });

  test("a decision is saved with the reviewer's name and applies at once; Undo takes it back", async ({ page, request }) => {
    const q = await getJson<{ open: number; items: ReviewItem[] }>(request, "/api/review");
    const item = q.items.find((i) => !i.decision)!;
    await page.goto("/review");
    const row = page.locator("li", { hasText: item.names[0] }).first(); // titles repeat, names do not
    try {
      await row.getByRole("button", { name: item.actions[0].label, exact: true }).click();
      await expect(page.locator("[data-sonner-toast]").first()).toContainText("Decision saved and applied");
      await expect(page.getByRole("tab", { name: /^Decided 1/ })).toBeVisible();
      await expect(page.getByRole("tab", { name: `To review ${q.open - 1}` })).toBeVisible();
      expect((await getJson<{ decided: number }>(request, "/api/review")).decided).toBe(1);
      // the decision is listed on the Decided tab
      await page.getByRole("tab", { name: /^Decided/ }).click();
      const decided = page.locator("li", { hasText: item.names[0] }).first();
      await expect(decided).toContainText(/Reviewed by Meera Joshi/);
      await decided.getByRole("button", { name: "Undo" }).click();
      await expect(page.locator("[data-sonner-toast]").first()).toContainText("Decision taken back");
    } finally {
      await send(request, "DELETE", `/api/review?id=${encodeURIComponent(item.id)}`, {});
    }
    const after = await getJson<{ open: number; decided: number }>(request, "/api/review");
    expect(after.decided).toBe(0);
    expect(after.open).toBe(q.open);
  });
});
