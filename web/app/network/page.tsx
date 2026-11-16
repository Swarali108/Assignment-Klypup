import type { Metadata } from "next";
import { PageHeader } from "@/components/ds";
import { NetworkView } from "@/components/insights/network-view";

export const metadata: Metadata = { title: "Network" };

export default function NetworkPage() {
  return (
    <>
      <PageHeader title="Network" description="Who holds what across events, which holders belong to one household, and who appears in more than one filing." />
      <NetworkView />
    </>
  );
}
