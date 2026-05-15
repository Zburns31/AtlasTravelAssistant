"use client";

import { useEffect, useRef, useState } from "react";

import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { useChat } from "@/hooks/useChat";
import { api } from "@/lib/api";
import { useChatStore } from "@/lib/store";
import { MessageBubble } from "./MessageBubble";
import { TypingIndicator } from "./TypingIndicator";

export function ChatPanel() {
  const { messages, status, send } = useChat();
  const sessionId = useChatStore((s) => s.sessionId);
  const setMessages = useChatStore((s) => s.setMessages);
  const setItinerary = useChatStore((s) => s.setItinerary);
  const [input, setInput] = useState("");
  const scrollRef = useRef<HTMLDivElement>(null);

  // Restore history + itinerary on mount.
  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const [history, itinerary] = await Promise.all([
          api.history(sessionId),
          api.getItinerary(sessionId),
        ]);
        if (cancelled) return;
        setMessages(history.messages);
        setItinerary(itinerary);
      } catch {
        /* first load — backend may not be up yet; ignore */
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [sessionId, setMessages, setItinerary]);

  // Auto-scroll to bottom on new messages.
  useEffect(() => {
    scrollRef.current?.scrollTo({
      top: scrollRef.current.scrollHeight,
      behavior: "smooth",
    });
  }, [messages.length, status]);

  function submit(e?: React.FormEvent) {
    e?.preventDefault();
    const text = input;
    setInput("");
    void send(text);
  }

  return (
    <section className="flex flex-col w-[340px] shrink-0 border-r border-subtle-ash bg-canvas-white h-full">
      <header className="flex items-center justify-between px-4 py-3 border-b border-subtle-ash">
        <h2 className="text-[14px] font-semibold text-deep-black">Chat</h2>
        <span className="text-[11px] text-midtone-gray">Session active</span>
      </header>

      <div
        ref={scrollRef}
        className="flex-1 overflow-y-auto px-4 py-4 flex flex-col gap-3 scroll-thin"
      >
        {messages.length === 0 && status === "idle" && (
          <div className="text-[12px] text-midtone-gray">
            Start by describing your trip — e.g. <em>“Plan a 3-day trip to
            Lisbon focused on food and history.”</em>
          </div>
        )}
        {messages.map((m, i) => (
          <MessageBubble key={i} message={m} />
        ))}
        {status === "thinking" && <TypingIndicator />}
      </div>

      <form
        onSubmit={submit}
        className="flex items-center gap-2 p-3 border-t border-subtle-ash"
      >
        <Input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="Describe your trip or refine the itinerary…"
          disabled={status === "thinking"}
          autoFocus
        />
        <Button
          type="submit"
          variant="primary"
          size="md"
          disabled={status === "thinking" || !input.trim()}
          className="px-4"
        >
          Send
        </Button>
      </form>
    </section>
  );
}
