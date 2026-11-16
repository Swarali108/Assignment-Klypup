import { expect, test as base } from "@playwright/test";
import { authFile } from "./helpers/accounts";

export { expect, authFile };

type Allowed = { status: number; url?: RegExp };

type Guard = {
  /** Expect these API answers (e.g. a 403 in a permission test); anything else on /api fails the test. */
  allow: (status: number, url?: RegExp) => void;
  /** Console and network problems seen so far. */
  problems: () => string[];
  isAllowed: (status: number, url: string) => boolean;
};

type Options = {
  /** Keep the first-sign-in setup guide on screen (default: dismiss it without saving anything). */
  keepSetupGuide: boolean;
  /** Keep the daily-brief sheet on screen (default: dismiss it). */
  keepBriefSheet: boolean;
};

/**
 * `test` for this suite. Every test fails on page errors, console errors and failed /api requests (4xx/5xx or a
 * request that never completes), except answers the test announced with guard.allow(). The daily-brief sheet and the
 * setup guide can cover the page the first time a role signs in, so they are dismissed on sight (a no-op when absent).
 */
export const test = base.extend<Options & { guard: Guard }>({
  keepSetupGuide: [false, { option: true }],
  keepBriefSheet: [false, { option: true }],

  guard: async ({}, use) => {
    const allowed: Allowed[] = [];
    const seen: string[] = [];
    await use({
      allow: (status, url) => void allowed.push({ status, url }),
      problems: () => seen,
      isAllowed: (status, url) => allowed.some((x) => x.status === status && (!x.url || x.url.test(url))),
    });
  },

  page: async ({ page, guard, keepSetupGuide, keepBriefSheet }, use, info) => {
    const problems = guard.problems();

    page.on("pageerror", (e) => problems.push(`pageerror: ${e.message}`));
    page.on("console", (m) => {
      if (m.type() !== "error") return;
      const text = m.text();
      // "Failed to load resource: ... 403" is reported by the response listener below, with its own allow-list.
      if (/Failed to load resource/.test(text)) return;
      problems.push(`console.error: ${text.slice(0, 300)} (${m.location().url})`);
    });
    page.on("response", (r) => {
      const url = r.url();
      if (!/\/api\//.test(url)) return;
      const s = r.status();
      if (s >= 400 && !guard.isAllowed(s, url)) problems.push(`API ${s} ${r.request().method()} ${url.replace(/^https?:\/\/[^/]+/, "")}`);
    });
    page.on("requestfailed", (r) => {
      const url = r.url();
      if (!/\/api\//.test(url)) return;
      const why = r.failure()?.errorText ?? "";
      // Navigations and route changes abort in-flight reads and streams on purpose.
      if (/ERR_ABORTED|cancelled|NS_BINDING_ABORTED/i.test(why)) return;
      problems.push(`API request failed ${r.method()} ${url.replace(/^https?:\/\/[^/]+/, "")}: ${why}`);
    });

    if (!keepBriefSheet) {
      await page.addLocatorHandler(page.getByRole("dialog").filter({ hasText: /your brief for/i }), async () => {
        await page.keyboard.press("Escape");
      });
    }
    if (!keepSetupGuide) {
      // The first-sign-in guide would cover the page for accounts that have not done it (head@, new.rm@), and closing it
      // would save "onboarded" for that account. So the page is told the account is set up, and nothing is written.
      await page.route("**/api/me/preferences", async (route) => {
        try {
          if (route.request().method() === "PUT") return await route.fulfill({ json: { onboarded: true, event_types: [], min_ticket_cr: null, alerts: "daily", book_count: 0, ...(route.request().postDataJSON() ?? {}) } });
          const current = await (await route.fetch()).json();
          return await route.fulfill({ json: { ...current, onboarded: true } });
        } catch {
          /* the test already ended */
        }
      });
      await page.route("**/api/auth/me", async (route) => {
        try {
          const res = await route.fetch();
          if (!res.ok()) return await route.fulfill({ response: res });
          return await route.fulfill({ json: { ...(await res.json()), onboarded: true } });
        } catch {
          /* the test already ended */
        }
      });
      await page.addLocatorHandler(page.getByRole("dialog").filter({ has: page.getByRole("button", { name: "Close the setup guide" }) }), async () => {
        await page.getByRole("button", { name: "Close the setup guide" }).click();
      });
    }

    await use(page);
    await page.unrouteAll({ behavior: "ignoreErrors" });

    // Fail on anything unexpected, unless the test already failed for its own reason.
    if (info.status === info.expectedStatus) expect(problems, "page errors / failed /api requests").toEqual([]);
  },
});
