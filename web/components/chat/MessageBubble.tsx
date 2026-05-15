"use client";

import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

import { cn } from "@/lib/cn";
import type { HistoryMessage } from "@/lib/types";

function fmtTime(d = new Date()) {
  return d.toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });
}

interface Props {
  message: HistoryMessage;
  timestamp?: string;
}

export function MessageBubble({ message, timestamp = fmtTime() }: Props) {
  const isUser = message.role === "user";
  return (
    <div
      className={cn(
        "flex flex-col max-w-[85%]",
        isUser ? "self-end items-end" : "self-start items-start",
      )}
    >
      <div
        className={cn(
          "rounded-[14px] px-3 py-2 text-[13px] leading-[1.5]",
          isUser
            ? "bg-deep-black text-canvas-white"
            : "bg-ghost-gray text-rich-black markdown-surface",
        )}
      >
        {isUser ? (
          message.content
        ) : (
          <ReactMarkdown remarkPlugins={[remarkGfm]}>
            {message.content}
          </ReactMarkdown>
        )}
      </div>
      <span className="text-[11px] text-midtone-gray mt-1">
        {isUser ? timestamp : `Atlas · ${timestamp}`}
      </span>
    </div>
  );
}
