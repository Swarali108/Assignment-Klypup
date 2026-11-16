"use client";

import { useState } from "react";
import { Download, FileDown, FileText, Loader2 } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuLabel, DropdownMenuSeparator, DropdownMenuTrigger } from "@/components/ui/dropdown-menu";
import { cn } from "@/lib/utils";

/**
 * "Download" with two formats: PDF (opens the print route, which calls the browser's Save as PDF) and Markdown.
 * Used for a conversation and for a person's call pack.
 */
export function DownloadMenu({
  label = "Download",
  pdfHref,
  onMarkdown,
  what,
  size = "sm",
  variant = "outline",
  className,
  align = "end",
}: {
  label?: string;
  pdfHref: string;
  onMarkdown: () => Promise<void>;
  /** "conversation" / "call pack": named in the menu items. */
  what: string;
  size?: "sm" | "default";
  variant?: "outline" | "ghost";
  className?: string;
  align?: "start" | "end";
}) {
  const [busy, setBusy] = useState(false);
  const md = async () => {
    setBusy(true);
    try {
      await onMarkdown();
    } catch (err) {
      toast.error((err as Error).message || "The download did not start. Try again.");
    } finally {
      setBusy(false);
    }
  };
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button variant={variant} size={size} className={cn("bg-surface", variant === "ghost" && "bg-transparent", className)} disabled={busy}>
          {busy ? <Loader2 className="animate-spin" /> : <Download />}
          {label}
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align={align} className="w-60">
        <DropdownMenuLabel className="text-xs font-normal text-muted-foreground">Download the {what}</DropdownMenuLabel>
        <DropdownMenuSeparator />
        <DropdownMenuItem asChild>
          <a href={pdfHref} target="_blank" rel="noopener">
            <FileDown />
            <span className="flex flex-col">
              <span>PDF</span>
              <span className="text-xs text-muted-foreground">Print-ready, opens Save as PDF</span>
            </span>
          </a>
        </DropdownMenuItem>
        <DropdownMenuItem onSelect={() => void md()}>
          <FileText />
          <span className="flex flex-col">
            <span>Markdown</span>
            <span className="text-xs text-muted-foreground">For notes, email or a CRM</span>
          </span>
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
