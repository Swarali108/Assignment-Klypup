"use client";

import Link from "next/link";
import { useState } from "react";
import { useRouter } from "next/navigation";
import { ArrowLeft, CheckCircle2, CircleAlert, FileSearch, Info, Link2, Loader2, Play, Plus } from "lucide-react";
import { cn } from "@/lib/utils";
import { ApiError } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { Textarea } from "@/components/ui/textarea";
import { DOC_TYPE_LABEL, EVENT_KIND_LABEL, eventsApi, makeEventId, tidyCompany } from "./api";
import type { Proposal, ProposalsResponse } from "./types";

/** A filing link whose document is already on this machine, for a quick try. */
const SAMPLE_LINK = "https://vectrasgroup.com/wp-content/uploads/2026/11/Prospectus_VEL_2026_Clean.pdf";
const SUPPORTED_TYPES = ["ipo", "buyback", "ofs_stock_exchange"] as const;

type Step = "links" | "reading" | "review";

function parseLinks(text: string): string[] {
  return Array.from(new Set(text.split(/[\s,]+/).map((s) => s.trim()).filter((s) => /^https?:\/\//i.test(s)))).slice(0, 6);
}

function shortUrl(url: string): { host: string; file: string } {
  try {
    const u = new URL(url);
    const file = decodeURIComponent(u.pathname.split("/").filter(Boolean).pop() ?? u.pathname);
    return { host: u.hostname.replace(/^www\./, ""), file };
  } catch {
    return { host: url, file: "" };
  }
}

function ProposalCard({ p }: { p: Proposal }) {
  const { host, file } = shortUrl(p.url);
  const docLabel = p.doc_type ? (DOC_TYPE_LABEL[p.doc_type] ?? p.label ?? p.doc_type) : null;
  return (
    <li className={cn("rounded-lg border bg-surface p-3.5", p.error && "border-negative/25 bg-negative-soft/30")}>
      <div className="flex items-start gap-3">
        <span className={cn("mt-0.5 grid size-7 shrink-0 place-items-center rounded-md", p.error ? "bg-negative-soft text-negative" : "bg-brand-soft text-brand-ink")}>
          {p.error ? <CircleAlert className="size-4" /> : <CheckCircle2 className="size-4" />}
        </span>
        <div className="min-w-0 flex-1">
          <p className="truncate text-sm font-medium text-foreground" title={p.url}>
            {file || host}
          </p>
          <p className="truncate text-xs text-muted-foreground">{host}</p>
          {p.error ? (
            <p className="mt-2 text-[13px] leading-snug text-negative">This link could not be used: {p.error}.</p>
          ) : (
            <>
              <p className="mt-2 flex flex-wrap items-center gap-1.5 text-[13px] text-foreground">
                {docLabel ? <span className="rounded-md bg-secondary px-1.5 py-0.5 text-xs font-medium">{docLabel}</span> : null}
                {p.event_type ? <span className="rounded-md bg-secondary px-1.5 py-0.5 text-xs font-medium">{EVENT_KIND_LABEL[p.event_type] ?? p.event_type}</span> : null}
                {p.company ? <span className="text-xs text-muted-foreground">for {tidyCompany(p.company)}</span> : null}
              </p>
              {p.type_quote ? (
                <blockquote className="mt-2 line-clamp-2 rounded-md bg-highlight/15 px-2.5 py-1.5 text-xs leading-relaxed text-muted-foreground ring-1 ring-inset ring-highlight/30">
                  Read from the first page: “{p.type_quote}”
                </blockquote>
              ) : null}
            </>
          )}
        </div>
      </div>
    </li>
  );
}

/**
 * "Add event from links": paste filing links → we read the first pages and say what each is →
 * confirm company and event type → create the event and start processing it live.
 */
export function AddEventDialog({
  asOf,
  defaultOpen = false,
  initial,
  trigger,
}: {
  asOf: string;
  defaultOpen?: boolean;
  /** Pre-filled proposals (design gallery). */
  initial?: { links: string; result: ProposalsResponse };
  trigger?: React.ReactNode;
}) {
  const router = useRouter();
  const [open, setOpen] = useState(defaultOpen);
  const [step, setStep] = useState<Step>(initial ? "review" : "links");
  const [text, setText] = useState(initial?.links ?? "");
  const [result, setResult] = useState<ProposalsResponse | null>(initial?.result ?? null);
  const [company, setCompany] = useState(tidyCompany(initial?.result.suggested.company));
  const [type, setType] = useState(initial?.result.suggested.event_type ?? "ipo");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const links = parseLinks(text);
  const usable = (result?.proposals ?? []).filter((p) => !p.error);
  const existing = result?.existing_event_id ?? null;

  function reset() {
    setStep("links");
    setResult(null);
    setError(null);
    setBusy(false);
  }

  async function read() {
    if (!links.length) {
      setError("Paste at least one link that starts with https://");
      return;
    }
    setError(null);
    setStep("reading");
    try {
      const r = await eventsApi.fromLinks(links);
      setResult(r);
      setCompany(tidyCompany(r.suggested.company));
      setType(r.suggested.event_type && (SUPPORTED_TYPES as readonly string[]).includes(r.suggested.event_type) ? r.suggested.event_type : "ipo");
      setStep("review");
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "The links could not be read. Please try again.");
      setStep("links");
    }
  }

  async function createAndRun() {
    if (!company.trim()) {
      setError("Enter the company name.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const id = makeEventId(company, type, asOf);
      await eventsApi.create({
        event_id: id,
        event_type: type,
        company: company.trim(),
        documents: usable.map((p) => ({ url: p.url, doc_type: p.doc_type ?? "announcement" })),
      });
      const job = await eventsApi.run(id);
      setOpen(false);
      router.push(`/events/${encodeURIComponent(id)}?job=${encodeURIComponent(job.job_id)}`);
    } catch (e) {
      const msg = e instanceof ApiError ? (e.status === 409 ? "An event for this company and month is already in the list. Open it from the events list." : e.message) : "Could not create the event.";
      setError(msg);
      setBusy(false);
    }
  }

  return (
    <Dialog
      open={open}
      onOpenChange={(o) => {
        setOpen(o);
        if (!o && !initial) setTimeout(reset, 200);
      }}
    >
      <DialogTrigger asChild>
        {trigger ?? (
          <Button size="lg" className="px-3.5">
            <Plus /> Add event from links
          </Button>
        )}
      </DialogTrigger>
      <DialogContent className="gap-0 p-0 sm:max-w-xl">
        <DialogHeader className="border-b px-6 py-5 text-left">
          <DialogTitle className="text-base">{step === "review" ? "Check what we found" : "Add an event from links"}</DialogTitle>
          <DialogDescription>
            {step === "review"
              ? "We read the first pages of each filing. Confirm the company and the kind of event, then we build the call list."
              : "Paste links to the filings: a prospectus, a buyback letter of offer or public announcement, or an exchange notice."}
          </DialogDescription>
        </DialogHeader>

        <div className="max-h-[60vh] overflow-y-auto px-6 py-5">
          {step === "links" ? (
            <div className="space-y-2">
              <Label htmlFor="links" className="text-[13px]">
                Filing links <span className="font-normal text-muted-foreground">(one per line, up to 6)</span>
              </Label>
              <Textarea
                id="links"
                value={text}
                onChange={(e) => setText(e.target.value)}
                placeholder="https://…/prospectus.pdf"
                rows={5}
                className="tnum resize-none font-normal text-[13px]"
                aria-invalid={!!error}
              />
              <div className="flex flex-wrap items-center justify-between gap-2 text-xs text-muted-foreground">
                <span className="tnum">{links.length ? `${links.length} link${links.length === 1 ? "" : "s"} ready to read` : "PDF links from SEBI, the exchanges or the company work best"}</span>
                <button type="button" onClick={() => setText(SAMPLE_LINK)} className="inline-flex items-center gap-1 font-medium text-brand-ink underline-offset-4 hover:underline">
                  <Link2 className="size-3.5" /> Use a sample link
                </button>
              </div>
            </div>
          ) : step === "reading" ? (
            <div role="status" className="space-y-4">
              <p className="flex items-center gap-2 text-sm text-muted-foreground">
                <Loader2 className="size-4 animate-spin text-info" /> Reading the first pages of {links.length === 1 ? "the filing" : `${links.length} filings`}…
              </p>
              {links.map((l) => (
                <div key={l} className="flex items-start gap-3 rounded-lg border p-3.5">
                  <Skeleton className="size-7 rounded-md" />
                  <div className="flex-1 space-y-2">
                    <Skeleton className="h-3.5 w-2/3" />
                    <Skeleton className="h-3 w-1/3" />
                    <Skeleton className="h-6 w-full" />
                  </div>
                </div>
              ))}
            </div>
          ) : result ? (
            <div className="space-y-5">
              <ul className="space-y-2.5">
                {result.proposals.map((p) => (
                  <ProposalCard key={p.url} p={p} />
                ))}
              </ul>

              {existing ? (
                <div className="flex items-start gap-3 rounded-lg border border-info/20 bg-info-soft/60 p-3.5">
                  <Info className="mt-0.5 size-4 shrink-0 text-info" />
                  <div className="min-w-0 flex-1">
                    <p className="text-sm font-medium text-foreground">This event is already in your list</p>
                    <p className="mt-0.5 text-[13px] text-muted-foreground">Open it, or process it again to rebuild its call list live.</p>
                    <div className="mt-3 flex flex-wrap gap-2">
                      <Button asChild size="sm">
                        <Link href={`/events/${encodeURIComponent(existing)}?process=1`} onClick={() => setOpen(false)}>
                          <Play /> Process now
                        </Link>
                      </Button>
                      <Button asChild size="sm" variant="outline">
                        <Link href={`/events/${encodeURIComponent(existing)}`} onClick={() => setOpen(false)}>
                          Open event
                        </Link>
                      </Button>
                    </div>
                  </div>
                </div>
              ) : usable.length ? (
                <div className="grid gap-4 sm:grid-cols-[minmax(0,1fr)_12rem]">
                  <div className="space-y-1.5">
                    <Label htmlFor="company" className="text-[13px]">
                      Company
                    </Label>
                    <Input id="company" value={company} onChange={(e) => setCompany(e.target.value)} />
                  </div>
                  <div className="space-y-1.5">
                    <Label className="text-[13px]">Kind of event</Label>
                    <Select value={type} onValueChange={setType}>
                      <SelectTrigger className="w-full">
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        {SUPPORTED_TYPES.map((t) => (
                          <SelectItem key={t} value={t}>
                            {EVENT_KIND_LABEL[t]}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </div>
                </div>
              ) : (
                <div className="flex items-start gap-3 rounded-lg border border-dashed p-3.5 text-[13px] text-muted-foreground">
                  <FileSearch className="mt-0.5 size-4 shrink-0" />
                  None of these links could be read as a filing. Go back and try a direct PDF link.
                </div>
              )}
            </div>
          ) : null}
          {error ? (
            <p role="alert" className="mt-3 flex items-start gap-1.5 text-[13px] text-negative">
              <CircleAlert className="mt-0.5 size-3.5 shrink-0" /> {error}
            </p>
          ) : null}
        </div>

        <div className="flex items-center justify-between gap-2 rounded-b-xl border-t bg-surface-sunken/50 px-6 py-4">
          {step === "review" ? (
            <Button variant="ghost" onClick={reset} disabled={busy}>
              <ArrowLeft /> Change links
            </Button>
          ) : (
            <span className="text-xs text-muted-foreground">Nothing is saved until you confirm.</span>
          )}
          {step === "review" ? (
            !existing && usable.length ? (
              <Button onClick={createAndRun} disabled={busy} size="lg" className="px-3.5">
                {busy ? <Loader2 className="animate-spin" /> : <Play />} Create and process
              </Button>
            ) : null
          ) : (
            <Button onClick={read} disabled={step === "reading" || !links.length} size="lg" className="px-3.5">
              {step === "reading" ? <Loader2 className="animate-spin" /> : <FileSearch />} Read links
            </Button>
          )}
        </div>
      </DialogContent>
    </Dialog>
  );
}
