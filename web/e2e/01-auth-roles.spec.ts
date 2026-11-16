import type { Page } from "@playwright/test";
import { ACCOUNTS, PASSWORD, type Role } from "./helpers/accounts";
import { test, expect, authFile } from "./fixtures";

const NAV = {
  everyone: ["Today", "Events", "Calendar", "Network", "History"],
  team: ["Team", "Review"],
  admin: ["Trust & Ops", "Sources", "Accuracy", "System health", "Pipeline console"],
};

async function navLabels(page: Page) {
  return (await page.getByRole("navigation", { name: "Main" }).first().getByRole("link").allInnerTexts()).map((t) => t.trim());
}

test.describe("anonymous visitor", () => {
  test.use({ storageState: { cookies: [], origins: [] } });

  test("every page redirects to the sign-in page and remembers where you were going", async ({ page }) => {
    await page.goto("/");
    await expect(page).toHaveURL(/\/login$/);
    await page.goto("/today");
    await expect(page).toHaveURL(/\/login\?next=%2Ftoday$/);
    await page.goto("/people/sedemac_ipo/p_manish_sharma?tab=trail");
    await expect(page).toHaveURL(/\/login\?next=/);
    expect(decodeURIComponent(new URL(page.url()).searchParams.get("next") ?? "")).toContain("/people/sedemac_ipo/p_manish_sharma");
  });

  test("the login page lists the demo accounts and fills one in", async ({ page }) => {
    await page.goto("/login");
    await expect(page.getByRole("button", { name: "Sign in", exact: true })).toBeVisible();
    for (const label of ["Admin", "Relationship manager", "Viewer", "New RM"]) {
      await expect(page.getByRole("button", { name: `Fill in the ${label} account` })).toBeVisible();
    }
    await page.getByRole("button", { name: "Fill in the Viewer account" }).click();
    await expect(page.locator("#email")).toHaveValue(ACCOUNTS.viewer.email);
    await expect(page.locator("#password")).toHaveValue(PASSWORD);
    await page.getByRole("button", { name: "Show password" }).click();
    await expect(page.locator("#password")).toHaveAttribute("type", "text");
  });

  test("a wrong password is refused with a plain message and no session", async ({ page, guard }) => {
    guard.allow(401, /\/api\/auth\/login/);
    await page.goto("/login");
    await page.locator("#email").fill(ACCOUNTS.rm.email);
    await page.locator("#password").fill("not-the-password");
    await page.getByRole("button", { name: "Sign in", exact: true }).click();
    await expect(page.getByRole("alert").filter({ hasText: "That email and password do not match" })).toBeVisible();
    await expect(page).toHaveURL(/\/login/);
    await page.goto("/today");
    await expect(page).toHaveURL(/\/login/);
  });

  test("an unknown email gets the same message as a wrong password", async ({ page, guard }) => {
    guard.allow(401, /\/api\/auth\/login/);
    await page.goto("/login");
    await page.locator("#email").fill("nobody@aurelia.demo");
    await page.locator("#password").fill(PASSWORD);
    await page.getByRole("button", { name: "Sign in", exact: true }).click();
    await expect(page.getByRole("alert").filter({ hasText: "That email and password do not match" })).toBeVisible();
  });

  test("signing in sends you to the page you asked for", async ({ page }) => {
    await page.goto("/login?next=%2Fevents");
    await page.locator("#email").fill(ACCOUNTS.viewer.email);
    await page.locator("#password").fill(PASSWORD);
    await page.getByRole("button", { name: "Sign in", exact: true }).click();
    await expect(page).toHaveURL(/\/events$/);
    await expect(page.getByRole("heading", { level: 1, name: "Events" })).toBeVisible();
  });

  test("the API answers 401 without a session, but the health and config probes stay public", async ({ request }) => {
    for (const url of ["/api/today", "/api/events", "/api/me", "/api/chat/conversations"]) {
      expect((await request.get(url)).status(), url).toBe(401);
    }
    expect((await request.get("/api/auth/config")).status()).toBe(200);
    expect((await request.get("/api/health")).status()).toBe(200);
  });
});

test.describe("sign out", () => {
  test.use({ storageState: { cookies: [], origins: [] } });

  test("signing out ends the session", async ({ page, guard }) => {
    guard.allow(401); // reads that were in flight when the session ended
    // A private session of its own, so signing out does not disturb the stored login other tests use.
    await page.goto("/login");
    await page.locator("#email").fill(ACCOUNTS.viewer.email);
    await page.locator("#password").fill(PASSWORD);
    await page.getByRole("button", { name: "Sign in", exact: true }).click();
    await expect(page).toHaveURL(/\/$/);
    await page.getByRole("button", { name: /Account menu for/ }).click();
    await page.getByRole("menuitem", { name: /Sign out/ }).click();
    await expect(page).toHaveURL(/\/login/);
    await page.goto("/today");
    await expect(page).toHaveURL(/\/login/);
  });
});

const ROLE_CASES: { role: Role; admin: boolean; team: boolean }[] = [
  { role: "admin", admin: true, team: true },
  { role: "head", admin: false, team: true },
  { role: "rm", admin: false, team: false },
  { role: "viewer", admin: false, team: false },
];

for (const c of ROLE_CASES) {
  test.describe(`${c.role} role`, () => {
    test.use({ storageState: authFile(c.role) });

    test("sees the right navigation and account label", async ({ page }) => {
      await page.goto("/today");
      await expect(page.getByRole("heading", { level: 1, name: "Today" })).toBeVisible();
      await expect(page.getByRole("button", { name: /Account menu for/ })).toBeVisible(); // the session has loaded
      const labels = await navLabels(page);
      for (const l of NAV.everyone) expect(labels).toContain(l);
      for (const l of NAV.team) c.team ? expect(labels).toContain(l) : expect(labels).not.toContain(l);
      for (const l of NAV.admin) c.admin ? expect(labels).toContain(l) : expect(labels).not.toContain(l);
      await page.getByRole("button", { name: /Account menu for/ }).click();
      await expect(page.getByRole("menu")).toContainText(ACCOUNTS[c.role].label);
    });

    if (!c.admin) {
      test("an admin page shows a plain explanation, not a broken page", async ({ page }) => {
        await page.goto("/ops");
        await expect(page.getByText("Trust & Ops is for admins")).toBeVisible();
        await page.goto("/admin/pipeline");
        await expect(page.getByText(/for admins/i).first()).toBeVisible();
      });
    }

    if (!c.team) {
      test("Team and Review say they are for the Head of RMs and admins", async ({ page, guard }) => {
      guard.allow(403, /\/api\/(team|review)/);
        await page.goto("/review");
        await expect(page.getByText("The review queue is for the Head of RMs and admins")).toBeVisible();
        await page.goto("/team");
        await expect(page.getByText(/Head of RMs/i).first()).toBeVisible();
        await expect(page.getByRole("link", { name: "Back to Today" })).toBeVisible();
      });
    }
  });
}

test.describe("who am I", () => {
  for (const role of ["admin", "rm", "viewer", "head"] as Role[]) {
    test(`${role}: /api/auth/me carries the role and permissions`, async ({ playwright, baseURL }) => {
      const ctx = await playwright.request.newContext({ baseURL, storageState: authFile(role) });
      const me = await (await ctx.get("/api/auth/me")).json();
      expect(me.email).toBe(ACCOUNTS[role].email);
      expect(me.role).toBe(role);
      expect(me.permissions.view).toBe(true);
      expect(me.permissions.ops).toBe(role === "admin");
      expect(me.permissions.process).toBe(role === "admin");
      expect(me.permissions.team).toBe(role === "admin" || role === "head");
      expect(me.permissions.edit_rm).toBe(role !== "viewer");
      await ctx.dispose();
    });
  }
});
