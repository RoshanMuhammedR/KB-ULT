"use client";

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
    <div className="flex h-full min-h-0 lg:grid lg:grid-cols-[280px_1fr]">
      <div className="hidden min-h-0 lg:block">
        <ConversationList />
      </div>

      <div className="flex min-h-0 w-full flex-col">
        <div className="min-h-0 flex-1 overflow-y-auto">
          {started ? (
            <Thread
              conversation={conversation}
              streamingId={streamingId}
              onAsk={(question) => void ask(question)}
            />
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
    </div>
  );
}
