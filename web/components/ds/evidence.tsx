"use client";

import { useEffect, useState } from "react";
import { ExternalLink, FileText, Highlighter, ImageOff, SearchX } from "lucide-react";
import { cn } from "@/lib/utils";
import { evidencePageUrl, resolveApiUrl } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { Skeleton } from "@/components/ui/skeleton";
import { FreshnessBadge } from "./freshness-badge";
import type { Evidence } from "@/lib/types";

export function pageLabel(e: Pick<Evidence, "printed_page" | "pdf_index">) {
  if (e.pdf_index == null) return e.printed_page ?? "exchange row";
  return e.printed_page ? `p. ${e.printed_page}` : `PDF p. ${e.pdf_index}`;
}

const SHORT: Record<string, string> = {
  "Red herring prospectus": "Prospectus",
  "Draft red herring prospectus": "Draft prospectus",
};

/** A small source link ("Prospectus · p. 16") that opens the page with the quote highlighted. */
export function EvidenceChip({
  evidence,
  imageSrc,
  highlight,
  className,
}: {
  evidence: Evidence;
  /** Override the page image (gallery fixtures). */
  imageSrc?: string;
  highlight?: boolean;
  className?: string;
}) {
  return (
    <EvidenceViewer
      evidence={evidence}
      imageSrc={imageSrc}
      highlight={highlight}
      trigger={
        <button
          type="button"
          className={cn(
            "inline-flex h-6 items-center gap-1.5 rounded-md border bg-surface px-2 text-xs font-medium text-muted-foreground transition-colors hover:border-brand/40 hover:bg-brand-soft hover:text-brand-ink",
            className,
          )}
        >
          <FileText className="size-3.5" aria-hidden />
          {SHORT[evidence.doc_label] ?? evidence.doc_label} · <span className="tnum">{pageLabel(evidence)}</span>
          {evidence.stale ? <span className="size-1.5 rounded-full bg-caution" title="Fetched a while ago: may be stale" aria-label="Stale source" /> : null}
        </button>
      }
    />
  );
}

/**
 * Dialog showing the source page image (highlight drawn by the API) next to the quote.
 * When the API cannot find the quote on the page (header X-Highlight: none) the plain page still
 * shows, with the quote beside it and a plain note. Never a blank state.
 */
export function EvidenceViewer({
  evidence,
  trigger,
  imageSrc,
  highlight,
  open,
  onOpenChange,
}: {
  evidence: Evidence;
  trigger?: React.ReactNode;
  imageSrc?: string;
  highlight?: boolean;
  open?: boolean;
  onOpenChange?: (o: boolean) => void;
}) {
  const src = imageSrc ?? evidencePageUrl(evidence);
  const pdfHref = evidence.cached === false ? (evidence.source_url ?? evidence.url) : resolveApiUrl(evidence.url);
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      {trigger ? <DialogTrigger asChild>{trigger}</DialogTrigger> : null}
      <DialogContent className="flex max-h-[92vh] w-[calc(100vw-2rem)] flex-col gap-0 overflow-hidden p-0 sm:max-w-5xl">
        <DialogHeader className="border-b px-6 py-4 text-left">
          <DialogTitle className="text-base">{evidence.doc_label}</DialogTitle>
          <DialogDescription className="tnum flex flex-wrap items-center gap-x-2 gap-y-1">
            <span>
              {evidence.pdf_index == null
                ? `Exchange row · ${evidence.printed_page ?? ""}`
                : `${evidence.printed_page ? `Printed page ${evidence.printed_page} · ` : ""}PDF page ${evidence.pdf_index}`}
            </span>
            <FreshnessBadge fetchedAt={evidence.fetched_at} ageDays={evidence.age_days} stale={evidence.stale} />
          </DialogDescription>
        </DialogHeader>
        <div className="grid min-h-0 flex-1 grid-rows-[minmax(0,1fr)_auto] md:grid-cols-[minmax(0,1fr)_20rem] md:grid-rows-1">
          <div data-evidence-scroll className="min-h-0 overflow-auto bg-surface-sunken p-4 md:p-6">
            {evidence.cached === false ? (
              <div className="mx-auto flex aspect-[1/1.414] w-full max-w-2xl flex-col items-center justify-center gap-2 rounded-md border border-dashed bg-surface p-8 text-center">
                <FileText className="size-6 text-muted-foreground" />
                <p className="text-sm font-medium">{evidence.pdf_index == null ? "This is a row on the exchange's own report" : "This filing is not stored on this machine"}</p>
                <p className="max-w-[40ch] text-xs text-muted-foreground">{evidence.pdf_index == null ? "The row is quoted here; the exchange page lists it." : "The quote is shown here; open the original filing to read the full page."}</p>
              </div>
            ) : (
              <PageImage key={src} src={src} known={imageSrc ? (highlight ?? true) : undefined} quote={evidence.quote} />
            )}
          </div>
          <aside className="flex flex-col gap-4 border-t p-6 md:border-t-0 md:border-l">
            <div>
              <h3 className="mb-2 text-xs font-medium text-muted-foreground">Quoted from the filing</h3>
              <blockquote className="rounded-lg bg-highlight/20 ring-1 ring-inset ring-highlight/40 px-3 py-2.5 text-sm leading-relaxed text-foreground">
                {evidence.quote}
              </blockquote>
            </div>
            <Button asChild variant="outline" className="mt-auto w-full justify-center">
              <a href={pdfHref} target="_blank" rel="noreferrer">
                <ExternalLink /> {evidence.pdf_index == null ? "Open the exchange page" : evidence.cached === false ? "Open the original filing" : `Open PDF at page ${evidence.pdf_index}`}
              </a>
            </Button>
          </aside>
        </div>
      </DialogContent>
    </Dialog>
  );
}

/** highlighted: true = quote marked, false = API said "none", null = not reported (no caption). */
type Loaded = { url: string; highlighted: boolean | null; y?: number } | "error" | null;

function PageImage({ src, known, quote }: { src: string; known?: boolean; quote: string }) {
  const [state, setState] = useState<Loaded>(known !== undefined ? { url: src, highlighted: known } : null);

  useEffect(() => {
    if (known !== undefined) return;
    let objectUrl: string | null = null;
    let cancelled = false;
    fetch(src)
      .then(async (res) => {
        if (!res.ok) throw new Error(String(res.status));
        const blob = await res.blob();
        objectUrl = URL.createObjectURL(blob);
        // X-Highlight: found | none. X-Highlight-Box: "x0,y0,x1,y1" as 0..1 fractions; we scroll to y0.
        const flag = res.headers.get("X-Highlight");
        const y = Number((res.headers.get("X-Highlight-Box") ?? "").split(",")[1]);
        if (!cancelled)
          setState({
            url: objectUrl,
            highlighted: flag === "none" ? false : flag ? true : null,
            y: Number.isFinite(y) && y > 0 ? y : undefined,
          });
      })
      .catch(() => {
        if (!cancelled) setState("error");
      });
    return () => {
      cancelled = true;
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [src, known]);

  if (state === null) {
    return (
      <div role="status" className="relative mx-auto aspect-[1/1.414] w-full max-w-2xl">
        <Skeleton className="size-full rounded-md" />
        <p className="absolute inset-0 flex items-center justify-center text-sm font-medium text-muted-foreground">
          Loading the filing page. The first view can take a few seconds.
        </p>
      </div>
    );
  }
  if (state === "error") {
    return (
      <div className="mx-auto flex aspect-[1/1.414] w-full max-w-2xl flex-col items-center justify-center gap-2 rounded-md border border-dashed bg-surface p-8 text-center">
        <ImageOff className="size-6 text-muted-foreground" />
        <p className="text-sm font-medium">The page image could not be loaded</p>
        <p className="max-w-[40ch] text-xs text-muted-foreground">The quote is shown on the right. Open the PDF to read the full page.</p>
      </div>
    );
  }
  return (
    <figure className="mx-auto w-full max-w-2xl">
      {state.highlighted !== null ? (
        <figcaption
          className={cn(
            "mb-3 inline-flex items-center gap-1.5 rounded-md px-2 py-1 text-xs font-medium",
            state.highlighted ? "bg-highlight/25 text-foreground" : "bg-secondary text-muted-foreground",
          )}
        >
          {state.highlighted ? <Highlighter className="size-3.5" /> : <SearchX className="size-3.5" />}
          {state.highlighted ? "Quote highlighted on the page" : "The exact quote could not be marked on this page image. The quoted text is shown alongside."}
        </figcaption>
      ) : null}
      {/* eslint-disable-next-line @next/next/no-img-element -- dynamic API image / object URL */}
      <img src={state.url} alt={`Source page containing: ${quote}`} className="w-full rounded-md bg-white shadow-(--shadow-raised) ring-1 ring-black/5"
        onLoad={(e) => {
          if (!state.y) return;
          const img = e.currentTarget;
          const scroller = img.closest("[data-evidence-scroll]");
          if (!scroller) return;
          const imgTop = img.getBoundingClientRect().top - scroller.getBoundingClientRect().top + scroller.scrollTop;
          scroller.scrollTo({ top: Math.max(0, imgTop + state.y * img.height - 140), behavior: "smooth" });
        }}
      />
    </figure>
  );
}
