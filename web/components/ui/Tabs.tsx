"use client";

import { cn } from "@/lib/cn";

interface Tab<T extends string> {
  id: T;
  label: string;
}

interface TabsProps<T extends string> {
  tabs: Tab<T>[];
  value: T;
  onChange: (id: T) => void;
}

export function Tabs<T extends string>({
  tabs,
  value,
  onChange,
}: TabsProps<T>) {
  return (
    <div
      className="inline-flex items-center gap-1 p-1 bg-ghost-gray rounded-[10px]"
      role="tablist"
    >
      {tabs.map((t) => (
        <button
          key={t.id}
          role="tab"
          aria-selected={t.id === value}
          onClick={() => onChange(t.id)}
          className={cn(
            "px-3 py-1 text-[13px] font-medium rounded-[8px] transition-colors",
            t.id === value
              ? "bg-canvas-white text-deep-black shadow-[var(--shadow-elevated)]"
              : "text-midtone-gray hover:text-rich-black",
          )}
        >
          {t.label}
        </button>
      ))}
    </div>
  );
}
