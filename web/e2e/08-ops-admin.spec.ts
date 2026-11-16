import { getJson } from "./helpers/api";
import { VECTRAS } from "./helpers/data";
import { test, expect, authFile } from "./fixtures";

test.use({ storageState: authFile("admin") });

test.describe("Trust & Ops", () => {
  test("shows what was checked and kept, straight from the verification totals", async ({ page, request }) => {
    const ops = await getJson<{ totals: { events: number; proposed: number; kept: number; rejected: number }; target_usd: number }>(request, "/api/ops");
    await page.goto("/ops");
    await expect(page.getByRole("heading", { level: 1, name: "Trust & Ops" })).toBeVisible();
    const t = ops.totals;
    await expect(page.getByText("Values checked", { exact: true }).locator("xpath=ancestor::*[contains(@class,'rounded')][1]")).toContainText(t.proposed.toLocaleString("en-IN"));
    await expect(page.getByText(`across ${t.events} events`, { exact: false })).toBeVisible();
    const aside = t.proposed - t.kept - t.rejected;
    await expect(page.getByText(`${t.kept.toLocaleString("en-IN")} kept · ${t.rejected.toLocaleString("en-IN")} rejected${aside > 0 ? ` · ${aside.toLocaleString("en-IN")} set aside` : ""}, never shown`)).toBeVisible();
    await expect(page.getByText("Average cost per event", { exact: true })).toBeVisible();
    await expect(page.getByText("Most expensive event", { exact: true })).toBeVisible();
    await expect(page.getByText(/Values kept and rejected, per event/)).toBeVisible();
  });

  test("the token panel reports cache hits, savings and cost per model", async ({ page, request }) => {
    const tok = await getJson<{ questions: number; cache_hit_rate: number; by_model: { model: string; calls: number }[] }>(request, "/api/ops/tokens");
    await page.goto("/ops");
    const panel = page.locator('section[aria-labelledby="token-optimization"]');
    await expect(panel.getByText("Token optimization")).toBeVisible();
    await expect(panel).toContainText("Cache hit rate");
    await expect(panel).toContainText(`${Math.round(tok.cache_hit_rate * 100)}%`);
    await expect(panel).toContainText("Saved by caching");
    await expect(panel).toContainText("Saved by summarising");
    await expect(panel).toContainText(new RegExp(`Across ${tok.questions} answers|Across ${tok.questions.toLocaleString("en-IN")} answers`));
    for (const m of tok.by_model) await expect(panel).toContainText(m.model.split("/")[1]);
    await expect(page.getByText("Where the time goes")).toBeVisible();
    await expect(page.getByText(/^Latest runs/).first()).toBeVisible();
  });
});

test.describe("Accuracy", () => {
  test("scores the call lists against hand-read filings, with every miss and its page", async ({ page, request }) => {
    const { result } = await getJson<{ result: { overall: { hit_rate: number; hits: number; value_fields: number; wrong: number; invented: number; missing: number; people: number; fully_right: number }; misses: unknown[] } }>(request, "/api/ops/accuracy");
    const o = result.overall;
    await page.goto("/ops/accuracy");
    await expect(page.getByRole("heading", { level: 1, name: "Accuracy" })).toBeVisible();
    await expect(page.getByText(`${(o.hit_rate * 100).toFixed(1)}%`).first()).toBeVisible();
    await expect(page.getByText(`${o.hits} of ${o.value_fields} values right`)).toBeVisible();
    await expect(page.getByText(`${o.fully_right} of ${o.people}`).first()).toBeVisible();
    await expect(page.getByText("Wrong or invented", { exact: true })).toBeVisible();
    await expect(page.getByText("Nothing shown that the filings do not say")).toBeVisible();
    expect(o.wrong + o.invented).toBe(0);
    await expect(page.getByText("Hit rate by field")).toBeVisible();
    await expect(page.getByText(`Every miss`).first()).toBeVisible();
    // the re-score button is there; it is not pressed in this suite
    await expect(page.getByRole("button", { name: /Check again/ })).toBeVisible();
  });
});

test.describe("System health", () => {
  test("shows spend, caches, sources and failed runs, and refreshes", async ({ page, request }) => {
    const h = await getJson<{ spend: { today: { calls: number; cached_calls: number; paid_calls: number } }; failed_runs: unknown[] }>(request, "/api/ops/health");
    await page.goto("/ops/health");
    await expect(page.getByRole("heading", { level: 1, name: "System health" })).toBeVisible();
    for (const label of ["Model spend today", "Model calls today", "Answers from the cache", "Failed runs"]) {
      await expect(page.getByText(label, { exact: true }).first()).toBeVisible();
    }
    await expect(page.getByText(/\d[\d,]* paid, \d[\d,]* from the cache/)).toBeVisible();
    await expect(page.getByText("Spend and limits")).toBeVisible();
    await expect(page.getByText("Caches", { exact: true })).toBeVisible();
    await expect(page.getByText("Downloaded documents")).toBeVisible();
    await expect(page.getByText("Where filings come from")).toBeVisible();
    if (h.failed_runs.length === 0) await expect(page.getByText("No failed runs")).toBeVisible();
    await page.getByRole("button", { name: "Refresh" }).first().click();
    await expect(page.getByText("Spend and limits")).toBeVisible();
  });
});

test.describe("Pipeline console", () => {
  async function pickVectras(page: import("@playwright/test").Page) {
    await page.getByRole("combobox").first().click();
    await page.getByRole("option", { name: new RegExp(`^${VECTRAS.company}`) }).first().click();
    await expect(page.getByText(/people on the call list/)).toBeVisible();
  }

  test("runs one cached step on a finished event; the run is recorded and compared with the run before", async ({ page, request }) => {
    const runs = async () => (await getJson<{ runs: unknown[] }>(request, `/api/admin/events/${VECTRAS.event}/history`)).runs.length;
    const before = await runs();
    await page.goto("/admin/pipeline");
    await expect(page.getByRole("heading", { level: 1, name: "Pipeline console" })).toBeVisible();
    await expect(page.getByText("Nothing running")).toBeVisible();
    await pickVectras(page);

    await page.getByRole("radiogroup", { name: "What to run" }).getByRole("radio", { name: "Rank who to call" }).click();
    await expect(page.getByRole("radiogroup", { name: "Model answers" }).getByRole("radio", { name: /^From the cache/ })).toHaveAttribute("aria-checked", "true");
    // the button stays disabled while another job (e.g. a scheduled check) is running; wait for it
    await expect(page.getByRole("button", { name: /^Run rank who to call/i })).toBeEnabled({ timeout: 120_000 });
    const started = page.waitForResponse((r) => r.url().endsWith("/api/admin/run") && r.request().method() === "POST");
    await page.getByRole("button", { name: /^Run rank who to call/i }).click();
    const job = await (await started).json();
    expect(job.job_id).toBeTruthy();
    expect(job.fresh).toBeFalsy();
    await expect.poll(runs, { timeout: 90_000 }).toBeGreaterThan(before);

    // the run's own log is kept, and the history compares the last two runs
    const log = await request.get(`/api/admin/jobs/${job.job_id}/log`);
    expect(log.status()).toBe(200);
    await page.goto("/admin/pipeline");
    await pickVectras(page);
    await expect(page.getByRole("heading", { name: "Run history" })).toBeVisible();
    await expect(page.getByText("What changed since the run before")).toBeVisible();
    // a cached re-run of the same documents must not change anyone's amount, tier or order
    await expect(page.getByText(/Nothing changed: the same \d+ (person|people), with the same amounts, tiers and order/)).toBeVisible();
  });

  test("the finished run stays on screen with its steps and log", async ({ page }) => {
    // When a run ends the console refreshes its event list in the background; it must keep the selected event and the
    // finished run's steps and log on screen (it used to fall back to the first event and "Nothing running").
    await page.goto("/admin/pipeline");
    await pickVectras(page);
    await page.getByRole("radiogroup", { name: "What to run" }).getByRole("radio", { name: "Rank who to call" }).click();
    await page.getByRole("button", { name: /^Run rank who to call/i }).click();
    await expect(page.getByText(/Finished in/)).toBeVisible({ timeout: 15_000 });
    await expect(page.getByRole("log")).toBeVisible();
    await expect(page.getByText("Nothing running")).toHaveCount(0);
    await expect(page.getByRole("combobox").first()).toContainText(VECTRAS.company);
  });

  test("a fresh run shows an estimate and waits for Confirm; Cancel spends nothing", async ({ page }) => {
    await page.goto("/admin/pipeline");
    await page.getByRole("combobox").first().click();
    await page.getByRole("option", { name: new RegExp(`^${VECTRAS.company}`) }).first().click();
    await page.getByRole("radiogroup", { name: "Model answers" }).getByRole("radio", { name: /^Fresh/ }).click();
    await page.getByRole("button", { name: /Estimate a fresh run/ }).click();
    await expect(page.getByText(/About \$[\d.]+ to \$[\d.]+/)).toBeVisible();
    await expect(page.getByText(/A fresh run of/)).toBeVisible();
    await expect(page.getByRole("button", { name: "Confirm and run" })).toBeVisible();
    await page.getByRole("button", { name: "Cancel", exact: true }).click();
    await expect(page.getByRole("button", { name: "Confirm and run" })).toHaveCount(0);
    await expect(page.getByText("Nothing running")).toBeVisible();
  });
});
