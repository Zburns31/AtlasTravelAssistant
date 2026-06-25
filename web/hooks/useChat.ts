"use client";

import { useCallback } from "react";

import { api } from "@/lib/api";
import { useChatStore } from "@/lib/store";
import type { ChatStreamEvent, Itinerary } from "@/lib/types";

export function useChat() {
  const {
    sessionId,
    messages,
    status,
    appendMessage,
    setMessages,
    setStatus,
    setItinerary,
    resetPlanningState,
    setTaskPlan,
    appendToolProgress,
  } = useChatStore();

  const send = useCallback(
    async (text: string) => {
      const trimmed = text.trim();
      if (!trimmed) return;

      // Optimistic user bubble + thinking state.
      appendMessage({ role: "user", content: trimmed });
      resetPlanningState();
      setStatus("thinking", "Atlas is thinking…");

      try {
        let streamedItinerary: Itinerary | null = null;
        let hasFinalItinerary = false;
        await api.chatStream(
          {
          message: trimmed,
          session_id: sessionId,
          },
          (event: ChatStreamEvent) => {
            switch (event.event) {
              case "thinking": {
                setStatus("thinking", "Atlas is thinking…");
                break;
              }
              case "plan_ready": {
                setTaskPlan(event.data.task_plan);
                setStatus("thinking", "Drafting a trip plan…");
                break;
              }
              case "tool_started": {
                appendToolProgress(event.data);
                const toolName = event.data.tool ?? "tool";
                setStatus("thinking", `Running ${toolName}…`);
                break;
              }
              case "tool_finished": {
                appendToolProgress(event.data);
                const toolName = event.data.tool ?? "tool";
                setStatus("thinking", `Updated from ${toolName}`);
                break;
              }
              case "done": {
                streamedItinerary = event.data.itinerary;
                hasFinalItinerary = event.data.itinerary !== null;
                setTaskPlan(event.data.task_plan ?? []);
                setItinerary(event.data.itinerary);
                break;
              }
              case "error": {
                throw new Error(event.data.detail ?? "Streaming chat failed");
              }
            }
          },
        );

        // Sync history from server — it's the source of truth.
        const history = await api.history(sessionId);
        setMessages(history.messages);
        setItinerary(streamedItinerary);
        setStatus(
          "idle",
          hasFinalItinerary ? "Itinerary ready" : "Response received",
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
    [
      sessionId,
      appendMessage,
      resetPlanningState,
      setMessages,
      setStatus,
      setItinerary,
      setTaskPlan,
      appendToolProgress,
    ],
  );

  return { sessionId, messages, status, send };
}
