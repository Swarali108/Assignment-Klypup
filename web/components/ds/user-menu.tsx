"use client";

import { Compass, Keyboard, LogOut, Newspaper, Presentation, SlidersHorizontal } from "lucide-react";
import { useBrief } from "@/components/brief/brief-provider";
import { useUi } from "@/lib/ui";
import { usePrefs } from "@/lib/prefs";
import { Avatar } from "./avatar";
import { ROLE_LABEL, useSession } from "@/lib/session";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuLabel, DropdownMenuSeparator, DropdownMenuTrigger } from "@/components/ui/dropdown-menu";

/** Name, role and sign out. Shows nothing until the session is known. */
export function UserMenu() {
  const { user, signOut } = useSession();
  const { openGuide, startTour, prefs } = usePrefs();
  const { openBrief } = useBrief();
  const { boardroom, toggleBoardroom, setShortcutsOpen } = useUi();
  if (!user) return <span className="size-9" aria-hidden />;
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <button
          type="button"
          aria-label={`Account menu for ${user.name}`}
          className="flex h-10 items-center gap-2.5 rounded-lg px-1.5 text-left outline-none transition-colors hover:bg-muted focus-visible:ring-3 focus-visible:ring-ring/50"
        >
          <Avatar name={user.name} size="sm" />
          <span className="hidden min-w-0 flex-col leading-tight md:flex">
            <span className="truncate text-[13px] font-medium text-foreground">{user.name}</span>
            <span className="truncate text-[11px] text-muted-foreground">{ROLE_LABEL[user.role]}</span>
          </span>
        </button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="w-60">
        <DropdownMenuLabel className="flex flex-col gap-0.5 py-2">
          <span className="text-sm font-medium text-foreground">{user.name}</span>
          <span className="text-xs font-normal text-muted-foreground">{user.email}</span>
          <span className="mt-1 text-xs font-normal text-brand-ink">{ROLE_LABEL[user.role]}</span>
        </DropdownMenuLabel>
        <DropdownMenuSeparator />
        <DropdownMenuItem onSelect={openBrief}>
          <Newspaper /> Today’s brief
        </DropdownMenuItem>
        <DropdownMenuItem onSelect={toggleBoardroom}>
          <Presentation /> Boardroom mode
          <span className="ml-auto text-xs text-muted-foreground">{boardroom ? "On" : "Off"}</span>
        </DropdownMenuItem>
        <DropdownMenuItem onSelect={() => setShortcutsOpen(true)}>
          <Keyboard /> Keyboard shortcuts
          <kbd className="ml-auto rounded border bg-secondary px-1.5 font-sans text-[11px] text-muted-foreground">?</kbd>
        </DropdownMenuItem>
        <DropdownMenuSeparator />
        <DropdownMenuItem onSelect={openGuide}>
          <SlidersHorizontal /> Setup guide
          {prefs && prefs.book_count > 0 ? <span className="tnum ml-auto text-xs text-muted-foreground">{prefs.book_count} in book</span> : null}
        </DropdownMenuItem>
        <DropdownMenuItem onSelect={startTour}>
          <Compass /> Product tour
        </DropdownMenuItem>
        <DropdownMenuSeparator />
        <DropdownMenuItem onSelect={() => void signOut()}>
          <LogOut /> Sign out
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
