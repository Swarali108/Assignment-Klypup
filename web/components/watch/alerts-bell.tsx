"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { Bell, BellRing, CalendarClock, CheckCheck, Handshake, Plus, TrendingUp } from "lucide-react";
import { cn } from "@/lib/utils";
import { v3, type Alert } from "@/lib/v3";
import { formatDate } from "@/lib/format";
import { useSession } from "@/lib/session";
import { Button } from "@/components/ui/button";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";

const ICON: Record<Alert["kind"], typeof Bell> = { new: Plus, lockin: CalendarClock, block: Handshake, amount: TrendingUp };

/** The bell in the top bar: unread count, and the alerts worked out from what this user follows. */
export function AlertsBell() {
  const { user } = useSession();
  const [data, setData] = useState<{ unread: number; items: Alert[] } | null>(null);
  const [failed, setFailed] = useState(false);
  const [open, setOpen] = useState(false);

  const load = useCallback(() => {
    v3.alerts()
      .then((d) => {
        setData(d);
        setFailed(false);
      })
      .catch(() => setFailed(true));
  }, []);

  useEffect(() => {
    if (!user) return;
    load();
    const again = () => load();
    window.addEventListener("finsight:alerts-refresh", again);
    const timer = window.setInterval(load, 5 * 60 * 1000);
    return () => {
      window.removeEventListener("finsight:alerts-refresh", again);
      window.clearInterval(timer);
    };
  }, [user, load]);

  if (!user) return null;
  const unread = data?.unread ?? 0;
  const read = async (ids: string[] | null) => {
    await v3.markRead(ids).catch(() => {});
    load();
  };
  return (
    <Popover
      open={open}
      onOpenChange={(o) => {
        setOpen(o);
        if (o) load();
      }}
    >
      <PopoverTrigger asChild>
        <Button variant="ghost" size="icon" className="relative" aria-label={unread ? `Alerts, ${unread} unread` : "Alerts"}>
          {unread ? <BellRing /> : <Bell />}
          {unread ? (
            <span className="tnum absolute top-1 right-1 grid min-w-4 place-items-center rounded-full bg-brand px-1 text-[10px] leading-4 font-semibold text-primary-foreground">
              {unread > 9 ? "9+" : unread}
            </span>
          ) : null}
        </Button>
      </PopoverTrigger>
      <PopoverContent align="end" className="w-[22rem] gap-0 p-0">
        <div className="flex items-center justify-between border-b px-4 py-3">
          <h2 className="text-sm font-semibold">Alerts</h2>
          <Button size="sm" variant="ghost" disabled={!unread} onClick={() => read(null)}>
            <CheckCheck /> Mark all read
          </Button>
        </div>
        <div className="max-h-96 overflow-y-auto">
          {data === null && !failed ? (
            <div className="space-y-3 p-4" aria-hidden>
              {[0, 1, 2].map((i) => (
                <div key={i} className="h-10 animate-pulse rounded-lg bg-secondary" />
              ))}
            </div>
          ) : failed && !data ? (
            <p className="p-5 text-sm text-muted-foreground">Alerts could not be loaded. They will be checked again shortly.</p>
          ) : data && data.items.length === 0 ? (
            <div className="px-5 py-8 text-center">
              <Bell className="mx-auto mb-2 size-5 text-faint" aria-hidden />
              <p className="text-sm font-medium">Nothing new</p>
              <p className="mt-1 text-xs leading-relaxed text-muted-foreground">
                Follow a person or a company from their page. You will see new events, lock-ins ending within 30 days and amount changes here.
              </p>
            </div>
          ) : (
            <ul className="divide-y divide-hairline">
              {data?.items.map((a) => {
                const Icon = ICON[a.kind] ?? Bell;
                return (
                  <li key={a.id}>
                    <Link
                      href={a.link || "/today"}
                      onClick={() => {
                        setOpen(false);
                        if (!a.read) void read([a.id]);
                      }}
                      className={cn("flex gap-3 px-4 py-3 transition-colors hover:bg-accent/60", !a.read && "bg-brand-soft/40")}
                    >
                      <Icon className={cn("mt-0.5 size-4 shrink-0", a.read ? "text-faint" : "text-brand")} aria-hidden />
                      <span className="min-w-0">
                        <span className={cn("block text-[13px] leading-snug", a.read ? "text-muted-foreground" : "font-medium text-foreground")}>{a.title}</span>
                        <span className="mt-0.5 block text-xs leading-snug text-muted-foreground">{a.detail}</span>
                        <span className="tnum mt-1 block text-[11px] text-faint">{formatDate(a.created_at.slice(0, 10))}</span>
                      </span>
                    </Link>
                  </li>
                );
              })}
            </ul>
          )}
        </div>
      </PopoverContent>
    </Popover>
  );
}
