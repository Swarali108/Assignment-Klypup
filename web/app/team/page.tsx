import type { Metadata } from "next";
import { PageHeader } from "@/components/ds";
import { TeamView } from "@/components/team/team-view";

export const metadata: Metadata = { title: "Team" };

export default function TeamPage() {
  return (
    <>
      <PageHeader title="Team" description="Calls, meetings and wins per RM and per event type, live from what the RMs log." />
      <TeamView />
    </>
  );
}
