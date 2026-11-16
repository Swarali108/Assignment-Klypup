"use client";

import { ThemeProvider } from "next-themes";
import { Toaster } from "@/components/ui/sonner";
import { TooltipProvider } from "@/components/ui/tooltip";
import { SessionProvider } from "@/lib/session";
import { PrefsProvider } from "@/lib/prefs";
import { ChatProvider } from "@/components/tower/chat-store";
import { BriefProvider } from "@/components/brief/brief-provider";
import { UiProvider } from "@/lib/ui";
import { CommandPaletteProvider } from "./command-palette";
import { NavProgress } from "./nav-progress";
import { Shortcuts } from "./shortcuts";

export function Providers({ children }: { children: React.ReactNode }) {
  return (
    <ThemeProvider attribute="class" defaultTheme="light" enableSystem={false} disableTransitionOnChange>
      <TooltipProvider delayDuration={250}>
        <UiProvider>
        <SessionProvider>
          <PrefsProvider>
            <ChatProvider>
              <BriefProvider>
              <CommandPaletteProvider>
                <NavProgress />
                <Shortcuts />
                {children}
                <Toaster position="bottom-right" />
              </CommandPaletteProvider>
              </BriefProvider>
            </ChatProvider>
          </PrefsProvider>
        </SessionProvider>
        </UiProvider>
      </TooltipProvider>
    </ThemeProvider>
  );
}
