"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { usePathname, useRouter } from "next/navigation";
import { Loader2, Play } from "lucide-react";
import { toast } from "sonner";
import { PageHeader } from "@/components/ds";
import { Button } from "@/components/ui/button";
import { ApiError } from "@/lib/api";
import { useSession } from "@/lib/session";
import { FollowButton } from "@/components/watch/follow-button";
import { eventsApi } from "./api";
import { ProcessPanel } from "./process-panel";
import { displayStatus, StatusChip } from "./status";
import type { EventDetail } from "./types";
import { useJob } from "./use-job";

/**
 * Event page header with "Process now" and the live progress panel. `process` (from ?process=1)
 * starts a run on arrival; `job` (from ?job=…) attaches to one already started (add-from-links).
 * When the run ends the server-rendered call list below is refreshed in place.
 */
export function EventLive({
  event,
  process,
  job,
  children,
}: {
  event: EventDetail;
  process?: boolean;
  job?: string | null;
  children: React.ReactNode;
}) {
  const router = useRouter();
  const pathname = usePathname();
  const [jobId, setJobId] = useState<string | null>(job ?? null);
  const [starting, setStarting] = useState(false);
  const [dismissed, setDismissed] = useState(false);
  const view = useJob(jobId);
  const refreshed = useRef<string | null>(null);
  const autoStarted = useRef(!!job);
  // Re-reading a scanned or unsupported filing cannot help, so no button there.
  const { can } = useSession();
  const supported = can("process") && event.status !== "not_supported" && event.status !== "scanned";
  const running = starting || view?.state === "running";

  const start = useCallback(async () => {
    setStarting(true);
    setDismissed(false);
    try {
      const j = await eventsApi.run(event.id);
      refreshed.current = null;
      setJobId(j.job_id);
    } catch (e) {
      toast.error("Could not start processing", { description: e instanceof ApiError ? e.message : "Please try again." });
    } finally {
      setStarting(false);
    }
  }, [event.id]);

  // Clean ?process / ?job from the URL once read, and start or re-attach.
  useEffect(() => {
    if (process || job) router.replace(pathname, { scroll: false });
    if (!(process || event.status === "processing") || job || autoStarted.current) return;
    const t = setTimeout(() => {
      autoStarted.current = true;
      void start();
    }, 0);
    return () => clearTimeout(t);
  }, [process, job, event.status, pathname, router, start]);

  // When a run ends (either way), re-read the call list.
  useEffect(() => {
    if (!jobId || !view || view.state === "running" || refreshed.current === jobId) return;
    refreshed.current = jobId;
    router.refresh();
    if (view.state === "complete") toast.success("Call list updated", { description: event.company });
  }, [jobId, view, router, event.company]);

  const status = running ? "processing" : displayStatus(event);
  const kind = event.type_label ?? event.type;
  const md = event.money_date;

  return (
    <>
      <PageHeader
        title={event.company}
        description={
          <span className="tnum">
            {kind}
            {md?.date_iso ? ` · ${md.label} ${md.display}` : ""}
            {md?.date_iso && md.relative ? <span title={md.display} className="text-faint"> ({md.relative})</span> : null}
          </span>
        }
        actions={
          <>
            <StatusChip status={status} className="max-sm:hidden" />
            <FollowButton kind="company" eventId={event.id} label="Follow company" />
            {supported ? (
              <Button onClick={start} disabled={running} size="lg" className="px-3.5">
                {running ? <Loader2 className="animate-spin" /> : <Play />}
                {running ? "Processing…" : "Process now"}
              </Button>
            ) : null}
          </>
        }
      />
      {view && !dismissed ? (
        <div className="mb-8">
          <ProcessPanel company={event.company} eventId={event.id} view={view} onDismiss={() => setDismissed(true)} onRetry={start} />
        </div>
      ) : null}
      {children}
    </>
  );
}
