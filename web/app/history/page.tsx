import type { Metadata } from "next";
import { PageHeader } from "@/components/ds";
import { HistoryList } from "@/components/history/history-list";

export const metadata: Metadata = { title: "History" };

export default function HistoryPage() {
  return (
    <>
      <PageHeader title="History" description="Every conversation you have had with the control tower: what was asked, what each answer cost, and the context the models were given." />
      <HistoryList />
    </>
  );
}
