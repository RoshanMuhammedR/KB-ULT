"use client";

import { useRouter } from "next/navigation";
import { useCallback } from "react";
import {
  ChatError,
  Composer,
  ConversationList,
  NewConversationEmpty,
  Thread
} from "@/components/saga/chat";
import { useConversationsStore } from "@/stores/conversations-store";
import { useAsk } from "@/lib/use-ask";

/**
 * A new conversation. The thread is rendered here while the first answer streams, then the
 * URL is swapped for the real /c/[id] once the server has named it — so a reload lands on
 * the saved thread rather than an empty page.
 */
export default function AskPage() {
  const router = useRouter();
  const refresh = useConversationsStore((state) => state.refresh);

  const onCreated = useCallback(
    (created: { id: string }) => {
      window.history.replaceState(null, "", `/app/c/${created.id}`);
      void refresh();
    },
    [refresh]
  );

  const { conversation, streamingId, error, ask, retry, busy } = useAsk({
    onCreated,
    onSettled: refresh
  });

  const started = conversation.messages.length > 0;

  return (
    <div className="grid min-h-dvh grid-rows-[auto_1fr_auto] lg:grid-cols-[300px_1fr] lg:grid-rows-1">
      <div className="hidden h-dvh lg:block">
        <ConversationList />
      </div>

      <div className="flex min-h-0 flex-col lg:h-dvh">
        <div className="min-h-0 flex-1 overflow-y-auto">
          {started ? (
            <Thread conversation={conversation} streamingId={streamingId} />
          ) : (
            <NewConversationEmpty onPick={(question) => void ask(question)} />
          )}
          {error ? (
            <div className="px-5 pb-8 md:px-8">
              <ChatError message={error} onRetry={retry} />
            </div>
          ) : null}
        </div>
        <Composer onSend={(question) => void ask(question)} disabled={busy} />
      </div>

      <button
        type="button"
        onClick={() => router.push("/library")}
        className="border-t border-border px-5 py-3 text-left text-[13px] text-muted-foreground lg:hidden"
      >
        Browse your library →
      </button>
    </div>
  );
}
