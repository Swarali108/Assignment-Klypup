import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { Suspense } from "react";
import { SkeletonList } from "@/components/ds";
import { Gallery } from "./gallery";

export const metadata: Metadata = { title: "Component gallery" };

export default function GalleryPage() {
  if (process.env.NEXT_PUBLIC_ENABLE_DEV !== "1") notFound(); // dev-only gallery; off in the demo and production
  return (
    <Suspense fallback={<SkeletonList rows={6} />}>
      <Gallery />
    </Suspense>
  );
}
