"use client";

import { useCallback, useEffect, useState } from "react";

/**
 * State remembered in localStorage (per browser). The first render always uses `initial` so server and client agree;
 * the stored value is applied right after mount. `loaded` turns true once that has happened.
 */
export function usePersistentState<T>(key: string, initial: T): [T, (next: T | ((prev: T) => T)) => void, boolean] {
  const [value, setValue] = useState<T>(initial);
  const [loaded, setLoaded] = useState(false);

  useEffect(() => {
    const t = setTimeout(() => {
      try {
        const raw = window.localStorage.getItem(key);
        if (raw !== null) {
          const stored = JSON.parse(raw) as T;
          // Objects are merged over the defaults, so a filter added later still has a value.
          setValue(typeof initial === "object" && initial && !Array.isArray(initial) ? ({ ...initial, ...stored } as T) : stored);
        }
      } catch {
        /* a blocked or corrupt store just means defaults */
      }
      setLoaded(true);
    }, 0);
    return () => clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key]);

  const set = useCallback(
    (next: T | ((prev: T) => T)) => {
      setValue((prev) => {
        const resolved = typeof next === "function" ? (next as (p: T) => T)(prev) : next;
        try {
          window.localStorage.setItem(key, JSON.stringify(resolved));
        } catch {
          /* ignore */
        }
        return resolved;
      });
    },
    [key],
  );
  return [value, set, loaded];
}
