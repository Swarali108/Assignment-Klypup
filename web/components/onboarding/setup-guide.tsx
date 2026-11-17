"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { usePathname, useRouter } from "next/navigation";
import { toast } from "sonner";
import { BellRing, BookUser, Check, Compass, Download, FileUp, Loader2, Radar, X } from "lucide-react";
import { cn } from "@/lib/utils";
import { api } from "@/lib/api";
import { useSession } from "@/lib/session";
import { fitsCoverage, namesFromCsv, prefsApi, usePrefs, type Alerts, type Preferences } from "@/lib/prefs";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogTitle } from "@/components/ui/dialog";
import type { CallItem } from "@/lib/types";

const TYPE_COPY: Record<string, { label: string; note: string }> = {
  ipo: { label: "IPOs", note: "Sellers in the offer get cash at listing; promoters' shares unlock later." },
  buyback: { label: "Buybacks", note: "Shareholders who tender get paid by the company." },
  ofs_stock_exchange: { label: "Offers for sale on the exchange", note: "Promoters sell a block through the exchange window." },
  ofs: { label: "Offers for sale", note: "Promoters sell part of their holding." },
};
const TICKETS = [null, 10, 25, 50, 100] as const;
const ALERTS: { value: Alerts; label: string; note: string }[] = [
  { value: "daily", label: "Every morning", note: "A short list of who to call, before the market opens." },
  { value: "weekly", label: "Monday summary", note: "The week's new money events, in one note." },
  { value: "off", label: "No alerts", note: "I'll open FinSight when I need it." },
];
const STEPS = [
  { title: "What do you cover?", icon: Radar },
  { title: "Bring your book", icon: BookUser },
  { title: "How should we nudge you?", icon: BellRing },
  { title: "A quick look around", icon: Compass },
] as const;

function Choice({ on, onClick, children, className }: { on: boolean; onClick: () => void; children: React.ReactNode; className?: string }) {
  return (
    <button
      type="button"
      role="checkbox"
      aria-checked={on}
      onClick={onClick}
      className={cn(
        "relative flex w-full items-start gap-3 rounded-xl border bg-surface px-4 py-3 text-left transition-[border-color,background-color] duration-150",
        on ? "border-brand/45 bg-brand-soft/50" : "hover:border-input",
        className,
      )}
    >
      <span className={cn("mt-0.5 grid size-4.5 shrink-0 place-items-center rounded-[5px] border transition-colors", on ? "border-brand bg-brand text-brand-foreground" : "border-input bg-surface")}>
        {on ? <Check className="size-3" strokeWidth={3} aria-hidden /> : null}
      </span>
      <span className="min-w-0">{children}</span>
    </button>
  );
}

/** First sign-in guide: coverage, client book, alerts, then the 4-stop tour. Skippable; reopen from the account menu. */
export function SetupGuide() {
  const { user } = useSession();
  const { prefs, setPrefs, guideOpen, closeGuide, startTour } = usePrefs();
  const router = useRouter();
  const pathname = usePathname();
  const [step, setStep] = useState(0);
  const [types, setTypes] = useState<string[]>([]);
  const [minTicket, setMinTicket] = useState<number | null>(null);
  const [alerts, setAlerts] = useState<Alerts>("daily");
  const [available, setAvailable] = useState<string[]>([]);
  const [today, setToday] = useState<CallItem[] | null>(null);
  const [book, setBook] = useState<{ names: string[]; file: string } | null>(null);
  const [bookState, setBookState] = useState<"idle" | "saving" | "saved" | "error">("idle");
  const [bookError, setBookError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [drag, setDrag] = useState(false);
  const fileInput = useRef<HTMLInputElement>(null);

  const prefsRef = useRef(prefs);
  useEffect(() => {
    prefsRef.current = prefs;
  }, [prefs]);

  // Start from what is stored each time the guide opens (not on every save while it is open).
  useEffect(() => {
    if (!guideOpen) return;
    const t = setTimeout(() => {
      const p = prefsRef.current;
      setStep(0);
      setTypes(p?.event_types ?? []);
      setMinTicket(p?.min_ticket_cr ?? null);
      setAlerts(p?.alerts ?? "daily");
      setBook(null);
      setBookState(p?.book_count ? "saved" : "idle");
    }, 0);
    Promise.all([api.events(), api.today()])
      .then(([ev, td]) => {
        const kinds = [...new Set(ev.events.map((e) => e.type))].filter((k) => TYPE_COPY[k]);
        setAvailable(kinds.length ? kinds : ["ipo", "buyback"]);
        setToday(td.items);
      })
      .catch(() => setAvailable(["ipo", "buyback"]));
    return () => clearTimeout(t);
  }, [guideOpen]);

  const draft: Preferences = useMemo(
    () => ({ onboarded: false, event_types: types, min_ticket_cr: minTicket, alerts, book_count: prefs?.book_count ?? 0 }),
    [types, minTicket, alerts, prefs?.book_count],
  );
  const matching = today ? today.filter((i) => fitsCoverage(i, draft)).length : null;
  const bookKeys = useMemo(() => new Set((book?.names ?? []).map((n) => n.toLowerCase().replace(/^(mr|mrs|ms|dr|shri|smt)\.?\s+/i, "").replace(/\s+/g, " ").trim())), [book]);
  const onList = today && book ? today.filter((i) => bookKeys.has(i.person.name.toLowerCase().replace(/^(mr|mrs|ms|dr|shri|smt)\.?\s+/i, "").replace(/\s+/g, " ").trim())).length : null;

  async function save(patch: Partial<Omit<Preferences, "book_count">>) {
    setSaving(true);
    try {
      setPrefs(await prefsApi.save(patch));
      return true;
    } catch {
      toast.error("Could not save that. Check the data service and try again.");
      return false;
    } finally {
      setSaving(false);
    }
  }

  async function finish(withTour: boolean) {
    const ok = await save({ event_types: types, min_ticket_cr: minTicket, alerts, onboarded: true });
    if (!ok) return;
    closeGuide();
    if (withTour) {
      if (pathname !== "/") router.push("/");
      setTimeout(startTour, 350);
    } else toast.success("You're set up. Reopen the guide any time from your account menu.");
  }

  async function skip() {
    closeGuide();
    if (prefs && !prefs.onboarded) {
      try {
        setPrefs(await prefsApi.save({ onboarded: true }));
      } catch {}
      toast("Setup skipped. You can open it again from your account menu.");
    }
  }

  async function readFile(file: File) {
    setBookError(null);
    if (!/\.(csv|txt)$/i.test(file.name) && file.type && !file.type.includes("csv") && !file.type.includes("text")) {
      setBookError("That doesn't look like a CSV file. Export your client list as CSV and try again.");
      return;
    }
    const names = namesFromCsv(await file.text());
    if (!names.length) {
      setBookError("No names found. Put one client name per row, with a column headed “name”.");
      return;
    }
    if (names.length > 5000) {
      setBookError(`That file has ${names.length.toLocaleString("en-IN")} names; up to 5,000 at a time, please.`);
      return;
    }
    setBook({ names, file: file.name });
    setBookState("saving");
    try {
      const { book_count } = await prefsApi.saveBook(names);
      if (prefs) setPrefs({ ...prefs, book_count });
      setBookState("saved");
    } catch {
      setBookState("error");
      setBookError("The names were read but could not be saved. Try again.");
    }
  }

  if (!user) return null;
  const S = STEPS[step];
  const last = step === STEPS.length - 1;

  return (
    <Dialog open={guideOpen} onOpenChange={(o) => (!o ? void skip() : undefined)}>
      <DialogContent
        showCloseButton={false}
        className="flex max-h-[min(92dvh,46rem)] flex-col gap-0 overflow-hidden rounded-2xl p-0 max-sm:top-auto max-sm:bottom-0 max-sm:max-w-none max-sm:translate-y-0 max-sm:rounded-b-none sm:max-w-[38rem]"
      >
        <div className="flex items-center gap-3 border-b px-6 pt-5 pb-4">
          <div className="flex flex-1 gap-1.5" aria-hidden>
            {STEPS.map((_, i) => (
              <span key={i} className={cn("h-1 flex-1 rounded-full transition-colors duration-300", i <= step ? "bg-brand" : "bg-secondary")} />
            ))}
          </div>
          <span className="tnum text-xs text-muted-foreground">
            {step + 1} of {STEPS.length}
          </span>
          <button type="button" onClick={() => void skip()} aria-label="Close the setup guide" className="-mr-2 grid size-8 place-items-center rounded-md text-muted-foreground hover:bg-muted hover:text-foreground">
            <X className="size-4" />
          </button>
        </div>

        <div className="min-h-0 flex-1 overflow-y-auto px-6 pt-6 pb-6">
          <div className="flex items-start gap-3.5">
            <span className="grid size-10 shrink-0 place-items-center rounded-xl bg-brand-soft text-brand-ink">
              <S.icon className="size-5" aria-hidden />
            </span>
            <div className="min-w-0">
              <DialogTitle className="text-xl leading-tight font-semibold tracking-[-0.015em]">
                {step === 0 ? `Welcome, ${user.name.split(" ")[0]}. ${S.title}` : S.title}
              </DialogTitle>
              <DialogDescription className="mt-1 text-sm leading-relaxed text-muted-foreground">
                {step === 0
                  ? "Your briefing and suggestions will show only the money events you work on."
                  : step === 1
                    ? "Upload your client list and anyone already in your book is marked on every list."
                    : step === 2
                      ? "Pick how you'd like to hear about new money."
                      : "Four stops, under a minute. You can replay it from your account menu."}
              </DialogDescription>
            </div>
          </div>

          {step === 0 ? (
            <div className="mt-6 space-y-6">
              <fieldset>
                <legend className="mb-2.5 text-[13px] font-semibold text-foreground">Event types</legend>
                <div className="grid gap-2">
                  {(available.length ? available : ["ipo", "buyback"]).map((k) => (
                    <Choice key={k} on={types.includes(k)} onClick={() => setTypes((t) => (t.includes(k) ? t.filter((x) => x !== k) : [...t, k]))}>
                      <span className="block text-sm font-medium text-foreground">{TYPE_COPY[k]?.label ?? k}</span>
                      <span className="block text-xs leading-snug text-muted-foreground">{TYPE_COPY[k]?.note}</span>
                    </Choice>
                  ))}
                </div>
                <p className="mt-2 text-xs text-muted-foreground">Leave all unticked to see every type.</p>
              </fieldset>
              <fieldset>
                <legend className="mb-2.5 text-[13px] font-semibold text-foreground">Smallest ticket worth a call</legend>
                <div className="flex flex-wrap gap-2" role="radiogroup">
                  {TICKETS.map((t) => (
                    <button
                      key={t ?? "any"}
                      type="button"
                      role="radio"
                      aria-checked={minTicket === t}
                      onClick={() => setMinTicket(t)}
                      className={cn(
                        "tnum h-9 rounded-full border px-4 text-[13px] font-medium transition-colors",
                        minTicket === t ? "border-brand/45 bg-brand-soft text-brand-ink" : "bg-surface text-foreground hover:border-input",
                      )}
                    >
                      {t === null ? "Any amount" : `₹${t} Cr`}
                    </button>
                  ))}
                </div>
              </fieldset>
              <p className="tnum rounded-lg bg-surface-sunken px-3.5 py-2.5 text-[13px] text-muted-foreground" aria-live="polite">
                {matching === null ? (
                  "Counting today's list…"
                ) : (
                  <>
                    <span className="font-semibold text-foreground">{matching}</span> of {today!.length} people on today&apos;s list fit this coverage.
                  </>
                )}
              </p>
            </div>
          ) : null}

          {step === 1 ? (
            <div className="mt-6 space-y-4">
              <label
                onDragOver={(e) => {
                  e.preventDefault();
                  setDrag(true);
                }}
                onDragLeave={() => setDrag(false)}
                onDrop={(e) => {
                  e.preventDefault();
                  setDrag(false);
                  const f = e.dataTransfer.files?.[0];
                  if (f) void readFile(f);
                }}
                className={cn(
                  "flex cursor-pointer flex-col items-center rounded-xl border border-dashed bg-surface-sunken/50 px-6 py-8 text-center transition-colors",
                  drag ? "border-brand bg-brand-soft/50" : "hover:border-input hover:bg-surface-sunken",
                )}
              >
                <input
                  ref={fileInput}
                  type="file"
                  accept=".csv,text/csv,text/plain"
                  className="sr-only"
                  onChange={(e) => {
                    const f = e.target.files?.[0];
                    if (f) void readFile(f);
                    e.target.value = "";
                  }}
                />
                <span className="mb-3 grid size-10 place-items-center rounded-full bg-surface text-muted-foreground ring-1 ring-border">
                  {bookState === "saving" ? <Loader2 className="size-4.5 animate-spin" /> : <FileUp className="size-4.5" />}
                </span>
                <span className="text-sm font-medium text-foreground">Drop a CSV here, or choose a file</span>
                <span className="mt-1 text-xs text-muted-foreground">One client per row. Names stay in your profile; nothing else is read.</span>
              </label>

              {bookError ? (
                <p role="alert" className="rounded-lg border border-negative/25 bg-negative-soft px-3.5 py-2.5 text-[13px] text-negative">
                  {bookError}
                </p>
              ) : null}

              {book ? (
                <div className="rounded-xl border bg-surface px-4 py-3.5 shadow-(--shadow-card)" aria-live="polite">
                  <p className="flex items-center gap-2 text-sm font-semibold text-foreground">
                    {bookState === "saved" ? <Check className="size-4 text-positive" aria-hidden /> : <Loader2 className="size-4 animate-spin text-muted-foreground" aria-hidden />}
                    <span className="tnum">{book.names.length.toLocaleString("en-IN")} names loaded</span>
                    <span className="truncate text-xs font-normal text-muted-foreground">from {book.file}</span>
                  </p>
                  {onList !== null ? (
                    <p className="tnum mt-1 text-[13px] text-muted-foreground">
                      {onList > 0 ? (
                        <>
                          <span className="font-medium text-foreground">{onList}</span> of them {onList === 1 ? "is" : "are"} on today&apos;s call list and will show <span className="font-medium text-info">In your book</span>.
                        </>
                      ) : (
                        "None of them are on today's call list yet. We'll flag them when they are."
                      )}
                    </p>
                  ) : null}
                  <div className="mt-2.5 flex flex-wrap gap-1.5">
                    {book.names.slice(0, 5).map((n) => (
                      <span key={n} className="rounded-md bg-secondary px-2 py-0.5 text-xs text-foreground">
                        {n}
                      </span>
                    ))}
                    {book.names.length > 5 ? <span className="tnum px-1 text-xs text-muted-foreground">+{book.names.length - 5} more</span> : null}
                  </div>
                </div>
              ) : prefs?.book_count ? (
                <p className="tnum flex items-center justify-between gap-3 rounded-lg bg-surface-sunken px-3.5 py-2.5 text-[13px] text-muted-foreground">
                  <span>
                    <span className="font-semibold text-foreground">{prefs.book_count.toLocaleString("en-IN")} names</span> already in your book.
                  </span>
                  <button
                    type="button"
                    className="text-xs font-medium text-negative hover:underline"
                    onClick={async () => {
                      try {
                        await prefsApi.clearBook();
                        setPrefs({ ...prefs, book_count: 0 });
                        setBookState("idle");
                      } catch {
                        toast.error("Could not clear the book. Try again.");
                      }
                    }}
                  >
                    Clear
                  </button>
                </p>
              ) : null}

              {user?.production ? null : (
                <a href="/sample_book.csv" download className="inline-flex items-center gap-1.5 text-[13px] font-medium text-brand-ink hover:underline">
                  <Download className="size-3.5" aria-hidden /> Download a sample CSV
                </a>
              )}
            </div>
          ) : null}

          {step === 2 ? (
            <div className="mt-6 grid gap-2" role="radiogroup" aria-label="Alerts">
              {ALERTS.map((a) => (
                <button
                  key={a.value}
                  type="button"
                  role="radio"
                  aria-checked={alerts === a.value}
                  onClick={() => setAlerts(a.value)}
                  className={cn(
                    "flex items-start gap-3 rounded-xl border bg-surface px-4 py-3.5 text-left transition-colors",
                    alerts === a.value ? "border-brand/45 bg-brand-soft/50" : "hover:border-input",
                  )}
                >
                  <span className={cn("mt-0.5 grid size-4.5 shrink-0 place-items-center rounded-full border", alerts === a.value ? "border-brand" : "border-input")}>
                    {alerts === a.value ? <span className="size-2.5 rounded-full bg-brand" /> : null}
                  </span>
                  <span>
                    <span className="block text-sm font-medium text-foreground">{a.label}</span>
                    <span className="block text-xs text-muted-foreground">{a.note}</span>
                  </span>
                </button>
              ))}
              <p className="mt-2 text-xs text-muted-foreground">Saved to your profile. This demo does not send email or messages yet.</p>
            </div>
          ) : null}

          {step === 3 ? (
            <ol className="mt-6 space-y-2.5">
              {[
                ["The prompt box", "Ask in plain words. Free lookups run at once."],
                ["Today", "Your ranked call list, cash in hand first."],
                ["A ₹ evidence chip", "Every amount opens the filing page it came from."],
                ["The cost check", "Anything that spends money shows its price and waits for you."],
              ].map(([t, d], i) => (
                <li key={t} className="flex items-start gap-3 rounded-xl border bg-surface px-4 py-3">
                  <span className="tnum grid size-6 shrink-0 place-items-center rounded-full bg-secondary text-xs font-semibold text-muted-foreground">{i + 1}</span>
                  <span>
                    <span className="block text-sm font-medium text-foreground">{t}</span>
                    <span className="block text-xs text-muted-foreground">{d}</span>
                  </span>
                </li>
              ))}
            </ol>
          ) : null}
        </div>

        <div className="flex items-center gap-2 border-t bg-surface-sunken/40 px-6 py-4">
          <Button variant="ghost" onClick={() => void skip()} className="text-muted-foreground">
            Skip setup
          </Button>
          <div className="ml-auto flex gap-2">
            {step > 0 ? (
              <Button variant="outline" onClick={() => setStep((s) => s - 1)} disabled={saving}>
                Back
              </Button>
            ) : null}
            {last ? (
              <>
                <Button variant="outline" onClick={() => void finish(false)} disabled={saving} className="max-sm:hidden">
                  Finish
                </Button>
                <Button onClick={() => void finish(true)} disabled={saving} className="bg-brand text-brand-foreground hover:bg-brand/90">
                  {saving ? <Loader2 className="animate-spin" /> : null} Start the tour
                </Button>
              </>
            ) : (
              <Button
                onClick={async () => {
                  if (step === 0 && !(await save({ event_types: types, min_ticket_cr: minTicket }))) return;
                  if (step === 2 && !(await save({ alerts }))) return;
                  setStep((s) => s + 1);
                }}
                disabled={saving || bookState === "saving"}
                className="bg-brand text-brand-foreground hover:bg-brand/90"
              >
                {saving ? <Loader2 className="animate-spin" /> : null}
                {step === 1 && !book && !prefs?.book_count ? "Skip for now" : "Continue"}
              </Button>
            )}
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}
