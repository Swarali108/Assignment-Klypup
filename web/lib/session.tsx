"use client";

import { createContext, useContext, useEffect, useMemo, useState } from "react";
import { usePathname, useRouter } from "next/navigation";
import { api, type SessionUser } from "@/lib/api";

type Permission = keyof SessionUser["permissions"];
type Ctx = { user: SessionUser | null; loading: boolean; can: (p: Permission) => boolean; signOut: () => Promise<void> };
const SessionCtx = createContext<Ctx>({ user: null, loading: true, can: () => false, signOut: async () => {} });

export const ROLE_LABEL: Record<SessionUser["role"], string> = { admin: "Admin", head: "Head of RMs", rm: "Relationship manager", viewer: "Viewer" };

/** Who is signed in and what their role may do. The data service is the real gate; this only hides what would be refused. */
export function SessionProvider({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const [user, setUser] = useState<SessionUser | null>(null);
  const [loading, setLoading] = useState(true);
  const onLogin = pathname.startsWith("/login");

  useEffect(() => {
    if (onLogin) return;
    let live = true;
    api
      .me()
      .then((u) => live && setUser(u))
      .catch(() => live && setUser(null))
      .finally(() => live && setLoading(false));
    return () => {
      live = false;
    };
  }, [onLogin]);

  const value = useMemo<Ctx>(
    () => ({
      user,
      loading,
      can: (p) => !!user?.permissions[p],
      signOut: async () => {
        try {
          await api.logout();
        } finally {
          setUser(null);
          router.replace("/login");
          router.refresh();
        }
      },
    }),
    [user, loading, router],
  );
  return <SessionCtx.Provider value={value}>{children}</SessionCtx.Provider>;
}

export const useSession = () => useContext(SessionCtx);
