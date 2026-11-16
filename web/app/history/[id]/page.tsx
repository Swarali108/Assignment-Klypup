import type { Metadata } from "next";
import { ThreadView } from "@/components/history/thread-view";

export const metadata: Metadata = { title: "Conversation" };

export default async function ThreadPage({ params }: PageProps<"/history/[id]">) {
  const { id } = await params;
  return <ThreadView id={decodeURIComponent(id)} />;
}
