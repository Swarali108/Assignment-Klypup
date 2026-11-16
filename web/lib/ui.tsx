"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";

const KEY = "aurelia.boardroom";

type Ctx = {
  /** Boardroom mode: costs, model names and technical chips hidden; larger type and spacing, for presenting. */
  boardroom: boolean;
  setBoardroom: (on: boolean) => void;
  toggleBoardroom: () => void;
  shortcutsOpen: boolean;
  setShortcutsOpen: (open: boolean) => void;
};
const UiCtx = createContext<Ctx | null>(null);

/** Presentation settings that belong to the browser, not the account. Boardroom mode is remembered. */
export function UiProvider({ children }: { children: React.ReactNode }) {
  const [boardroom, setOn] = useState(false);
  const [shortcutsOpen, setShortcutsOpen] = useState(false);

  useEffect(() => {
    const t = setTimeout(() => {
      try {
        setOn(window.localStorage.getItem(KEY) === "1");
      } catch {
        /* blocked storage: stays off */
      }
    }, 0);
    return () => clearTimeout(t);
  }, []);

  useEffect(() => {
    const root = document.documentElement;
    if (boardroom) root.setAttribute("data-boardroom", "");
    else root.removeAttribute("data-boardroom");
  }, [boardroom]);

  const setBoardroom = useCallback((on: boolean) => {
    setOn(on);
    try {
      window.localStorage.setItem(KEY, on ? "1" : "0");
    } catch {
      /* ignore */
    }
  }, []);
  const toggleBoardroom = useCallback(() => setBoardroom(!boardroom), [boardroom, setBoardroom]);

  const value = useMemo(
    () => ({ boardroom, setBoardroom, toggleBoardroom, shortcutsOpen, setShortcutsOpen }),
    [boardroom, setBoardroom, toggleBoardroom, shortcutsOpen],
  );
  return <UiCtx.Provider value={value}>{children}</UiCtx.Provider>;
}

export function useUi() {
  const c = useContext(UiCtx);
  if (!c) throw new Error("useUi must be used inside <UiProvider>");
  return c;
}
