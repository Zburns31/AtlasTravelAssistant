import { Badge } from "@/components/ui/Badge";
import { SOURCE_LABEL } from "@/lib/categoryStyles";
import { fmtDate, fmtMoney } from "@/lib/format";
import type { ItineraryDay } from "@/lib/types";
import { ActivityCard } from "./ActivityCard";
import { TravelConnector } from "./TravelConnector";

function dayLabel(iso: string) {
  return fmtDate(iso, {
    weekday: "short",
    month: "short",
    day: "numeric",
  });
}

export function DaySection({
  day,
  dayNum,
}: {
  day: ItineraryDay;
  dayNum: number;
}) {
  const cost =
    day.activities.reduce(
      (sum, a) => sum + (a.estimated_cost_usd ?? 0),
      0,
    ) +
    day.travel_segments.reduce(
      (sum, s) => sum + (s.estimated_cost_usd ?? 0),
      0,
    );

  return (
    <section className="mt-4">
      <header className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          <h3 className="text-[16px] font-semibold text-deep-black">
            Day {dayNum}
          </h3>
          <span className="text-[12px] text-midtone-gray">
            {dayLabel(day.date)}
          </span>
          <Badge
            variant={day.source === "user" ? "inverse" : "neutral"}
          >
            {SOURCE_LABEL[day.source]}
          </Badge>
        </div>
        {cost > 0 && (
          <span className="text-[12px] text-midtone-gray">
            ~{fmtMoney(cost)}
          </span>
        )}
      </header>
      {day.title && (
        <p className="text-[13px] text-rich-black mb-2 italic">{day.title}</p>
      )}
      <div className="relative">
        {/* Vertical timeline line */}
        <div
          aria-hidden
          className="absolute left-[5px] top-2 bottom-2 w-px bg-subtle-ash"
        />
        <div className="flex flex-col gap-2">
          {day.activities.map((a, i) => (
            <div key={`a-${i}`}>
              <ActivityCard activity={a} />
              {day.travel_segments[i] && (
                <TravelConnector segment={day.travel_segments[i]} />
              )}
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}
