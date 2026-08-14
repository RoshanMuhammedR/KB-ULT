"use client";

import { useParams } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { Pencil, Trash2 } from "lucide-react";
import { Button, ConfirmDialog, Input, Skeleton } from "@kb/ui";
import { ChatError, Composer, ConversationList, Thread } from "@/components/saga/chat";
import type { Conversation } from "@/types/api";
import * as api from "@/lib/api";
import { useConversations } from "@/lib/conversations-context";
import { useAsk } from "@/lib/use-ask";
import { useToast } from "@/lib/toast";
import { useRouter } from "next/navigation";

export default function ConversationPage() {
  const { conversationId } = useParams<{ conversationId: string }>();
  const router = useRouter();
  const toast = useToast();
  const { refresh, rename, remove } = useConversations();

  const [loaded, setLoaded] = useState<Conversation | null>(null);
  const [missing, setMissing] = useState(false);
  const [renaming, setRenaming] = useState(false);
  const [draft, setDraft] = useState("");
  const [confirmingDelete, setConfirmingDelete] = useState(false);
  const [deleting, setDeleting] = useState(false);

  useEffect(() => {
    let cancelled = false;
    api
      .getConversation(conversationId)
      .then((conversation) => {
        if (!cancelled) setLoaded(conversation);
      })
      .catch(() => {
        if (!cancelled) setMissing(true);
      });
    return () => {
      cancelled = true;
    };
  }, [conversationId]);

  const { conversation, streamingId, error, ask, retry, removeMessage, busy } = useAsk({
    initial: loaded,
    onSettled: refresh
  });

  const onDeleteMessage = useCallback(
    (messageId: string) => {
      void removeMessage(messageId).catch(() => toast.error("Couldn't delete that message."));
    },
    [removeMessage, toast]
  );

  async function commitRename() {
    const title = draft.trim();
    setRenaming(false);
    if (!title || title === conversation.title) return;
    try {
      await rename(conversationId, title);
      setLoaded((current) => (current ? { ...current, title } : current));
    } catch {
      toast.error("Couldn't rename that conversation.");
    }
  }

  async function confirmDelete() {
    setDeleting(true);
    try {
      await remove(conversationId);
      router.replace("/");
    } catch {
      toast.error("Couldn't delete that conversation.");
      setDeleting(false);
    }
  }

  if (missing) {
    return (
      <div className="mx-auto max-w-md px-5 py-24 text-center">
        <h1 className="text-display-md">That conversation isn&apos;t here</h1>
        <p className="mt-2 text-sm text-muted-foreground">
          It may have been deleted. Your other threads are still in the list.
        </p>
        <Button className="mt-6" onClick={() => router.push("/")}>
          Start a new conversation
        </Button>
      </div>
    );
  }

  return (
    <div className="grid min-h-dvh lg:grid-cols-[300px_1fr]">
      <div className="hidden h-dvh lg:block">
        <ConversationList activeId={conversationId} />
      </div>

      <div className="flex min-h-0 flex-col lg:h-dvh">
        <header className="flex items-center gap-2 border-b border-border px-5 py-4 md:px-8">
          {renaming ? (
            <form
              className="flex-1"
              onSubmit={(event) => {
                event.preventDefault();
                void commitRename();
              }}
            >
              <Input
                autoFocus
                value={draft}
                aria-label="Conversation title"
                onChange={(event) => setDraft(event.target.value)}
                onBlur={() => void commitRename()}
                className="h-9 text-sm"
              />
            </form>
          ) : (
            <h1 className="min-w-0 flex-1 truncate text-[17px] font-semibold">
              {loaded ? conversation.title : <Skeleton className="h-5 w-56" />}
            </h1>
          )}
          <Button
            variant="ghost"
            size="sm"
            onClick={() => {
              setDraft(conversation.title);
              setRenaming(true);
            }}
          >
            <Pencil className="size-3.5" aria-hidden /> Rename
          </Button>
          <Button variant="danger" size="sm" onClick={() => setConfirmingDelete(true)}>
            <Trash2 className="size-3.5" aria-hidden /> Delete
          </Button>
        </header>

        <div className="min-h-0 flex-1 overflow-y-auto">
          {loaded ? (
            <Thread
              conversation={conversation}
              streamingId={streamingId}
              onDeleteMessage={onDeleteMessage}
            />
          ) : (
            <div className="mx-auto max-w-3xl space-y-6 px-5 py-8 md:px-8">
              <Skeleton className="h-10 w-2/3" />
              <Skeleton className="h-24" />
              <Skeleton className="h-10 w-1/2" />
            </div>
          )}
          {error ? (
            <div className="px-5 pb-8 md:px-8">
              <ChatError message={error} onRetry={retry} />
            </div>
          ) : null}
        </div>

        <Composer onSend={(question) => void ask(question)} disabled={busy} />
      </div>

      {confirmingDelete ? (
        <ConfirmDialog
          title="Delete this conversation?"
          body={`“${conversation.title}” and every message in it will be removed. This can't be undone.`}
          confirmLabel="Delete conversation"
          busy={deleting}
          onConfirm={() => void confirmDelete()}
          onCancel={() => setConfirmingDelete(false)}
        />
      ) : null}
    </div>
  );
}
