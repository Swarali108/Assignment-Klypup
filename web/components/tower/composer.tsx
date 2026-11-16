"use client";

import { forwardRef, useEffect, useImperativeHandle, useRef, useState } from "react";
import { ArrowUp, Square } from "lucide-react";
import { cn } from "@/lib/utils";

export type ComposerHandle = { focus: () => void; fill: (text: string) => void };

/** The one prompt box: Enter sends, Shift+Enter adds a line, grows up to ~8 lines. */
export const Composer = forwardRef<
  ComposerHandle,
  { onSend: (text: string) => void; onStop?: () => void; busy?: boolean; disabled?: boolean; placeholder?: string; size?: "lg" | "md"; className?: string; footer?: React.ReactNode }
>(function Composer({ onSend, onStop, busy = false, disabled = false, placeholder = "Ask about anyone who came into money", size = "md", className, footer }, ref) {
  const [value, setValue] = useState("");
  const area = useRef<HTMLTextAreaElement>(null);
  useImperativeHandle(ref, () => ({
    focus: () => area.current?.focus(),
    fill: (text: string) => {
      setValue(text);
      requestAnimationFrame(() => area.current?.focus());
    },
  }));

  useEffect(() => {
    const el = area.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, 220)}px`;
  }, [value]);

  const submit = () => {
    const text = value.trim();
    if (!text || busy || disabled) return;
    onSend(text);
    setValue("");
  };

  return (
    <div
      data-tour="prompt"
      className={cn(
        "group/composer relative rounded-2xl border bg-surface shadow-(--shadow-raised) transition-[border-color,box-shadow] duration-200 focus-within:border-brand/35 focus-within:shadow-[0_0_0_4px_var(--brand-soft),var(--shadow-raised)]",
        className,
      )}
    >
      <label htmlFor="prompt" className="sr-only">
        Ask AURELIA
      </label>
      <textarea
        id="prompt"
        ref={area}
        rows={1}
        value={value}
        disabled={disabled}
        onChange={(e) => setValue(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
            e.preventDefault();
            submit();
          }
        }}
        placeholder={placeholder}
        className={cn(
          "block w-full resize-none bg-transparent pr-16 text-foreground caret-brand outline-none placeholder:text-faint focus-visible:outline-none disabled:opacity-60",
          size === "lg" ? "min-h-[5.5rem] px-5 pt-4.5 pb-4 text-base leading-relaxed" : "min-h-[3.25rem] px-4 pt-3.5 pb-3 text-[15px] leading-relaxed",
        )}
      />
      {footer}
      <div className="absolute right-2.5 bottom-2.5">
        {busy ? (
          <button
            type="button"
            onClick={onStop}
            aria-label="Stop answering"
            className="grid size-9 place-items-center rounded-xl bg-foreground text-background transition-transform active:scale-95"
          >
            <Square className="size-3.5 fill-current" />
          </button>
        ) : (
          <button
            type="button"
            onClick={submit}
            disabled={!value.trim() || disabled}
            aria-label="Send"
            className="grid size-9 place-items-center rounded-xl bg-brand text-brand-foreground transition-[transform,opacity,background-color] hover:bg-brand/90 active:scale-95 disabled:bg-secondary disabled:text-faint"
          >
            <ArrowUp className="size-4.5" />
          </button>
        )}
      </div>
    </div>
  );
});
