import { Suspense } from "react";
import type { Metadata } from "next";
import { ConversationPrint } from "@/components/print/conversation-print";

export const metadata: Metadata = { title: "Conversation report" };

export default async function ConversationPrintPage({ params }: PageProps<"/history/[id]/print">) {
  const { id } = await params;
  return (
    <Suspense>
      <ConversationPrint id={decodeURIComponent(id)} />
    </Suspense>
  );
}
