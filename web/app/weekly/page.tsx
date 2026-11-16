import { Suspense } from "react";
import type { Metadata } from "next";
import { WeeklyPrint } from "@/components/print/weekly-print";

export const metadata: Metadata = { title: "Weekly short list" };

export default function WeeklyPage() {
  return (
    <Suspense>
      <WeeklyPrint />
    </Suspense>
  );
}
