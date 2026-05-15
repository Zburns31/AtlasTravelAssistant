"use client";

import { useState } from "react";

import { Badge } from "@/components/ui/Badge";
import { CATEGORY_COLOR, CATEGORY_LABEL } from "@/lib/categoryStyles";
import { cn } from "@/lib/cn";
import { fmtMoney, fmtTime } from "@/lib/format";
import type { Activity } from "@/lib/types";

export function ActivityCard({ activity: a }: { activity: Activity }) {
  const [open, setOpen] = useState(false);
  const timeLabel = a.start_time
    ? `${fmtTime(a.start_time)}${a.end_time ? ` – ${fmtTime(a.end_time)}` : ""}`
    : a.duration_minutes
      ? `${a.duration_minutes} min`
      : "";

  return (
    <div className="relative pl-6">
      {/* Timeline dot */}
      <span
        aria-hidden
        className="absolute left-0 top-2 w-3 h-3 rounded-full border-2 border-canvas-white"
        style={{ backgroundColor: CATEGORY_COLOR[a.category] }}
      />
      <div className="rounded-[10px] border border-subtle-ash bg-canvas-white">
        <button
          type="button"
          onClick={() => setOpen((v) => !v)}
          className="w-full flex items-start justify-between gap-3 px-3 py-2 text-left"
        >
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2 flex-wrap">
              <span className="text-[14px] font-medium text-deep-black">
                {a.title}
              </span>
              <Badge
                variant="outline"
                style={{
                  borderColor: CATEGORY_COLOR[a.category],
                  color: CATEGORY_COLOR[a.category],
                }}
              >
                {CATEGORY_LABEL[a.category]}
              </Badge>
            </div>
            <div className="flex items-center gap-3 mt-1 text-[12px] text-midtone-gray">
              {timeLabel && <span>🕒 {timeLabel}</span>}
              {a.location && <span>📍 {a.location}</span>}
              {a.estimated_cost_usd != null && (
                <span>💰 {fmtMoney(a.estimated_cost_usd)}</span>
              )}
            </div>
          </div>
          <span
            className={cn(
              "text-midtone-gray text-[12px] mt-1 transition-transform",
              open && "rotate-180",
            )}
            aria-hidden
          >
            ▾
          </span>
        </button>
        {open && (
          <div className="px-3 pb-3 -mt-1 text-[12px] text-rich-black">
            {a.description && <p>{a.description}</p>}
            {a.notes.length > 0 && (
              <ul className="mt-2 list-disc list-inside text-midtone-gray">
                {a.notes.map((n, i) => (
                  <li key={i}>{n.content}</li>
                ))}
              </ul>
            )}
            {a.booking_url && (
              <a
                href={a.booking_url}
                target="_blank"
                rel="noopener noreferrer"
                className="inline-block mt-2 text-deep-black underline"
              >
                Booking link ↗
              </a>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
