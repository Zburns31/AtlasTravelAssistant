"use client";

import { useCallback } from "react";

import { api } from "@/lib/api";
import { useChatStore } from "@/lib/store";

export function useChat() {
  const {
    sessionId,
    messages,
    status,
    appendMessage,
    setMessages,
    setStatus,
    setItinerary,
  } = useChatStore();

  const send = useCallback(
    async (text: string) => {
      const trimmed = text.trim();
      if (!trimmed) return;

      // Optimistic user bubble + thinking state.
      appendMessage({ role: "user", content: trimmed });
      setStatus("thinking", "Atlas is thinking…");

      try {
        const resp = await api.chat({
          message: trimmed,
          session_id: sessionId,
        });

        // Sync history from server — it's the source of truth.
        const history = await api.history(sessionId);
        setMessages(history.messages);
        setItinerary(resp.itinerary);
        setStatus(
          "idle",
          resp.itinerary ? "Itinerary ready" : "Response received",
        );
      } catch (err) {
        const detail = err instanceof Error ? err.message : String(err);
        appendMessage({
          role: "assistant",
          content: `⚠️ ${detail}`,
        });
        setStatus("error", detail);
      }
    },
    [sessionId, appendMessage, setMessages, setStatus, setItinerary],
  );

  return { sessionId, messages, status, send };
}
