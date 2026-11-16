"use client";

import { useSession } from "@/lib/session";

/** Renders its children only when the signed-in role has the permission (the data service enforces it too). */
export function Can({ permission, children, fallback = null }: { permission: "edit_rm" | "export" | "ask" | "process" | "ops" | "team" | "review"; children: React.ReactNode; fallback?: React.ReactNode }) {
  const { can } = useSession();
  return <>{can(permission) ? children : fallback}</>;
}
