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
    setIncrementalPlan,
    resetPlanningState,
    upsertPlanStep,
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
                setIncrementalPlan(event.data.incremental_plan);
                setStatus("thinking", "Drafting a trip plan…");
                break;
              }
              case "plan_step_started": {
                upsertPlanStep(event.data.step, event.data.session_id);
                setStatus("thinking", `Working on ${event.data.step.task}…`);
                break;
              }
              case "plan_step_updated": {
                upsertPlanStep(event.data.step, event.data.session_id);
                setStatus("thinking", `Updating ${event.data.step.task}…`);
                break;
              }
              case "plan_step_completed": {
                upsertPlanStep(event.data.step, event.data.session_id);
                setStatus("thinking", `${event.data.step.task} complete`);
                break;
              }
              case "tool_started": {
                break;
              }
              case "tool_finished": {
                break;
              }
              case "done": {
                streamedItinerary = event.data.itinerary;
                hasFinalItinerary = event.data.itinerary !== null;
                setIncrementalPlan(event.data.incremental_plan);
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
        setIncrementalPlan(history.incremental_plan);
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
      setIncrementalPlan,
      upsertPlanStep,
    ],
  );

  return { sessionId, messages, status, send };
}
