import type { Metadata } from "next";
import { PageHeader } from "@/components/ds";
import { MoneyCalendar } from "@/components/insights/money-calendar";

export const metadata: Metadata = { title: "Calendar" };

export default function CalendarPage() {
  return (
    <>
      <PageHeader title="Calendar" description="When money reaches people: listing days, lock-in ends and buyback payments, with the amount due on each date." />
      <MoneyCalendar />
    </>
  );
}
