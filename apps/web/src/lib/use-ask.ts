"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import type { Citation, Conversation, Message } from "@/types/api";
import * as api from "@/lib/api";

const EMPTY: Conversation = {
  id: "",
  title: "",
  messages: [],
  created_at: null,
  updated_at: null
};

let localSeq = 0;
const localId = (prefix: string) => `${prefix}-local-${++localSeq}`;

/**
 * Drives a conversation: renders the question immediately, streams the answer in, and
 * reconciles with the ids the server assigns when it finishes.
 *
 * A failure mid-stream removes the optimistic pair entirely rather than leaving half an
 * answer on screen, because the server persisted nothing either — that's what lets the error
 * honestly say "nothing was saved, so you can ask it again as-is".
 */
export function useAsk({
  initial,
  onCreated,
  onSettled
}: {
  initial?: Conversation | null;
  onCreated?: (conversation: { id: string; title: string }) => void;
  onSettled?: () => void;
} = {}) {
  const [conversation, setConversation] = useState<Conversation>(initial ?? EMPTY);
  const [streamingId, setStreamingId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const lastQuestion = useRef<string | null>(null);
  const abort = useRef<AbortController | null>(null);

  useEffect(() => {
    if (initial) setConversation(initial);
  }, [initial]);

  // Navigating away mid-answer cancels the request rather than leaking it.
  useEffect(() => {
    return () => abort.current?.abort();
  }, []);

  const ask = useCallback(
    async (question: string) => {
      setError(null);
      lastQuestion.current = question;

      const userId = localId("user");
      const assistantId = localId("assistant");
      const askedAt = new Date().toISOString();

      const userMessage: Message = {
        id: userId,
        role: "user",
        content: question,
        citations: [],
        insufficient_context: false,
        created_at: askedAt
      };
      const assistantMessage: Message = {
        id: assistantId,
        role: "assistant",
        content: "",
        citations: [],
        insufficient_context: false,
        created_at: askedAt
      };

      setConversation((current) => ({
        ...current,
        messages: [...current.messages, userMessage, assistantMessage]
      }));
      setStreamingId(assistantId);

      const controller = new AbortController();
      abort.current = controller;
      const conversationId = conversation.id || null;

      const patchAssistant = (patch: Partial<Message>) =>
        setConversation((current) => ({
          ...current,
          messages: current.messages.map((message) =>
            message.id === assistantId ? { ...message, ...patch } : message
          )
        }));

      try {
        let streamed = "";
        await api.streamAnswer(
          conversationId,
          question,
          {
            onConversation: (created) => {
              setConversation((current) =>
                current.id ? current : { ...current, id: created.id, title: created.title }
              );
              if (!conversationId) onCreated?.(created);
            },
            onDelta: (delta) => {
              streamed += delta;
              patchAssistant({ content: streamed });
            },
            onCitations: (citations: Citation[]) => patchAssistant({ citations }),
            onDone: (done) =>
              patchAssistant({
                id: done.message_id,
                insufficient_context: done.insufficient_context
              })
          },
          controller.signal
        );
        setStreamingId(null);
        onSettled?.();
      } catch (err) {
        if (controller.signal.aborted) return; // navigated away; not an error worth showing
        setStreamingId(null);
        // Drop both optimistic messages: the server saved neither.
        setConversation((current) => ({
          ...current,
          messages: current.messages.filter(
            (message) => message.id !== userId && message.id !== assistantId
          )
        }));
        setError(err instanceof Error ? err.message : "That question didn't get through.");
      } finally {
        abort.current = null;
      }
    },
    [conversation.id, onCreated, onSettled]
  );

  const retry = useCallback(() => {
    if (lastQuestion.current) void ask(lastQuestion.current);
  }, [ask]);

  const removeMessage = useCallback(
    async (messageId: string) => {
      if (!conversation.id) return;
      const previous = conversation.messages;
      setConversation((current) => ({
        ...current,
        messages: current.messages.filter((message) => message.id !== messageId)
      }));
      try {
        await api.deleteMessage(conversation.id, messageId);
        onSettled?.();
      } catch {
        setConversation((current) => ({ ...current, messages: previous }));
        throw new Error("Couldn't delete that message.");
      }
    },
    [conversation.id, conversation.messages, onSettled]
  );

  return {
    conversation,
    streamingId,
    error,
    ask,
    retry,
    removeMessage,
    busy: streamingId !== null
  };
}
