"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { ArrowRight, Copy, MessageSquare, PhoneCall, RotateCw } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogTitle } from "@/components/ui/dialog";
import { useChat } from "@/components/tower/chat-store";
import { briefCost, PREFILL_EVENT, PREFILL_KEY } from "@/lib/brief";
import { dayLabel, greetingFor } from "@/lib/market";
import { useSession } from "@/lib/session";
import { useBrief } from "./brief-provider";

/** The brief as plain text for an email: subject line, greeting, one dash per bullet, a closing line. */
function emailText(greeting: string, first: string, label: string, bullets: string[]) {
  return [
    `Subject: Your FinSight brief, ${label}`,
    "",
    `${greeting}, ${first},`,
    "",
    ...bullets.map((b) => `- ${b}`),
    "",
    "Numbers are from the filings.",
  ].join("\n");
}

/** Full-screen, calm sheet: the day's three to five lines, what to do next, who wrote it. */
export function BriefSheet() {
  const { brief, open, loading, failed, closeBrief, rewrite } = useBrief();
  const { user } = useSession();
  const { newChat } = useChat();
  const router = useRouter();
  const [now] = useState(() => new Date());
  const first = user?.name.split(" ")[0] ?? "";
  const greeting = greetingFor(now.getHours());
  const label = dayLabel(now);

  const copy = async () => {
    if (!brief) return;
    try {
      await navigator.clipboard.writeText(emailText(greeting, first, label, brief.bullets.map((b) => b.text)));
      toast.success("Brief copied. Paste it into an email.");
    } catch {
      toast.error("Could not copy. Select the text and copy it instead.");
    }
  };

  const ask = () => {
    if (!brief) return;
    try {
      window.sessionStorage.setItem(PREFILL_KEY, brief.ask_prompt);
    } catch {
      /* the composer simply opens empty */
    }
    newChat();
    closeBrief();
    router.push("/");
    window.dispatchEvent(new Event(PREFILL_EVENT));
  };

  return (
    <Dialog open={open} onOpenChange={(o) => (o ? null : closeBrief())}>
      <DialogContent
        showCloseButton
        className="top-0 left-0 flex h-dvh max-h-dvh w-full max-w-none translate-x-0 translate-y-0 flex-col items-center justify-center overflow-y-auto rounded-none bg-background p-6 ring-0 sm:max-w-none"
      >
        <div className="w-full max-w-[40rem] py-8">
          <DialogTitle className="text-[1.75rem] leading-tight font-semibold tracking-[-0.025em] text-balance text-foreground sm:text-[2.25rem]">
            {greeting}, {first || "there"}
            <span className="font-normal text-muted-foreground"> — your brief for {label}</span>
          </DialogTitle>
          <DialogDescription className="mt-3 text-[15px] text-muted-foreground">
            What changed, who to call, and what is coming, in under a minute.
          </DialogDescription>

          {brief ? (
            brief.bullets.length ? (
              <ol className="mt-8 divide-y divide-hairline overflow-hidden rounded-2xl border bg-surface shadow-(--shadow-card)">
                {brief.bullets.map((b) => (
                  <li key={b.topic}>
                    <Link
                      href={b.link}
                      onClick={closeBrief}
                      className="group flex items-start gap-3 px-5 py-4 text-[15px] leading-relaxed text-foreground transition-colors hover:bg-accent/50"
                    >
                      <span className="mt-2.5 size-1.5 shrink-0 rounded-full bg-brand" aria-hidden />
                      <span className="tnum min-w-0 flex-1 text-pretty">{b.text}</span>
                      <ArrowRight className="mt-1 size-4 shrink-0 text-faint opacity-0 transition-opacity group-hover:opacity-100" aria-hidden />
                    </Link>
                  </li>
                ))}
              </ol>
            ) : (
              <p className="mt-8 rounded-2xl border border-dashed px-5 py-6 text-[15px] text-muted-foreground">Nothing new to report yet. Check back after the next filings are read.</p>
            )
          ) : failed ? (
            <p className="mt-8 rounded-2xl border border-dashed px-5 py-6 text-[15px] text-muted-foreground">Today’s brief could not be loaded.</p>
          ) : (
            <div className="mt-8 space-y-3" role="status" aria-label="Writing your brief">
              {[92, 78, 85].map((w) => (
                <div key={w} className="h-14 animate-pulse rounded-xl bg-surface-sunken" style={{ width: `${w}%` }} />
              ))}
            </div>
          )}

          <div className="mt-8 flex flex-wrap items-center gap-2.5">
            <Button asChild size="lg" onClick={closeBrief}>
              <Link href="/today">
                <PhoneCall /> Start calling
              </Link>
            </Button>
            <Button size="lg" variant="outline" className="bg-surface shadow-(--shadow-card)" onClick={ask} disabled={!brief}>
              <MessageSquare /> Ask about this
            </Button>
            <Button size="lg" variant="ghost" className="text-muted-foreground" onClick={() => void copy()} disabled={!brief?.bullets.length}>
              <Copy /> Copy as email
            </Button>
          </div>

          <p className="tnum mt-8 text-xs text-faint">
            <span data-tech>
              {brief?.model ? `Written by ${brief.written_by}` : "Written by code from the data"} · {briefCost(brief?.cost_usd ?? 0)} ·{" "}
            </span>
            numbers from the filings
            {user?.role === "admin" ? (
              <button type="button" onClick={rewrite} disabled={loading} data-tech className="ml-3 inline-flex items-center gap-1 text-muted-foreground hover:text-foreground hover:underline disabled:opacity-50">
                <RotateCw className="size-3" aria-hidden /> Rewrite
              </button>
            ) : null}
          </p>
        </div>
      </DialogContent>
    </Dialog>
  );
}
