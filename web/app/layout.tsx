import type { Metadata } from "next";
import "@fontsource-variable/inter";
import "./globals.css";
import { AppShell, Providers } from "@/components/ds";

export const metadata: Metadata = {
  title: { default: "FinSight", template: "%s · FinSight" },
  description: "Who to call today, why, and how much: money events turned into a call list.",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="en-IN" suppressHydrationWarning className="h-full">
      <body className="min-h-full">
        <Providers>
          <AppShell>{children}</AppShell>
        </Providers>
      </body>
    </html>
  );
}
