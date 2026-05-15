"use client";

import { useChatStore } from "@/lib/store";

export function StatusBar() {
  const { status, statusText } = useChatStore();
  const dotColor =
    status === "error"
      ? "var(--color-callout-red)"
      : status === "thinking"
        ? "var(--color-cat-food)"
        : "var(--color-success-green)";

  return (
    <div className="px-4 py-2 border-t border-subtle-ash bg-canvas-white flex items-center gap-2 text-[11px] text-midtone-gray">
      <span
        aria-hidden
        className="inline-block w-1.5 h-1.5 rounded-full"
        style={{ backgroundColor: dotColor }}
      />
      <span className="truncate">{statusText}</span>
    </div>
  );
}
