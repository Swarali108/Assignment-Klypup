import type { Metadata } from "next";
import { PageHeader } from "@/components/ds";
import { ReviewView } from "@/components/review/review-view";

export const metadata: Metadata = { title: "Review" };

export default function ReviewPage() {
  return (
    <>
      <PageHeader title="Review" description="Matches and rows the system was not sure about. Your decision applies everywhere at once and is kept with your name." />
      <ReviewView />
    </>
  );
}
