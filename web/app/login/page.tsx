import type { Metadata } from "next";
import { Wordmark } from "@/components/ds";
import { LoginForm } from "./login-form";
import { FilingTrace } from "./filing-trace";

export const metadata: Metadata = { title: "Sign in" };

/** Where to go after sign-in: only a path on this site. Parsed, not prefix-matched, so "/\t/evil" or "/\\evil" fall back to "/". */
function safeNext(value: unknown): string {
  if (typeof value !== "string" || !value.startsWith("/") || /[\x00-\x1f\x7f\\]/.test(value)) return "/";
  try {
    const url = new URL(value, "http://same.origin");
    if (url.origin !== "http://same.origin") return "/";
    // Normalising "/.//evil" gives the path "//evil" (protocol-relative): collapse leading slashes.
    return `${url.pathname.replace(/^\/+/, "/")}${url.search}${url.hash}`;
  } catch {
    return "/";
  }
}

/**
 * Which demo accounts to offer, as the data service says (it decides: none in production unless DEMO_ACCOUNTS=1, and
 * never the admin there). If the service does not answer: none when APP_ENV=production here, else all (local dev).
 */
async function demoAccounts(): Promise<string[] | "all"> {
  const productionHere = /^prod(uction)?$/i.test((process.env.APP_ENV ?? "").trim());
  try {
    const base = (process.env.API_ORIGIN || process.env.API_INTERNAL_ORIGIN || "http://127.0.0.1:8000").replace(/\/+$/, "");
    const res = await fetch(`${base}/api/auth/config`, { cache: "no-store" });
    if (res.ok) {
      const config = (await res.json()) as { production?: boolean; demo_accounts?: string[] };
      if (Array.isArray(config.demo_accounts)) return config.demo_accounts;
      return productionHere || config.production ? [] : "all";
    }
  } catch {
    // The data service is unreachable; fall through to the local setting.
  }
  return productionHere ? [] : "all";
}

export default async function LoginPage({ searchParams }: PageProps<"/login">) {
  const sp = await searchParams;
  const next = safeNext(sp.next);
  const demo = await demoAccounts();
  const hasDemo = demo === "all" || demo.length > 0;
  return (
    <main className="grid min-h-dvh bg-background lg:grid-cols-[minmax(0,1.1fr)_minmax(0,1fr)]">
      <section className="relative hidden flex-col justify-between overflow-hidden border-r bg-sidebar px-12 py-11 lg:flex xl:px-16">
        <Wordmark />
        <div className="flex flex-col gap-10">
          <div className="max-w-[30rem]">
            <h1 className="text-[2.25rem] leading-[1.1] font-semibold tracking-[-0.03em] text-foreground">
              Every rupee, traced to the line it came from.
            </h1>
            <p className="mt-4 text-[15px] leading-relaxed text-muted-foreground">
              AURELIA reads the filings behind every IPO, buyback and offer for sale, checks each figure on its page, and only then puts a
              name on your call list.
            </p>
          </div>
          <FilingTrace />
        </div>
        <p className="text-xs text-faint">A real line from a real filing.{hasDemo ? " Demonstration environment with sample accounts." : ""}</p>
      </section>
      <section className="flex flex-col justify-center px-5 py-8 sm:px-10">
        <div className="mx-auto w-full max-w-[420px]">
          <Wordmark className="mb-6 lg:hidden" />
          <div className="mb-8 lg:hidden">
            <p className="mb-3 text-[15px] leading-snug font-semibold tracking-[-0.01em] text-foreground">Every rupee, traced to the line it came from.</p>
            <FilingTrace compact />
          </div>
          <h2 className="text-[26px] font-semibold tracking-[-0.02em]">Sign in</h2>
          <p className="mt-1.5 text-sm text-muted-foreground">{hasDemo ? "Use your work email, or pick a demo account below." : "Use your work email."}</p>
          <LoginForm next={next} demo={demo} />
        </div>
      </section>
    </main>
  );
}
