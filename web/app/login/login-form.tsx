"use client";

import { useState } from "react";
import { Eye, EyeOff, Loader2, Phone, ScanEye, ShieldCheck, Sparkles, Users } from "lucide-react";
import { ApiError, api } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { cn } from "@/lib/utils";

const PASSWORD = "demo1234";
const DEMO = [
  { email: "admin@finsight.demo", name: "Asha Menon", role: "Admin", note: "Everything: process events, add events, Trust & Ops", icon: ShieldCheck },
  { email: "rm@finsight.demo", name: "Rohan Kapoor", role: "Relationship manager", note: "Call list, outcomes and notes, export, ask", icon: Phone },
  { email: "viewer@finsight.demo", name: "Vikram Shah", role: "Viewer", note: "Read only", icon: ScanEye },
  { email: "head@finsight.demo", name: "Meera Joshi", role: "Head", note: "Team view: assign calls, review queue", icon: Users },
  { email: "new.rm@finsight.demo", name: "Neha Iyer", role: "New RM", note: "First sign-in: see the setup guide", icon: Sparkles },
] as const;

/** demo: the demo emails the data service offers ("all" in local dev); an empty list hides the demo box. */
export function LoginForm({ next, demo = [] }: { next: string; demo?: readonly string[] | "all" }) {
  const shown = DEMO.filter((d) => demo === "all" || demo.includes(d.email));
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [show, setShow] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await api.login(email.trim(), password);
      window.location.assign(next);
    } catch (err) {
      setError(err instanceof ApiError && err.status !== 0 ? err.message : "The service did not answer. Please try again.");
      setBusy(false);
    }
  }

  return (
    <>
      <form onSubmit={submit} className="mt-8 space-y-4">
        <div className="space-y-1.5">
          <Label htmlFor="email">Email</Label>
          <Input id="email" type="email" autoComplete="username" required value={email} onChange={(e) => setEmail(e.target.value)} className="h-10 bg-surface" placeholder="name@company.com" />
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="password">Password</Label>
          <div className="relative">
            <Input id="password" type={show ? "text" : "password"} autoComplete="current-password" required value={password} onChange={(e) => setPassword(e.target.value)} className="h-10 bg-surface pr-10" />
            <button type="button" onClick={() => setShow((s) => !s)} aria-label={show ? "Hide password" : "Show password"} className="absolute inset-y-0 right-0 grid w-10 place-items-center text-muted-foreground hover:text-foreground">
              {show ? <EyeOff className="size-4" /> : <Eye className="size-4" />}
            </button>
          </div>
        </div>
        {error ? (
          <p role="alert" className="rounded-lg border border-negative/30 bg-negative-soft px-3 py-2 text-sm text-negative">
            {error}
          </p>
        ) : null}
        <Button type="submit" disabled={busy} className="h-10 w-full bg-brand text-brand-foreground hover:bg-brand/90">
          {busy ? <Loader2 className="animate-spin" /> : null} Sign in
        </Button>
      </form>

      {shown.length === 0 ? null : (
      <div className="mt-8 rounded-xl border bg-surface p-4 shadow-(--shadow-card)">
        <h3 className="text-sm font-semibold">Demo accounts</h3>
        <p className="mt-0.5 text-xs text-muted-foreground">
          Password for every account: <span className="tnum font-medium text-foreground">{PASSWORD}</span>
        </p>
        <ul className="mt-3 divide-y divide-hairline">
          {shown.map((d) => (
            <li key={d.email}>
              <button
                type="button"
                onClick={() => {
                  setEmail(d.email);
                  setPassword(PASSWORD);
                  setError(null);
                }}
                className={cn("flex w-full items-center gap-3 py-2.5 text-left outline-none transition-colors hover:bg-muted/60 focus-visible:bg-muted/60", email === d.email && "bg-brand-soft/60")}
                aria-label={`Fill in the ${d.role} account`}
              >
                <span className="grid size-8 shrink-0 place-items-center rounded-full bg-surface-sunken text-muted-foreground ring-1 ring-inset ring-border">
                  <d.icon className="size-4" />
                </span>
                <span className="min-w-0 flex-1">
                  <span className="flex items-baseline gap-2">
                    <span className="text-[13px] font-medium text-foreground">{d.role}</span>
                    <span className="truncate text-xs text-muted-foreground">{d.email}</span>
                  </span>
                  <span className="block truncate text-xs text-muted-foreground">{d.note}</span>
                </span>
                <span className="text-xs font-medium text-brand-ink">Use</span>
              </button>
            </li>
          ))}
        </ul>
      </div>
      )}
    </>
  );
}
