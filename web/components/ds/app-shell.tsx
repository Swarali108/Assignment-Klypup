"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { Menu, MessageSquare, Search, SquarePen, Trash2 } from "lucide-react";
import { cn } from "@/lib/utils";
import { api } from "@/lib/api";
import { formatDate } from "@/lib/format";
import { Button } from "@/components/ui/button";
import { Sheet, SheetContent, SheetHeader, SheetTitle, SheetTrigger } from "@/components/ui/sheet";
import { useChat } from "@/components/tower/chat-store";
import { SetupGuide } from "@/components/onboarding/setup-guide";
import { SpotlightTour } from "@/components/onboarding/spotlight-tour";
import { useCommandPalette, useNav } from "./command-palette";
import { UserMenu } from "./user-menu";
import { ThemeToggle } from "./theme-toggle";
import { AlertsBell } from "@/components/watch/alerts-bell";
import { Wordmark } from "./brand";

function isActive(pathname: string, href: string) {
  if (href === "/today") return pathname === "/today" || pathname.startsWith("/people");
  if (href === "/ops") return pathname === "/ops"; // /ops/health and /ops/accuracy are their own items
  return pathname === href || pathname.startsWith(`${href}/`);
}

function NavLinks({ onNavigate }: { onNavigate?: () => void }) {
  const pathname = usePathname();
  const nav = useNav().filter((n) => n.href !== "/");
  return (
    <nav aria-label="Main" className="flex flex-col gap-0.5">
      {nav.map((n, i) => {
        const on = isActive(pathname, n.href);
        const firstAdmin = n.admin && !nav[i - 1]?.admin;
        return (
          <div key={n.href} className="contents">
            {firstAdmin ? <h2 className="mt-5 mb-1.5 px-3 text-xs font-medium text-faint">Admin</h2> : null}
            <Link
              href={n.href}
              onClick={onNavigate}
              aria-current={on ? "page" : undefined}
              data-tour={n.href === "/today" ? "nav-today" : undefined}
              className={cn(
                "group flex h-9 items-center gap-3 rounded-lg px-3 text-sm font-medium transition-colors",
                on ? "bg-surface text-foreground shadow-(--shadow-card) ring-1 ring-border" : "text-muted-foreground hover:bg-sidebar-accent hover:text-foreground",
              )}
            >
              <n.icon className={cn("size-4", on ? "text-brand" : "text-faint group-hover:text-muted-foreground")} />
              {n.label}
            </Link>
          </div>
        );
      })}
    </nav>
  );
}

/** Recent control-tower conversations (current user only). */
function Conversations({ onNavigate }: { onNavigate?: () => void }) {
  const { conversations, conversationsError, activeId, open, remove } = useChat();
  const router = useRouter();
  const pathname = usePathname();
  return (
    <div className="mt-7 flex min-h-0 flex-1 flex-col">
      <div className="flex items-baseline justify-between px-3 pb-2">
        <h2 className="text-xs font-medium text-faint">Recent</h2>
        <Link href="/history" onClick={onNavigate} className="text-xs text-muted-foreground hover:text-foreground hover:underline">
          See all
        </Link>
      </div>
      <div className="-mx-1 min-h-0 flex-1 overflow-y-auto px-1 [scrollbar-width:thin]">
        {conversations === null ? (
          <div className="space-y-2 px-3 pt-1" aria-hidden>
            {[78, 62, 70].map((w) => (
              <div key={w} className="h-3 animate-pulse rounded bg-sidebar-accent" style={{ width: `${w}%` }} />
            ))}
          </div>
        ) : conversations.length === 0 ? (
          <p className="px-3 text-xs leading-relaxed text-muted-foreground">
            {conversationsError ? "Conversations could not be loaded." : "Your questions and answers will be kept here."}
          </p>
        ) : (
          <ul className="flex flex-col gap-px">
            {conversations.map((c) => {
              const on = pathname === "/" && c.id === activeId;
              return (
                <li key={c.id} className="group/conv relative">
                  <button
                    type="button"
                    onClick={() => {
                      void open(c.id);
                      if (pathname !== "/") router.push("/");
                      onNavigate?.();
                    }}
                    aria-current={on ? "true" : undefined}
                    className={cn(
                      "flex h-8 w-full items-center gap-2.5 rounded-lg pr-8 pl-3 text-left text-[13px] transition-colors",
                      on ? "bg-sidebar-accent font-medium text-foreground" : "text-muted-foreground hover:bg-sidebar-accent hover:text-foreground",
                    )}
                  >
                    <MessageSquare className="size-3.5 shrink-0 text-faint" aria-hidden />
                    <span className="truncate">{c.title}</span>
                  </button>
                  <button
                    type="button"
                    onClick={() => void remove(c.id)}
                    aria-label={`Delete “${c.title}”`}
                    className="absolute top-1/2 right-1 grid size-6 -translate-y-1/2 place-items-center rounded-md text-faint opacity-0 transition-opacity group-hover/conv:opacity-100 hover:bg-surface hover:text-negative focus-visible:opacity-100"
                  >
                    <Trash2 className="size-3.5" />
                  </button>
                </li>
              );
            })}
          </ul>
        )}
      </div>
    </div>
  );
}

function Rail({ onNavigate }: { onNavigate?: () => void }) {
  const { newChat } = useChat();
  const router = useRouter();
  const pathname = usePathname();
  return (
    <>
      <button
        type="button"
        onClick={() => {
          newChat();
          if (pathname !== "/") router.push("/");
          onNavigate?.();
        }}
        className={cn(
          "mb-4 flex h-10 items-center gap-3 rounded-lg border bg-surface px-3 text-sm font-medium text-foreground shadow-(--shadow-card) transition-colors hover:border-input",
          pathname === "/" && "ring-1 ring-brand/25",
        )}
      >
        <SquarePen className="size-4 text-brand" aria-hidden />
        New chat
      </button>
      <NavLinks onNavigate={onNavigate} />
      <Conversations onNavigate={onNavigate} />
    </>
  );
}

/**
 * Application frame: a ChatGPT-style left rail (new chat, pages, recent conversations; a sheet under 1024px),
 * a slim top bar with search, theme and account, and the setup guide on a first sign-in.
 * The control tower at "/" takes the whole content area; every other page sits in the 1240px column.
 */
export function AppShell({ children, asOf: asOfProp }: { children: React.ReactNode; asOf?: string }) {
  const { setOpen } = useCommandPalette();
  const pathname = usePathname();
  const { title, turns } = useChat();
  const [asOfFetched, setAsOf] = useState<string | null>(null);
  const [menuOpen, setMenuOpen] = useState(false);
  const asOf = asOfProp ?? asOfFetched;

  // Login and the print routes (/history/[id]/print, /people/[e]/[p]/print) draw no app chrome.
  const bare = pathname.startsWith("/login") || pathname.startsWith("/weekly") || /\/print\/?$/.test(pathname);
  const tower = pathname === "/";

  useEffect(() => {
    if (asOfProp || bare) return;
    api
      .summary()
      .then((s) => setAsOf(s.as_of))
      .catch(() => setAsOf(null));
  }, [asOfProp, bare]);

  if (bare) return <>{children}</>;

  return (
    <div className="flex min-h-dvh w-full">
      <aside className="hidden w-64 shrink-0 border-r bg-sidebar lg:block">
        <div className="sticky top-0 flex h-dvh flex-col px-3 pt-5 pb-4">
          <Link href="/" className="mb-6 px-2" aria-label="AURELIA control tower">
            <Wordmark />
          </Link>
          <Rail />
          <p className="mt-3 border-t px-3 pt-3 text-[11px] leading-relaxed text-faint">Every amount links to the page of the filing it came from.</p>
        </div>
      </aside>

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="sticky top-0 z-30 flex h-14 items-center gap-3 border-b bg-background px-4 sm:px-6 lg:px-8">
          <Sheet open={menuOpen} onOpenChange={setMenuOpen}>
            <SheetTrigger asChild>
              <Button variant="ghost" size="icon" className="lg:hidden" aria-label="Open navigation" data-tour="menu">
                <Menu />
              </Button>
            </SheetTrigger>
            <SheetContent side="left" className="flex w-76 flex-col bg-sidebar p-4">
              <SheetHeader className="mb-2 p-0">
                <SheetTitle asChild>
                  <div>
                    <Wordmark />
                  </div>
                </SheetTitle>
              </SheetHeader>
              <Rail onNavigate={() => setMenuOpen(false)} />
            </SheetContent>
          </Sheet>
          <Link href="/" className="lg:hidden" aria-label="AURELIA control tower">
            <span className="text-[13px] font-semibold tracking-[0.2em]">AURELIA</span>
          </Link>

          {tower ? (
            <p className="min-w-0 truncate text-sm font-medium text-foreground max-lg:hidden">{turns.length ? (title ?? "New conversation") : "Control tower"}</p>
          ) : (
            <button
              type="button"
              onClick={() => setOpen(true)}
              className="ml-auto flex h-9 w-full max-w-md items-center gap-2.5 rounded-lg border bg-surface px-3 text-sm text-muted-foreground shadow-(--shadow-card) transition-colors hover:border-input hover:text-foreground max-sm:w-9 max-sm:justify-center max-sm:px-0 lg:ml-0"
              aria-label="Search or ask a question"
            >
              <Search className="size-4 shrink-0" />
              <span className="truncate max-sm:hidden">Search people, companies, or ask a question</span>
              <kbd className="ml-auto hidden rounded border bg-secondary px-1.5 font-sans text-[11px] font-medium text-muted-foreground sm:inline">⌘K</kbd>
            </button>
          )}

          <div className="ml-auto flex items-center gap-3">
            {asOf ? (
              <span className="tnum hidden whitespace-nowrap text-xs text-muted-foreground md:inline">
                Data as of <span className="font-medium text-foreground">{formatDate(asOf)}</span>
              </span>
            ) : null}
            <AlertsBell />
            <ThemeToggle />
            <UserMenu />
          </div>
        </header>

        {tower ? (
          <main id="main" data-tower className="flex min-h-0 flex-1 flex-col">
            {children}
          </main>
        ) : (
          <main id="main" className="mx-auto w-full max-w-[1240px] flex-1 px-4 pt-8 pb-16 sm:px-6 lg:px-10 lg:pt-10">
            {children}
          </main>
        )}
      </div>
      <SetupGuide />
      <SpotlightTour />
    </div>
  );
}
